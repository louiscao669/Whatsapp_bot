"""Dashboard rewards services."""

from ._common import *  # noqa: F401,F403

def _award_dashboard_currency(
    db,
    participant,
    amount,
    reason,
    *,
    assignment_id=None,
    response_id=None,
    source_event_id=None,
    metadata=None,
):
    from .store import _get_or_create_wallet

    if not amount:
        return None
    existing = None
    if response_id:
        existing = db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant.id,
                ParticipantCurrencyEvent.reason == reason,
                ParticipantCurrencyEvent.response_id == response_id,
            )
        ).first()
    elif source_event_id:
        existing = db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant.id,
                ParticipantCurrencyEvent.reason == reason,
                ParticipantCurrencyEvent.source_event_id == source_event_id,
            )
        ).first()
    if existing:
        return None

    wallet = _get_or_create_wallet(db, participant)
    wallet.balance += amount
    wallet.updated_at = utc_now()
    if amount > 0:
        wallet.lifetime_earned += amount
    else:
        wallet.lifetime_spent += abs(amount)
    event = ParticipantCurrencyEvent(
        participant_id=participant.id,
        wallet_id=wallet.id,
        assignment_id=assignment_id,
        response_id=response_id,
        amount=amount,
        balance_after=wallet.balance,
        reason=reason,
        source="user_dashboard",
        source_event_id=source_event_id,
        currency_metadata=metadata or {},
    )
    db.add(event)
    db.flush()
    return {
        "event_id": event.id,
        "amount": event.amount,
        "balance_after": event.balance_after,
        "reason": event.reason,
    }


def _batch_reward_event(db, participant_id, batch_id):
    if not batch_id:
        return None
    return db.scalars(
        select(ParticipantCurrencyEvent)
        .where(
            ParticipantCurrencyEvent.participant_id == participant_id,
            ParticipantCurrencyEvent.reason == "batch_chest_reward",
            ParticipantCurrencyEvent.source_event_id == batch_id,
        )
        .order_by(ParticipantCurrencyEvent.created_at.desc())
    ).first()


def _batch_is_complete(db, participant_id, batch_id):
    if not batch_id:
        return False
    assignments = db.scalars(
        select(Assignment).where(
            Assignment.participant_id == participant_id,
            Assignment.batch_id == batch_id,
        )
    ).all()
    return bool(assignments) and all(
        assignment.status == AssignmentStatus.COMPLETED.value
        for assignment in assignments
    )


def claim_batch_chest_reward(db, participant_id: str, batch_id: str):
    from .profile import _participant_by_id
    from .store import _get_or_create_wallet
    from .payload import get_user_dashboard_payload

    batch_id = (batch_id or "").strip()
    if not batch_id:
        raise ChestRewardError("Batch is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise ChestRewardError("Participant not found")
    if not _batch_is_complete(db, participant.id, batch_id):
        raise ChestRewardError("Complete this batch before opening the chest")
    if _batch_reward_event(db, participant.id, batch_id):
        raise ChestRewardError("This chest is already opened")

    wallet = _get_or_create_wallet(db, participant)
    amount = random.randint(CHEST_REWARD_MIN, CHEST_REWARD_MAX)
    wallet.balance += amount
    wallet.lifetime_earned += amount
    wallet.updated_at = datetime.now(timezone.utc)

    db.add(
        ParticipantCurrencyEvent(
            participant_id=participant.id,
            wallet_id=wallet.id,
            amount=amount,
            balance_after=wallet.balance,
            reason="batch_chest_reward",
            source="user_dashboard",
            source_event_id=batch_id,
            currency_metadata={
                "batch_id": batch_id,
                "reward_type": "chest",
                "min": CHEST_REWARD_MIN,
                "max": CHEST_REWARD_MAX,
            },
        )
    )
    db.flush()
    payload = get_user_dashboard_payload(db, participant_id)
    payload["last_reward"] = {
        "type": "batch_chest",
        "batch_id": batch_id,
        "amount": amount,
        "currency": "diamonds",
    }
    return payload


