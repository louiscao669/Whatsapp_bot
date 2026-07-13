import logging
import os
import threading
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from eten_shared.database import get_session_factory
from eten_shared.models import (
    AssignmentStatus,
    ParticipantEvent,
    Reminder,
    ReminderStatus,
    utc_now,
)
from app.providers.delivery import (
    provider_name_for_participant,
    send_assignment_prompt as send_provider_assignment_prompt,
    send_reminder as send_provider_reminder,
    send_text_message as send_provider_text_message,
)
from app.engagement.dashboard_nudge import (
    batch_ready_message,
    question_reminder_message,
    resolve_dashboard_nudge,
)
from app.providers.whatsapp.reminders import create_next_template_reminder
from app.providers.whatsapp.schedule_policy import (
    can_send_question_reminder,
    is_template_reminder,
    is_within_customer_service_window,
)

_scheduler_started = False
_scheduler_lock = threading.Lock()
_flask_app = None


def get_reminder_poll_interval_seconds():
    return int(os.getenv("REMINDER_POLL_INTERVAL_SECONDS", "300"))


def get_reminder_max_retries():
    return int(os.getenv("REMINDER_MAX_RETRIES", "3"))


def get_reminder_retry_backoff_minutes():
    configured_value = os.getenv("REMINDER_RETRY_BACKOFF_MINUTES", "5,15,30")
    return [
        int(value.strip())
        for value in configured_value.split(",")
        if value.strip()
    ]


def get_retry_delay(retry_count):
    backoff_minutes = get_reminder_retry_backoff_minutes()
    if not backoff_minutes:
        return timedelta(minutes=5)

    index = min(max(retry_count - 1, 0), len(backoff_minutes) - 1)
    return timedelta(minutes=backoff_minutes[index])


def reminders_enabled():
    return (
        os.getenv("REMINDER_SCHEDULER_ENABLED", "true").lower() == "true"
        and bool(os.getenv("DATABASE_URL"))
    )


def mark_reminder_cancelled(reminder, reason):
    reminder.status = ReminderStatus.CANCELLED.value
    reminder.failure_reason = reason
    reminder.updated_at = utc_now()


def mark_reminder_for_retry(reminder, error_message):
    metadata = reminder.delivery_metadata or {}
    retry_count = int(metadata.get("retry_count", 0)) + 1
    max_retries = get_reminder_max_retries()

    metadata = {
        **metadata,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "last_error": error_message,
        "last_failed_at": utc_now().isoformat(),
    }

    if retry_count > max_retries:
        reminder.status = ReminderStatus.FAILED.value
        reminder.failure_reason = error_message
        reminder.delivery_metadata = metadata
        reminder.updated_at = utc_now()
        return

    retry_delay = get_retry_delay(retry_count)
    reminder.status = ReminderStatus.PENDING.value
    reminder.failure_reason = error_message
    reminder.scheduled_for = utc_now() + retry_delay
    reminder.delivery_metadata = {
        **metadata,
        "next_retry_at": reminder.scheduled_for.isoformat(),
        "retry_delay_minutes": int(retry_delay.total_seconds() // 60),
    }
    reminder.updated_at = utc_now()


def process_due_reminders(limit=50):
    session_factory = get_session_factory()
    processed_count = 0

    with session_factory() as db:
        try:
            reminders = (
                db.scalars(
                    select(Reminder)
                    .where(
                        Reminder.status == ReminderStatus.PENDING.value,
                        Reminder.scheduled_for <= utc_now(),
                    )
                    .order_by(Reminder.scheduled_for)
                    .limit(limit)
                )
                .unique()
                .all()
            )

            from app.engagement.batch_continuation import (
                BATCH_NEXT_ASSIGNMENT_TYPE,
                process_batch_next_assignment_reminder,
            )

            for reminder in reminders:
                if reminder.reminder_type == BATCH_NEXT_ASSIGNMENT_TYPE:
                    prompt = process_batch_next_assignment_reminder(db, reminder)
                    participant = reminder.participant
                    if prompt and participant:
                        # Platform-engagement experiment: dashboard-nudged
                        # batches get a deep-link nudge instead of the
                        # in-chat question; the assignment still exists in the
                        # DB to be answered on the dashboard.
                        dashboard_link = resolve_dashboard_nudge(db, participant)
                        if dashboard_link:
                            send_provider_text_message(
                                db, participant, batch_ready_message(dashboard_link)
                            )
                            surface = "dashboard"
                        else:
                            send_provider_assignment_prompt(db, participant, prompt)
                            surface = "messenger"
                        db.add(
                            ParticipantEvent(
                                participant_id=participant.id,
                                event_type="batch_next_nudged",
                                source="scheduler",
                                event_metadata={
                                    "reminder_id": reminder.id,
                                    "assignment_id": prompt.assignment_id,
                                    "nudge_surface": surface,
                                },
                            )
                        )
                    processed_count += 1
                    continue

                participant = reminder.participant
                assignment = reminder.assignment
                participant_session = participant.session

                if not assignment:
                    mark_reminder_cancelled(reminder, "Assignment no longer exists")
                    continue

                if assignment.status == AssignmentStatus.COMPLETED.value:
                    mark_reminder_cancelled(reminder, "Assignment already completed")
                    continue

                if (
                    participant_session
                    and not participant_session.reminders_enabled
                ):
                    mark_reminder_cancelled(reminder, "Participant disabled reminders")
                    continue

                if participant_session and participant_session.opted_out_at:
                    mark_reminder_cancelled(reminder, "Participant opted out")
                    continue

                provider_name = provider_name_for_participant(db, participant)
                template_reminder = is_template_reminder(reminder)
                if not template_reminder:
                    can_send, reason = can_send_question_reminder(
                        db,
                        reminder,
                        assignment,
                    )
                    if not can_send:
                        mark_reminder_cancelled(reminder, reason)
                        continue

                if (
                    provider_name == "whatsapp"
                    and not template_reminder
                    and not is_within_customer_service_window(participant)
                ):
                    mark_reminder_cancelled(
                        reminder,
                        "Outside WhatsApp 24-hour customer service window",
                    )
                    continue

                # Platform-engagement experiment: for dashboard-nudged
                # batches, point follow-up reminders at the dashboard (deep
                # link) instead of re-sending the question in chat. Falls back
                # to the in-chat reminder for template reminders (which have
                # their own WhatsApp-window handling) or when no link can be
                # built.
                dashboard_link = (
                    None
                    if template_reminder
                    else resolve_dashboard_nudge(db, participant)
                )
                try:
                    if dashboard_link:
                        response = send_provider_text_message(
                            db, participant, question_reminder_message(dashboard_link)
                        )
                    else:
                        response = send_provider_reminder(
                            db, participant, assignment, reminder
                        )
                except Exception as exc:
                    mark_reminder_for_retry(reminder, str(exc))
                    continue

                reminder.status = ReminderStatus.SENT.value
                reminder.sent_at = utc_now()
                reminder.updated_at = reminder.sent_at
                reminder.delivery_metadata = {
                    **(reminder.delivery_metadata or {}),
                    "http_status": response.status_code,
                }
                if provider_name == "whatsapp" and is_template_reminder(reminder):
                    create_next_template_reminder(db, reminder, assignment, participant)
                if participant_session:
                    participant_session.last_reminder_sent_at = reminder.sent_at

                db.add(
                    ParticipantEvent(
                        participant_id=participant.id,
                        event_type="reminder_sent",
                        source="scheduler",
                        event_metadata={
                            "reminder_id": reminder.id,
                            "assignment_id": assignment.id,
                            "reminder_type": reminder.reminder_type,
                            "provider": getattr(response, "provider", provider_name),
                            "nudge_surface": "dashboard" if dashboard_link else "messenger",
                            "scheduled_for": reminder.scheduled_for.isoformat(),
                            "sent_at": reminder.sent_at.isoformat(),
                        },
                    )
                )
                processed_count += 1

            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logging.exception("Failed to process due reminders")
            raise

    return processed_count


def reminder_scheduler_loop():
    logging.info("Reminder scheduler started")
    while True:
        try:
            process_due_reminders()
        except Exception:
            logging.exception("Reminder scheduler tick failed")
        time.sleep(get_reminder_poll_interval_seconds())


def start_reminder_scheduler(app=None):
    global _scheduler_started, _flask_app

    _flask_app = app

    if not reminders_enabled():
        logging.info("Reminder scheduler disabled")
        return

    with _scheduler_lock:
        if _scheduler_started:
            return

        thread = threading.Thread(
            target=reminder_scheduler_loop,
            name="reminder-scheduler",
            daemon=True,
        )
        thread.start()
        _scheduler_started = True
