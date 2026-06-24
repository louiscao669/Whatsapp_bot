"""Participant streak calculation and rewards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from eten_shared.models import (
    ParticipantBadge,
    ParticipantCurrencyEvent,
    ParticipantEvent,
    ParticipantResponse,
    QAItem,
    utc_now,
)


DEFAULT_TIMEZONE = "UTC"
STREAK_FREEZE_ITEM_ID = "streak_freeze"
STREAK_PAUSE_KEY = "streak_pause"
STREAK_STATUS_KEY = "streak_status"
STREAK_FREEZE_AWARDED_EVENT = "streak_freeze_awarded"
STREAK_FREEZE_USED_EVENT = "streak_freeze_used"
STREAK_PAUSE_STARTED_EVENT = "streak_pause_started"
STREAK_PAUSE_ENDED_EVENT = "streak_pause_ended"
STREAK_MILESTONE_EVENT = "streak_milestone_awarded"
STREAK_REPORT_EVENT = "streak_progress_report_created"
STREAK_PAUSE_MAX_DAYS = 7


@dataclass(frozen=True)
class StreakMilestone:
    days: int
    badge_type: str
    title: str
    description: str
    reward_summary: str
    freeze_tokens: int = 0
    resolver_status: bool = False
    progress_report: bool = False


STREAK_MILESTONES = (
    StreakMilestone(
        days=3,
        badge_type="streak_3_days",
        title="Three-Day Streak",
        description="Answered at least one question across 3 streak days.",
        reward_summary="Encouragement badge",
    ),
    StreakMilestone(
        days=7,
        badge_type="streak_7_days",
        title="Seven-Day Streak",
        description="Kept a validation streak for 7 days.",
        reward_summary="Badge + 1 streak freeze",
        freeze_tokens=1,
    ),
    StreakMilestone(
        days=14,
        badge_type="streak_14_days",
        title="Two-Week Resolver",
        description="Maintained a 14-day validation streak.",
        reward_summary="Badge + Resolver profile status",
        resolver_status=True,
    ),
    StreakMilestone(
        days=30,
        badge_type="streak_30_days",
        title="Thirty-Day Resolver",
        description="Maintained a 30-day validation streak.",
        reward_summary="Badge + personalized progress report",
        progress_report=True,
    ),
)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def participant_timezone(participant) -> tuple[str, ZoneInfo]:
    for candidate in (getattr(participant, "timezone", None), DEFAULT_TIMEZONE):
        name = (candidate or "").strip()
        if not name:
            continue
        try:
            return name, ZoneInfo(name)
        except ZoneInfoNotFoundError:
            continue
    return DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)


def local_date_for(value: datetime, participant) -> date:
    _, tz = participant_timezone(participant)
    return _ensure_aware(value).astimezone(tz).date()


def _local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _parse_iso_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _ensure_aware(parsed)


def _parse_iso_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def streak_pause_state(participant) -> dict:
    preferences = participant.dashboard_preferences or {}
    pause = dict(preferences.get(STREAK_PAUSE_KEY) or {})
    pause.setdefault("active", False)
    pause.setdefault("history", [])
    return pause


def paused_local_dates(participant, through_day: date | None = None) -> set[date]:
    pause = streak_pause_state(participant)
    _, tz = participant_timezone(participant)
    today = through_day or utc_now().astimezone(tz).date()
    periods = list(pause.get("history") or [])
    if pause.get("active") and pause.get("started_at"):
        periods.append({"started_at": pause.get("started_at"), "ended_at": None})

    days: set[date] = set()
    for period in periods:
        started_at = _parse_iso_datetime(period.get("started_at"))
        if not started_at:
            continue
        ended_at = _parse_iso_datetime(period.get("ended_at"))
        start_day = started_at.astimezone(tz).date()
        end_day = ended_at.astimezone(tz).date() if ended_at else today
        end_day = min(end_day, start_day + timedelta(days=STREAK_PAUSE_MAX_DAYS - 1))
        if end_day < start_day:
            continue
        day = start_day
        while day <= min(end_day, today):
            days.add(day)
            day += timedelta(days=1)
    return days


def activity_by_local_day(
    db: Session,
    participant,
    *,
    start_day: date | None = None,
    end_day: date | None = None,
) -> dict[date, int]:
    _, tz = participant_timezone(participant)
    statement = select(ParticipantResponse.received_at).where(
        ParticipantResponse.participant_id == participant.id
    )
    if start_day:
        start_utc, _ = _local_day_bounds(start_day, tz)
        statement = statement.where(ParticipantResponse.received_at >= start_utc)
    if end_day:
        _, end_utc = _local_day_bounds(end_day, tz)
        statement = statement.where(ParticipantResponse.received_at < end_utc)

    days: dict[date, int] = {}
    for received_at in db.scalars(statement).all():
        day = local_date_for(received_at, participant)
        days[day] = days.get(day, 0) + 1
    return days


def _freeze_purchase_count(db: Session, participant_id: str) -> int:
    events = db.scalars(
        select(ParticipantCurrencyEvent).where(
            ParticipantCurrencyEvent.participant_id == participant_id,
            ParticipantCurrencyEvent.reason == "store_purchase",
        )
    ).all()
    return sum(
        1
        for event in events
        if (event.currency_metadata or {}).get("item_id") == STREAK_FREEZE_ITEM_ID
    )


def _freeze_award_count(db: Session, participant_id: str) -> int:
    events = db.scalars(
        select(ParticipantEvent).where(
            ParticipantEvent.participant_id == participant_id,
            ParticipantEvent.event_type == STREAK_FREEZE_AWARDED_EVENT,
        )
    ).all()
    return sum(int((event.event_metadata or {}).get("count", 1) or 0) for event in events)


def _freeze_used_events(db: Session, participant_id: str):
    return db.scalars(
        select(ParticipantEvent).where(
            ParticipantEvent.participant_id == participant_id,
            ParticipantEvent.event_type == STREAK_FREEZE_USED_EVENT,
        )
    ).all()


def freeze_used_local_dates(db: Session, participant_id: str) -> set[date]:
    return {
        parsed
        for parsed in (
            _parse_iso_date((event.event_metadata or {}).get("local_date"))
            for event in _freeze_used_events(db, participant_id)
        )
        if parsed is not None
    }


def get_freeze_token_balance(db: Session, participant) -> dict:
    purchased = _freeze_purchase_count(db, participant.id)
    awarded = _freeze_award_count(db, participant.id)
    used = len(_freeze_used_events(db, participant.id))
    return {
        "available": max(purchased + awarded - used, 0),
        "purchased": purchased,
        "awarded": awarded,
        "used": used,
    }


def _streak_count(
    *,
    today: date,
    active_days: set[date],
    covered_days: set[date],
) -> int:
    if not active_days:
        return 0

    anchor = today
    if anchor not in active_days:
        yesterday = today - timedelta(days=1)
        if yesterday in active_days or yesterday in covered_days:
            anchor = yesterday

    count = 0
    day = anchor
    while True:
        if day in active_days:
            count += 1
        elif day in covered_days:
            pass
        else:
            break
        day -= timedelta(days=1)
    return count


def _weekly_streak_count(today: date, active_days: set[date]) -> int:
    if not active_days:
        return 0

    active_weeks = {(day.isocalendar().year, day.isocalendar().week) for day in active_days}
    anchor_monday = today - timedelta(days=today.weekday())
    current_week = today.isocalendar().year, today.isocalendar().week
    if current_week not in active_weeks:
        previous = today - timedelta(days=7)
        previous_week = previous.isocalendar().year, previous.isocalendar().week
        if previous_week in active_weeks:
            anchor_monday -= timedelta(days=7)

    count = 0
    week_start = anchor_monday
    while True:
        week_key = week_start.isocalendar().year, week_start.isocalendar().week
        if week_key not in active_weeks:
            break
        count += 1
        week_start -= timedelta(days=7)
    return count


def next_milestone_payload(current_streak: int) -> dict | None:
    for milestone in STREAK_MILESTONES:
        if current_streak < milestone.days:
            return {
                "days": milestone.days,
                "badge_type": milestone.badge_type,
                "title": milestone.title,
                "reward_summary": milestone.reward_summary,
                "days_remaining": milestone.days - current_streak,
                "progress": current_streak / milestone.days,
            }
    return None


def activity_heatmap(db: Session, participant, *, days: int = 91) -> list[dict]:
    _, tz = participant_timezone(participant)
    today = utc_now().astimezone(tz).date()
    start_day = today - timedelta(days=days - 1)
    activity = activity_by_local_day(db, participant, start_day=start_day, end_day=today)
    cells = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        count = activity.get(day, 0)
        cells.append(
            {
                "date": day.isoformat(),
                "count": count,
                "level": 0 if count == 0 else min(count, 4),
            }
        )
    return cells


def streak_status_payload(db: Session, participant) -> dict:
    timezone_name, tz = participant_timezone(participant)
    today = utc_now().astimezone(tz).date()
    activity = activity_by_local_day(db, participant, end_day=today)
    active_days = set(activity)
    covered_days = paused_local_dates(participant, today) | freeze_used_local_dates(
        db, participant.id
    )
    current_streak = _streak_count(
        today=today,
        active_days=active_days,
        covered_days=covered_days,
    )
    weekly_streak = _weekly_streak_count(today, active_days)
    freeze_tokens = get_freeze_token_balance(db, participant)
    pause = streak_pause_state(participant)
    preferences = participant.dashboard_preferences or {}

    return {
        "timezone": timezone_name,
        "today": today.isoformat(),
        "current_daily_streak": current_streak,
        "current_weekly_streak": weekly_streak,
        "next_milestone": next_milestone_payload(current_streak),
        "freeze_tokens": freeze_tokens,
        "pause": {
            "active": bool(pause.get("active")),
            "started_at": pause.get("started_at"),
            "max_until": pause.get("max_until"),
            "max_days": STREAK_PAUSE_MAX_DAYS,
        },
        "resolver_status": preferences.get(STREAK_STATUS_KEY),
        "heatmap": activity_heatmap(db, participant),
        "milestones": [
            {
                "days": milestone.days,
                "badge_type": milestone.badge_type,
                "title": milestone.title,
                "reward_summary": milestone.reward_summary,
            }
            for milestone in STREAK_MILESTONES
        ],
    }


def _existing_badge_types(db: Session, participant_id: str) -> set[str]:
    return set(
        db.scalars(
            select(ParticipantBadge.badge_type).where(
                ParticipantBadge.participant_id == participant_id
            )
        ).all()
    )


def _award_streak_badge(db: Session, participant, milestone: StreakMilestone):
    badge = ParticipantBadge(
        participant_id=participant.id,
        badge_type=milestone.badge_type,
        title=milestone.title,
        description=milestone.description,
        badge_metadata={
            "streak_days": milestone.days,
            "reward_summary": milestone.reward_summary,
        },
    )
    db.add(badge)
    db.flush()
    return badge


def _progress_report(db: Session, participant) -> dict:
    passages = db.execute(
        select(
            QAItem.passage_id,
            QAItem.passage_reference,
            func.count(ParticipantResponse.id).label("response_count"),
        )
        .join(QAItem, QAItem.id == ParticipantResponse.qa_item_id)
        .where(ParticipantResponse.participant_id == participant.id)
        .group_by(QAItem.passage_id, QAItem.passage_reference)
        .order_by(func.count(ParticipantResponse.id).desc(), QAItem.passage_id.asc())
        .limit(8)
    ).all()
    total_passages = db.scalar(
        select(func.count(distinct(QAItem.passage_id)))
        .join(ParticipantResponse, ParticipantResponse.qa_item_id == QAItem.id)
        .where(ParticipantResponse.participant_id == participant.id)
    )
    return {
        "total_passages_helped": int(total_passages or 0),
        "top_passages": [
            {
                "passage_id": passage_id,
                "passage_reference": passage_reference or passage_id,
                "response_count": int(response_count or 0),
            }
            for passage_id, passage_reference, response_count in passages
        ],
    }


def latest_progress_report(db: Session, participant_id: str) -> dict | None:
    event = db.scalars(
        select(ParticipantEvent)
        .where(
            ParticipantEvent.participant_id == participant_id,
            ParticipantEvent.event_type == STREAK_REPORT_EVENT,
        )
        .order_by(ParticipantEvent.created_at.desc(), ParticipantEvent.id.desc())
    ).first()
    return dict(event.event_metadata or {}) if event else None


def _use_freezes_for_gap(db: Session, participant, response) -> None:
    current_day = local_date_for(response.received_at, participant)
    activity = activity_by_local_day(db, participant, end_day=current_day)
    previous_days = sorted(day for day in activity if day < current_day)
    if not previous_days:
        return

    previous_day = previous_days[-1]
    gap_days = []
    day = previous_day + timedelta(days=1)
    paused_days = paused_local_dates(participant, current_day)
    already_used = freeze_used_local_dates(db, participant.id)
    while day < current_day:
        if day not in paused_days and day not in already_used:
            gap_days.append(day)
        day += timedelta(days=1)

    if not gap_days:
        return

    available = get_freeze_token_balance(db, participant)["available"]
    if available < len(gap_days):
        return

    for missed_day in gap_days:
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=STREAK_FREEZE_USED_EVENT,
                source="streaks",
                event_metadata={
                    "local_date": missed_day.isoformat(),
                    "trigger_response_id": response.id,
                },
            )
        )
    db.flush()


def update_streak_for_response(db: Session, participant, response) -> list[ParticipantBadge]:
    if response is None:
        return []

    db.flush()
    _use_freezes_for_gap(db, participant, response)
    status = streak_status_payload(db, participant)
    current_streak = int(status["current_daily_streak"] or 0)
    existing = _existing_badge_types(db, participant.id)
    awarded = []

    for milestone in STREAK_MILESTONES:
        if current_streak < milestone.days or milestone.badge_type in existing:
            continue

        badge = _award_streak_badge(db, participant, milestone)
        awarded.append(badge)
        existing.add(milestone.badge_type)
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=STREAK_MILESTONE_EVENT,
                source="streaks",
                event_metadata={
                    "badge_id": badge.id,
                    "badge_type": badge.badge_type,
                    "streak_days": milestone.days,
                    "reward_summary": milestone.reward_summary,
                },
            )
        )

        if milestone.freeze_tokens:
            db.add(
                ParticipantEvent(
                    participant_id=participant.id,
                    event_type=STREAK_FREEZE_AWARDED_EVENT,
                    source="streaks",
                    event_metadata={
                        "count": milestone.freeze_tokens,
                        "milestone_days": milestone.days,
                        "badge_id": badge.id,
                    },
                )
            )

        if milestone.resolver_status:
            preferences = dict(participant.dashboard_preferences or {})
            preferences[STREAK_STATUS_KEY] = "Resolver"
            participant.dashboard_preferences = preferences
            db.add(
                ParticipantEvent(
                    participant_id=participant.id,
                    event_type="streak_status_awarded",
                    source="streaks",
                    event_metadata={
                        "status": "Resolver",
                        "milestone_days": milestone.days,
                        "badge_id": badge.id,
                    },
                )
            )

        if milestone.progress_report:
            db.add(
                ParticipantEvent(
                    participant_id=participant.id,
                    event_type=STREAK_REPORT_EVENT,
                    source="streaks",
                    event_metadata={
                        "milestone_days": milestone.days,
                        "badge_id": badge.id,
                        **_progress_report(db, participant),
                    },
                )
            )

    db.flush()
    return awarded


def set_streak_pause(db: Session, participant, paused: bool) -> None:
    now = utc_now()
    _, tz = participant_timezone(participant)
    now_local_day = now.astimezone(tz).date()
    max_until = now_local_day + timedelta(days=STREAK_PAUSE_MAX_DAYS - 1)
    preferences = dict(participant.dashboard_preferences or {})
    pause = dict(preferences.get(STREAK_PAUSE_KEY) or {})
    history = list(pause.get("history") or [])
    active = bool(pause.get("active"))

    if paused and not active:
        if get_freeze_token_balance(db, participant)["available"] < 1:
            raise ValueError("No streak freezes available")

        pause = {
            "active": True,
            "started_at": now.isoformat(),
            "max_until": max_until.isoformat(),
            "history": history,
        }
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=STREAK_FREEZE_USED_EVENT,
                source="user_dashboard",
                event_metadata={
                    "reason": "streak_pause",
                    "started_at": pause["started_at"],
                    "max_until": pause["max_until"],
                    "covered_days": STREAK_PAUSE_MAX_DAYS,
                },
            )
        )
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=STREAK_PAUSE_STARTED_EVENT,
                source="user_dashboard",
                event_metadata={
                    "started_at": pause["started_at"],
                    "max_until": pause["max_until"],
                    "freeze_tokens_used": 1,
                },
            )
        )
    elif not paused and active:
        started_at = pause.get("started_at")
        max_until = pause.get("max_until")
        history.append(
            {
                "started_at": started_at,
                "ended_at": now.isoformat(),
                "max_until": max_until,
            }
        )
        pause = {
            "active": False,
            "started_at": None,
            "max_until": None,
            "history": history,
        }
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=STREAK_PAUSE_ENDED_EVENT,
                source="user_dashboard",
                event_metadata={
                    "started_at": started_at,
                    "ended_at": now.isoformat(),
                    "max_until": max_until,
                },
            )
        )
    else:
        pause["active"] = active
        pause["history"] = history

    preferences[STREAK_PAUSE_KEY] = pause
    participant.dashboard_preferences = preferences
    participant.updated_at = now
    db.flush()
