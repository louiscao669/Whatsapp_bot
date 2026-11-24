"""Jointly place reviewed omission, grammar and mistranslation edits on matching clauses."""
import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from random import Random

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from evaluation.scripts.pipeline.build_prepared_window_conditions import (
    BASE, ROOT, RUN, SOL_RELEASE, Edit, checked_json, choose, grammar, load_bank,
    load_tier1_metadata, mis, passage_edits, read, render, save, SOL_SET,
)
from evaluation.scripts.pipeline.draw_window_omissions import band
from evaluation.scripts.pipeline.refit_window_doses import bank_dir, new_groups, positions, window_input

DOSES = {'omission': (15, 30), 'mistranslation': (15, 30), 'grammar': (30,)}
EVIDENCE = ROOT / 'evaluation/datasets/perturbations/sol_scratch66_answer_evidence.json'


def content_positions(edits):
    return {(e.verse, e.start + i) for e in edits for i, c in enumerate(e.before) if mis.content_len(c)}


class PlacementModel:
    """Binary edit selections and their footprints on clauses and evidence phrases."""
    def __init__(self):
        self.n = 0
        self.rows = []
        self.lower = []
        self.upper = []

    def variable(self):
        self.n += 1
        return self.n - 1

    def constrain(self, terms, low=-np.inf, high=np.inf):
        self.rows.append(terms)
        self.lower.append(low)
        self.upper.append(high)

    def any_selected(self, variables):
        if not variables:
            return None
        if len(variables) == 1:
            return variables[0]
        flag = self.variable()
        for v in variables:
            self.constrain({v: 1, flag: -1}, high=0)
        self.constrain({**{v: -1 for v in variables}, flag: 1}, high=0)
        return flag

    def disagreement(self, variables):
        distinct = set(variables)
        if len(distinct) < 2:
            return None
        flag = self.variable()
        for a, b in combinations(distinct, 2):
            for left, right in ((a, b), (b, a)):
                terms = {flag: -1}
                if left is not None:
                    terms[left] = 1
                if right is not None:
                    terms[right] = -1
                self.constrain(terms, high=0)
        return flag

    def all_selected(self, variables):
        if None in variables:
            return None
        if len(variables) == 1:
            return variables[0]
        flag = self.variable()
        for v in variables:
            self.constrain({flag: 1, v: -1}, high=0)
        self.constrain({**dict.fromkeys(variables, 1), flag: -1}, high=len(variables)-1)
        return flag

    def solve(self, costs):
        rows, columns, values = [], [], []
        for i, terms in enumerate(self.rows):
            for j, weight in terms.items():
                rows.append(i)
                columns.append(j)
                values.append(weight)
        matrix = coo_matrix((values, (rows, columns)), shape=(len(self.rows), self.n)).tocsc()
        objective = np.zeros(self.n)
        for v, cost in costs.items():
            objective[v] = cost
        fit = milp(objective, integrality=np.ones(self.n), bounds=Bounds(0, 1),
                   constraints=LinearConstraint(matrix, self.lower, self.upper),
                   options={'mip_rel_gap': 0})
        if not fit.success:
            raise RuntimeError(f'Joint clause placement failed: {fit.message}')
        return fit.x > .5


def candidates(w, family, pool, bank, excluded):
    clean = w['conditions']['clean']['verses']
    groups = {key: [e for e in group if e.verse in clean] for key, group in pool.items()}
    groups = {key: group for key, group in groups.items() if group}
    if bank:
        def signature(group):
            return tuple(sorted((e.verse,e.start,e.before,e.after) for e in group))
        seen = {signature(group) for group in groups.values()}
        for key, group in new_groups(w, family, bank, excluded).items():
            sig = signature(group)
            if sig not in seen:
                groups[key] = group
                seen.add(sig)
    return groups


def evidence_spans(w, item):
    if w['question'] != item['question']:
        raise ValueError(f'Stale evidence for {w["id"]}')
    result = []
    for part in item['evidence']:
        text = w['conditions']['clean']['verses'][part['verse']]
        quote = part['quote']
        if not quote or text.count(quote) != 1:
            raise ValueError(f'Ambiguous evidence location in {w["id"]}')
        result.append(Edit(part['verse'], text.index(quote), quote, ''))
    if not result:
        raise ValueError(f'Missing answer evidence in {w["id"]}')
    return result


def dose_limits(w, family, groups, conflicts, tolerance):
    clean = w['conditions']['clean']['verses']
    total = w['clean_content_chars']
    doses = DOSES[family]
    limits = {d: band(total, d, tolerance) for d in doses}
    prior = {d: w['conditions'][family+str(d)] for d in doses}
    if all(c['status'] == 'within_target' for c in prior.values()):
        return limits
    # Retry the entire nested ladder before designating any dose as held.
    plan = choose(groups, clean, doses, tolerance, family == 'omission', conflicts=conflicts)
    counts = {d: sum(mis.content_len(e.before) for k in ids for e in groups[k])
              for d, ids in plan.items()}
    if any(prior[d]['status'] == 'within_target' and not (lo <= counts[d] <= hi)
           for d, (lo, hi) in limits.items()):
        # All supported earlier doses must remain attainable.
        counts = {d: c['affected_chars'] for d, c in prior.items()}
    for d, (lo, hi) in limits.items():
        if not lo <= counts[d] <= hi:
            limits[d] = (counts[d], counts[d])
    return limits


def place(w, groups, evidence, tolerance, seed):
    clean = w['conditions']['clean']['verses']
    total = w['clean_content_chars']
    clauses = [g[0] for g in groups['omission'].values()]
    clause_points = [content_positions([e]) for e in clauses]
    if set().union(*clause_points) != content_positions([Edit(v, 0, text, '') for v, text in clean.items()]):
        raise ValueError(f'Incomplete omission clause partition in {w["id"]}')
    features = clause_points + [content_positions([e]) for e in evidence]
    model = PlacementModel()
    variables, footprints, active = {}, {}, {15: [], 30: []}
    for family, doses in DOSES.items():
        pool = groups[family]
        keys = list(pool)
        occupied = [positions(pool[k]) for k in keys]
        points = [content_positions(pool[k]) for k in keys]
        conflicts = [(i, j) for i, j in combinations(range(len(keys)), 2) if occupied[i] & occupied[j]]
        limits = dose_limits(w, family, pool, conflicts, tolerance)
        for d in doses:
            condition = family + str(d)
            ids = [model.variable() for _ in keys]
            variables[condition] = dict(zip(keys, ids))
            lo, hi = limits[d]
            model.constrain({v:len(p) for v, p in zip(ids, points)}, lo, hi)
            if limits[d] == band(total, d, tolerance):
                active[d].append(condition)
            for i, j in conflicts:
                model.constrain({ids[i]: 1, ids[j]: 1}, high=1)
            if d == 30 and 15 in doses:
                for k, v in zip(keys, ids):
                    model.constrain({variables[family+'15'][k]: 1, v: -1}, high=0)
            if family == 'omission' and d == max(doses):
                for verse in clean:
                    clause_ids = [v for k, v in zip(keys, ids) if pool[k][0].verse == verse]
                    model.constrain(dict.fromkeys(clause_ids, 1), high=len(clause_ids)-1)
            footprints[condition] = [model.any_selected([v for v, p in zip(ids, points) if p & feature])
                                     for feature in features]

    clause_flags, evidence_flags, shared_any, inexact = [], [], [], {}
    for d, conditions in active.items():
        if len(conditions) < 2:
            continue
        flags = [model.disagreement([footprints[k][i] for k in conditions]) for i in range(len(features))]
        clause_differences = [f for f in flags[:len(clauses)] if f is not None]
        clause_flags.extend(clause_differences)
        evidence_flags.extend(f for f in flags[len(clauses):] if f is not None)
        inexact[d] = model.any_selected(clause_differences)
        shared = [model.all_selected([footprints[k][i] for k in conditions]) for i in range(len(clauses))]
        common = model.any_selected([flag for flag in shared if flag is not None])
        if common is not None:
            shared_any.append(common)

    # Each priority dominates every possible improvement in subsequent priorities.
    evidence_cost = len(clause_flags) + 1
    shared_cost = (len(evidence_flags) + 1) * evidence_cost
    exact_cost = (len(shared_any) + 1) * shared_cost
    costs = {}
    for flags, weight in ((clause_flags, 1), (evidence_flags, evidence_cost), (shared_any, -shared_cost),
                          ([f for f in inexact.values() if f is not None], exact_cost)):
        for v in flags:
            costs[v] = costs.get(v, 0) + weight
    # Prefer an exact full-dose comparison to an exact pair in a window with a third dose held.
    for d, flag in inexact.items():
        if flag is not None and len(active[d]) == sum(d in ds for ds in DOSES.values()):
            costs[flag] += (len(inexact) + 1) * exact_cost
    rng = Random(f'{seed}|{w["id"]}|joint-clauses-v1')
    edit_vars = [v for lookup in variables.values() for v in lookup.values()]
    for v in edit_vars:
        costs[v] = costs.get(v, 0) + rng.uniform(-.2, .2) / max(1, len(edit_vars))
    solution = model.solve(costs)
    possible = {}
    for d in (15, 30):
        if len(active[d]) != sum(d in ds for ds in DOSES.values()):
            possible[str(d)] = None
        else:
            flag = inexact[d]
            # Optimize this dose alone, maintaining every other dose and nesting constraint.
            possible[str(d)] = flag is None or not solution[flag] or not model.solve({flag: 1})[flag]
    plan = {k: [key for key, var in lookup.items() if solution[var]] for k, lookup in variables.items()}
    return plan, possible


def materialize(w, family, dose, keys, groups, native, bank, tolerance):
    clean = w['conditions']['clean']['verses']
    base_keys = [k for k in keys if isinstance(k, int)]
    fresh_keys = [k for k in keys if isinstance(k, str)]
    base_edits = [e for k in base_keys for e in groups[k]]
    if native(family, dose, base_keys, list(clean)) != render(clean, base_edits):
        raise ValueError(f'Passage generator disagrees in {w["id"]} / {family}')
    if fresh_keys:
        original = window_input(clean, family)
        indices = [int(k.removeprefix('window-')) for k in fresh_keys]
        if family == 'grammar':
            generated, _ = grammar.apply_grammar_bank(original, rate=dose/100, seed=bank['spec']['seed'],
                                                       bank=bank, selected_bank_indices=indices)
        else:
            generated, _ = mis.apply_mistranslations(original, rate=dose/100, seed=0, bank=bank,
                                                      selected_group_indices=indices)
        if generated != window_input(render(clean, [e for k in fresh_keys for e in groups[k]]), family):
            raise ValueError(f'Window generator disagrees in {w["id"]} / {family}')
    edits = [e for k in keys for e in groups[k]]
    verses = render(clean, edits)
    n = len(content_positions(edits))
    total = w['clean_content_chars']
    if n != sum(mis.content_len(e.before) for e in edits):
        raise ValueError('A source character was counted twice')
    if family == 'omission' and total-sum(map(mis.content_len, verses.values())) != n:
        raise ValueError('Omission did not materialize the exact source-character dose')
    lo, hi = band(total, dose, tolerance)
    result = dict(status='within_target' if lo <= n <= hi else 'held', target_percent=dose,
                  actual_percent=100*n/total, affected_chars=n, selected_ids=keys,
                  edits=[asdict(e) for e in edits], verses=verses)
    if fresh_keys:
        result['window_bank_id'] = bank['bank_id']
    if result['status'] == 'held':
        result.update(reason='Reviewed edits and nested whole-window dose constraints leave this dose outside tolerance.',
                      eligible_groups=len(groups), eligible_content_chars=len(content_positions(
                          [e for group in groups.values() for e in group])))
    if family == 'mistranslation' and bank and bank.get('schema_version') == 3:
        from evaluation.scripts.variants.banks.mistranslation_bundles import verify_window_cell
        verify_window_cell(w,result,bank)
    return result


def audit_window(w, groups, evidence):
    indexed = [(k, content_positions(g)) for k, g in groups['omission'].items()]
    phrases = [content_positions([e]) for e in evidence]
    stats = {}
    for family, doses in DOSES.items():
        for dose in doses:
            key = family+str(dose)
            touched = content_positions([Edit(**e) for e in w['conditions'][key]['edits']])
            stats[key] = dict(clauses=[k for k, p in indexed if p & touched],
                              evidence_phrases=[i+1 for i, p in enumerate(phrases) if p & touched])
    matches = {}
    for d in (15, 30):
        keys = [f+str(d) for f in DOSES if d in DOSES[f]]
        passing = [k for k in keys if w['conditions'][k]['status'] == 'within_target']
        sets = [set(stats[k]['clauses']) for k in passing]
        shared = sorted(set.intersection(*sets)) if sets else []
        union = sorted(set.union(*sets)) if sets else []
        match = 'Exact' if shared == union else 'Partial' if shared else 'No common clause'
        matches[str(d)] = dict(status=match if len(passing) == len(keys) else 'Dose held',
                               passing=passing, shared=shared, union=union)
    return dict(conditions=stats, comparisons=matches)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('draft', 'root', 'output', 'report'):
        cli.add_argument('--'+name, type=Path, required=True)
    cli.add_argument('--evidence', type=Path, default=EVIDENCE)
    cli.add_argument('--seed', type=int, required=True)
    args = cli.parse_args()
    if args.draft.resolve() == args.output.resolve():
        cli.error('Choose a new output path for the matched passages')
    draft = read(args.draft)
    roster = {q['id']:q for q in load_bank(SOL_SET) if q['source']=='Hard77'}
    annotations = read(args.evidence)['items']
    if set(annotations) != set(roster) or set(roster) != {w['id'] for w in draft['windows']}:
        raise ValueError('Evidence, bank and window rosters differ')
    manifest = read(SOL_RELEASE/'manifest.json')
    metadata = {m['id']:m for m in load_tier1_metadata(ROOT/'evaluation')}
    excluded = {(e['source'], e['target']) for file in BASE.glob('t1_*/_base/_shared/mistranslation_bank_sol_length_zh.json')
                for e in read(file).get('curation', {}).get('excluded_pairs', [])}
    approved = {(r['id'], r['family']) for r in read(args.root/'generation.json')['completed'] if r['approved']}
    cached = {}
    ledger = []
    for w in draft['windows']:
        q = roster[w['id']]
        item = annotations[w['id']]
        if (q['question'] != w['question'] or q['choices'][ord(q['correct'])-65] != item['answer']
                or q['verses'] != w['conditions']['clean']['verses']):
            raise ValueError(f'Stale bank or key for {w["id"]}')
        evidence = evidence_spans(w, item)
        pid = w['passage_id']
        if pid not in cached:
            pack = checked_json(SOL_RELEASE/(pid+'.json'), manifest['files'][pid+'.json'])
            cached[pid] = passage_edits(pack, RUN/'release'/pid, excluded, metadata[pid])
        pool, native = cached[pid]
        banks = {f: read(bank_dir(args.root, w, f)/'window_bank.json') if (w['id'], f) in approved else None
                 for f in DOSES}
        groups = {f: candidates(w, f, pool[f], banks[f], excluded) for f in DOSES}
        before = audit_window(w, groups, evidence)
        tolerance = draft['tolerance_percentage_points']
        plan, possible = place(w, groups, evidence, tolerance, args.seed)
        for family, doses in DOSES.items():
            for dose in doses:
                key = family+str(dose)
                old = w['conditions'][key]
                cell = materialize(w, family, dose, plan[key], groups[family], native, banks[family], tolerance)
                if cell['status'] == 'held' and old['status'] == 'within_target' and 'combined_review' not in cell:
                    raise ValueError(f'Passing dose regressed at {w["id"]} / {key}')
                w['conditions'][key] = cell
        after = audit_window(w, groups, evidence)
        ledger.append(dict(id=w['id'], reference=w['reference'], evidence=item['evidence'], exact_possible=possible,
                           clauses=[dict(id=k, verse=g[0].verse, text=g[0].before)
                                    for k,g in groups['omission'].items()], before=before, after=after))
        print(w['reference'], [r['status'] for r in after['comparisons'].values()], flush=True)
    draft['counts'] = {k:dict(Counter(w['conditions'][k]['status'] for w in draft['windows'])) for k in draft['counts']}
    draft['clause_matching'] = dict(seed=args.seed, parent_sha256=sha256(args.draft.read_bytes()).hexdigest(),
        evidence_sha256=sha256(args.evidence.read_bytes()).hexdigest(), windows=ledger)
    save(args.output, draft)
    from evaluation.scripts.pipeline.report_matched_windows import write_report
    write_report(draft, args.report)


if __name__ == '__main__':
    main()
