"""Drain cross-surface outbox notifications enqueued by the platform.

The user dashboard enqueues an `outbox_notifications` row when a participant
answers there (see platform user_dashboard service). This poller pushes a
messenger confirmation ("recorded via dashboard") plus the participant's
current open question, keeping the chat surface in step without coupling the
two processes.
"""

import logging
import os
import threading
import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from eten_shared.database import get_session_factory
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    OutboxNotification,
    OutboxStatus,
    ParticipantEvent,
    ParticipantResponse,
    QAItem,
    utc_now,
)
from eten_shared.answer_llm_scoring import (
    resolve_choice_letter,
    resolve_response_passage_text,
    score_open_answer,
)
from eten_shared.mcq import (
    choice_letters_for_type,
    normalize_labeled_choices,
    parse_mcq_correct_letter,
    question_type_value,
)

# Judge score -> stored is_correct label. All three are auto-scored; 0.5 gets its
# own label so a partial never gets read back as a clean pass or a clean fail.
_AUTO_LABELS = {1.0: "yes (auto)", 0.5: "partial (auto)", 0.0: "no (auto)"}
from eten_shared.domain.assignments import build_assignment_prompt
from app.providers.delivery import (
    provider_name_for_participant,
    send_assignment_prompt as send_provider_assignment_prompt,
    send_text_message,
)
from app.providers.whatsapp.schedule_policy import is_within_customer_service_window
from app.providers.whatsapp.schedule_policy import create_assignment_reminders
from app.engagement.badges import evaluate_and_award_badges
from app.engagement.currency import (
    award_batch_completion_currency,
    award_response_currency,
)
from eten_shared.domain.streaks import update_streak_for_response

DASHBOARD_ANSWER_SYNCED_TYPE = "dashboard_answer_synced"
NEW_ASSIGNMENT_ASSIGNED_TYPE = "new_assignment_assigned"
ANSWER_LLM_SCORE_REQUESTED_TYPE = "answer_llm_score_requested"
ANSWER_POSTPROCESS_REQUESTED_TYPE = "answer_postprocess_requested"
MCQ_CHOICE_RESOLUTION_REQUESTED_TYPE = "mcq_choice_resolution_requested"
KNOWN_NOTIFICATION_TYPES = (
    DASHBOARD_ANSWER_SYNCED_TYPE,
    NEW_ASSIGNMENT_ASSIGNED_TYPE,
    ANSWER_LLM_SCORE_REQUESTED_TYPE,
    ANSWER_POSTPROCESS_REQUESTED_TYPE,
    MCQ_CHOICE_RESOLUTION_REQUESTED_TYPE,
)

_outbox_started = False
_outbox_lock = threading.Lock()


def get_outbox_poll_interval_seconds():
    return int(os.getenv("OUTBOX_POLL_INTERVAL_SECONDS", "60"))


def get_outbox_max_attempts():
    return int(os.getenv("OUTBOX_MAX_ATTEMPTS", "3"))


def outbox_push_enabled():
    return (
        os.getenv("OUTBOX_PUSH_ENABLED", "true").lower() == "true"
        and bool(os.getenv("DATABASE_URL"))
    )


def _cancel(notification, reason):
    notification.status = OutboxStatus.CANCELLED.value
    notification.failure_reason = reason


def _mark_failure(notification, error_message):
    notification.attempt_count += 1
    notification.failure_reason = error_message
    if notification.attempt_count >= get_outbox_max_attempts():
        notification.status = OutboxStatus.FAILED.value


def _current_open_assignment(db, participant, participant_session):
    assignment_id = (
        participant_session.current_assignment_id if participant_session else None
    )
    if assignment_id:
        assignment = db.get(Assignment, assignment_id)
        if assignment and assignment.status != AssignmentStatus.COMPLETED.value:
            return assignment
    return None


def _dashboard_synced_message(payload):
    if payload.get("batch_completed"):
        size = payload.get("completed_batch_size")
        question_label = "question" if size == 1 else "questions"
        suffix = f" That completed your batch of {size} {question_label}." if size else ""
        return (
            "Your answer was recorded via the dashboard."
            + suffix
        )
    return "Your answer was recorded via the dashboard."


def _new_assignment_message(payload):
    count = payload.get("assigned_count")
    if isinstance(count, int) and count > 1:
        return f"You have {count} new questions to answer:"
    return "You have a new question to answer:"


def _lead_message(notification_type, payload):
    """The text sent ahead of the delivered question, per notification type."""

    if notification_type == DASHBOARD_ANSWER_SYNCED_TYPE:
        return _dashboard_synced_message(payload)
    if notification_type == NEW_ASSIGNMENT_ASSIGNED_TYPE:
        return _new_assignment_message(payload)
    return None


def process_pending_outbox(limit=50):
    """Send pending outbox notifications. Returns the number processed."""

    session_factory = get_session_factory()
    processed = 0

    with session_factory() as db:
        try:
            notifications = db.scalars(
                select(OutboxNotification)
                .where(OutboxNotification.status == OutboxStatus.PENDING.value)
                .order_by(OutboxNotification.created_at)
                .limit(limit)
            ).all()

            for notification in notifications:
                participant = notification.participant
                if not participant:
                    _cancel(notification, "Participant no longer exists")
                    continue

                participant_session = participant.session
                if participant_session and participant_session.opted_out_at:
                    _cancel(notification, "Participant opted out")
                    continue

                if notification.notification_type not in KNOWN_NOTIFICATION_TYPES:
                    _cancel(
                        notification,
                        f"Unknown notification type {notification.notification_type!r}",
                    )
                    continue

                if notification.notification_type == ANSWER_LLM_SCORE_REQUESTED_TYPE:
                    response = db.get(
                        ParticipantResponse, (notification.payload or {}).get("response_id")
                    )
                    if not response or not response.qa_item:
                        _cancel(notification, "Response or question no longer exists")
                        continue
                    # The variant passage the participant read. Must not fall
                    # back to qa_item.passage_text, which is shared across a
                    # chapter's conditions and so contains text a degraded-cell
                    # respondent never saw.
                    passage_text = resolve_response_passage_text(response)
                    if passage_text is None and response.assignment is not None and (
                        response.assignment.experiment_cell_id
                    ):
                        _mark_failure(
                            notification,
                            "Experiment cell has no passage (NULL experiment_passage_id); "
                            "refusing to judge against the clean chapter text",
                        )
                        continue
                    try:
                        result = score_open_answer(
                            question=response.qa_item.question_text,
                            original_question=response.qa_item.original_question_text,
                            participant_answer=response.transcript_text or response.response_text or "",
                            expected_answer=response.qa_item.expected_answer,
                            original_expected_answer=response.qa_item.original_expected_answer,
                            passage=passage_text,
                            language=participant.target_language,
                        )
                    except Exception as exc:
                        _mark_failure(notification, str(exc))
                        continue
                    response.correctness_score = result.score
                    # 0.5 is a real judgement, not a failure to decide: it is
                    # auto-scored like the other two, and only the label differs.
                    response.is_correct = _AUTO_LABELS[result.score]
                    response.scored_at = utc_now()
                    response.review_status = "auto"
                    response.flag_reason = None
                    response.matched_keywords = []
                    response.missing_keywords = []
                    response.backtranslated_text = result.backtranslated_answer
                    response.scoring_metadata = {
                        "method": "backtranslation_llm_judge",
                        "scale": "0/0.5/1",
                        "status": "complete",
                        "label": result.label,
                        "expected_answer_english": result.expected_answer_english,
                        "rationale": result.rationale,
                        "core_claim_expected": result.core_claim_expected,
                        "core_claim_found": result.core_claim_found,
                        "passage_source": (
                            "experiment_variant"
                            if (response.assignment is not None
                                and response.assignment.experiment_cell_id)
                            else "qa_item"
                        ),
                    }
                    notification.status = OutboxStatus.SENT.value
                    notification.sent_at = utc_now()
                    processed += 1
                    continue

                if notification.notification_type == MCQ_CHOICE_RESOLUTION_REQUESTED_TYPE:
                    response = db.get(
                        ParticipantResponse, (notification.payload or {}).get("response_id")
                    )
                    if not response or not response.qa_item:
                        _cancel(notification, "Response or question no longer exists")
                        continue
                    qa_item = response.qa_item
                    reply_text = response.transcript_text or response.response_text or ""
                    try:
                        question_type = question_type_value(qa_item)
                        letters = choice_letters_for_type(question_type)
                        options = normalize_labeled_choices(
                            qa_item.mcq_choices, question_type
                        )
                        resolution = resolve_choice_letter(
                            question=qa_item.question_text,
                            participant_answer=reply_text,
                            choices={
                                letters[i]: option
                                for i, option in enumerate(options)
                                if i < len(letters)
                            },
                            language=participant.target_language,
                        )
                    except Exception as exc:
                        _mark_failure(notification, str(exc))
                        continue

                    if resolution.letter is None:
                        # The reply selects nothing. Held as pending, NOT scored
                        # wrong -- "declined to answer" is missing data, and
                        # recording it as an error would bias human MCQ accuracy
                        # down in exactly the arm the pilot is measuring.
                        response.is_correct = "pending"
                        response.review_status = "pending"
                        response.correctness_score = None
                        # Still unscored: leave scored_at NULL so the pilot
                        # report keeps counting this as missing data.
                        response.scored_at = None
                        response.flag_reason = "MCQ reply selects no choice."
                        response.scoring_metadata = {
                            "method": "llm_choice_resolution",
                            "status": "unresolved",
                            "rationale": resolution.rationale,
                        }
                    else:
                        # Letter now known; correctness is still the exact
                        # letter-vs-key comparison the grid uses.
                        correct_letter = parse_mcq_correct_letter(
                            qa_item.mcq_correct_choice
                        )
                        is_right = resolution.letter == correct_letter
                        response.response_text = resolution.letter
                        response.correctness_score = 1.0 if is_right else 0.0
                        response.is_correct = "yes (auto)" if is_right else "no (auto)"
                        response.review_status = "auto"
                        response.scored_at = utc_now()
                        response.flag_reason = None
                        response.scoring_metadata = {
                            "method": "llm_choice_resolution",
                            "status": "complete",
                            "resolved_letter": resolution.letter,
                            "correct_letter": correct_letter,
                            "rationale": resolution.rationale,
                            "original_reply": reply_text,
                        }
                    notification.status = OutboxStatus.SENT.value
                    notification.sent_at = utc_now()
                    processed += 1
                    continue

                if notification.notification_type == ANSWER_POSTPROCESS_REQUESTED_TYPE:
                    payload = notification.payload or {}
                    response = db.get(ParticipantResponse, payload.get("response_id"))
                    if not response:
                        _cancel(notification, "Response no longer exists")
                        continue

                    # All operations here are idempotent: currency is keyed to
                    # the response/batch event, badges are unique per participant,
                    # and reminder creation skips existing reminder types.
                    award_response_currency(
                        db,
                        participant,
                        response,
                        is_first_answer=(
                            payload.get("completed_count_at_response") == 1
                        ),
                    )
                    update_streak_for_response(db, participant, response)
                    if payload.get("batch_completed"):
                        award_batch_completion_currency(
                            db,
                            participant,
                            int(payload.get("completed_batch_size") or 0),
                            response_id=response.id,
                        )
                    evaluate_and_award_badges(
                        db,
                        participant,
                        batch_completed=bool(payload.get("batch_completed")),
                    )

                    next_assignment_id = payload.get("next_assignment_id")
                    if next_assignment_id:
                        next_assignment = db.get(Assignment, next_assignment_id)
                        if next_assignment:
                            create_assignment_reminders(
                                db, next_assignment, participant
                            )

                    notification.status = OutboxStatus.SENT.value
                    notification.sent_at = utc_now()
                    processed += 1
                    continue

                provider_name = provider_name_for_participant(db, participant)
                if provider_name == "whatsapp" and not is_within_customer_service_window(
                    participant
                ):
                    _cancel(
                        notification,
                        "Outside WhatsApp 24-hour customer service window",
                    )
                    continue

                open_assignment = _current_open_assignment(
                    db, participant, participant_session
                )
                # A new-assignment push only makes sense if there is still a
                # question to deliver (the participant may have already answered
                # it on another surface before the poller ran).
                if (
                    notification.notification_type == NEW_ASSIGNMENT_ASSIGNED_TYPE
                    and open_assignment is None
                ):
                    _cancel(notification, "No open assignment to deliver")
                    continue

                payload = notification.payload or {}
                try:
                    lead_message = _lead_message(
                        notification.notification_type, payload
                    )
                    if lead_message:
                        send_text_message(db, participant, lead_message)
                    # Deliver the participant's currently open question so they can
                    # answer on either surface without messaging the bot first.
                    delivered_assignment_id = None
                    if open_assignment:
                        qa_item = open_assignment.qa_item or db.get(
                            QAItem, open_assignment.qa_item_id
                        )
                        if qa_item:
                            prompt = build_assignment_prompt(
                                db, open_assignment, qa_item, participant
                            )
                            send_provider_assignment_prompt(db, participant, prompt)
                            # Proactive messenger delivery: stamp delivery + the
                            # time-on-task clock (delivered_at == started_at on
                            # the messenger; a bot gets no "opened" signal).
                            open_assignment.delivered_at = (
                                open_assignment.delivered_at or utc_now()
                            )
                            open_assignment.started_at = (
                                open_assignment.started_at or open_assignment.delivered_at
                            )
                            delivered_assignment_id = open_assignment.id
                except Exception as exc:  # delivery errors: retry next tick
                    _mark_failure(notification, str(exc))
                    continue

                notification.status = OutboxStatus.SENT.value
                notification.sent_at = utc_now()
                db.add(
                    ParticipantEvent(
                        participant_id=participant.id,
                        event_type="outbox_notification_sent",
                        source="scheduler",
                        event_metadata={
                            "outbox_notification_id": notification.id,
                            "notification_type": notification.notification_type,
                            "provider": provider_name,
                            "delivered_assignment_id": delivered_assignment_id,
                            "payload": payload,
                        },
                    )
                )
                processed += 1

            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logging.exception("Failed to process outbox notifications")
            raise

    return processed


def outbox_loop():
    logging.info("Outbox poller started")
    while True:
        try:
            process_pending_outbox()
        except Exception:
            logging.exception("Outbox poller tick failed")
        time.sleep(get_outbox_poll_interval_seconds())


def start_outbox_poller():
    global _outbox_started

    if not outbox_push_enabled():
        logging.info("Outbox poller disabled")
        return

    with _outbox_lock:
        if _outbox_started:
            return

        thread = threading.Thread(
            target=outbox_loop,
            name="outbox-poller",
            daemon=True,
        )
        thread.start()
        _outbox_started = True
