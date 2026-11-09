#!/usr/bin/env python3
"""Show observed E-selection rates at every tested Hard66 omission dose."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORTS = REPO / 'evaluation/reports'
OUT = REPORTS / 'hard66_omission_e_rates_2026-10-29'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(REPORTS / 'hard66_small_models_variants_2026-10-28/.matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import PercentFormatter
import numpy as np

MODELS = [
    ('llama321b', 'Llama 3.2 1B'),
    ('qwen2515b', 'Qwen 2.5 1.5B'),
    ('qwen317b_think', 'Qwen3 1.7B · thinking'),
    ('qwen317b_nothink', 'Qwen3 1.7B · no thinking'),
    ('llama323b', 'Llama 3.2 3B'),
    ('qwen253b', 'Qwen 2.5 3B'),
    ('phi4mini38b', 'Phi-4-mini 3.8B'),
    ('gemma34b', 'Gemma 3 4B'),
]
LEVELS = [0, 5, 10, 15, 20, 25, 30]


def main():
    sources, values, audit = {}, {}, []

    def load(path):
        content = path.read_bytes()
        sources[str(path.relative_to(REPO))] = hashlib.sha256(content).hexdigest()
        return json.loads(content)

    def add(config, dose, count, n, source):
        assert n == 65 and 0 <= count <= n
        assert (config, dose) not in values
        values[config, dose] = 100 * count / n
        audit.append({'config': config, 'omission_percent': dose, 'e_count': count,
                      'n': n, 'e_rate_percent': 100 * count / n,
                      'source': str(source.relative_to(REPO))})

    source = REPORTS / 'qa_rewrite_model_results_2026-10-27/results_data.json'
    for row in load(source)['conditions']:
        if row['dataset'] == 'hard' and row['condition'].startswith('omission/'):
            counts = row['after']
            assert sum(counts[k] for k in ('mcq_correct', 'mcq_incorrect_ad_count', 'mcq_e_count', 'mcq_unresolved_count')) == counts['mcq_n']
            dose = int(row['condition'].split('/')[1].rstrip('%'))
            add(row['config'], dose, counts['mcq_e_count'], counts['mcq_n'], source)

    report = REPORTS / 'hard66_small_models_variants_2026-10-28'
    source = report / 'results.json'
    raw = load(source)
    for row in load(report / 'summary.json')['configurations']:
        condition = row['variant']
        if condition == 'clean' or condition.startswith('omission/'):
            subset = [r for r in raw if r['config'] == row['config'] and r['variant'] == condition]
            assert len(subset) == len({r['id'] for r in subset}) == row['n']
            counts = Counter(r['grade']['label'] for r in subset)
            assert counts['abstain_e'] == row['abstain_e']
            dose = 0 if condition == 'clean' else int(condition.split('/')[1].rstrip('%'))
            add(row['config'], dose, counts['abstain_e'], row['n'], source)

    report = REPORTS / 'hard66_book_mcq_2026-10-28'
    source = report / 'results.json'
    subset = [r for r in load(source) if r['config'] == 'llama323b' and r['condition'] == 'open_book']
    assert len(subset) == len({r['id'] for r in subset}) == 65
    row = next(r for r in load(report / 'summary.json')['configurations'] if r['config'] == 'llama323b' and r['condition'] == 'open_book')
    count = sum(r['grade']['label'] == 'abstain_e' for r in subset)
    assert count == row['abstain_e']
    add('llama323b', 0, count, 65, source)
    assert len(values) == 38
    matrix = np.array([[values.get((config, dose), np.nan) for dose in LEVELS] for config, _ in MODELS])
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none', 'text.color': '#172B3B',
                         'axes.labelcolor': '#526578', 'xtick.color': '#526578', 'ytick.color': '#172B3B'})
    fig, ax = plt.subplots(figsize=(20, 11.25), facecolor='white')
    fig.subplots_adjust(left=.275, right=.88, top=.78, bottom=.22)
    fig.text(.055, .935, 'Hard66 · E response rate under omission', fontsize=28, weight='bold')
    fig.text(.055, .878, 'E = “cannot tell from the passage” · percentage of all 65 active MCQs',
             fontsize=16, color='#526578')
    cmap = LinearSegmentedColormap.from_list('e_rate', ['#F6F2FC', '#C5B7E2', '#8575BE', '#5B448E'])
    cmap.set_bad('#E9EDF1')
    im = ax.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=0, vmax=35, aspect='auto')
    for i in range(len(MODELS)):
        for j in range(len(LEVELS)):
            value = matrix[i, j]
            label = '—' if np.isnan(value) else f'{value:.1f}%'
            color = '#8B98A5' if np.isnan(value) else ('white' if value >= 20 else '#30254B')
            ax.text(j, i, label, ha='center', va='center', fontsize=17, weight='bold', color=color)
    ax.set_xticks(range(len(LEVELS)), [f'{n}%' for n in LEVELS], fontsize=15)
    ax.set_yticks(range(len(MODELS)), [label for _, label in MODELS], fontsize=15)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position('top')
    ax.set_xlabel('Omission level (0% = clean passage)', fontsize=14, labelpad=18)
    ax.tick_params(axis='both', which='both', length=0, pad=12)
    ax.set_xticks(np.arange(-.5, len(LEVELS), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(MODELS), 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=3)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cax = fig.add_axes([.905, .22, .016, .56])
    colorbar = fig.colorbar(im, cax=cax, ticks=[0, 10, 20, 30, 35])
    colorbar.ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    colorbar.ax.tick_params(labelsize=12)
    colorbar.outline.set_visible(False)
    colorbar.set_label('E response rate', fontsize=13, labelpad=10, color='#526578')
    fig.text(.055, .147,
             '— = not evaluated. Invalid answers remain in the denominator and are not counted as E.',
             fontsize=12, color='#526578')
    fig.text(.055, .104,
             'Rates describe E selection, not whether E was appropriate. Each dose refers to omission across the full passage.',
             fontsize=12, color='#526578')
    fig.text(.055, .061,
             'The earlier four configurations and the newer three models used different omission-window extraction procedures.',
             fontsize=11.5, color='#526578')
    stem = 'hard66_omission_e_rates_all_models'
    outputs = []
    for extension in ('png', 'svg'):
        path = OUT / f'{stem}.{extension}'
        fig.savefig(path, dpi=200, facecolor='white')
        outputs.append(str(path))
    plt.close(fig)
    (OUT / 'e_rate_counts.json').write_text(json.dumps({'source_sha256': sources, 'conditions': audit}, indent=2) + '\n')
    print(json.dumps({'outputs': outputs, 'verified_cells': len(values)}, indent=2))


if __name__ == '__main__':
    main()
