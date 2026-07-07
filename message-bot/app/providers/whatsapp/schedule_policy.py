"""WhatsApp-specific reminder cadence and sendability policy."""

import os
from collections import Counter
from datetime import timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import desc, select

from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    ParticipantEvent,
    ParticipantResponse,
    Reminder,
    ReminderStatus,
    utc_now,
)


LEGACY_REMINDER_SEQUENCE = (
    ("assignment_pending_3h", timedelta(hours=3)),
    ("assignment_pending_9h", timedelta(hours=9)),
    ("assignment_pending_21h", timedelta(hours=21)),
)
RULE_BASED_REMINDER_SEQUENCE = (
    ("assignment_pending_rule_1", 1),
    ("assignment_pending_rule_2", 2),
)
QUESTION_REMINDER_TYPES = tuple(
    reminder_type
    for reminder_type, _ in LEGACY_REMINDER_SEQUENCE + RULE_BASED_REMINDER_SEQUENCE
)
MAX_QUESTION_REMINDERS = 2
QUESTION_REMINDER_WINDOW = timedelta(hours=24)
QUESTION_REMINDER_SCHEDULE_BUFFER = timedelta(minutes=15)
MIN_QUESTION_REMINDER_SPACING = timedelta(hours=3)
DEFAULT_HISTORICAL_RESPONSE_DELAY = timedelta(hours=6)
DEFAULT_REMINDER_EFFECTIVENESS = 0.30
DEFAULT_ACTIVE_HOURS = tuple(range(9, 22))
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
    if reminder_type == "assignment_pending_rule_1":
        return "Reminder: you have a question waiting. Reply when you are ready."
    if reminder_type == "assignment_pending_rule_2":
        return "Final reminder for this question. Reply when you can, or ignore this message to skip for now."
    return f"Template reminder: {get_reminder_template_name()}"


def _as_aware_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp_timedelta(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def _round_up_to_quarter_hour(value):
    value = value.replace(second=0, microsecond=0)
    rounded_minute = ((value.minute + 14) // 15) * 15
    return value.replace(minute=0) + timedelta(minutes=rounded_minute)


def _delivery_time_for_assignment(assignment):
    return _as_aware_utc(assignment.assigned_at) or utc_now()


def _question_reminder_deadline(assignment, *, scheduling=False):
    deadline = _delivery_time_for_assignment(assignment) + QUESTION_REMINDER_WINDOW
    if scheduling:
        deadline -= QUESTION_REMINDER_SCHEDULE_BUFFER
    return deadline


def _is_question_text_reminder(reminder):
    metadata = reminder.delivery_metadata or {}
    if metadata.get("message_kind") and metadata.get("message_kind") != "text":
        return False
    return reminder.assignment_id and reminder.reminder_type in QUESTION_REMINDER_TYPES


def _get_participant_zoneinfo(participant):
    _, participant_tz = get_participant_timezone(participant)
    return participant_tz


def _typical_active_hours(db, participant):
    participant_tz = _get_participant_zoneinfo(participant)
    hour_counts = Counter()

    response_times = db.scalars(
        select(ParticipantResponse.received_at)
        .where(ParticipantResponse.participant_id == participant.id)
        .order_by(desc(ParticipantResponse.received_at))
        .limit(100)
    ).all()
    for timestamp in response_times:
        timestamp = _as_aware_utc(timestamp)
        if timestamp:
            hour_counts[timestamp.astimezone(participant_tz).hour] += 2

    if len(hour_counts) < 3:
        event_times = db.scalars(
            select(ParticipantEvent.created_at)
            .where(
                ParticipantEvent.participant_id == participant.id,
                ParticipantEvent.event_type.in_(
                    ("message_received", "response_recorded")
                ),
            )
            .order_by(desc(ParticipantEvent.created_at))
            .limit(100)
        ).all()
        for timestamp in event_times:
            timestamp = _as_aware_utc(timestamp)
            if timestamp:
                hour_counts[timestamp.astimezone(participant_tz).hour] += 1

    if not hour_counts:
        return list(DEFAULT_ACTIVE_HOURS), "default_active_hours"

    active_hours = set()
    for hour, _ in hour_counts.most_common(4):
        active_hours.update(((hour - 1) % 24, hour, (hour + 1) % 24))
    return sorted(active_hours), "participant_activity_history"


def _historical_response_delay(db, participant):
    rows = db.execute(
        select(Assignment.assigned_at, ParticipantResponse.received_at)
        .join(
            ParticipantResponse,
            ParticipantResponse.assignment_id == Assignment.id,
        )
        .where(
            Assignment.participant_id == participant.id,
            ParticipantResponse.received_at.is_not(None),
        )
        .order_by(desc(ParticipantResponse.received_at))
        .limit(50)
    ).all()

    delays = []
    for assigned_at, received_at in rows:
        assigned_at = _as_aware_utc(assigned_at)
        received_at = _as_aware_utc(received_at)
        if not assigned_at or not received_at or received_at <= assigned_at:
            continue
        delay = received_at - assigned_at
        if timedelta(minutes=1) <= delay <= timedelta(hours=72):
            delays.append(delay)

    if not delays:
        return DEFAULT_HISTORICAL_RESPONSE_DELAY, "default_response_delay"

    return median(delays), "participant_response_history"


def _historical_reminder_effectiveness(db, participant):
    sent_reminders = db.scalars(
        select(Reminder)
        .where(
            Reminder.participant_id == participant.id,
            Reminder.status == ReminderStatus.SENT.value,
            Reminder.sent_at.is_not(None),
            Reminder.assignment_id.is_not(None),
            Reminder.reminder_type.in_(QUESTION_REMINDER_TYPES),
        )
        .order_by(desc(Reminder.sent_at))
        .limit(30)
    ).all()
    if not sent_reminders:
        return DEFAULT_REMINDER_EFFECTIVENESS, "default_reminder_effectiveness"

    effective_count = 0
    for reminder in sent_reminders:
        sent_at = _as_aware_utc(reminder.sent_at)
        if not sent_at:
            continue
        responded = db.scalars(
            select(ParticipantResponse.id)
            .where(
                ParticipantResponse.assignment_id == reminder.assignment_id,
                ParticipantResponse.received_at >= sent_at,
                ParticipantResponse.received_at <= sent_at + timedelta(hours=4),
            )
            .limit(1)
        ).first()
        if responded:
            effective_count += 1

    return effective_count / len(sent_reminders), "participant_reminder_history"


def _unanswered_assignment_count(db, participant):
    return len(
        db.scalars(
            select(Assignment.id).where(
                Assignment.participant_id == participant.id,
                Assignment.status.in_(
                    (
                        AssignmentStatus.ASSIGNED.value,
                        AssignmentStatus.IN_PROGRESS.value,
                    )
                ),
            )
        ).all()
    )


def _question_feature_adjustment(assignment):
    qa_item = assignment.qa_item
    question_type = (getattr(qa_item, "question_type", None) or "").lower()
    difficulty = (getattr(qa_item, "difficulty", None) or "").lower()

    adjustment = timedelta()
    if question_type in {"mcq", "tf"}:
        adjustment -= timedelta(minutes=30)
    elif question_type == "open":
        adjustment += timedelta(minutes=30)

    if difficulty == "hard":
        adjustment += timedelta(hours=1)
    elif difficulty == "easy":
        adjustment -= timedelta(minutes=30)

    return adjustment, question_type or None, difficulty or None


def _snap_to_typical_active_hour(
    raw_target,
    active_hours,
    participant,
    *,
    earliest,
    deadline,
):
    raw_target = _as_aware_utc(raw_target)
    earliest = _as_aware_utc(earliest)
    deadline = _as_aware_utc(deadline)
    if raw_target is None or earliest is None or deadline is None:
        return None

    participant_tz = _get_participant_zoneinfo(participant)
    active_hours = sorted(set(active_hours or DEFAULT_ACTIVE_HOURS))
    raw_local = raw_target.astimezone(participant_tz)
    earliest_local = earliest.astimezone(participant_tz)
    deadline_local = deadline.astimezone(participant_tz)
    rounded_minute = _round_up_to_quarter_hour(raw_local).minute

    if raw_local.hour in active_hours:
        candidate = _round_up_to_quarter_hour(raw_target)
        return min(max(candidate, earliest), deadline)

    future_candidates = []
    for day_offset in range(3):
        candidate_date = raw_local.date() + timedelta(days=day_offset)
        for hour in active_hours:
            candidate_local = raw_local.replace(
                year=candidate_date.year,
                month=candidate_date.month,
                day=candidate_date.day,
                hour=hour,
                minute=rounded_minute,
                second=0,
                microsecond=0,
            )
            if max(raw_local, earliest_local) <= candidate_local <= deadline_local:
                future_candidates.append(candidate_local)

    if future_candidates:
        return min(future_candidates).astimezone(timezone.utc)

    earlier_candidates = []
    for day_offset in range(3):
        candidate_date = raw_local.date() - timedelta(days=day_offset)
        for hour in active_hours:
            candidate_local = raw_local.replace(
                year=candidate_date.year,
                month=candidate_date.month,
                day=candidate_date.day,
                hour=hour,
                minute=rounded_minute,
                second=0,
                microsecond=0,
            )
            if earliest_local <= candidate_local <= raw_local:
                earlier_candidates.append(candidate_local)

    if earlier_candidates:
        return max(earlier_candidates).astimezone(timezone.utc)

    return min(max(_round_up_to_quarter_hour(raw_target), earliest), deadline)


def _rule_based_reminder_schedule(db, assignment, participant):
    delivered_at = _delivery_time_for_assignment(assignment)
    now = utc_now()
    earliest = max(now + timedelta(minutes=5), delivered_at + timedelta(minutes=30))
    deadline = _question_reminder_deadline(assignment, scheduling=True)
    if earliest >= deadline:
        return []

    active_hours, active_hours_source = _typical_active_hours(db, participant)
    historical_delay, historical_delay_source = _historical_response_delay(db, participant)
    effectiveness, effectiveness_source = _historical_reminder_effectiveness(db, participant)
    unanswered_count = _unanswered_assignment_count(db, participant)
    current_batch_size = max(participant.preferred_batch_size or 1, 1)
    pressure = unanswered_count / current_batch_size
    question_adjustment, question_type, question_difficulty = _question_feature_adjustment(
        assignment
    )

    pressure_adjustment = timedelta()
    if pressure >= 1.5:
        pressure_adjustment -= timedelta(hours=2)
    elif pressure >= 1:
        pressure_adjustment -= timedelta(hours=1)

    effectiveness_adjustment = timedelta()
    if effectiveness < 0.15:
        effectiveness_adjustment += timedelta(hours=1)
    elif effectiveness >= 0.45 and pressure >= 1:
        effectiveness_adjustment -= timedelta(minutes=30)

    first_delay = _clamp_timedelta(
        historical_delay * 1.15
        + pressure_adjustment
        + question_adjustment
        + effectiveness_adjustment,
        timedelta(hours=3),
        timedelta(hours=10),
    )

    if effectiveness < 0.15:
        second_delay = max(first_delay + timedelta(hours=6), timedelta(hours=20))
    elif effectiveness >= 0.45:
        second_delay = first_delay + timedelta(hours=5)
    else:
        second_delay = first_delay + timedelta(hours=7)
    if pressure >= 1:
        second_delay -= timedelta(hours=1)
    second_delay = _clamp_timedelta(
        second_delay,
        first_delay + MIN_QUESTION_REMINDER_SPACING,
        timedelta(hours=22),
    )

    schedule = []
    for reminder_type, sequence_number, delay in (
        ("assignment_pending_rule_1", 1, first_delay),
        ("assignment_pending_rule_2", 2, second_delay),
    ):
        raw_target = delivered_at + delay
        target = _snap_to_typical_active_hour(
            raw_target,
            active_hours,
            participant,
            earliest=earliest,
            deadline=deadline,
        )
        if not target:
            continue
        if schedule:
            minimum_time = schedule[-1]["scheduled_for"] + MIN_QUESTION_REMINDER_SPACING
            if target < minimum_time:
                target = _snap_to_typical_active_hour(
                    minimum_time,
                    active_hours,
                    participant,
                    earliest=minimum_time,
                    deadline=deadline,
                )
        if not target or target > deadline:
            continue

        schedule.append(
            {
                "reminder_type": reminder_type,
                "sequence_number": sequence_number,
                "scheduled_for": target,
                "raw_target": raw_target,
                "delay": target - delivered_at,
                "metadata": {
                    "message_kind": "text",
                    "provider": "whatsapp",
                    "schedule_policy": "rule_based_v1",
                    "sequence_number": sequence_number,
                    "max_question_reminders": MAX_QUESTION_REMINDERS,
                    "question_window_hours": int(
                        QUESTION_REMINDER_WINDOW.total_seconds() // 3600
                    ),
                    "raw_target_at": raw_target.isoformat(),
                    "active_hours": active_hours,
                    "active_hours_source": active_hours_source,
                    "historical_response_delay_hours": round(
                        historical_delay.total_seconds() / 3600,
                        2,
                    ),
                    "historical_response_delay_source": historical_delay_source,
                    "reminder_effectiveness": round(effectiveness, 3),
                    "reminder_effectiveness_source": effectiveness_source,
                    "unanswered_questions": unanswered_count,
                    "current_batch_size": current_batch_size,
                    "backlog_pressure": round(pressure, 3),
                    "question_type": question_type,
                    "question_difficulty": question_difficulty,
                    "delay_hours": round((target - delivered_at).total_seconds() / 3600, 2),
                },
            }
        )

    return schedule[:MAX_QUESTION_REMINDERS]


def _cancel_extra_or_late_question_reminders(db, assignment):
    reminders = db.scalars(
        select(Reminder)
        .where(
            Reminder.assignment_id == assignment.id,
            Reminder.status == ReminderStatus.PENDING.value,
            Reminder.reminder_type.in_(QUESTION_REMINDER_TYPES),
        )
        .order_by(Reminder.scheduled_for)
    ).all()
    deadline = _question_reminder_deadline(assignment)
    valid_count = 0
    for reminder in reminders:
        scheduled_for = _as_aware_utc(reminder.scheduled_for)
        if scheduled_for and scheduled_for > deadline:
            reminder.status = ReminderStatus.CANCELLED.value
            reminder.failure_reason = "Outside 24-hour question reminder window"
            reminder.updated_at = utc_now()
            continue
        valid_count += 1
        if valid_count > MAX_QUESTION_REMINDERS:
            reminder.status = ReminderStatus.CANCELLED.value
            reminder.failure_reason = "Question reminder cap reached"
            reminder.updated_at = utc_now()


def create_assignment_reminders(db, assignment, participant):
    existing_reminders = db.scalars(
        select(Reminder).where(Reminder.assignment_id == assignment.id)
    ).all()
    existing_types = {reminder.reminder_type for reminder in existing_reminders}
    existing_question_reminders = [
        reminder for reminder in existing_reminders if _is_question_text_reminder(reminder)
    ]

    if not existing_question_reminders:
        for reminder_config in _rule_based_reminder_schedule(db, assignment, participant):
            reminder_type = reminder_config["reminder_type"]
            if reminder_type in existing_types:
                continue

            db.add(
                Reminder(
                    participant_id=participant.id,
                    assignment_id=assignment.id,
                    reminder_type=reminder_type,
                    message_text=build_reminder_message(reminder_type),
                    status=ReminderStatus.PENDING.value,
                    scheduled_for=reminder_config["scheduled_for"],
                    delivery_metadata=reminder_config["metadata"],
                )
            )
    _cancel_extra_or_late_question_reminders(db, assignment)

    existing_types = set(
        db.scalars(
            select(Reminder.reminder_type).where(Reminder.assignment_id == assignment.id)
        ).all()
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


def question_reminder_sent_count(db, assignment_id):
    return len(
        db.scalars(
            select(Reminder.id).where(
                Reminder.assignment_id == assignment_id,
                Reminder.status == ReminderStatus.SENT.value,
                Reminder.reminder_type.in_(QUESTION_REMINDER_TYPES),
            )
        ).all()
    )


def can_send_question_reminder(db, reminder, assignment):
    if not _is_question_text_reminder(reminder):
        return True, None

    now = utc_now()
    deadline = _question_reminder_deadline(assignment)
    if now > deadline:
        return False, "Outside 24-hour question reminder window"

    if question_reminder_sent_count(db, assignment.id) >= MAX_QUESTION_REMINDERS:
        return False, "Question reminder cap reached"

    return True, None


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
