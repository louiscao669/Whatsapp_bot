import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.models import (
    Assignment,
    AssignmentStatus,
    Participant,
    ParticipantEvent,
    ParticipantResponse,
    ParticipantSession,
    ResponseType,
    ReviewStatus,
    SessionState,
    utc_now,
)


@dataclass
class WorkflowResult:
    participant_id: str
    session_id: str
    session_state: str
    response_id: Optional[str] = None
    assignment_id: Optional[str] = None


def normalize_response_text(text):
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(normalized.split())


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


def record_participant_event(db: Session, participant, event_type, metadata=None):
    event = ParticipantEvent(
        participant_id=participant.id,
        event_type=event_type,
        source="whatsapp",
        event_metadata=metadata or {},
    )
    db.add(event)
    return event


def score_text_response(qa_item, response_text):
    normalized_text = normalize_response_text(response_text)
    required_keywords = qa_item.required_keywords or []
    matched_keywords = []
    missing_keywords = []

    for keyword in required_keywords:
        normalized_keyword = normalize_response_text(keyword)
        if normalized_keyword and normalized_keyword in normalized_text:
            matched_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    if not required_keywords:
        return normalized_text, None, matched_keywords, missing_keywords, False, None

    correctness_score = len(matched_keywords) / len(required_keywords)
    is_flagged = bool(missing_keywords)
    flag_reason = (
        "Missing required keywords: " + ", ".join(missing_keywords)
        if missing_keywords
        else None
    )

    return (
        normalized_text,
        correctness_score,
        matched_keywords,
        missing_keywords,
        is_flagged,
        flag_reason,
    )


def save_response_for_current_assignment(
    db: Session,
    participant,
    participant_session,
    response_text,
):
    if not participant_session.current_assignment_id:
        if participant_session.state == SessionState.ONBOARDING.value:
            participant_session.state = SessionState.IDLE.value
        return None

    assignment = db.get(Assignment, participant_session.current_assignment_id)
    if assignment is None or assignment.participant_id != participant.id:
        participant_session.current_assignment_id = None
        participant_session.state = SessionState.IDLE.value
        return None

    if assignment.status == AssignmentStatus.COMPLETED.value:
        participant_session.current_assignment_id = None
        participant_session.state = SessionState.IDLE.value
        return None

    qa_item = assignment.qa_item
    (
        normalized_text,
        correctness_score,
        matched_keywords,
        missing_keywords,
        is_flagged,
        flag_reason,
    ) = score_text_response(qa_item, response_text)

    response = ParticipantResponse(
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        assignment_id=assignment.id,
        response_type=ResponseType.TEXT.value,
        response_text=response_text,
        normalized_text=normalized_text,
        correctness_score=correctness_score,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        is_flagged=is_flagged,
        flag_reason=flag_reason,
        review_status=(
            ReviewStatus.FLAGGED.value
            if is_flagged
            else ReviewStatus.NOT_FLAGGED.value
        ),
    )
    db.add(response)

    assignment.status = AssignmentStatus.COMPLETED.value
    assignment.completed_at = utc_now()
    assignment.attempt_count += 1
    participant.completed_count += 1
    participant_session.current_assignment_id = None
    participant_session.state = SessionState.IDLE.value

    record_participant_event(
        db,
        participant,
        "response_recorded",
        {
            "assignment_id": assignment.id,
            "qa_item_id": qa_item.id,
            "response_type": ResponseType.TEXT.value,
            "correctness_score": correctness_score,
            "is_flagged": is_flagged,
        },
    )

    db.flush()
    return response


def record_whatsapp_text_message(wa_id, display_name, message_id, message_text):
    session_factory = get_session_factory()

    with session_factory() as db:
        try:
            participant = get_or_create_participant(db, wa_id, display_name)
            participant_session = get_or_create_participant_session(db, participant)
            record_participant_event(
                db,
                participant,
                "message_received",
                {
                    "message_id": message_id,
                    "message_type": ResponseType.TEXT.value,
                    "message_text": message_text,
                    "received_at": utc_now().isoformat(),
                    "session_state": participant_session.state,
                },
            )

            response = save_response_for_current_assignment(
                db,
                participant,
                participant_session,
                message_text,
            )

            db.commit()

            return WorkflowResult(
                participant_id=participant.id,
                session_id=participant_session.id,
                session_state=participant_session.state,
                response_id=response.id if response else None,
                assignment_id=response.assignment_id if response else None,
            )
        except SQLAlchemyError:
            db.rollback()
            logging.exception("Failed to persist WhatsApp chatbot workflow")
            raise
