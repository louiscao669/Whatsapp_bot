"""Create reviewed mixed grammar drafts; default scope is 1 Kings 13 only."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from dotenv import load_dotenv

from evaluation.scripts.variants.current import create_grammar_variants as g
from evaluation.scripts.variants.current import mixed_grammar as m
from evaluation.scripts.pipeline import review_grammar_windows as audit

ROOT = Path(__file__).resolve().parents[3]
NAMES = ROOT / 'evaluation/datasets/pseudonym_remap/name_map_tier1_sol_reviewed122.json'
DEFAULT_RUN = ROOT / 'evaluation/runs/sol_mixed_grammar_word_class_1kgs13_2026-11-22'
DEFAULT_REPORT = ROOT / 'deliverables/sol_mixed_grammar_word_class_1kgs13.html'


def read(path):
    return json.loads(path.read_text())


def names_for(window, name_map):
    text = ''.join(window['conditions']['clean']['verses'].values())
    names = set()
    for entity in name_map['entities']:
        if entity.get('type') not in ('person', 'place', 'people', 'deity'):
            continue
        for name in entity.get('release_forms', {}).get('zh', {}):
            if name and name in text:names.add(name)
    return sorted(names)


def review(request, judge, meanings):
    judge_id, judgment = judge.call(request)
    meaning_id, meaning = meanings.evaluate(request)
    status = m.outcome(judgment, meaning, request['edited_clause'])
    result = dict(status=status, grammar=judgment, meaning=meaning,
                  grammar_review_id=judge_id, meaning_review_id=meaning_id)
    edits = request.get('selected_edits') or [dict(
        before=request['original_clause'], after=request['edited_clause'])]
    return m.adjudications.apply_review(result, edits)


def candidates_from_proposals(window, units, response, proposal_id, lexical_response=None, lexical_id=None):
    candidates = []
    for proposal in response['candidates']:
        unit = units[proposal['unit_index']]
        candidates.append(dict(verse=unit['verse'], start=unit['start'],
            before=unit['text'], after=proposal['edited_clause'], content_chars=unit['content_chars'],
            subtype=proposal['subtype'], provenance='model_proposal', proposal_id=proposal_id,
            proposal_explanation=proposal['explanation']))
    # Existing misordering candidates enter the new review; old approvals are
    # not silently treated as approvals under this different grammar policy.
    for edit in window['conditions']['grammar30']['edits']:
        enclosing = [u for u in units if u['verse'] == edit['verse']
                     and u['start'] <= edit['start']
                     and edit['start'] + len(edit['before']) <= u['start'] + len(u['text'])]
        if len(enclosing) != 1:
            raise g.GrammarError('Existing misordering edit lacks one enclosing source clause')
        unit = enclosing[0];relative = edit['start'] - unit['start']
        if unit['text'][relative:relative + len(edit['before'])] != edit['before']:
            raise g.GrammarError('Existing misordering edit has stale source text')
        normalized = dict(verse=edit['verse'], start=unit['start'], before=unit['text'],
            after=unit['text'][:relative] + edit['after'] + unit['text'][relative + len(edit['before']):])
        # Preserve the original edit separately. Expanding its review focus to
        # the enclosing clause also counts that entire clean clause in the dose.
        # An older phrase-sized edit must not silently make a clause dose fit.
        if normalized != edit:
            normalized.update(imported_edit=edit, dose_unit_expanded_to_enclosing_clause=True)
        candidates.append(dict(**normalized, content_chars=unit['content_chars'],
            subtype='misordering', provenance='existing_misordering_candidate',
            proposal_id=None, proposal_explanation='Existing selected grammar edit; independently re-reviewed.'))
    for proposal in (lexical_response or {}).get('candidates', []):
        unit = units[proposal['unit_index']]
        candidates.append(dict(verse=unit['verse'], start=unit['start'],
            before=unit['text'], after=proposal['edited_clause'], content_chars=unit['content_chars'],
            subtype='word_form', word_form_mechanism='lexical_word_class',
            word_class_transition={k: proposal[k] for k in ('source_form', 'target_form', 'source_word_class', 'target_word_class')},
            provenance='model_word_class_proposal', proposal_id=lexical_id,
            proposal_explanation=proposal['explanation']))
    for candidate in candidates:
        candidate['family'] = 'misordering' if candidate['subtype'] == 'misordering' else 'misselection'
        candidate['operations'] = m.edit_operations(candidate['before'], candidate['after'])
        candidate['candidate_id'] = g.json_digest(dict(window_id=window['id'], **candidate))
    return candidates


def reuse_review_caches(source, target):
    """Copy records, never approvals by status. Consumers revalidate exact keys."""
    for filename, field in [('proposals.json', 'records'), ('grammar_reviews.json', 'records'),
                            ('word_class_proposals.json', 'records'), ('word_class_reviews.json', 'records'),
                            ('meaning_readings.json', 'readings'), ('meaning_judgments.json', 'reviews')]:
        old = source / filename
        if not old.exists():continue
        incoming = read(old);new = target / filename
        existing = read(new) if new.exists() else {'schema_version': 1, field: {}}
        for data in (incoming, existing):
            if data.get('schema_version') != 1 or not isinstance(data.get(field), dict):
                raise g.GrammarError('Invalid reusable review cache')
        for key, record in incoming[field].items():
            if key in existing[field] and existing[field][key] != record:
                raise g.GrammarError('Conflicting cached review records; refusing to overwrite')
            existing[field][key] = record
        m.save(new, existing)


def build_window(window, folder, args, name_map):
    folder.mkdir(parents=True, exist_ok=True)
    if args.reuse_cache_from:
        reuse_review_caches(args.reuse_cache_from / folder.name, folder)
    units = m.clauses(window);names = names_for(window, name_map)
    clean_verses = window['conditions']['clean']['verses']
    clean, offsets = m.render(clean_verses)
    writer = m.StructuredCache(folder / 'proposals.json', args.generator_model, m.WRITER_PROMPT,
        m.WRITER_SCHEMA, 'writer', 8000, args.offline)
    judge = m.StructuredCache(folder / 'grammar_reviews.json', args.judge_model, m.JUDGE_PROMPT,
        m.JUDGE_SCHEMA, 'judge', 1800, args.offline)
    lexical_writer = m.StructuredCache(folder / 'word_class_proposals.json', args.generator_model,
        m.WORD_CLASS_PROMPT, m.WORD_CLASS_SCHEMA, 'word_class_writer', 5000, args.offline)
    lexical_judge = m.StructuredCache(folder / 'word_class_reviews.json', args.judge_model,
        m.WORD_CLASS_JUDGE_PROMPT, m.JUDGE_SCHEMA, 'judge', 2200, args.offline)
    meanings = g.GrammarMeaningCache(folder, model=args.judge_model, offline=args.offline)
    request = dict(clean_passage=clean, clauses=units, protected_names=names,
                   max_per_class=args.max_per_class)
    proposal_id, response = writer.call(request)
    m.validate_proposals(response, request)
    lexical_request = dict(clean_passage=clean, clauses=units, protected_names=names,
                           max_candidates=args.max_word_class)
    lexical_id, lexical_response = lexical_writer.call(lexical_request)
    m.validate_word_class_proposals(lexical_response, lexical_request)
    candidates = candidates_from_proposals(window, units, response, proposal_id, lexical_response, lexical_id)
    for candidate in candidates:
        failures = m.hard_failures(candidate['before'], candidate['after'], candidate['subtype'], names)
        if 'word_class_transition' in candidate:
            failures += m.word_class_failures(candidate['before'], candidate['after'], candidate['word_class_transition'])
        if failures:
            candidate.update(status='needs_repair', hard_failures=failures, grammar=None, meaning=None)
        else:
            paired = dict(original_passage=clean, clause_start=offsets[candidate['verse']] + candidate['start'],
                          original_clause=candidate['before'], edited_clause=candidate['after'],
                          proposed_subtype=candidate['subtype'], protected_names=names,
                          review_scope='one_edit_in_clean_window')
            if 'word_class_transition' in candidate:
                paired.update(word_form_mechanism='lexical_word_class', word_class_transition=candidate['word_class_transition'])
            candidate.update(review(paired, lexical_judge if 'word_class_transition' in candidate else judge, meanings))
        m.save(folder / 'candidates.json', dict(window_id=window['id'], candidates=candidates))
        print(f"{window['id']} {candidate.get('word_form_mechanism', candidate['subtype'])} {candidate['status']}", flush=True)
    total = sum(g.content_len(t) for t in clean_verses.values())
    if total != window['clean_content_chars']:
        raise g.GrammarError('Clean content-character denominator changed')
    selection = m.choose_candidates(candidates, total, rate=args.rate, tolerance_pp=args.tolerance_pp,
        seed=args.seed + g.seed_offset(window['id']), misselection_share=args.misselection_share)
    selected = selection.pop('selected')
    draft = m.apply_candidates(clean_verses, selected)
    combined = None
    if selection['target_met']:
        shown, _ = m.render(draft)
        if any(clean.count(name) != shown.count(name) for name in names):
            raise g.GrammarError('Assembled passage changed a protected name')
        paired = dict(original_passage=clean, clause_start=0, original_clause=clean, edited_clause=shown,
                      review_scope='complete_displayed_window', protected_names=names,
                      selected_edits=[{k: c[k] for k in ('verse', 'before', 'after', 'subtype', 'word_class_transition') if k in c} for c in selected])
        combined = review(paired, lexical_judge if any('word_class_transition' in c for c in selected) else judge, meanings)
        status = combined['status'];reason = 'combined_window_review'
    else:
        status = 'needs_repair';reason = 'no_approved_combination_within_dose_tolerance'
    result = dict(id=window['id'], passage_id=window['passage_id'], reference=audit.reference(window),
        clean=clean_verses, draft=draft, candidates=candidates, selected_ids=[c['candidate_id'] for c in selected],
        selection=selection, combined=combined, status=status, reason=reason,
        unavailable_classes=response['unavailable_classes'], protected_names=names,
        word_class_unavailable_reason=lexical_response['unavailable_reason'],
        source_sha256=g.json_digest(clean_verses), draft_sha256=g.json_digest(draft),
        eligible_for_publication=status == 'pass', published=False)
    m.save(folder / 'result.json', result)
    print(f"{window['id']} WINDOW {status} dose={selection['actual_percent']:.1f}%", flush=True)
    return result


def reasons(row):
    if row.get('manual_adjudications'):
        original = {k: v for k, v in row.items() if k != 'manual_adjudications'}
        return '\n'.join(d['reason'] for d in row['manual_adjudications']) + '\n\nOriginal model evidence:\n' + reasons(original)
    if row.get('hard_failures'):return '; '.join(row['hard_failures'])
    if not row.get('grammar'):return row.get('reason', '')
    return row['grammar']['explanation'] + '\n\n' + row['meaning']['judgment']['explanation']


def render_report(data, path):
    windows = data['windows'];scope = data['configuration']['passage']
    h = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>Mixed Chinese grammar creation</title><style>body{max-width:1250px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;color:#263f43}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #ccd8d6;text-align:left;vertical-align:top}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.pass{color:#08734c}.flagged{color:#906300}.needs_repair{color:#a62b31}details{padding:12px;border:1px solid #d6e0dd;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer}select{padding:8px}@media(max-width:750px){.grid{grid-template-columns:1fr}}</style>',
         '<h1>Mixed Chinese grammar · ' + escape(scope) + '</h1>',
         '<p>Three new misselection classes plus existing misordering candidates. All new wording is model-generated. Existing misordering wording is explicitly identified. No manual replacement wording, QA data, participant data or publication.</p>',
         '<p>Pass = eligible after grammar and meaning checks; flagged = unresolved ambiguity/disagreement; needs repair = a failed requirement. A candidate label alone is never approval. Simple 的／地／得 substitutions are excluded. Dose counts clean characters in whole affected clauses; mixture counts selected primary edit instances. Actual addition/deletion/substitution operations are retained separately.</p>',
         '<p>Writer: ' + escape(data['configuration']['generator_model']) + ' · Reviewer: ' + escape(data['configuration']['judge_model']) + '</p>',
         '<h2>Candidate results</h2><table><tr><th>Type</th><th>Pass</th><th>Flagged</th><th>Needs repair</th></tr>']
    for subtype in m.TYPES:
        counts = data['summary']['candidates_by_type'][subtype]
        h.append('<tr><th>' + escape(m.LABELS[subtype]) + '</th>' + ''.join('<td>' + str(counts.get(s, 0)) + '</td>' for s in audit.SEVERITY) + '</tr>')
    counts = data['summary']['lexical_word_class']
    h.append('<tr><th>Of word form: new lexical word-class substitutions</th>' + ''.join('<td>' + str(counts.get(s, 0)) + '</td>' for s in audit.SEVERITY) + '</tr>')
    h.append('</table><p>A separate writer explicitly searches for related lexical forms of a different word class. Marker-only edits cannot satisfy this search. Reported class transitions are independently checked; valid Chinese conversion and semantic changes cannot pass. Passing lexical proposals are preferred within the existing dose limits.</p><h2>New lexical word-class proposals</h2><table><tr><th>Window / transition</th><th>Clean</th><th>Proposed</th><th>Result</th></tr>')
    for wi, w in enumerate(windows, 1):
        for ci, c in enumerate(w['candidates'], 1):
            if 'word_class_transition' not in c:continue
            t = c['word_class_transition']
            h.append(f'<tr><td><a href="#w{wi}c{ci}">' + escape(w['reference']) + '</a><br>' + escape(t['source_word_class'] + ' → ' + t['target_word_class']) + '</td><td lang="zh">' + escape(c['before']) + '</td><td lang="zh">' + escape(c['after']) + '</td><td class="' + c['status'] + '">' + audit.LABELS[c['status']] + '</td></tr>')
    h.append('</table><h2>Window results</h2><table><tr><th>Window</th><th>Dose</th><th>Selected types</th><th>Result</th></tr>')
    for wi, w in enumerate(windows, 1):
        h.append(f'<tr><td><a href="#w{wi}">' + escape(w['reference']) + '</a></td><td>' + f"{w['selection']['actual_percent']:.1f}%" + '</td><td>' + escape(str(w['selection']['subtype_counts'])) + '</td><td class="' + w['status'] + '">' + audit.LABELS[w['status']] + '</td></tr>')
    h.append('</table><h2>All candidates</h2><label>Show <select id="filter"><option value="all">All candidates</option><option value="pass">Pass</option><option value="flagged">Flagged</option><option value="needs_repair">Needs repair</option></select></label><table><tr><th>Window / type</th><th>Clean</th><th>Proposed</th><th>Result</th></tr>')
    for wi, w in enumerate(windows, 1):
        for ci, c in enumerate(w['candidates'], 1):
            h.append(f'<tr data-status="{c["status"]}"><td><a href="#w{wi}c{ci}">' + escape(w['reference']) + '</a><br>' + escape(m.LABELS[c['subtype']]) + '</td><td lang="zh">' + escape(c['before']) + '</td><td lang="zh">' + escape(c['after']) + '</td><td class="' + c['status'] + '">' + audit.LABELS[c['status']] + '</td></tr>')
    h.append('</table>')
    for wi, w in enumerate(windows, 1):
        h.append(f'<h2 id="w{wi}">' + escape(w['reference']) + ' · ' + audit.LABELS[w['status']] + '</h2><div class="grid">')
        for label, verses in [('Clean', w['clean']), ('Draft (unpublished)', w['draft'])]:
            h.append('<section><h3>' + label + '</h3>' + ''.join('<p lang="zh">' + escape(v + '　' + t) + '</p>' for v, t in verses.items()) + '</section>')
        h.append('</div><p>' + escape(w['reason']) + '</p>')
        if w['combined']:h.append('<details><summary>Complete-window review</summary><pre>' + escape(reasons(w['combined'])) + '</pre></details>')
        if w['unavailable_classes']:h.append('<details><summary>Unavailable proposal types</summary><pre>' + escape(json.dumps(w['unavailable_classes'], ensure_ascii=False, indent=2)) + '</pre></details>')
        if w['word_class_unavailable_reason']:h.append('<p>Lexical word-class search: ' + escape(w['word_class_unavailable_reason']) + '</p>')
        for ci, c in enumerate(w['candidates'], 1):
            selected = c['candidate_id'] in w['selected_ids']
            h.append(f'<details id="w{wi}c{ci}"><summary>' + escape(m.LABELS[c['subtype']] + ' · ' + audit.LABELS[c['status']] + (' · Selected' if selected else '')) + '</summary><p lang="zh">' + escape(c['before']) + ' → ' + escape(c['after']) + '</p><pre>' + escape(reasons(c)) + '</pre><details><summary>Full provenance and review evidence</summary><pre>' + escape(json.dumps(c, ensure_ascii=False, indent=2)) + '</pre></details></details>')
    h.append('<script>document.getElementById("filter").addEventListener("change",e=>document.querySelectorAll("tr[data-status]").forEach(r=>r.hidden=e.target.value!=="all"&&r.dataset.status!==e.target.value));window.addEventListener("hashchange",()=>{const e=document.getElementById(location.hash.slice(1));if(e&&e.tagName==="DETAILS")e.open=true;});</script></html>')
    path.parent.mkdir(parents=True, exist_ok=True);path.write_text(''.join(h))


def run(args):
    load_dotenv(ROOT / '.env')
    manifest = read(args.manifest);name_map = read(NAMES)
    windows = [w for w in manifest['windows'] if w['id'] not in manifest.get('held_for_review', [])
               and (args.passage == 'all' or w['passage_id'] == args.passage)]
    if not windows:raise ValueError('No active windows for requested passage')
    for window in windows:
        audit.edit_requests(window)
        candidates_from_proposals(window, m.clauses(window), {'candidates': []}, 'preflight')
    files = [args.manifest, NAMES, Path(m.__file__), Path(g.__file__), Path(__file__), Path(audit.__file__),
             Path(m.adjudications.__file__)]
    cfg = dict(policy=m.POLICY, word_class_policy=m.WORD_CLASS_POLICY, semantic_policy=g.MEANING_POLICY, passage=args.passage,
        window_ids=[w['id'] for w in windows], generator_model=args.generator_model, judge_model=args.judge_model,
        max_per_class=args.max_per_class, max_word_class=args.max_word_class, rate=args.rate, tolerance_pp=args.tolerance_pp,
        reuse_cache_from=str(args.reuse_cache_from) if args.reuse_cache_from else None,
        seed=args.seed, misselection_share=args.misselection_share,
        source_files={str(p.resolve()): sha256(p.read_bytes()).hexdigest() for p in files},
        questions_sent=False, participant_data_sent=False, automatic_publication=False)
    config_path = args.output / 'configuration.json'
    if config_path.exists() and read(config_path) != cfg:
        raise ValueError('Pipeline inputs changed; use a separate output folder')
    m.save(config_path, cfg);completed = {};errors = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(build_window, w, args.output / g.json_digest(w['id'])[:16], args, name_map): w for w in windows}
        for f in as_completed(futures):
            w = futures[f]
            try:completed[w['id']] = f.result()
            except Exception as exc:errors[w['id']] = type(exc).__name__ + ': ' + str(exc)
            m.save(args.output / 'state.json', dict(completed=len(completed), expected=len(windows), errors=errors))
    if errors:raise RuntimeError('Mixed grammar run incomplete; valid cached evidence is resumable. ' + str(errors))
    for path, expected in cfg['source_files'].items():
        if sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Input changed during mixed grammar generation')
    data = dict(configuration=cfg, windows=[completed[w['id']] for w in windows])
    candidates = [c for w in data['windows'] for c in w['candidates']]
    data['summary'] = dict(candidates_by_type={t: dict(Counter(c['status'] for c in candidates if c['subtype'] == t)) for t in m.TYPES},
                         lexical_word_class=dict(Counter(c['status'] for c in candidates if 'word_class_transition' in c)),
                         windows=dict(Counter(w['status'] for w in data['windows'])))
    m.save(args.output / 'results.json', data)
    m.save(args.output / 'approved_window_drafts.json', dict(policy=m.POLICY, published=False,
        windows=[{k: w[k] for k in ('id', 'source_sha256', 'draft', 'draft_sha256', 'selection', 'selected_ids', 'status')}
                 for w in data['windows'] if w['status'] == 'pass']))
    render_report(data, args.report)
    m.save(args.output / 'verification.json', dict(complete=True, windows=len(windows), candidates=len(candidates),
        source_hashes_unchanged=True, report_sha256=sha256(args.report.read_bytes()).hexdigest(),
        published_materials_changed=False, manual_candidate_wording=False))
    print('SUMMARY', data['summary'], flush=True);print('REPORT', args.report, flush=True)
    return data


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=audit.MANIFEST)
    p.add_argument('--passage', default='t1_1kgs13', help='One passage ID; all requires explicit expansion authorization')
    p.add_argument('--output', type=Path, default=DEFAULT_RUN)
    p.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    p.add_argument('--generator-model', default='gpt-6.1-sol');p.add_argument('--judge-model', default='gpt-6.1-sol')
    p.add_argument('--max-per-class', type=int, choices=(1, 2, 3), default=2)
    p.add_argument('--max-word-class', type=int, choices=(1, 2, 3), default=2,
                   help='Separate lexical word-class search; marker-only proposals cannot fill these slots')
    p.add_argument('--reuse-cache-from', type=Path,
                   help='Previous mixed-grammar run; reuse only exact request/model/prompt-bound cache entries')
    p.add_argument('--rate', type=float, default=.30);p.add_argument('--tolerance-pp', type=float, default=2)
    p.add_argument('--misselection-share', type=float, default=None,
                   help='Optional soft share of selected error instances; e.g. 0.7. No fixed mix by default.')
    p.add_argument('--seed', type=int, default=2026);p.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    p.add_argument('--offline', action='store_true')
    args = p.parse_args(argv)
    if not 0 < args.rate <= 1 or not 0 <= args.tolerance_pp <= 10 or (args.misselection_share is not None and not 0 <= args.misselection_share <= 1):
        p.error('Invalid dose, tolerance or mixture share')
    args.output = args.output.resolve();args.report = args.report.resolve();args.manifest = args.manifest.resolve()
    if args.reuse_cache_from:
        args.reuse_cache_from = args.reuse_cache_from.resolve()
        if not (args.reuse_cache_from / 'configuration.json').exists():p.error('Reuse source must be a mixed-grammar run')
        if args.reuse_cache_from == args.output:p.error('Reuse source and new output must be separate')
    if args.passage != 't1_1kgs13' and args.output == DEFAULT_RUN:
        p.error('Use a separate --output and --report when expanding beyond 1 Kings 13')
    return args


if __name__ == '__main__':
    run(parse_args())
