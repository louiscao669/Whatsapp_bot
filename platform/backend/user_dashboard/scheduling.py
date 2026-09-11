"""Dashboard scheduling services."""

from ._common import *  # noqa: F401,F403

def _next_batch_hour():
    raw = os.getenv("BATCH_NEXT_ASSIGN_HOUR", str(DEFAULT_NEXT_BATCH_HOUR)).strip()
    try:
        hour = int(raw)
    except ValueError:
        return DEFAULT_NEXT_BATCH_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_NEXT_BATCH_HOUR


def _participant_zone(participant):
    for candidate in (
        getattr(participant, "timezone", None),
        os.getenv("BATCH_NEXT_ASSIGN_DEFAULT_TIMEZONE"),
        os.getenv("MESSAGE_BOT_DEFAULT_TIMEZONE"),
        DEFAULT_NEXT_BATCH_TIMEZONE,
    ):
        name = (candidate or "").strip()
        if not name:
            continue
        try:
            return name, ZoneInfo(name)
        except ZoneInfoNotFoundError:
            continue
    return DEFAULT_NEXT_BATCH_TIMEZONE, ZoneInfo(DEFAULT_NEXT_BATCH_TIMEZONE)


def _next_batch_scheduled_time(participant):
    timezone_name, participant_tz = _participant_zone(participant)
    local_now = utc_now().astimezone(participant_tz)
    scheduled_local = (local_now + timedelta(days=1)).replace(
        hour=_next_batch_hour(),
        minute=0,
        second=0,
        microsecond=0,
    )
    return scheduled_local.astimezone(timezone.utc), scheduled_local, timezone_name


def _pending_next_batch_reminder(db, participant_id):
    return db.scalars(
        select(Reminder)
        .where(
            Reminder.participant_id == participant_id,
            Reminder.reminder_type == BATCH_NEXT_ASSIGNMENT_TYPE,
            Reminder.status == ReminderStatus.PENDING.value,
        )
        .order_by(Reminder.scheduled_for.asc())
    ).first()


def _schedule_dashboard_next_batch(db, participant):
    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason="Superseded by dashboard batch-completion schedule",
    )
    scheduled_for, scheduled_local, timezone_name = _next_batch_scheduled_time(participant)
    reminder = Reminder(
        participant_id=participant.id,
        assignment_id=None,
        reminder_type=BATCH_NEXT_ASSIGNMENT_TYPE,
        message_text="Auto-assign next dashboard batch after completion",
        status=ReminderStatus.PENDING.value,
        scheduled_for=scheduled_for,
        delivery_metadata={
            "schedule": "next_day_local_time",
            "local_time": scheduled_local.isoformat(),
            "timezone": timezone_name,
            "source_surface": "user_dashboard",
        },
    )
    db.add(reminder)
    db.flush()
    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="batch_next_scheduled",
            source="user_dashboard",
            event_metadata={
                "reminder_id": reminder.id,
                "scheduled_for": scheduled_for.isoformat(),
                "scheduled_local": scheduled_local.isoformat(),
                "timezone": timezone_name,
            },
        )
    )
    return reminder


def _assign_dashboard_next_batch(db, participant, *, source, reminder=None):
    from backend.shared.assignment_selection import select_next_participant_qa_item
    from backend.shared.assignment_selection import experiment_assignment_kwargs

    participant_session = get_or_create_participant_session(db, participant)
    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        raise DashboardAnswerError("Finish the current question before starting a new batch")

    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason=f"Dashboard next batch started by {source}",
    )
    participant_session.current_assignment_id = assignment.next_assignment_id
    participant_session.current_batch_id = None
    participant_session.state = SessionState.IDLE.value

    assignment = get_incomplete_assignment(db, participant)
    if assignment:
        qa_item = db.get(QAItem, assignment.qa_item_id)
        if not qa_item:
            raise DashboardAnswerError("Queued question is no longer available")
        participant_session.current_assignment_id = assignment.id
        participant_session.current_batch_id = assignment.batch_id
        participant_session.state = SessionState.AWAITING_RESPONSE.value
        participant_session.last_prompt_sent_at = utc_now()
        newly_assigned = False
    else:
        if not (automatic_assignment_enabled() or experiment_assignment_enabled()):
            raise DashboardAnswerError("Automatic assignment is currently disabled")
        qa_item, cell = select_next_participant_qa_item(db, participant)
        if not qa_item:
            raise DashboardAnswerError("No eligible question is available for a new batch")

        prompt = create_assignment_for_qa_item(
            db,
            participant,
            participant_session,
            qa_item,
            completed_batch_size=0,
            assignment_source=source,
            **experiment_assignment_kwargs(db, participant_session, cell, qa_item),
        )
        assignment = db.get(Assignment, prompt.assignment_id)
        newly_assigned = True
    # The question is now available on the dashboard. Stamp delivery here —
    # this is EARLIER than started_at (set when the participant opens the
    # question card, see mark_dashboard_question_viewed), so the gap
    # delivered_at -> started_at measures dashboard wait time.
    assignment.delivered_at = assignment.delivered_at or utc_now()
    if reminder:
        reminder.status = ReminderStatus.SENT.value
        reminder.sent_at = utc_now()
        reminder.updated_at = reminder.sent_at
    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="batch_next_delivered",
            source="user_dashboard",
            event_metadata={
                "assignment_id": assignment.id,
                "qa_item_id": qa_item.id,
                "batch_id": assignment.batch_id,
                "reminder_id": reminder.id if reminder else None,
                "delivery": source,
                "assigned": newly_assigned,
            },
        )
    )
    db.flush()
    return assignment


def _materialize_due_dashboard_next_batch(db, participant):
    reminder = _pending_next_batch_reminder(db, participant.id)
    if not reminder or reminder.scheduled_for > utc_now():
        return None
    try:
        return _assign_dashboard_next_batch(
            db,
            participant,
            source="scheduled",
            reminder=reminder,
        )
    except DashboardAnswerError as exc:
        reminder.status = ReminderStatus.FAILED.value
        reminder.failure_reason = str(exc)
        reminder.updated_at = utc_now()
        return None


