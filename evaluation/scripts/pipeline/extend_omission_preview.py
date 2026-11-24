"""Add reviewed 5/10/20/25% examples to the ten-question 15/30% preview."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
from html import escape
import os
from pathlib import Path

from evaluation.scripts.pipeline import preview_omission_questions as preview

n = preview.n
m = n.m
NEW_DOSES = (5, 10, 20, 25)
ALL_DOSES = (5, 10, 15, 20, 25, 30)
WRITER_PROMPT = n.OMISSION_WRITER.replace(
    'We need a NESTED 30%, 40%, 50%, 60% ladder. Higher levels keep ALL earlier deletions unchanged.',
    'We need additional candidates for the supplied low/intermediate omission targets (5%, 10%, 20%, 25%).\n'
    'Existing 15% and 30% comparison passages stay unchanged. These examples need not form a fully nested ladder.'
).replace('between the four doses, not only one maximum-deletion text. Provide alternative 30% foundations\nwhen necessary.',
    'at the requested doses, not only one maximum-deletion text. Small doses need short, substantive\n'
    'word or phrase deletions. Do not remove decorative details or discourse markers to reach a number.')


def pool_within(pool, upper, family='omission'):
    mask = preview.deleted_positions(upper['edits'])
    if family=='mistranslation':
        atoms=set(n.signature(upper['edits']))
        pool=[c for c in pool if set(n.signature(c['edits']))<=atoms]
    else:
        pool = [c for c in pool if preview.deleted_positions(c['edits']) <= mask]
    for _ in range(len(pool)):
        ids = {c['id'] for c in pool}
        pool = [c for c in pool if set(c.get('requires', [])) <= ids]
    return pool


def fit_cell(w, state, original, dose, attempt, iteration, family='omission'):
    all_candidates = state['pool']
    higher = min((int(d) for d,c in state['cells'].items()
        if int(d)>dose and c['status'] in n.PASS), default=30)
    candidates = pool_within(all_candidates, state['cells'][str(higher)],family) if attempt==0 else all_candidates
    history = original['history'] + state['history']
    banned = [(w['id'],dose,c['selected_ids']) for h in history for c in h.values()
        if c['status'] in ('held','rejected') and set(c['selected_ids']) <= {x['id'] for x in candidates}]
    lower = max((int(d) for d,c in state['cells'].items()
        if int(d)<dose and c['status'] in n.PASS), default=None)
    preferred = {(w['id'],dose):state['cells'][str(lower)]['selected_ids']} if lower else None
    options = dict(doses=(dose,),strict=True,banned=banned,preferred=preferred,
        forbidden=[(w['id'],bad) for bad in original.get('baseline',{}).get('forbidden_candidate_sets',[])],
        seed=20261119+iteration*100+attempt*10+dose)
    solution=n.plan([w],{w['id']:candidates},family,**options)
    mode='within_higher_dose' if attempt==0 else 'independent'
    if solution is None and candidates is not all_candidates:
        candidates=all_candidates
        options['banned']=[(w['id'],dose,c['selected_ids']) for h in history for c in h.values()
            if c['status'] in ('held','rejected')]
        solution=n.plan([w],{w['id']:candidates},family,**options)
        mode='independent'
    if solution is None:
        cell=n.materialize(w,all_candidates,[],family,dose)
        cell.update(status='held_dose',reason='No in-band selection from the current reviewed candidate pool.')
        return cell
    cell=n.materialize(w,candidates,solution['selected'][(w['id'],dose)],family,dose)
    cell['selection_mode']=mode
    cell['optimization_fallback_stages']=solution.get('optimization_fallback_stages',[])
    n.apply_remembered_review(w,dose,cell,n.remembered_review(history,cell))
    return cell


def build_one(w, fixed, original, source, folder, *, target_doses=NEW_DOSES, writer_prompt=WRITER_PROMPT, family='omission'):
    path=folder/'preview.json'
    config=dict(window_id=w['id'],fixed_sha256=m.clean_digest(fixed['cells']),
        original_sha256=m.clean_digest(original),targets=list(target_doses),tolerance_pp=2,
        writer=n.WRITER,reviewer=m.review.JUDGE,max_batches=5,max_candidates=40,
        prompt_sha256=m.clean_digest([writer_prompt,n.OMISSION_CANDIDATE_REVIEW,m.COMBINED_REVIEW] if family=='omission' else [writer_prompt,n.mr.PROMPT]))
    if family!='omission':config['family']=family
    state=m.review.read(path) if path.exists() else dict(configuration=config,
        cells=deepcopy(fixed['cells']),pool=deepcopy(original['pool']),history=[],attempts=[],
        baseline=dict(verses=fixed['cells']['30']['verses']),batches=0,proposed_count=0,proposals=[])
    if state['configuration']!=config:raise ValueError('Extension inputs changed')
    def pending():return [d for d in target_doses if state['cells'].get(str(d),{}).get('status') not in n.PASS]
    m.review.save(path,state)
    with m.OpenAI(timeout=180,max_retries=2) as client:
        for iteration in range(6):
            if not pending():break
            for attempt in range(2):
                cells={str(d):fit_cell(w,state,original,d,attempt,iteration,family) for d in pending()}
                if not cells:break
                items=list(cells.values())
                for start in range(0,len(items),4):
                    n.review_cells(client,w,{i+1:c for i,c in enumerate(items[start:start+4])},source,folder,family)
                for dose,cell in cells.items():
                    n.apply_remembered_review(w,dose,cell,None)
                    n.validate_chain(w,{dose:cell},family,doses=(int(dose),))
                state['cells'].update(cells)
                state['history'].append(deepcopy(cells))
                state['attempts'].append(dict(iteration=iteration,attempt=attempt))
                m.review.save(path,state)
                print(w['reference'],{d:(round(c['actual_percent'],1),c['status']) for d,c in cells.items()},flush=True)
            if not pending():break
            if state['batches']>=5 or state['proposed_count']>=40:break
            n.generate_candidates(client,w,source,family,state,folder/'generation',
                min(8,40-state['proposed_count']),doses=tuple(pending()),writer_prompt=writer_prompt)
            m.review.save(path,state)
            print(w['reference'],'candidate batch',state['batches'],'proposed',state['proposed_count'],flush=True)
    state['stop_reason']='all_requested_doses_passed' if not pending() else 'bounded_generation_and_review_exhausted'
    assert all(state['cells'][d]==cell for d,cell in fixed['cells'].items())
    all_doses=tuple(sorted(set(target_doses)|{int(d) for d in fixed['cells']}))
    def contains(low,high):
        a=state['cells'][str(low)]['edits'];b=state['cells'][str(high)]['edits']
        return set(n.signature(a))<=set(n.signature(b)) if family=='mistranslation' else preview.deleted_positions(a)<=preview.deleted_positions(b)
    state['nesting']={f'{low}-{high}':contains(low,high) for low,high in zip(all_doses,all_doses[1:])}
    m.review.save(path,state)
    return state


def report(data):
    family=data.get('family','omission')
    mis=family=='mistranslation'
    doses=tuple(data.get('display_doses',ALL_DOSES))
    retained=set(data.get('retained_doses',(15,30)))
    title=data.get('title','10 omission questions · 5%, 10%, 15%, 20%, 25%, 30%')
    intro=data.get('intro','The same ten questions appear at all six doses, with passages and unchanged answer choices.')
    note=data.get('note','New: 5%, 10%, 20% and 25%. The existing 15% and 30% versions are unchanged.')
    adjacent={f'{a}-{b}' for a,b in zip(doses,doses[1:])}
    rate_text=('Rates count clean Chinese content characters in normalized substitution spans, not the percentage of false facts or visibly changed characters. ' if mis else 'Rates count deleted clean Chinese content characters; ')
    check_text=('All six required checks apply, including written gender agreement. ' if mis else 'The current five required checks apply at every new dose. ')
    nesting_text=('Nesting requires the same source spans AND replacement wording to persist. ' if mis else 'Nesting compares deleted source positions. ')
    flags_text=('contradictions, unclear references or interacting substitutions.' if mis else 'ambiguity, recoverable information or additional semantic distortion.')
    labels={'pass':'Pass','pass_with_flags':'Pass with flags','held':'Held: uncertain',
        'rejected':'Held: failed check','held_dose':'Held: dose'}
    p=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>'+escape(title)+'</title>',
       '<style>body{max-width:1400px;margin:30px auto;padding:0 22px;font:16px/1.65 system-ui;color:#203a43}'
       'h1{line-height:1.2}h2{margin-top:2.4em}.note{background:#edf4f2;border-left:4px solid #398479;padding:16px}'
       '.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card{border:1px solid #d3dfdc;border-radius:8px;background:#f4f7f5;padding:20px}'
       '.held{border-top:5px solid #a34f2c}.zh{font-size:18px}small{color:#4e6870}li{margin:.4em 0}'
       'details{margin:14px 0}summary{cursor:pointer;font-weight:600}del{background:#ffe3d7;color:#8a301e}ins{background:#dcefe5;color:#145a3d;text-decoration:none}'
       'table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #d2dfd9;padding:8px;text-align:left}'
       '.scroll{overflow:auto}select{padding:8px;font:inherit}a{color:#0d637c}.hidden{display:none}.single{grid-template-columns:1fr}'
       '@media(max-width:850px){.grid{grid-template-columns:1fr}}</style></head><body>',
       '<h1>'+escape(title)+'</h1>',
       '<p>'+escape(intro)+'</p>',
       '<div class="note">'+escape(note)+' '
       +rate_text+'Tolerance is ±2 percentage points. '+check_text+
       'No manual passage or QA repairs were inserted. Local drafts; not published.</div>',
       '<p><b>This collection is not guaranteed to be nested.</b> The selector prefers containment in a higher-dose version '
       'where possible, but can select independently to keep the fixed comparisons and meet review requirements. '
       +nesting_text+'Actual containment across adjacent doses is shown below. Pass with flags meets all required checks '
       'while recording effects such as '+flags_text+'</p>',
       '<table><tr><th>Dose</th><th>Pass</th><th>Pass with flags</th><th>Held</th></tr>']
    for dose in doses:
        counts=Counter(w['cells'][str(dose)]['status'] for w in data['windows'])
        p.append(f'<tr><td>{dose}%'+(' · retained' if dose in retained else '')+'</td>'+''.join(
            f'<td>{x}</td>' for x in (counts['pass'],counts['pass_with_flags'],sum(v for k,v in counts.items() if k not in n.PASS)))+'</tr>')
    p.append('</table><h2>Every window</h2><div class="scroll"><table><tr><th>Window</th>'+''.join(f'<th>{d}%</th>' for d in doses)+'<th>Non-nested adjacent pairs</th></tr>')
    for i,w in enumerate(data['windows'],1):
        p.append(f'<tr><td><a href="#q{i}">'+escape(w['reference'])+'</a></td>')
        for d in doses:
            c=w['cells'][str(d)];p.append(f'<td>{c["actual_percent"]:.1f}%<br><small>'+labels[c['status']]+'</small></td>')
        p.append('<td>'+escape(', '.join(k.replace('-','% → ')+'%' for k,v in w['nesting'].items() if k in adjacent and not v) or 'None')+'</td></tr>')
    p.append('</table></div><p><label>Show dose <select id="dose"><option value="all">All doses</option>'+''.join(f'<option value="{d}">{d}% only</option>' for d in doses)+'</select></label></p>')
    for i,w in enumerate(data['windows'],1):
        q=w['qa'];p.append(f'<h2 id="q{i}">{i}. '+escape(w['reference'])+'</h2><div class="grid">')
        for d in doses:
            c=w['cells'][str(d)];p.append('<article data-dose="'+str(d)+'" class="card'+(' held' if c['status'] not in n.PASS else '')+f'"><h3>{d}% '+family+f'</h3><p><small>{c["actual_percent"]:.1f}% actual · {c["affected_chars"]}/{w["clean_content_chars"]} source characters · '+labels[c['status']]+'</small></p>')
            if c['status']=='held_dose' and not c['edits']:
                p.append('<p><b>No valid defective version was built at this dose.</b> The clean passage below is shown only for reference.</p>')
            p.extend('<p class="zh"><small>'+escape(v)+'</small>　'+escape(t)+'</p>' for v,t in c['verses'].items())
            p.append('<h3 class="zh">'+escape(q['question'])+'</h3><ol type="A" class="zh">'+''.join('<li>'+escape(x)+'</li>' for x in q['choices'])+'</ol>')
            if mis:
                p.append('<details><summary>Substitutions: clean → shown</summary><ul>'+''.join('<li>'+escape(e['verse']+' · '+e['before']+' → '+e['after'])+'</li>' for e in c['edits'])+'</ul>')
            else:
                p.append('<details><summary>Removed text and unit counts</summary><p>'+escape(str(c['unit_counts']))+'</p>')
            for verse,body in w['clean'].items():
                start=0;parts=[]
                for e in sorted((e for e in c['edits'] if e['verse']==verse),key=lambda e:e['start']):
                    parts.extend([escape(body[start:e['start']]),'<del>'+escape(e['before'])+'</del>'])
                    if mis:parts.append('<ins>'+escape(e['after'])+'</ins>')
                    start=e['start']+len(e['before'])
                parts.append(escape(body[start:]));p.append('<p class="zh">'+escape(verse)+'　'+''.join(parts)+'</p>')
            p.append('</details><details><summary>Review findings</summary><p>'+escape(c.get('review',{}).get('reason',c.get('reason','')))+ '</p><p>'+escape(', '.join(c.get('flags',[])))+'</p></details></article>')
        key=q['correct'];p.append('</div><details><summary>Clean-source answer key</summary><p>'+escape(key+'. '+q['choices'][ord(key)-ord('A')])+ '</p><p>The key is for the clean passage. Defects can remove or alter its supporting evidence; this is not a separate answerability judgment for each defective passage.</p></details>')
    p.append('<script>document.getElementById("dose").addEventListener("change",e=>{const v=e.target.value;document.querySelectorAll("[data-dose]").forEach(x=>x.classList.toggle("hidden",v!=="all"&&x.dataset.dose!==v));document.querySelectorAll(".grid").forEach(x=>x.classList.toggle("single",v!=="all"));});</script></body></html>')
    return ''.join(p)


def run(folder,report_path,workers):
    os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1');m.load_dotenv(m.ROOT/'.env')
    preview_path=m.ROOT/'evaluation/runs/sol_omission_preview10_2026-11-19/examples.json'
    source_path=m.ROOT/'evaluation/runs/sol_nested_defects_all66_2026-11-19/all_windows.json'
    fixed=m.review.read(preview_path);original=m.review.read(source_path)['families']['omission']['windows']
    manifest=m.review.read(m.MANIFEST);sources=m.english_by_passage();banks=[(p.name,m.review.read(p)) for p in m.BANKS]
    lookup={w['id']:w for pid in sources for w in m.load_candidates(manifest,banks,pid,sources)[0]}
    config=dict(preview_sha256=sha256(preview_path.read_bytes()).hexdigest(),source_sha256=sha256(source_path.read_bytes()).hexdigest(),
        selected_ids=[w['id'] for w in fixed['windows']],new_doses=list(NEW_DOSES),published=False)
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'configuration.json').exists() and m.review.read(folder/'configuration.json')!=config:raise ValueError('Changed extension inputs')
    m.review.save(folder/'configuration.json',config);errors={}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks={executor.submit(build_one,lookup[row['id']],row,original[row['id']],sources[lookup[row['id']]['passage_id']],folder/m.clean_digest(row['id'])[:16]):row['id'] for row in fixed['windows']}
        for task in as_completed(tasks):
            try:task.result()
            except Exception as exc:errors[tasks[task]]=type(exc).__name__+': '+str(exc)[:500]
    result=dict(configuration=config,windows=[],execution_errors=errors,published=False)
    for row in fixed['windows']:
        state=m.review.read(folder/m.clean_digest(row['id'])[:16]/'preview.json')
        result['windows'].append(dict(id=row['id'],reference=row['reference'],qa=row['qa'],clean=row['clean'],
            clean_content_chars=row['clean_content_chars'],**state))
    m.review.save(folder/'examples.json',result)
    if errors:raise RuntimeError(str(errors))
    report_path.write_text(report(result),encoding='utf-8');print('REPORT',report_path,flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--workers',type=int,choices=(1,2,3,4),default=3)
    a=p.parse_args();run(a.output,a.report,a.workers)
