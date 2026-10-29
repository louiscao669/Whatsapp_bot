#!/usr/bin/env python3
"""Plot the completed Gold72 small-model variant comparison."""
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import run_gold72_small_models_variants as run

os.environ.setdefault('MPLCONFIGDIR', str(run.ROOT / 'matplotlib_cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def main():
    summary = json.loads((run.OUT / 'summary.json').read_text())
    lookup = {(s['config'], s['variant']): s for s in summary['configurations']}
    methods = ['clean'] + run.METHODS
    colors = {'correct': '#286c9e', 'incorrect_ad': '#df9850', 'abstain_e': '#a6b0bc',
              'invalid': '#b46a9b', 'failure': '#963f4d'}
    labels = {'correct': 'Original-key match', 'incorrect_ad': 'Other A–D', 'abstain_e': 'E: insufficient information',
              'invalid': 'Invalid', 'failure': 'Failed'}
    outcomes = [k for k in run.baseline.OUTCOMES if any(s[k] for s in summary['configurations'])]
    fig, axes = plt.subplots(1, 3, figsize=(15.2, 5.8), sharey=True)
    fig.patch.set_facecolor('#ffffff')
    for ax, (config, _) in zip(axes, run.baseline.MODELS):
        left = [0.0] * len(methods)
        for outcome in outcomes:
            values = [100 * lookup[config, method][outcome] / 71 for method in methods]
            ax.barh(range(len(methods)), values, left=left, color=colors[outcome], height=0.65,
                    edgecolor='white', linewidth=0.8)
            for y, (start, width, method) in enumerate(zip(left, values, methods)):
                count = lookup[config, method][outcome]
                if width >= 7:
                    ax.text(start + width/2, y, str(count), ha='center', va='center', fontsize=10,
                            color='white' if outcome == 'correct' else '#192b3a', fontweight='bold')
            left = [start + value for start, value in zip(left, values)]
        ax.set_title(run.baseline.LABELS[config], fontsize=13, fontweight='bold', pad=14)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
        ax.set_yticks(range(len(methods)), [run.METHOD_LABELS[m] for m in methods])
        ax.tick_params(axis='both', length=0, labelsize=10)
        ax.grid(axis='x', alpha=0.15, zorder=0)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_visible(False)
    axes[0].invert_yaxis()
    fig.suptitle('Gold72: responses across passage conditions', x=0.04, y=0.98,
                 ha='left', fontsize=18, fontweight='bold', color='#172b3b')
    fig.text(0.04, 0.925, '71 MCQs per bar · segment labels are response counts · clean results reused from the previous run',
             fontsize=11, color='#53616d')
    handles = [Patch(facecolor=colors[k], label=labels[k]) for k in outcomes]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.54, 0.06), ncol=len(handles),
               frameon=False, fontsize=11)
    fig.text(0.04, 0.025, 'Agreement uses the original answer key. E is separate; these are not per-variant answerability judgments.',
             fontsize=10, color='#53616d')
    fig.subplots_adjust(left=0.145, right=0.985, bottom=0.20, top=0.82, wspace=0.12)
    fig.savefig(run.OUT / 'outcomes.png', dpi=180, facecolor='white')
    fig.savefig(run.OUT / 'outcomes.svg', facecolor='white')
    plt.close(fig)
    path = run.OUT / 'index.html'
    document = path.read_text()
    block = '<div id="outcome-chart"><img src="outcomes.png" alt="Gold72 outcome counts by model and passage condition" style="width:100%;height:auto"><p><a href="outcomes.png">Download PNG</a> · <a href="outcomes.svg">Download editable SVG</a></p></div>'
    if 'id="outcome-chart"' not in document:
        document = document.replace('<h2>All outcomes</h2>', block + '<h2>All outcomes</h2>')
        path.write_text(document)
    print(str(run.OUT / 'outcomes.png'))


if __name__ == '__main__':
    main()
