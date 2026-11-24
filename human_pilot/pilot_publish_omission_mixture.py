"""Publish a reviewed omission-only release without replacing other conditions.

The default is a read-only preview. Application requires the exact saved preview,
and performs a single transaction. Already presented assignments are immutable.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

from _bootstrap import use_platform
use_platform()
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, selectinload
from eten_shared.database import get_database_url
from eten_shared.experiment_plan import SLOTS, SOL_SCRATCH_SET, build_cells
from eten_shared.models import (Assignment, AssignmentDelivery, AnswerReceipt,
    ExperimentPassage, ExperimentPassageVerse, ExperimentPlanCell, ExperimentWindow, ParticipantResponse,
    PilotQuestionTrial, QAItem)

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'evaluation/datasets/passages/sol_scratch65_omission_mix205030_v1.json'
RELEASE_SHA256='d202d159bc92597e2a41bca48e95229e8b5de5785909e53c7b535c735ab48c18'
CONDITIONS=('omission15','omission30')
PREFIX='reviewed122_sol/Hard77/'
CONTENT=re.compile(r'[\w\u3400-\u9fff]')
CHECKS={'information_omitted','fluent','deletion_only','valid_in_context','key_content_removed'}


def digest(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def validate_release(release):
    windows=release['windows']
    if (release['release']!='sol-scratch65-omission-mix205030-v1' or len(windows)!=65
            or len({w['id'] for w in windows})!=65 or release['conditions']!=list(CONDITIONS)
            or release['mix_basis']!='deletion_occurrences_pooled_per_dose'
            or release['target_mix']!={'word':20,'phrase':50,'clause':30}):
        raise ValueError('Unexpected omission release scope')
    totals={c:Counter() for c in CONDITIONS}; occupied=defaultdict(set)
    for w in windows:
        clean=w['clean']; total=sum(len(CONTENT.findall(t)) for t in clean.values())
        if total!=w['clean_content_chars'] or set(w['conditions'])!=set(CONDITIONS):
            raise ValueError('Window denominator or condition scope changed')
        if occupied[w['passage_id']] & set(clean):raise ValueError('Overlapping window verses')
        occupied[w['passage_id']].update(clean)
        for condition,c in w['conditions'].items():
            if c['status'] not in ('pass','pass_with_flags') or set(c['checks'])!=CHECKS or set(c['checks'].values())!={'yes'}:
                raise ValueError('An unapproved variant cannot be published')
            raw=dict(clean); changes=defaultdict(list); removed=0
            for e in c['edits']:
                if e['after'] or not e['before'] or e['verse'] not in clean:raise ValueError('Not a deletion')
                changes[e['verse']].append(e)
            for label,edits in changes.items():
                cursor=0; pieces=[]; body=clean[label]
                for e in sorted(edits,key=lambda e:e['start']):
                    start=e['start']
                    if start<cursor or not body.startswith(e['before'],start):raise ValueError('Invalid or overlapping deletion')
                    pieces.append(body[cursor:start]);cursor=start+len(e['before'])
                    removed+=len(CONTENT.findall(e['before']))
                raw[label]=''.join(pieces)+body[cursor:]
            seen=set()
            for cleanup in c['punctuation_cleanup']:
                label=cleanup['verse']
                if label in seen or raw[label]!=cleanup['before'] or CONTENT.findall(cleanup['before'])!=CONTENT.findall(cleanup['after']):
                    raise ValueError('Cleanup changes lexical content')
                seen.add(label);raw[label]=cleanup['after']
            dose=int(condition.removeprefix('omission'))
            if (raw!=c['verses'] or list(raw)!=list(c['verses']) or any(not CONTENT.search(t) for t in raw.values())
                    or c['affected_chars']!=removed or c['target_percent']!=dose
                    or abs(c['actual_percent']-100*removed/total)>1e-9
                    or abs(100*removed-dose*total)>2*total):
                raise ValueError('Rendered text or dose mismatch')
            totals[condition].update(c['unit_counts'])
    for condition,counts in totals.items():
        if set(counts)-set(release['target_mix']):raise ValueError('Unexpected unit category')
        if any(100*counts[k]!=share*sum(counts.values()) for k,share in release['target_mix'].items()):
            raise ValueError('Pooled mixture differs from the approved 20/50/30 release')
    return {w['id']:w for w in windows}


def snapshot(db):
    passages=db.scalars(select(ExperimentPassage).options(selectinload(ExperimentPassage.verses)).where(
        ExperimentPassage.source_passage_id.startswith('reviewed122_sol/',autoescape=True))).all()
    result={}
    for p in passages:
        result[p.id]=dict(id=p.id,source=p.source_passage_id,condition=p.condition,language=p.language,
            chapter=p.chapter,name=p.name,reference=p.passage_reference,text=p.passage_text,
            verses=[dict(id=v.id,label=v.verse_number,position=v.position,text=v.text) for v in p.verses])
    return result,passages


def overlay(passage,clean,replacements):
    """Restore newly retained verses in source order, preserving all other wording."""
    old={v['label']:v for v in passage['verses']}
    if set(old)-{v['label'] for v in clean['verses']}:raise ValueError('Unknown source verse')
    rows=[]
    for v in clean['verses']:
        label=v['label']
        if label not in old and label not in replacements:continue
        item=dict(old[label]) if label in old else dict(id=str(uuid5(NAMESPACE_URL,
            'eten:'+passage['id']+':'+label)),label=label,text=replacements[label])
        item.update(text=replacements.get(label,item['text']),position=v['position'])
        rows.append(item)
    return dict(passage,verses=rows,text='\n'.join(f'{v["label"].split(":")[-1]} {v["text"]}' for v in rows))


def roster(db):
    return db.execute(select(ExperimentWindow,QAItem).join(QAItem,ExperimentWindow.qa_item_id==QAItem.id).where(
        ExperimentWindow.source_passage_id.startswith(PREFIX,autoescape=True))).all()


def immutable_content(db):
    """Fingerprint question content, delivery boundaries, and Latin-square groups."""
    q=db.execute(select(QAItem.id,QAItem.passage_id,QAItem.form_group_id,QAItem.question_text,
        QAItem.mcq_choices,QAItem.mcq_correct_choice,QAItem.expected_answer,QAItem.review_removed_at,QAItem.active).where(
        QAItem.passage_id.startswith('reviewed122_sol/',autoescape=True)).order_by(QAItem.id)).all()
    w=db.execute(select(ExperimentWindow.id,ExperimentWindow.qa_item_id,ExperimentWindow.content_id,
        ExperimentWindow.source_passage_id,ExperimentWindow.verse_numbers,ExperimentWindow.group_index,
        ExperimentWindow.sequence_index,ExperimentWindow.window_key,ExperimentWindow.window_ordinals).where(
        ExperimentWindow.source_passage_id.startswith('reviewed122_sol/',autoescape=True)).order_by(ExperimentWindow.id)).all()
    return digest([[str(v) if hasattr(v,'isoformat') else v for v in row] for row in q]+[list(row) for row in w])


def assignment_texts(db):
    return {a.id:dict(text=a.passage_text,verses=a.passage_verse_numbers) for a in db.scalars(
        select(Assignment).join(QAItem,QAItem.id==Assignment.qa_item_id).where(
            QAItem.passage_id.startswith('reviewed122_sol/',autoescape=True)))}


def prepare(db,release):
    expected=validate_release(release); before,objects=snapshot(db)
    by_source={(p['source'],p['condition'],p['language']):p for p in before.values()}
    windows=roster(db);active={w.content_id:(w,q) for w,q in windows if q.review_removed_at is None}
    if len(active)!=65 or set(active)!=set(expected):raise ValueError('Hosted active roster differs from the 65 reviewed windows')
    if {w.content_id for w,q in windows if q.review_removed_at is not None}!=set(release['excluded_held']):
        raise ValueError('Hosted held roster changed')
    replacements=defaultdict(dict)
    for cid,item in expected.items():
        w,q=active[cid];source=PREFIX+item['passage_id'];labels=list(item['clean'])
        if (w.source_passage_id!=source or q.passage_id!=source or q.form_group_id!=cid or w.verse_numbers!=labels):
            raise ValueError('Hosted window boundaries differ: '+cid)
        clean=by_source[source,'clean','zh'];clean_text={v['label']:v['text'] for v in clean['verses']}
        if {v:clean_text.get(v) for v in labels}!=item['clean']:raise ValueError('Hosted clean wording differs: '+cid)
        for condition,variant in item['conditions'].items():
            p=by_source[source,condition,'zh']
            replacements[p['id']].update(variant['verses'])
    after=json.loads(json.dumps(before))
    for pid,edits in replacements.items():
        p=before[pid];clean=by_source[p['source'],'clean','zh']
        after[pid]=overlay(p,clean,edits)
    changed={pid for pid in before if before[pid]!=after[pid]}
    # Model all eight rotations from the saved live groups, without creating readers.
    encounters=Counter()
    for rotation in range(8):
        plan={g:c for g,c,_ in build_cells('verify-omission-release',rotation,SOL_SCRATCH_SET)}
        for cid,(w,q) in active.items():
            condition=plan[w.group_index];p=by_source[w.source_passage_id,condition,'zh']
            texts={v['label']:v['text'] for v in after[p['id']]['verses']}
            actual={label:texts[label] for label in w.verse_numbers}
            if condition in CONDITIONS and actual!=expected[cid]['conditions'][condition]['verses']:
                raise ValueError('An installed rotation would serve different omission wording')
            encounters[condition]+=1
    if encounters!=Counter({c:65*SLOTS.count(c) for c in set(SLOTS)}):raise ValueError('Latin-square balance differs')
    return before,after,objects,active,changed,encounters


def unseen_updates(db,active,before,after):
    candidates=(select(Assignment,ExperimentPlanCell.condition).join(ExperimentPlanCell,Assignment.experiment_cell_id==ExperimentPlanCell.id)
        .where(Assignment.qa_item_id.in_([q.id for w,q in active.values()]),Assignment.status=='assigned',
            ExperimentPlanCell.condition.in_(CONDITIONS),ExperimentPlanCell.status.in_(('active','pending')),
            Assignment.started_at.is_(None),Assignment.delivered_at.is_(None),Assignment.completed_at.is_(None)))
    for model in (AssignmentDelivery,PilotQuestionTrial,AnswerReceipt,ParticipantResponse):
        candidates=candidates.where(~select(model.id).where(model.assignment_id==Assignment.id).exists())
    by_qa={q.id:w for w,q in active.values()}; lookup={(p['source'],p['condition']):p['id'] for p in before.values() if p['language']=='zh'}
    updates=[]
    for a,condition in db.execute(candidates):
        if not a.passage_text:continue
        w=by_qa[a.qa_item_id];pid=lookup[w.source_passage_id,condition];labels=w.verse_numbers
        old={v['label']:v['text'] for v in before[pid]['verses']};new={v['label']:v['text'] for v in after[pid]['verses']}
        old_labels=[n for n in labels if n in old]
        old_text=' '.join(old[n].strip() for n in old_labels);new_text=' '.join(new[n].strip() for n in labels)
        if (a.passage_verse_numbers,a.passage_text) not in ((old_labels,old_text),(labels,new_text)):
            raise ValueError('Unrecognized unseen passage snapshot: '+a.id)
        if (a.passage_verse_numbers,a.passage_text)!=(labels,new_text):updates.append((a,new_text,labels))
    return updates


def publish(db,release,*,apply=False,preview=None,audit_path=None):
    postgres=db.get_bind().dialect.name=='postgresql'
    if postgres:
        if apply:
            db.execute(text('SET LOCAL lock_timeout = \'5s\''))
            db.execute(text('SELECT pg_advisory_xact_lock(742908122)'))
            db.execute(text('LOCK TABLE assignments IN ACCESS EXCLUSIVE MODE NOWAIT'))
            db.execute(text('LOCK TABLE experiment_passages, experiment_passage_verses IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        else:db.execute(text('SET TRANSACTION READ ONLY'))
    before,after,objects,active,changed,encounters=prepare(db,release)
    content_before=immutable_content(db);assignments_before=assignment_texts(db)
    updates=unseen_updates(db,active,before,after)
    if apply and (preview is None or preview['release_sha256']!=digest(release) or preview['before_sha256']!=digest(before)
                  or preview['immutable_content_sha256']!=content_before):
        raise ValueError('The preview is missing or the hosted source has changed; make a fresh preview')
    if apply:
        # Free existing positions before restoring source order; unique position
        # constraints are immediate in PostgreSQL and SQLite.
        for p in objects:
            if p.id in changed:
                for i,v in enumerate(p.verses):v.position=-i-1
        db.flush()
        for p in objects:
            if p.id not in changed:continue
            p.passage_text=after[p.id]['text'];existing={v.id:v for v in p.verses}
            for row in after[p.id]['verses']:
                if row['id'] in existing:
                    v=existing[row['id']];v.text=row['text'];v.position=row['position']
                else:p.verses.append(ExperimentPassageVerse(id=row['id'],verse_number=row['label'],
                    position=row['position'],text=row['text']))
        for a,body,labels in updates:a.passage_text=body;a.passage_verse_numbers=labels
        db.flush()
        db.expire_all()
        actual,_=snapshot(db)
        if actual!=after or immutable_content(db)!=content_before:raise ValueError('Unexpected database change')
        expected_assignments=dict(assignments_before)
        for a,body,labels in updates:expected_assignments[a.id]=dict(text=body,verses=labels)
        if assignment_texts(db)!=expected_assignments:raise ValueError('Unexpected assignment snapshot change')
    report=dict(release=release['release'],applied=apply,active_windows=65,verified_omission_variants=130,
        changed_passage_records=len(changed),unchanged_passage_records=len(before)-len(changed),
        unseen_assignments_updated=len(updates),protected_assignment_snapshots=len(assignments_before)-len(updates),
        verified_rotations=8,condition_encounters=dict(encounters),other_conditions_unchanged=True,
        question_wording_and_groups_unchanged=True,excluded_held=release['excluded_held'])
    audit=dict(summary=report,release_sha256=digest(release),before_sha256=digest(before),after_sha256=digest(after),
        immutable_content_sha256=content_before,before=before,after=after,
        updated_assignments=[dict(id=a.id,before=assignments_before[a.id],after=dict(text=body,verses=labels)) for a,body,labels in updates],
        assignment_snapshot_sha256_before=digest(assignments_before))
    if audit_path:
        if audit_path.exists():raise ValueError('Audit already exists; use a new filename')
        dump(audit_path,audit)
    return report,audit


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--release',type=Path,default=RELEASE);ap.add_argument('--audit',type=Path,required=True)
    ap.add_argument('--apply',action='store_true');ap.add_argument('--preview',type=Path)
    args=ap.parse_args();data=args.release.read_bytes()
    if sha256(data).hexdigest()!=RELEASE_SHA256:raise ValueError('Omission release file differs from its pinned hash')
    release=json.loads(data)
    preview=json.loads(args.preview.read_text()) if args.preview else None
    engine=create_engine(get_database_url(),connect_args={'connect_timeout':10})
    with Session(engine) as db:
        report,audit=publish(db,release,apply=args.apply,preview=preview,audit_path=args.audit)
        if args.apply:db.commit()
        else:db.rollback()
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
