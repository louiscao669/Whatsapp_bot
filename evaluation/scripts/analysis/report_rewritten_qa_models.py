#!/usr/bin/env python3
"""Build before/after results from the verified changed-question replay."""
from __future__ import annotations

from collections import Counter
import html
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO))
from evaluation.scripts.campaigns.current import rerun_rewritten_qa as replay

ROOT = replay.DEFAULT_OUTPUT
OUT = REPO / 'evaluation/reports/qa_rewrite_model_results_2026-10-27'
LABELS = {'llama321b':'Llama 3.2 1B', 'qwen2515b':'Qwen 2.5 1.5B',
          'qwen317b_think':'Qwen3 1.7B · thinking', 'qwen317b_nothink':'Qwen3 1.7B · no thinking'}
COLORS = ['#A86116','#087EA4','#8C4AA5','#2E7D32']


def recover_selected_choice(score, answer):
    """Use the original answer label: historical score parsing omitted E."""
    result=dict(score)
    if score['q_type']!='mcq':return result
    assert replay.form_key(score)==replay.form_key(answer)
    choice=answer.get('selected_choice')
    if choice not in ('A','B','C','D','E'):
        choice=score.get('selected_choice')
    if choice not in ('A','B','C','D','E'):choice=None
    if choice!=score.get('selected_choice'):
        assert score.get('selected_choice') is None and choice=='E'
        assert not score['direct_correct']
        result['scorer_selected_choice']=score.get('selected_choice')
        result['selected_choice_source']='original_answer_log'
    result['selected_choice']=choice
    return result


def load_score_rows(directory):
    directory=Path(directory)
    scores=replay.read(directory/'scores_target_llama.json')['items']
    answers=replay.read(directory/'generated_answers_target_llama.json')
    index={replay.form_key(a):a for a in answers}
    assert len(index)==len(answers) and set(index)=={replay.form_key(s) for s in scores}
    return [recover_selected_choice(s,index[replay.form_key(s)]) for s in scores]


def metrics(rows):
    mcq=[r for r in rows if r['q_type']=='mcq']
    op=[r for r in rows if r['q_type']=='open']
    answered=[r for r in mcq if r.get('selected_choice')!='E']
    substantive=[r for r in mcq if r.get('selected_choice') in ('A','B','C','D')]
    correct=sum(bool(r['direct_correct']) for r in mcq)
    wrong=sum(not r['direct_correct'] for r in substantive)
    abstained=sum(r.get('selected_choice')=='E' for r in mcq)
    unresolved=sum(r.get('selected_choice') not in ('A','B','C','D','E') for r in mcq)
    assert correct+wrong+abstained+unresolved==len(mcq)
    return dict(total=len(rows), mcq_n=len(mcq), mcq_correct=sum(bool(r['direct_correct']) for r in mcq),
                mcq_accuracy=sum(bool(r['direct_correct']) for r in mcq)/len(mcq) if mcq else None,
                mcq_e_count=abstained, mcq_e_rate=abstained/len(mcq) if mcq else None,
                mcq_incorrect_ad_count=wrong, mcq_unresolved_count=unresolved,
                mcq_accuracy_excluding_e=sum(bool(r['direct_correct']) for r in answered)/len(answered) if answered else None,
                mcq_accuracy_among_ad=sum(bool(r['direct_correct']) for r in substantive)/len(substantive) if substantive else None,
                open_n=len(op), open_score_mean=sum(r['llm_score'] for r in op)/len(op) if op else None,
                generation_errors=sum(bool(r.get('generation_error')) for r in rows))


def score_value(row):
    if row is None:return None
    return float(bool(row['direct_correct'])) if row['q_type']=='mcq' else row['llm_score']


def build():
    verification=replay.read(ROOT/'verification.json')
    assert verification['status']=='complete'
    assert replay.read(ROOT/'input_binding_verification.json')['affected_saved_rows']==verification['updated_baseline_rows']
    manifest=replay.read(ROOT/'manifest.json')
    changed=replay.read(ROOT/'changed_results.json')
    jobs={j['id']:j for j in manifest['jobs']}
    OUT.mkdir(parents=True,exist_ok=True)
    conditions=[]
    canonical_cells=set()
    for dataset in ('gold','hard'):
        for config in replay.CONFIGS:
            for method in replay.METHODS:
                root,slug,_=replay.source_for(dataset,config,method)
                cells=[(key,cell) for key,cell in manifest['cells'].items() if cell['source_root']==str(root) and cell['config']==config[0] and cell['method']==method]
                max_hard=dataset=='hard' and method=='grammar/max_approved'
                assert len(cells)==(8 if max_hard else 10),(dataset,config,method,len(cells))
                old,new=[],[]
                for key,cell in cells:
                    canonical_cells.add(key)
                    old.extend(load_score_rows(cell['source_directory']))
                    new.extend(load_score_rows(ROOT/'updated_runs'/key))
                before,after=metrics(old),metrics(new)
                assert before['mcq_n']==after['mcq_n']==(71 if dataset=='gold' else 57 if max_hard else 65)
                conditions.append(dict(dataset=dataset,config=config[0],model=config[1],condition=method,passage_count=len(cells),before=before,after=after,
                    delta_mcq_correct=after['mcq_correct']-before['mcq_correct'],
                    delta_mcq_percentage_points=100*(after['mcq_accuracy']-before['mcq_accuracy']),
                    delta_open_score_mean=(after['open_score_mean']-before['open_score_mean']) if before['open_n'] else None))
    pairs=[]
    baseline_cache={}
    for r in changed:
        job=jobs[r['id']]
        directory=job['baseline_directory']
        if directory not in baseline_cache:
            baseline_cache[directory]={replay.form_key(s):s for s in load_score_rows(directory)}
        before=baseline_cache[directory].get(replay.form_key(r['score']))
        after=recover_selected_choice(r['score'],r['answer'])
        assert bool(before)==r['has_baseline']
        pairs.append(dict(id=r['id'],case_id=r['case_id'],dataset=r['dataset'],config=r['config'],condition=r['method'],form=r['score']['q_type'],
                          question=r['score']['question'],before=before,after=after,
                          difference=score_value(r['score'])-score_value(before) if before else None))
        pair=pairs[-1]
        pair['answer_text_unchanged']=bool(before) and before['generated_answer'].strip()==r['score']['generated_answer'].strip()
        pair['open_score_changed_with_same_answer']=pair['form']=='open' and pair['answer_text_unchanged'] and pair['difference']!=0
    assert len(pairs)==1344 and sum(p['before'] is not None for p in pairs)==972
    tally=Counter('new_coverage' if p['before'] is None else 'higher' if p['difference']>0 else 'lower' if p['difference']<0 else 'same' for p in pairs)
    score_flags=[p for p in pairs if p['open_score_changed_with_same_answer']]
    unique_answers={k:replay.read(ROOT/'answer_cache'/(k+'.json')) for k in {j['generation_key'] for j in manifest['jobs']}}
    failed_records=[r for r in changed if r['answer'].get('generation_error')]
    generation_quality=dict(distinct_inputs=len(unique_answers),failed_inputs=sum(bool(a.get('generation_error')) for a in unique_answers.values()),
        affected_evaluations=len(failed_records),retained_length_limited_outputs=sum(a.get('answer_effort',{}).get('done_reason')=='length' for a in unique_answers.values()))
    data=dict(verification=verification,counts=manifest['counts'],paired_outcomes=dict(tally),conditions=conditions,
              generation_quality=generation_quality,
              same_answer_score_changes=dict(evaluations=len(score_flags),distinct_question_ids=len({p['case_id'] for p in score_flags}),clean_evaluations=sum(p['condition']=='omission/0%' for p in score_flags)),
              notes=['Only accepted changed forms were rerun; unchanged response and score rows were reused verbatim.',
                     'Exact repeated model inputs share one newly generated response and are not independent repeats.',
                     'Gold open-question and other new coverage is separate from existing full-set totals.',
                     'Gold accepted English rewrites were translated into Chinese; options, keys, passages, and windows are preserved.',
                     'E response labels are recovered from original answer logs because historical score files recorded these labels as null. Correctness scores are unchanged. Unresolved or failed responses are counted separately from E and incorrect A–D answers.',
                     'Max grammar uses approved sentence defects; its coverage measure differs from 5–30% clause-content coverage.',
                     'The existing Hard66 maximum-grammar runs cover 57 MCQs across 8 passages; other Hard66 conditions cover 65 MCQs across 10 passages. Their original denominators are retained.'])
    replay.write(OUT/'results_data.json',data)
    replay.write(OUT/'question_comparisons.json',pairs)
    replay.write(OUT/'same_answer_score_changes.json',score_flags)
    replay.write(OUT/'generation_failures.json',failed_records)
    # Updated summary beside every revised campaign copy, including duplicate
    # clean baseline copies retained in the source campaigns.
    for source_root in sorted({c['source_root'] for c in manifest['cells'].values()}):
        items=[c for c in replay.read(ROOT/'cell_summaries.json') if manifest['cells'][c['source_cell']]['source_root']==source_root]
        grouped={}
        for c in items:
            key=(c['config'],c['method'])
            grouped.setdefault(key,[]).append(c)
        summaries=[]
        for (config,method),cells in grouped.items():
            old,new=[],[]
            for cell in cells:
                key=cell['source_cell'];meta=manifest['cells'][key]
                old.extend(load_score_rows(meta['source_directory']))
                new.extend(load_score_rows(ROOT/'updated_runs'/key))
            summaries.append(dict(config=config,condition=method,before=metrics(old),after=metrics(new),changed_rows=sum(c['changed_rows'] for c in cells)))
        destination=ROOT/'updated_runs'/Path(source_root).relative_to(replay.RUNS)
        replay.write(destination/'results_summary.json',dict(original_run=source_root,revision=str(ROOT),conditions=summaries))
    figures(conditions)
    report(data,pairs,manifest)
    print(json.dumps({'counts':manifest['counts'],'paired_outcomes':dict(tally),'clean':[r for r in conditions if r['condition']=='omission/0%'],'report':str(OUT/'index.html')},ensure_ascii=False,indent=2))


def figures(rows):
    os.environ['MPLCONFIGDIR']=str(OUT/'.matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    for dataset in ('gold','hard'):
        fig,axes=plt.subplots(1,4,figsize=(17,4.8),sharey=True)
        for ax,family in zip(axes,['omission','mistranslation','grammar','wbw']):
            methods=['omission/0%']+[f'{family}/{r}%' for r in [5,10,15,20,25,30]] if family!='wbw' else ['omission/0%','google_word_by_word']
            xs=[0,5,10,15,20,25,30] if family!='wbw' else [0,1]
            for (name,_,_),color in zip(replay.CONFIGS,COLORS):
                series=[next(r for r in rows if r['dataset']==dataset and r['config']==name and r['condition']==m) for m in methods]
                before=[r['before']['mcq_accuracy'] for r in series];after=[r['after']['mcq_accuracy'] for r in series]
                ax.plot(xs,before,color=color,alpha=.45,ls='--',lw=1.4)
                ax.plot(xs,after,color=color,marker='o',markersize=3.8,lw=1.8,label=LABELS[name])
                if family=='grammar':
                    end=next(r for r in rows if r['dataset']==dataset and r['config']==name and r['condition']=='grammar/max_approved')
                    ax.scatter([40],[end['before']['mcq_accuracy']],facecolors='none',edgecolors=color,alpha=.5,s=36)
                    ax.scatter([40],[end['after']['mcq_accuracy']],color=color,s=22)
            ax.set_title({'omission':'Omission','mistranslation':'Mistranslation','grammar':'Grammar','wbw':'Word-by-word'}[family])
            ax.set_ylim(0,1.02);ax.grid(axis='y',color='#e2e8f0');ax.yaxis.set_major_formatter(PercentFormatter(1))
            if family=='wbw':ax.set_xticks([0,1],['Clean','Word-by-word'])
            elif family=='grammar':ax.set_xticks(xs+[40],[str(x) for x in xs]+['Max*']);ax.set_xlabel('Defect level (%)')
            else:ax.set_xticks(xs);ax.set_xlabel('Defect level (%)')
        axes[0].set_ylabel('MCQ accuracy')
        fig.suptitle(('Gold72 · 71 active MCQs' if dataset=='gold' else 'Hard66 · 65 MCQs (Max: 57)')+' — revised-question results',fontsize=17,x=.06,ha='left')
        fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,.09),ncol=4,frameon=False)
        fig.text(.06,.055,'Solid = updated results. Dashed = original results. Only changed questions were rerun.',fontsize=10,color='#526171')
        footnote='*Max: approved sentence defects, a different coverage measure; shown separately from the 5–30% series.'
        if dataset=='hard':footnote+=' Max also uses the original 8-passage subset (57 MCQs).'
        fig.text(.06,.012,footnote,fontsize=9,color='#526171')
        fig.tight_layout(rect=[0,.18,1,.92])
        for ext in ('png','svg'):fig.savefig(OUT/f'{dataset}_updated_mcq.{ext}',dpi=180,facecolor='white')
        plt.close(fig)


def report(data,pairs,manifest):
    e=lambda s:html.escape(str(s))
    def response(row):
        if row is None:return 'No completed baseline'
        selected=row.get('selected_choice')
        prefix=f'Choice {selected}: ' if row['q_type']=='mcq' and selected else ''
        return prefix+str(row.get('generated_answer',''))
    def outcome(row):
        if row is None:return '—'
        if row['q_type']=='mcq':
            return ('Correct' if row['direct_correct'] else 'Incorrect')+' ('+str(row.get('selected_choice') or '?')+')'
        return str(score_value(row))
    parts=['<h1>Updated results for the rewritten questions</h1>',
           '<p class="subtitle">27 October 2026 · Gold72 and Hard66 · four model configurations · all 21 conditions</p>',
           '<div class="card"><p><b>16 question forms covering 9 question IDs.</b> 1,344 evaluations used 764 distinct model inputs. There are 972 matched earlier results and 372 new-coverage results.</p><p>Original runs are preserved. Revised run copies replace only the changed forms; all other responses and scores remain identical. Open and multiple-choice forms count separately.</p></div>',
           '<h2>Clean-passage MCQ results — full active sets</h2><table><tr><th>Dataset</th><th>Model</th><th>Before</th><th>Updated</th><th>Change</th></tr>']
    for row in data['conditions']:
        if row['condition']!='omission/0%':continue
        b,a=row['before'],row['after']
        parts.append(f'<tr><td>{e(row["dataset"].title())}</td><td>{e(LABELS[row["config"]])}</td><td>{b["mcq_correct"]}/{b["mcq_n"]} ({100*b["mcq_accuracy"]:.1f}%)</td><td>{a["mcq_correct"]}/{a["mcq_n"]} ({100*a["mcq_accuracy"]:.1f}%)</td><td>{row["delta_mcq_percentage_points"]:+.1f} pp</td></tr>')
    parts.append('</table>')
    if all(r['delta_mcq_correct']==0 for r in data['conditions'] if r['condition']=='omission/0%'):
        parts.append('<p><b>Clean-passage MCQ totals are unchanged for all four model configurations in both datasets.</b></p>')
    health=data['generation_quality']
    if health['failed_inputs'] or health['retained_length_limited_outputs']:
        parts.append('<div class="card"><p><b>Generation outcomes:</b> '+str(health['failed_inputs'])+' of '+str(health['distinct_inputs'])+' distinct model inputs failed to produce a usable answer after the existing retry rules, affecting '+str(health['affected_evaluations'])+' evaluation rows. These failures remain in the scores. '+str(health['retained_length_limited_outputs'])+' retained outputs reached the token limit.</p><p><a href="generation_failures.json">Inspect failed responses</a></p></div>')
    for dataset in ('gold','hard'):
        parts.append(f'<h2>{dataset.title()} — all conditions</h2><img alt="{dataset} before and after MCQ curves" src="{dataset}_updated_mcq.svg"><details><summary>Exact MCQ counts for every condition</summary><table><tr><th>Condition</th>'+''.join('<th>'+e(LABELS[c[0]])+'</th>' for c in replay.CONFIGS)+'</tr>')
        for method in replay.METHODS:
            parts.append('<tr><td>'+e(method)+'</td>')
            for c in replay.CONFIGS:
                row=next(r for r in data['conditions'] if r['dataset']==dataset and r['config']==c[0] and r['condition']==method)
                parts.append(f'<td>{row["before"]["mcq_correct"]} → {row["after"]["mcq_correct"]} / {row["after"]["mcq_n"]}</td>')
            parts.append('</tr>')
        parts.append('</table></details>')
    flags=data['same_answer_score_changes']
    if flags['evaluations']:
        parts.append('<div class="card"><h2>Open-answer scoring check</h2><p>'+str(flags['evaluations'])+' matched evaluations received a different open-answer score despite identical Chinese answer text ('+str(flags['clean_evaluations'])+' on clean passages). These are scoring changes, not changes in the answer given. Results retain the original scoring method; affected comparisons are marked below.</p><p>For example, the unchanged answer “从犹大来的神人” was previously scored 1.0 but now scored 0.5: the judge treated “God” and the expected placeholder “Most High A” differently.</p><p><a href="same_answer_score_changes.json">Inspect all flagged scoring comparisons</a></p></div>')
    parts.append('<h2>Clean-passage open answers — changed forms only</h2><p>Mean judge score on the 0–1 scale. These means include the scoring changes flagged above. A dash means no matching completed baseline exists.</p><table><tr><th>Dataset</th><th>Model</th><th>Forms</th><th>Before</th><th>Updated</th></tr>')
    for dataset in ('gold','hard'):
        for c in replay.CONFIGS:
            selected=[p for p in pairs if p['dataset']==dataset and p['config']==c[0] and p['condition']=='omission/0%' and p['form']=='open']
            before=[score_value(p['before']) for p in selected if p['before'] is not None]
            old=f'{sum(before)/len(before):.3f}' if before else '—'
            new=sum(score_value(p['after']) for p in selected)/len(selected)
            parts.append('<tr><td>'+e(dataset.title())+'</td><td>'+e(LABELS[c[0]])+'</td><td>'+str(len(selected))+'</td><td>'+old+'</td><td>'+f'{new:.3f}'+'</td></tr>')
    parts.append('</table>')
    parts.append('<h2>Each changed question — clean-passage responses</h2><p>Open answers use the existing 0 / 0.5 / 1 scoring rubric. A dash indicates that this form/configuration had no matching completed baseline. New open results are not added to the full-set MCQ totals.</p>')
    for cid,question in manifest['questions'].items():
        prompt=next(j for j in manifest['jobs'] if j['case_id']==cid and j['method']=='omission/0%')
        parts.append('<details class="card"><summary><b>'+e(question['displayed_question'])+'</b><br><small>'+e(cid)+'</small></summary>')
        parts.append('<p><b>Earlier displayed question:</b> '+e(question['earlier_displayed_question'])+'</p><p><b>Expected answer:</b> '+e(question['accepted_case']['expected_answer'])+'</p>')
        if cid.startswith('gold:'):parts.append('<p><b>Accepted English rewrite:</b> '+e(question['accepted_case']['question'])+'</p>')
        if prompt['public_question'].get('choices'):
            correct=question['accepted_case']['correct_option']
            parts.append('<ul>'+''.join('<li><b>'+e(label)+':</b> '+e(value)+(' <b>(correct)</b>' if label==correct else '')+'</li>' for label,value in prompt['public_question']['choices'].items())+'</ul>')
        parts.append('<details><summary>Exact clean passage supplied to the model · '+e(prompt['public_question']['passage_reference'])+'</summary><p style="white-space:pre-wrap">'+e(prompt['passage'])+'</p></details>')
        parts.append('<table><tr><th>Model</th><th>Before</th><th>Updated</th><th>New answer</th></tr>')
        for c in replay.CONFIGS:
            r=next(r for r in pairs if r['case_id']==cid and r['config']==c[0] and r['condition']=='omission/0%')
            flag='<br><small>Same answer; judge score changed.</small>' if r['open_score_changed_with_same_answer'] else ''
            parts.append('<tr><td>'+e(LABELS[c[0]])+'</td><td>'+e(outcome(r['before']))+'</td><td>'+e(outcome(r['after']))+flag+'</td><td>'+e(response(r['after']))+'</td></tr>')
        parts.append('</table><details><summary>All conditions and individual answers</summary><p>Each cell shows the earlier result → revised result. Expand a cell to compare the answers.</p><table><tr><th>Condition</th>'+''.join('<th>'+e(LABELS[c[0]])+'</th>' for c in replay.CONFIGS)+'</tr>')
        for method in replay.METHODS:
            parts.append('<tr><td>'+e('Clean' if method=='omission/0%' else method)+'</td>')
            for c in replay.CONFIGS:
                r=next(r for r in pairs if r['case_id']==cid and r['config']==c[0] and r['condition']==method)
                flag='<p><b>Same answer; judge score changed.</b></p>' if r['open_score_changed_with_same_answer'] else ''
                parts.append('<td><details><summary>'+e(outcome(r['before'])+' → '+outcome(r['after']))+'</summary>'+flag+'<p><b>Before:</b> '+e(response(r['before']))+'</p><p><b>Updated:</b> '+e(response(r['after']))+'</p></details></td>')
            parts.append('</tr>')
        parts.append('</table></details></details>')
    parts.append('<h2>Files and verification</h2><p><a href="results_data.json">Full condition totals, including open scores and E-response metrics</a> · <a href="question_comparisons.json">Every changed-question comparison</a></p><ul>'+''.join('<li>'+e(n)+'</li>' for n in data['notes'])+'</ul>')
    parts.append('<p>All affected stored rows were checked against their original passages, verse windows, options, and keys. The 990 updated stored rows include 18 repeated clean-baseline copies; the main comparison uses 972 unique matched evaluations.</p>')
    style='body{font:16px/1.6 system-ui,sans-serif;color:#172b3b;background:#f4f6f8;margin:0}main{max-width:1250px;margin:auto;padding:32px 24px}h1{font-size:32px;line-height:1.2}h2{margin-top:36px;font-size:23px}.subtitle,small{color:#596e7e}.card{padding:20px;background:white;border:1px solid #dce3e9;border-radius:10px;margin:16px 0}table{border-collapse:collapse;background:white;width:100%;margin:18px 0}th,td{border-bottom:1px solid #e0e6eb;text-align:left;padding:10px;vertical-align:top}th{background:#e9eff4}img{width:100%;background:white}summary{cursor:pointer;color:#1d527a}a{color:#145f9c}details{overflow-x:auto}p{max-width:1100px}'
    (OUT/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Updated QA model results</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')


if __name__=='__main__':
    build()
