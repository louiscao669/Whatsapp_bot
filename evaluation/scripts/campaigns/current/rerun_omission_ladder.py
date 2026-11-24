"""Run the original seven reader settings on the approved 20/50/30 release."""
import argparse
from collections import Counter
import fcntl
from hashlib import sha256
import json
from pathlib import Path
import shutil

from dotenv import load_dotenv
import requests
from evaluation.scripts.campaigns.current import run_window_dose_readers as runner
from evaluation.scripts.pipeline import release_omission_ladder as bank

old=runner.old
ROOT=bank.ROOT
RUN=ROOT/'evaluation/runs/sol_omission205030_readers_2026-11-22'
REPORT=ROOT/'evaluation/reports/sol_omission205030_readers_2026-11-22'


def stimuli_from_release(release,qas):
    bank.validate(release);lookup={q['id']:q for q in qas};stimuli=[];held=[]
    for w in release['windows']:
        q=lookup[w['id']]
        if q['source']!='Hard77' or q['verses']!=w['clean']:raise ValueError('QA/window mismatch')
        stimuli.append(dict(item=w['id'],reference=w['reference'],qa=q,family='clean',dose=0,
            actual_percent=0,review_status='clean',passage=' '.join(w['clean'].values()),verses=w['clean']))
    for dose in release['doses']:
        condition=f'omission{dose}'
        for w in release['windows']:
            if condition in w['held_conditions']:
                held.append(dict(item=w['id'],reference=w['reference'],family='omission',dose=dose,**w['held_conditions'][condition]));continue
            c=w['conditions'][condition]
            stimuli.append(dict(item=w['id'],reference=w['reference'],qa=lookup[w['id']],family='omission',dose=dose,
                actual_percent=c['actual_percent'],review_status=c['status'],
                passage=' '.join(c['verses'].values()),verses=c['verses'],edits=c['edits']))
    if len(stimuli)!=616 or len(held)!=34:raise ValueError('Release scope changed')
    return stimuli,held


def prepare():
    release=old.read(bank.DEST);qas=old.read(bank.QA);stimuli,held=stimuli_from_release(release,qas)
    with requests.Session() as session:
        response=session.get(old.LOCAL+'/api/tags',timeout=20);response.raise_for_status();inventory=response.json()['models']
        response=session.get(old.LOCAL+'/api/version',timeout=20);response.raise_for_status();version=response.json()
    names={m for m,_ in old.MODELS};weights={x['name']:x['digest'] for x in inventory if x['name'] in names}
    historical=old.read(old.RUN/'design.json')['models']
    if set(weights)!=names or any(weights[m]!=historical[m] for m in names):raise ValueError('Reader weights changed/missing')
    jobs=runner.request_jobs(stimuli,weights)
    sources=[p for p in sorted((ROOT/'evaluation/runs').glob('sol_*_window_dose_readers_2026-11-19')) if (p/'design.json').exists()]
    if len(sources)!=10:raise ValueError('Expected the ten previous passage campaigns')
    reuse={};(RUN/'answers').mkdir(parents=True,exist_ok=True);(RUN/'mappings').mkdir(exist_ok=True)
    for job in jobs:
        for source in sources:
            path=source/'answers'/(job['signature']+'.json')
            if not path.exists():continue
            record=old.read(path)
            if record['request']!=job['body'] or record['model_digest']!=job['model_digest']:
                raise ValueError('Cached request differs')
            dest=RUN/'answers'/path.name
            if dest.exists() and dest.read_bytes()!=path.read_bytes():raise ValueError('Conflicting cached answer')
            if not dest.exists():shutil.copy2(path,dest)
            reuse[job['signature']]=dict(source=str(path.relative_to(ROOT)),sha256=sha256(path.read_bytes()).hexdigest())
            break
    for source in sources:
        for path in (source/'mappings').glob('*.json'):
            dest=RUN/'mappings'/path.name
            if not dest.exists():shutil.copy2(path,dest)
    files=[bank.DEST,bank.QA,Path(__file__),Path(runner.__file__),Path(old.__file__),Path(old.gen.__file__),Path(old.small.__file__)]
    design=dict(version='omission205030_reader_rerun_v1',release=release['release'],
        question_ids=[w['id'] for w in release['windows']],doses=release['doses'],families=['omission'],
        models=[dict(model=m,thinking=t,label=runner.LABELS[i]) for i,(m,t) in enumerate(old.MODELS)],
        weights=weights,inference=old.CONFIG,ollama_version=version,
        input_sha256={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files},
        stimuli_sha256=old.digest(stimuli),requests_sha256=old.digest(jobs),expected=len(jobs),
        reused_requests=len(reuse),new_requests=len(jobs)-len(reuse),excluded_stimuli=held,
        scoring=dict(key='clean-source reference answer',abstention='E',mapper=old.JUDGE,
            mapper_scope='Original unmatched nonempty answers from the four primary reader settings only',
            mapper_input='Response and choices only; no passage/question/key',random_fallback=False),
        protocol='Original reader-specific prompts, parser families, model weights, temperature zero, '
            '8192 context and 2500 generated-token cap. Fresh conversation per request. '
            'Exact unchanged requests reuse prior responses; changed requests run again. Thinking traces retained.',
        excluded_held=release['excluded_held'],published_stimuli=True)
    if (RUN/'design.json').exists() and old.read(RUN/'design.json')!=design:raise ValueError('Frozen run differs')
    old.save(RUN/'design.json',design);old.save(RUN/'stimuli.json',stimuli);old.save(RUN/'requests.json',jobs)
    old.save(RUN/'reuse_manifest.json',reuse)
    before=[];before_sources={}
    for source in sources:
        p=ROOT/'evaluation/reports'/source.name/'results.json'
        before_sources[str(p.relative_to(ROOT))]=sha256(p.read_bytes()).hexdigest()
        before.extend(r for r in old.read(p) if r['family'] in ('clean','omission') and r['item'] in design['question_ids'])
    old.save(RUN/'before_results.json',before);old.save(RUN/'before_sources.json',before_sources)
    print('PREPARED',json.dumps({k:design[k] for k in ['expected','reused_requests','new_requests']}),flush=True)
    return design,jobs


def collect(design,jobs):
    rows,summaries=runner.results(RUN,design,jobs)
    summaries=[s for s in summaries if s['family'] in ('clean','omission')]
    if len(rows)!=4312 or len(summaries)!=70:raise ValueError('Incomplete campaign')
    REPORT.mkdir(parents=True,exist_ok=True)
    old.save(REPORT/'results.json',rows);old.save(REPORT/'summary.json',summaries)
    old.save(REPORT/'excluded_stimuli.json',design['excluded_stimuli'])
    old.save(RUN/'verification.json',dict(observations=len(rows),expected=design['expected'],
        held_stimuli_excluded=34,held_officer_question_excluded=True,source_hashes_unchanged=True,
        model_weights_pinned=True,raw_responses_saved=True,thinking_traces_saved=True,
        reused_requests=design['reused_requests'],new_requests=design['new_requests'],
        outcomes=dict(Counter(r['outcome'] for r in rows))))
    old.save(RUN/'state.json',dict(status='complete',completed=len(rows),expected=len(jobs)))
    print('COLLECTED',len(rows),'responses',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('stage',choices=['prepare','read','map','collect','all'])
    args=ap.parse_args();RUN.mkdir(parents=True,exist_ok=True);load_dotenv(ROOT/'.env')
    with (RUN/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        design,jobs=prepare() if args.stage in ('prepare','all') else (old.read(RUN/'design.json'),old.read(RUN/'requests.json'))
        if args.stage in ('read','all'):runner.read_all(RUN,design,jobs)
        if args.stage in ('map','all'):runner.map_unmatched(RUN,jobs)
        if args.stage in ('collect','all'):collect(design,jobs)
