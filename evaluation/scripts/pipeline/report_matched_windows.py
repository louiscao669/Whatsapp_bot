"""Show dose, shared clauses and annotated answer evidence for each joint placement."""
from collections import Counter
from html import escape

from evaluation.scripts.pipeline.report_window_doses import condition_label, passage


def write_report(draft, path):
    audit = draft['clause_matching']
    ledger = audit['windows']
    overview, same_evidence = [], []
    for d in ('15', '30'):
        for stage in ('before', 'after'):
            counts = Counter(r[stage]['comparisons'][d]['status'] for r in ledger)
            values = ''.join(f'<td>{counts[s]}</td>' for s in ('Exact', 'Partial', 'No common clause', 'Dose held'))
            overview.append(f'<tr><th>{d}% · {stage}</th>{values}</tr>')
            comparable = [r[stage] for r in ledger if r[stage]['comparisons'][d]['status'] != 'Dose held']
            phrase_sets = [{tuple(s['conditions'][k]['evidence_phrases']) for k in s['comparisons'][d]['passing']}
                           for s in comparable]
            all_miss = sum(sets == {()} for sets in phrase_sets)
            agree = sum(len(sets) == 1 for sets in phrase_sets)
            same_evidence.append(f'<tr><th>{d}% · {stage}</th><td>{len(comparable)}</td><td>{agree-all_miss}</td>'
                                 f'<td>{all_miss}</td><td>{len(comparable)-agree}</td></tr>')
    exposure = []
    for key in draft['counts']:
        accepted = [(w, a) for w, a in zip(draft['windows'], ledger, strict=True)
                    if w['conditions'][key]['status'] == 'within_target']
        before, after = [sum(bool(a[s]['conditions'][key]['evidence_phrases']) for w,a in accepted)
                         for s in ('before', 'after')]
        exposure.append(f'<tr><th>{condition_label(key)}</th><td>{len(accepted)}</td><td>{before}</td><td>{after}</td></tr>')

    summary, details = [], []
    for i, (window, row) in enumerate(zip(draft['windows'], ledger, strict=True), 1):
        ref = escape(window['reference'])
        after = row['after']
        def label(d):
            result = after['comparisons'][d]
            counts = f'{len(result["shared"])}/{len(result["union"])}'
            if result['status'] == 'Dose held':
                return 'Dose held'
            return f'{result["status"]} · {counts}'
        held = [k for k in draft['counts'] if window['conditions'][k]['status'] == 'held']
        held_text = ', '.join(map(condition_label, held)) or '—'
        summary.append(f'<tr><th><a href="#w{i}">{ref}</a></th><td>{label("15")}</td><td>{label("30")}</td>'
                       f'<td>{held_text}</td></tr>')
        details.append(f'<section id="w{i}"><h2>{i}. {ref}</h2><p lang="zh">{escape(window["question"])}</p>'
                       '<h3>Clean evidence phrases</h3><ol>')
        for item in row['evidence']:
            details.append(f'<li lang="zh">{escape(item["verse"])}　{escape(item["quote"])}</li>')
        details.append('</ol>')
        for d in ('15', '30'):
            possible = row['exact_possible'][d]
            feasibility = {True:'Feasible', False:'Infeasible with these reviewed edits', None:'Dose held'}[possible]
            details.append(f'<p><strong>{d}%</strong> · {label(d)} · Exact set matching when optimizing this dose alone: {feasibility}.</p>')
        details.append('<details><summary>Clean passage and numbered clause boundaries</summary><ol>')
        for clause in row['clauses']:
            details.append(f'<li value="{clause["id"]}" lang="zh">{escape(clause["verse"])}　{escape(clause["text"])}</li>')
        details.append('</ol></details>')
        for key in draft['counts']:
            cell = window['conditions'][key]
            footprint = after['conditions'][key]
            cp = ', '.join(map(str, footprint['clauses'])) or 'none'
            ep = ', '.join(map(str, footprint['evidence_phrases'])) or 'none'
            details.append(f'<details><summary>{condition_label(key)} · {cell["actual_percent"]:.2f}% · '
                           f'{"For review" if key in held else "In band"}</summary>'
                           f'<p>{cell["affected_chars"]}/{window["clean_content_chars"]} clean content characters. '
                           f'Clause IDs {cp}. Evidence phrases touched: {ep}.</p>'
                           + passage(cell['verses']) + '</details>')
        details.append('<a href="#windows">Back to windows</a></section>')
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clause matching in the 66 from-scratch windows</title>
<style>body{{font:16px/1.55 system-ui;margin:2rem auto;padding:0 1rem;max-width:70rem;color:#162b32}}
td,th{{padding:.38rem .65rem;border-bottom:1px solid #ced7d8;text-align:left}} table{{border-collapse:collapse}}
thead{{background:#eaf1f1}}details{{margin:.6rem 0}}summary{{cursor:pointer}}section{{padding:1rem 0;border-top:1px solid #c8d4d6}}
a{{color:#075872}} .scroll{{overflow-x:auto}}</style><main>
<h1>Clause matching in the 66 from-scratch windows</h1><p>Local study draft · seed {audit['seed']}</p>
<p>At 15%, the comparison includes omission and mistranslation. At 30%, it also includes grammar.
An exact match requires identical sets of edited clauses. A partial match requires at least one clause
shared by every type. “No common clause” still allows pairwise overlap at 30%. A held dose makes its
full comparison ineligible. Percentages use source content characters with a ±2 percentage point tolerance.</p>
<table><thead><tr><th>Placement</th><th>Exact</th><th>Partial</th><th>No common clause</th><th>Dose held</th></tr></thead>
<tbody>{''.join(overview)}</tbody></table>
<h2>Edits touching the answer evidence</h2><p>Counts include passing variants whose recorded source span overlaps a marked evidence phrase.
For grammar that span is the entire reviewed clause. Touching a phrase does not establish that its meaning or the answer changed.</p>
<table><thead><tr><th>Dose · placement</th><th>Full comparisons</th><th>Same phrases touched</th>
<th>All miss the phrases</th><th>Different evidence exposure</th></tr></thead><tbody>{''.join(same_evidence)}</tbody></table>
<table><thead><tr><th>Condition</th><th>In band</th><th>Before</th><th>After</th></tr></thead><tbody>{''.join(exposure)}</tbody></table>
<h2 id="windows">Results by window</h2><p>The fraction counts clauses shared by all types over clauses touched by any type.
Select a passage to inspect the exact-match check, generated texts, clause IDs, and evidence phrases.</p>
<div class="scroll"><table><thead><tr><th>Window</th><th>15%</th><th>30%</th><th>Doses for review</th></tr></thead>
<tbody>{''.join(summary)}</tbody></table></div>{''.join(details)}</main></html>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding='utf-8')
