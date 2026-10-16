"""Exercise dashboard paths whose dependencies were hidden by wildcard imports."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from backend.user_dashboard.engagement import (
    _enqueue_outbox_notification,
    record_dashboard_heartbeat,
)
from backend.user_dashboard.errors import DashboardSettingsError
from backend.user_dashboard.scheduling import _assign_dashboard_next_batch
from backend.user_dashboard.settings import update_dashboard_settings
from eten_shared.models import (
    Assignment,
    Base,
    OutboxStatus,
    Participant,
    QAItem,
)
from eten_shared.notification_types import (
    DASHBOARD_ANSWER_SYNCED_TYPE,
    PER_RESPONSE_NOTIFICATION_TYPES,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def participant_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            participant = Participant(display_name="Dashboard test")
            db.add(participant)
            db.flush()
            yield db, participant
    finally:
        engine.dispose()


@pytest.mark.parametrize("notification_type", sorted(PER_RESPONSE_NOTIFICATION_TYPES))
def test_scoring_jobs_survive_a_later_answer(participant_db, notification_type):
    db, participant = participant_db
    first = _enqueue_outbox_notification(
        db, participant, notification_type, {"response_id": "first"}
    )
    db.flush()
    second = _enqueue_outbox_notification(
        db, participant, notification_type, {"response_id": "second"}
    )
    db.flush()
    assert first.status == second.status == OutboxStatus.PENDING.value
    assert first.id != second.id


def test_dashboard_pushes_supersede_older_pushes(participant_db):
    db, participant = participant_db
    first = _enqueue_outbox_notification(
        db, participant, DASHBOARD_ANSWER_SYNCED_TYPE, {}
    )
    db.flush()
    second = _enqueue_outbox_notification(
        db, participant, DASHBOARD_ANSWER_SYNCED_TYPE, {}
    )
    assert first.status == OutboxStatus.SUPERSEDED.value
    assert second.status == OutboxStatus.PENDING.value


def test_heartbeat_does_not_count_time_away(participant_db):
    db, participant = participant_db
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch("backend.user_dashboard.engagement.utc_now", return_value=start):
        record_dashboard_heartbeat(db, participant.id, "session")
    db.flush()
    with patch(
        "backend.user_dashboard.engagement.utc_now",
        return_value=start + timedelta(seconds=15),
    ):
        payload = record_dashboard_heartbeat(db, participant.id, "session")
    assert payload["active_seconds"] == 15
    db.flush()
    with patch(
        "backend.user_dashboard.engagement.utc_now",
        return_value=start + timedelta(minutes=5),
    ):
        payload = record_dashboard_heartbeat(db, participant.id, "session")
    assert payload["active_seconds"] == 15
    assert payload["heartbeat_count"] == 3


def test_language_settings_validate_and_persist(participant_db):
    db, participant = participant_db
    with patch(
        "backend.user_dashboard.payload.get_user_dashboard_payload", return_value={}
    ):
        update_dashboard_settings(db, participant.id, language=" ZH ")
    assert participant.dashboard_preferences["language"] == "zh"
    with pytest.raises(DashboardSettingsError, match="Unsupported language"):
        update_dashboard_settings(db, participant.id, language="unknown")


def test_starting_next_batch_resumes_a_queued_assignment(participant_db):
    db, participant = participant_db
    item = QAItem(
        passage_id="test", question_text="What happened?", expected_answer="Something"
    )
    db.add(item)
    db.flush()
    assignment = Assignment(
        participant_id=participant.id, qa_item_id=item.id, batch_id="queued-batch"
    )
    db.add(assignment)
    db.flush()
    with patch(
        "backend.user_dashboard.scheduling.get_incomplete_assignment",
        return_value=assignment,
    ):
        result = _assign_dashboard_next_batch(db, participant, source="test")
    assert result is assignment
    assert participant.session.current_assignment_id == assignment.id
    assert assignment.delivered_at is not None
