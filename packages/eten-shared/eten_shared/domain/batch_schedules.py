"""Pending next-batch reminder rows shared by bot and platform."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.models import Reminder, ReminderStatus, utc_now

BATCH_NEXT_ASSIGNMENT_TYPE = "batch_next_assignment"


def has_pending_next_batch_schedule(db: Session, participant_id: str) -> bool:
    return (
        db.scalars(
            select(Reminder.id).where(
                Reminder.participant_id == participant_id,
                Reminder.reminder_type == BATCH_NEXT_ASSIGNMENT_TYPE,
                Reminder.status == ReminderStatus.PENDING.value,
            )
        ).first()
        is not None
    )


def cancel_pending_next_batch_schedules(db: Session, participant_id: str, *, reason: str):
    reminders = db.scalars(
        select(Reminder).where(
            Reminder.participant_id == participant_id,
            Reminder.reminder_type == BATCH_NEXT_ASSIGNMENT_TYPE,
            Reminder.status == ReminderStatus.PENDING.value,
        )
    ).all()
    for reminder in reminders:
        reminder.status = ReminderStatus.CANCELLED.value
        reminder.failure_reason = reason
        reminder.updated_at = utc_now()
