"""Evaluate the seven established local reader settings on one reviewed window-dose bank."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import time

from dotenv import load_dotenv
import requests

from evaluation.scripts.campaigns.current import run_sol_slide_experiment as old
from evaluation.scripts.pipeline import build_passage_omission_preview as omission
from evaluation.scripts.pipeline import build_passage_mistranslation_preview as mistranslation

ROOT=old.REPO
DOSES=(5,10,15,20,25,30,40,50,60)
FAMILIES=('omission','mistranslation')
LOW=ROOT/'evaluation/runs/sol_low_dose_all66_2026-11-19/all_windows.json'
HIGH=ROOT/'evaluation/runs/sol_nested_defects_all66_2026-11-19/all_windows.json'
QA=ROOT/'evaluation/datasets/qa/reviewed122_sol/zh.json'
LABELS=['Llama 3.2 1B','Qwen 2.5 1.5B','Qwen 3 1.7B · thinking','Qwen 3 1.7B · no thinking',
        'Gemma 3 4B','Phi-4-mini 3.8B','Qwen 2.5 3B']


def passage_label(rows):
    matches=[re.match(r'^(.*?) (\d+):',r['reference']) for r in rows if r['family']=='clean']
    if not matches or any(m is None for m in matches):raise ValueError('Unrecognized passage references')
    books={m.group(1) for m in matches};chapters=sorted({int(m.group(2)) for m in matches})
    if len(books)!=1:raise ValueError('A passage run must use one book')
    suffix=str(chapters[0]) if len(chapters)==1 else '–'.join(map(str,(chapters[0],chapters[-1])))
    return next(iter(books))+' '+suffix


def inputs(passage_id,skip_held=False,excluded=None):
    low,high,qas=old.read(LOW),old.read(HIGH),{q['id']:q for q in old.read(QA)}
    roster=[w for w in low['families']['omission']['windows'] if w['qa']['passage_id']==passage_id]
    if not roster:raise ValueError('No active from-scratch windows for this passage')
    stimuli=[]
    for w in roster:
        q=qas[w['id']]
        if w['qa']!=q or q['source']!='Hard77' or q['verses']!=w['clean']:
            raise ValueError('QA or clean window changed')
        stimuli.append(dict(item=q['id'],reference=w['reference'],qa=q,family='clean',dose=0,
            actual_percent=0,review_status='clean',passage=' '.join(w['clean'].values()),verses=w['clean']))
    for family,driver in [('omission',omission),('mistranslation',mistranslation)]:
        lows={w['id']:w for w in low['families'][family]['windows']}
        highs=high['families'][family]['windows']
        for dose in DOSES:
            for w in roster:
                state=lows[w['id']] if dose<30 else highs[w['id']]
                if state['clean']!=w['clean']:raise ValueError('Mismatched source window')
                if lows[w['id']]['cells']['30']!=highs[w['id']]['cells']['30']:
                    raise ValueError('Different 30% anchor versions')
                cell=state['cells'][str(dose)]
                if skip_held and cell['status'] not in ('pass','pass_with_flags'):
                    if excluded is not None:
                        excluded.append(dict(item=w['id'],reference=w['reference'],family=family,dose=dose,
                            status=cell['status'],actual_percent=cell.get('actual_percent'),
                            reason=cell.get('reason','Not approved for reader evaluation')))
                    continue
                driver.check_cell(w,state['pool'],dose,cell)
                stimuli.append(dict(item=w['id'],reference=w['reference'],qa=qas[w['id']],family=family,dose=dose,
                    actual_percent=cell['actual_percent'],review_status=cell['status'],
                    passage=' '.join(cell['verses'].values()),verses=cell['verses'],edits=cell['edits']))
    if not skip_held and len(stimuli)!=len(roster)*(1+2*len(DOSES)):raise ValueError('Incomplete condition grid')
    return stimuli


def request_jobs(stimuli,weights):
    jobs=[]
    for i,(model,thinking) in enumerate(old.MODELS):
        for s in stimuli:
            body,public=old.request_for(s['qa'],s['passage'],model,thinking,'mcq',i>=4)
            signature=old.digest([weights[model],body])
            jobs.append(dict(signature=signature,reader_index=i,model=model,thinking=thinking,
                reader=old.model_name(model,thinking),label=LABELS[i],item=s['item'],family=s['family'],dose=s['dose'],
                body=body,public=public,model_digest=weights[model]))
    if len({j['signature'] for j in jobs})!=len(jobs):
        raise ValueError('Duplicate complete requests in this experiment')
    return jobs


def initialize(folder,passage_id,skip_held=False):
    excluded=[]
    stimuli=inputs(passage_id,skip_held,excluded)
    with requests.Session() as session:
        r=session.get(old.LOCAL+'/api/tags',timeout=20);r.raise_for_status();inventory=r.json()['models']
        v=session.get(old.LOCAL+'/api/version',timeout=20);v.raise_for_status();server_version=v.json()
    names={model for model,_ in old.MODELS}
    selected=[r for r in inventory if r['name'] in names]
    weights={r['name']:r['digest'] for r in selected}
    if set(weights)!=names:raise ValueError('A requested local model is missing')
    historical=old.read(old.RUN/'design.json')['models']
    if any(weights[k]!=historical[k] for k in weights):raise ValueError('Model weights differ from original experiment')
    jobs=request_jobs(stimuli,weights)
    files=[LOW,HIGH,QA,Path(old.__file__),Path(old.gen.__file__),Path(old.small.__file__)]
    design=dict(version='reviewed_window_dose_readers_v1',passage_id=passage_id,
        question_ids=[s['item'] for s in stimuli if s['family']=='clean'],doses=list(DOSES),families=list(FAMILIES),
        models=[dict(model=k,thinking=t,label=LABELS[i]) for i,(k,t) in enumerate(old.MODELS)],
        weights=weights,inference=old.CONFIG,ollama_version=server_version,
        input_sha256={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files},
        stimuli_sha256=old.digest(stimuli),requests_sha256=old.digest(jobs),expected=len(jobs),
        scoring=dict(key='clean-source reference answer',abstention='E',mapper=old.JUDGE,
            mapper_scope='Unmatched nonempty answers from the four primary reader settings only; original prompt and parsers.',
            mapper_input='Reader answer and options only; no passage, question or key.',random_fallback=False),
        protocol='Fresh conversation per item; same original reader-specific prompt families, 2500 generated-token cap, '
                 'temperature zero, unchanged choice order. One answer per model/question/condition. '
                 'Raw responses and available thinking text retained. Nine existing doses; no 35/45/55% versions. '
                 'Clean baseline run once per reader. Low-dose selections need not be nested; 30–60% are nested.',
        published=False)
    if skip_held:
        design.update(excluded_stimuli=excluded,exclusion_policy='Skip only held question/condition/dose cells; preserve all approved cells and show their denominators.')
    path=folder/'design.json'
    if path.exists() and old.read(path)!=design:raise ValueError('Frozen experiment inputs changed')
    old.save(path,design);old.save(folder/'stimuli.json',stimuli);old.save(folder/'requests.json',jobs)
    old.save(folder/'model_inventory.json',selected)
    print('PREPARED',len(design['question_ids']),'questions',len(jobs),'responses',flush=True)
    return design,jobs


def verify_inputs(design):
    for relative,digest in design['input_sha256'].items():
        if sha256((ROOT/relative).read_bytes()).hexdigest()!=digest:raise ValueError('Changed experiment input: '+relative)


def parse_answer(job,answer):
    if not answer:return None
    if job['reader_index']>=4:return old.small.parse_choice(answer,job['public']['choices'])[0]
    return old.gen.selected_choice_from_raw_answer(job['public'],answer)


def read_all(folder,design,jobs,limit=None):
    verify_inputs(design)
    if old.digest(old.read(folder/'requests.json'))!=design['requests_sha256']:raise ValueError('Changed requests')
    state=dict(status='running',expected=len(jobs),completed=0,new_requests=0)
    old.save(folder/'state.json',state)
    with requests.Session() as session:
        tags=session.get(old.LOCAL+'/api/tags',timeout=20);tags.raise_for_status()
        current={x['name']:x['digest'] for x in tags.json()['models']}
        if any(current.get(k)!=v for k,v in design['weights'].items()):raise ValueError('Reader weights changed')
        for job in jobs:
            path=folder/'answers'/(job['signature']+'.json')
            if path.exists():
                record=old.read(path)
                if record['request']!=job['body'] or record['model_digest']!=job['model_digest']:
                    raise ValueError('Answer checkpoint differs from frozen request')
            else:
                if limit is not None and state['new_requests']>=limit:break
                state.update(current_reader=job['reader'],current_family=job['family'],current_dose=job['dose'],current_item=job['item'])
                old.save(folder/'state.json',state)
                started=time.time()
                raw=old.infer_response(session,job['body'])
                content=str(raw['message'].get('content') or '')
                answer=old.gen.clean_raw_answer(content)
                effort=old.gen.ollama_effort(raw,content)
                if job['thinking'] is False and effort['thinking_chars']:
                    raise ValueError('No-thinking model emitted a thinking trace')
                trace=raw['message'].get('thinking') or ''.join(old.gen.INLINE_THINK_RE.findall(content))
                record=dict(signature=job['signature'],request=job['body'],model_digest=job['model_digest'],
                    item=job['item'],reader=job['reader'],family=job['family'],dose=job['dose'],
                    answer=answer,direct_choice=parse_answer(job,answer),thinking_text=trace,
                    raw_response=raw,effort=effort,started_at=started,completed_at=time.time())
                old.save(path,record);state['new_requests']+=1
            state['completed']+=1
            old.save(folder/'state.json',state)
            if state['completed']%8==0:
                print('READ',state['completed'],'/',len(jobs),job['reader'],job['family'],job['dose'],flush=True)
    state['status']='read_complete' if state['completed']==len(jobs) else 'checkpointed'
    old.save(folder/'state.json',state)


def map_unmatched(folder,jobs):
    pending={}
    for job in jobs:
        record=old.read(folder/'answers'/(job['signature']+'.json'))
        if job['reader_index']>=4 or record['direct_choice'] or not record['answer'].strip():continue
        key=old.digest([old.JUDGE,job['public']['choices'],record['answer']])
        pending[key]=(job['public']['choices'],record['answer'])
    if not pending:return
    client=old.scoring.get_openai_client()
    def map_one(pair):
        key,(choices,answer)=pair;path=folder/'mappings'/(key+'.json')
        if path.exists():
            saved=old.read(path)
            if saved['answer']!=answer or saved['choices']!=choices or saved['model']!=old.JUDGE:
                raise ValueError('Mapping checkpoint mismatch')
            return
        choice=old.gen.openai_closest_mcq_choice(client,old.JUDGE,raw_answer=answer,choices=choices,retries=2)
        if choice not in 'ABCDE':raise ValueError('Invalid mapper result')
        old.save(path,dict(signature=key,model=old.JUDGE,answer=answer,choices=choices,choice=choice))
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(map_one,pending.items()))
    print('MAPPED',len(pending),'distinct unmatched responses',flush=True)


def results(folder,design,jobs):
    verify_inputs(design)
    stimuli=old.read(folder/'stimuli.json')
    if old.digest(stimuli)!=design['stimuli_sha256']:raise ValueError('Stimulus snapshot changed')
    lookup={(s['family'],s['dose'],s['item']):s for s in stimuli}
    records=[]
    for job in jobs:
        record=old.read(folder/'answers'/(job['signature']+'.json'));s=lookup[job['family'],job['dose'],job['item']]
        if record['request']!=job['body'] or record['model_digest']!=job['model_digest']:raise ValueError('Response provenance mismatch')
        direct=parse_answer(job,record['answer'])
        if direct!=record['direct_choice']:raise ValueError('Parser result changed')
        choice=direct;method='rules' if choice else 'invalid'
        if not choice and record['answer'].strip() and job['reader_index']<4:
            key=old.digest([old.JUDGE,job['public']['choices'],record['answer']]);mapped=old.read(folder/'mappings'/(key+'.json'))
            choice=mapped['choice'];method='gpt-4.1-mini mapping'
        outcome='correct' if choice==s['qa']['correct'] else 'abstain' if choice=='E' else 'incorrect' if choice in ('A','B','C','D') else 'invalid'
        if job['thinking'] is False and record['effort']['thinking_chars']:raise ValueError('Unexpected reasoning')
        records.append(dict(reader=job['reader'],reader_index=job['reader_index'],label=job['label'],
            family=job['family'],dose=job['dose'],actual_percent=s['actual_percent'],item=job['item'],
            reference=s['reference'],question=s['qa']['question'],choices=s['qa']['choices'],key=s['qa']['correct'],
            passage=s['passage'],choice=choice,direct_choice=direct,outcome=outcome,scoring_method=method,
            answer=record['answer'],thinking_text=record['thinking_text'],effort=record['effort'],
            request_hash=job['signature'],response_seconds=record['completed_at']-record['started_at']))
    summaries=[]
    for i,(model,thinking) in enumerate(old.MODELS):
        for family,dose in [('clean',0)]+[(f,d) for f in FAMILIES for d in DOSES]:
            rows=[r for r in records if r['reader_index']==i and r['family']==family and r['dose']==dose]
            expected_items={s['item'] for s in stimuli if s['family']==family and s['dose']==dose}
            if len(rows)!=len(expected_items) or {r['item'] for r in rows}!=expected_items:
                raise ValueError('Missing or extra observations')
            counts=Counter(r['outcome'] for r in rows)
            summaries.append(dict(reader_index=i,label=LABELS[i],model=model,thinking=thinking,family=family,dose=dose,
                n=len(rows),**{k:counts[k] for k in ('correct','incorrect','abstain','invalid')},
                accuracy=counts['correct']/len(rows) if rows else None,
                abstention_rate=counts['abstain']/len(rows) if rows else None,
                mapped=sum(r['scoring_method']!='rules' and r['scoring_method']!='invalid' for r in rows),
                length_limited=sum(r['effort']['done_reason']=='length' for r in rows),
                generated_tokens=sum(r['effort']['output_tokens'] or 0 for r in rows),
                mean_actual_percent=sum(r['actual_percent'] for r in rows)/len(rows) if rows else None))
    if len(records)!=design['expected']:raise ValueError('Incomplete reader campaign')
    return records,summaries


def render_report(folder,report_dir,design,jobs):
    records,summaries=results(folder,design,jobs)
    title_text=passage_label(records);question_count=len(design['question_ids'])
    cell_ns=sorted({s['n'] for s in summaries});varying_n=len(cell_ns)>1
    cell_label=f'{min(cell_ns)}–{max(cell_ns)} questions per cell' if varying_n else f'{question_count} questions per cell'
    report_dir.mkdir(parents=True,exist_ok=True)
    old.save(report_dir/'results.json',records);old.save(report_dir/'summary.json',summaries)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    for metric,title in [('accuracy','Accuracy against clean-source key'),('abstention_rate','Cannot-determine responses (E)')]:
        fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
        for ax,family in zip(axes,FAMILIES):
            for i,label in enumerate(LABELS):
                series=[s for s in summaries if s['reader_index']==i and s['family'] in ('clean',family)]
                series.sort(key=lambda s:s['dose'])
                ax.plot([s['dose'] for s in series],[s[metric] for s in series],marker=['o','s','^','v','D','P','X'][i],ms=4,lw=1.5,label=label)
            ax.set_title(family.title());ax.set_xlabel('Target affected source characters (%)')
            ax.set_xticks([0,*DOSES]);ax.set_ylim(-.03,1.03);ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.grid(alpha=.2)
        axes[0].set_ylabel(title);fig.suptitle(f'{title_text} · {cell_label}')
        fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=3,frameon=False,fontsize=9)
        fig.tight_layout(rect=(0,.16,1,.95))
        for ext in ('png','svg'):fig.savefig(report_dir/f'{metric}.{ext}',dpi=180)
        plt.close(fig)
    p=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title_text)+' · reader dose experiment</title>',
       '<style>body{max-width:1250px;margin:32px auto;padding:0 20px;font:16px/1.6 system-ui;color:#20343b}img{max-width:100%}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ccd9d8;text-align:left}.scroll{overflow:auto}.note{padding:18px;background:#edf4f2}details{border:1px solid #d5dfdd;padding:12px;margin:10px 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:#f3f6f5;padding:15px}.correct{color:#176b49}.incorrect{color:#a13930}.abstain{color:#966000}.hidden{display:none}select{padding:8px;font:inherit}a{color:#126378}</style></head><body>',
       '<h1>'+escape(title_text)+' · omission and mistranslation</h1>',
       f'<p>{len(design["question_ids"])} from-scratch questions · 7 reader settings · 9 defect doses · {len(records)} responses including clean baselines.</p>',
       '<div class="note">Accuracy uses the clean-source key. E means “无法判断” and is reported separately from wrong A–D answers. '
       'Defective passages can remove or contradict the key’s evidence. These scores do not separately judge whether each response is reasonable for the defective passage. '+
       (f'{cell_label}. Denominators vary because held versions are excluded; see the exclusions and per-cell counts below. ' if varying_n else
        f'{question_count} questions per cell: one answer changes accuracy by {100/question_count:.1f} percentage points. ')+
       'This is exploratory, with one generation per item and setting.</div>',
       '<p>Rates count affected clean Chinese source characters, with ±2 percentage-point tolerance. Low-dose versions need not be nested; the 30–60% versions are nested. '
       'The original reader-specific prompts and parsers are retained: the first four settings use the primary prompt; Gemma, Phi and Qwen 3B use the additional-reader prompt. '
       'Unmatched nonempty primary-reader answers use the original GPT-4.1-mini mapper with only the answer and choices. '
       'All models use temperature 0, an 8,192-token context and a 2,500-token generation cap. Thinking counts against that cap. '
       'Raw outputs, available thinking traces and length-limit events are retained. Questions and passages were not changed or published.</p>',
       '<img src="accuracy.png" alt="Accuracy by target defect dose"><img src="abstention_rate.png" alt="Cannot-determine responses by target defect dose">']
    if design.get('excluded_stimuli'):
        p.append('<h2>Held versions excluded</h2><p>These missing cells are neither incorrect answers nor abstentions. All other approved versions of the same question remain included.</p><ul>')
        for e in design['excluded_stimuli']:
            p.append('<li>'+escape(f'{e["reference"]} · {e["family"]} {e["dose"]}% · {e["status"]}: {e["reason"]}')+'</li>')
        p.append('</ul>')
        old.save(report_dir/'excluded_stimuli.json',design['excluded_stimuli'])
    p.append('<h2>Response checks</h2><p>Mapped choices are included in the outcome tables. An E assigned by the mapper is distinguished here from a direct E selection. A length limit is a generation event, not automatically an abstention.</p><table><tr><th>Reader</th><th>Mapped choices</th><th>E from mapping</th><th>Invalid</th><th>Hit token limit</th></tr>')
    for i,label in enumerate(LABELS):
        rows=[r for r in records if r['reader_index']==i]
        counts=[sum(r['scoring_method']=='gpt-4.1-mini mapping' for r in rows),
                sum(r['scoring_method']=='gpt-4.1-mini mapping' and r['choice']=='E' for r in rows),
                sum(r['outcome']=='invalid' for r in rows),
                sum(r['effort']['done_reason']=='length' for r in rows)]
        p.append('<tr><th>'+escape(label)+'</th>'+''.join(f'<td>{c}</td>' for c in counts)+'</tr>')
    p.append('</table>')
    for family in FAMILIES:
        denominator_note='The denominator is shown in each cell.' if varying_n else f'Each cell is out of {question_count}.'
        p.append('<h2>'+family.title()+f'</h2><p>Each entry is <b>correct / wrong / E / invalid</b>. {denominator_note}</p><div class="scroll"><table><tr><th>Reader</th>'+''.join(f'<th>{d}%</th>' for d in (0,*DOSES))+'</tr>')
        for i,label in enumerate(LABELS):
            p.append('<tr><th>'+escape(label)+'</th>')
            for dose in (0,*DOSES):
                s=next(s for s in summaries if s['reader_index']==i and s['dose']==dose and s['family']==('clean' if dose==0 else family))
                p.append('<td>'+' / '.join(str(s[k]) for k in ('correct','incorrect','abstain','invalid'))+(f'<br>n={s["n"]}' if varying_n else '')+'</td>')
            p.append('</tr>')
        p.append('</table></div>')
    p.append('<h2>Response review</h2><p>Filter by reader, condition and dose. Expand an item for its passage, options, response and recorded thinking.</p>')
    for key,values in [('reader',[(str(i),v) for i,v in enumerate(LABELS)]),('family',[(f,f) for f in ('clean',*FAMILIES)]),('dose',[(str(d),str(d)+'%') for d in (0,*DOSES)])]:
        p.append(f'<select id="{key}"><option value="all">All {key}s</option>'+''.join(f'<option value="{v}">{escape(label)}</option>' for v,label in values)+'</select> ')
    for r in records:
        p.append(f'<details class="item" data-reader="{r["reader_index"]}" data-family="{r["family"]}" data-dose="{r["dose"]}"><summary>'+escape(f'{r["label"]} · {r["family"]} {r["dose"]}% · {r["reference"]}')+f' · <b class="{r["outcome"]}">{r["choice"] or "—"} · {r["outcome"]}</b></summary>')
        p.append(f'<p>Actual dose: {r["actual_percent"]:.1f}% · Key: {r["key"]} · Scoring: {escape(r["scoring_method"])}</p><p lang="zh">'+escape(r['passage'])+'</p><h3>'+escape(r['question'])+'</h3><ol type="A">')
        p.extend('<li>'+escape(c)+'</li>' for c in r['choices']);p.append('</ol><h4>Final response</h4><pre>'+escape(r['answer'] or '(empty)')+'</pre>')
        p.append(f'<p>Generated tokens: {r["effort"]["output_tokens"]} · Stop reason: {escape(str(r["effort"]["done_reason"]))}</p>')
        if r['thinking_text']:p.append('<details><summary>Recorded thinking</summary><pre>'+escape(r['thinking_text'])+'</pre></details>')
        p.append('</details>')
    p.append('<script>for(const key of ["reader","family","dose"])document.getElementById(key).addEventListener("change",()=>{for(const item of document.querySelectorAll(".item")){item.classList.toggle("hidden",["reader","family","dose"].some(k=>document.getElementById(k).value!=="all"&&document.getElementById(k).value!==item.dataset[k]));}});</script></body></html>')
    (report_dir/'index.html').write_text(''.join(p),encoding='utf-8')
    verify_inputs(design)
    verification=dict(observations=len(records),summary_cells=len(summaries),unique_observations=len({(r['reader_index'],r['family'],r['dose'],r['item']) for r in records}),
        per_cell_n=cell_ns if varying_n else question_count,
        excluded_stimuli=design.get('excluded_stimuli',[]),source_hashes_unchanged=True,model_weights_pinned=True,
        no_thinking_violations=0,mapped_responses=sum(r['scoring_method']=='gpt-4.1-mini mapping' for r in records),
        thinking_responses_with_trace=sum(bool(r['thinking_text']) for r in records if r['reader_index']==2),
        length_limited=sum(r['effort']['done_reason']=='length' for r in records),
        outcomes=dict(Counter(r['outcome'] for r in records)),published=False)
    old.save(folder/'verification.json',verification);old.save(folder/'state.json',dict(status='complete',completed=len(records),expected=len(jobs)))
    print('VERIFIED',verification,flush=True);print('REPORT',report_dir/'index.html',flush=True)
    return records,summaries


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('prepare','read','map','report','all'))
    p.add_argument('--passage-id',default='t1_1kgs13');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report-dir',type=Path,required=True);p.add_argument('--limit',type=int)
    p.add_argument('--skip-held',action='store_true',help='Explicitly exclude held stimulus cells and retain their reasons in the frozen design and report.')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);load_dotenv(ROOT/'.env')
    with (a.output/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.stage in ('prepare','all'):design,jobs=initialize(a.output,a.passage_id,a.skip_held)
        else:design,jobs=old.read(a.output/'design.json'),old.read(a.output/'requests.json')
        if a.stage in ('read','all'):read_all(a.output,design,jobs,a.limit)
        if a.stage in ('map','all'):map_unmatched(a.output,jobs)
        if a.stage in ('report','all'):render_report(a.output,a.report_dir,design,jobs)


if __name__=='__main__':main()
