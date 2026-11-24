"""Draw nested omission doses from eligible clauses and measure overlap with fixed defects."""
import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from html import escape
from pathlib import Path
from random import Random

from evaluation.scripts.pipeline.build_prepared_window_conditions import (
    ROOT, RUN, SOL_RELEASE, checked_json, load_tier1_metadata, mis, passage_edits, read, render, save,
)


def band(total, target, tolerance):
    return (total * (target - tolerance) + 99) // 100, total * (target + tolerance) // 100


def mask_for_edits(clauses, edits):
    mask = 0
    for i, clause in enumerate(clauses):
        for e in edits:
            if clause.verse != e['verse']:
                continue
            start = max(clause.start, e['start'])
            end = min(clause.start + len(clause.before), e['start'] + len(e['before']))
            if start < end and mis.content_len(clause.before[start-clause.start:end-clause.start]):
                mask |= 1 << i
                break
    return mask


def high_options(clauses, total, tolerance):
    """Enumerate each valid 30% mask once if it admits at least one 15% subset."""
    weights = [mis.content_len(e.before) for e in clauses]
    low_min, low_max = band(total, 15, tolerance)
    high_min, high_max = band(total, 30, tolerance)
    low_band = ((1 << (low_max + 1)) - 1) ^ ((1 << low_min) - 1)
    low_cap = (1 << (low_max + 1)) - 1
    verse_masks = {}
    for i, e in enumerate(clauses):
        verse_masks[e.verse] = verse_masks.get(e.verse, 0) | (1 << i)
    full = [verse_masks[e.verse] for e in clauses]
    suffix = [0] * (len(weights) + 1)
    for i in reversed(range(len(weights))):
        suffix[i] = suffix[i+1] + weights[i]

    def visit(start, selected, amount, sums):
        if amount >= high_min and sums & low_band:
            yield selected
        for i in range(start, len(weights)):
            if amount + suffix[i] < high_min:
                break
            weight = weights[i]
            candidate = selected | (1 << i)
            if amount + weight <= high_max and candidate & full[i] != full[i]:
                # Bit k records whether a nested subset weighs k source characters.
                yield from visit(i+1, candidate, amount+weight, (sums | (sums << weight)) & low_cap)
    yield from visit(0, 0, 0, 1)


def low_options(clauses, high, total, tolerance):
    minimum, maximum = band(total, 15, tolerance)
    options = [(0, 0)]
    for i, e in enumerate(clauses):
        if high & (1 << i):
            weight = mis.content_len(e.before)
            options += [(mask | (1 << i), count+weight) for mask, count in options if count+weight <= maximum]
    return [mask for mask, count in options if count >= minimum]


def draw(w, pool, generate, seed, policy, tolerance):
    cells = w['conditions']
    clean = cells['clean']['verses']
    total = sum(map(mis.content_len, clean.values()))
    keys = [k for k, (e,) in pool.items() if e.verse in clean]
    clauses = [pool[k][0] for k in keys]
    if sum(mis.content_len(e.before) for e in clauses) != total or total != w['clean_content_chars']:
        raise ValueError(f'Clause weights disagree with the clean window in {w["reference"]}')
    touched = {k:mask_for_edits(clauses, c['edits']) for k,c in cells.items()
               if k.startswith(('grammar', 'mistranslation')) and c['status'] == 'within_target'}
    refs = {k:m for k,m in touched.items() if k.endswith('30')}
    union = touched.get('grammar30', 0) | touched.get('mistranslation30', 0)
    original = mask_for_edits(clauses, cells['omission30']['edits'])
    rng = Random(f'{seed}|{w["id"]}|omission-pair-v1')
    n = ties = 0
    best_cost = len(clauses) + 1
    common = Counter()
    minima = {k:len(clauses)+1 for k in refs}
    inspect_low = len(clean) == 3 and 'mistranslation15' in touched
    low_probability_sum = 0.0
    low_min_shared = len(clauses)+1
    for candidate in high_options(clauses, total, tolerance):
        n += 1
        if inspect_low:
            overlaps = [(m & touched['mistranslation15']).bit_count()
                        for m in low_options(clauses, candidate, total, tolerance)]
            low_probability_sum += sum(x > 0 for x in overlaps) / len(overlaps)
            low_min_shared = min(low_min_shared, min(overlaps))
        for k,m in refs.items():
            shared = (candidate & m).bit_count()
            common[k] += int(shared > 0)
            minima[k] = min(minima[k], shared)
        # Reservoir sampling gives every distinct eligible high-dose set an equal draw.
        if rng.randrange(n) == 0:
            uniform = candidate
        cost = (candidate & union).bit_count()
        if cost < best_cost:
            best_cost, ties = cost, 0
        if cost == best_cost:
            ties += 1
            if rng.randrange(ties) == 0:
                least = candidate
    audit = dict(id=w['id'], reference=w['reference'], verse_count=len(clean), clause_count=len(clauses),
                 eligible_30_sets=n, sets_with_minimum_overlap=ties)
    if not n:
        if all(cells[f'omission{d}']['status']=='within_target' for d in (15,30)):
            raise ValueError('Published in-band pair missing from enumeration')
        audit['decision'] = 'No valid nested omission pair; retained prior doses and review status.'
        return audit
    high = uniform if policy == 'uniform' else least
    options = low_options(clauses, high, total, tolerance)
    audit['eligible_15_subsets_of_drawn_30'] = len(options)
    if policy == 'least-overlap' and 'mistranslation15' in touched:
        low_cost = min((m & touched['mistranslation15']).bit_count() for m in options)
        options = [m for m in options if (m & touched['mistranslation15']).bit_count() == low_cost]
    low = rng.choice(options)
    audit.update(minimum_shared_clauses=best_cost, prior_shared_clauses=(original & union).bit_count(),
                 chosen_shared_clauses=(high & union).bit_count(), decision='Drawn',
                 comparisons={k:dict(prior_shared=(original & m).bit_count(),
                                     uniform_sets_sharing=common[k], minimum_shared=minima[k],
                                     chosen_shared=(high & m).bit_count()) for k,m in refs.items()})
    if inspect_low:
        before = mask_for_edits(clauses, cells['omission15']['edits'])
        audit['comparison_15'] = dict(uniform_probability_sharing=low_probability_sum/n,
            minimum_shared=low_min_shared, prior_shared=(before & touched['mistranslation15']).bit_count(),
            chosen_shared=(low & touched['mistranslation15']).bit_count())
    for dose, mask in ((15, low), (30, high)):
        ids = [k for i,k in enumerate(keys) if mask & (1 << i)]
        edits = [pool[k][0] for k in ids]
        count = sum(mis.content_len(e.before) for e in edits)
        generated = generate('omission', dose, ids, list(clean))
        if (generated != render(clean, edits) or total-sum(map(mis.content_len, generated.values())) != count
                or abs(100*count-dose*total) > tolerance*total):
            raise ValueError('Draw disagrees with the omission generator or the dose band')
        cells[f'omission{dose}'] = dict(status='within_target', target_percent=dose, actual_percent=100*count/total,
            affected_chars=count, selected_ids=ids, edits=[asdict(e) for e in edits], verses=generated)
    return audit


def write_report(path, audits, seed, policy):
    def details(row):
        count = row['eligible_30_sets']
        if not count:
            return '<td colspan="9">No valid nested omission pair. Prior passages and review statuses retained.</td>'
        cells = [f'{count:,}']
        for name in ('mistranslation15', 'mistranslation30', 'grammar30'):
            if name == 'mistranslation15':
                comparison = row.get('comparison_15')
                probability = comparison and comparison['uniform_probability_sharing']
            else:
                comparison = row['comparisons'].get(name)
                probability = comparison and comparison['uniform_sets_sharing'] / count
            if comparison is None:
                cells.extend(['—', '—'])
            else:
                cells.extend([f'{100*probability:.1f}%',
                              f"{comparison['prior_shared']} → {comparison['chosen_shared']}"])
        cells.extend([str(row['minimum_shared_clauses']), f"{row['sets_with_minimum_overlap']:,}"])
        return ''.join(f'<td>{value}</td>' for value in cells)

    sections = []
    for title, group in [('Three-verse windows', [r for r in audits if r['verse_count'] == 3]),
                         ('Other windows', [r for r in audits if r['verse_count'] != 3])]:
        rows = ''.join(f"<tr><th>{escape(r['reference'])}</th><td>{r['clause_count']}</td>"
                       f"{details(r)}</tr>" for r in group)
        sections.append(f'''<h2>{title} ({len(group)})</h2><div><table>
<thead><tr><th rowspan="2">Passage</th><th rowspan="2">Clauses</th><th rowspan="2">Valid 30% sets</th>
<th colspan="2">Omission × mistranslation 15%</th><th colspan="2">Omission × mistranslation 30%</th>
<th colspan="2">Omission × grammar 30%</th><th rowspan="2">Fewest shared at 30% across types</th>
<th rowspan="2">Sets tied for fewest</th></tr><tr>{('<th>Random chance</th><th>Prior → drawn</th>')*3}</tr></thead>
<tbody>{rows}</tbody></table></div>''')
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Omission placement across defect types</title>
<style>body{{font:16px/1.5 system-ui;margin:2rem;color:#172b40}} table{{border-collapse:collapse;font-size:.88rem}}
th,td{{border:1px solid #c5ced5;padding:.45rem;text-align:center}} thead{{background:#e9f1f5}}
tbody th{{text-align:left;white-space:nowrap}} div{{overflow-x:auto}} p{{max-width:90ch}}</style>
<h1>Omission placement across defect types</h1><p>Local draft · {escape(policy)} · seed {seed}</p>
<p>Each valid 30% omission set leaves content in every verse and includes a subset that meets the 15% dose.
Both rates allow two percentage points on either side of the target, measured against clean content characters.</p>
<p>Random chance is the probability of sharing at least one clause with the fixed comparison passage.
The uniform draw selects a 30% set first, then a 15% subset. Prior → drawn counts shared clauses.
The last two columns compare omission with the union of the passing 30% comparison passages.
Held comparisons are excluded. The 15% comparison is reported for three-verse windows.</p>
{''.join(sections)}</html>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding='utf-8')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--draft', type=Path, required=True)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--report', type=Path)
    cli.add_argument('--seed', type=int, required=True)
    cli.add_argument('--policy', choices=('uniform','least-overlap'), default='uniform')
    args = cli.parse_args()
    if args.draft.resolve() == args.output.resolve():
        cli.error('Choose a separate draft for the draw')
    draft = read(args.draft)
    metadata = {m['id']:m for m in load_tier1_metadata(ROOT/'evaluation')}
    manifest = read(SOL_RELEASE/'manifest.json')
    sources = {}
    audits = []
    for w in draft['windows']:
        pid = w['passage_id']
        if pid not in sources:
            pack = checked_json(SOL_RELEASE/(pid+'.json'), manifest['files'][pid+'.json'])
            pool, generate = passage_edits(pack, RUN/'release'/pid, set(), metadata[pid])
            sources[pid] = pool['omission'], generate
        audits.append(draw(w, *sources[pid], args.seed, args.policy, draft['tolerance_percentage_points']))
    draft['omission_draw'] = dict(policy=args.policy, seed=args.seed,
                                  parent_sha256=sha256(args.draft.read_bytes()).hexdigest(), windows=audits)
    draft['counts'] = {k:dict(Counter(w['conditions'][k]['status'] for w in draft['windows'])) for k in draft['counts']}
    save(args.output, draft)
    if args.report:
        write_report(args.report, audits, args.seed, args.policy)
    print(f'{len(audits)} windows; {sum(a["eligible_30_sets"]>0 for a in audits)} valid nested draws; {args.output}')


if __name__ == '__main__':
    main()
