"""Release checks for database text, immutable history, and delivery windows."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

path = Path(__file__).resolve().parents[1] / 'operations/promote_reviewed_variants.py'
spec = importlib.util.spec_from_file_location('promote_reviewed_variants', path)
promotion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promotion)
from eten_shared.models import Base


@pytest.fixture
def db_release():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        manifest = {'release_id':'test-release', 'cells':[]}
        for condition in promotion.SOURCES:
            manifest['cells'].append({'passage':'t1_test','condition':condition,
                'text':f'{condition} full text',
                'verses':[(f'1:{i}', f'{condition} verse {i}') for i in range(1,4)]})
        for seq,prefix in enumerate(('', 'hard66/')):
            qa=promotion.QAItem(id=f'qa-{seq}',passage_id=prefix+'t1_test',
                question_text='Question?',expected_answer='A')
            db.add(qa)
            db.add(promotion.ExperimentWindow(qa_item_id=qa.id,source_passage_id=qa.passage_id,
                content_id=f'content-{seq}',window_key=f'window-{seq}',group_index=seq+1,
                sequence_index=seq,verse_numbers=['1:1','1:2','1:3']))
            for condition in promotion.SOURCES:
                p=promotion.ExperimentPassage(id=f'{seq}-{condition}',source_passage_id=qa.passage_id,
                    chapter=seq+1,condition=condition,language='zh',passage_text='old full text')
                db.add(p)
                for i in range(1,4):db.add(promotion.ExperimentPassageVerse(
                    experiment_passage_id=p.id,verse_number=f'1:{i}',position=i,text=f'old verse {i}'))
        assignments=[]
        for index,(test,started,completed) in enumerate(((True,True,False),(True,True,True),(False,True,False),(False,False,False))):
            participant=promotion.Participant(id=f'p-{index}',dashboard_preferences={'test_participant':test})
            cell=promotion.ExperimentPlanCell(id=f'cell-{index}',participant_id=participant.id,
                chapter=1,condition='grammar30',sequence_index=0,experiment_passage_id='0-grammar30')
            assignment=promotion.Assignment(id=f'a-{index}',participant_id=participant.id,
                qa_item_id='qa-0',experiment_cell_id=cell.id,passage_text='old delivered text',
                passage_verse_numbers=['1:1','1:2','1:3'],status='completed' if completed else 'assigned',
                started_at=datetime.now(timezone.utc) if started else None,
                completed_at=datetime.now(timezone.utc) if completed else None)
            db.add_all([participant,cell,assignment]);assignments.append(assignment)
        db.commit()
        yield db,manifest,assignments
    engine.dispose()


def test_updates_both_sets_and_preserves_presented_real_and_completed_texts(db_release):
    db,manifest,assignments=db_release
    backup,stats=promotion.database_update(db,manifest,update=True)
    assert stats=={'passages':6,'verses':18,'delivery_windows':6,
        'refreshed_assignments':2,'preserved_historical_assignments':2}
    assert assignments[0].passage_text=='grammar30 verse 1 grammar30 verse 2 grammar30 verse 3'
    assert assignments[1].passage_text==assignments[2].passage_text=='old delivered text'
    assert assignments[3].passage_text==assignments[0].passage_text
    assert len(backup['assignments'])==2
    assert {p.source_passage_id for p in db.scalars(select(promotion.ExperimentPassage))}=={'t1_test','hard66/t1_test'}
    promotion.database_update(db,manifest,update=False)
    assert db.get(promotion.QAItem,'qa-0').question_text=='Question?'


def test_missing_rows_and_verse_mismatch_roll_back(db_release):
    db,manifest,_=db_release
    db.delete(db.get(promotion.ExperimentPassage,'1-mistranslation30'));db.flush()
    with pytest.raises(ValueError,match='all 60'):promotion.database_update(db,manifest,update=True)
    db.rollback()
    verse=db.scalar(select(promotion.ExperimentPassageVerse).where(
        promotion.ExperimentPassageVerse.experiment_passage_id=='1-mistranslation30'))
    verse.verse_number='1:99';db.flush()
    with pytest.raises(ValueError,match='Verse labels'):promotion.database_update(db,manifest,update=True)
    db.rollback()
    assert all(p.passage_text=='old full text' for p in db.scalars(select(promotion.ExperimentPassage)))


def test_answer_receipt_prevents_refresh_even_if_status_is_not_completed(db_release):
    db,manifest,assignments=db_release
    # The decision must consult response records independently of cached status.
    assert not promotion.snapshot_can_refresh(assignments[0],test_participant=True,has_response=True,has_trial=False)
    assert promotion.snapshot_can_refresh(assignments[0],test_participant=True,has_response=False,has_trial=True)
    assert not promotion.snapshot_can_refresh(assignments[3],test_participant=False,has_response=False,has_trial=True)


def test_file_validation_detects_stale_results_and_modified_inputs(tmp_path):
    (tmp_path/'text.txt').write_text('new')
    manifest={'writes':[{'path':'text.txt','after':promotion.sha(tmp_path/'text.txt')}],
              'archive_results':[{'path':'scores_old.json'}]}
    promotion.verify_files(tmp_path,tmp_path,manifest)
    (tmp_path/'scores_old.json').write_text('{}')
    with pytest.raises(ValueError,match='Stale result'):promotion.verify_files(tmp_path,tmp_path,manifest)
    (tmp_path/'text.txt').write_text('old')
    with pytest.raises(ValueError,match='File mismatch'):promotion.verify_files(tmp_path,tmp_path,manifest)
