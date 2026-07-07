"""Rule-based preferred batch-size nudges."""

from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    ParticipantEvent,
    utc_now,
)

MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 10
INCREASE_EVIDENCE_DAYS = 3
DECREASE_EVIDENCE_DAYS = 5
NUDGE_COOLDOWN_DAYS = 5
DECLINE_COOLDOWN_DAYS = 7
TARGET_COMPLETION_HOURS = 24
MIN_BATCHES_FOR_DECREASE = 3

BATCH_SIZE_NUDGE_SENT_EVENT = "batch_size_nudge_sent"
BATCH_SIZE_NUDGE_ACCEPTED_EVENT = "batch_size_nudge_accepted"
BATCH_SIZE_NUDGE_DECLINED_EVENT = "batch_size_nudge_declined"
BATCH_SIZE_CHANGED_EVENT = "batch_size_changed"

BATCH_SIZE_NUDGE_ACCEPT_REPLY = "batch_size_nudge_accept"
BATCH_SIZE_NUDGE_DECLINE_REPLY = "batch_size_nudge_decline"


@dataclass(frozen=True)
class BatchSizeNudge:
    action: str
    current_size: int
    proposed_size: int
    reason: str


def clamp_batch_size(value) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = MIN_BATCH_SIZE
    return min(max(size, MIN_BATCH_SIZE), MAX_BATCH_SIZE)


def batch_size_response_choice(message_text) -> Optional[str]:
    normalized = " ".join(str(message_text or "").strip().lower().split())
    if normalized in {
        BATCH_SIZE_NUDGE_ACCEPT_REPLY,
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
    }:
        return "accept"
    if normalized in {
        BATCH_SIZE_NUDGE_DECLINE_REPLY,
        "no",
        "n",
        "not now",
        "no thanks",
        "later",
    }:
        return "decline"
    return None


def _aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _event_metadata(event):
    return event.event_metadata or {}


def _current_size_since(db: Session, participant, now):
    event = db.scalars(
        select(ParticipantEvent)
        .where(
            ParticipantEvent.participant_id == participant.id,
            ParticipantEvent.event_type == BATCH_SIZE_CHANGED_EVENT,
        )
        .order_by(ParticipantEvent.created_at.desc(), ParticipantEvent.id.desc())
    ).first()
    if event:
        return _aware(event.created_at)
    return _aware(getattr(participant, "created_at", None)) or now


def _latest_event(db: Session, participant_id: str, event_types):
    return db.scalars(
        select(ParticipantEvent)
        .where(
            ParticipantEvent.participant_id == participant_id,
            ParticipantEvent.event_type.in_(tuple(event_types)),
        )
        .order_by(ParticipantEvent.created_at.desc(), ParticipantEvent.id.desc())
    ).first()


def _cooldown_active(db: Session, participant, now) -> bool:
    last_event = _latest_event(
        db,
        participant.id,
        (
            BATCH_SIZE_NUDGE_SENT_EVENT,
            BATCH_SIZE_NUDGE_ACCEPTED_EVENT,
            BATCH_SIZE_NUDGE_DECLINED_EVENT,
            BATCH_SIZE_CHANGED_EVENT,
        ),
    )
    if not last_event:
        return False

    cooldown_days = (
        DECLINE_COOLDOWN_DAYS
        if last_event.event_type == BATCH_SIZE_NUDGE_DECLINED_EVENT
        else NUDGE_COOLDOWN_DAYS
    )
    return (_aware(last_event.created_at) or now) > now - timedelta(days=cooldown_days)


def get_pending_batch_size_nudge(db: Session, participant):
    sent = _latest_event(db, participant.id, (BATCH_SIZE_NUDGE_SENT_EVENT,))
    if not sent:
        return None

    response = _latest_event(
        db,
        participant.id,
        (BATCH_SIZE_NUDGE_ACCEPTED_EVENT, BATCH_SIZE_NUDGE_DECLINED_EVENT),
    )
    if response and _aware(response.created_at) >= _aware(sent.created_at):
        return None

    metadata = _event_metadata(sent)
    proposed_size = clamp_batch_size(metadata.get("proposed_size"))
    current_size = clamp_batch_size(metadata.get("current_size"))
    if proposed_size == current_size:
        return None
    return BatchSizeNudge(
        action=str(metadata.get("action") or ""),
        current_size=current_size,
        proposed_size=proposed_size,
        reason=str(metadata.get("reason") or ""),
    )


def record_batch_size_nudge_sent(db: Session, participant, nudge: BatchSizeNudge, *, source):
    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type=BATCH_SIZE_NUDGE_SENT_EVENT,
            source=source,
            event_metadata={
                "action": nudge.action,
                "current_size": nudge.current_size,
                "proposed_size": nudge.proposed_size,
                "reason": nudge.reason,
            },
        )
    )


def apply_batch_size_nudge_response(db: Session, participant, choice: str, *, source: str):
    pending = get_pending_batch_size_nudge(db, participant)
    if not pending:
        return None

    if choice == "accept":
        old_size = clamp_batch_size(getattr(participant, "preferred_batch_size", None))
        participant.preferred_batch_size = pending.proposed_size
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=BATCH_SIZE_NUDGE_ACCEPTED_EVENT,
                source=source,
                event_metadata={
                    "action": pending.action,
                    "old_size": old_size,
                    "new_size": pending.proposed_size,
                },
            )
        )
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=BATCH_SIZE_CHANGED_EVENT,
                source=source,
                event_metadata={
                    "reason": "participant_accepted_batch_size_nudge",
                    "old_size": old_size,
                    "new_size": pending.proposed_size,
                },
            )
        )
        return {
            "accepted": True,
            "new_size": pending.proposed_size,
            "message": f"Done. Your next batches will have {pending.proposed_size} questions.",
        }

    if choice == "decline":
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type=BATCH_SIZE_NUDGE_DECLINED_EVENT,
                source=source,
                event_metadata={
                    "action": pending.action,
                    "current_size": pending.current_size,
                    "proposed_size": pending.proposed_size,
                },
            )
        )
        return {
            "accepted": False,
            "new_size": pending.current_size,
            "message": "No problem. Your batch size will stay the same.",
        }

    return None


def _batch_completion_rows(db: Session, participant_id: str, since):
    events = db.scalars(
        select(ParticipantEvent)
        .where(
            ParticipantEvent.participant_id == participant_id,
            ParticipantEvent.event_type == "batch_completed",
            ParticipantEvent.created_at >= since,
        )
        .order_by(ParticipantEvent.created_at.desc(), ParticipantEvent.id.desc())
    ).all()
    rows = []
    for event in events:
        metadata = _event_metadata(event)
        batch_id = metadata.get("batch_id")
        if not batch_id:
            continue
        first_assignment = db.scalars(
            select(Assignment)
            .where(
                Assignment.participant_id == participant_id,
                Assignment.batch_id == batch_id,
            )
            .order_by(Assignment.assigned_at.asc(), Assignment.id.asc())
        ).first()
        if not first_assignment:
            continue
        rows.append(
            {
                "batch_id": batch_id,
                "started_at": _aware(first_assignment.assigned_at),
                "completed_at": _aware(event.created_at),
                "metadata": metadata,
            }
        )
    return rows


def _has_three_straight_on_time_days(db: Session, participant, current_size: int, since, now) -> bool:
    rows = _batch_completion_rows(db, participant.id, since)
    qualifying_dates = set()
    for row in rows:
        metadata = row["metadata"]
        if clamp_batch_size(metadata.get("preferred_batch_size")) != current_size:
            continue
        if int(metadata.get("completed_count") or 0) < current_size:
            continue
        started_at = row["started_at"]
        completed_at = row["completed_at"]
        if not started_at or not completed_at:
            continue
        if completed_at - started_at <= timedelta(hours=TARGET_COMPLETION_HOURS):
            qualifying_dates.add(completed_at.date())

    today = now.date()
    for offset in range(0, INCREASE_EVIDENCE_DAYS):
        candidate = today - timedelta(days=offset)
        streak = {candidate - timedelta(days=i) for i in range(INCREASE_EVIDENCE_DAYS)}
        if streak.issubset(qualifying_dates):
            return True
    return False


def _batch_outcomes(db: Session, participant_id: str, current_size: int, since, now):
    assignments = db.scalars(
        select(Assignment)
        .where(
            Assignment.participant_id == participant_id,
            Assignment.batch_id.is_not(None),
            Assignment.assigned_at >= since,
        )
        .order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
    ).all()
    batches = {}
    for assignment in assignments:
        batch = batches.setdefault(
            assignment.batch_id,
            {
                "started_at": _aware(assignment.assigned_at),
                "completed": 0,
                "completed_at": None,
            },
        )
        assigned_at = _aware(assignment.assigned_at)
        if assigned_at and assigned_at < batch["started_at"]:
            batch["started_at"] = assigned_at
        if assignment.status == AssignmentStatus.COMPLETED.value:
            batch["completed"] += 1
            completed_at = _aware(assignment.completed_at)
            if completed_at and (
                batch["completed_at"] is None or completed_at > batch["completed_at"]
            ):
                batch["completed_at"] = completed_at

    outcomes = []
    for batch in batches.values():
        started_at = batch["started_at"]
        if not started_at or started_at > now - timedelta(hours=TARGET_COMPLETION_HOURS):
            continue
        completed_in_time = (
            batch["completed"] >= current_size
            and batch["completed_at"] is not None
            and batch["completed_at"] - started_at <= timedelta(hours=TARGET_COMPLETION_HOURS)
        )
        outcomes.append(
            {
                "started_at": started_at,
                "missed": not completed_in_time,
            }
        )
    return sorted(outcomes, key=lambda item: item["started_at"], reverse=True)


def recommend_batch_size_nudge(db: Session, participant, now=None) -> Optional[BatchSizeNudge]:
    now = _aware(now or utc_now())
    current_size = clamp_batch_size(getattr(participant, "preferred_batch_size", None))
    if getattr(participant, "preferred_batch_size", None) != current_size:
        participant.preferred_batch_size = current_size

    if _cooldown_active(db, participant, now):
        return None

    since = _current_size_since(db, participant, now)
    days_at_current_size = (now - since).total_seconds() / 86400

    if (
        current_size < MAX_BATCH_SIZE
        and days_at_current_size >= INCREASE_EVIDENCE_DAYS
        and _has_three_straight_on_time_days(db, participant, current_size, since, now)
    ):
        return BatchSizeNudge(
            action="increase",
            current_size=current_size,
            proposed_size=current_size + 1,
            reason="completed_current_batch_within_24h_for_3_straight_days",
        )

    if current_size > MIN_BATCH_SIZE and days_at_current_size >= DECREASE_EVIDENCE_DAYS:
        outcomes = _batch_outcomes(db, participant.id, current_size, since, now)
        recent = outcomes[:5]
        if len(recent) >= MIN_BATCHES_FOR_DECREASE:
            missed = sum(1 for outcome in recent if outcome["missed"])
            if missed / len(recent) > 0.5:
                return BatchSizeNudge(
                    action="decrease",
                    current_size=current_size,
                    proposed_size=current_size - 1,
                    reason="missed_24h_target_for_more_than_half_of_recent_batches",
                )

    return None
