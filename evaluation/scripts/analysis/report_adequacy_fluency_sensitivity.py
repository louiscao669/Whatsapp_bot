#!/usr/bin/env python3
"""Summarize saved accuracy changes; no generation, rescoring, or source edits."""
from collections import Counter
import hashlib
import html
import json
import os
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[3]
REPORTS = REPO / 'evaluation/reports'
OUT = REPORTS / 'adequacy_fluency_sensitivity_2026-10-29'
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', str(OUT / '.matplotlib'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
import numpy as np

MODELS = [
    ('llama321b', 'Llama 3.2 1B'),
    ('qwen2515b', 'Qwen 2.5 1.5B'),
    ('qwen317b_think', 'Qwen3 1.7B · thinking'),
    ('qwen317b_nothink', 'Qwen3 1.7B · no thinking'),
    ('qwen253b', 'Qwen 2.5 3B'),
    ('phi4mini38b', 'Phi-4-mini 3.8B'),
    ('gemma34b', 'Gemma 3 4B'),
]
DATASETS = [('hard', 'Hard66', 65), ('gold', 'Gold72', 71)]
CONDITIONS = [
    ('omission/15%', 'Omission 15%'), ('omission/30%', 'Omission 30%'),
    ('mistranslation/15%', 'Mistranslation 15%'),
    ('mistranslation/30%', 'Mistranslation 30%'),
    ('grammar/30%', 'Grammar 30%'), ('google_word_by_word', 'Google word-by-word'),
]
PLOT_CONDITIONS = ['omission/30%', 'mistranslation/30%', 'grammar/30%', 'google_word_by_word']


def main():
    sources, cells = {}, {}

    def load(path):
        content = path.read_bytes()
        sources[str(path.relative_to(REPO))] = hashlib.sha256(content).hexdigest()
        return json.loads(content)

    original = REPORTS / 'qa_rewrite_model_results_2026-10-27'
    for r in load(original / 'results_data.json')['conditions']:
        if r['condition'] not in ['omission/0%'] + [c for c, _ in CONDITIONS]:
            continue
        a = r['after']
        assert sum(a[k] for k in ['mcq_correct', 'mcq_incorrect_ad_count', 'mcq_e_count', 'mcq_unresolved_count']) == a['mcq_n']
        assert abs(a['mcq_accuracy'] - a['mcq_correct'] / a['mcq_n']) < 1e-12
        condition = 'clean' if r['condition'] == 'omission/0%' else r['condition']
        cells[r['dataset'], r['config'], condition] = (a['mcq_correct'], a['mcq_n'])

    # Cross-check every original-model condition against the previously delivered figures.
    checked_original = set()
    for family in ['omission', 'mistranslation', 'grammar', 'word_by_word']:
        chart = load(original / f'comparisons/hard66_gold72_{family}_2026-10-29/outcome_counts.json')
        for r in chart['bars']:
            condition = 'clean' if r['condition'] == 'omission/0%' else r['condition']
            key = (r['dataset'], r['config'], condition)
            if key in cells:
                assert cells[key] == (r['counts']['mcq_correct'], r['n'])
                checked_original.add(key)
    assert checked_original == set(cells)

    for dataset, label, n in DATASETS:
        report = REPORTS / f'{label.lower()}_small_models_variants_2026-10-28'
        raw = load(report / 'results.json')
        summaries = load(report / 'summary.json')['configurations']
        for r in summaries:
            if r['variant'] not in ['clean'] + [c for c, _ in CONDITIONS]:
                continue
            subset = [x for x in raw if x['config'] == r['config'] and x['variant'] == r['variant']]
            counts = Counter(x['grade']['label'] for x in subset)
            assert len(subset) == len({x['id'] for x in subset}) == r['n'] == n
            for k in ['correct', 'incorrect_ad', 'abstain_e', 'invalid', 'failure']:
                assert counts[k] == r[k]
            cells[dataset, r['config'], r['variant']] = (counts['correct'], n)

    assert len(cells) == 2 * 7 * 7
    records, aggregate, comparisons = [], [], []
    for dataset, label, n in DATASETS:
        for config, model in MODELS:
            base, base_n = cells[dataset, config, 'clean']
            assert base_n == n
            for condition, condition_label in [('clean', 'Clean')] + CONDITIONS:
                correct, denominator = cells[dataset, config, condition]
                assert denominator == n
                records.append(dict(dataset=label, config=config, model=model,
                    condition=condition, condition_label=condition_label,
                    n=n, correct=correct, clean_correct=base,
                    accuracy_percent=100 * correct / n,
                    clean_accuracy_percent=100 * base / n,
                    accuracy_drop_pp=100 * (base - correct) / n))
            om, mis, gr = (cells[dataset, config, c][0] for c in PLOT_CONDITIONS[:3])
            comparisons.append(dict(dataset=label, config=config,
                omission_drop_exceeds_grammar=om < gr,
                mistranslation_drop_exceeds_grammar=mis < gr))
        for condition, condition_label in [('clean', 'Clean')] + CONDITIONS:
            subset = [r for r in records if r['dataset'] == label and r['condition'] == condition]
            assert len(subset) == 7
            aggregate.append(dict(dataset=label, condition=condition, condition_label=condition_label,
                configurations=7, questions_per_configuration=n,
                correct_total=sum(r['correct'] for r in subset), response_total=7*n,
                mean_accuracy_percent=mean(r['accuracy_percent'] for r in subset),
                mean_accuracy_drop_pp=mean(r['accuracy_drop_pp'] for r in subset)))
    assert all(r['omission_drop_exceeds_grammar'] and r['mistranslation_drop_exceeds_grammar'] for r in comparisons)

    # Retain the saved open-ended comparison as supplementary evidence, separately scored.
    open_report = load(REPORTS / 'hard66_open_vs_mcq_2026-10-29/comparison_results.json')
    opens = []
    for config, model in MODELS[:3]:
        subset = {r['condition']: r for r in open_report['summaries'] if r['config'] == config}
        base = subset['omission/0%']
        for condition in ['omission/0%'] + PLOT_CONDITIONS:
            r = subset[condition]
            assert r['matched_n'] == 64
            opens.append(dict(dataset='Hard66', config=config, model=model, n=64,
                condition='clean' if condition == 'omission/0%' else condition,
                full_credit_count=r['open_full_credit'], partial_credit_count=r['open_partial'],
                mean_score=r['open_mean_score'], full_credit_rate_percent=100*r['open_full_credit_rate'],
                full_credit_drop_pp=100*(base['open_full_credit_rate']-r['open_full_credit_rate']),
                mean_score_drop_pp=100*(base['open_mean_score']-r['open_mean_score'])))

    notes = [
        'MCQ accuracy = original-key A–D matches / all active questions. E and invalid outputs are not correct.',
        'Positive drop = clean accuracy minus condition accuracy, in percentage points. Negative means an improvement.',
        'Means give equal weight to the seven model configurations; Qwen3 thinking modes are separate configurations.',
        'Llama 3.2 3B is omitted because matching defect-condition evaluations are unavailable.',
        'Grammar is the controlled fluency-focused comparison: its construction seeks to preserve recoverable meaning.',
        'Word-by-word is reported separately: it is a different translation method, not a pure fluency or 30% manipulation.',
        'Dose labels are nominal full-passage rates, not matched perceptual severity; question windows can have different exposure.',
        'Original-model and newer three-model campaigns use different omission-window extraction procedures.',
        'These are descriptive saved-run results, not repeated independent experiments; shared questions and related models are not independent replicates.',
        'Hard66 and Gold72 differ in items, options and windows. Changes are calculated within each dataset and configuration.',
        'Open-ended results use the earlier 64 matched items, saved judge scores of 0 / 0.5 / 1, and failures as zero. They are not pooled with MCQ accuracy.',
    ]
    payload = dict(source_sha256=sources, notes=notes, model_results=records,
                   aggregate_results=aggregate, within_configuration_comparisons=comparisons,
                   supplemental_open_results=opens,
                   verification=dict(verified_mcq_cells=len(cells), original_chart_cells=len(checked_original),
                       omission_larger_than_grammar=14, mistranslation_larger_than_grammar=14))
    (OUT / 'accuracy_sensitivity_data.json').write_text(json.dumps(payload, indent=2) + '\n')

    plt.rcParams.update({'font.family':'DejaVu Sans', 'svg.fonttype':'none', 'font.size':13,
                         'text.color':'#172B3B', 'xtick.color':'#172B3B', 'ytick.color':'#172B3B'})
    fig, axes = plt.subplots(1, 2, figsize=(20, 11.25), sharey=True, facecolor='white')
    fig.subplots_adjust(left=.245, right=.975, bottom=.24, top=.74, wspace=.10)
    fig.text(.045, .945, 'Accuracy is more sensitive to meaning defects than grammar errors', fontsize=26, weight='bold')
    fig.text(.045, .890, 'Drop from clean-passage MCQ accuracy · percentage points · all 7 tested configurations', fontsize=17, color='#526578')
    cmap = LinearSegmentedColormap.from_list('drop', [(0,'#A2C7E4'),(.5,'#FAFBFC'),(.72,'#F9C17C'),(1,'#A43A24')])
    norm = TwoSlopeNorm(vmin=-5, vcenter=0, vmax=32)
    for ax, (dataset, label, n) in zip(axes, DATASETS):
        matrix = [[100*(cells[dataset, m, 'clean'][0]-cells[dataset, m, c][0])/n for c in PLOT_CONDITIONS] for m, _ in MODELS]
        matrix.append([mean(row[j] for row in matrix) for j in range(4)])
        matrix = np.array(matrix)
        ax.imshow(matrix, cmap=cmap, norm=norm, aspect='auto')
        ax.set_title(f'{label} · {n} MCQs', loc='left', fontsize=21, weight='bold', pad=57)
        ax.set_xticks(range(4), ['Omission\n30%', 'Mistranslation\n30%', 'Grammar\n30%', 'Word-by-word\n(separate)'], fontsize=14)
        ax.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False, length=0, pad=12)
        ax.set_yticks(range(8), [label for _, label in MODELS] + ['Mean across configurations'], fontsize=15)
        ax.set_xticks(np.arange(-.5,4,1), minor=True)
        ax.set_yticks(np.arange(-.5,8,1), minor=True)
        ax.grid(which='minor', color='white', linewidth=3)
        ax.tick_params(which='minor', length=0)
        for (i,j), value in np.ndenumerate(matrix):
            ax.text(j,i, f'{value:.1f}' if abs(value)<.05 else f'{value:+.1f}',
                    ha='center', va='center', fontsize=17, weight='bold' if i==7 else 'normal',
                    color='white' if value>=23 else '#172B3B')
        ax.axhline(6.5, color='#172B3B', linewidth=1.3)
        ax.axvline(2.5, color='#172B3B', linewidth=1.0, linestyle='--')
        for s in ax.spines.values(): s.set_visible(False)
    fig.text(.045, .168, 'Both omission and mistranslation cause a larger accuracy drop than grammar in all 14 dataset × configuration comparisons.', fontsize=15, weight='bold')
    fig.text(.045, .116, 'Positive = accuracy fell; negative = accuracy improved. Values are changes in percentage points, not percentage reductions.', fontsize=12.5, color='#526578')
    fig.text(.045, .077, '30% is the nominal full-passage dose; local question exposure and severity are not matched across defect types.', fontsize=12.5, color='#526578')
    fig.text(.045, .038, 'Word-by-word may affect meaning as well as fluency. This figure summarizes existing MCQ runs; it does not establish statistical significance.', fontsize=12, color='#526578')
    stem='hard66_gold72_adequacy_fluency_accuracy_drop'
    for ext in ['png','svg']:
        fig.savefig(OUT/f'{stem}.{ext}', dpi=200, facecolor='white')
    plt.close(fig)

    def table(headers, rows):
        return '<table><thead><tr>'+''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in r)+'</tr>' for r in rows)+'</tbody></table>'
    aggregate_index={(r['dataset'],r['condition']):r for r in aggregate}
    summary_rows=[]
    for condition, label in [('clean','Clean')]+CONDITIONS:
        row=[label]
        for _, ds, _ in DATASETS:
            r=aggregate_index[ds,condition]
            row += [f"{r['mean_accuracy_percent']:.1f}%",f"{r['mean_accuracy_drop_pp']:+.1f}",f"{r['correct_total']}/{r['response_total']}"]
        summary_rows.append(row)
    content='<h1>Accuracy sensitivity: adequacy and fluency</h1><p>Saved evaluations, 29 October 2026. No new model inference or grading.</p>'
    content+=f'<img src="{stem}.png" alt="Per-model accuracy drops for Hard66 and Gold72">'
    content+='<p><a href="'+stem+'.png">PNG chart</a> · <a href="'+stem+'.svg">Editable SVG</a> · <a href="accuracy_sensitivity_data.json">All counts, rates and provenance (JSON)</a></p>'
    content+='<h2>Equal-weight averages across seven configurations</h2>'+table(['Condition','Hard66 accuracy','Hard66 drop (pp)','Hard66 correct/total','Gold72 accuracy','Gold72 drop (pp)','Gold72 correct/total'],summary_rows)
    content+='<p>Totals repeat the same question set across seven configurations; they do not represent 455 or 497 independent questions.</p>'
    for _, label, _ in DATASETS:
        rows=[]
        for config, model in MODELS:
            lookup={r['condition']:r for r in records if r['dataset']==label and r['config']==config}
            rows.append([model]+[f"{lookup[c]['correct']}/{lookup[c]['n']} ({lookup[c]['accuracy_percent']:.1f}%)" for c in ['clean']+[c for c,_ in CONDITIONS]])
        content+='<h2>'+label+': exact MCQ counts and accuracy</h2>'+table(['Model','Clean']+[l for _,l in CONDITIONS],rows)
    content+='<h2>Supplement: Hard66 open-ended results</h2><p>64 matched items per configuration. Full credit only is shown below; the JSON also includes partial-credit means.</p>'
    open_rows=[]
    for config, model in MODELS[:3]:
        lookup={r['condition']:r for r in opens if r['config']==config}
        open_rows.append([model]+[f"{lookup[c]['full_credit_count']}/64 ({lookup[c]['full_credit_rate_percent']:.1f}%)" for c in ['clean']+PLOT_CONDITIONS])
    content+=table(['Model','Clean','Omission 30%','Mistranslation 30%','Grammar 30%','Word-by-word'],open_rows)
    content+='<h2>Interpretation and limits</h2><ul>'+''.join('<li>'+html.escape(n)+'</li>' for n in notes)+'</ul>'
    content+='<p>The pattern supports greater sensitivity to the tested adequacy defects than to the tested meaning-preserving grammar defects. It does not show insensitivity to every kind of fluency problem.</p>'
    content+='<h2>Source files</h2><ul>'+''.join('<li><a href="'+html.escape(str(REPO/p))+'">'+html.escape(p)+'</a></li>' for p in sources)+'</ul>'
    (OUT/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Accuracy sensitivity: adequacy and fluency</title><style>body{font:16px/1.5 system-ui,sans-serif;color:#172b3b;max-width:1500px;margin:40px auto;padding:0 30px}img{width:100%}table{border-collapse:collapse;width:100%;margin:20px 0;font-size:14px}th,td{padding:10px;border-bottom:1px solid #dce4eb;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#f0f4f7}a{color:#245e99}li{margin:9px 0}</style>'+content+'</html>')
    print(json.dumps({'report':str(OUT/'index.html'),'figure':str(OUT/f'{stem}.png'),
                     'verification':payload['verification'],'aggregate_results':aggregate},indent=2))


if __name__ == '__main__':
    main()
