"""Bound candidate-bank capacity, then review a bounded one-passage dose ladder.

This diagnostic makes fresh selections at each dose. It neither extends the
published 15/30 selections nor writes any candidate bank or live stimulus.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from html import escape
from itertools import combinations
from pathlib import Path
from random import Random

from evaluation.scripts.pipeline import build_mixed_window_omissions as m


def capacity_plan(windows, *, exact=False, target=None, tolerance=2, seed=20261118,
                  fixed=None, banned=()):
    model=m.Model();variables={};errors={};dose_errors={}
    rate=model.var(100)
    model.constrain({rate:1},low=1)
    if target is not None:model.constrain({rate:1},target,target)
    for w in windows:
        ids={c['id']:model.var() for c in w['candidates']};variables[w['id']]=ids
        total=w['clean_content_chars']
        terms={ids[c['id']]:100*c['chars'] for c in w['candidates']}
        terms[rate]=-total
        model.constrain(terms,-tolerance*total,tolerance*total)
        err=model.var(100*total);dose_errors[err]=1
        for sign in (1,-1):
            model.constrain({**{i:sign*v for i,v in terms.items()},err:-1},high=0)
        for a,b in combinations(w['candidates'],2):
            ea,eb=a['edit'],b['edit']
            if ea['verse']==eb['verse'] and max(ea['start'],eb['start'])<min(
                    ea['start']+len(ea['before']),eb['start']+len(eb['before'])):
                model.constrain({ids[a['id']]:1,ids[b['id']]:1},high=1)
        for v,text in w['clean'].items():
            model.constrain({ids[c['id']]:c['chars'] for c in w['candidates'] if c['edit']['verse']==v},
                            high=m.review.mis.content_len(text)-1)
        if fixed and w['id'] in fixed:
            for cid,var in ids.items():
                value=int(cid in fixed[w['id']]);model.constrain({var:1},value,value)
        for wid,selected in banned:
            if wid==w['id']:
                model.constrain({var:1 if cid in selected else -1 for cid,var in ids.items()},
                                high=len(selected)-1)
    for kind,share in m.SHARES.items():
        terms={variables[w['id']][c['id']]:5*int(c['kind']==kind)-share
               for w in windows for c in w['candidates']}
        if exact:model.constrain(terms,0,0)
        else:
            err=model.var(5*sum(len(w['candidates']) for w in windows));errors[err]=1
            for sign in (1,-1):
                model.constrain({**{i:sign*v for i,v in terms.items()},err:-1},high=0)
    if model.solve({}) is None:return None
    if target is None:model.minimize_and_fix({rate:-1})
    if errors:model.minimize_and_fix(errors)
    model.minimize_and_fix(dose_errors)
    rng=Random(seed)
    solution=model.solve({i:rng.uniform(-1,1) for ids in variables.values() for i in ids.values()})
    return dict(target=int(solution[rate]),selected={wid:[cid for cid,var in ids.items() if solution[var]]
                                                    for wid,ids in variables.items()})


def raw_maximum(w):
    """Per-window coverage ceiling without mixture, dose-band, or fluency limits."""
    model=m.Model();pool=w['candidates'];ids={c['id']:model.var() for c in pool}
    for a,b in combinations(pool,2):
        ea,eb=a['edit'],b['edit']
        if ea['verse']==eb['verse'] and max(ea['start'],eb['start'])<min(
                ea['start']+len(ea['before']),eb['start']+len(eb['before'])):
            model.constrain({ids[a['id']]:1,ids[b['id']]:1},high=1)
    for v,t in w['clean'].items():
        model.constrain({ids[c['id']]:c['chars'] for c in pool if c['edit']['verse']==v},
                        high=m.review.mis.content_len(t)-1)
    sol=model.solve({ids[c['id']]:-c['chars'] for c in pool})
    chosen=[c['id'] for c in pool if sol[ids[c['id']]]]
    return m.materialize(w,chosen,None)


def summarize(scenario):
    counts=Counter();statuses=Counter();rates=[]
    for cell in scenario['cells'].values():
        counts.update(cell['unit_counts']);statuses[cell['status']]+=1;rates.append(cell['actual_percent'])
    total=sum(counts.values())
    return dict(counts={k:counts[k] for k in m.KINDS},
                shares={k:100*counts[k]/total for k in m.KINDS},statuses=dict(statuses),
                actual_min=min(rates),actual_max=max(rates))


def add_verified_baseline(result,path):
    if not path.exists():return
    prior=m.review.read(path)
    if any(prior.get(k)!=result.get(k) for k in ('passage_id','manifest_sha256','bank_sha256')):
        raise ValueError('Existing 15/30 trial uses a different candidate bank or source')
    result['previous_reviewed_baseline']={w['id']:w['conditions'] for w in prior['rounds'][-1]['windows']}
    result['previous_reviewed_baseline_path']=str(path)


def highest_tested_pass(result,wid):
    cells=list(result.get('previous_reviewed_baseline',{}).get(wid,{}).values())
    for s in result['scenarios']:
        cells.append(s['cells'][wid])
        cells.extend(h[wid] for h in s['history'])
    passed=[c for c in cells if c['status'] in ('pass','pass_with_flags')]
    return max(passed,key=lambda c:c['actual_percent']) if passed else None


def html_report(result):
    p=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>Omission capacity audit</title><style>body{max-width:1100px;margin:2rem auto;padding:0 1rem;font:16px/1.6 system-ui;color:#203c42}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd9d9;padding:.5rem;text-align:left}article{padding:1rem;background:#f0f5f3;margin:1rem 0;border-radius:8px}small{color:#526569}</style>',
       '<h1>'+escape(result.get('passage_title','1 Kings 13'))+' · Approved omission capacity</h1>',
       '<p>Local diagnostic only. Dose = deleted Chinese content characters / clean content characters. '
       'Mix = word/phrase/clause deletion occurrences, pooled across eight windows. '
       'Only approved candidates are used; overlapping spans cannot be combined and every verse retains content.</p>',
       '<p>Each dose uses fresh selections, independently of the existing 15%/30% draws and other defect conditions. '
       'The numeric ceiling does not prove combined fluency. Tested passes do not establish a globally maximal fluent dose. '
       'Dose tolerance is ±2 percentage points. No lexical rewriting or new deletion candidates were used.</p>',
       f'<p>Highest feasible whole-percentage common target: exact 20/40/40 = <b>{result["exact_ceiling"]}%</b>; '
       f'mix allowed to vary = <b>{result["flexible_ceiling"]}%</b>. These are numeric limits.</p>',
       '<table><tr><th>Window</th><th>Clean characters</th><th>Maximum deletable</th><th>Candidate-only ceiling</th><th>Highest tested pass</th></tr>']
    for w in result['windows']:
        c=w['raw_maximum'];best=highest_tested_pass(result,w['id'])
        label=f'{best["actual_percent"]:.1f}%' if best else 'Not yet checked'
        p.append(f'<tr><td>{escape(w["reference"])}</td><td>{w["clean_content_chars"]}</td><td>{c["deleted_chars"]}</td><td>{c["actual_percent"]:.1f}%</td><td>{label}</td></tr>')
    p.append('</table><p>Highest tested pass includes accepted combinations from either review round and, '
             'when source and bank hashes match, the previously reviewed 15%/30% trial. These individual maxima '
             'do not together establish an exact 20/40/40 mixture or a uniform condition.</p>')
    p.append('<h2>Combined review</h2><table><tr><th>Target</th><th>Mix rule</th><th>Actual range</th><th>Word / phrase / clause</th><th>Review</th></tr>')
    for s in result['scenarios']:
        a=summarize(s)
        p.append(f'<tr><td>{s["target"]}%</td><td>{"Exact" if s["exact"] else "Closest feasible"}</td>'
                 f'<td>{a["actual_min"]:.1f}–{a["actual_max"]:.1f}%</td><td>'+ ' / '.join(f'{a["shares"][k]:.1f}%' for k in m.KINDS)+
                 '</td><td>'+escape(str(a['statuses']))+'</td></tr>')
    p.append('</table>')
    for w in result['windows']:
        p.append('<h2>'+escape(w['reference'])+'</h2><details><summary>Clean Chinese</summary>')
        p.extend('<p>'+escape(v)+'　'+escape(t)+'</p>' for v,t in w['clean'].items());p.append('</details>')
        for s in result['scenarios']:
            c=s['cells'][w['id']]
            p.append(f'<article><h3>{s["target"]}% target · {c["actual_percent"]:.1f}% achieved · {escape(c["status"])}</h3>')
            p.extend('<p>'+escape(v)+'　'+escape(t)+'</p>' for v,t in c['verses'].items())
            if c.get('review'):p.append('<p>'+escape(c['review']['reason'])+'</p>')
            p.append('<p><small>'+escape(str(c.get('checks',{})))+'</small></p>')
            p.append('<details><summary>Selected deletions</summary><ul>')
            p.extend('<li>'+escape(x['kind']+' · '+x['edit']['verse']+' · '+x['edit']['before'])+'</li>' for x in c['selected'])
            p.append('</ul></details></article>')
    return ''.join(p)+'</html>'


def run(passage_id,out,report,cache,with_review=False):
    sources=m.english_by_passage();manifest=m.review.read(m.MANIFEST)
    ws,conflicts=m.load_candidates(manifest,[(p.name,m.review.read(p)) for p in m.BANKS],passage_id,sources)
    exact=capacity_plan(ws,exact=True);flex=capacity_plan(ws)
    result=dict(passage_id=passage_id,published=False,manifest_sha256=m.clean_digest(manifest),
                passage_title=ws[0]['reference'].split(':')[0],
                bank_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in m.BANKS},
                exact_ceiling=exact['target'],flexible_ceiling=flex['target'],
                excluded_conflicts=conflicts,windows=[dict(id=w['id'],reference=w['reference'],
                    clean=w['clean'],clean_content_chars=w['clean_content_chars'],raw_maximum=raw_maximum(w)) for w in ws],
                scenarios=[])
    add_verified_baseline(result,m.ROOT/'evaluation/runs/sol_omission_mix_204040_2026-11-18'/passage_id/'mixture.json')
    specs=[(exact['target'],True)]+[(d,False) for d in (50,60,flex['target']) if d<=flex['target']]
    for target,is_exact in dict.fromkeys(specs):
        plan=capacity_plan(ws,exact=is_exact,target=target)
        if plan is None:continue
        result['scenarios'].append(dict(target=target,exact=is_exact,round=1,
            cells={w['id']:m.materialize(w,plan['selected'][w['id']],target) for w in ws},history=[]))
    def save():
        m.review.save(out,result);report.parent.mkdir(parents=True,exist_ok=True);report.write_text(html_report(result))
    save()
    if not with_review:return result
    m.load_dotenv(m.ROOT/'.env')
    with m.OpenAI(timeout=150,max_retries=3) as client:
        for iteration in range(2):
            def review_one(w):
                # Variant labels are arbitrary IDs; the reviewer sees no target or desired mixture.
                cells={i+1:s['cells'][w['id']] for i,s in enumerate(result['scenarios'])}
                return m.review_window(client,w,cells,sources[passage_id],cache)
            jobs=[w for w in ws if any(s['cells'][w['id']]['status']=='pending_combined_review' for s in result['scenarios'])]
            def record(w,reviewed):
                for i,c in reviewed.items():result['scenarios'][i-1]['cells'][w['id']]=c
                save();print(w['reference'],{result['scenarios'][i-1]['target']:c['status'] for i,c in reviewed.items()},flush=True)
            if jobs:record(jobs[0],review_one(jobs[0]))
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[(w,pool.submit(review_one,w)) for w in jobs[1:]]
                for w,f in futures:record(w,f.result())
            if iteration:break
            for s in result['scenarios']:
                fixed={wid:c['selected_ids'] for wid,c in s['cells'].items() if c['status'] in ('pass','pass_with_flags')}
                bad=[(wid,c['selected_ids']) for wid,c in s['cells'].items() if wid not in fixed]
                if not bad:continue
                s['history'].append(deepcopy(s['cells']))
                plan=capacity_plan(ws,exact=s['exact'],target=s['target'],fixed=fixed,banned=bad,seed=20261119)
                if plan is None:
                    s['stop_reason']='No alternative under this dose, mix and fixed passing combinations.';continue
                s['round']=2
                for w in ws:
                    if w['id'] not in fixed:s['cells'][w['id']]=m.materialize(w,plan['selected'][w['id']],s['target'])
            save()
    return result


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--passage-id',required=True)
    cli.add_argument('--review',action='store_true')
    args=cli.parse_args()
    folder=m.ROOT/'evaluation/runs/sol_omission_capacity_2026-11-18'/args.passage_id
    result=run(args.passage_id,folder/'capacity.json',m.ROOT/'deliverables'/f'sol_omission_capacity_{args.passage_id}.html',
               folder/'reviews',args.review)
    print({f'{s["target"]}% exact={s["exact"]}':summarize(s) for s in result['scenarios']},flush=True)
