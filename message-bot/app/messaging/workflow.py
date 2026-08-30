import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from eten_shared.database import get_session_factory
from eten_shared.answer_llm_scoring import llm_answer_scoring_enabled
from eten_shared.answer_receipts import (
    assignment_for_provider_message,
    assignment_has_delivery,
    create_answer_receipt,
)
from eten_shared.domain.assignments import (
    AssignmentPrompt,
    automatic_assignment_enabled,
    build_assignment_prompt,
    complete_current_batch_if_needed,
    create_assignment_for_qa_item,
    ExperimentPassageMissingError,
    experiment_passage_assignment_kwargs,
    resolve_experiment_passage,
    experiment_assignment_enabled,
    get_incomplete_assignment,
    get_chained_assignment,
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
from eten_shared.keyword_matching import normalize_response_text
from eten_shared.question_discovery import (
    experiment_batch_should_reset,
    select_next_experiment_cell_item,
    select_next_qa_item,
)
from eten_shared.recordings import (
    has_question_recording_for_participant,
    participant_language_code,
)
from eten_shared.mcq import (
    choice_letters_for_type,
    choice_response_is_correct,
    choice_response_letter,
    is_choice_scored_item,
    question_type_value,
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
    AnswerReceipt,
    ExperimentPassage,
    OutboxNotification,
    OutboxStatus,
    ParticipantEvent,
    Participant,
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
    engagement_deferred: bool = False


# [2026-08-12] score_text_response_with_rubric / score_text_response /
# score_text_response_for_participant deleted. Keyword matching was the open
# instrument while the offline benchmarks used an LLM judge on a 0/0.5/1 scale,
# which made human-vs-proxy comparisons scorer-confounded. It also failed
# directionally: it under-credits a correct answer phrased differently (exactly
# what humans do), and items whose gold answer is not lexically present in the
# passage -- e.g. 2chr26 26:11 -- scored ~0 for every respondent regardless of
# what they wrote. Open answers are now judged only by
# eten_shared.answer_llm_scoring.score_open_answer.


def audio_answer_lacks_usable_transcript(transcript_text, response_type) -> bool:
    if response_type != ResponseType.AUDIO.value:
        return False
    if not (transcript_text or "").strip():
        return True
    return is_placeholder_transcript(transcript_text)


# has_usable_text_for_keyword_scoring deleted with the keyword scorer (unused).
# audio_answer_lacks_usable_transcript above is the surviving gate: it decides
# whether there is anything for the LLM judge to read.


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

    incomplete = get_chained_assignment(
        db, participant, participant_session.current_assignment_id
    ) or get_incomplete_assignment(db, participant, participant_session.current_batch_id)
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

    if experiment_assignment_enabled():
        # Designed (Latin-square) assignment for the human pilot. Serve strictly
        # from the participant's plan cell; keep one condition per batch and show
        # that condition's variant passage.
        qa_item, cell = select_next_experiment_cell_item(db, participant)
        if qa_item is None:
            participant_session.current_batch_id = None
            participant_session.current_assignment_id = None
            participant_session.state = SessionState.IDLE.value
            return None, False, completed_batch_size
        if experiment_batch_should_reset(db, participant_session.current_batch_id, cell):
            participant_session.current_batch_id = None
        # The condition reaches the participant ONLY through this passage: the QA
        # is shared across all of a chapter's conditions. If it cannot be
        # resolved, refuse to assign rather than letting build_assignment_prompt
        # fall back to the condition-invariant qa_item.passage_text.
        experiment_passage = resolve_experiment_passage(
            db, cell, qa_item, participant_language_code(participant)
        )
        if experiment_passage is None:
            raise ExperimentPassageMissingError(
                f"plan cell {cell.id} (group {cell.chapter}, condition "
                f"{cell.condition!r}) has no variant for source passage "
                f"{qa_item.passage_id!r}. Run scripts/verify_experiment_delivery.py."
            )
        if experiment_passage.condition != cell.condition:
            # Would deliver a real variant, just the WRONG one -- undetectable
            # downstream, since the exported condition comes from the cell.
            raise ExperimentPassageMissingError(
                f"plan cell {cell.id} is condition {cell.condition!r} but its passage "
                f"is condition {experiment_passage.condition!r}."
            )
        passage_kwargs = experiment_passage_assignment_kwargs(
            db, experiment_passage, qa_item
        )
        if not (passage_kwargs.get("passage_text") or "").strip():
            raise ExperimentPassageMissingError(
                f"experiment_passage {experiment_passage.id} (chapter {cell.chapter}, "
                f"condition {cell.condition!r}) has empty passage text."
            )
        prompt = create_assignment_for_qa_item(
            db,
            participant,
            participant_session,
            qa_item,
            completed_batch_size=completed_batch_size,
            assignment_source="experiment",
            experiment_cell_id=cell.id,
            **passage_kwargs,
        )
    elif automatic_assignment_enabled():
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
    else:
        participant_session.current_batch_id = None
        participant_session.current_assignment_id = None
        participant_session.state = SessionState.IDLE.value
        return None, False, completed_batch_size

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

    mcq_scoring = None
    choice_answer_correct = None
    backtranslated_text = None
    scoring_metadata = {}

    # [2026-08-12] Keyword scoring removed for open answers. It was the pilot's
    # open instrument while the offline benchmarks were produced by an LLM
    # judge, so human and proxy scores sat on different scales and any
    # human-vs-proxy delta was confounded with the scorer. Open answers are now
    # judged exclusively by the LLM path (queued here, resolved in
    # engagement/outbox.py).
    mcq_needs_llm_resolution = False
    if is_choice_scored_item(qa_item):
        normalized_text = None
        correctness_score = None
        matched_keywords = []
        missing_keywords = []
        needs_expert_review = False
        flag_reason = None
        # Exact letter first -- identical to the grid's mcq_correct, noiseless,
        # and the overwhelmingly common case.
        parsed_letter = choice_response_letter(qa_item, analysis_text)
        if parsed_letter is not None:
            choice_answer_correct = choice_response_is_correct(qa_item, analysis_text)
        elif unusable_audio_transcript or not (analysis_text or "").strip():
            # Nothing to resolve. Held, not scored 0 -- see the open branch.
            choice_answer_correct = None
            needs_expert_review = True
            flag_reason = "Pending: no usable reply text for this choice question."
            scoring_metadata = {"method": "none", "status": "unusable_reply"}
        elif llm_answer_scoring_enabled():
            # [2026-08-12] Unparseable reply. choice_response_is_correct would
            # return False here, recording a participant who wrote "the second
            # one" as WRONG. Queue an LLM to map the reply onto a letter; the
            # correctness comparison still happens against the stored key.
            choice_answer_correct = None
            mcq_needs_llm_resolution = True
            needs_expert_review = True
            flag_reason = "MCQ choice resolution queued."
            scoring_metadata = {
                "method": "llm_choice_resolution",
                "status": "queued",
            }
        else:
            choice_answer_correct = None
            needs_expert_review = True
            flag_reason = (
                "Pending: MCQ reply did not parse and LLM resolution is disabled "
                "(set ENABLE_LLM_ANSWER_SCORING)."
            )
            scoring_metadata = {"method": "none", "status": "scorer_disabled"}
    else:
        normalized_text = normalize_response_text(analysis_text)
        correctness_score = None
        matched_keywords = []
        missing_keywords = []
        needs_expert_review = True

        if unusable_audio_transcript:
            # No usable text to judge -- these go to a human, as before.
            if not (transcript_text or "").strip():
                flag_reason = "Pending expert review: no transcript for audio answer."
            else:
                flag_reason = "Pending expert review: placeholder transcript."
        elif not llm_answer_scoring_enabled():
            # Fail loudly rather than silently leaving open answers unscored:
            # with keyword scoring gone there is no fallback scorer.
            flag_reason = (
                "Pending expert review: LLM answer scoring is disabled "
                "(set ENABLE_LLM_ANSWER_SCORING)."
            )
            scoring_metadata = {"method": "none", "status": "scorer_disabled"}
        else:
            flag_reason = "LLM scoring queued."
            scoring_metadata = {
                "method": "backtranslation_llm_judge",
                "scale": "0/0.5/1",
                "status": "queued",
            }

    if is_choice_scored_item(qa_item):
        # None means "not resolved yet" (queued or unusable), NOT "wrong".
        if choice_answer_correct is None:
            is_correct_label = "pending"
        else:
            is_correct_label = "yes (auto)" if choice_answer_correct else "no (auto)"
    else:
        # Open answers are never labelled at ingest now: they are "pending"
        # until the outbox judge writes a 0 / 0.5 / 1 back.
        is_correct_label = "pending"

    stored_response_text = response_text
    stored_media_id = media_id
    stored_media_url = media_url
    stored_transcript = transcript_text
    if is_choice_scored_item(qa_item):
        parsed = choice_response_letter(qa_item, analysis_text)
        # Keep the raw reply when it did not parse: the outbox resolver needs
        # the participant's own words, and overwriting them with None would
        # destroy the only copy.
        stored_response_text = parsed if parsed is not None else response_text
        if parsed is not None:
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
        backtranslated_text=backtranslated_text,
        scoring_metadata=scoring_metadata,
        correctness_score=correctness_score,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        is_correct=is_correct_label,
        flag_reason=flag_reason,
        # A cleanly-parsed MCQ is final at ingest; everything else is pending
        # until the outbox resolves it.
        review_status=(
            ReviewStatus.PENDING.value
            if needs_expert_review
            else ReviewStatus.AUTO.value
        ),
        source_channel=provider if provider != "workflow" else None,
        # A cleanly-parsed choice is scored right here, so stamp the verdict
        # time now. Everything else stays NULL until the outbox resolves it --
        # NULL means "no verdict yet", which the pilot report counts as missing
        # data rather than as a wrong answer.
        scored_at=utc_now() if choice_answer_correct is not None else None,
    )
    db.add(response)
    db.flush()
    if (
        not is_choice_scored_item(qa_item)
        and llm_answer_scoring_enabled()
        and not unusable_audio_transcript
    ):
        db.add(OutboxNotification(
            participant_id=participant.id,
            notification_type="answer_llm_score_requested",
            payload={"response_id": response.id},
            status=OutboxStatus.PENDING.value,
        ))
    elif mcq_needs_llm_resolution:
        db.add(OutboxNotification(
            participant_id=participant.id,
            notification_type="mcq_choice_resolution_requested",
            payload={"response_id": response.id},
            status=OutboxStatus.PENDING.value,
        ))

    # Assignment completion (status/completed_at/attempt_count) already
    # applied atomically by try_complete_assignment above.
    participant.completed_count += 1
    participant_session.current_assignment_id = assignment.next_assignment_id
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
            "scoring_method": (scoring_metadata or {}).get("method", "choice"),
            "choice_scored": is_choice_scored_item(qa_item),
            "question_type": qa_item.question_type,
        },
        provider=provider,
    )

    db.flush()
    return response


def _record_provider_answer_for_participant(
    *,
    participant=None,
    provider,
    display_name,
    message_id,
    message_type,
    message_metadata,
    external_user_id=None,
    expected_assignment_id=None,
    defer_engagement=False,
    response_text=None,
    media_id=None,
    media_url=None,
    transcript_text=None,
    record_response=True,
):
    session_factory = get_session_factory()

    with session_factory() as db:
        try:
            contact = None
            if participant is None:
                contact = db.scalars(
                    select(ParticipantProviderContact).where(
                        ParticipantProviderContact.provider == provider,
                        ParticipantProviderContact.external_user_id
                        == str(external_user_id),
                        ParticipantProviderContact.opted_out_at.is_(None),
                    )
                ).first()
                if contact is None:
                    raise ValueError(
                        f"No active {provider} contact found for "
                        f"external_user_id={external_user_id}"
                    )
                participant = contact.participant
            else:
                participant = db.merge(participant)

            now = utc_now()
            participant.last_seen_at = now
            if contact is not None:
                contact.last_seen_at = now
            # display_name is not persisted: names are not collected under the
            # approved protocol. The parameter is retained so provider adapters
            # need no signature change.
            participant_session = get_or_create_participant_session(db, participant)
            if (
                expected_assignment_id is not None
                and participant_session.current_assignment_id
                != expected_assignment_id
            ):
                # A stale inline-keyboard tap must not mutate or commit any
                # participant state. This check now shares the answer-writing
                # transaction instead of requiring a separate preflight one.
                db.rollback()
                return None
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
            streak_badges = []
            if not defer_engagement:
                response_award = award_response_currency(db, participant, response)
                if response_award:
                    currency_awards.append(response_award)
                streak_badges = update_streak_for_response(db, participant, response)
            (
                prompt,
                batch_completed,
                completed_batch_size,
            ) = create_assignment_prompt(db, participant, participant_session)
            if prompt and not defer_engagement:
                assignment = db.get(Assignment, prompt.assignment_id)
                if assignment:
                    create_assignment_reminders(db, assignment, participant)
            if batch_completed:
                if not defer_engagement:
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
                else:
                    batch_size_nudge = None
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
                    if next_assignment and not defer_engagement:
                        create_assignment_reminders(db, next_assignment, participant)
            else:
                batch_size_nudge = None
            awarded_badges = list(streak_badges)
            if not defer_engagement:
                awarded_badges += evaluate_and_award_badges(
                    db,
                    participant,
                    batch_completed=batch_completed,
                )

            if defer_engagement and response:
                db.add(
                    OutboxNotification(
                        participant_id=participant.id,
                        notification_type="answer_postprocess_requested",
                        payload={
                            "response_id": response.id,
                            "next_assignment_id": prompt.assignment_id if prompt else None,
                            "batch_completed": batch_completed,
                            "completed_batch_size": completed_batch_size,
                            "completed_count_at_response": participant.completed_count,
                            "source": provider,
                        },
                        status=OutboxStatus.PENDING.value,
                    )
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
                engagement_deferred=defer_engagement,
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
    if provider == "telegram" and record_response:
        # Telegram text answers use the same single-transaction fast path as
        # inline MCQs. Initial/resume prompts (record_response=False) retain the
        # normal engagement setup because no answer latency is involved.
        return _record_provider_answer_for_participant(
            provider=provider,
            external_user_id=str(external_user_id),
            display_name=display_name,
            message_id=message_id,
            message_type=ResponseType.TEXT.value,
            message_metadata={
                "provider": provider,
                "external_user_id": str(external_user_id),
                "message_text": message_text,
            },
            response_text=message_text,
            record_response=True,
            defer_engagement=True,
        )

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


def mcq_answer_format_error(qa_item, raw_answer):
    """Return participant-facing guidance, or None for a strict valid choice."""

    if not is_choice_scored_item(qa_item):
        return None
    valid_letters = choice_letters_for_type(question_type_value(qa_item))
    answer = (raw_answer or "").strip()
    callback_match = re.fullmatch(r"mcq_([0-3])", answer, flags=re.IGNORECASE)
    valid_callback = bool(
        callback_match and int(callback_match.group(1)) < len(valid_letters)
    )
    if valid_callback or answer.upper() in valid_letters:
        return None
    letters = ", ".join(valid_letters[:-1]) + f", or {valid_letters[-1]}"
    return f"Wrong answer format. Reply with {letters}, or tap a choice button."


def record_telegram_answer_receipt(
    *,
    chat_id,
    display_name,
    update_id,
    raw_answer,
    assignment_id=None,
    question_message_id=None,
):
    """Durably accept a Telegram answer and return its prepared successor."""

    session_factory = get_session_factory()
    with session_factory() as db:
        contact = db.scalar(
            select(ParticipantProviderContact).where(
                ParticipantProviderContact.provider == "telegram",
                ParticipantProviderContact.external_user_id == str(chat_id),
                ParticipantProviderContact.opted_out_at.is_(None),
            )
        )
        if not contact:
            raise ValueError("No active Telegram participant")
        participant = contact.participant
        mapped_assignment = None
        if question_message_id is not None:
            mapped_assignment = assignment_for_provider_message(
                db,
                participant_id=participant.id,
                provider="telegram",
                provider_message_id=question_message_id,
            )
        assignment = db.get(Assignment, assignment_id) if assignment_id else mapped_assignment
        if assignment_id and mapped_assignment and mapped_assignment.id != assignment_id:
            assignment = None
        if assignment is None:
            participant_session = get_or_create_participant_session(db, participant)
            assignment = db.get(Assignment, participant_session.current_assignment_id)
        if assignment is None or assignment.participant_id != participant.id:
            return WorkflowResult(
                participant_id=participant.id,
                session_id=participant.session.id if participant.session else "",
                session_state=participant.session.state if participant.session else SessionState.IDLE.value,
                status_message="No question has been delivered yet. Please wait for the question before answering.",
                engagement_deferred=True,
            )

        was_delivered = bool(assignment.delivered_at) or assignment_has_delivery(
            db,
            participant_id=participant.id,
            assignment_id=assignment.id,
            provider="telegram",
        )
        if not was_delivered:
            return WorkflowResult(
                participant_id=participant.id,
                session_id=participant.session.id if participant.session else "",
                session_state=participant.session.state if participant.session else SessionState.IDLE.value,
                status_message="No question has been delivered yet. Please wait for the question before answering.",
                engagement_deferred=True,
            )

        format_error = mcq_answer_format_error(assignment.qa_item, raw_answer)
        if format_error:
                return WorkflowResult(
                    participant_id=participant.id,
                    session_id=participant.session.id if participant.session else "",
                    session_state=participant.session.state if participant.session else SessionState.IDLE.value,
                    status_message=format_error,
                    engagement_deferred=True,
                )

        normalized_answer = " ".join(
            "".join(
                character if character.isalnum() else " "
                for character in (raw_answer or "").casefold()
            ).split()
        )
        if normalized_answer in {
            "hi", "hello", "hey", "hi there", "hello there", "你好", "您好"
        }:
            prompt = build_assignment_prompt(db, assignment, assignment.qa_item, participant)
            return WorkflowResult(
                participant_id=participant.id,
                session_id=participant.session.id if participant.session else "",
                session_state=participant.session.state if participant.session else SessionState.IDLE.value,
                prompt=prompt,
                engagement_deferred=True,
            )

        receipt, created = create_answer_receipt(
            db,
            participant_id=participant.id,
            assignment=assignment,
            provider="telegram",
            provider_update_id=update_id,
            provider_question_message_id=question_message_id,
            response_type=ResponseType.TEXT.value,
            raw_answer=raw_answer,
        )
        prompt = None
        successor = db.get(Assignment, assignment.next_assignment_id) \
            if assignment.next_assignment_id else None
        if created and successor and successor.status == AssignmentStatus.ASSIGNED.value:
            prompt = build_assignment_prompt(db, successor, successor.qa_item, participant)
        db.commit()
        return WorkflowResult(
            participant_id=participant.id,
            session_id=participant.session.id if participant.session else "",
            session_state=participant.session.state if participant.session else SessionState.IDLE.value,
            response_id=receipt.id,
            assignment_id=assignment.id,
            prompt=prompt,
            engagement_deferred=True,
            status_message=None if created else "This question was already answered.",
        )


def process_pending_answer_receipts(limit=50):
    """Project immutable receipts into the existing response lifecycle."""

    session_factory = get_session_factory()
    processed = 0
    with session_factory() as db:
        receipts = db.scalars(
            select(AnswerReceipt)
            .where(AnswerReceipt.status == "pending")
            .order_by(AnswerReceipt.created_at, AnswerReceipt.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for receipt in receipts:
            assignment = db.get(Assignment, receipt.assignment_id)
            participant = db.get(Participant, receipt.participant_id)
            if not assignment or not participant:
                receipt.status = "failed"
                receipt.failure_reason = "Assignment or participant no longer exists"
                continue
            existing = db.scalar(
                select(ParticipantResponse).where(
                    ParticipantResponse.assignment_id == assignment.id
                )
            )
            if existing:
                receipt.response_id = existing.id
                receipt.status = "processed"
                receipt.processed_at = utc_now()
                processed += 1
                continue

            participant_session = get_or_create_participant_session(db, participant)
            participant_session.current_assignment_id = assignment.id
            participant_session.current_batch_id = assignment.batch_id
            participant_session.state = SessionState.AWAITING_RESPONSE.value
            response = save_response_for_current_assignment(
                db,
                participant,
                participant_session,
                response_text=receipt.raw_answer,
                response_type=receipt.response_type,
                provider=receipt.provider,
            )
            if response is None:
                receipt.status = "failed"
                receipt.failure_reason = "Assignment could not be completed"
                continue

            batch_completed, completed_batch_size = complete_current_batch_if_needed(
                db, participant, participant_session
            )
            successor = db.get(Assignment, assignment.next_assignment_id) \
                if assignment.next_assignment_id else None
            if successor and successor.status == AssignmentStatus.ASSIGNED.value:
                participant_session.current_assignment_id = successor.id
                participant_session.current_batch_id = successor.batch_id
                participant_session.state = SessionState.AWAITING_RESPONSE.value
            else:
                participant_session.current_assignment_id = None
                participant_session.current_batch_id = None
                participant_session.state = SessionState.IDLE.value
            db.add(OutboxNotification(
                participant_id=participant.id,
                notification_type="answer_postprocess_requested",
                payload={
                    "response_id": response.id,
                    "next_assignment_id": successor.id if successor else None,
                    "batch_completed": batch_completed,
                    "completed_batch_size": completed_batch_size,
                    "completed_count_at_response": participant.completed_count,
                    "source": receipt.provider,
                },
                status=OutboxStatus.PENDING.value,
            ))
            if receipt.provider == "user_dashboard":
                db.add(OutboxNotification(
                    participant_id=participant.id,
                    notification_type="dashboard_answer_synced",
                    payload={
                        "response_id": response.id,
                        "assignment_id": assignment.id,
                        "qa_item_id": assignment.qa_item_id,
                        "batch_id": assignment.batch_id,
                        "batch_completed": batch_completed,
                        "completed_batch_size": completed_batch_size,
                        "next_assignment_id": successor.id if successor else None,
                    },
                    status=OutboxStatus.PENDING.value,
                ))
            receipt.response_id = response.id
            receipt.status = "processed"
            receipt.processed_at = utc_now()
            processed += 1
        db.commit()
    return processed


_receipt_processor_started = False


def start_answer_receipt_processor():
    global _receipt_processor_started
    if _receipt_processor_started:
        return
    _receipt_processor_started = True

    def loop():
        while True:
            try:
                process_pending_answer_receipts()
            except Exception:
                logging.exception("Answer receipt processor failed")
            time.sleep(0.5)

    threading.Thread(target=loop, name="answer-receipts", daemon=True).start()


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
