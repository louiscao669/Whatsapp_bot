"""Dashboard payload services."""

from ._common import *  # noqa: F401,F403

def get_user_dashboard_payload(db, participant_id: str, event_limit: int = 100):
    from .profile import _participant_by_id
    from .scheduling import _materialize_due_dashboard_next_batch
    from .store import _get_or_create_wallet
    from .community import get_language_weekly_leaderboard
    from .store import get_store_payload
    from .journey import get_luke_chapter_activity
    from .journey import get_luke_journey_chapters
    from .serialization import _iso_datetime
    from .profile import _profile_photo_url
    from .store import get_equipped_cosmetics

    participant = _participant_by_id(db, participant_id)
    if not participant:
        return None

    _materialize_due_dashboard_next_batch(db, participant)
    wallet = _get_or_create_wallet(db, participant)
    currency_events = db.scalars(
        select(ParticipantCurrencyEvent)
        .where(ParticipantCurrencyEvent.participant_id == participant.id)
        .order_by(ParticipantCurrencyEvent.created_at.desc())
        .limit(event_limit)
    ).all()
    badges = db.scalars(
        select(ParticipantBadge)
        .where(ParticipantBadge.participant_id == participant.id)
        .order_by(ParticipantBadge.awarded_at.desc())
    ).all()
    total_questions_answered = db.scalar(
        select(func.count(ParticipantCurrencyEvent.id)).where(
            ParticipantCurrencyEvent.participant_id == participant.id,
            ParticipantCurrencyEvent.reason == "answer_completed",
            ParticipantCurrencyEvent.amount > 0,
        )
    )
    total_batches_answered = db.scalar(
        select(func.count(distinct(Assignment.batch_id))).where(
            Assignment.participant_id == participant.id,
            Assignment.status == AssignmentStatus.COMPLETED.value,
            Assignment.batch_id.is_not(None),
        )
    )

    history_summary = {
        "total_questions_answered": int(total_questions_answered or 0),
        "total_batches_answered": int(total_batches_answered or 0),
        "chapter_activity": get_luke_chapter_activity(db, participant.id),
        "journey_chapters": get_luke_journey_chapters(db, participant.id),
    }
    serialized_events = [
        {
            "created_at": _iso_datetime(event.created_at),
            "reason": event.reason,
            "amount": event.amount,
            "balance_after": event.balance_after,
        }
        for event in currency_events
    ]
    serialized_badges = [
        {
            "badge_type": badge.badge_type,
            "title": badge.title,
            "description": badge.description or "",
            "awarded_at": _iso_datetime(badge.awarded_at),
        }
        for badge in badges
    ]
    leaderboard = get_language_weekly_leaderboard(db, participant)
    streak = {
        **streak_status_payload(db, participant),
        "progress_report": latest_progress_report(db, participant.id),
    }
    store = get_store_payload(db, participant)
    wallet_payload = {
        "balance": wallet.balance if wallet else 0,
    }
    view_model = compose_dashboard_view_model(
        participant=participant,
        wallet=wallet_payload,
        history_summary=history_summary,
        events=serialized_events,
        badges=serialized_badges,
        leaderboard=leaderboard,
        streak=streak,
        store=store,
    )

    return {
        "participant": {
            "id": participant.id,
            "display_name": participant.display_name or "",
            "participant_id": participant.id,
            "profile_photo_url": _profile_photo_url(participant_id, participant),
        },
        "wallet": wallet_payload,
        "xp_points": 0,
        "events": serialized_events,
        "badges": serialized_badges,
        "streak": streak,
        "store": store,
        "cosmetics": {
            "equipped": get_equipped_cosmetics(participant),
        },
        "settings": {
            "language": (participant.dashboard_preferences or {}).get("language", "en"),
            "batch_size": max(int(participant.preferred_batch_size or 3), 1),
        },
        **view_model,
    }


