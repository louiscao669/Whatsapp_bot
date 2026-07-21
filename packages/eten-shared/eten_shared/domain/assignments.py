"""Participant assignment DB logic shared by the message bot and platform."""

import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from eten_shared.domain.batch_schedules import cancel_pending_next_batch_schedules
from eten_shared.domain.batch_size_nudges import clamp_batch_size
from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.question_discovery import get_qa_item_distribution_metrics
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Participant,
    ParticipantEvent,
    ParticipantSession,
    PassageVerse,
    QAItem,
    SessionState,
    new_id,
    utc_now,
)
from eten_shared.recordings import (
    get_latest_question_recording,
    participant_language_code,
    participant_question_audio_satisfied,
    question_recording_playback_url,
)



def record_participant_event(db: Session, participant, event_type, metadata=None, *, source="workflow"):
    event = ParticipantEvent(
        participant_id=participant.id,
        event_type=event_type,
        source=source,
        event_metadata=metadata or {},
    )
    db.add(event)
    return event


@dataclass
class AssignmentPrompt:
    assignment_id: str
    qa_item_id: str
    audio_url: Optional[str]
    question_text: str
    passage_reference: Optional[str] = None
    passage_text: Optional[str] = None
    question_type: str = "open"
    mcq_choices: tuple = ()


class AssignmentAssignError(Exception):
    pass


def automatic_assignment_enabled() -> bool:
    """Return whether automatic QA selection is enabled for this deployment."""
    return os.getenv("ENABLE_AUTOMATIC_ASSIGNMENT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def try_complete_assignment(db: Session, assignment) -> bool:
    """Atomically mark an assignment completed; first commit wins.

    Guards against the same assignment being answered simultaneously on two
    surfaces (dashboard + messenger). Returns True when THIS caller completed
    the assignment, False when another writer got there first.
    """

    now = utc_now()
    result = db.execute(
        update(Assignment)
        .where(
            Assignment.id == assignment.id,
            Assignment.status != AssignmentStatus.COMPLETED.value,
        )
        .values(
            status=AssignmentStatus.COMPLETED.value,
            completed_at=now,
            attempt_count=Assignment.attempt_count + 1,
        )
    )
    if result.rowcount == 0:
        db.expire(assignment)
        return False

    # Refresh the in-session object so callers see the completed state.
    assignment.status = AssignmentStatus.COMPLETED.value
    assignment.completed_at = now
    return True


def get_or_create_participant_session(db: Session, participant):
    participant_session = db.scalars(
        select(ParticipantSession).where(
            ParticipantSession.participant_id == participant.id
        )
    ).first()

    if participant_session is None:
        participant_session = ParticipantSession(
            participant_id=participant.id,
            state=SessionState.ONBOARDING.value,
        )
        db.add(participant_session)
        db.flush()

    return participant_session


def get_incomplete_assignment(db: Session, participant, batch_id=None):
    statement = (
        select(Assignment)
        .where(
            Assignment.participant_id == participant.id,
            Assignment.status == AssignmentStatus.ASSIGNED.value,
        )
        .order_by(Assignment.assigned_at, Assignment.id)
    )
    if batch_id:
        in_batch = db.scalars(statement.where(Assignment.batch_id == batch_id)).first()
        if in_batch:
            return in_batch

    return db.scalars(statement).first()


PASSAGE_CONTEXT_WINDOW = 2


def surrounding_passage_text(db: Session, assignment, window: int = PASSAGE_CONTEXT_WINDOW):
    """Return the assigned verse(s) plus ``window`` verses of context on each
    side, joined as one flowing paragraph (no verse numbers or reference).

    Uses global verse ``position`` ordering, so the window spans a chapter
    boundary when the target sits near a chapter edge. Returns ``None`` when the
    verse data is unavailable, so callers can fall back to stored passage text.
    """

    translation_id = getattr(assignment, "passage_translation_id", None)
    verse_numbers = list(getattr(assignment, "passage_verse_numbers", None) or [])
    if not translation_id or not verse_numbers:
        return None

    target_positions = db.scalars(
        select(PassageVerse.position).where(
            PassageVerse.translation_id == translation_id,
            PassageVerse.verse_number.in_(verse_numbers),
        )
    ).all()
    if not target_positions:
        return None

    low = min(target_positions) - window
    high = max(target_positions) + window
    verses = db.scalars(
        select(PassageVerse)
        .where(
            PassageVerse.translation_id == translation_id,
            PassageVerse.position >= low,
            PassageVerse.position <= high,
        )
        .order_by(PassageVerse.position)
    ).all()
    texts = [verse.text.strip() for verse in verses if verse.text and verse.text.strip()]
    if not texts:
        return None
    return " ".join(texts)


def build_assignment_prompt(db: Session, assignment, qa_item, participant):
    language = participant_language_code(participant)
    recording = get_latest_question_recording(db, qa_item.id, language)
    audio_url = question_recording_playback_url(recording) or qa_item.audio_url
    return AssignmentPrompt(
        assignment_id=assignment.id,
        qa_item_id=qa_item.id,
        audio_url=audio_url,
        question_text=qa_item.question_text,
        passage_reference=qa_item.passage_reference,
        passage_text=surrounding_passage_text(db, assignment)
        or assignment.passage_text
        or qa_item.passage_text,
        question_type=qa_item.question_type or "open",
        mcq_choices=tuple(qa_item.mcq_choices or ()),
    )


def resume_incomplete_assignment(db: Session, participant, participant_session, assignment):
    qa_item = db.get(QAItem, assignment.qa_item_id)
    if not qa_item:
        return None

    participant_session.current_assignment_id = assignment.id
    participant_session.current_batch_id = assignment.batch_id
    participant_session.state = SessionState.AWAITING_RESPONSE.value
    return build_assignment_prompt(db, assignment, qa_item, participant)


def get_preferred_batch_size(participant):
    size = clamp_batch_size(participant.preferred_batch_size)
    if participant.preferred_batch_size != size:
        participant.preferred_batch_size = size
    return size


def count_completed_assignments_in_batch(db: Session, participant, batch_id):
    if not batch_id:
        return 0

    return len(
        db.scalars(
            select(Assignment).where(
                Assignment.participant_id == participant.id,
                Assignment.batch_id == batch_id,
                Assignment.status == AssignmentStatus.COMPLETED.value,
            )
        ).all()
    )


def complete_current_batch_if_needed(db: Session, participant, participant_session):
    batch_id = participant_session.current_batch_id
    completed_count = count_completed_assignments_in_batch(db, participant, batch_id)
    preferred_batch_size = get_preferred_batch_size(participant)

    if not batch_id or completed_count < preferred_batch_size:
        return False, completed_count

    participant_session.current_batch_id = None
    participant_session.current_assignment_id = None
    participant_session.state = SessionState.IDLE.value
    record_participant_event(
        db,
        participant,
        "batch_completed",
        {
            "batch_id": batch_id,
            "completed_count": completed_count,
            "preferred_batch_size": preferred_batch_size,
        },
    )
    return True, completed_count


def create_assignment_for_qa_item(
    db: Session,
    participant,
    participant_session,
    qa_item,
    completed_batch_size=0,
    assignment_source="auto",
    experiment_cell_id=None,
):
    batch_id = participant_session.current_batch_id or new_id()
    assignment = Assignment(
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        batch_id=batch_id,
        status=AssignmentStatus.ASSIGNED.value,
        assigned_at=utc_now(),
        experiment_cell_id=experiment_cell_id,
    )
    db.add(assignment)
    db.flush()

    participant_session.current_assignment_id = assignment.id
    participant_session.current_batch_id = batch_id
    participant_session.state = SessionState.AWAITING_RESPONSE.value
    participant_session.last_prompt_sent_at = utc_now()

    record_participant_event(
        db,
        participant,
        "assignment_created",
        {
            "assignment_id": assignment.id,
            "qa_item_id": qa_item.id,
            "batch_id": batch_id,
            "passage_id": qa_item.passage_id,
            "completed_batch_size": completed_batch_size,
            "preferred_batch_size": get_preferred_batch_size(participant),
            "distribution_metrics": get_qa_item_distribution_metrics(db, qa_item),
            "assignment_source": assignment_source,
            "experiment_cell_id": experiment_cell_id,
        },
    )

    return build_assignment_prompt(db, assignment, qa_item, participant)


def assign_qa_item_to_participant(db: Session, participant, participant_session, qa_item):
    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason="Manual assignment superseded scheduled next batch",
    )

    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        raise AssignmentAssignError(
            "Participant must be idle or onboarding before a new question can be assigned "
            f"(current state: {participant_session.state})."
        )

    batch_completed, completed_batch_size = complete_current_batch_if_needed(
        db, participant, participant_session
    )
    if batch_completed:
        raise AssignmentAssignError(
            "Participant just completed a batch. Submit assign again to give them this question."
        )

    if not qa_item.active:
        raise AssignmentAssignError("This question is inactive.")

    if not qa_item_is_assignable(qa_item):
        raise AssignmentAssignError(
            "This question was removed during QA review and cannot be assigned."
        )

    if not participant_question_audio_satisfied(db, qa_item.id, participant):
        language = participant_language_code(participant)
        raise AssignmentAssignError(
            f"No expert question recording for language '{language}'. "
            "Record the question at /record before assigning, or set "
            "REQUIRE_QUESTION_AUDIO=false to allow text-only questions."
        )

    existing_assignment = db.scalars(
        select(Assignment).where(
            Assignment.participant_id == participant.id,
            Assignment.qa_item_id == qa_item.id,
        )
    ).first()
    if existing_assignment:
        raise AssignmentAssignError(
            "This participant already has an assignment for this question."
        )

    if participant_session.current_assignment_id:
        current_assignment = db.get(Assignment, participant_session.current_assignment_id)
        if (
            current_assignment
            and current_assignment.status != AssignmentStatus.COMPLETED.value
        ):
            raise AssignmentAssignError(
                "Participant already has an open assignment. Wait for their response first."
            )

    prompt = create_assignment_for_qa_item(
        db,
        participant,
        participant_session,
        qa_item,
        completed_batch_size=completed_batch_size,
        assignment_source="admin",
    )
    return prompt
