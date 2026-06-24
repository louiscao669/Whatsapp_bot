"""Schedule and deliver the next question batch after batch completion."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.models import (
    Assignment,
    ParticipantEvent,
    Reminder,
    ReminderStatus,
    SessionState,
    utc_now,
)
from app.providers.whatsapp.schedule_policy import (
    BATCH_NEXT_ASSIGNMENT_TYPE,
    BATCH_NEXT_START_NOW_REPLY,
    BATCH_NEXT_WAIT_REPLY,
    batch_next_response_choice,
    create_assignment_reminders,
    format_batch_next_assign_hour,
    is_within_customer_service_window,
    next_batch_assignment_time,
)


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
    """Schedule the next batch for the next day at the configured local hour."""

    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason="Superseded by a new batch-completion schedule",
    )

    (
        scheduled_for,
        scheduled_local,
        timezone_name,
        schedule_reason,
    ) = next_batch_assignment_time(participant)
    reminder = Reminder(
        participant_id=participant.id,
        assignment_id=None,
        reminder_type=BATCH_NEXT_ASSIGNMENT_TYPE,
        message_text="Auto-assign next batch after completion",
        status=ReminderStatus.PENDING.value,
        scheduled_for=scheduled_for,
        delivery_metadata={
            "schedule": "next_day_local_time",
            "schedule_reason": schedule_reason,
            "local_time": scheduled_local.isoformat(),
            "timezone": timezone_name,
        },
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
                "scheduled_local": scheduled_local.isoformat(),
                "timezone": timezone_name,
                "schedule_reason": schedule_reason,
            },
        )
    )
    return reminder


def process_batch_next_assignment_reminder(db: Session, reminder: Reminder):
    """
    Create the next-batch assignment for a due reminder.
    Returns an AssignmentPrompt when a question was assigned, else None.
    """
    from app.messaging.workflow import create_assignment_prompt
    from app.engagement.reminders import mark_reminder_cancelled

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

    assignment = db.get(Assignment, prompt.assignment_id)
    if assignment:
        create_assignment_reminders(db, assignment, participant)

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
