"""Recombine reviewed omission candidates for a configurable omission mixture.

The mixture counts deletion occurrences pooled at each dose. No new candidates,
manual wording, production imports, or participant changes are made here.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

from evaluation.scripts.pipeline import build_nested_window_defects as n

m = n.m
DOSES = (15, 30)


def selected_windows(baseline, passage_id=None, assignment=None, all_active=False):
    held=set(baseline.get('held_for_review',[]))
    return [w for w in baseline['windows'] if w['id'] not in held and
            (w['id'] in assignment if assignment is not None else
             all_active or w['passage_id']==passage_id)]


def mixture_candidate(candidate):
    """Count a reviewed multi-clause deletion span in the clause-level category."""
    c=deepcopy(candidate)
    if len(c['edits'])!=len(c['kinds']) or set(c['kinds'])-set(m.KINDS)-{'multiple_clauses'}:
        raise ValueError('Missing or unsupported reviewed omission-unit classification')
    if 'multiple_clauses' in c['kinds']:
        c['reviewed_kinds']=list(c['kinds'])
        c['kinds']=['clause' if k=='multiple_clauses' else k for k in c['kinds']]
    return c


def reuse_histories(paths, windows, histories, sources, input_hashes):
    """Import unchanged, compatible review evidence, including failed combinations."""
    current={w['id']:w for w in windows}; provenance={}
    for path in paths:
        previous=m.review.read(path); cfg=previous['configuration']
        if cfg['prompt_sha256']!=m.clean_digest(m.COMBINED_REVIEW) or cfg['reviewer']!=m.review.JUDGE:
            raise ValueError('Cached review rubric or model differs: '+str(path))
        if cfg['inputs']!=input_hashes:
            raise ValueError('Cached review source banks differ: '+str(path))
        passage_ids=sorted({w.get('passage_id',cfg.get('passage_id')) for w in previous['windows']})
        english=(sources[cfg['passage_id']].english if cfg.get('passage_id') else
                 {p:sources[p].english for p in passage_ids})
        if cfg['source_sha256']!=m.clean_digest(english):
            raise ValueError('Cached English source changed: '+str(path))
        for old in previous['windows']:
            wid=old['id']
            if wid not in current:continue
            if old['clean']!=current[wid]['clean']:
                raise ValueError('Cached clean window changed: '+wid)
            histories[wid].extend(deepcopy(r['cells'][wid]) for r in previous['rounds'])
        provenance[str(path)]=sha256(path.read_bytes()).hexdigest()
    return provenance


def summary(windows, cells, doses=DOSES, accepted_only=False):
    result = {}
    for dose in doses:
        counts = Counter()
        statuses = Counter()
        for w in windows:
            if str(dose) not in cells[w['id']]:continue
            cell = cells[w['id']][str(dose)]
            if accepted_only and cell['status'] not in n.PASS:continue
            counts.update(cell['unit_counts'])
            statuses[cell['status']] += 1
        total = sum(counts.values())
        result[str(dose)] = dict(occurrences=dict(counts), total_occurrences=total,
            percentages={k:100*counts[k]/total if total else 0 for k in m.KINDS},
            statuses=dict(statuses))
    return result


def review_window(client, w, cells, source, folder):
    """JSON dose keys are strings; the structured reviewer uses integer IDs."""
    reviewed=n.review_cells(client,w,{int(d):c for d,c in cells.items()},source,folder,'omission')
    return {str(d):c for d,c in reviewed.items()}


def report_html(result, publication=None):
    cfg = result['configuration']; latest = result['rounds'][-1]
    doses=tuple(cfg.get('doses',DOSES))
    nested=cfg.get('nested_doses',[])
    published=bool(publication and publication.get('published'))
    research_release=published and publication.get('scope')=='research'
    mix_label='/'.join(f'{cfg["target_percentages"][k]:g}' for k in m.KINDS)
    def status_label(status):
        return {'pass':'Pass','pass_with_flags':'Pass with flags','rejected':'Needs review — failed check',
                'held':'Needs review — uncertain','held_dose':'Needs review — dose',
                'pending_combined_review':'Review pending'}.get(status,status)
    def table(stats):
        rows = ['<table><tr><th>Dose</th><th>Word</th><th>Phrase</th><th>Clause</th><th>Review</th></tr>']
        for dose, s in stats.items():
            rows.append(f'<tr><td>{dose}%</td>'+''.join(
                f'<td>{s["occurrences"].get(k,0)} ({s["percentages"][k]:.1f}%)</td>' for k in m.KINDS)
                +'<td>'+escape('; '.join(f'{status_label(k)}: {v}' for k,v in s['statuses'].items()))+'</td></tr>')
        return ''.join(rows)+'</table>'
    p=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>Omission mixture comparison</title><style>body{font:16px/1.65 system-ui;max-width:1200px;margin:28px auto;padding:0 20px;color:#243a40}',
       'table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #d8e1df;text-align:left}',
       '.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}article{background:#f1f5f4;padding:18px}',
       '.zh{font-size:18px}del{background:#ffe1d6}summary{cursor:pointer}h2{margin-top:2em}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>',
       '<h1>'+escape(result['passage_title'])+' · '+mix_label+' omission preference</h1>',
       (f'<p>Published as a separate research release: {publication["approved_variants"]} approved variants. Held variants are excluded. The human pilot’s conditions, passages, QAs and assignments are unchanged. ' if research_release else
        '<p>Published to the live pilot. All 130 omission variants were verified after publication; the other conditions and QA content were preserved. ' if published else
        '<p>Local drafts only. Existing test passages are unchanged. ')+
       'The target mix counts deletion occurrences, pooled across the selected windows separately at each dose. ',
       'Dose counts deleted clean Chinese content characters, with ±2 percentage points allowed in every window. '+
       ('The published 15% and 30% versions are retained exactly. The 30%, 40%, 50% and 60% versions keep every earlier deletion; other doses are selected independently.</p>' if nested else
        'Doses are selected independently; nesting is not required.</p>'),
       '<p>Existing reviewed units retain their classifications; multi-clause spans count as clause-level deletion occurrences in the three-category mix. New combinations receive the unchanged five-check bilingual review, without the QA, answer key, desired mix, or prior verdicts.</p>',
       '<p>Required checks: information omitted, substantive content removed, fluent Chinese, deletion only, and valid in the displayed context. Semantic distortion, ambiguous references, and recoverability are recorded as nonblocking flags. A flagged pass meets all five checks; a failed or uncertain check remains unavailable for publication.</p>',
       '<h2>Previous reference passages</h2>',table(result['baseline_summary']),
       '<h2>'+('Release review outcomes' if research_release else 'Published selections' if published else 'New selections')+'</h2>',table(latest['summary']),
       '<p>Stop reason: '+escape(result.get('stop_reason','In progress'))+'. Reviewer: '+escape(cfg['reviewer'])+'.</p>']
    if latest.get('accepted_summary'):
        p.extend(['<p>The selection table includes held candidates. The following mixture counts only versions that passed every required check and met their dose.</p>',
                  '<h2>Passing versions only</h2>',table(latest['accepted_summary'])])
    if result.get('reviewed_chain_retention'):
        p.append('<p>Final selection retained earlier reviewed passages in '+str(len(result['reviewed_chain_retention']))+
                 ' windows where doing so increased passing variants while preserving the complete nested sequence. '
                 'The original repair outputs and source review rounds remain recorded; no wording or verdict was changed.</p>')
    needs=[(w,d,c) for w in result['windows'] for d,c in latest['cells'][w['id']].items() if c['status'] not in n.PASS]
    p.append('<h2>Still needs review</h2>')
    if not needs:p.append('<p>None. Every variant passed the required checks.</p>')
    else:
        p.append('<table><tr><th>Window / dose</th><th>Outcome</th><th>Failed or uncertain checks</th><th>Reviewer finding</th></tr>')
        for w,d,c in needs:
            failures=', '.join(k+' = '+v for k,v in c.get('checks',{}).items() if v!='yes')
            p.append('<tr><td>'+escape(w['reference']+' · '+d+'%')+'</td><td>'+escape(status_label(c['status']))+
                '</td><td>'+escape(failures)+'</td><td>'+escape(c.get('reason','') if c['status']=='held_dose' else c.get('review',{}).get('reason',c.get('reason','Pending')))+ '</td></tr>')
        p.append('</table>')
    p.append('<h2>Every window</h2><div style="overflow:auto"><table><tr><th>Window</th>'+''.join(f'<th>{d}% dose / review</th>' for d in doses)+'</tr>')
    for w in result['windows']:
        p.append('<tr><td>'+escape(w['reference'])+'</td>'+''.join(
            (f'<td>{latest["cells"][w["id"]][str(d)]["actual_percent"]:.1f}% · '+escape(status_label(latest['cells'][w['id']][str(d)]['status']))+'</td>')
            if str(d) in latest['cells'][w['id']] else '<td>Not assigned</td>' for d in doses)+'</tr>')
    p.append('</table></div>')
    for w in result['windows']:
        p.append('<h2>'+escape(w['reference'])+'</h2><details><summary>Clean passage</summary>')
        for v,t in w['clean'].items():p.append('<p class="zh">'+escape(v+'　'+t)+'</p>')
        p.append('</details><div class="grid">')
        for dose in doses:
            if str(dose) not in latest['cells'][w['id']]:continue
            c=latest['cells'][w['id']][str(dose)]
            p.append(f'<article><h3>{dose}% target · {c["actual_percent"]:.1f}% actual</h3><p>'+escape(status_label(c['status']))+' · '+escape(str(c['unit_counts']))+'</p>')
            if c.get('reason'):p.append('<p>'+escape(c['reason'])+'</p>')
            for v,t in c['verses'].items():p.append('<p class="zh">'+escape(v+'　'+t)+'</p>')
            if c.get('review'):p.append('<p>'+escape(c['review']['reason'])+'</p>')
            if c.get('flags'):p.append('<p>Flags: '+escape(', '.join(c['flags']))+'</p>')
            p.append('<details><summary>Deleted units</summary><ul>')
            lookup={x['id']:x for x in result['pools'][w['id']]}
            for cid in c['selected_ids']:
                candidate=lookup[cid]
                for kind,e in zip(candidate['kinds'],candidate['edits']):
                    p.append('<li>'+escape(kind+' · '+e['verse'])+' · <del>'+escape(e['before'])+'</del></li>')
            p.append('</ul></details></article>')
        p.append('</div>')
    return ''.join(p)+'</html>'


def run(args):
    weights=n.omission_mix_weights(dict(zip(m.KINDS,args.mix)))
    assignment_path=getattr(args,'assignment',None)
    assignment=m.review.read(assignment_path)['window_conditions'] if assignment_path else None
    if assignment is not None and (not assignment or any(c not in ('omission15','omission30') for c in assignment.values())):
        raise ValueError('Assigned preview needs window IDs mapped to omission15 or omission30')
    baseline=m.review.read(args.baseline)
    low={w['id']:w for w in m.review.read(args.low_bank)['families']['omission']['windows']}
    high=m.review.read(args.high_bank)['families']['omission']['windows']
    sources=m.english_by_passage()
    all_active=getattr(args,'all_active',False)
    windows=[]; pools={}; histories={}; originals={}
    for base in selected_windows(baseline,args.passage_id,assignment,all_active):
        wid=base['id']
        source=sources[base['passage_id']]
        lo,hi=low[wid],high[wid]; clean=base['conditions']['clean']['verses']
        assert clean==lo['clean']==hi['clean']
        assert all(source.chinese[v]==t for v,t in clean.items())
        w=dict(id=wid,passage_id=base['passage_id'],reference=lo['reference'],clean=clean,clean_content_chars=base['clean_content_chars'])
        windows.append(w); lookup={}
        for c in hi['pool']+lo['pool']:
            rebuilt=n.make_candidate(c['edits'],c['kinds'])
            assert all(rebuilt[k]==c[k] for k in ('id','edits','chars','kinds'))
            c=mixture_candidate(c)
            assert all(not e['after'] and clean[e['verse']][e['start']:e['start']+len(e['before'])]==e['before'] for e in c['edits'])
            if c['id'] in lookup:
                assert all(lookup[c['id']].get(k)==c.get(k) for k in ('edits','chars','kinds','requires'))
            lookup[c['id']]=deepcopy(c)
        pools[wid]=list(lookup.values())
        doses=DOSES if assignment is None else (int(assignment[wid].removeprefix('omission')),)
        originals[wid]={str(d):deepcopy(base['conditions']['omission'+str(d)]) for d in doses}
        histories[wid]=deepcopy(hi['history']+lo['history']+[hi['cells'],lo['cells'],originals[wid]])
    if not windows:raise ValueError('No eligible windows in requested passage')
    if assignment is not None and set(originals)!=set(assignment):
        raise ValueError('Assignment contains missing or held windows')
    cfg=dict(passage_id=args.passage_id,target_weights=weights,
        target_percentages={k:100*v/sum(weights.values()) for k,v in weights.items()},
        doses=list(DOSES),seed=args.seed,max_rounds=args.max_rounds,reviewer=m.review.JUDGE,
        prompt_sha256=m.clean_digest(m.COMBINED_REVIEW),
        source_sha256=m.clean_digest(source.english if assignment is None and not all_active else
            {p:sources[p].english for p in sorted({w['passage_id'] for w in windows})}),
        inputs={str(p):sha256(p.read_bytes()).hexdigest() for p in (args.baseline,args.low_bank,args.high_bank)},
        mixture_basis='deletion_occurrences_pooled_per_dose',selection='independent_doses',tolerance_pp=2)
    if assignment is not None:
        cfg.update(window_conditions=assignment,assignment_sha256=sha256(assignment_path.read_bytes()).hexdigest())
    if all_active:
        cfg.update(scope='all_active_windows',excluded_held=baseline.get('held_for_review',[]))
    if any('reviewed_kinds' in c for pool in pools.values() for c in pool):
        cfg['unit_grouping']='A reviewed multiple_clauses span counts as one clause-level deletion occurrence; original reviewed_kinds are preserved.'
    reuse_paths=getattr(args,'reuse_review',[])
    if reuse_paths:
        cfg['reused_review_inputs']=reuse_histories(reuse_paths,windows,histories,sources,cfg['inputs'])
    result=m.review.read(args.output) if args.output.exists() else dict(configuration=cfg,
        passage_title=(f'{len(windows)} active windows' if all_active else
                       f'{len(windows)} unanswered windows' if assignment is not None else windows[0]['reference'].split(':')[0]),windows=windows,pools=pools,
        baseline=originals,baseline_summary=summary(windows,originals),rounds=[],published=False)
    if result['configuration']!=cfg:raise ValueError('Run inputs changed; use a new output path')
    def save():
        m.review.save(args.output,result)
        if result['rounds']:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(report_html(result))
    for iteration in range(args.max_rounds):
        fixed={}; banned=[]
        if iteration:
            for wid,cs in result['rounds'][iteration-1]['cells'].items():
                for d,c in cs.items():
                    if c['status'] in n.PASS:fixed[(wid,int(d))]=c['selected_ids']
        memory={wid:histories[wid]+[r['cells'][wid] for r in result['rounds'][:iteration]] for wid in pools}
        for wid,history in memory.items():
            for entry in history:
                for c in entry.values():
                    if c['status'] in ('held','rejected'):
                        banned.extend((wid,d,c['selected_ids']) for d in DOSES)
        if iteration==len(result['rounds']):
            cells={w['id']:{} for w in windows}; fits={}
            for dose in DOSES:
                dose_windows=[w for w in windows if str(dose) in originals[w['id']]]
                if not dose_windows:continue
                print(f'Fitting {len(dose_windows)} windows at {dose}% (round {iteration+1})',flush=True)
                solution=n.plan(dose_windows,pools,'omission',doses=(dose,),strict=True,
                    omission_mix=weights,fixed=fixed,banned=banned,seed=args.seed+iteration*100+dose)
                if solution is None:
                    if not result['rounds']:raise ValueError('No in-band mixture from approved candidates')
                    result['stop_reason']='No further in-band selection after failed combinations were excluded';save();return result
                fits[str(dose)]={k:v for k,v in solution.items() if k!='selected'}
                for w in dose_windows:
                    wid=w['id'];c=n.materialize(w,pools[wid],solution['selected'][(wid,dose)],'omission',dose)
                    prior=n.remembered_review(memory[wid],c)
                    n.apply_remembered_review(w,dose,c,prior)
                    if prior:c['review_reused']=True
                    cells[wid][str(dose)]=c
            result['rounds'].append(dict(round=iteration+1,cells=cells,fit=fits,review_complete=False))
        record=result['rounds'][iteration]; cells=record['cells']
        record['summary']=summary(windows,cells);save()
        print('Selection',iteration+1,json.dumps(record['summary']),flush=True)
        if not args.review:return result
        jobs=[w for w in windows if any(c['status']=='pending_combined_review' for c in cells[w['id']].values())]
        if jobs:
            os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1');m.load_dotenv(m.ROOT/'.env')
            with m.OpenAI(timeout=180,max_retries=2) as client,ThreadPoolExecutor(max_workers=getattr(args,'workers',2)) as executor:
                pending={executor.submit(review_window,client,w,cells[w['id']],sources[w['passage_id']],
                    args.output.parent/'reviews'/m.clean_digest(w['id'])[:16]):w for w in jobs}
                for future in as_completed(pending):
                    w=pending[future];cells[w['id']]=future.result()
                    record['summary']=summary(windows,cells);save()
                    print(w['reference'],{d:c['status'] for d,c in cells[w['id']].items()},flush=True)
        record['review_complete']=True
        for w in windows:
            for d,c in cells[w['id']].items():
                replay=n.materialize(w,pools[w['id']],c['selected_ids'],'omission',int(d))
                assert all(replay[k]==c[k] for k in ('verses','edits','affected_chars','actual_percent','unit_counts'))
                assert abs(c['actual_percent']-int(d))<=2
                if c['status'] in n.PASS:assert all(c['checks'][k]=='yes' for k in m.review.ClauseChecks.model_fields)
        if all(c['status'] in n.PASS for cs in cells.values() for c in cs.values()):
            result['stop_reason']=f'All {sum(map(len,cells.values()))} passage variants passed review';save();return result
        save()
    result['stop_reason']='Bounded review and redraw exhausted; remaining failures held';save();return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    scope=p.add_mutually_exclusive_group(required=True)
    scope.add_argument('--passage-id')
    scope.add_argument('--assignment',type=Path,help='Frozen window_conditions map; build only each assigned dose')
    scope.add_argument('--all-active',action='store_true',help='Build both doses for every window not held in the baseline')
    for name in ('baseline','low-bank','high-bank','output','report'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mix',type=int,nargs=3,metavar=('WORD','PHRASE','CLAUSE'),default=[20,50,30])
    p.add_argument('--seed',type=int,default=20261121)
    p.add_argument('--max-rounds',type=int,choices=(1,2,3),default=2)
    p.add_argument('--review',action='store_true')
    p.add_argument('--workers',type=int,choices=range(1,7),default=2,help='Concurrent independent window reviews; does not change selection or review rules')
    p.add_argument('--reuse-review',type=Path,action='append',default=[],help='Compatible prior mixture run; reuse identical full-context verdicts')
    args=p.parse_args();result=run(args)
    print(json.dumps(dict(stop_reason=result.get('stop_reason','Awaiting combined review'),
        summary=result['rounds'][-1]['summary'],report=str(args.report)),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
