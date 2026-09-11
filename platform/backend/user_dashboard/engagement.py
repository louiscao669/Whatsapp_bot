"""Dashboard engagement services."""

from ._common import *  # noqa: F401,F403

def _enqueue_outbox_notification(db, participant, notification_type, payload):
    """Queue a cross-surface notification for the message-bot poller.

    Older pending notifications of the same type for the same participant
    are superseded so rapid dashboard answering collapses into one push --
    except for per-response scoring work, which must not be collapsed.
    """

    stale = [] if notification_type in _PER_RESPONSE_NOTIFICATIONS else db.scalars(
        select(OutboxNotification).where(
            OutboxNotification.participant_id == participant.id,
            OutboxNotification.notification_type == notification_type,
            OutboxNotification.status == OutboxStatus.PENDING.value,
        )
    ).all()
    for notification in stale:
        notification.status = OutboxStatus.SUPERSEDED.value
        notification.failure_reason = "Superseded by a newer notification"

    notification = OutboxNotification(
        participant_id=participant.id,
        notification_type=notification_type,
        payload=payload or {},
        status=OutboxStatus.PENDING.value,
    )
    db.add(notification)
    return notification


def mark_dashboard_question_viewed(db, participant_id: str, assignment_id: str):
    """Record that a question was first rendered on the dashboard.

    Starts the time-on-task clock (assignment.started_at) if it has not
    already been started by a messenger delivery.
    """
    from .profile import _participant_by_id
    from .serialization import _iso_datetime


    assignment_id = (assignment_id or "").strip()
    if not assignment_id:
        raise DashboardAnswerError("Assignment is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")

    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.participant_id != participant.id:
        raise DashboardAnswerError("Assignment not found")

    started_now = False
    if (
        assignment.status != AssignmentStatus.COMPLETED.value
        and assignment.started_at is None
    ):
        now = utc_now()
        # Fallback: if the question was never marked delivered (e.g. it was
        # created and opened without going through the batch-delivery path),
        # treat this first render as the delivery moment too.
        assignment.delivered_at = assignment.delivered_at or now
        assignment.started_at = now
        started_now = True

    record_participant_event(
        db,
        participant,
        "question_viewed",
        {
            "assignment_id": assignment.id,
            "qa_item_id": assignment.qa_item_id,
            "batch_id": assignment.batch_id,
            "started_clock": started_now,
            "source_surface": "user_dashboard",
        },
        source="user_dashboard",
    )
    return {
        "assignment_id": assignment.id,
        "started_at": _iso_datetime(assignment.started_at),
        "started_clock": started_now,
    }


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def record_dashboard_heartbeat(db, participant_id: str, session_key: str, *, active: bool = True):
    """Accumulate engaged dwell time for one dashboard browser session.

    Idempotent-ish upsert keyed by (participant_id, session_key). Each call
    advances ``active_seconds`` by the elapsed time since the previous
    heartbeat, but only when the page reported itself active and the gap is
    within ``DASHBOARD_HEARTBEAT_MAX_GAP_SECONDS`` (so an idle/hidden tab that
    resumes does not book the away-time as engagement). Dashboard-only; there is
    no messenger equivalent.
    """
    from .profile import _participant_by_id


    session_key = (session_key or "").strip()
    if not session_key:
        raise DashboardAnswerError("Session key is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")

    now = utc_now()
    session = db.scalars(
        select(DashboardEngagementSession).where(
            DashboardEngagementSession.participant_id == participant.id,
            DashboardEngagementSession.session_key == session_key,
        )
    ).first()

    if session is None:
        session = DashboardEngagementSession(
            participant_id=participant.id,
            session_key=session_key,
            started_at=now,
            last_heartbeat_at=now,
            active_seconds=0,
            heartbeat_count=1,
        )
        db.add(session)
    else:
        delta = (now - _as_utc(session.last_heartbeat_at)).total_seconds()
        if active and 0 < delta <= DASHBOARD_HEARTBEAT_MAX_GAP_SECONDS:
            session.active_seconds = int(session.active_seconds + round(delta))
        session.last_heartbeat_at = now
        session.heartbeat_count = (session.heartbeat_count or 0) + 1

    return {
        "session_key": session_key,
        "active_seconds": session.active_seconds,
        "heartbeat_count": session.heartbeat_count,
    }


