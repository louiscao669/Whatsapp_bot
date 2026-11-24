"""Expand the approved five-dose preview workflow to all 66 active windows."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
from html import escape
from math import ceil, floor
import os
from pathlib import Path

from evaluation.scripts.pipeline import build_passage_omission_preview as omission
from evaluation.scripts.pipeline import build_passage_mistranslation_preview as mistranslation

x = omission.x
n, m = x.n, x.m
DOSES = omission.DOSES
DRIVERS = {'omission': omission, 'mistranslation': mistranslation}
SOURCE = m.ROOT / 'evaluation/runs/sol_nested_defects_all66_2026-11-19/all_windows.json'
REUSE = {
    'omission': [
        m.ROOT / 'evaluation/runs/sol_omission_preview10_5_to_30_2026-11-19/examples.json',
        m.ROOT / 'evaluation/runs/sol_omission_1kgs13_5_to_25_2026-11-19/examples.json'],
    'mistranslation': [
        m.ROOT / 'evaluation/runs/sol_mistranslation_1kgs13_5_to_25_2026-11-19/examples.json']}


def merge_reuse(w, qa, base, rows, driver):
    """Reuse only current-source, fully reviewed versions; retain atomic bundles."""
    base = deepcopy(base)
    fixed = {'cells': {'30': deepcopy(base['cells']['30'])}}
    if w['clean'] != base['clean'] or w['question'] != qa['question']:
        raise ValueError('Current source or question differs from baseline')
    for old in rows:
        if old['clean'] != w['clean'] or old['qa'] != qa:
            raise ValueError('Previously reviewed source or QA changed')
        pool = {c['id']: c for c in base['pool']}
        for c in old['pool']:
            if c['id'] in pool:
                prior = pool[c['id']]
                if any(prior.get(k) != c.get(k) for k in ('edits', 'requires', 'chars', 'kinds')):
                    raise ValueError('Reused candidate ID has different edits or constraints')
            else:
                base['pool'].append(deepcopy(c)); pool[c['id']] = c
        base['history'].extend(deepcopy(old.get('history', [])))
        for dose in DOSES:
            cell = old['cells'].get(str(dose))
            if not cell or cell['status'] not in n.PASS:
                continue
            driver.check_cell(w, base['pool'], dose, cell)
            if str(dose) in fixed['cells'] and fixed['cells'][str(dose)] != cell:
                raise ValueError('Two reused reviewed versions disagree')
            fixed['cells'][str(dose)] = deepcopy(cell)
    for dose, cell in fixed['cells'].items():
        driver.check_cell(w, base['pool'], int(dose), cell)
        for bad in base.get('baseline', {}).get('forbidden_candidate_sets', []):
            if set(bad) <= set(cell['selected_ids']):
                raise ValueError('Reused version contains a forbidden combination')
    return fixed, base


def prepare():
    manifest = m.review.read(m.MANIFEST)
    sources = m.english_by_passage()
    banks = [(p.name, m.review.read(p)) for p in m.BANKS]
    windows = [w for pid in sources for w in m.load_candidates(manifest, banks, pid, sources)[0]]
    expected = {w['id'] for w in manifest['windows']}
    if len(windows) != 66 or {w['id'] for w in windows} != expected:
        raise ValueError('Expected all 66 active windows exactly once')
    qa_path = m.DATA / 'qa/reviewed122_sol/zh.json'
    qas = {q['id']: q for q in m.review.read(qa_path)}
    original = m.review.read(SOURCE)['families']
    jobs = []
    for family, driver in DRIVERS.items():
        previous = {}
        for path in REUSE[family]:
            for row in m.review.read(path)['windows']:
                previous.setdefault(row['id'], []).append(row)
        for w in windows:
            fixed, base = merge_reuse(w, qas[w['id']], original[family]['windows'][w['id']],
                                     previous.get(w['id'], []), driver)
            jobs.append(dict(family=family, w=w, fixed=fixed, base=base))
    files = [SOURCE, qa_path, m.MANIFEST, *m.BANKS, *(p for paths in REUSE.values() for p in paths)]
    config = dict(targets=list(DOSES), window_ids=[w['id'] for w in windows],
        input_sha256={str(p.relative_to(m.ROOT)): sha256(p.read_bytes()).hexdigest() for p in files},
        bilingual_sources_sha256=m.clean_digest({pid: dict(english=s.english, chinese=s.chinese) for pid,s in sources.items()}),
        prompt_sha256=m.clean_digest([omission.WRITER_PROMPT, mistranslation.WRITER_PROMPT,
                                     n.OMISSION_CANDIDATE_REVIEW, m.COMBINED_REVIEW, n.mr.PROMPT]),
        reused_target_versions=sum(len(j['fixed']['cells'])-1 for j in jobs),
        writer=n.WRITER, reviewer=m.review.JUDGE, tolerance_pp=2, max_batches=5, max_candidates=40,
        published=False, authorization='User requested both families across all 66 windows')
    return windows, sources, qas, jobs, config


def job_key(job):
    return job['family'] + '/' + m.clean_digest(job['w']['id'])[:16]


def verify_state(job, state):
    w, family = job['w'], job['family']
    if not state.get('stop_reason') or any(state['cells'].get(d) != c for d,c in job['fixed']['cells'].items()):
        raise ValueError('Incomplete state or changed frozen comparison')
    for d in DOSES:
        c = state['cells'][str(d)]
        if c['status'] == 'pending_combined_review':
            raise ValueError('Review still pending')
        replay = n.materialize(w, state['pool'], c['selected_ids'], family, d)
        if any(replay[k] != c[k] for k in ('verses','edits','affected_chars','actual_percent')):
            raise ValueError('Final version fails exact replay')
        if c['status'] in n.PASS:
            DRIVERS[family].check_cell(w, state['pool'], d, c)
        for bad in job['base'].get('baseline', {}).get('forbidden_candidate_sets', []):
            if set(bad) <= set(c['selected_ids']):
                raise ValueError('Forbidden combination selected')


def collect(folder, jobs, qas, config, statuses, report_dir):
    result = dict(configuration=config, families={}, execution_errors={k:v['error'] for k,v in statuses.items()
                  if v['status']=='execution_error'}, published=False)
    held = []
    for family in DRIVERS:
        rows = []
        for job in jobs:
            if job['family'] != family or statuses.get(job_key(job), {}).get('status') != 'complete':
                continue
            state = m.review.read(folder/job_key(job)/'preview.json'); verify_state(job, state)
            w = job['w']
            rows.append(dict(id=w['id'], reference=w['reference'], qa=qas[w['id']], clean=w['clean'],
                             clean_content_chars=w['clean_content_chars'], **state))
            for d in DOSES:
                c = state['cells'][str(d)]
                if c['status'] not in n.PASS:
                    reason=c.get('review',{}).get('reason') or c.get('reason','')
                    if c['status']=='held_dose' and not c['edits']:
                        size=w['clean_content_chars']
                        low=ceil((d-2)*size/100);high=floor((d+2)*size/100)
                        smallest=min((p['chars'] for p in state['pool']),default=None)
                        reason=(f'No approved candidate combination fits {d}% ±2 percentage points. '
                                f'This {size}-character window permits {low}–{high} affected characters. '
                                f'The smallest current approved candidate affects {smallest} characters. '
                                'No defective version was built for this target.')
                    held.append(dict(family=family, window_id=w['id'], reference=w['reference'], dose=d,
                        actual_percent=c['actual_percent'], status=c['status'],
                        reason=reason,
                        failed_checks={k:v for k,v in c.get('checks',{}).items() if v!='yes'}))
        reused = sum(len(j['fixed']['cells'])-1 for j in jobs if j['family']==family)
        data = dict(configuration=config, family=family, title=f'All 66 windows · 5%–25% {family}',
            intro='All active from-scratch windows, with five target doses per window. Questions and answer choices are unchanged.',
            note=f'{reused} target versions reused after verification. Existing 30% comparison versions remain unchanged.',
            display_doses=list(DOSES), retained_doses=[], windows=rows, published=False)
        data['summary'] = dict(counts={str(d):dict(Counter(w['cells'][str(d)]['status'] for w in rows)) for d in DOSES},
            complete_windows=sum(all(w['cells'][str(d)]['status'] in n.PASS for d in DOSES) for w in rows),
            fully_nested_windows=sum(all(w['nesting'][f'{a}-{b}'] for a,b in zip(DOSES,DOSES[1:])) for w in rows),
            new_candidates_proposed=sum(w['proposed_count'] for w in rows))
        result['families'][family] = data
        m.review.save(folder/(family+'.json'), data)
        if len(rows)==66:
            (report_dir/f'sol_{family}_all66_5_to_25.html').write_text(x.report(data), encoding='utf-8')
    completed = sum(len(d['windows'])*len(DOSES) for d in result['families'].values())
    result['summary'] = dict(expected=660, completed=completed, pending=660-completed,
        counts={f:d['summary'] for f,d in result['families'].items()}, held=held, published=False)
    m.review.save(folder/'all_windows.json',result);m.review.save(folder/'summary.json',result['summary'])
    return result


def status_report(result):
    p=['<!doctype html><html><head><meta charset="utf-8"><title>All 66 windows · low-dose review</title>',
       '<style>body{font:16px/1.5 system-ui;margin:30px;color:#203a43}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:left}.held{background:#ffe4d6}.flag{background:#fff7db}.pass{background:#e7f5ed}</style></head><body>',
       '<h1>All 66 windows · omission and mistranslation</h1><p>5%, 10%, 15%, 20%, 25%; tolerance ±2 percentage points. Local drafts; not published. Pass with flags meets every required check. Doses need not be nested.</p>']
    for f,data in result['families'].items():
        p.append(f'<h2>{escape(f.title())}</h2><p><a href="sol_{f}_all66_5_to_25.html">Open all passages, questions, edits and review findings</a></p><table><tr><th>Window</th>'+''.join(f'<th>{d}%</th>' for d in DOSES)+'</tr>')
        for i,w in enumerate(data['windows'],1):
            p.append(f'<tr><td><a href="sol_{f}_all66_5_to_25.html#q{i}">{escape(w["reference"])}</a></td>')
            for d in DOSES:
                c=w['cells'][str(d)];css='flag' if c['status']=='pass_with_flags' else 'pass' if c['status']=='pass' else 'held'
                p.append(f'<td class="{css}">{c["actual_percent"]:.1f}%<br>{escape(c["status"].replace("_"," "))}</td>')
            p.append('</tr>')
        p.append('</table>')
    p.append('<h2>Held versions</h2>')
    for h in result['summary']['held']:
        p.append(f'<p><b>{escape(h["reference"])} · {h["family"]} · {h["dose"]}%</b><br>{escape(h["reason"])}<br>{escape(str(h["failed_checks"]))}</p>')
    p.append('</body></html>');return ''.join(p)


def run(folder, report_dir, workers=4, preflight=False):
    os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1');m.load_dotenv(m.ROOT/'.env')
    windows,sources,qas,jobs,config=prepare()
    folder.mkdir(parents=True,exist_ok=True);report_dir.mkdir(parents=True,exist_ok=True)
    path=folder/'configuration.json'
    if path.exists() and m.review.read(path)!=config:raise ValueError('Campaign inputs changed')
    m.review.save(path,config)
    print('PREFLIGHT',len(windows),'windows;',config['reused_target_versions'],'reused; 660 target versions',flush=True)
    if preflight:return
    statuses=m.review.read(folder/'jobs.json') if (folder/'jobs.json').exists() else {}
    def execute(job):
        key=job_key(job);w=job['w']
        if statuses.get(key,{}).get('status')=='complete':
            state=m.review.read(folder/key/'preview.json');verify_state(job,state);return state
        print('START',job['family'],w['reference'],flush=True)
        state=x.build_one(w,job['fixed'],job['base'],sources[w['passage_id']],folder/key,
            target_doses=DOSES,writer_prompt=DRIVERS[job['family']].WRITER_PROMPT,family=job['family'])
        verify_state(job,state);return state
    # Fully reused windows finish immediately; the remaining model jobs share one concurrency bound.
    jobs.sort(key=lambda j:(len(j['fixed']['cells'])<6,j['w']['passage_id'],j['family'],j['w']['id']))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures={executor.submit(execute,j):j for j in jobs}
        for future in as_completed(futures):
            job=futures[future];key=job_key(job)
            try:
                state=future.result()
                statuses[key]=dict(status='complete',family=job['family'],reference=job['w']['reference'],
                    counts=dict(Counter(state['cells'][str(d)]['status'] for d in DOSES)))
            except Exception as exc:
                statuses[key]=dict(status='execution_error',error=type(exc).__name__+': '+str(exc)[:1200])
            m.review.save(folder/'jobs.json',statuses)
            print('FINISHED',job['family'],job['w']['reference'],statuses[key],'; jobs',len(statuses),'of',len(jobs),flush=True)
    # Return to manifest order for stable comparison across reports.
    order={w['id']:i for i,w in enumerate(windows)};jobs.sort(key=lambda j:(j['family'],order[j['w']['id']]))
    result=collect(folder,jobs,qas,config,statuses,report_dir)
    if result['execution_errors']:raise RuntimeError(str(result['execution_errors']))
    if result['summary']['pending']:raise ValueError('Campaign incomplete')
    if prepare()[-1] != config:
        raise ValueError('Source inputs changed during the campaign')
    (report_dir/'sol_defects_all66_5_to_25_status.html').write_text(status_report(result),encoding='utf-8')
    m.review.save(folder/'verification.json',dict(exact_replay=True,all_required_checks_on_passes=True,
        all_132_frozen_30_percent_comparisons_unchanged=True,qa_and_clean_sources_unchanged=True,
        dependencies_and_forbidden_combinations_checked=True,completed_versions=660,published=False))
    print('COMPLETE',result['summary'],flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--report-dir',type=Path,default=m.ROOT/'deliverables')
    p.add_argument('--workers',type=int,choices=(1,2,3,4),default=4);p.add_argument('--preflight',action='store_true')
    a=p.parse_args();run(a.output,a.report_dir,a.workers,a.preflight)
