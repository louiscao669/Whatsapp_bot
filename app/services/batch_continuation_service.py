"""Schedule and deliver the next question batch after batch completion."""

import os
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Participant, ParticipantEvent, Reminder, ReminderStatus, SessionState, utc_now

BATCH_NEXT_ASSIGNMENT_TYPE = "batch_next_assignment"
MAX_BATCH_NEXT_ASSIGN_DELAY_MINUTES = (23 * 60) + (59)  # 23h 59m


def get_batch_next_assign_delay_minutes() -> int:
    raw = (os.getenv("BATCH_NEXT_ASSIGN_DELAY_MINUTES") or "0").strip()
    try:
        delay = int(raw)
    except ValueError as exc:
        raise ValueError(
            "BATCH_NEXT_ASSIGN_DELAY_MINUTES must be a whole number of minutes"
        ) from exc

    if delay < 0:
        raise ValueError("BATCH_NEXT_ASSIGN_DELAY_MINUTES cannot be negative")

    if delay > MAX_BATCH_NEXT_ASSIGN_DELAY_MINUTES:
        raise ValueError(
            "BATCH_NEXT_ASSIGN_DELAY_MINUTES cannot exceed 23 hours 59 minutes "
            f"({MAX_BATCH_NEXT_ASSIGN_DELAY_MINUTES} minutes)"
        )

    return delay


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


def schedule_next_batch_assignment(db: Session, participant, participant_session):
    """Schedule the next batch via the reminder scheduler (delay 0 = due on next poll)."""
    delay_minutes = get_batch_next_assign_delay_minutes()

    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason="Superseded by a new batch-completion schedule",
    )

    scheduled_for = utc_now() + timedelta(minutes=delay_minutes)
    reminder = Reminder(
        participant_id=participant.id,
        assignment_id=None,
        reminder_type=BATCH_NEXT_ASSIGNMENT_TYPE,
        message_text="Auto-assign next batch after completion",
        status=ReminderStatus.PENDING.value,
        scheduled_for=scheduled_for,
        delivery_metadata={"delay_minutes": delay_minutes},
    )
    db.add(reminder)
    db.flush()

    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="batch_next_scheduled",
            source="workflow",
            event_metadata={
                "reminder_id": reminder.id,
                "scheduled_for": scheduled_for.isoformat(),
                "delay_minutes": delay_minutes,
            },
        )
    )
    return reminder


def process_batch_next_assignment_reminder(db: Session, reminder: Reminder):
    """
    Create the next-batch assignment for a due reminder.
    Returns an AssignmentPrompt when a question was assigned, else None.
    """
    from app.services.chatbot_workflow import create_assignment_prompt
    from app.services.reminder_service import (
        is_within_customer_service_window,
        mark_reminder_cancelled,
    )

    participant = reminder.participant
    if not participant:
        mark_reminder_cancelled(reminder, "Participant no longer exists")
        return None

    participant_session = participant.session
    if not participant_session:
        mark_reminder_cancelled(reminder, "Participant session no longer exists")
        return None

    if participant_session.opted_out_at:
        mark_reminder_cancelled(reminder, "Participant opted out")
        return None

    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        mark_reminder_cancelled(
            reminder,
            f"Participant session is {participant_session.state}, not idle",
        )
        return None

    if not is_within_customer_service_window(participant):
        mark_reminder_cancelled(
            reminder,
            "Outside WhatsApp 24-hour customer service window",
        )
        return None

    reminder.status = ReminderStatus.SENT.value
    reminder.sent_at = utc_now()
    reminder.updated_at = reminder.sent_at

    prompt, _, _ = create_assignment_prompt(db, participant, participant_session)
    if not prompt:
        reminder.failure_reason = "No eligible question available for next batch"
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type="batch_next_delivered",
                source="scheduler",
                event_metadata={
                    "reminder_id": reminder.id,
                    "delivery": "scheduled",
                    "assigned": False,
                },
            )
        )
        return None

    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="batch_next_delivered",
            source="scheduler",
            event_metadata={
                "reminder_id": reminder.id,
                "assignment_id": prompt.assignment_id,
                "qa_item_id": prompt.qa_item_id,
                "delivery": "scheduled",
                "assigned": True,
            },
        )
    )
    return prompt
