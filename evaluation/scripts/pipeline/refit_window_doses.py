"""Refit held doses with the newly reviewed, window-specific defect banks."""
import argparse
from collections import Counter
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

from evaluation.scripts.pipeline.build_prepared_window_conditions import (
    BASE, ROOT, RUN, SOL_RELEASE, Edit, checked_json, choose, grammar, load_tier1_metadata,
    mis, passage_edits, read, render, save, validate_reviewed_bank,
)
from evaluation.scripts.pipeline.refill_window_defects import bank_dir, jobs, window_input
from evaluation.scripts.pipeline.report_window_doses import write_report


def new_groups(w, family, bank, excluded):
    """Project the generator's window offsets back to the original verse labels."""
    text = window_input(w['conditions']['clean']['verses'], family)
    frames = []
    cursor = 0
    for label, body in w['conditions']['clean']['verses'].items():
        start = cursor + (len(label.split(':')[-1]) + 1 if family == 'grammar' else 0)
        assert text.startswith(body, start)
        frames.append((start, start + len(body), label))
        cursor = start + len(body) + 1

    def local(start, before, after):
        end = start + len(before)
        (lo, hi, label), = [f for f in frames if f[0] < end and f[1] > start]
        left, right = max(lo, start), min(hi, end)
        prefix, suffix = text[start:left], text[right:end]
        if not (text.startswith(before, start) and after.startswith(prefix) and after.endswith(suffix)):
            raise ValueError('Window edit crossed the verse boundary')
        return Edit(label, left-lo, text[left:right], after[len(prefix):len(after)-len(suffix)])

    result = {}
    if family == 'grammar':
        grammar.validate_grammar_bank(text, bank)
        offsets = {}
        pos = 0
        for i, unit in enumerate(grammar.passage_units(text)):
            offsets[i] = pos
            pos += len(unit['text'])
        for i, entry in enumerate(bank['entries']):
            edit = local(offsets[entry['unit_index']], entry['original_text'], entry['corrupted_text'])
            if mis.content_len(edit.before) != entry['content_chars']:
                raise ValueError('Window clause weight differs from its bank')
            result[f'window-{i}'] = [edit]
    else:
        validate_reviewed_bank(bank, text)
        if bank.get('schema_version') == 3:
            for i, candidate in enumerate(bank['candidates']):
                if any((e['source'],e['target']) in excluded for e in candidate['edits']):
                    continue
                result[f'window-{i}'] = [local(e['start'], e['source'], e['target']) for e in candidate['edits']]
            return result
        candidates = mis.candidate_groups(mis.find_occurrences(text, mis.normalized_replacements(bank)))
        for i, g in enumerate(candidates):
            if (g['source'], g['target']) not in excluded:
                result[f'window-{i}'] = [local(o['start'], o['source'], o['target']) for o in g['occurrences']]
    return result


def positions(group):
    return {(e.verse, p) for e in group for p in range(e.start, e.start+len(e.before))}


def refit(w, family, pool, bank, excluded, tolerance):
    cs = w['conditions']
    clean = cs['clean']['verses']
    total = w['clean_content_chars']
    groups = {k: [e for e in v if e.verse in clean] for k, v in pool.items()}
    groups = {k: v for k, v in groups.items() if v}
    def signature(g):
        return tuple(sorted((e.verse,e.start,e.before,e.after) for e in g))
    old_spans = {signature(g) for g in groups.values()}
    fresh = new_groups(w, family, bank, excluded) if bank is not None else {}
    for k, g in fresh.items():
        # Retain different replacements on the same footprint: their combinations
        # can differ in fluency even when they have identical character coverage.
        if signature(g) not in old_spans:
            groups[k] = g
    masks = [positions(g) for g in groups.values()]
    conflicts = [(a,b) for a,b in combinations(range(len(masks)),2) if masks[a] & masks[b]]
    doses = sorted(c['target_percent'] for k,c in cs.items() if k.startswith(family))
    prior = {dose: cs[f'{family}{dose}'] for dose in doses}
    fixed = {d: c['selected_ids'] for d,c in prior.items() if c['status']=='within_target'}
    plan = choose(groups, clean, doses, tolerance, False, conflicts=conflicts, fixed=fixed,
                  baseline_chars={d:c['affected_chars'] for d,c in prior.items()})
    edits = {dose: [e for i in ids for e in groups[i]] for dose,ids in plan.items()}
    chars = {dose:sum(mis.content_len(e.before) for e in group) for dose,group in edits.items()}
    if not any(abs(100*chars[d]-d*total) < abs(100*prior[d]['affected_chars']-d*total) for d in doses):
        plan = {d:c['selected_ids'] for d,c in prior.items()}
        edits = {d:[e for i in ids for e in groups[i]] for d,ids in plan.items()}
        chars = {d:c['affected_chars'] for d,c in prior.items()}
    covered = set().union(*masks)
    available = sum(mis.content_len(clean[v][p]) for v,p in covered)
    for d in doses:
        if d in fixed:
            assert set(plan[d])==set(fixed[d])
            if family == 'mistranslation' and bank and bank.get('schema_version') == 3:
                from evaluation.scripts.variants.banks.mistranslation_bundles import verify_window_cell
                verify_window_cell(w, cs[f'{family}{d}'], bank)
            continue
        window_ids = [k for k in plan[d] if isinstance(k, str)]
        if window_ids:
            indices = [int(k.removeprefix('window-')) for k in window_ids]
            original = window_input(clean, family)
            if family == 'grammar':
                generated, _ = grammar.apply_grammar_bank(original, rate=d/100, seed=bank['spec']['seed'],
                    bank=bank, selected_bank_indices=indices)
            else:
                generated, _ = mis.apply_mistranslations(original, rate=d/100, seed=0, bank=bank,
                    selected_group_indices=indices)
            changed = render(clean, [e for k in window_ids for e in fresh[k]])
            if generated != window_input(changed, family):
                raise ValueError(f'Fresh {family} edits differ from the native renderer in {w["reference"]}')
        c = cs[f'{family}{d}']
        actual = 100*chars[d]/total
        ok = abs(100*chars[d]-d*total) <= tolerance*total
        c.update(status='within_target' if ok else 'held', actual_percent=actual,
                 affected_chars=chars[d], selected_ids=plan[d], edits=[asdict(e) for e in edits[d]],
                 verses=render(clean, edits[d]))
        if bank is not None:
            c['window_bank_id'] = bank['bank_id']
        if ok:
            for field in ('reason','eligible_groups','eligible_content_chars'):
                c.pop(field, None)
        else:
            c.update(eligible_groups=len(groups), eligible_content_chars=available,
                     reason=('Insufficient approved source coverage.' if 100*available < (d-tolerance)*total
                             else 'No combination of the approved edits falls inside the target band.'))
            if family == 'grammar':
                sums = {0}
                for unit in grammar.passage_units(window_input(clean, family)):
                    if unit['affectable']:
                        sums |= {n + unit['content_chars'] for n in sums}
                closest = min(sums, key=lambda n: (abs(100*n-d*total), n))
                if abs(100*closest-d*total) > tolerance*total:
                    c['reason'] = (f'Whole clauses cannot reach the band even with every clause approved. '
                                   f'The closest possible dose is {100*closest/total:.2f}%.')
        if family == 'mistranslation' and bank and bank.get('schema_version') == 3:
            from evaluation.scripts.variants.banks.mistranslation_bundles import verify_window_cell
            verify_window_cell(w,c,bank)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('draft', 'root', 'output', 'report'):
        cli.add_argument('--'+name, type=Path, required=True)
    args = cli.parse_args()
    draft = read(args.draft)
    metadata = {m['id']:m for m in load_tier1_metadata(ROOT/'evaluation')}
    manifest = read(SOL_RELEASE/'manifest.json')
    excluded = {(e['source'],e['target']) for file in BASE.glob('t1_*/_base/_shared/mistranslation_bank_sol_length_zh.json')
                for e in read(file).get('curation',{}).get('excluded_pairs',[])}
    pools = {}
    ledger = []
    generation = read(args.root/'generation.json')
    finished = {(r['id'],r['family']):r for r in generation['completed']}
    for w,family in list(jobs(draft)):
        pid = w['passage_id']
        if pid not in pools:
            pack = checked_json(SOL_RELEASE/(pid+'.json'), manifest['files'][pid+'.json'])
            pools[pid], _ = passage_edits(pack,RUN/'release'/pid,excluded,metadata[pid])
        path = bank_dir(args.root,w,family)/'window_bank.json'
        prior = {k:c['actual_percent'] for k,c in w['conditions'].items() if k.startswith(family)}
        record = finished.get((w['id'],family))
        if record is None:
            detail = 'Generation incomplete'
        else:
            bank = read(path) if record['approved'] else None
            refit(w,family,pools[pid][family],bank,excluded,draft['tolerance_percentage_points'])
            detail = 'Completed' if bank is not None else 'No new edits passed review'
        ledger.append(dict(id=w['id'],reference=w['reference'],family=family,generation=detail,
                           approved=record['approved'] if record else None, before=prior,
                           after={k:w['conditions'][k]['actual_percent'] for k in prior}))
    draft['counts'] = {k:dict(Counter(w['conditions'][k]['status'] for w in draft['windows']))
                       for k in draft['counts']}
    draft['window_refill'] = ledger
    save(args.output, draft)
    write_report(draft,args.report)
    print(draft['counts'])


if __name__ == '__main__':
    main()
