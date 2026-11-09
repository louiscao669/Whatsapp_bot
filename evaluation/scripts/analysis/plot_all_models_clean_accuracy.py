#!/usr/bin/env python3
"""One chart of saved clean-passage MCQ accuracy on Hard66 and Gold72."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORTS = REPO / 'evaluation/reports'
OUT = REPORTS / 'hard66_gold72_clean_accuracy_2026-10-29'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(REPORTS / 'hard66_small_models_variants_2026-10-28/.matplotlib')

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
    ('llama323b', 'Llama 3.2 3B'),
    ('qwen253b', 'Qwen 2.5 3B'),
    ('phi4mini38b', 'Phi-4-mini 3.8B'),
    ('gemma34b', 'Gemma 3 4B'),
]
DATASETS = [('hard', 'Hard66', 65, '#426A9F'), ('gold', 'Gold72', 71, '#D79932')]


def main():
    sources, results = {}, {}

    def load(path):
        data = path.read_bytes()
        sources[str(path.relative_to(REPO))] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    report = REPORTS / 'qa_rewrite_model_results_2026-10-27'
    prior = load(report / 'individual_charts/e_separated/outcome_counts.json')
    prior = {(r['config'], r['condition']): r for r in prior if r['family'] == 'omission'}
    for row in load(report / 'results_data.json')['conditions']:
        if row['condition'] != 'omission/0%':
            continue
        dataset, config, values = row['dataset'], row['config'], row['after']
        n, correct = values['mcq_n'], values['mcq_correct']
        assert n == (65 if dataset == 'hard' else 71)
        assert sum(values[k] for k in ('mcq_correct', 'mcq_incorrect_ad_count', 'mcq_e_count', 'mcq_unresolved_count')) == n
        assert abs(values['mcq_accuracy'] - correct / n) < 1e-12
        if dataset == 'hard':
            assert prior[config, 'omission/0%']['mcq_correct'] == correct
            assert prior[config, 'omission/0%']['n'] == n
        assert (dataset, config) not in results
        results[dataset, config] = {'n': n, 'correct': correct, 'accuracy': correct / n,
                                   'source': str((report / 'results_data.json').relative_to(REPO))}

    for dataset, _, n, _ in DATASETS:
        prefix = 'hard66' if dataset == 'hard' else 'gold72'
        for campaign in ('small_models_variants', 'llama'):
            if campaign == 'small_models_variants':
                report = REPORTS / f'{prefix}_small_models_variants_2026-10-28'
                select = lambda r: r.get('variant') == 'clean'
            else:
                name = 'hard66_book_mcq_2026-10-28' if dataset == 'hard' else 'gold72_llama_book_mcq_2026-10-28'
                report = REPORTS / name
                select = lambda r: r.get('condition') == 'open_book' and r['config'] == 'llama323b'
            summaries = [r for r in load(report / 'summary.json')['configurations'] if select(r)]
            raw = load(report / 'results.json')
            for summary in summaries:
                config = summary['config']
                subset = [r for r in raw if select(r) and r['config'] == config]
                assert len(subset) == len({r['id'] for r in subset}) == n == summary['n']
                counts = Counter(r['grade']['label'] for r in subset)
                for key in ('correct', 'incorrect_ad', 'abstain_e', 'invalid', 'failure'):
                    assert counts[key] == summary[key]
                assert abs(summary['accuracy'] - counts['correct'] / n) < 1e-12
                assert (dataset, config) not in results
                results[dataset, config] = {'n': n, 'correct': counts['correct'],
                                           'accuracy': counts['correct'] / n,
                                           'source': str((report / 'results.json').relative_to(REPO))}

    assert set(results) == {(d, c) for d, _, _, _ in DATASETS for c, _ in MODELS}
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 13, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.spines.left': False, 'text.color': '#172B3B',
                         'axes.labelcolor': '#526578', 'xtick.color': '#526578', 'ytick.color': '#172B3B'})
    fig, ax = plt.subplots(figsize=(20, 11.25), facecolor='white')
    fig.subplots_adjust(left=.253, right=.97, top=.79, bottom=.165)
    fig.text(.055, .937, 'Clean-passage accuracy · Hard66 and Gold72', fontsize=28, weight='bold')
    fig.text(.055, .884, 'All 8 evaluated model configurations · passages supplied · MCQ only', fontsize=16, color='#526578')
    for i in range(len(MODELS)):
        if i % 2 == 0:
            ax.axhspan(i - .47, i + .47, color='#F3F6F9', zorder=0)
    for dataset, name, n, color in DATASETS:
        offset = -.18 if dataset == 'hard' else .18
        ys = [i + offset for i in range(len(MODELS))]
        values = [100 * results[dataset, config]['accuracy'] for config, _ in MODELS]
        ax.barh(ys, values, height=.30, color=color, zorder=3)
        for y, value in zip(ys, values):
            ax.text(value + .9, y, f'{value:.1f}%', va='center', ha='left', fontsize=13, weight='bold', color=color)
    ax.set_yticks(range(len(MODELS)), [label for _, label in MODELS], fontsize=15)
    ax.tick_params(axis='y', length=0, pad=16)
    ax.set_ylim(len(MODELS) - .45, -.6)
    ax.set_xlim(0, 105)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.set_xlabel('Correct answers / all active MCQs', fontsize=14, labelpad=12)
    ax.grid(axis='x', color='#DCE4EB', linewidth=.8, zorder=1)
    ax.spines['bottom'].set_color('#B9C5CF')
    fig.legend(handles=[Patch(facecolor=color, label=f'{name} ({n} MCQs)') for _, name, n, color in DATASETS],
               loc='upper right', bbox_to_anchor=(.96, .848), ncol=2, frameon=False, fontsize=15,
               handlelength=1.7, columnspacing=2)
    fig.text(.055, .066,
             'Accuracy uses every active question; E responses and invalid answers are not counted as correct. Labels are rounded to one decimal.',
             fontsize=11.5, color='#526578')
    fig.text(.055, .032,
             'Existing clean-passage evaluations, including Llama 3.2 3B open-book MCQ runs. Qwen3 thinking modes are shown separately.',
             fontsize=11.5, color='#526578')
    stem = 'hard66_gold72_all_models_clean_accuracy'
    outputs = []
    for extension in ('png', 'svg'):
        path = OUT / f'{stem}.{extension}'
        fig.savefig(path, dpi=200, facecolor='white')
        outputs.append(str(path))
    plt.close(fig)
    records = [dict(dataset=name, config=config, model_label=label, **results[dataset, config])
               for config, label in MODELS for dataset, name, _, _ in DATASETS]
    (OUT / 'accuracy_counts.json').write_text(json.dumps({'source_sha256': sources, 'results': records}, indent=2) + '\n')
    print(json.dumps({'outputs': outputs, 'verified_bars': len(records),
                      'accuracies': [{k:r[k] for k in ('dataset','model_label','correct','n','accuracy')} for r in records]}, indent=2))


if __name__ == '__main__':
    main()
