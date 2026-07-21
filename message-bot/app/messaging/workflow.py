import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from eten_shared.database import get_session_factory
from eten_shared.domain.assignments import (
    AssignmentPrompt,
    automatic_assignment_enabled,
    build_assignment_prompt,
    complete_current_batch_if_needed,
    create_assignment_for_qa_item,
    get_incomplete_assignment,
    get_or_create_participant_session,
    get_preferred_batch_size,
    record_participant_event as _record_participant_event,
    resume_incomplete_assignment,
    try_complete_assignment,
)
from eten_shared.domain.batch_schedules import has_pending_next_batch_schedule
from eten_shared.domain.identity import (
    PROVIDER_WHATSAPP,
    get_or_create_participant_by_contact,
    resolve_participant,
)
from eten_shared.domain.batch_size_nudges import (
    apply_batch_size_nudge_response,
    batch_size_response_choice,
    recommend_batch_size_nudge,
    record_batch_size_nudge_sent,
)
from eten_shared.domain.streaks import update_streak_for_response
from app.engagement.badges import evaluate_and_award_badges
from app.engagement.currency import (
    award_batch_completion_currency,
    award_response_currency,
)
from app.providers.whatsapp.schedule_policy import create_assignment_reminders
from eten_shared.media_storage import (
    store_provider_audio_bytes,
    store_whatsapp_audio,
)
from eten_shared.keyword_matching import (
    keyword_matches_in_response,
    normalize_response_text,
)
from eten_shared.qa_keywords import (
    KeywordRubric,
    get_language_keywords,
    rubric_from_qa_item,
)
from eten_shared.question_discovery import select_next_qa_item
from eten_shared.recordings import (
    has_question_recording_for_participant,
    participant_language_code,
)
from eten_shared.mcq import (
    choice_response_is_correct,
    choice_response_letter,
    is_choice_scored_item,
)
from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.transcription import (
    TranscriptionResult,
    get_placeholder_transcript_text,
    is_placeholder_transcript,
    transcribe_audio_bytes,
    transcribe_whatsapp_audio,
)
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    ParticipantEvent,
    ParticipantProviderContact,
    ParticipantResponse,
    ParticipantSession,
    QAItem,
    ResponseType,
    ReviewStatus,
    SessionState,
    new_id,
    utc_now,
)


def record_participant_event(db: Session, participant, event_type, metadata=None):
    return _record_participant_event(db, participant, event_type, metadata, source="whatsapp")


def record_provider_participant_event(
    db: Session,
    participant,
    event_type,
    metadata=None,
    *,
    provider="workflow",
):
    return _record_participant_event(
        db,
        participant,
        event_type,
        metadata,
        source=provider,
    )


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
    currency_awards: tuple = ()
    currency_balance: Optional[int] = None
    status_message: Optional[str] = None
    batch_size_nudge: Optional[object] = None


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


def create_assignment_prompt(db: Session, participant, participant_session):
    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        return None, False, 0

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
            # Question is about to be delivered on the messenger: stamp the
            # delivery moment and start the time-on-task clock (both kept if
            # already set on another surface). On the messenger there is no
            # separate "opened" signal, so delivered_at == started_at here.
            incomplete.delivered_at = incomplete.delivered_at or utc_now()
            incomplete.started_at = incomplete.started_at or incomplete.delivered_at
            return prompt, False, completed_batch_size

    if not automatic_assignment_enabled():
        participant_session.current_batch_id = None
        participant_session.current_assignment_id = None
        participant_session.state = SessionState.IDLE.value
        return None, False, completed_batch_size

    qa_item = select_next_qa_item(db, participant)
    if qa_item is None:
        participant_session.current_batch_id = None
        participant_session.state = SessionState.IDLE.value
        return None, False, completed_batch_size

    prompt = create_assignment_for_qa_item(
        db,
        participant,
        participant_session,
        qa_item,
        completed_batch_size=completed_batch_size,
        assignment_source="auto",
    )
    if prompt:
        # Delivered immediately over the messenger: stamp delivery + start the
        # clock (delivered_at == started_at on the messenger; no "opened" event).
        new_assignment = db.get(Assignment, prompt.assignment_id)
        if new_assignment:
            new_assignment.delivered_at = new_assignment.delivered_at or utc_now()
            new_assignment.started_at = (
                new_assignment.started_at or new_assignment.delivered_at
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
    provider="workflow",
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

    # Race guard: first surface to complete the assignment wins. If another
    # surface (e.g. the dashboard) completed it concurrently, treat this like
    # the already-completed case above.
    if not try_complete_assignment(db, assignment):
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
        source_channel=provider if provider != "workflow" else None,
    )
    db.add(response)

    # Assignment completion (status/completed_at/attempt_count) already
    # applied atomically by try_complete_assignment above.
    participant.completed_count += 1
    participant_session.current_assignment_id = None
    participant_session.state = SessionState.IDLE.value

    record_provider_participant_event(
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
        provider=provider,
    )

    db.flush()
    return response


def _record_provider_answer_for_participant(
    *,
    participant,
    provider,
    display_name,
    message_id,
    message_type,
    message_metadata,
    response_text=None,
    media_id=None,
    media_url=None,
    transcript_text=None,
    record_response=True,
):
    session_factory = get_session_factory()

    with session_factory() as db:
        try:
            participant = db.merge(participant)
            participant.last_seen_at = utc_now()
            if display_name and participant.display_name != display_name:
                participant.display_name = display_name
            participant_session = get_or_create_participant_session(db, participant)
            from app.engagement.batch_continuation import (
                cancel_pending_next_batch_schedules,
            )
            from app.providers.whatsapp.schedule_policy import (
                batch_next_response_choice,
                format_batch_next_assign_hour,
            )

            event_metadata = {
                "message_id": message_id,
                "message_type": message_type,
                "received_at": utc_now().isoformat(),
                "session_state": participant_session.state,
            }
            event_metadata.update(message_metadata or {})

            nudge_choice = batch_size_response_choice(response_text)
            if nudge_choice:
                nudge_response = apply_batch_size_nudge_response(
                    db,
                    participant,
                    nudge_choice,
                    source=provider,
                )
                if nudge_response:
                    record_provider_participant_event(
                        db,
                        participant,
                        "message_received",
                        event_metadata,
                        provider=provider,
                    )
                    db.commit()
                    return WorkflowResult(
                        participant_id=participant.id,
                        session_id=participant_session.id,
                        session_state=participant_session.state,
                        status_message=nudge_response["message"],
                    )

            if has_pending_next_batch_schedule(db, participant.id):
                next_batch_choice = batch_next_response_choice(response_text)
                event_metadata["batch_next_choice"] = next_batch_choice or "unrecognized"
                record_provider_participant_event(
                    db,
                    participant,
                    "message_received",
                    event_metadata,
                    provider=provider,
                )

                if next_batch_choice == "wait":
                    record_provider_participant_event(
                        db,
                        participant,
                        "batch_next_wait_selected",
                        {"message_id": message_id},
                        provider=provider,
                    )
                    db.commit()
                    return WorkflowResult(
                        participant_id=participant.id,
                        session_id=participant_session.id,
                        session_state=participant_session.state,
                        status_message=(
                            "Okay, I'll send your next batch tomorrow at "
                            f"{format_batch_next_assign_hour()}."
                        ),
                    )

                if next_batch_choice != "start_now":
                    db.commit()
                    return WorkflowResult(
                        participant_id=participant.id,
                        session_id=participant_session.id,
                        session_state=participant_session.state,
                        status_message=(
                            "Reply Start now to begin another batch, or Tomorrow "
                            "to wait until tomorrow at "
                            f"{format_batch_next_assign_hour()}."
                        ),
                    )

                cancel_pending_next_batch_schedules(
                    db,
                    participant.id,
                    reason="Participant requested the next batch immediately",
                )
                record_provider_participant_event(
                    db,
                    participant,
                    "batch_next_start_now_selected",
                    {"message_id": message_id},
                    provider=provider,
                )
            else:
                record_provider_participant_event(
                    db,
                    participant,
                    "message_received",
                    event_metadata,
                    provider=provider,
                )

            response = None
            if record_response:
                response = save_response_for_current_assignment(
                    db,
                    participant,
                    participant_session,
                    response_text=response_text,
                    response_type=message_type,
                    media_id=media_id,
                    media_url=media_url,
                    transcript_text=transcript_text,
                    provider=provider,
                )
            currency_awards = []
            response_award = award_response_currency(db, participant, response)
            if response_award:
                currency_awards.append(response_award)
            streak_badges = update_streak_for_response(db, participant, response)
            (
                prompt,
                batch_completed,
                completed_batch_size,
            ) = create_assignment_prompt(db, participant, participant_session)
            if prompt:
                assignment = db.get(Assignment, prompt.assignment_id)
                if assignment:
                    create_assignment_reminders(db, assignment, participant)
            if batch_completed:
                batch_award = award_batch_completion_currency(
                    db,
                    participant,
                    completed_batch_size,
                )
                if batch_award:
                    currency_awards.append(batch_award)
                batch_size_nudge = recommend_batch_size_nudge(db, participant)
                if batch_size_nudge:
                    record_batch_size_nudge_sent(
                        db,
                        participant,
                        batch_size_nudge,
                        source=provider,
                    )
                # Start the next batch immediately (parity with the dashboard)
                # instead of scheduling it for tomorrow and asking the
                # participant to confirm "Start now / Tomorrow".
                cancel_pending_next_batch_schedules(
                    db,
                    participant.id,
                    reason="Bot starts the next batch immediately after completion",
                )
                next_prompt, _, _ = create_assignment_prompt(
                    db, participant, participant_session
                )
                if next_prompt:
                    prompt = next_prompt
                    next_assignment = db.get(Assignment, next_prompt.assignment_id)
                    if next_assignment:
                        create_assignment_reminders(db, next_assignment, participant)
            else:
                batch_size_nudge = None
            awarded_badges = list(streak_badges) + evaluate_and_award_badges(
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
                currency_awards=tuple(currency_awards),
                currency_balance=(
                    currency_awards[-1]["balance_after"] if currency_awards else None
                ),
                batch_size_nudge=batch_size_nudge,
            )
        except SQLAlchemyError:
            db.rollback()
            logging.exception("Failed to persist %s chatbot workflow", provider)
            raise


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
        participant, _contact, _created = get_or_create_participant_by_contact(
            db, PROVIDER_WHATSAPP, wa_id, display_name=display_name, phone=wa_id
        )
        db.commit()

    return _record_provider_answer_for_participant(
        participant=participant,
        provider="whatsapp",
        display_name=display_name,
        message_id=message_id,
        message_type=message_type,
        message_metadata=message_metadata,
        response_text=response_text,
        media_id=media_id,
        media_url=media_url,
        transcript_text=transcript_text,
    )


def get_participant_by_provider_contact(provider, external_user_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        contact = db.scalars(
            select(ParticipantProviderContact).where(
                ParticipantProviderContact.provider == provider,
                ParticipantProviderContact.external_user_id == str(external_user_id),
                ParticipantProviderContact.opted_out_at.is_(None),
            )
        ).first()
        if not contact:
            return None
        participant = contact.participant
        participant.last_seen_at = utc_now()
        contact.last_seen_at = utc_now()
        db.commit()
        return participant


def record_provider_text_message(
    *,
    provider,
    external_user_id,
    display_name,
    message_id,
    message_text,
    record_response=True,
):
    participant = get_participant_by_provider_contact(provider, external_user_id)
    if participant is None:
        raise ValueError(
            f"No active {provider} contact found for external_user_id={external_user_id}"
        )

    return _record_provider_answer_for_participant(
        participant=participant,
        provider=provider,
        display_name=display_name,
        message_id=message_id,
        message_type=ResponseType.TEXT.value,
        message_metadata={
            "provider": provider,
            "external_user_id": str(external_user_id),
            "message_text": message_text,
        },
        response_text=message_text,
        record_response=record_response,
    )


def record_telegram_text_message(
    chat_id,
    display_name,
    message_id,
    message_text,
    *,
    record_response=True,
):
    return record_provider_text_message(
        provider="telegram",
        external_user_id=str(chat_id),
        display_name=display_name,
        message_id=message_id,
        message_text=message_text,
        record_response=record_response,
    )


def record_telegram_choice_answer(
    chat_id,
    display_name,
    message_id,
    assignment_id,
    choice_index,
):
    """Record an MCQ/TF answer from an inline-keyboard tap.

    Returns None when the tapped button belongs to an assignment that is no
    longer the participant's current one (stale message / already answered);
    otherwise routes ``mcq_<index>`` through the normal choice-scoring chain
    (parse_mcq_response_letter already understands that format).
    """
    participant = get_participant_by_provider_contact("telegram", str(chat_id))
    if participant is None:
        raise ValueError(
            f"No active telegram contact found for external_user_id={chat_id}"
        )

    session_factory = get_session_factory()
    with session_factory() as db:
        merged = db.merge(participant)
        participant_session = get_or_create_participant_session(db, merged)
        current_assignment_id = participant_session.current_assignment_id
        db.commit()

    if current_assignment_id != assignment_id:
        return None

    return _record_provider_answer_for_participant(
        participant=participant,
        provider="telegram",
        display_name=display_name,
        message_id=message_id,
        message_type=ResponseType.TEXT.value,
        message_metadata={
            "provider": "telegram",
            "external_user_id": str(chat_id),
            "input_method": "inline_keyboard",
            "assignment_id": assignment_id,
            "choice_index": choice_index,
        },
        response_text=f"mcq_{choice_index}",
    )


def record_telegram_voice_message(
    chat_id,
    display_name,
    message_id,
    file_id,
    audio_bytes,
    *,
    file_unique_id=None,
    mime_type=None,
    duration_seconds=None,
    record_response=True,
):
    """Record a Telegram voice/audio answer through the same
    store → transcribe → keyword-score chain as WhatsApp audio answers.

    The caller (bot handler) has already downloaded the voice file from the
    Telegram Bot API into ``audio_bytes``.
    """
    participant = get_participant_by_provider_contact("telegram", str(chat_id))
    if participant is None:
        raise ValueError(
            f"No active telegram contact found for external_user_id={chat_id}"
        )

    storage_media_id = file_unique_id or file_id
    stored_media = None
    try:
        stored_media = store_provider_audio_bytes(
            audio_bytes,
            media_id=storage_media_id,
            mime_type=mime_type or "audio/ogg",
            provider="telegram",
        )
    except Exception:
        logging.exception(
            "Failed to store Telegram voice media %s", storage_media_id
        )

    stored_media_url = stored_media.storage_uri if stored_media else None
    stored_content_type = stored_media.content_type if stored_media else mime_type

    try:
        transcription = transcribe_audio_bytes(
            audio_bytes,
            content_type=stored_content_type or "audio/ogg",
            object_path=stored_media.object_path if stored_media else "",
            language_hint=participant.target_language,
        )
    except Exception:
        logging.exception(
            "Transcription failed for Telegram voice media %s", storage_media_id
        )
        transcription = TranscriptionResult(
            text=get_placeholder_transcript_text(),
            provider="placeholder",
        )

    return _record_provider_answer_for_participant(
        participant=participant,
        provider="telegram",
        display_name=display_name,
        message_id=message_id,
        message_type=ResponseType.AUDIO.value,
        message_metadata={
            "provider": "telegram",
            "external_user_id": str(chat_id),
            "media_id": file_id,
            "file_unique_id": file_unique_id,
            "mime_type": mime_type,
            "duration_seconds": duration_seconds,
            "media_url": stored_media_url,
            "storage_bucket": stored_media.bucket if stored_media else None,
            "storage_object_path": stored_media.object_path if stored_media else None,
            "storage_file_size": stored_media.file_size if stored_media else None,
            "transcription_provider": transcription.provider,
            "transcription_confidence": transcription.confidence,
        },
        media_id=file_id,
        media_url=stored_media_url,
        transcript_text=transcription.text,
        record_response=record_response,
    )


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
            participant = resolve_participant(db, PROVIDER_WHATSAPP, wa_id)
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
