#!/usr/bin/env python3
"""Compare omission-induced changes in E rate, relative to clean baselines."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORTS = REPO / 'evaluation/reports'
OUT = REPORTS / 'hard66_gold72_abstention_omission_2026-10-29'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(REPORTS / 'hard66_small_models_variants_2026-10-28/.matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

MODELS = [
    ('llama321b', 'Llama 3.2 1B'),
    ('qwen2515b', 'Qwen 2.5 1.5B'),
    ('qwen317b_think', 'Qwen3 1.7B · thinking'),
    ('qwen317b_nothink', 'Qwen3 1.7B · no thinking'),
    ('qwen253b', 'Qwen 2.5 3B'),
    ('phi4mini38b', 'Phi-4-mini 3.8B'),
    ('gemma34b', 'Gemma 3 4B'),
]
DATASETS = [('hard', 'Hard66', 65, '#426A9F'), ('gold', 'Gold72', 71, '#D79932')]
DOSES = [0, 15, 30]


def main():
    counts, sources = {}, {}

    def load(path):
        content = path.read_bytes()
        sources[str(path.relative_to(REPO))] = hashlib.sha256(content).hexdigest()
        return json.loads(content)

    for row in load(REPORTS / 'qa_rewrite_model_results_2026-10-27/results_data.json')['conditions']:
        if row['condition'] not in [f'omission/{dose}%' for dose in DOSES]:
            continue
        dataset, config, values = row['dataset'], row['config'], row['after']
        assert values['mcq_n'] == (65 if dataset == 'hard' else 71)
        assert sum(values[k] for k in ('mcq_correct', 'mcq_incorrect_ad_count', 'mcq_e_count', 'mcq_unresolved_count')) == values['mcq_n']
        dose = int(row['condition'].split('/')[1].rstrip('%'))
        assert (dataset, config, dose) not in counts
        counts[dataset, config, dose] = values['mcq_e_count']

    for dataset, _, n, _ in DATASETS:
        prefix = 'hard66' if dataset == 'hard' else 'gold72'
        report = REPORTS / f'{prefix}_small_models_variants_2026-10-28'
        raw = load(report / 'results.json')
        for row in load(report / 'summary.json')['configurations']:
            condition = row['variant']
            if condition not in ('clean', 'omission/15%', 'omission/30%'):
                continue
            config = row['config']
            subset = [r for r in raw if r['config'] == config and r['variant'] == condition]
            assert len(subset) == len({r['id'] for r in subset}) == row['n'] == n
            observed = Counter(r['grade']['label'] for r in subset)
            assert observed['abstain_e'] == row['abstain_e']
            dose = 0 if condition == 'clean' else int(condition.split('/')[1].rstrip('%'))
            assert (dataset, config, dose) not in counts
            counts[dataset, config, dose] = observed['abstain_e']
    assert len(counts) == 42

    records, changes = [], {}
    for config, label in MODELS:
        for dataset, name, n, _ in DATASETS:
            clean = counts[dataset, config, 0]
            for dose in (15, 30):
                e = counts[dataset, config, dose]
                delta = 100 * (e - clean) / n
                changes[dataset, config, dose] = delta
                records.append({'dataset': name, 'config': config, 'model_label': label,
                                'omission_percent': dose, 'n': n, 'clean_e_count': clean,
                                'omission_e_count': e, 'clean_e_rate_percent': 100 * clean / n,
                                'omission_e_rate_percent': 100 * e / n,
                                'change_from_clean_percentage_points': delta})

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none', 'font.size': 13,
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
                         'text.color': '#172B3B', 'axes.labelcolor': '#526578',
                         'xtick.color': '#526578', 'ytick.color': '#172B3B'})
    fig, axes = plt.subplots(1, 2, figsize=(20, 11.25), sharey=True, facecolor='white')
    fig.subplots_adjust(left=.255, right=.975, top=.745, bottom=.23, wspace=.13)
    fig.text(.055, .938, 'How strongly does omission increase abstention?', fontsize=28, weight='bold')
    fig.text(.055, .88, 'Change in E rate = E rate with omission − E rate on clean passages', fontsize=17, color='#526578')
    fig.legend(handles=[Patch(facecolor=c, label=f'{name} ({n} MCQs)') for _, name, n, c in DATASETS],
               loc='upper left', bbox_to_anchor=(.05, .846), ncol=2, frameon=False,
               fontsize=15, handlelength=1.7, columnspacing=2)
    for ax, dose in zip(axes, (15, 30)):
        for i in range(len(MODELS)):
            if i % 2 == 0:
                ax.axhspan(i - .47, i + .47, color='#F3F6F9', zorder=0)
        for dataset, _, _, color in DATASETS:
            offset = -.18 if dataset == 'hard' else .18
            positions = [i + offset for i in range(len(MODELS))]
            values = [changes[dataset, config, dose] for config, _ in MODELS]
            ax.barh(positions, values, height=.30, color=color, zorder=3)
            for y, value in zip(positions, values):
                if value == 0:
                    ax.plot(0, y, marker='|', markersize=13, markeredgewidth=2, color=color, clip_on=False, zorder=4)
                label = '0.0' if value == 0 else f'{value:+.1f}'
                ax.text(value + .45, y, label, ha='left', va='center', fontsize=13, weight='bold', color=color)
        ax.set_title(f'{dose}% omission', loc='left', fontsize=20, pad=18, weight='bold')
        ax.set_xlim(0, 31)
        ax.set_xticks([0, 5, 10, 15, 20, 25, 30])
        ax.set_ylim(len(MODELS) - .45, -.6)
        ax.set_xlabel('Increase in E rate (percentage points)', fontsize=13, labelpad=12)
        ax.set_yticks(range(len(MODELS)), [label for _, label in MODELS], fontsize=15)
        ax.tick_params(axis='y', length=0, pad=16)
        ax.grid(axis='x', color='#DCE4EB', linewidth=.8, zorder=1)
        ax.spines['bottom'].set_color('#B9C5CF')
    fig.text(.055, .137,
             'Larger increases mean more abstention in response to omission after accounting for the clean-passage baseline.',
             fontsize=12.5, color='#526578')
    fig.text(.055, .096,
             'This measures responsiveness, not the correctness of E choices. Llama 3.2 3B is excluded because no omission runs are available.',
             fontsize=11.5, color='#526578')
    fig.text(.055, .055,
             'Shared tested doses are shown. Compare datasets within each model; omission-window extraction differs between model campaigns.',
             fontsize=11.5, color='#526578')
    stem = 'hard66_gold72_omission_abstention_change'
    outputs = []
    for extension in ('png', 'svg'):
        path = OUT / f'{stem}.{extension}'
        fig.savefig(path, dpi=200, facecolor='white')
        outputs.append(str(path))
    plt.close(fig)
    (OUT / 'abstention_change_counts.json').write_text(json.dumps({
        'definition': '100 * (E count at dose - E count at clean baseline) / all active MCQs',
        'source_sha256': sources, 'results': records,
    }, indent=2) + '\n')
    print(json.dumps({'outputs': outputs, 'verified_source_cells': len(counts), 'bars': len(records)}, indent=2))


if __name__ == '__main__':
    main()
