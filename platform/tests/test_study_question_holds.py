"""A documented hold reduces enrollment without hiding an incomplete bank."""
from collections import Counter
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import pilot_import_reviewed122 as bank
from sol_editorial import ITEM
from backend.admin.services.study_enrollment import enroll_study_participant
from eten_shared.experiment_plan import ExperimentPlanError
from eten_shared.models import Base, ExperimentPlanCell, ExperimentWindow, Participant, QAItem
from eten_shared.question_discovery.experiment_selection import remaining_cell_items, participant_wh_filter
from eten_shared.question_forms import participant_question_forms


@pytest.fixture
def study(monkeypatch):
    monkeypatch.setenv('ENABLE_EXPERIMENT_ASSIGNMENT', 'true')
    monkeypatch.setenv('REQUIRE_QUESTION_AUDIO', 'false')
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        bank.install(db,bank.load_bank(bank.SOL_SET),qa_set=bank.SOL_SET,apply=True)
        db.flush()
        yield db
    engine.dispose()


def test_hold_keeps_rotation_balance_and_is_not_served(study):
    counts=Counter();rotations=set()
    for i in range(8):
        result,_=enroll_study_participant(study,str(uuid4()),'Hold validation '+str(i))
        rotations.add(result['rotation'])
        p=study.get(Participant,result['participant_id']);seen=set()
        for cell in study.scalars(select(ExperimentPlanCell).where(ExperimentPlanCell.participant_id==p.id)):
            for q in remaining_cell_items(study,cell,p,set(),participant_wh_filter(p),participant_question_forms(p)):
                assert q.form_group_id!=ITEM
                assert q.form_group_id not in seen
                seen.add(q.form_group_id);counts[q.form_group_id,cell.condition]+=1
        assert len(seen)==65
    assert len(rotations)==8
    assert all(n==(2 if condition=='clean' else 1) for (_,condition),n in counts.items())
    held=study.scalar(select(QAItem).where(QAItem.form_group_id==ITEM))
    assert held.review_removed_at is not None
    assert study.scalar(select(ExperimentWindow).where(ExperimentWindow.qa_item_id==held.id)) is not None


def test_unplanned_missing_window_still_blocks_enrollment(study):
    window=study.scalars(select(ExperimentWindow).where(
        ExperimentWindow.source_passage_id.startswith('reviewed122_sol/Hard77/',autoescape=True),
        ExperimentWindow.content_id!=ITEM)).first()
    study.delete(window);study.flush()
    with pytest.raises(ExperimentPlanError,match='eligible questions'):
        enroll_study_participant(study,str(uuid4()),'Incomplete-bank check')
