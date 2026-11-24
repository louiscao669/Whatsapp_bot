"""Rebuild the 5–60% omission collection while retaining published 15/30% texts.

Uses the existing candidate writer, five-check reviewer and bounded redraws.
The 20/50/30 occurrence mix is soft; dose and review failures remain held.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
import os
from pathlib import Path

from evaluation.scripts.pipeline import rebuild_omission_mixture as r

n,m=r.n,r.m
DOSES=(5,10,15,20,25,30,40,50,60)
NESTED=(30,40,50,60)
FROZEN=(15,30)
SOURCE=m.ROOT/'evaluation/runs/sol_omission_mix205030_all65_2026-11-21/mixture.json'
RELEASE=m.DATA/'passages/sol_scratch65_omission_mix205030_v1.json'
PUBLICATION=SOURCE.parent/'publication.json'
WRITER=n.OMISSION_WRITER.replace(
    'We need a NESTED 30%, 40%, 50%, 60% ladder. Higher levels keep ALL earlier deletions unchanged.',
    'Propose candidates for the supplied unresolved targets among 5%, 10%, 20%, 25%, 40%, 50%, 60%. '
    'The published 15% and 30% passages are FIXED. The 40%, 50%, 60% versions must extend the '
    'fixed 30% deletions, keeping every earlier deletion atom unchanged. Other target doses may be independent. '
    'Additional high-dose candidates must be compatible with the fixed 30% deletion atoms; '
    'do not propose overlapping replacements for those atoms. Use the current ladder and review reasons.'
).replace('between the four doses, not only one maximum-deletion text. Provide alternative 30% foundations\nwhen necessary.',
          'at the unresolved doses, not only one maximum-deletion text. Do not change either fixed comparison.')


def load_inputs(args):
    published=m.review.read(SOURCE);package=m.review.read(RELEASE);publication=m.review.read(PUBLICATION)
    if not publication['published'] or sha256(RELEASE.read_bytes()).hexdigest()!=publication['release_sha256']:
        raise ValueError('Published omission release is not verified')
    if package['provenance']['run_sha256']!=sha256(SOURCE.read_bytes()).hexdigest():
        raise ValueError('The published review run changed')
    windows=deepcopy(published['windows']);sources=m.english_by_passage()
    if len(windows)!=65 or {w['id'] for w in windows}!=set(published['rounds'][-1]['cells']):
        raise ValueError('Expected all 65 active windows')
    files=[SOURCE,RELEASE,PUBLICATION]
    raw={}
    for name,digest in published['configuration']['inputs'].items():
        path=Path(name)
        if sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Source bank changed: '+name)
        files.append(path)
        if 'low_dose' in name:raw['low']={w['id']:w for w in m.review.read(path)['families']['omission']['windows']}
        if 'nested_defects' in name:raw['high']=m.review.read(path)['families']['omission']['windows']
    english={p:sources[p].english for p in sorted({w['passage_id'] for w in windows})}
    if m.clean_digest(english)!=published['configuration']['source_sha256']:raise ValueError('English source changed')
    fixed=deepcopy(published['rounds'][-1]['cells']);histories={};baseline={};generation={}
    package_windows={w['id']:w for w in package['windows']}
    for w in windows:
        wid=w['id'];lo,hi=raw['low'][wid],raw['high'][wid]
        if w['clean']!=lo['clean'] or w['clean']!=hi['clean'] or any(sources[w['passage_id']].chinese[v]!=t for v,t in w['clean'].items()):
            raise ValueError('Clean Chinese changed: '+wid)
        for dose in FROZEN:
            if fixed[wid][str(dose)]!=package_windows[wid]['conditions']['omission'+str(dose)]:
                raise ValueError('Frozen comparison differs from published release')
        histories[wid]=deepcopy(hi['history']+lo['history']+[hi['cells'],lo['cells']]+[x['cells'][wid] for x in published['rounds']])
        baseline[wid]={str(d):deepcopy(fixed[wid][str(d)] if d in FROZEN else
                                      (lo if d<30 else hi)['cells'][str(d)]) for d in DOSES}
        for d,c in baseline[wid].items():
            c['unit_counts']=n.materialize(w,published['pools'][wid],c['selected_ids'],'omission',int(d))['unit_counts']
        generation[wid]=dict(pool=deepcopy(published['pools'][wid]),batches=0,proposed_count=0,
            proposals=deepcopy(hi.get('proposals',[])+lo.get('proposals',[])),
            consumed_proposal_signatures=[],baseline=dict(verses=fixed[wid]['30']['verses']))
    config=dict(doses=list(DOSES),nested_doses=list(NESTED),frozen_doses=list(FROZEN),
        target_percentages=dict(word=20,phrase=50,clause=30),target_weights=dict(word=2,phrase=5,clause=3),
        mixture_basis='deletion_occurrences_pooled_per_dose',tolerance_pp=2,seed=args.seed,max_rounds=3,
        max_new_candidate_batches_per_window=2,max_new_candidates_per_batch=8,
        reviewer=m.review.JUDGE,writer=n.WRITER,
        prompt_sha256=m.clean_digest([WRITER,n.OMISSION_CANDIDATE_REVIEW,m.COMBINED_REVIEW]),
        inputs={str(p):sha256(p.read_bytes()).hexdigest() for p in files},
        bilingual_sha256=m.clean_digest({p:dict(english=sources[p].english,chinese=sources[p].chinese) for p in english}),
        excluded_held=published['configuration']['excluded_held'],
        authorization='All 65 active windows; user confirmed retaining published 15/30 and nesting 40–60 above 30.')
    return config,windows,sources,published['pools'],fixed,histories,baseline,generation


def quality_failed(c):
    return bool(c.get('review')) and any(v in ('no','uncertain') for v in c.get('checks',{}).values())


def select_round(result,histories,iteration):
    windows=result['windows'];pools=result['pools'];fixed=result['fixed'];cfg=result['configuration']
    previous=result['rounds'][iteration-1]['cells'] if iteration else {}
    memory={w['id']:histories[w['id']]+[x['cells'][w['id']] for x in result['rounds'][:iteration]] for w in windows}
    banned=[]
    for wid,entries in memory.items():
        seen=set()
        for h in entries:
            for c in h.values():
                if quality_failed(c):
                    key=tuple(sorted(c['selected_ids']))
                    if key not in seen:banned.extend((wid,d,list(key)) for d in DOSES);seen.add(key)
    cells=deepcopy(fixed);fits={}
    for targets in ((5,),(10,),(20,),(25,),NESTED):
        frozen={(wid,d):cs[str(d)]['selected_ids'] for wid,cs in fixed.items() for d in FROZEN}
        preferred={}
        for wid,cs in previous.items():
            for d in targets:
                if d not in FROZEN and cs[str(d)]['status'] in n.PASS:
                    (preferred if len(targets)>1 else frozen)[wid,d]=cs[str(d)]['selected_ids']
        print('Fitting round',iteration+1,'doses',targets,flush=True)
        fit=n.plan(windows,pools,'omission',doses=targets,strict=False,fixed=frozen,preferred=preferred,
            banned=banned,omission_mix=cfg['target_weights'],seed=cfg['seed']+iteration*100+targets[-1])
        if fit is None:raise ValueError('No selection retains the published comparisons')
        fits['-'.join(map(str,targets))]={k:v for k,v in fit.items() if k!='selected'}
        for w in windows:
            wid=w['id']
            for d in targets:
                if d in FROZEN:
                    if set(fit['selected'][wid,d])!=set(fixed[wid][str(d)]['selected_ids']):
                        raise ValueError('Published deletion changed')
                    continue
                c=n.materialize(w,pools[wid],fit['selected'][wid,d],'omission',d)
                prior=n.remembered_review(memory[wid],c);n.apply_remembered_review(w,d,c,prior)
                if prior:c['review_reused']=True
                if c['status']=='held_dose':
                    c['reason']=(f'No in-band version was selected at {d}% ±2 points under the approved candidate '
                        f'and nesting constraints. This held selection reaches {c["actual_percent"]:.2f}%. '
                        'The fixed 15%/30% passages and all required checks remain unchanged.')
                cells[wid][str(d)]=c
    return dict(round=iteration+1,cells=cells,fit=fits,review_complete=False)


def review_one(client,w,cells,source,folder):
    cells=deepcopy(cells)
    todo=[d for d in sorted(cells,key=int) if cells[d]['status']=='pending_combined_review']
    for start in range(0,len(todo),4):
        group=todo[start:start+4]
        reviewed=r.review_window(client,w,{d:cells[d] for d in group},source,folder)
        cells.update(reviewed)
    return cells


def verify(result):
    latest=result['rounds'][-1]
    for w in result['windows']:
        wid=w['id'];cells=latest['cells'][wid]
        if set(cells)!=set(map(str,DOSES)):raise ValueError('Missing target dose')
        for d in FROZEN:
            if cells[str(d)]!=result['fixed'][wid][str(d)]:raise ValueError('Published comparison changed')
        n.validate_chain(w,{str(d):cells[str(d)] for d in NESTED},'omission',doses=NESTED)
        for d,c in cells.items():
            replay=n.materialize(w,result['pools'][wid],c['selected_ids'],'omission',int(d))
            if any(replay[k]!=c[k] for k in ('verses','edits','affected_chars','actual_percent','unit_counts','punctuation_cleanup')):
                raise ValueError('Exact replay failed')
            if c['status'] in n.PASS:
                if any(c.get('checks',{}).get(k)!='yes' for k in m.review.ClauseChecks.model_fields):raise ValueError('Missing review check')
                if abs(100*c['affected_chars']-int(d)*w['clean_content_chars'])>2*w['clean_content_chars']:raise ValueError('Passing version misses dose')
    return True


def refresh(result):
    if not result['rounds']:return
    record=result['rounds'][-1];cells=record['cells']
    record['summary']=r.summary(result['windows'],cells,doses=DOSES)
    record['accepted_summary']=r.summary(result['windows'],cells,doses=DOSES,accepted_only=True)


def retain_reviewed_chains(result, histories):
    """Recover passing reviewed versions only when their complete ladder nests.

    No wording is edited and no failed verdict is promoted. An exact-context
    failure blocks reuse of a conflicting pass. Keep the pre-retention cells
    and source rounds so the final selection remains auditable.
    """
    if 'reviewed_chain_retention' in result:return
    retained={};latest=result['rounds'][-1]
    fingerprint=lambda c:m.clean_digest(dict(edits=c['edits'],verses=c['verses']))
    for w in result['windows']:
        wid=w['id'];current=latest['cells'][wid]
        memory=histories[wid]+[record['cells'][wid] for record in result['rounds']]
        failed={fingerprint(c) for cs in memory for c in cs.values() if quality_failed(c)}
        options=[]
        for d in NESTED[1:]:
            choices=[];seen=set()
            for record in reversed(result['rounds']):
                c=record['cells'][wid][str(d)];key=fingerprint(c)
                if key in seen or (c['status'] in n.PASS and key in failed):continue
                seen.add(key);choices.append((record['round'],c))
            options.append(choices)
        original=sum(current[str(d)]['status'] in n.PASS for d in NESTED[1:])
        best_score=(original,3);best=None
        for choices in product(*options):
            chain={'30':result['fixed'][wid]['30'],**{str(d):c for d,(_,c) in zip(NESTED[1:],choices)}}
            try:n.validate_chain(w,chain,'omission',doses=NESTED)
            except ValueError:continue
            score=(sum(c['status'] in n.PASS for _,c in choices),
                   sum(fingerprint(c)==fingerprint(current[str(d)]) for d,(_,c) in zip(NESTED[1:],choices)))
            if score>best_score:best_score=score;best=choices
        if best is not None:
            retained[wid]=dict(passes_before=original,passes_after=best_score[0],
                before={str(d):deepcopy(current[str(d)]) for d in NESTED[1:]},
                source_rounds={str(d):round_number for d,(round_number,_) in zip(NESTED[1:],best)})
            for d,(_,c) in zip(NESTED[1:],best):current[str(d)]=deepcopy(c)
    result['reviewed_chain_retention']=retained
    refresh(result)


def write_verification(result, folder):
    m.review.save(folder/'verification.json',dict(expected_variants=585,exact_replay=True,
        all_130_published_comparisons_unchanged=True,all_65_high_dose_ladders_nested=True,
        all_passing_variants_in_band_and_reviewed=True,inputs_unchanged=True,published=False,
        retained_reviewed_chains=len(result.get('reviewed_chain_retention',{})),
        summary=result['rounds'][-1]['summary'],accepted_summary=result['rounds'][-1]['accepted_summary']))


def refill(result,sources,iteration,folder,workers,save):
    prior=result['rounds'][-1]['cells'];jobs=[]
    for w in result['windows']:
        bad=[int(d) for d,c in prior[w['id']].items() if int(d) not in FROZEN and
             (c['status']=='held_dose' if iteration==1 else c['status'] not in n.PASS)]
        if bad and result['generation'][w['id']]['batches']<2:jobs.append((w,bad))
    if not jobs:return
    os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1');m.load_dotenv(m.ROOT/'.env')
    def execute(w,targets):
        state=deepcopy(result['generation'][w['id']]);state.update(pool=deepcopy(result['pools'][w['id']]),cells=deepcopy(prior[w['id']]))
        with m.OpenAI(timeout=180,max_retries=2) as client:
            n.generate_candidates(client,w,sources[w['passage_id']],'omission',state,
                folder/'generation'/m.clean_digest(w['id'])[:16],8,doses=tuple(targets),writer_prompt=WRITER)
        usable=[]
        for candidate in state['pool']:
            try:usable.append(r.mixture_candidate(candidate))
            except ValueError:state.setdefault('unclassified_candidates',[]).append(candidate)
        state['pool']=usable
        return state
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending={executor.submit(execute,w,ds):w for w,ds in jobs}
        for future in as_completed(pending):
            w=pending[future];state=future.result();result['generation'][w['id']]=state;result['pools'][w['id']]=state['pool']
            save();print('Additional candidates reviewed:',w['reference'],'pool',len(state['pool']),flush=True)


def run(args):
    config,windows,sources,pools,fixed,histories,baseline,generation=load_inputs(args)
    result=m.review.read(args.output) if args.output.exists() else dict(configuration=config,
        passage_title='65 active windows · 5%–60%',windows=windows,pools=deepcopy(pools),fixed=fixed,
        baseline=baseline,baseline_summary=r.summary(windows,baseline,doses=DOSES),
        generation=generation,rounds=[],execution_errors={},published=False)
    if result['configuration']!=config:raise ValueError('Inputs changed; use a new output path')
    def save():
        refresh(result);m.review.save(args.output,result)
        if result['rounds']:
            publication_path=args.output.parent/'research_publication.json'
            publication=m.review.read(publication_path) if publication_path.exists() else None
            args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(r.report_html(result,publication=publication))
    if result.get('stop_reason') and all(x['review_complete'] for x in result['rounds']):
        retain_reviewed_chains(result,histories);verify(result);save()
        write_verification(result,args.output.parent)
        return result
    for iteration in range(config['max_rounds']):
        if iteration==len(result['rounds']):
            if iteration and args.review:refill(result,sources,iteration,args.output.parent,args.workers,save)
            result['rounds'].append(select_round(result,histories,iteration));save()
        record=result['rounds'][iteration]
        if record['review_complete']:continue
        print('Selection',iteration+1,json.dumps(r.summary(windows,record['cells'],doses=DOSES)),flush=True)
        verify(result)
        if not args.review:return result
        os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1');m.load_dotenv(m.ROOT/'.env')
        jobs=[w for w in windows if any(c['status']=='pending_combined_review' for c in record['cells'][w['id']].values())]
        result['execution_errors']={}
        with m.OpenAI(timeout=180,max_retries=2) as client,ThreadPoolExecutor(max_workers=args.workers) as executor:
            pending={executor.submit(review_one,client,w,record['cells'][w['id']],sources[w['passage_id']],
                args.output.parent/'reviews'/m.clean_digest(w['id'])[:16]):w for w in jobs}
            for future in as_completed(pending):
                w=pending[future]
                try:record['cells'][w['id']]=future.result()
                except Exception as exc:result['execution_errors'][w['id']]=type(exc).__name__+': '+str(exc)[:1200]
                save();print(w['reference'],dict(Counter(c['status'] for c in record['cells'][w['id']].values())),flush=True)
        if result['execution_errors']:raise RuntimeError(str(result['execution_errors']))
        record['review_complete']=True;verify(result);save()
        if all(c['status'] in n.PASS for cs in record['cells'].values() for c in cs.values()):
            result['stop_reason']='All 585 variants passed';break
    else:result['stop_reason']='Bounded selection, candidate refill and review exhausted; remaining variants held'
    retain_reviewed_chains(result,histories);verify(result)
    for path,digest in config['inputs'].items():
        if sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Input changed during the run')
    save()
    write_verification(result,args.output.parent)
    print('COMPLETE',result['stop_reason'],json.dumps(result['rounds'][-1]['summary']),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--seed',type=int,default=20261121);p.add_argument('--workers',type=int,choices=range(1,7),default=6)
    p.add_argument('--review',action='store_true')
    run(p.parse_args())
