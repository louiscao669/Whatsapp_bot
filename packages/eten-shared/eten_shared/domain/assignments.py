"""Participant assignment DB logic shared by WhatsApp bot and platform."""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.domain.batch_schedules import cancel_pending_next_batch_schedules
from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.domain.reminder_records import create_assignment_reminders
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Participant,
    ParticipantEvent,
    ParticipantResponse,
    ParticipantSession,
    QAItem,
    SessionState,
    new_id,
    utc_now,
)
from eten_shared.recordings import (
    get_latest_question_recording,
    has_question_recording_for_participant,
    participant_language_code,
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
    question_type: str = "open"
    mcq_choices: tuple = ()


class AssignmentAssignError(Exception):
    pass


def get_or_create_participant(db: Session, wa_id, display_name=None):
    participant = db.scalars(select(Participant).where(Participant.wa_id == wa_id)).first()
    now = utc_now()

    if participant is None:
        participant = Participant(
            wa_id=wa_id,
            display_name=display_name,
            last_seen_at=now,
        )
        db.add(participant)
        db.flush()
        return participant

    participant.last_seen_at = now
    if display_name and participant.display_name != display_name:
        participant.display_name = display_name

    return participant


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


def get_qa_item_distribution_metrics(db: Session, qa_item):
    responses = db.scalars(
        select(ParticipantResponse).where(ParticipantResponse.qa_item_id == qa_item.id)
    ).all()
    actual_response_count = len(responses)
    response_gap = max(qa_item.min_responses_required - actual_response_count, 0)

    scored_responses = [
        response.correctness_score
        for response in responses
        if response.correctness_score is not None
    ]
    average_correctness = (
        sum(scored_responses) / len(scored_responses) if scored_responses else None
    )
    low_accuracy_risk = (
        1 - average_correctness if average_correctness is not None else 0
    )
    flag_rate = (
        sum(1 for response in responses if response.is_correct == "pending")
        / actual_response_count
        if actual_response_count
        else 0
    )
    accuracy_risk = max(low_accuracy_risk, flag_rate)

    return {
        "actual_response_count": actual_response_count,
        "response_gap": response_gap,
        "average_correctness": average_correctness,
        "flag_rate": flag_rate,
        "accuracy_risk": accuracy_risk,
    }


def get_qa_item_priority(db: Session, qa_item):
    metrics = get_qa_item_distribution_metrics(db, qa_item)
    return (
        -metrics["response_gap"],
        -metrics["accuracy_risk"],
        -qa_item.review_priority,
        metrics["actual_response_count"],
        qa_item.created_at,
    )


def select_next_qa_item(db: Session, participant):
    assigned_qa_item_ids = set(
        db.scalars(
            select(Assignment.qa_item_id).where(
                Assignment.participant_id == participant.id
            )
        ).all()
    )

    statement = select(QAItem).where(
        QAItem.active.is_(True),
        QAItem.review_removed_at.is_(None),
    )

    candidates = [
        qa_item
        for qa_item in db.scalars(statement).all()
        if qa_item.id not in assigned_qa_item_ids
        and has_question_recording_for_participant(db, qa_item.id, participant)
        and qa_item_is_assignable(qa_item)
    ]
    if not candidates:
        return None

    return sorted(candidates, key=lambda item: get_qa_item_priority(db, item))[0]


def get_incomplete_assignment(db: Session, participant, batch_id=None):
    statement = (
        select(Assignment)
        .where(
            Assignment.participant_id == participant.id,
            Assignment.status == AssignmentStatus.ASSIGNED.value,
        )
        .order_by(Assignment.assigned_at)
    )
    if batch_id:
        in_batch = db.scalars(statement.where(Assignment.batch_id == batch_id)).first()
        if in_batch:
            return in_batch

    return db.scalars(statement).first()


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
    return max(participant.preferred_batch_size or 1, 1)


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
):
    batch_id = participant_session.current_batch_id or new_id()
    assignment = Assignment(
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        batch_id=batch_id,
        status=AssignmentStatus.ASSIGNED.value,
        assigned_at=utc_now(),
    )
    db.add(assignment)
    db.flush()
    create_assignment_reminders(db, assignment, participant)

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

    if not has_question_recording_for_participant(db, qa_item.id, participant):
        language = participant_language_code(participant)
        raise AssignmentAssignError(
            f"No expert question recording for language '{language}'. "
            "Record the question at /record before assigning."
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

