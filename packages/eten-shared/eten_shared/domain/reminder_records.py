"""DB-only assignment reminder scheduling (no WhatsApp send)."""

import os
from datetime import timedelta

from sqlalchemy import select

from eten_shared.models import Reminder, ReminderStatus

REMINDER_SEQUENCE = (
    ("assignment_pending_3h", timedelta(hours=3)),
    ("assignment_pending_9h", timedelta(hours=9)),
    ("assignment_pending_21h", timedelta(hours=21)),
)
TEMPLATE_REMINDER_TYPE = "assignment_template_reminder"


def get_reminder_template_name():
    return os.getenv("REMINDER_TEMPLATE_NAME")


def get_reminder_template_language():
    return os.getenv("REMINDER_TEMPLATE_LANGUAGE", "en_US")


def get_template_reminder_first_delay():
    return timedelta(hours=int(os.getenv("REMINDER_TEMPLATE_FIRST_DELAY_HOURS", "48")))


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
