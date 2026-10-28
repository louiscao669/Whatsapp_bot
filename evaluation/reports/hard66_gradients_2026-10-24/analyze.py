"""Plot the completed Hard66 campaign without changing its results."""
import hashlib
import html
import json
import os
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
ROOT = REPO / 'evaluation/runs/hard66_full_ladder_2026-10-23'
os.environ['MPLCONFIGDIR'] = str(OUT / '.matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

MODELS = ['llama3.2:1b', 'qwen2.5:1.5b', 'qwen3:1.7b']
LABELS = ['Llama 3.2 1B', 'Qwen 2.5 1.5B', 'Qwen 3 1.7B (thinking)']
COLORS = ['#9c5700', '#0074b4', '#a13b82']
MARKERS = ['s', 'o', '^']
RATES = [0, 5, 10, 15, 20, 25, 30]
state = json.loads((ROOT / 'campaign_state.json').read_text())
assert state['status'] == 'complete' and state['completed_cells'] == 420
groups = defaultdict(list)
records = []
for key, cell in state['cells'].items():
    stage, model, pid, method = key.split('/', 3)
    slug = model.replace(':', '').replace('.', '') + '_think'
    directory = ROOT / pid / slug / method
    for name, digest in cell['result_hashes'].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    answers = {r['id']: r for r in json.loads((directory / 'generated_answers_target_llama.json').read_text())}
    scores = json.loads((directory / 'scores_target_llama.json').read_text())['items']
    assert len(scores) == len(answers) and {r['id'] for r in scores} == set(answers)
    rate = 0 if stage == 'clean' else None if stage == 'wbw' else int(method.split('/')[1][:-1])
    for row in scores:
        answer = answers[row['id']]
        error = answer.get('generation_error')
        value = float(bool(row['direct_correct'])) if row['q_type'] == 'mcq' else row['llm_score']
        assert value in (0, .5, 1)
        # Failed generations remain in the denominator. The saved scores already
        # assign zero to all 55 failures; make the policy explicit here.
        if error:
            assert value == 0
        record = {'stage': stage, 'rate': rate, 'model': model, 'passage': pid,
                  'id': row['id'], 'form': row['q_type'], 'score': value,
                  'generation_error': error,
                  'genuine_abstention': row['q_type'] == 'mcq' and not error and answer.get('selected_choice') == 'E',
                  'fallback_choice': answer.get('selected_choice') if answer.get('selected_choice_source') == 'random_empty_response_fallback' else None}
        groups[stage, rate, model, row['q_type']].append(record)
        records.append(record)
assert len(records) == 5418

summary = []
lookup = {}
for (stage, rate, model, form), rows in groups.items():
    n = len(rows)
    assert n == (65 if form == 'mcq' else 64)
    valid = [r for r in rows if not r['generation_error']]
    item = {'stage': stage, 'rate': rate, 'model': model, 'form': form, 'n': n,
            'score_percent': 100 * sum(r['score'] for r in rows) / n,
            'fully_correct': sum(r['score'] == 1 for r in rows),
            'partial': sum(r['score'] == .5 for r in rows),
            'generation_errors': n - len(valid),
            'genuine_E': sum(r['genuine_abstention'] for r in rows),
            'successful_only_score_percent': 100 * sum(r['score'] for r in valid) / len(valid)}
    summary.append(item)
    lookup[stage, rate, model, form] = item

notes = [
    'Scores use the clean-source answer key, including for defective passages.',
    'Each model/condition contains 65 MCQs and 64 open answers from 10 passages; questions receive equal weight.',
    'MCQ accuracy is binary. Open-answer mean score gives 1 for correct, 0.5 for partial, and 0 for incorrect.',
    'All 55 generation failures remain in the denominator with score 0. Code-generated fallback choices are not counted as genuine E abstentions.',
    'The same clean results are reused at 0% for both plots. Word-by-word is a separate condition with no assigned defect percentage.',
    'The x-axis shows nominal whole-passage defect rates; models answered from curated local verse windows.',
    'These are descriptive observed results, with no fitted trend or claim of statistical significance.'
]
report = {'source_run': str(ROOT), 'verified_cells': len(state['cells']), 'rows': len(records),
          'generation_errors': sum(bool(r['generation_error']) for r in records),
          'notes': notes, 'summary': summary, 'records': records}
(OUT / 'gradient_data.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 12,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.labelcolor': '#343a40', 'text.color': '#202832',
                     'xtick.color': '#4d5560', 'ytick.color': '#4d5560'})
for form in ['mcq', 'open']:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.8), sharey=True)
    fig.subplots_adjust(left=.085, right=.98, top=.73, bottom=.20, wspace=.13)
    title = 'MCQ accuracy' if form == 'mcq' else 'Open-answer mean score'
    fig.suptitle(title + ' across defect levels', x=.085, y=.97, ha='left', fontsize=18)
    for ax, stage in zip(axes, ['omission', 'mistranslation']):
        for model, label, color, marker in zip(MODELS, LABELS, COLORS, MARKERS):
            values = [lookup['clean' if rate == 0 else stage, rate, model, form]['score_percent'] for rate in RATES]
            ax.plot(RATES, values, color=color, marker=marker, linewidth=2.1,
                    markersize=5.5, label=label)
        ax.set(title=stage.capitalize(), xlim=(-1, 31), ylim=(0, 100),
               xticks=RATES, yticks=[0, 20, 40, 60, 80, 100], xlabel='Nominal passage defect (%)')
        ax.yaxis.set_major_formatter(PercentFormatter())
        ax.grid(axis='y', color='#dce1e5', linewidth=.7)
        ax.set_axisbelow(True)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(.075, .90),
               ncol=3, frameon=False, fontsize=11, handlelength=1.7, columnspacing=1.5)
    caption = ('65 MCQs per point. E counts as incorrect against the clean answer key.' if form == 'mcq'
               else '64 open answers per point. Correct = 1; partial = 0.5; incorrect = 0.')
    fig.text(.085, .075, caption + '\nGeneration failures count as 0. The same clean baseline is reused at 0%.',
             fontsize=10.2, color='#505861', va='center')
    fig.savefig(OUT / f'{form}_gradient.png', dpi=180, facecolor='white')
    fig.savefig(OUT / f'{form}_gradient.pdf', facecolor='white')
    plt.close(fig)

def table(form):
    header = '<tr><th>Condition</th>' + ''.join(f'<th>{html.escape(x)}</th>' for x in LABELS) + '</tr>'
    rows = ''
    conditions = [('clean', 0)] + [(s, rate) for s in ['omission', 'mistranslation'] for rate in RATES[1:]] + [('wbw', None)]
    for stage, rate in conditions:
        label = 'Clean' if stage == 'clean' else 'Word-by-word' if stage == 'wbw' else f'{stage.capitalize()} {rate}%'
        rows += '<tr><td>' + label + '</td>'
        for model in MODELS:
            x = lookup[stage, rate, model, form]
            details = f'{x["generation_errors"]} failures'
            if form == 'mcq':
                details += f'; {x["genuine_E"]} genuine E answers'
            rows += f'<td>{x["score_percent"]:.2f}%<small>{details}</small></td>'
        rows += '</tr>'
    return '<table><thead>' + header + '</thead><tbody>' + rows + '</tbody></table>'

page = '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hard66 gradients</title><style>body{max-width:1080px;margin:32px auto;padding:0 18px;font:16px/1.55 system-ui;color:#202832}img{width:100%;height:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:9px;text-align:right;border-bottom:1px solid #ddd}th:first-child,td:first-child{text-align:left}small{display:block;font-size:12px;color:#626973}.scroll{overflow-x:auto}</style><h1>Hard66: completed variant gradients</h1><p>420 combinations; 5,418 answers. Grammar is excluded from this report.</p>'
for form in ['mcq', 'open']:
    page += f'<img src="{form}_gradient.png" alt="{form} scores over omission and mistranslation rates"><div class="scroll">' + table(form) + '</div>'
page += '<h2>How to read these results</h2><ul>' + ''.join('<li>'+html.escape(n)+'</li>' for n in notes) + '</ul>'
(OUT / 'gradients.html').write_text(page)
print(json.dumps({'output': str(OUT), 'verified_cells': len(state['cells']), 'answer_rows': len(records), 'failures': report['generation_errors']}))
for model in MODELS:
    print(model, {form: {s: round(lookup[s, rate, model, form]['score_percent'], 2) for s, rate in [('clean',0),('omission',30),('mistranslation',30),('wbw',None)]} for form in ['mcq','open']})
