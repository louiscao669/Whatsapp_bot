#!/usr/bin/env python3
"""Compare the saved three-model Hard66 and Gold72 mistranslation experiments."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORTS = REPO / 'evaluation/reports'
OUT = REPORTS / 'hard66_small_models_variants_2026-10-28/comparisons/hard66_gold72_mistranslation_2026-10-29'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(REPORTS / 'hard66_small_models_variants_2026-10-28/.matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

MODELS = [('gemma34b', 'Gemma 3 4B'), ('phi4mini38b', 'Phi-4-mini 3.8B'), ('qwen253b', 'Qwen 2.5 3B')]
CATEGORIES = [('correct', 'Correct A–D', '#269275'), ('incorrect_ad', 'Incorrect A–D', '#D98838'),
              ('abstain_e', 'E: cannot tell', '#8575BE'), ('no_valid_answer', 'No valid answer', '#AAB3BD')]
CONDITIONS = ['clean', 'mistranslation/15%', 'mistranslation/30%']
INK, MUTED = '#172B3B', '#526578'


def main():
    outcomes, sources, audit = {}, [], []
    for dataset, n in [('hard66', 65), ('gold72', 71)]:
        report = REPORTS / f'{dataset}_small_models_variants_2026-10-28'
        result_path = report / 'results.json'
        data = json.loads(result_path.read_text())
        saved = json.loads((report / 'individual_charts/e_separated/outcome_counts.json').read_text())
        digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
        assert digest == saved['source_sha256']
        sources.append({'dataset': dataset, 'path': str(result_path), 'sha256': digest})
        old = {(r['config'], r['condition']): r for r in saved['bars'] if r['family'] == 'mistranslation'}
        for config, _ in MODELS:
            for condition in CONDITIONS:
                subset = [r for r in data if r['config'] == config and r['variant'] == condition]
                assert len(subset) == len({r['id'] for r in subset}) == n
                counts = Counter(r['grade']['label'] for r in subset)
                counts['no_valid_answer'] = counts['invalid'] + counts['failure']
                counts = {key: counts[key] for key, _, _ in CATEGORIES}
                assert sum(counts.values()) == n
                assert counts == old[config, condition]['counts']
                assert old[config, condition]['n'] == n
                outcomes[dataset, config, condition] = (n, counts)
                audit.append({'dataset': dataset, 'config': config, 'condition': condition,
                              'n': n, 'counts': counts,
                              'percentages': {key: value / n * 100 for key, value in counts.items()}})

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 13, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'text.color': INK, 'axes.labelcolor': MUTED,
                         'xtick.color': MUTED, 'ytick.color': MUTED})
    fig = plt.figure(figsize=(20, 11.25), facecolor='white')
    outer = fig.add_gridspec(1, 3, left=.06, right=.985, bottom=.275, top=.73, wspace=.16)
    fig.text(.06, .933, 'Mistranslation · Hard66 and Gold72', fontsize=29, weight='bold')
    fig.text(.06, .876, 'Gemma, Phi, and Qwen · E responses shown separately', fontsize=16, color=MUTED)
    for i, (config, name) in enumerate(MODELS):
        spec = outer[0, i]
        bounds = spec.get_position(fig)
        fig.text(bounds.x0, bounds.y1 + .085, name, fontsize=20, weight='bold')
        inner = spec.subgridspec(1, 2, wspace=.14)
        for j, (dataset, title) in enumerate([('hard66', 'Hard66'), ('gold72', 'Gold72')]):
            ax = fig.add_subplot(inner[0, j])
            values = [outcomes[dataset, config, c] for c in CONDITIONS]
            bottoms = [0.0] * len(CONDITIONS)
            for key, _, color in CATEGORIES:
                heights = [counts[key] / n for n, counts in values]
                ax.bar(range(3), heights, bottom=bottoms, width=.65, color=color,
                       edgecolor='white', linewidth=.7, zorder=3)
                for x, height, bottom in zip(range(3), heights, bottoms):
                    if height >= .075:
                        ax.text(x, bottom + height / 2, f'{height:.0%}', ha='center', va='center',
                                fontsize=13, weight='bold',
                                color='white' if key in ('correct', 'abstain_e') else INK)
                bottoms = [a + b for a, b in zip(bottoms, heights)]
            assert all(abs(b - 1) < 1e-12 for b in bottoms)
            ax.set_title(title, loc='left', fontsize=15, color=MUTED, pad=16, weight='bold')
            ax.set_xticks(range(3), ['0', '15', '30'])
            ax.set_xlabel('Mistranslation level (%)', fontsize=12, labelpad=10)
            ax.set_xlim(-.6, 2.6)
            ax.set_ylim(0, 1.04)
            ax.set_yticks([0, .25, .5, .75, 1])
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.tick_params(axis='both', labelsize=12, length=3)
            ax.tick_params(axis='y', labelleft=(i == 0 and j == 0))
            ax.grid(axis='y', color='#E1E7ED', zorder=0)
            for spine in ('left', 'bottom'):
                ax.spines[spine].set_color('#B9C5CF')
            if i == 0 and j == 0:
                ax.set_ylabel('Share of all MCQ responses', fontsize=14, labelpad=10)
    fig.legend(handles=[Patch(facecolor=color, label=label) for _, label, color in CATEGORIES],
               loc='lower center', bbox_to_anchor=(.53, .155), ncol=4,
               frameon=False, fontsize=14, columnspacing=2)
    fig.text(.06, .115,
             'Hard66: 65 active MCQs per condition · Gold72: 71 active MCQs per condition · 0% = clean passage',
             fontsize=12, color=MUTED)
    fig.text(.06, .077,
             'Correctness uses the original answer key. E = “cannot tell from the passage.” Rounded labels; small segments are unlabeled.',
             fontsize=11.5, color=MUTED)
    fig.text(.06, .041,
             'Only evaluated levels are shown. Defect rates apply to the full passage; individual question windows may differ.',
             fontsize=11, color=MUTED)
    stem = 'hard66_gold72_small_models_mistranslation_e_separated'
    outputs = []
    for extension in ('png', 'svg'):
        path = OUT / f'{stem}.{extension}'
        fig.savefig(path, dpi=200, facecolor='white')
        outputs.append(str(path))
    plt.close(fig)
    assert len(audit) == 18
    (OUT / 'outcome_counts.json').write_text(json.dumps({
        'sources': sources, 'bar_count': len(audit), 'bars': audit,
        'verification': 'All bars independently recounted from saved results and matched to original chart counts. No new model inference.',
    }, indent=2) + '\n')
    print(json.dumps({'outputs': outputs, 'verified_bars': len(audit)}, indent=2))


if __name__ == '__main__':
    main()
