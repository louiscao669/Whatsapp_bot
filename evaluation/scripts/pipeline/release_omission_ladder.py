"""Freeze approved omission windows; held variants are metadata, never stimuli."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from evaluation.scripts.pipeline import rebuild_omission_ladder as pipeline

ROOT=pipeline.m.ROOT
RUN=ROOT/'evaluation/runs/sol_omission_mix205030_all65_5_to_60_2026-11-21'
DEST=ROOT/'evaluation/datasets/passages/sol_scratch65_omission_205030_ladder_v1.json'
QA=ROOT/'evaluation/datasets/qa/reviewed122_sol/zh.json'
RELEASE='sol-scratch65-omission-205030-ladder-v1'


def build():
    result=json.loads((RUN/'mixture.json').read_text())
    if not result.get('stop_reason') or not all(r['review_complete'] for r in result['rounds']):
        raise ValueError('Review is incomplete')
    pipeline.verify(result)
    for path,digest in result['configuration']['inputs'].items():
        if sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed')
    qas={q['id']:q for q in json.loads(QA.read_text())};windows=[]
    for w in result['windows']:
        if qas[w['id']]['source']!='Hard77' or qas[w['id']]['verses']!=w['clean']:
            raise ValueError('Question/window identity changed')
        cs=result['rounds'][-1]['cells'][w['id']]
        windows.append(dict(deepcopy(w),conditions={f'omission{d}':deepcopy(c) for d,c in cs.items()
            if c['status'] in pipeline.n.PASS},held_conditions={f'omission{d}':dict(status=c['status'],
            actual_percent=c['actual_percent'],reason=c.get('reason') if c['status']=='held_dose' else c['review']['reason'])
            for d,c in cs.items() if c['status'] not in pipeline.n.PASS}))
    release=dict(release=RELEASE,release_date='2026-11-22',language='zh',
        purpose='Approved research stimuli; does not alter human-pilot conditions or assignment plans',
        doses=list(pipeline.DOSES),target_mix=dict(word=20,phrase=50,clause=30),
        mix_basis='deletion_occurrences_pooled_per_dose',frozen_doses=[15,30],nested_doses=[30,40,50,60],
        excluded_held=result['configuration']['excluded_held'],windows=windows,
        accepted_summary=result['rounds'][-1]['accepted_summary'],
        provenance={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in
            [RUN/'mixture.json',RUN/'verification.json',QA,pipeline.RELEASE]})
    validate(release)
    if DEST.exists() and json.loads(DEST.read_text())!=release:raise ValueError('Immutable release already differs')
    pipeline.m.review.save(DEST,release)
    return release


def validate(release):
    if release['release']!=RELEASE or release['doses']!=list(pipeline.DOSES):raise ValueError('Unexpected release')
    if len(release['windows'])!=65 or len({w['id'] for w in release['windows']})!=65:raise ValueError('Wrong roster')
    for w in release['windows']:
        if set(w['conditions']) & set(w['held_conditions']):raise ValueError('Held stimulus exposed')
        if set(w['conditions'])|set(w['held_conditions'])!={f'omission{d}' for d in pipeline.DOSES}:
            raise ValueError('Missing condition disposition')
        for condition,c in w['conditions'].items():
            dose=int(condition.removeprefix('omission'))
            if c['status'] not in pipeline.n.PASS or set(c['checks'].values())!={'yes'}:
                raise ValueError('Unapproved stimulus')
            if set(c['checks'])!=set(pipeline.m.review.ClauseChecks.model_fields):raise ValueError('Missing check')
            if c['target_percent']!=dose or abs(c['actual_percent']-dose)>2+1e-9:raise ValueError('Wrong dose')
            if set(c['verses'])!=set(w['clean']):raise ValueError('Missing verse')
    if sum(len(w['conditions']) for w in release['windows'])!=551:raise ValueError('Approved scope changed')


if __name__=='__main__':
    build();print(DEST);print(sha256(DEST.read_bytes()).hexdigest())
