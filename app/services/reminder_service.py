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
TEMPLATE_REMINDER_TYPE = "assignment_template_reminder"
CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)

_scheduler_started = False
_scheduler_lock = threading.Lock()
_flask_app = None


def get_reminder_poll_interval_seconds():
    return int(os.getenv("REMINDER_POLL_INTERVAL_SECONDS", "300"))


def get_reminder_max_retries():
    return int(os.getenv("REMINDER_MAX_RETRIES", "3"))


def get_reminder_template_name():
    return os.getenv("REMINDER_TEMPLATE_NAME")


def get_reminder_template_language():
    return os.getenv("REMINDER_TEMPLATE_LANGUAGE", "en_US")


def get_template_reminder_first_delay():
    return timedelta(hours=int(os.getenv("REMINDER_TEMPLATE_FIRST_DELAY_HOURS", "48")))


def get_template_reminder_repeat_delay():
    return timedelta(hours=int(os.getenv("REMINDER_TEMPLATE_REPEAT_HOURS", "48")))


def get_template_reminder_max_count():
    return int(os.getenv("REMINDER_TEMPLATE_MAX_COUNT", "0"))


def template_reminders_enabled():
    return bool(get_reminder_template_name())


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
    if reminder_type == "assignment_pending_21h":
        return "Final reminder for this question. Reply when you can, or ignore this message to skip for now."
    return f"Template reminder: {get_reminder_template_name()}"


def is_template_reminder(reminder):
    return (reminder.delivery_metadata or {}).get("message_kind") == "template"


def get_template_body_parameters(participant, assignment, reminder):
    configured_value = os.getenv("REMINDER_TEMPLATE_BODY_PARAMS", "")
    if not configured_value.strip():
        return []

    context = {
        "name": participant.display_name or "there",
        "wa_id": participant.wa_id,
        "assignment_id": assignment.id if assignment else "",
        "reminder_type": reminder.reminder_type if reminder else "",
    }
    return [
        value.strip().format(**context)
        for value in configured_value.split(",")
        if value.strip()
    ]


def build_template_message_input(recipient, template_name, language_code, body_parameters=None):
    template = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if body_parameters:
        template["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": value} for value in body_parameters
                ],
            }
        ]

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "template",
        "template": template,
    }


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
                delivery_metadata={
                    "delay_hours": int(delay.total_seconds() // 3600),
                    "message_kind": "text",
                },
            )
        )

    if template_reminders_enabled() and TEMPLATE_REMINDER_TYPE not in existing_types:
        first_delay = get_template_reminder_first_delay()
        db.add(
            Reminder(
                participant_id=participant.id,
                assignment_id=assignment.id,
                reminder_type=TEMPLATE_REMINDER_TYPE,
                message_text=build_reminder_message(TEMPLATE_REMINDER_TYPE),
                status=ReminderStatus.PENDING.value,
                scheduled_for=assignment.assigned_at + first_delay,
                delivery_metadata={
                    "delay_hours": int(first_delay.total_seconds() // 3600),
                    "message_kind": "template",
                    "template_name": get_reminder_template_name(),
                    "template_language": get_reminder_template_language(),
                    "template_count": 1,
                },
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


def send_whatsapp_message(payload):
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
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response


def send_whatsapp_text(recipient, text):
    return send_whatsapp_message(get_text_message_input(recipient, text))


def send_whatsapp_template(recipient, participant, assignment, reminder):
    template_name = (reminder.delivery_metadata or {}).get("template_name") or get_reminder_template_name()
    if not template_name:
        raise RuntimeError("REMINDER_TEMPLATE_NAME is required to send template reminders")

    language_code = (
        (reminder.delivery_metadata or {}).get("template_language")
        or get_reminder_template_language()
    )
    return send_whatsapp_message(
        build_template_message_input(
            recipient=recipient,
            template_name=template_name,
            language_code=language_code,
            body_parameters=get_template_body_parameters(participant, assignment, reminder),
        )
    )


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


def create_next_template_reminder(db, reminder, assignment, participant):
    metadata = reminder.delivery_metadata or {}
    template_count = int(metadata.get("template_count", 1))
    max_count = get_template_reminder_max_count()
    if max_count and template_count >= max_count:
        return None

    repeat_delay = get_template_reminder_repeat_delay()
    next_count = template_count + 1
    next_reminder = Reminder(
        participant_id=participant.id,
        assignment_id=assignment.id,
        reminder_type=TEMPLATE_REMINDER_TYPE,
        message_text=build_reminder_message(TEMPLATE_REMINDER_TYPE),
        status=ReminderStatus.PENDING.value,
        scheduled_for=utc_now() + repeat_delay,
        delivery_metadata={
            "delay_hours": int(repeat_delay.total_seconds() // 3600),
            "message_kind": "template",
            "template_name": get_reminder_template_name(),
            "template_language": get_reminder_template_language(),
            "template_count": next_count,
            "previous_reminder_id": reminder.id,
        },
    )
    db.add(next_reminder)
    return next_reminder


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

            from app.services.batch_continuation_service import (
                BATCH_NEXT_ASSIGNMENT_TYPE,
                process_batch_next_assignment_reminder,
            )

            for reminder in reminders:
                if reminder.reminder_type == BATCH_NEXT_ASSIGNMENT_TYPE:
                    prompt = process_batch_next_assignment_reminder(db, reminder)
                    participant = reminder.participant
                    if prompt and participant:
                        if _flask_app is None:
                            logging.error(
                                "Cannot send scheduled next-batch assignment without Flask app context"
                            )
                        else:
                            from app.utils.whatsapp_utils import send_assignment_prompt

                            with _flask_app.app_context():
                                send_assignment_prompt(participant.wa_id, prompt)
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

                template_reminder = is_template_reminder(reminder)
                if (
                    not template_reminder
                    and not is_within_customer_service_window(participant)
                ):
                    mark_reminder_cancelled(
                        reminder,
                        "Outside WhatsApp 24-hour customer service window",
                    )
                    continue

                try:
                    if template_reminder:
                        response = send_whatsapp_template(
                            participant.wa_id,
                            participant,
                            assignment,
                            reminder,
                        )
                    else:
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
                if is_template_reminder(reminder):
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
