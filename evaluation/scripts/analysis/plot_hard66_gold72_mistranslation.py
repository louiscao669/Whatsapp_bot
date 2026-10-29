#!/usr/bin/env python3
"""Compare saved Hard66 / Gold72 mistranslation results with E shown separately."""
import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORT = REPO / 'evaluation/reports/qa_rewrite_model_results_2026-10-27'
OUT = REPORT / 'comparisons/hard66_gold72_mistranslation_2026-10-29'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(OUT / '.matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

MODELS = [
    ('llama321b', 'Llama 3.2 1B'),
    ('qwen2515b', 'Qwen 2.5 1.5B'),
    ('qwen317b_think', 'Qwen3 1.7B · thinking'),
    ('qwen317b_nothink', 'Qwen3 1.7B · no thinking'),
]
CATEGORIES = [
    ('mcq_correct', 'Correct A–D', '#269275'),
    ('mcq_incorrect_ad_count', 'Incorrect A–D', '#D98838'),
    ('mcq_e_count', 'E: cannot tell', '#8575BE'),
    ('mcq_unresolved_count', 'No valid answer', '#AAB3BD'),
]
LEVELS = [0, 5, 10, 15, 20, 25, 30]
INK = '#172B3B'
MUTED = '#526578'


def condition_for_level(level):
    return 'omission/0%' if level == 0 else f'mistranslation/{level}%'


def main():
    source = REPORT / 'results_data.json'
    data = json.loads(source.read_text())
    rows = {}
    for row in data['conditions']:
        if row['condition'].startswith('mistranslation/') or row['condition'] == 'omission/0%':
            key = (row['dataset'], row['config'], row['condition'])
            assert key not in rows, key
            rows[key] = row['after']

    previous = json.loads((REPORT / 'individual_charts/e_separated/outcome_counts.json').read_text())
    previous = {(r['config'], r['condition']): r for r in previous if r['family'] == 'mistranslation'}
    audit = []
    for config, _ in MODELS:
        for dataset, expected_n in [('hard', 65), ('gold', 71)]:
            for level in LEVELS:
                condition = condition_for_level(level)
                row = rows[dataset, config, condition]
                assert row['mcq_n'] == expected_n
                assert sum(row[key] for key, _, _ in CATEGORIES) == expected_n
                if dataset == 'hard':
                    prior = previous[config, condition]
                    assert all(row[key] == prior[key] for key, _, _ in CATEGORIES)
                    assert row['mcq_n'] == prior['n']
                audit.append({
                    'dataset': dataset, 'config': config, 'condition': condition,
                    'n': expected_n,
                    'counts': {key: row[key] for key, _, _ in CATEGORIES},
                    'percentages': {key: 100 * row[key] / expected_n for key, _, _ in CATEGORIES},
                })

    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 11, 'svg.fonttype': 'none',
        'axes.spines.top': False, 'axes.spines.right': False,
        'text.color': INK, 'axes.labelcolor': MUTED,
        'xtick.color': MUTED, 'ytick.color': MUTED,
    })
    fig = plt.figure(figsize=(20, 11.25), facecolor='white')
    outer = fig.add_gridspec(2, 2, left=.052, right=.985, bottom=.18, top=.82,
                             wspace=.15, hspace=.62)
    fig.text(.052, .948, 'Mistranslation · Hard66 and Gold72', fontsize=28, weight='bold')
    fig.text(.052, .902, 'Same four model configurations · E responses shown separately',
             fontsize=15, color=MUTED)

    for i, (config, name) in enumerate(MODELS):
        spec = outer[i // 2, i % 2]
        bounds = spec.get_position(fig)
        fig.text(bounds.x0, bounds.y1 + .052, name, fontsize=17, weight='bold')
        inner = spec.subgridspec(1, 2, wspace=.16)
        for j, (dataset, title) in enumerate([('hard', 'Hard66'), ('gold', 'Gold72')]):
            ax = fig.add_subplot(inner[0, j])
            values = [rows[dataset, config, condition_for_level(level)] for level in LEVELS]
            bottoms = [0.0] * len(LEVELS)
            for key, label, color in CATEGORIES:
                heights = [v[key] / v['mcq_n'] for v in values]
                ax.bar(range(7), heights, bottom=bottoms, width=.76,
                       color=color, edgecolor='white', linewidth=.6, zorder=3)
                for x, height, bottom in zip(range(7), heights, bottoms):
                    if height >= .08:
                        ax.text(x, bottom + height / 2, f'{height:.0%}',
                                ha='center', va='center', fontsize=10.5, weight='bold',
                                color='white' if key in ('mcq_correct', 'mcq_e_count') else INK)
                bottoms = [a + b for a, b in zip(bottoms, heights)]
            ax.set_title(title, loc='left', fontsize=13, pad=9, weight='bold', color=MUTED)
            ax.set_xticks(range(7), [str(n) for n in LEVELS])
            ax.set_xlabel('Mistranslation level (%)', fontsize=11, labelpad=5)
            ax.set_ylim(0, 1.04)
            ax.set_yticks([0, .25, .5, .75, 1])
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.tick_params(axis='both', labelsize=10, length=3)
            if j == 1:
                ax.tick_params(axis='y', labelleft=False)
            ax.grid(axis='y', color='#E1E7ED', zorder=0)
            for spine in ('left', 'bottom'):
                ax.spines[spine].set_color('#B9C5CF')
    fig.text(.012, .505, 'Share of all MCQ responses', rotation=90,
             va='center', fontsize=13, color=MUTED)
    fig.legend(handles=[Patch(facecolor=c, label=label) for _, label, c in CATEGORIES],
               loc='lower center', bbox_to_anchor=(.52, .085), ncol=4,
               frameon=False, fontsize=13, handlelength=1.7, columnspacing=2)
    fig.text(.052, .059,
             'Hard66: 65 active MCQs per condition · Gold72: 71 active MCQs per condition · 0% = clean passage',
             fontsize=11, color=MUTED)
    fig.text(.052, .029,
             'Correctness uses the original answer key. E = “cannot tell from the passage.” Rounded labels; segments below 8% are unlabeled.',
             fontsize=10.5, color=MUTED)

    outputs = []
    for extension in ('png', 'svg'):
        path = OUT / f'hard66_gold72_mistranslation_e_separated.{extension}'
        fig.savefig(path, dpi=200, facecolor='white')
        outputs.append(str(path))
    plt.close(fig)
    (OUT / 'outcome_counts.json').write_text(json.dumps({
        'source': str(source.relative_to(REPO)),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'description': 'Existing updated results; no new model inference. All 28 Hard66 bars match the supplied chart source.',
        'bars': audit,
    }, indent=2) + '\n')
    (OUT / 'index.html').write_text('''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mistranslation: Hard66 and Gold72</title>
<style>body{margin:0;background:#f2f5f8;color:#172b3b;font-family:system-ui,sans-serif}main{max-width:1800px;margin:24px auto;padding:0 20px}img{width:100%;background:white;border-radius:8px}a{color:#176e9d}p{line-height:1.6}</style>
<main><p><a href="hard66_gold72_mistranslation_e_separated.png">Download PNG</a> ·
<a href="hard66_gold72_mistranslation_e_separated.svg">Download editable SVG</a> ·
<a href="outcome_counts.json">Exact counts</a></p>
<img src="hard66_gold72_mistranslation_e_separated.png" alt="Side-by-side Hard66 and Gold72 mistranslation outcomes for four model configurations.">
<p>Saved updated evaluations: 65 active Hard66 MCQs and 71 active Gold72 MCQs per condition.
Each model has Hard66 on the left and Gold72 on the right. E is separate from other incorrect choices.
Correct A–D indicates agreement with the original answer key; E appropriateness is not adjudicated.
Mistranslation rates apply to the full passage. These are the original saved mistranslation runs shown in the reference chart.</p></main></html>''')
    assert len(audit) == 56
    print(json.dumps({'outputs': outputs, 'verified_bars': len(audit)}, indent=2))


if __name__ == '__main__':
    main()
