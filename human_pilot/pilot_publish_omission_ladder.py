"""Publish approved research windows in a separate namespace, without pilot plans."""
import argparse
from hashlib import sha256
import json
import sys
from uuid import NAMESPACE_URL, uuid5
from pathlib import Path

from _bootstrap import use_platform
use_platform()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, selectinload
from eten_shared.database import get_database_url
from eten_shared.models import ExperimentPassage, ExperimentPassageVerse
import pilot_publish_omission_mixture as live
from evaluation.scripts.pipeline import release_omission_ladder as bank

PREFIX='sol_omission205030_ladder_v1/'
RELEASE_SHA256='07c0cfbfcd8ff665fb7185b011ae03969d27c725dba1258cade6532e20bed570'


def expected_rows(release):
    bank.validate(release);result={}
    for w in release['windows']:
        for condition,c in w['conditions'].items():
            identity='eten:research:'+release['release']+':'+w['id']+':'+condition
            pid=str(uuid5(NAMESPACE_URL,identity))
            result[pid]=dict(id=pid,source_passage_id=PREFIX+w['id'],condition=condition,
                language='zh',chapter=int(next(iter(w['clean'])).split(':')[0]),
                name='Sol approved research '+condition,passage_reference=w['reference'],
                passage_text='\n'.join(f'{v} {t}' for v,t in c['verses'].items()),
                verses=[dict(id=str(uuid5(NAMESPACE_URL,identity+':'+v)),verse_number=v,position=i,text=t)
                        for i,(v,t) in enumerate(c['verses'].items(),1)])
    return result


def snapshot(db):
    rows=db.scalars(select(ExperimentPassage).options(selectinload(ExperimentPassage.verses)).where(
        ExperimentPassage.source_passage_id.startswith(PREFIX,autoescape=True))).all()
    return {p.id:dict(id=p.id,source_passage_id=p.source_passage_id,condition=p.condition,
        language=p.language,chapter=p.chapter,name=p.name,passage_reference=p.passage_reference,
        passage_text=p.passage_text,verses=[dict(id=v.id,verse_number=v.verse_number,position=v.position,text=v.text)
            for v in p.verses]) for p in rows}


def publish(db,release,apply=False,preview=None):
    if db.get_bind().dialect.name=='postgresql':
        if apply:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text('SELECT pg_advisory_xact_lock(742908123)'))
        else:db.execute(text('SET TRANSACTION READ ONLY'))
    expected=expected_rows(release);before=snapshot(db)
    if set(before)-set(expected):raise ValueError('Unknown content in versioned research namespace')
    if any(row!=expected[pid] for pid,row in before.items()):raise ValueError('Published immutable text differs')
    pilot_before=live.digest(live.snapshot(db)[0]);qa_before=live.immutable_content(db)
    # Check the already-published participant doses against the actual live bank.
    pilot_release=json.loads(live.RELEASE.read_text())
    _,_,_,_,pilot_changes,_=live.prepare(db,pilot_release)
    if pilot_changes:raise ValueError('Participant 15/30 passages are not the verified published release')
    audit=dict(release=release['release'],release_sha256=live.digest(release),
        expected_sha256=live.digest(expected),before_sha256=live.digest(before),
        approved_variants=len(expected),held_variants=sum(len(w['held_conditions']) for w in release['windows']),
        existing=len(before),create=len(expected)-len(before),namespace=PREFIX,
        pilot_passages_sha256=pilot_before,qa_and_windows_sha256=qa_before,
        human_conditions_unchanged=True,participant_assignments_modified=0)
    if apply:
        if preview is None or any(preview[k]!=audit[k] for k in ('release_sha256','expected_sha256','before_sha256','pilot_passages_sha256','qa_and_windows_sha256')):
            raise ValueError('Missing or stale publication preview')
        for pid,row in expected.items():
            if pid in before:continue
            fields=dict(row);verses=fields.pop('verses');p=ExperimentPassage(**fields)
            p.verses=[ExperimentPassageVerse(**v) for v in verses];db.add(p)
        db.flush()
        if snapshot(db)!=expected:raise ValueError('Published research content failed readback')
        if live.digest(live.snapshot(db)[0])!=pilot_before or live.immutable_content(db)!=qa_before:
            raise ValueError('Pilot content changed during publication')
    return dict(audit,applied=apply)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--audit',type=Path,required=True)
    ap.add_argument('--apply',action='store_true');ap.add_argument('--preview',type=Path)
    args=ap.parse_args();data=bank.DEST.read_bytes()
    if sha256(data).hexdigest()!=RELEASE_SHA256:raise ValueError('Research release differs from its pinned hash')
    release=json.loads(data);preview=json.loads(args.preview.read_text()) if args.preview else None
    engine=create_engine(get_database_url(),connect_args={'connect_timeout':10})
    with Session(engine) as db:
        audit=publish(db,release,args.apply,preview)
        if args.apply:db.commit()
        else:db.rollback()
    if args.apply:
        with Session(engine) as db:
            db.execute(text('SET TRANSACTION READ ONLY'))
            if snapshot(db)!=expected_rows(release):raise ValueError('Post-commit readback mismatch')
            audit['fresh_connection_readback_verified']=True
    live.dump(args.audit,audit);print(json.dumps(audit,ensure_ascii=False))
