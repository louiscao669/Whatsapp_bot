"""Run an explicitly authorized full-bank nested draft campaign, with resumable jobs."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path

from evaluation.scripts.pipeline import build_nested_window_defects as n
from evaluation.scripts.pipeline import repair_nested_agreement as agreement
from evaluation.scripts.pipeline.report_nested_window_defects import report

FAMILIES=('omission','mistranslation')


def verify(result, windows, families):
    lookup={w['id']:w for w in windows}
    for family in families:
        states=result['families'][family]['windows']
        if set(states)!=set(lookup):raise ValueError('Window coverage differs from manifest')
        for wid,s in states.items():
            w=lookup[wid]
            if s['clean']!=w['clean']:raise ValueError('Clean source changed')
            n.validate_chain(w,s['cells'],family)
            for dose,c in s['cells'].items():
                replay=n.materialize(w,s['pool'],c['selected_ids'],family,int(dose))
                if any(replay[k]!=c[k] for k in ('verses','edits','affected_chars','actual_percent')):
                    raise ValueError('Saved text or dose fails exact replay')
                if c['status'] in n.PASS:
                    fields=n.mr.Checks.model_fields if family=='mistranslation' else n.m.review.ClauseChecks.model_fields
                    if any(c.get('checks',{}).get(k)!='yes' for k in fields):
                        raise ValueError('Passing cell lacks required review checks')


def collect(folder,windows,sources,reused):
    result=dict(title='Sol · All 66 from-scratch windows',configuration=dict(writer=n.WRITER,reviewer=n.m.review.JUDGE,
        version=n.VERSION),published=False,families={f:dict(windows={},stop_reason='Full-bank draft campaign') for f in FAMILIES})
    per_passage={pid:n.m.review.read(path) for pid,path in reused.items()}
    completed=[];pending=[];held=[]
    for family in FAMILIES:
        for pid,ws in windows.items():
            path=folder/pid/family/'nested.json'
            part=per_passage.get(pid) or (n.m.review.read(path) if path.exists() else None)
            states=part.get('families',{}).get(family,{}).get('windows',{}) if part else {}
            for w in ws:
                s=deepcopy(states.get(w['id']) or dict(reference=w['reference'],clean=w['clean'],
                    english={v:sources[pid].english[v] for v in w['clean']},cells={},proposed_count=0,batches=0,history=[],
                    baseline=dict(verses=w['conditions'][family+'30']['verses'])))
                result['families'][family]['windows'][w['id']]=s
                for d in n.DOSES:
                    c=s['cells'].get(str(d));row=dict(passage_id=pid,window_id=w['id'],reference=s['reference'],family=family,dose=d)
                    if not c or c['status']=='pending_combined_review':pending.append(row);continue
                    row.update(status=c['status'],actual_percent=c['actual_percent'])
                    completed.append(row)
                    if c['status'] not in n.PASS:
                        row.update(reason=(c.get('reason','') if c['status']=='held_dose' else
                            c.get('review',{}).get('reason') or c.get('reason','')),
                            failed_checks={k:v for k,v in c.get('checks',{}).items() if v!='yes'})
                        held.append(row)
    summary=dict(total_expected=528,completed=len(completed),pending=len(pending),held=held,
        counts={f:{str(d):dict(Counter(x['status'] for x in completed if x['family']==f and x['dose']==d))
                   for d in n.DOSES} for f in FAMILIES},
        complete_ladders={f:sum(n.all_pass(s['cells']) for s in result['families'][f]['windows'].values()) for f in FAMILIES},
        reused_passages=list(reused),published=False)
    result['summary']=summary
    n.m.review.save(folder/'all_windows.json',result);n.m.review.save(folder/'summary.json',summary)
    (n.m.ROOT/'deliverables/sol_nested_defects_all66.html').write_text(report(result),encoding='utf-8')
    return summary


def run(folder,concurrency=2):
    os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1')
    folder.mkdir(parents=True,exist_ok=True)
    m=n.m;manifest=m.review.read(m.MANIFEST);sources=m.english_by_passage()
    banks=[(p.name,m.review.read(p)) for p in m.BANKS]
    windows={pid:m.load_candidates(manifest,banks,pid,sources)[0] for pid in sources}
    if sum(map(len,windows.values()))!=66:raise ValueError('Expected exactly 66 active source windows')
    config=dict(version=n.VERSION,manifest_sha256=m.clean_digest(manifest),
        bank_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in m.BANKS},
        prompt_sha256=m.clean_digest([n.OMISSION_WRITER,n.MISTRANSLATION_WRITER,n.OMISSION_CANDIDATE_REVIEW,m.COMBINED_REVIEW,n.mr.PROMPT]),
        writer=n.WRITER,reviewer=m.review.JUDGE,max_batches=5,max_candidates=60,review_rounds=2,
        authorization='User explicitly requested all 66 windows on 2026-11-19')
    config_path=folder/'campaign.json'
    if config_path.exists() and m.review.read(config_path)!=config:
        raise ValueError('Campaign inputs changed; use a new output directory')
    m.review.save(config_path,config)
    reused={}
    previous=m.ROOT/'evaluation/runs/sol_nested_defects_2026-11-18/t1_1kgs13/nested.json'
    old=m.review.read(previous)
    if (old['configuration']['manifest_sha256']==config['manifest_sha256'] and
        old['configuration']['bank_sha256']==config['bank_sha256'] and
        old.get('agreement_migration',{}).get('review_prompt_sha256')==m.clean_digest([agreement.AUDIT,n.mr.PROMPT])):
        verify(old,windows['t1_1kgs13'],FAMILIES)
        snapshot=folder/'reused_1kgs13.json'
        if snapshot.exists() and m.clean_digest(m.review.read(snapshot))!=m.clean_digest(old):
            raise ValueError('Previously reused draft changed')
        m.review.save(snapshot,old);reused['t1_1kgs13']=snapshot
    status_path=folder/'jobs.json';statuses=m.review.read(status_path) if status_path.exists() else {}
    jobs=[(pid,f) for pid in sorted(windows,key=lambda p:len(windows[p])) if pid not in reused for f in FAMILIES]
    def execute(job):
        pid,family=job;key=pid+'/'+family;path=folder/pid/family
        if statuses.get(key,{}).get('status')=='complete':
            result=m.review.read(path/'nested.json');verify(result,windows[pid],[family]);return result
        print('START',key,flush=True)
        result=n.run(pid,path,families=(family,),workers=2)
        verify(result,windows[pid],[family]);return result
    collect(folder,windows,sources,reused)
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures={executor.submit(execute,job):job for job in jobs}
        for future in as_completed(futures):
            pid,family=futures[future];key=pid+'/'+family
            try:
                result=future.result();states=result['families'][family]['windows']
                statuses[key]=dict(status='complete',complete_ladders=sum(n.all_pass(s['cells']) for s in states.values()))
            except Exception as exc:
                statuses[key]=dict(status='execution_error',error=type(exc).__name__+': '+str(exc)[:1500])
            m.review.save(status_path,statuses)
            summary=collect(folder,windows,sources,reused)
            print('FINISHED',key,statuses[key],'; completed',summary['completed'],'pending',summary['pending'],flush=True)
    return collect(folder,windows,sources,reused)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output',type=Path,required=True)
    cli.add_argument('--concurrency',type=int,choices=(1,2,3,4),default=2)
    args=cli.parse_args();run(args.output,args.concurrency)
