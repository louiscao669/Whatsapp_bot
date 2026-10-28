#!/usr/bin/env python3
"""Export separate Hard66 charts using the completed rewritten-QA results."""
from pathlib import Path
import json
import os
import zipfile

REPO = Path(__file__).resolve().parents[3]
REPORT = REPO / 'evaluation/reports/qa_rewrite_model_results_2026-10-27'
OUT = REPORT / 'individual_charts'
OUT.mkdir(exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(REPORT / '.matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

MODELS = [
    ('llama321b', 'Llama 3.2 1B', '#A86116', 'o'),
    ('qwen2515b', 'Qwen 2.5 1.5B', '#087EA4', 's'),
    ('qwen317b_think', 'Qwen3 1.7B · thinking', '#8C4AA5', '^'),
    ('qwen317b_nothink', 'Qwen3 1.7B · no thinking', '#2E7D32', 'D'),
]
plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 15,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.labelcolor': '#273746', 'text.color': '#172b3b',
    'xtick.color': '#405364', 'ytick.color': '#405364',
    'svg.fonttype': 'none', 'axes.titlepad': 18,
})


def main():
    data = json.loads((REPORT / 'results_data.json').read_text())
    assert data['verification']['status'] == 'complete'
    rows = {(r['config'], r['condition']): r for r in data['conditions'] if r['dataset'] == 'hard'}
    exported = []
    for family, title in [('grammar', 'Grammar'), ('mistranslation', 'Mistranslation'),
                          ('omission', 'Omission'), ('word_by_word', 'Word-by-word translation')]:
        fig = plt.figure(figsize=(12.8, 7.2), facecolor='white')
        if family == 'grammar':
            grid = fig.add_gridspec(1, 2, width_ratios=[5, 1.2], left=.10, right=.96, bottom=.29, top=.79, wspace=.16)
            ax = fig.add_subplot(grid[0, 0])
            maximum = fig.add_subplot(grid[0, 1], sharey=ax)
        else:
            ax = fig.add_axes([.10, .29, .86, .50])
            maximum = None
        fig.text(.10, .92, 'Hard66 · ' + title, fontsize=26, weight='bold')
        fig.text(.10, .855, 'Updated MCQ accuracy · 65 active questions · four model configurations', fontsize=15, color='#526578')
        if family == 'word_by_word':
            methods = ['omission/0%', 'google_word_by_word']
            xs = [0, 1]
            ax.set_xticks(xs, ['Clean passage', 'Word-by-word passage'])
            ax.set_xlim(-.16, 1.16)
        else:
            xs = [0, 5, 10, 15, 20, 25, 30]
            methods = ['omission/0%'] + [f'{family}/{n}%' for n in xs[1:]]
            ax.set_xticks(xs)
            ax.set_xlabel('Defect level (%)', labelpad=10)
        for config, label, color, marker in MODELS:
            values = [rows[config, condition]['after'] for condition in methods]
            assert all(v['mcq_n'] == 65 for v in values)
            ys = [v['mcq_accuracy'] for v in values]
            assert all(abs(v['mcq_correct'] / 65 - y) < 1e-12 for v, y in zip(values, ys))
            ax.plot(xs, ys, color=color, marker=marker, markersize=7, linewidth=2.5, label=label)
            if maximum is not None:
                value = rows[config, 'grammar/max_approved']['after']
                assert value['mcq_n'] == 57
                offset = {'llama321b': -.21, 'qwen2515b': -.07, 'qwen317b_think': .07, 'qwen317b_nothink': .21}[config]
                maximum.scatter(offset, value['mcq_accuracy'], color=color, marker=marker, s=65, zorder=3)
        ax.set_ylabel('MCQ accuracy', labelpad=12)
        for plot in [ax] + ([maximum] if maximum is not None else []):
            plot.set_ylim(0, 1.02)
            plot.set_yticks([0, .2, .4, .6, .8, 1])
            plot.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            plot.grid(axis='y', color='#dce4ec', linewidth=.9)
            plot.set_axisbelow(True)
            plot.tick_params(axis='both', length=4)
            plot.spines['left'].set_color('#b8c5d0')
            plot.spines['bottom'].set_color('#b8c5d0')
        if maximum is not None:
            maximum.set_xlim(-.5, .5)
            maximum.set_xticks([0], ['Maximum*'])
            maximum.tick_params(axis='y', labelleft=False, left=False)
            maximum.spines['left'].set_visible(False)
            maximum.set_title('57 MCQs', fontsize=14, color='#526578')
        fig.legend(*ax.get_legend_handles_labels(), loc='lower center', bbox_to_anchor=(.54, .105),
                   ncol=2, frameon=False, fontsize=14, columnspacing=2.6, handlelength=2.6)
        note = 'Results after the accepted QA rewrites; unchanged question results are retained.'
        fig.text(.10, .065, note, fontsize=11, color='#526578')
        if maximum is not None:
            fig.text(.10, .025, '*Maximum uses approved sentence defects and the original 8-passage subset (57 MCQs).',
                     fontsize=10.5, color='#526578')
        for ext in ('png', 'svg'):
            path = OUT / f'hard66_{family}_updated.{ext}'
            fig.savefig(path, dpi=200, facecolor='white')
            exported.append(path)
        plt.close(fig)
    bundle = OUT / 'hard66_four_graphs.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in exported:
            archive.write(path, path.name)
    print(json.dumps({'graphs': [str(p) for p in exported], 'bundle': str(bundle)}, indent=2))


if __name__ == '__main__':
    main()
