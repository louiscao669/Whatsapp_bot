#!/usr/bin/env python3
"""Make slide-sized Hard66 figures matching the earlier E-separated charts."""
from collections import Counter
import hashlib
import html
import json
import os
from pathlib import Path
import zipfile

REPO = Path(__file__).resolve().parents[3]
REPORT = REPO / 'evaluation/reports/hard66_small_models_variants_2026-10-28'
OUT = REPORT / 'individual_charts/e_separated'
os.environ.setdefault('MPLCONFIGDIR', str(REPORT / '.matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

MODELS = [('gemma34b', 'Gemma 3 4B'), ('phi4mini38b', 'Phi-4-mini 3.8B'), ('qwen253b', 'Qwen 2.5 3B')]
CATEGORIES = [('correct', 'Correct A–D', '#269275'), ('incorrect_ad', 'Incorrect A–D', '#D98838'),
              ('abstain_e', 'E: cannot tell', '#8575BE'), ('no_valid_answer', 'No valid answer', '#AAB3BD')]
FIGURES = [('omission', 'Omission', ['clean', 'omission/15%', 'omission/30%'], ['0', '15', '30']),
           ('mistranslation', 'Mistranslation', ['clean', 'mistranslation/15%', 'mistranslation/30%'], ['0', '15', '30']),
           ('grammar', 'Grammar', ['clean', 'grammar/30%'], ['0', '30']),
           ('word_by_word', 'Google word-by-word', ['clean', 'google_word_by_word'], ['Clean', 'Google\nword-by-word'])]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results_path = REPORT / 'results.json'
    raw = json.loads(results_path.read_text())
    summaries = {(r['config'], r['variant']): r for r in json.loads((REPORT / 'summary.json').read_text())['configurations']}
    outcomes = {}
    for config, _ in MODELS:
        for condition in ['clean', 'omission/15%', 'omission/30%', 'mistranslation/15%', 'mistranslation/30%', 'grammar/30%', 'google_word_by_word']:
            subset = [r for r in raw if r['config'] == config and r['variant'] == condition]
            assert len(subset) == len({r['id'] for r in subset}) == 65
            counts = Counter(r['grade']['label'] for r in subset)
            saved = summaries[config, condition]
            assert all(counts[label] == saved[label] for label in ['correct', 'incorrect_ad', 'abstain_e', 'invalid', 'failure'])
            counts['no_valid_answer'] = counts['invalid'] + counts['failure']
            assert sum(counts[key] for key, _, _ in CATEGORIES) == 65
            outcomes[config, condition] = {key: counts[key] for key, _, _ in CATEGORIES}
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 12, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'text.color': '#172B3B', 'axes.labelcolor': '#405364',
                         'xtick.color': '#405364', 'ytick.color': '#405364'})
    audit = []
    files = []
    for family, title, conditions, ticks in FIGURES:
        fig, axes = plt.subplots(1, 3, figsize=(16, 9), sharey=True)
        fig.subplots_adjust(left=.072, right=.975, top=.735, bottom=.275, wspace=.20)
        fig.text(.072, .925, 'Hard66 · ' + title, fontsize=29, weight='bold')
        fig.text(.072, .855, 'E responses shown separately · new model results · each bar totals 100%',
                 fontsize=15, color='#526578')
        xs = list(range(len(conditions)))
        for ax, (config, name) in zip(axes, MODELS):
            values = [outcomes[config, method] for method in conditions]
            bottom = [0.0] * len(conditions)
            for key, _, color in CATEGORIES:
                heights = [value[key] / 65 for value in values]
                ax.bar(xs, heights, bottom=bottom, width=.58, color=color,
                       edgecolor='white', linewidth=.7, zorder=3)
                for x, h, b in zip(xs, heights, bottom):
                    if h >= .075:
                        ax.text(x, b+h/2, f'{h:.0%}', ha='center', va='center',
                                fontsize=14, color='white' if key in ('correct', 'abstain_e') else '#172B3B',
                                weight='bold')
                bottom = [b+h for b, h in zip(bottom, heights)]
            assert all(abs(value - 1) < 1e-12 for value in bottom)
            ax.set_title(name, loc='left', fontsize=18, pad=16, weight='bold')
            ax.set_xticks(xs, ticks, fontsize=14)
            ax.set_xlim(-.6, len(xs)-.4)
            ax.set_ylim(0, 1.04)
            ax.set_yticks([0, .25, .5, .75, 1])
            ax.tick_params(axis='y', labelsize=13)
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.grid(axis='y', color='#E1E7ED', zorder=0)
            ax.spines['left'].set_color('#B9C5CF')
            ax.spines['bottom'].set_color('#B9C5CF')
            if family != 'word_by_word':
                ax.set_xlabel('Defect level (%)', labelpad=10, fontsize=14)
            for method, values_for_bar in zip(conditions, values):
                audit.append(dict(family=family, config=config, condition=method, n=65,
                                  counts=values_for_bar,
                                  percentages={k: 100*v/65 for k, v in values_for_bar.items()}))
        axes[0].set_ylabel('Share of all MCQ responses', fontsize=14)
        fig.legend(handles=[Patch(facecolor=color, label=label) for _, label, color in CATEGORIES],
                   loc='lower center', bbox_to_anchor=(.53, .135), ncol=4, frameon=False, fontsize=13)
        fig.text(.072, .095, '65 active MCQs per bar. Correct/incorrect refer to the original answer key. E = “cannot tell from passage.”',
                 fontsize=11.5, color='#526578')
        note = 'Only evaluated conditions are shown. Labels are rounded; small segments are unlabeled. No valid answer is separate from E.'
        fig.text(.072, .058, note, fontsize=10.8, color='#526578')
        if family == 'omission':
            fig.text(.072, .024, 'Omission windows preserve original verse boundaries using the saved deletion records; no deleted content is restored.',
                     fontsize=10.4, color='#526578')
        for ext in ('png', 'svg'):
            path = OUT / f'hard66_{family}_e_separated.{ext}'
            fig.savefig(path, dpi=200, facecolor='white')
            files.append(path)
        plt.close(fig)
    audit_path = OUT / 'outcome_counts.json'
    audit_path.write_text(json.dumps({'source': str(results_path),
                                     'source_sha256': hashlib.sha256(results_path.read_bytes()).hexdigest(),
                                     'models': MODELS, 'bar_count': len(audit), 'bars': audit}, indent=2)+'\n')
    files.append(audit_path)
    cards = []
    for family, title, _, _ in FIGURES:
        stem = 'hard66_' + family + '_e_separated'
        cards.append('<section><h2>'+html.escape(title)+'</h2><p><a href="'+stem+'.png">Download PNG</a> · <a href="'+stem+'.svg">Download editable SVG</a></p><img src="'+stem+'.png" alt="Hard66 '+html.escape(title)+' outcomes for three models"></section>')
    page = OUT / 'index.html'
    page.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hard66 · new model charts</title><style>body{font:16px/1.6 system-ui;background:#f4f6f8;color:#172b3b;margin:0}main{max-width:1440px;margin:auto;padding:28px}section{background:white;border:1px solid #dce3e9;border-radius:12px;padding:22px;margin:24px 0}img{width:100%;height:auto}a{color:#145b81}h1,h2{line-height:1.2}</style><main><h1>Hard66 · new model charts</h1><p>Gemma 3 4B · Phi-4-mini 3.8B · Qwen 2.5 3B. Saved results only; no new model calls.</p><p><a href="hard66_four_graphs_e_separated.zip">Download all PNGs and editable SVGs</a> · <a href="outcome_counts.json">Exact chart counts</a> · <a href="../../index.html">Full evaluation report</a></p>'+''.join(cards)+'</main></html>')
    files.append(page)
    bundle = OUT / 'hard66_four_graphs_e_separated.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
    print(json.dumps({'gallery': str(page), 'bundle': str(bundle), 'bar_count_verified': len(audit),
                      'outputs': [str(p) for p in files]}, indent=2))


if __name__ == '__main__':
    main()
