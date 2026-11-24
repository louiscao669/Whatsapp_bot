"""Compare corrected and previous WBW responses, preserving the matched item and reader."""
import argparse
from collections import Counter
import csv
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

import rerun_sol_wbw_names as exp

RUN = exp.run
NAMES = [RUN.model_name(*config) for config in RUN.MODELS]
STUDIES = {'scratch': 'From-scratch', 'prepared': 'Prepared'}


def observations(db, study):
    db.row_factory = sqlite3.Row
    sql = """
        SELECT o.model,o.form,o.item,o.request_hash,o.choice,o.outcome,a.answer,a.tokens,a.done_reason,
               g.score,g.english,g.rationale,m.signature
        FROM observations o JOIN answers a ON a.hash=o.request_hash
        LEFT JOIN grades g ON o.form='open' AND (o.study,o.model,o.condition,o.item)=(g.study,g.model,g.condition,g.item)
        LEFT JOIN mapped_observations m ON o.form='mcq' AND (o.study,o.model,o.condition,o.item)=(m.study,m.reader,m.condition,m.item)
        WHERE o.study=? AND o.condition='wbw'"""
    return {(row['item'], row['model'], row['form']): dict(row) for row in db.execute(sql, (study,))}


def pair_rows(study):
    rows, design, packs, revised, selected = exp.protocol()
    roster = [r for r in rows if r['source'] == RUN.STUDIES[study]]
    affected = {r['id'] for r in selected[study]}
    with exp.prior_db() as old, sqlite3.connect((exp.FOLDER/'observations.sqlite').as_uri()+'?mode=ro', uri=True) as new:
        baseline, current = observations(old, study), observations(new, study)
    old.close()
    new.close()
    assert baseline.keys() == current.keys() and len(baseline) == len(roster)*10
    results = []
    for row in roster:
        item = row['id']
        before, after = exp.excerpts(row, packs, revised)
        for index, (model, think) in enumerate(RUN.MODELS):
            reader = NAMES[index]
            mode = False if study == 'prepared' and index < 2 else think
            for form in (('mcq', 'open') if index < 3 else ('mcq',)):
                key = (item, reader, form)
                record = dict(study=study, id=item, reference=row['reference'], question=row['question'],
                              reader=reader, form=form, affected=item in affected,
                              key=row['correct'], choices=' | '.join(row['choices']), old_excerpt=before, new_excerpt=after)
                if item not in affected:
                    assert baseline[key] == current[key]
                for prefix, excerpt, value in [('old', before, baseline[key]), ('new', after, current[key])]:
                    body, _ = RUN.request_for(row, excerpt, model, mode, form, index >= 4)
                    assert value['request_hash'] == RUN.digest([study, design['models'][model], body])
                    if form == 'mcq':
                        assert value['score'] is None
                        expected = ('correct' if value['choice'] == row['correct'] else 'abstain' if value['choice'] == 'E'
                                    else 'incorrect' if value['choice'] in list('ABCD') else 'invalid')
                        assert value['outcome'] == expected
                        if index < 4 and value['answer'].strip():
                            assert value['outcome'] != 'invalid'
                    else:
                        assert value['score'] in (0.0, 0.5, 1.0) and value['outcome'] is None
                    for field in ['answer','choice','outcome','score','english','rationale','done_reason','request_hash']:
                        record[f'{prefix}_{field}'] = value[field]
                    record[f'{prefix}_mapped'] = bool(value['signature'])
                assert (record['old_request_hash'] != record['new_request_hash']) == record['affected']
                results.append(record)
    return results


def counts(records, prefix):
    counts = Counter()
    for row in records:
        if row['form'] == 'mcq':
            counts[row[prefix+'_outcome']] += 1
        else:
            score = row[prefix+'_score']
            counts[{1: 'full', 0.5: 'partial', 0: 'zero'}[score]] += 1
            counts['points'] += score
    return counts


def percent(value, total):
    return f'{100*value/total:.1f}%'


def rate_change(a, b, total):
    return f'{a}/{total} → {b}/{total} ({100*(b-a)/total:+.1f} pp)'


def table(rows, form, readers=True):
    if form == 'mcq':
        lines = ['| Reader | Correct, before → after | Correct, % | Gains / losses | Wrong A–D | E | Invalid |',
                 '|---|---:|---:|---:|---:|---:|---:|']
        fields = ('incorrect','abstain','invalid')
    else:
        lines = ['| Reader | Full credit, before → after | Full credit, % | Gains / losses of full credit | Partial credit | Zero credit | Mean points, before → after |',
                 '|---|---:|---:|---:|---:|---:|---:|']
        fields = ('partial','zero')
    per_reader = NAMES if form=='mcq' else NAMES[:3]
    for name in [*(per_reader if readers else []), 'All configurations']:
        items = [r for r in rows if r['form']==form and (name=='All configurations' or r['reader']==name)]
        a, b = counts(items,'old'), counts(items,'new')
        col = 'correct' if form=='mcq' else 'full'
        gains = sum((r['old_outcome'] != 'correct' and r['new_outcome'] == 'correct') if form=='mcq'
                    else (r['old_score'] < 1 and r['new_score'] == 1) for r in items)
        losses = gains - (b[col] - a[col])
        vals = [name, rate_change(a[col],b[col],len(items)),
                f'{percent(a[col],len(items))} → {percent(b[col],len(items))}', f'{gains} / {losses}']
        vals.extend(f'{a[f]} → {b[f]}' for f in fields)
        if form=='open':
            vals.append(f"{a['points']/len(items):.3f} → {b['points']/len(items):.3f}")
        lines.append('| ' + ' | '.join(vals) + ' |')
    return lines


def biggest_item_changes(records):
    counts_by_item = {}
    for row in records:
        if row['form'] != 'mcq':
            continue
        key = row['id']
        if key not in counts_by_item:
            counts_by_item[key] = dict(reference=row['reference'], question=row['question'], before=0, after=0)
        counts_by_item[key]['before'] += row['old_outcome'] == 'correct'
        counts_by_item[key]['after'] += row['new_outcome'] == 'correct'
    for item in counts_by_item.values():
        item['delta'] = item['after']-item['before']
    deltas = [item['delta'] for item in counts_by_item.values()]
    extremes = {max(deltas), min(deltas)} - {0}
    lines = ['## Largest question-level MCQ changes', '',
             'Counts are correct responses across the seven reader configurations. All ties at either extreme are shown.', '',
             '| Passage | Question | Before | After | Change |', '|---|---|---:|---:|---:|']
    for item in sorted(counts_by_item.values(), key=lambda x: -x['delta']):
        if item['delta'] in extremes:
            lines.append(f"| {item['reference']} | {item['question']} | {item['before']}/7 | {item['after']}/7 | {item['delta']:+d} |")
    return lines


def write_report(study):
    results = pair_rows(study)
    changed = [r for r in results if r['affected']]
    exp.REPORT.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile('w',encoding='utf-8-sig',newline='',dir=exp.REPORT,delete=False) as f:
        w = csv.DictWriter(f, fieldnames=list(changed[0]))
        w.writeheader()
        w.writerows(changed)
    Path(f.name).replace(exp.REPORT / f'{study}-item-comparison.csv')
    n = len(changed)//10
    lines = [f'# {STUDIES[study]} QA results for the corrected Google word-by-word passages', '',
             f'{n} of {len(results)//10} question windows changed. Each was rerun under the original seven '
             'multiple-choice configurations and three open-ended configurations. The comparison uses the latest '
             'pre-correction experiment with the same stems, choices, keys, model weights and prompts.', '',
             '## Multiple choice on affected questions', '', *table(changed,'mcq'), '',
             'Gains and losses count paired question–configuration responses moving into or out of correctness. '
             'E means “cannot tell.” Rates include abstentions and invalid replies in the denominator.', '',
             '## Open answers on affected questions', '', *table(changed,'open'), '',
             'Full credit is 1 point and partial credit is 0.5. The original scoring procedure translates and judges '
             'open answers using GPT-4.1-mini and reuses a grade for the same item and identical answer where available.', '',
             *biggest_item_changes(changed), '', '## Whole-set word-by-word results', '',
             f'These totals include the {len(results)//10-n} question windows whose input stayed identical. '
             'Their recorded responses and scores were carried forward.', '',
             *table(results,'mcq'), '', *table(results,'open'), '',
             'The pooled rates are descriptive. Each question contributes one response per configuration.', '']
    (exp.REPORT/f'{study}-results.md').write_text('\n'.join(lines),encoding='utf-8')
    print('\n'.join([*table(changed,'mcq',False),*table(changed,'open',False)]),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study',choices=STUDIES)
    write_report(parser.parse_args().study)
