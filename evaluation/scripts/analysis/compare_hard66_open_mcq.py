#!/usr/bin/env python3
"""Compare saved open and MCQ results on their 64 shared Hard66 question IDs."""
from collections import Counter, defaultdict
import hashlib
import html
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RUN = REPO / 'evaluation/runs/qa_rewrite_rerun_2026-10-27'
OUT = REPO / 'evaluation/reports/hard66_open_vs_mcq_2026-10-29'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(REPO / 'evaluation/reports/hard66_small_models_variants_2026-10-28/.matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

MODELS = [('llama321b', 'Llama 3.2 1B'), ('qwen2515b', 'Qwen 2.5 1.5B'),
          ('qwen317b_think', 'Qwen3 1.7B · thinking')]
RATES = [5, 10, 15, 20, 25, 30]
METHODS = ['omission/0%'] + [f'{f}/{r}%' for f in ('omission', 'mistranslation', 'grammar') for r in RATES] + ['google_word_by_word']
OVERVIEW = [('omission/0%', 'Clean'), ('omission/15%', 'Omission 15%'), ('omission/30%', 'Omission 30%'),
            ('mistranslation/15%', 'Mistranslation 15%'), ('mistranslation/30%', 'Mistranslation 30%'),
            ('grammar/30%', 'Grammar 30%'), ('google_word_by_word', 'Google\nword-by-word')]
BLUE, PURPLE, MUTED = '#426A9F', '#8575BE', '#526578'


def main():
    hashes = {}

    def read(path):
        raw = path.read_bytes()
        hashes[str(path.relative_to(REPO))] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    manifest = read(RUN / 'manifest.json')
    reference = read(REPO / 'evaluation/reports/qa_rewrite_model_results_2026-10-27/results_data.json')
    reference = {(r['config'], r['condition']): r['after'] for r in reference['conditions'] if r['dataset'] == 'hard'}
    groups, paths = defaultdict(list), defaultdict(list)
    for key, cell in manifest['cells'].items():
        if cell['dataset'] != 'hard' or cell['config'] not in dict(MODELS) or cell['method'] not in METHODS:
            continue
        path = RUN / 'updated_runs' / key / 'scores_target_llama.json'
        group = cell['config'], cell['method']
        groups[group].extend(read(path)['items'])
        paths[group].append(str(path.relative_to(REPO)))

    summaries, details, paired_ids = [], [], None
    mismatches, excluded = {}, set()
    for config, name in MODELS:
        for method in METHODS:
            rows = groups[config, method]
            assert len(paths[config, method]) == 10
            assert len(rows) == len({r['id'] for r in rows}) == 129
            opens = {r['id'].removesuffix('-open'): r for r in rows if r['q_type'] == 'open'}
            mcqs = {r['id'].removesuffix('-mcq'): r for r in rows if r['q_type'] == 'mcq'}
            common = sorted(opens.keys() & mcqs.keys())
            assert len(opens) == len(common) == 64 and len(mcqs) == 65
            if paired_ids is None:
                paired_ids = common
            assert common == paired_ids
            excluded.update(mcqs.keys() - opens.keys())
            hist = Counter(r['llm_score'] for r in opens.values())
            assert set(hist) <= {0, .5, 1}
            assert all(r['llm_score'] == 0 for r in opens.values() if r.get('generation_error'))
            assert not any(r['direct_correct'] for r in mcqs.values() if r.get('generation_error'))
            full, partial = hist[1], hist[.5]
            weighted = (full + .5 * partial) / 64
            mcq_all_correct = sum(bool(r['direct_correct']) for r in mcqs.values())
            mcq_paired_correct = sum(bool(mcqs[k]['direct_correct']) for k in common)
            ref = reference[config, method]
            assert ref['open_n'] == 64 and ref['mcq_n'] == 65
            assert abs(ref['open_score_mean'] - weighted) < 1e-12
            assert ref['mcq_correct'] == mcq_all_correct
            result = dict(config=config, model=name, condition=method, matched_n=64,
                          mcq_correct=mcq_paired_correct, mcq_accuracy=mcq_paired_correct / 64,
                          open_full_credit=full, open_full_credit_rate=full / 64,
                          open_partial=partial, open_zero=hist[0], open_mean_score=weighted,
                          open_failures=sum(bool(r.get('generation_error')) for r in opens.values()),
                          mcq_failures=sum(bool(mcqs[k].get('generation_error')) for k in common),
                          original_mcq_n=65, original_mcq_correct=mcq_all_correct,
                          original_mcq_accuracy=mcq_all_correct / 65,
                          source_files=paths[config, method])
            summaries.append(result)
            for key in common:
                op, mc = opens[key], mcqs[key]
                if op['question'] != mc['question']:
                    mismatches[key] = {'open_question': op['question'], 'mcq_question': mc['question']}
                details.append({'config': config, 'condition': method, 'id': key,
                                'passage': op['passage_reference'], 'open_question': op['question'],
                                'mcq_question': mc['question'], 'open_expected': op['standard_answer'],
                                'open_answer': op['generated_answer'], 'open_score': op['llm_score'],
                                'open_judge_rationale': op.get('llm_rationale'),
                                'mcq_answer': mc['generated_answer'], 'mcq_correct': bool(mc['direct_correct']),
                                'open_generation_error': op.get('generation_error'),
                                'mcq_generation_error': mc.get('generation_error')})
    assert len(summaries) == 60 and len(details) == 3840
    assert excluded == {'uw-t1_1kgs13:e302'}
    lookup = {(r['config'], r['condition']): r for r in summaries}
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 12, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
                         'text.color': '#172B3B', 'axes.labelcolor': MUTED, 'xtick.color': MUTED, 'ytick.color': '#172B3B'})

    def save(fig, stem):
        for ext in ('png', 'svg'):
            fig.savefig(OUT / f'{stem}.{ext}', dpi=200, facecolor='white')
        plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(20, 11.25), sharey=True, facecolor='white')
    fig.subplots_adjust(left=.16, right=.985, top=.755, bottom=.265, wspace=.12)
    fig.text(.055, .938, 'Hard66 · Open-ended answers versus MCQ', fontsize=28, weight='bold')
    fig.text(.055, .88, 'Full-credit rates on the same 64 question pairs · saved results with accepted rewrites', fontsize=16, color=MUTED)
    for ax, (config, name) in zip(axes, MODELS):
        for i in range(len(OVERVIEW)):
            if i % 2 == 0:
                ax.axhspan(i - .47, i + .47, color='#F3F6F9', zorder=0)
        for field, color, offset in [('mcq_accuracy', BLUE, -.18), ('open_full_credit_rate', PURPLE, .18)]:
            ys = [i + offset for i in range(len(OVERVIEW))]
            values = [lookup[config, method][field] for method, _ in OVERVIEW]
            ax.barh(ys, values, height=.30, color=color, zorder=3)
            for y, v in zip(ys, values):
                ax.text(v + .018, y, f'{v:.1%}', va='center', ha='left', fontsize=11, weight='bold', color=color)
        ax.set_title(name, loc='left', fontsize=17, weight='bold', pad=18)
        ax.set_yticks(range(len(OVERVIEW)), [label for _, label in OVERVIEW], fontsize=14)
        ax.set_ylim(len(OVERVIEW) - .45, -.6)
        ax.set_xlim(0, 1.055)
        ax.set_xticks([0, .25, .5, .75, 1])
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.set_xlabel('Fully correct answers', labelpad=10, fontsize=13)
        ax.tick_params(axis='y', length=0, pad=12)
        ax.grid(axis='x', color='#DCE4EB', zorder=0)
        ax.spines['bottom'].set_color('#B9C5CF')
    fig.legend(handles=[Patch(facecolor=BLUE, label='MCQ: correct choice'), Patch(facecolor=PURPLE, label='Open: full credit (score 1)')],
               loc='lower center', bbox_to_anchor=(.56, .16), ncol=2, frameon=False, fontsize=15)
    fig.text(.055, .121, 'Open answers were translated into English and graded by GPT-4.1-mini. Partial credit (0.5) is not counted as fully correct.', fontsize=11.5, color=MUTED)
    fig.text(.055, .081, 'Both formats use 64 matched questions here; earlier MCQ charts used 65. Failed responses remain in the denominator.', fontsize=11.5, color=MUTED)
    fig.text(.055, .041, f'Two matched pairs have different question wording. Full dose curves and partial-credit results are included in the linked report.', fontsize=11.5, color=MUTED)
    save(fig, 'hard66_open_vs_mcq_overview')

    for family, title in [('omission', 'Omission'), ('mistranslation', 'Mistranslation'), ('grammar', 'Grammar')]:
        fig, axes = plt.subplots(1, 3, figsize=(20, 11.25), sharey=True, facecolor='white')
        fig.subplots_adjust(left=.065, right=.975, top=.74, bottom=.26, wspace=.14)
        fig.text(.065, .93, f'Hard66 · Open versus MCQ · {title}', fontsize=28, weight='bold')
        fig.text(.065, .87, '64 matched question pairs per model and dose · the open mean includes partial credit', fontsize=16, color=MUTED)
        for ax, (config, name) in zip(axes, MODELS):
            methods = ['omission/0%'] + [f'{family}/{rate}%' for rate in RATES]
            for field, color, marker, linestyle, label in [
                ('mcq_accuracy', BLUE, 'o', '-', 'MCQ: correct choice'),
                ('open_full_credit_rate', PURPLE, 's', '-', 'Open: full credit'),
                ('open_mean_score', '#6A7280', '^', '--', 'Open: mean score, with partial credit')]:
                ax.plot([0] + RATES, [lookup[config, m][field] for m in methods], color=color,
                        marker=marker, linestyle=linestyle, linewidth=2.3, markersize=6, label=label)
            ax.set_title(name, loc='left', fontsize=18, weight='bold', pad=16)
            ax.set_ylim(0, 1.02)
            ax.set_xlim(-1, 31)
            ax.set_xticks([0] + RATES)
            ax.set_yticks([0, .25, .5, .75, 1])
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.set_xlabel(f'{title} level (%)', fontsize=13, labelpad=10)
            ax.grid(color='#E1E7ED')
            ax.spines['bottom'].set_color('#B9C5CF')
        axes[0].set_ylabel('Correct rate / fraction of maximum score', fontsize=13)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(.52, .14), ncol=3, frameon=False, fontsize=13)
        fig.text(.065, .10, 'Open mean = (full-credit answers + 0.5 × partial answers) / 64; this is not strict accuracy.', fontsize=12, color=MUTED)
        fig.text(.065, .057, 'Saved GPT-4.1-mini grades after English back-translation. Different scoring methods and two stem differences limit causal interpretation.', fontsize=11.5, color=MUTED)
        save(fig, f'hard66_open_vs_mcq_{family}')

    result = {'matching': {'n': 64, 'base_question_ids': paired_ids, 'excluded_mcq_only_ids': sorted(excluded),
                           'wording_differences': mismatches}, 'judge_settings': manifest['settings'],
              'metrics': {'open_full_credit_rate': 'count of saved open scores equal to 1, divided by 64',
                          'open_mean_score': 'mean of saved scores 0, 0.5, 1; failures retained as 0',
                          'mcq_accuracy': 'correct MCQ choices among the same 64 base question IDs'},
              'source_sha256': hashes, 'summaries': summaries}
    (OUT / 'comparison_results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'paired_question_results.json').write_text(json.dumps(details, ensure_ascii=False, indent=2) + '\n')
    e = html.escape
    def method_label(method):
        return 'Clean' if method == 'omission/0%' else 'Google word-by-word' if method == 'google_word_by_word' else method.replace('/', ' ').capitalize()
    parts = ['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hard66: Open-ended versus MCQ</title><style>body{margin:0;background:#f3f6f9;color:#172b3b;font:16px/1.6 system-ui}main{max-width:1500px;margin:auto;padding:30px}section{background:white;border-radius:10px;padding:24px;margin:24px 0}img{width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:9px;text-align:right;border-bottom:1px solid #dce4eb}th:first-child,td:first-child{text-align:left}th{background:#f3f6f9}a{color:#235d8f}.scroll{overflow:auto}</style><main>
<h1>Hard66: Open-ended versus MCQ</h1><p>Existing results for Llama 3.2 1B, Qwen 2.5 1.5B, and Qwen3 1.7B with thinking. No model answers or grades were regenerated.</p>
<p>We match 64 question IDs in both formats across 10 passages. One MCQ-only item, uw-t1_1kgs13:e302, is excluded from the paired comparisons. The original 65-item MCQ totals are also retained below.</p>
<p>MCQs use direct answer-key scoring. Open answers were translated into English and graded by GPT-4.1-mini: full credit = 1, partial = 0.5, incorrect or failed = 0. The open mean includes partial credit and is not strict accuracy. Two matched pairs have different wording; this comparison does not isolate the effect of answer choices. Grammar Max and the separate 100% grammar condition have no open results and are excluded.</p>
<p><a href="comparison_results.json">Summary data and verification</a> · <a href="paired_question_results.json">All 3,840 matched question results</a></p>''']
    for stem, title in [('hard66_open_vs_mcq_overview', 'Selected conditions')] + [(f'hard66_open_vs_mcq_{f}', f.title() + ': all tested doses') for f in ('omission', 'mistranslation', 'grammar')]:
        parts.append(f'<section><h2>{title}</h2><p><a href="{stem}.png">PNG</a> · <a href="{stem}.svg">Editable SVG</a></p><img src="{stem}.png" alt="{e(title)}"></section>')
    for config, name in MODELS:
        parts.append(f'<section><h2>{e(name)}</h2><div class="scroll"><table><tr><th>Condition</th><th>MCQ correct /64</th><th>Open full /64</th><th>Open partial</th><th>Open mean ×100</th><th>Open failures</th><th>Original MCQ /65</th></tr>')
        for method in METHODS:
            r = lookup[config, method]
            parts.append(f'<tr><td>{e(method_label(method))}</td><td>{r["mcq_correct"]}/64 ({r["mcq_accuracy"]:.1%})</td><td>{r["open_full_credit"]}/64 ({r["open_full_credit_rate"]:.1%})</td><td>{r["open_partial"]}</td><td>{100*r["open_mean_score"]:.1f}</td><td>{r["open_failures"]}</td><td>{r["original_mcq_correct"]}/65 ({r["original_mcq_accuracy"]:.1%})</td></tr>')
        parts.append('</table></div></section>')
    parts.append('<section><h2>Wording differences in matched pairs</h2>')
    for key, value in mismatches.items():
        parts.append(f'<p><b>{e(key)}</b><br>Open: {e(value["open_question"])}<br>MCQ: {e(value["mcq_question"])}</p>')
    parts.append('</section></main></html>')
    (OUT / 'index.html').write_text(''.join(parts))
    print(json.dumps({'report': str(OUT / 'index.html'), 'groups': len(summaries), 'matched_results': len(details),
                      'clean': [{k: r[k] for k in ('model','mcq_correct','open_full_credit','open_partial','open_mean_score','open_failures')} for r in summaries if r['condition'] == 'omission/0%']}, indent=2))


if __name__ == '__main__':
    main()
