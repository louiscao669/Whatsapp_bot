"""WhatsApp-specific reminder cadence and sendability policy."""

import os
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from eten_shared.models import Reminder, ReminderStatus, utc_now


REMINDER_SEQUENCE = (
    ("assignment_pending_3h", timedelta(hours=3)),
    ("assignment_pending_9h", timedelta(hours=9)),
    ("assignment_pending_21h", timedelta(hours=21)),
)
TEMPLATE_REMINDER_TYPE = "assignment_template_reminder"
BATCH_NEXT_ASSIGNMENT_TYPE = "batch_next_assignment"
CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)
BATCH_NEXT_START_NOW_REPLY = "batch_next_start_now"
BATCH_NEXT_WAIT_REPLY = "batch_next_wait_tomorrow"
DEFAULT_BATCH_NEXT_ASSIGN_HOUR = 8
DEFAULT_BATCH_NEXT_ASSIGN_TIMEZONE = "UTC"
EARLY_MORNING_BATCH_NEXT_HOUR = 0
START_NOW_RESPONSES = frozenset(
    {
        BATCH_NEXT_START_NOW_REPLY,
        "start",
        "start now",
        "now",
        "new batch",
        "next batch",
        "begin",
        "yes",
        "y",
    }
)
WAIT_RESPONSES = frozenset(
    {
        BATCH_NEXT_WAIT_REPLY,
        "wait",
        "wait until tomorrow",
        "tomorrow",
        "tomorrow 8",
        "tomorrow at 8",
        "no",
        "n",
    }
)


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


def build_reminder_message(reminder_type):
    if reminder_type == "assignment_pending_3h":
        return "Reminder: you have a question waiting. Reply when you are ready."
    if reminder_type == "assignment_pending_9h":
        return "Reminder: your question is still waiting. Your answer helps validate this translation."
    if reminder_type == "assignment_pending_21h":
        return "Final reminder for this question. Reply when you can, or ignore this message to skip for now."
    return f"Template reminder: {get_reminder_template_name()}"


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
                    "provider": "whatsapp",
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
                    "provider": "whatsapp",
                    "template_name": get_reminder_template_name(),
                    "template_language": get_reminder_template_language(),
                    "template_count": 1,
                },
            )
        )


def get_batch_next_assign_hour() -> int:
    raw = (
        os.getenv("BATCH_NEXT_ASSIGN_HOUR")
        or str(DEFAULT_BATCH_NEXT_ASSIGN_HOUR)
    ).strip()
    try:
        hour = int(raw)
    except ValueError as exc:
        raise ValueError(
            "BATCH_NEXT_ASSIGN_HOUR must be a whole number from 0 through 23"
        ) from exc

    if hour < 0 or hour > 23:
        raise ValueError("BATCH_NEXT_ASSIGN_HOUR must be from 0 through 23")

    return hour


def format_hour(hour):
    if hour == 0:
        return "12 AM"
    if hour < 12:
        return f"{hour} AM"
    if hour == 12:
        return "12 PM"
    return f"{hour - 12} PM"


def format_batch_next_assign_hour():
    return format_hour(get_batch_next_assign_hour())


def get_batch_next_assign_default_timezone() -> str:
    return (
        os.getenv("BATCH_NEXT_ASSIGN_DEFAULT_TIMEZONE")
        or os.getenv("MESSAGE_BOT_DEFAULT_TIMEZONE")
        or DEFAULT_BATCH_NEXT_ASSIGN_TIMEZONE
    ).strip()


def get_participant_timezone(participant):
    candidates = [
        getattr(participant, "timezone", None),
        get_batch_next_assign_default_timezone(),
        DEFAULT_BATCH_NEXT_ASSIGN_TIMEZONE,
    ]
    for candidate in candidates:
        timezone_name = (candidate or "").strip()
        if not timezone_name:
            continue
        try:
            return timezone_name, ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            continue

    return DEFAULT_BATCH_NEXT_ASSIGN_TIMEZONE, ZoneInfo(DEFAULT_BATCH_NEXT_ASSIGN_TIMEZONE)


def batch_next_response_choice(message_text):
    normalized = " ".join(str(message_text or "").strip().lower().split())
    if normalized in START_NOW_RESPONSES:
        return "start_now"
    if normalized in WAIT_RESPONSES:
        return "wait"
    return None


def next_batch_assignment_time(participant, now=None):
    now_utc = now or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    timezone_name, participant_tz = get_participant_timezone(participant)
    local_now = now_utc.astimezone(participant_tz)
    configured_hour = get_batch_next_assign_hour()
    scheduled_hour = configured_hour
    schedule_reason = "next_day_configured_hour"

    if 0 <= local_now.hour < configured_hour:
        scheduled_hour = EARLY_MORNING_BATCH_NEXT_HOUR
        schedule_reason = "early_morning_midnight_to_preserve_whatsapp_window"

    scheduled_local = (local_now + timedelta(days=1)).replace(
        hour=scheduled_hour,
        minute=0,
        second=0,
        microsecond=0,
    )
    return (
        scheduled_local.astimezone(timezone.utc),
        scheduled_local,
        timezone_name,
        schedule_reason,
    )


def is_template_reminder(reminder):
    return (reminder.delivery_metadata or {}).get("message_kind") == "template"


def is_within_customer_service_window(participant):
    if not participant.last_seen_at:
        return False

    last_seen_at = participant.last_seen_at
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)

    return utc_now() - last_seen_at <= CUSTOMER_SERVICE_WINDOW
