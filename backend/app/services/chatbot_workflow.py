import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.services.badge_service import evaluate_and_award_badges
from app.services.media_storage_service import store_whatsapp_audio
from app.services.reminder_service import create_assignment_reminders
from app.services.keyword_matching_service import (
    keyword_matches_in_response,
    normalize_response_text,
)
from app.services.qa_keywords_service import (
    KeywordRubric,
    get_language_keywords,
    rubric_from_qa_item,
)
from app.services.qa_recordings_service import (
    get_latest_question_recording,
    has_question_recording_for_participant,
    participant_language_code,
    question_recording_playback_url,
)
from app.services.mcq_service import (
    choice_response_is_correct,
    choice_response_letter,
    is_choice_scored_item,
)
from app.services.qa_review_service import qa_item_is_assignable
from app.services.transcription_service import (
    is_placeholder_transcript,
    transcribe_whatsapp_audio,
)
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
    question_type: str = "open"
    mcq_choices: tuple = ()


class AssignmentAssignError(Exception):
    pass


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


def score_text_response_with_rubric(response_text: str, rubric: KeywordRubric):
    if is_placeholder_transcript(response_text or ""):
        required = rubric.required_keywords or []
        return (
            normalize_response_text(response_text or ""),
            None,
            [],
            list(required),
            True,
            "Pending expert review: placeholder transcript.",
        )

    normalized_text = normalize_response_text(response_text)
    required_keywords = rubric.required_keywords or []
    matched_keywords = []
    missing_keywords = []

    for keyword in required_keywords:
        if keyword_matches_in_response(
            keyword,
            response_text,
            keyword_specs=rubric.required_keyword_specs,
        ):
            matched_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    if not required_keywords:
        return (
            normalized_text,
            None,
            matched_keywords,
            missing_keywords,
            True,
            "Pending expert review: no required keywords configured for this language.",
        )

    correctness_score = len(matched_keywords) / len(required_keywords)
    needs_expert_review = bool(missing_keywords)
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
        needs_expert_review,
        flag_reason,
    )


def score_text_response(
    qa_item,
    response_text,
    db: Optional[Session] = None,
    language: Optional[str] = None,
):
    if db is not None and language:
        rubric = get_language_keywords(db, qa_item.id, language)
    else:
        rubric = rubric_from_qa_item(qa_item)
    return score_text_response_with_rubric(response_text, rubric)


def score_text_response_for_participant(
    db: Session,
    qa_item,
    participant,
    response_text,
):
    language = (participant.target_language or "eng").strip() or "eng"
    rubric = get_language_keywords(db, qa_item.id, language)
    return score_text_response_with_rubric(response_text, rubric)


def audio_answer_lacks_usable_transcript(transcript_text, response_type) -> bool:
    if response_type != ResponseType.AUDIO.value:
        return False
    if not (transcript_text or "").strip():
        return True
    return is_placeholder_transcript(transcript_text)


def has_usable_text_for_keyword_scoring(
    transcript_text,
    response_text,
    response_type,
) -> bool:
    if response_type == ResponseType.TEXT.value:
        return bool((response_text or "").strip())
    if response_type == ResponseType.AUDIO.value:
        return not audio_answer_lacks_usable_transcript(transcript_text, response_type)
    return False


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


def _create_assignment_for_qa_item(
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
    from app.services.batch_continuation_service import cancel_pending_next_batch_schedules

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
            "Record the question at /admin/record before assigning."
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

    prompt = _create_assignment_for_qa_item(
        db,
        participant,
        participant_session,
        qa_item,
        completed_batch_size=completed_batch_size,
        assignment_source="admin",
    )
    return prompt


def create_assignment_prompt(db: Session, participant, participant_session):
    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        return None, False, 0

    from app.services.batch_continuation_service import has_pending_next_batch_schedule

    if has_pending_next_batch_schedule(db, participant.id):
        return None, False, 0

    batch_completed, completed_batch_size = complete_current_batch_if_needed(
        db, participant, participant_session
    )
    if batch_completed:
        return None, True, completed_batch_size

    incomplete = get_incomplete_assignment(
        db, participant, participant_session.current_batch_id
    )
    if incomplete:
        prompt = resume_incomplete_assignment(
            db, participant, participant_session, incomplete
        )
        if prompt:
            return prompt, False, completed_batch_size

    qa_item = select_next_qa_item(
        db, participant
    )
    if qa_item is None:
        participant_session.current_batch_id = None
        participant_session.state = SessionState.IDLE.value
        return None, False, completed_batch_size

    prompt = _create_assignment_for_qa_item(
        db,
        participant,
        participant_session,
        qa_item,
        completed_batch_size=completed_batch_size,
        assignment_source="auto",
    )
    return prompt, False, completed_batch_size


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
    unusable_audio_transcript = audio_answer_lacks_usable_transcript(
        transcript_text,
        response_type,
    )

    keyword_scoring = None
    mcq_scoring = None
    choice_answer_correct = None
    if is_choice_scored_item(qa_item):
        normalized_text = None
        correctness_score = None
        matched_keywords = []
        missing_keywords = []
        needs_expert_review = False
        flag_reason = None
        choice_answer_correct = choice_response_is_correct(qa_item, analysis_text)
    elif has_usable_text_for_keyword_scoring(transcript_text, response_text, response_type):
        keyword_scoring = score_text_response_for_participant(
            db, qa_item, participant, analysis_text
        )

    if not is_choice_scored_item(qa_item):
        if unusable_audio_transcript:
            normalized_text = normalize_response_text(analysis_text)
            correctness_score = None
            matched_keywords = []
            missing_keywords = []
            needs_expert_review = True
            if not (transcript_text or "").strip():
                flag_reason = "Pending expert review: no transcript for audio answer."
            else:
                flag_reason = "Pending expert review: placeholder transcript (not keyword-scored)."
        elif keyword_scoring:
            (
                normalized_text,
                correctness_score,
                matched_keywords,
                missing_keywords,
                needs_expert_review,
                flag_reason,
            ) = keyword_scoring
        else:
            (
                normalized_text,
                correctness_score,
                matched_keywords,
                missing_keywords,
                needs_expert_review,
                flag_reason,
            ) = score_text_response_for_participant(db, qa_item, participant, analysis_text)

    if is_choice_scored_item(qa_item):
        is_correct_label = "yes (auto)" if choice_answer_correct else "no (auto)"
    elif needs_expert_review:
        is_correct_label = "pending"
    elif correctness_score is not None and correctness_score < 1.0:
        is_correct_label = "no (auto)"
    else:
        is_correct_label = "yes (auto)"

    stored_response_text = response_text
    stored_media_id = media_id
    stored_media_url = media_url
    stored_transcript = transcript_text
    if is_choice_scored_item(qa_item):
        stored_response_text = choice_response_letter(qa_item, analysis_text)
        stored_media_id = None
        stored_media_url = None
        stored_transcript = None

    response = ParticipantResponse(
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        assignment_id=assignment.id,
        response_type=response_type,
        response_text=stored_response_text,
        media_id=stored_media_id,
        media_url=stored_media_url,
        transcript_text=stored_transcript,
        normalized_text=normalized_text,
        correctness_score=correctness_score,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        is_correct=is_correct_label,
        flag_reason=flag_reason,
        review_status=ReviewStatus.AUTO.value
        if is_choice_scored_item(qa_item)
        else (
            ReviewStatus.PENDING.value
            if needs_expert_review
            else ReviewStatus.AUTO.value
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
            "is_correct": response.is_correct,
            "keyword_scored": bool(keyword_scoring),
            "choice_scored": is_choice_scored_item(qa_item),
            "question_type": qa_item.question_type,
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
            from app.services.batch_continuation_service import (
                cancel_pending_next_batch_schedules,
                schedule_next_batch_assignment,
            )

            cancel_pending_next_batch_schedules(
                db,
                participant.id,
                reason="Participant sent a new inbound message",
            )
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
            if batch_completed:
                schedule_next_batch_assignment(db, participant, participant_session)
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
    language_hint = None
    try:
        with get_session_factory()() as db:
            participant = db.scalars(
                select(Participant).where(Participant.wa_id == wa_id)
            ).first()
            if participant:
                language_hint = participant.target_language
    except Exception:
        logging.exception("Could not load participant language for transcription")

    transcription = transcribe_whatsapp_audio(
        media_id=media_id,
        mime_type=stored_content_type,
        sha256=sha256,
        media_url=stored_media_url,
        language_hint=language_hint,
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
