"""Apply explicit user rejections to a saved grammar ladder without model calls."""
import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path

from evaluation.scripts.pipeline import build_mixed_grammar_ladder as b
from evaluation.scripts.variants.current import grammar_adjudications as a
from evaluation.scripts.variants.current import mixed_grammar as m


def apply(data):
    revised = deepcopy(data); changes = []
    for w in revised['windows']:
        w['candidates'] = [a.apply_candidate(c) for c in w['candidates']]
        candidates = {c['candidate_id']: c for c in w['candidates']}
        for v in w['variants']:
            selected = [candidates[cid] for cid in v.get('selected_ids', [])]
            decisions = {d['id']: d for c in selected for d in a.decisions_for(c)}
            if decisions:
                changes.append(dict(id=w['id'], reference=w['reference'], rate=v['rate'],
                    previous_status=v['status'], status='needs_repair',
                    selected_ids=v['selected_ids'], manual_adjudications=list(decisions.values())))
                v['model_status'] = v.get('model_status', v['status'])
                v.update(status='needs_repair', reason='manual_rejection',
                         manual_adjudications=list(decisions.values()), eligible_for_publication=False)
                v['combined'] = a.apply_review(v['combined'], selected)
            if v['status'] == 'pass':
                assert all(a.eligible(c) for c in selected)
    rates = {}
    for rate in revised['configuration']['rates']:
        vs = [v for w in revised['windows'] for v in w['variants'] if v['rate'] == rate]
        def counts(rows):
            ss = [v['selection'] for v in rows if v['selection']]
            return dict(misselection=sum(s['misselection_count'] for s in ss),
                        misordering=sum(s['edit_count']-s['misselection_count'] for s in ss))
        passed = [v for v in vs if v['status'] == 'pass']
        rates[f'{rate:g}'] = dict(statuses=dict(Counter(v['status'] for v in vs)),
            all_selected=counts(vs), passing_selected=counts(passed),
            passing_actual_doses=[v['selection']['actual_percent'] for v in passed])
    revised['summary'] = dict(rates=rates,
        statuses=dict(Counter(v['status'] for w in revised['windows'] for v in w['variants'])),
        manual_rejections=len(changes))
    return revised, changes


def run(args):
    args.source = args.source.resolve(); args.output = args.output.resolve()
    if args.output == args.source.parent:
        raise ValueError('Keep the original model-run results in a separate directory')
    source_bytes = args.source.read_bytes(); original = json.loads(source_bytes)
    revised, changes = apply(original)
    revised['configuration'].update(adjudication_policy=a.POLICY,
        adjudication_source=str(args.source), adjudication_source_sha256=sha256(source_bytes).hexdigest(),
        adjudication_rules_sha256=sha256(Path(a.__file__).read_bytes()).hexdigest(),
        manual_review=True, manual_candidate_wording=False,
        reselection_performed=False, new_model_calls=0, published=False)
    for old, new in zip(original['windows'], revised['windows']):
        assert old['clean'] == new['clean']
        for ov, nv in zip(old['variants'], new['variants']):
            for field in ('draft', 'selection', 'selected_ids', 'draft_sha256'):
                assert ov.get(field) == nv.get(field)
    m.save(args.output / 'results.json', revised)
    m.save(args.output / 'manual_rejections.json', changes)
    m.save(args.output / 'held_variants.json', [dict(id=w['id'], reference=w['reference'], **v)
        for w in revised['windows'] for v in w['variants'] if v['status'] != 'pass'])
    m.save(args.output / 'approved_window_drafts.json', dict(published=False,
        adjudication_policy=a.POLICY, windows=[dict(id=w['id'], source_sha256=w['source_sha256'],
            variants=[v for v in w['variants'] if v['status'] == 'pass']) for w in revised['windows']]))
    b.render_report(revised, args.report)
    indices = {w['id']: i for i, w in enumerate(revised['windows'])}
    block = ['<h2>Manual rejections</h2><p>These are explicit user review decisions, '
             'not manually written passages. Original model evidence remains visible. '
             'Affected versions are rejected and excluded from the approved draft package; '
             'no replacements or live publication were performed.</p><table><tr><th>Window</th>'
             '<th>Dose</th><th>Previous model status</th><th>Current decision</th></tr>']
    for change in changes:
        block.append(f'<tr><td><a href="#w{indices[change["id"]]}r{change["rate"]:g}">'
            + escape(change['reference']) + f'</a></td><td>{change["rate"]:g}%</td><td>'
            + escape(change['previous_status']) + '</td><td>Rejected by user: '
            + escape('; '.join(d['reason'] for d in change['manual_adjudications'])) + '</td></tr>')
    block.append('</table>')
    html = args.report.read_text().replace('<h2>Window overview</h2>', ''.join(block) + '<h2>Window overview</h2>')
    html = html.replace('Only approved candidates enter selection;',
        'Selections preserve the original model run; subsequent user rejections override its approvals;')
    html = html.replace('Unattainable', 'No approved combination')
    args.report.write_text(html)
    class Parsed(HTMLParser):
        def __init__(self):
            super().__init__(); self.ids=[]; self.links=[]; self.parts=[]
        def handle_starttag(self, tag, attrs):
            attrs=dict(attrs)
            if 'id' in attrs: self.ids.append(attrs['id'])
            if attrs.get('href','').startswith('#'): self.links.append(attrs['href'][1:])
        def handle_data(self, data): self.parts.append(data)
    parsed=Parsed(); parsed.feed(html)
    assert len(parsed.ids)==len(set(parsed.ids)) and set(parsed.links)<=set(parsed.ids)
    visible=''.join(parsed.parts)
    for w in revised['windows']:
        for v in w['variants']:
            assert all(t in visible for t in (v['draft'] or {}).values())
    assert args.source.read_bytes() == source_bytes
    m.save(args.output / 'verification.json', dict(complete=True, source_results_unchanged=True,
        all_passages_and_selections_unchanged=True, rejected_edits_excluded_from_approved_package=True,
        manual_review_marked=True, html_drafts_and_links_verified=True, model_calls=0,
        published_materials_changed=False, report_sha256=sha256(args.report.read_bytes()).hexdigest()))
    print(json.dumps(dict(changes=changes, summary=revised['summary']['statuses']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    run(p.parse_args())
