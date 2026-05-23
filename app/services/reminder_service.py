import logging
import os
import threading
import time
from datetime import timezone, timedelta

import requests
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session_factory
from app.models import (
    AssignmentStatus,
    ParticipantEvent,
    ParticipantSession,
    Reminder,
    ReminderStatus,
    utc_now,
)


REMINDER_SEQUENCE = (
    ("assignment_pending_3h", timedelta(hours=3)),
    ("assignment_pending_9h", timedelta(hours=9)),
    ("assignment_pending_21h", timedelta(hours=21)),
)
CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)

_scheduler_started = False
_scheduler_lock = threading.Lock()


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


def get_graph_api_version():
    return os.getenv("VERSION", "v25.0")


def build_reminder_message(reminder_type):
    if reminder_type == "assignment_pending_3h":
        return "Reminder: you have a question waiting. Reply when you are ready."
    if reminder_type == "assignment_pending_9h":
        return "Reminder: your question is still waiting. Your answer helps validate this translation."
    return "Final reminder for this question. Reply when you can, or ignore this message to skip for now."


def create_assignment_reminders(db, assignment, participant):
    existing_types = set(
        db.scalars(
            select(Reminder.reminder_type).where(Reminder.assignment_id == assignment.id)
        ).all()
    )

    for reminder_type, delay in REMINDER_SEQUENCE:
        if reminder_type in existing_types:
            continue

        db.add(
            Reminder(
                participant_id=participant.id,
                assignment_id=assignment.id,
                reminder_type=reminder_type,
                message_text=build_reminder_message(reminder_type),
                status=ReminderStatus.PENDING.value,
                scheduled_for=assignment.assigned_at + delay,
                delivery_metadata={"delay_hours": int(delay.total_seconds() // 3600)},
            )
        )


def get_text_message_input(recipient, text):
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }


def send_whatsapp_text(recipient, text):
    access_token = os.getenv("ACCESS_TOKEN")
    phone_number_id = os.getenv("PHONE_NUMBER_ID")
    if not access_token or not phone_number_id:
        raise RuntimeError("ACCESS_TOKEN and PHONE_NUMBER_ID are required to send reminders")

    url = (
        f"https://graph.facebook.com/{get_graph_api_version()}/"
        f"{phone_number_id}/messages"
    )
    response = requests.post(
        url,
        json=get_text_message_input(recipient, text),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response


def is_within_customer_service_window(participant):
    if not participant.last_seen_at:
        return False

    last_seen_at = participant.last_seen_at
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)

    return utc_now() - last_seen_at <= CUSTOMER_SERVICE_WINDOW


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

            for reminder in reminders:
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

                if not is_within_customer_service_window(participant):
                    mark_reminder_cancelled(
                        reminder,
                        "Outside WhatsApp 24-hour customer service window",
                    )
                    continue

                try:
                    response = send_whatsapp_text(
                        participant.wa_id,
                        reminder.message_text,
                    )
                except requests.RequestException as exc:
                    mark_reminder_for_retry(reminder, str(exc))
                    continue

                reminder.status = ReminderStatus.SENT.value
                reminder.sent_at = utc_now()
                reminder.updated_at = reminder.sent_at
                reminder.delivery_metadata = {
                    **(reminder.delivery_metadata or {}),
                    "http_status": response.status_code,
                }
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
    global _scheduler_started

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
