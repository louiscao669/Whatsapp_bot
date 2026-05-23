import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.services.badge_service import evaluate_and_award_badges
from app.services.media_storage_service import store_whatsapp_audio
from app.services.reminder_service import create_assignment_reminders
from app.services.transcription_service import transcribe_whatsapp_audio
from app.models import (
    Assignment,
    AssignmentStatus,
    Participant,
    ParticipantEvent,
    ParticipantResponse,
    ParticipantSession,
    QAItem,
    ResponseType,
    ReviewStatus,
    SessionState,
    new_id,
    utc_now,
)


@dataclass
class AssignmentPrompt:
    assignment_id: str
    qa_item_id: str
    audio_url: Optional[str]
    question_text: str
    passage_reference: Optional[str] = None


@dataclass
class WorkflowResult:
    participant_id: str
    session_id: str
    session_state: str
    response_id: Optional[str] = None
    assignment_id: Optional[str] = None
    prompt: Optional[AssignmentPrompt] = None
    batch_completed: bool = False
    completed_batch_size: int = 0
    awarded_badges: tuple = ()


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


def get_qa_item_distribution_metrics(qa_item):
    responses = qa_item.responses or []
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
        sum(1 for response in responses if response.is_flagged)
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


def get_qa_item_priority(qa_item):
    metrics = get_qa_item_distribution_metrics(qa_item)
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

    statement = select(QAItem).where(QAItem.active.is_(True))
    if participant.target_language:
        statement = statement.where(QAItem.language == participant.target_language)

    candidates = [
        qa_item
        for qa_item in db.scalars(statement).all()
        if qa_item.id not in assigned_qa_item_ids
    ]
    if not candidates:
        return None

    return sorted(candidates, key=get_qa_item_priority)[0]


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


def create_assignment_prompt(db: Session, participant, participant_session):
    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        return None, False, 0

    batch_completed, completed_batch_size = complete_current_batch_if_needed(
        db, participant, participant_session
    )
    if batch_completed:
        return None, True, completed_batch_size

    qa_item = select_next_qa_item(db, participant)
    if qa_item is None:
        participant_session.current_batch_id = None
        participant_session.state = SessionState.IDLE.value
        return None, False, completed_batch_size

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
            "distribution_metrics": get_qa_item_distribution_metrics(qa_item),
        },
    )

    return (
        AssignmentPrompt(
            assignment_id=assignment.id,
            qa_item_id=qa_item.id,
            audio_url=qa_item.audio_url,
            question_text=qa_item.question_text,
            passage_reference=qa_item.passage_reference,
        ),
        False,
        completed_batch_size,
    )


def save_response_for_current_assignment(
    db: Session,
    participant,
    participant_session,
    response_text=None,
    response_type=ResponseType.TEXT.value,
    media_id=None,
    media_url=None,
    transcript_text=None,
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
    analysis_text = transcript_text or response_text or ""
    (
        normalized_text,
        correctness_score,
        matched_keywords,
        missing_keywords,
        is_flagged,
        flag_reason,
    ) = score_text_response(qa_item, analysis_text)

    response = ParticipantResponse(
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        assignment_id=assignment.id,
        response_type=response_type,
        response_text=response_text,
        media_id=media_id,
        media_url=media_url,
        transcript_text=transcript_text,
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
            "response_type": response_type,
            "media_id": media_id,
            "has_transcript": bool(transcript_text),
            "correctness_score": correctness_score,
            "is_flagged": is_flagged,
        },
    )

    db.flush()
    return response


def record_whatsapp_answer(
    wa_id,
    display_name,
    message_id,
    message_type,
    message_metadata,
    response_text=None,
    media_id=None,
    media_url=None,
    transcript_text=None,
):
    session_factory = get_session_factory()

    with session_factory() as db:
        try:
            participant = get_or_create_participant(db, wa_id, display_name)
            participant_session = get_or_create_participant_session(db, participant)
            event_metadata = {
                "message_id": message_id,
                "message_type": message_type,
                "received_at": utc_now().isoformat(),
                "session_state": participant_session.state,
            }
            event_metadata.update(message_metadata or {})
            record_participant_event(
                db,
                participant,
                "message_received",
                event_metadata,
            )

            response = save_response_for_current_assignment(
                db,
                participant,
                participant_session,
                response_text=response_text,
                response_type=message_type,
                media_id=media_id,
                media_url=media_url,
                transcript_text=transcript_text,
            )
            (
                prompt,
                batch_completed,
                completed_batch_size,
            ) = create_assignment_prompt(db, participant, participant_session)
            awarded_badges = evaluate_and_award_badges(
                db,
                participant,
                batch_completed=batch_completed,
            )

            db.commit()

            return WorkflowResult(
                participant_id=participant.id,
                session_id=participant_session.id,
                session_state=participant_session.state,
                response_id=response.id if response else None,
                assignment_id=response.assignment_id if response else None,
                prompt=prompt,
                batch_completed=batch_completed,
                completed_batch_size=completed_batch_size,
                awarded_badges=tuple(
                    {
                        "badge_type": badge.badge_type,
                        "title": badge.title,
                        "description": badge.description,
                    }
                    for badge in awarded_badges
                ),
            )
        except SQLAlchemyError:
            db.rollback()
            logging.exception("Failed to persist WhatsApp chatbot workflow")
            raise


def record_whatsapp_text_message(wa_id, display_name, message_id, message_text):
    return record_whatsapp_answer(
        wa_id=wa_id,
        display_name=display_name,
        message_id=message_id,
        message_type=ResponseType.TEXT.value,
        message_metadata={"message_text": message_text},
        response_text=message_text,
    )


def record_whatsapp_audio_message(
    wa_id,
    display_name,
    message_id,
    media_id,
    mime_type=None,
    sha256=None,
    voice=None,
):
    stored_media = None
    try:
        stored_media = store_whatsapp_audio(media_id=media_id, mime_type=mime_type)
    except Exception:
        logging.exception("Failed to store WhatsApp audio media %s", media_id)

    stored_media_url = stored_media.storage_uri if stored_media else None
    stored_content_type = stored_media.content_type if stored_media else mime_type
    transcription = transcribe_whatsapp_audio(
        media_id=media_id,
        mime_type=stored_content_type,
        sha256=sha256,
        media_url=stored_media_url,
    )
    return record_whatsapp_answer(
        wa_id=wa_id,
        display_name=display_name,
        message_id=message_id,
        message_type=ResponseType.AUDIO.value,
        message_metadata={
            "media_id": media_id,
            "mime_type": mime_type,
            "sha256": sha256,
            "voice": voice,
            "media_url": stored_media_url,
            "storage_bucket": stored_media.bucket if stored_media else None,
            "storage_object_path": stored_media.object_path if stored_media else None,
            "storage_file_size": stored_media.file_size if stored_media else None,
            "transcription_provider": transcription.provider,
            "transcription_confidence": transcription.confidence,
        },
        media_id=media_id,
        media_url=stored_media_url,
        transcript_text=transcription.text,
    )
