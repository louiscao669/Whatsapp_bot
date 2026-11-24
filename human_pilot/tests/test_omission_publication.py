import json
from copy import deepcopy
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pilot_publish_omission_mixture as p
from eten_shared.models import Base, Participant, utc_now
from eten_shared.domain.assignments import experiment_passage_assignment_kwargs


def release():return json.loads(p.RELEASE.read_text())


def populate(db,r):
    original=json.loads((p.ROOT/'evaluation/runs/sol_latest_window_preview_2026-11-20/preview_manifest.json').read_text())
    by_source={}
    for w in original['windows']:
        by_source.setdefault(w['passage_id'],{}).update(w['conditions']['clean']['verses'])
    missing=list(r['windows'][0]['clean'])[-1]
    missing_source=r['windows'][0]['passage_id'];passages={}
    for chapter,(source,verses) in enumerate(by_source.items(),1):
        for condition in set(p.SLOTS):
            parent=p.ExperimentPassage(source_passage_id=p.PREFIX+source,condition=condition,language='zh',
                chapter=chapter,passage_text='before')
            parent.verses=[p.ExperimentPassageVerse(verse_number=label,position=i,text=body)
                for i,(label,body) in enumerate(verses.items())
                if not (source==missing_source and condition=='omission15' and label==missing)]
            parent.verses.append(p.ExperimentPassageVerse(verse_number='99:99',position=1000,text='窗口外的文字。'))
            parent.passage_text='\n\n'.join(f'{v.verse_number} {v.text}' for v in parent.verses)
            db.add(parent);passages[source,condition]=parent
    prepared=p.ExperimentPassage(source_passage_id='reviewed122_sol/Prepared60/example',condition='omission15',
        language='zh',chapter=800,passage_text='Prepared remains unchanged.')
    db.add(prepared)
    items={}
    for i,w in enumerate(original['windows']):
        source=p.PREFIX+w['passage_id']
        q=p.QAItem(passage_id=source,form_group_id=w['id'],question_text='问题',expected_answer='答案',
                  mcq_choices=['答案','乙','丙','丁','无法判断'],mcq_correct_choice='A',active=False,
                  review_removed_at=utc_now() if w['id'] in r['excluded_held'] else None)
        db.add(q);db.flush()
        db.add(p.ExperimentWindow(qa_item_id=q.id,source_passage_id=source,content_id=w['id'],
            verse_numbers=list(w['conditions']['clean']['verses']),window_key='|'.join(w['conditions']['clean']['verses']),
            group_index=301+i*8//66,sequence_index=i))
        items[w['id']]=q
    db.flush();first=r['windows'][0];q=items[first['id']]
    assignments={}
    for protection in ('unseen','shown','receipt','delivery','other_condition'):
        person=Participant(target_language='zh');db.add(person);db.flush()
        condition='grammar30' if protection=='other_condition' else 'omission15'
        parent=passages[first['passage_id'],condition]
        cell=p.ExperimentPlanCell(participant_id=person.id,chapter=301,condition=condition,status='active',
            sequence_index=0,experiment_passage_id=parent.id)
        db.add(cell);db.flush()
        bodies={v.verse_number:v.text for v in parent.verses};labels=[v for v in first['clean'] if v in bodies]
        a=p.Assignment(participant_id=person.id,qa_item_id=q.id,experiment_cell_id=cell.id,
            passage_verse_numbers=labels,passage_text=' '.join(bodies[v] for v in labels),
            delivered_at=utc_now() if protection=='shown' else None)
        db.add(a);db.flush();assignments[protection]=a.id
        if protection=='receipt':db.add(p.AnswerReceipt(participant_id=person.id,assignment_id=a.id,qa_item_id=q.id,
            provider='test',provider_update_id=a.id,response_type='mcq',raw_answer='A'))
        if protection=='delivery':db.add(p.AssignmentDelivery(participant_id=person.id,assignment_id=a.id,
            provider='test',provider_message_id=a.id))
    db.flush();return assignments


def test_publish_only_omissions_restores_verses_and_preserves_exposures():
    r=release();engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        assignments=populate(db,r);before=p.assignment_texts(db)
        report,preview=p.publish(db,r)
        assert report['active_windows']==65 and report['verified_omission_variants']==130
        assert report['changed_passage_records']==20 and report['unseen_assignments_updated']==1
        assert p.assignment_texts(db)==before
        report,audit=p.publish(db,r,apply=True,preview=preview)
        after=p.assignment_texts(db)
        assert after[assignments['unseen']]['text']==' '.join(r['windows'][0]['conditions']['omission15']['verses'].values())
        assert after[assignments['unseen']]['verses']==list(r['windows'][0]['clean'])
        for key,aid in assignments.items():
            if key!='unseen':assert after[aid]==before[aid]
        active={w.content_id:q for w,q in p.roster(db) if q.review_removed_at is None}
        parents={(x.source_passage_id,x.condition):x for x in db.scalars(select(p.ExperimentPassage))}
        for w in r['windows']:
            for condition,c in w['conditions'].items():
                delivered=experiment_passage_assignment_kwargs(db,parents[p.PREFIX+w['passage_id'],condition],active[w['id']])
                assert delivered['passage_text']==' '.join(c['verses'].values())
                assert delivered['passage_verse_numbers']==list(w['clean'])
        for pid,old in audit['before'].items():
            new=audit['after'][pid]
            if not old['source'].startswith(p.PREFIX) or old['condition'] not in p.CONDITIONS:assert old==new
            else:assert next(v['text'] for v in new['verses'] if v['label']=='99:99')=='窗口外的文字。'
        report,again=p.publish(db,r)
        assert report['changed_passage_records']==report['unseen_assignments_updated']==0
        assert p.publish(db,r,apply=True,preview=again)[0]['changed_passage_records']==0


def test_failed_review_or_lexical_cleanup_cannot_publish():
    r=release();r['windows'][0]['conditions']['omission15']['checks']['fluent']='no'
    with pytest.raises(ValueError,match='unapproved'):p.validate_release(r)
    r=release();c=r['windows'][0]['conditions']['omission15'];label=next(iter(c['verses']))
    c['punctuation_cleanup']=[dict(verse=label,before=c['verses'][label],after='被改写的文字。')]
    with pytest.raises(ValueError,match='Cleanup'):p.validate_release(r)


def test_stale_preview_rolls_back_before_any_mutation():
    r=release();engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        populate(db,r);_,preview=p.publish(db,r)
        parent=db.scalar(select(p.ExperimentPassage).where(p.ExperimentPassage.condition=='grammar30'))
        parent.passage_text+='changed';db.flush();before,_=p.snapshot(db)
        with pytest.raises(ValueError,match='preview'):p.publish(db,r,apply=True,preview=preview)
        assert p.snapshot(db)[0]==before
