"""Build 5/10/15/20/25% omission previews for every window in one passage."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path

from evaluation.scripts.pipeline import extend_omission_preview as x

n=x.n
m=x.m
DOSES=(5,10,15,20,25)
WRITER_PROMPT=x.WRITER_PROMPT.replace('(5%, 10%, 20%, 25%)','(5%, 10%, 15%, 20%, 25%)').replace(
    'Existing 15% and 30% comparison passages stay unchanged.',
    'Existing reviewed comparison passages stay unchanged; generate candidates only for the supplied unresolved targets.')


def check_cell(w,pool,dose,cell):
    if cell['status'] not in n.PASS:raise ValueError('Only passed versions may be reused')
    if any(cell.get('checks',{}).get(k)!='yes' for k in m.review.ClauseChecks.model_fields):
        raise ValueError('Required review check missing')
    replay=n.materialize(w,pool,cell['selected_ids'],'omission',dose)
    if any(replay[k]!=cell[k] for k in ('verses','edits','affected_chars','actual_percent')):
        raise ValueError('Saved omission fails exact replay')
    n.validate_chain(w,{str(dose):cell},'omission',doses=(dose,))


def run(passage_id,folder,report_path,workers=3):
    os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1');m.load_dotenv(m.ROOT/'.env')
    source_path=m.ROOT/'evaluation/runs/sol_nested_defects_all66_2026-11-19/all_windows.json'
    preview_path=m.ROOT/'evaluation/runs/sol_omission_preview10_5_to_30_2026-11-19/examples.json'
    qa_path=m.DATA/'qa/reviewed122_sol/zh.json'
    original=m.review.read(source_path)['families']['omission']['windows']
    previous={r['id']:r for r in m.review.read(preview_path)['windows']}
    manifest=m.review.read(m.MANIFEST);sources=m.english_by_passage();banks=[(p.name,m.review.read(p)) for p in m.BANKS]
    windows=m.load_candidates(manifest,banks,passage_id,sources)[0]
    qas={q['id']:q for q in m.review.read(qa_path)}
    prepared=[];reused=0
    for w in windows:
        base=deepcopy(original[w['id']]);fixed={'cells':{'30':deepcopy(base['cells']['30'])}}
        assert w['question']==qas[w['id']]['question'] and w['clean']==base['clean']
        if w['id'] in previous:
            old=previous[w['id']]
            assert old['clean']==w['clean'] and old['qa']==qas[w['id']]
            lookup={c['id']:c for c in base['pool']}
            for c in old['pool']:
                if c['id'] not in lookup:base['pool'].append(deepcopy(c));lookup[c['id']]=c
            for dose in DOSES:
                c=old['cells'].get(str(dose))
                if c and c['status'] in n.PASS:
                    check_cell(w,base['pool'],dose,c)
                    fixed['cells'][str(dose)]=deepcopy(c);reused+=1
            base['history']+=deepcopy(old['history'])
        check_cell(w,base['pool'],30,fixed['cells']['30'])
        prepared.append((w,fixed,base))
    config=dict(passage_id=passage_id,targets=list(DOSES),selected_ids=[w['id'] for w in windows],
        source_sha256=sha256(source_path.read_bytes()).hexdigest(),preview_sha256=sha256(preview_path.read_bytes()).hexdigest(),
        qa_sha256=sha256(qa_path.read_bytes()).hexdigest(),reused_target_versions=reused,published=False)
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'configuration.json').exists() and m.review.read(folder/'configuration.json')!=config:
        raise ValueError('One-passage preview inputs changed')
    m.review.save(folder/'configuration.json',config);errors={}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks={executor.submit(x.build_one,w,fixed,base,sources[passage_id],folder/m.clean_digest(w['id'])[:16],
            target_doses=DOSES,writer_prompt=WRITER_PROMPT):w['id'] for w,fixed,base in prepared}
        for task in as_completed(tasks):
            try:task.result()
            except Exception as exc:errors[tasks[task]]=type(exc).__name__+': '+str(exc)[:500]
    title=windows[0]['reference'].split(':')[0]
    result=dict(configuration=config,title=f'{title} · {len(windows)} windows · 5%–25% omission',
        intro=f'All {len(windows)} active from-scratch windows in this passage, each at 5%, 10%, 15%, 20% and 25% omission. Questions and answer choices are unchanged.',
        note=f'{reused} target-dose versions were reused after verification. The other {len(windows)*len(DOSES)-reused} were assembled and reviewed in this run. Existing 30% comparison versions remain unchanged.',
        display_doses=list(DOSES),retained_doses=[],windows=[],execution_errors=errors,published=False)
    for w,fixed,base in prepared:
        state=m.review.read(folder/m.clean_digest(w['id'])[:16]/'preview.json')
        assert all(state['cells'][d]==c for d,c in fixed['cells'].items())
        result['windows'].append(dict(id=w['id'],reference=w['reference'],qa=qas[w['id']],clean=w['clean'],
            clean_content_chars=w['clean_content_chars'],**state))
    m.review.save(folder/'examples.json',result)
    if errors:raise RuntimeError(str(errors))
    summary=dict(counts={str(d):dict(Counter(w['cells'][str(d)]['status'] for w in result['windows'])) for d in DOSES},
        complete_windows=sum(all(w['cells'][str(d)]['status'] in n.PASS for d in DOSES) for w in result['windows']),
        fully_nested_windows=sum(all(w['nesting'][f'{a}-{b}'] for a,b in zip(DOSES,DOSES[1:])) for w in result['windows']),
        held=[dict(reference=w['reference'],dose=d,cell=w['cells'][str(d)]) for w in result['windows'] for d in DOSES if w['cells'][str(d)]['status'] not in n.PASS])
    result['summary']=summary;m.review.save(folder/'examples.json',result);m.review.save(folder/'summary.json',summary)
    report_path.write_text(x.report(result),encoding='utf-8');print('REPORT',report_path,flush=True)
    print(summary['counts'],flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--passage-id',default='t1_1kgs13')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--workers',type=int,choices=(1,2,3,4),default=3)
    a=p.parse_args();run(a.passage_id,a.output,a.report,a.workers)
