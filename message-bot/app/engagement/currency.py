from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.models import (
    ParticipantCurrencyEvent,
    ParticipantEvent,
    ParticipantWallet,
    utc_now,
)


ANSWER_COMPLETED_COINS = 1
FIRST_ANSWER_COMPLETED_COINS = 5
BATCH_COMPLETED_BONUS_COINS = 3


def get_or_create_wallet(db: Session, participant) -> ParticipantWallet:
    wallet = db.scalars(
        select(ParticipantWallet).where(
            ParticipantWallet.participant_id == participant.id
        )
    ).first()
    if wallet:
        return wallet

    wallet = ParticipantWallet(participant_id=participant.id)
    db.add(wallet)
    db.flush()
    return wallet


def wallet_snapshot(wallet: ParticipantWallet) -> dict:
    return {
        "wallet_id": wallet.id,
        "balance": wallet.balance,
        "lifetime_earned": wallet.lifetime_earned,
        "lifetime_spent": wallet.lifetime_spent,
    }


def award_currency(
    db: Session,
    participant,
    amount: int,
    reason: str,
    source: str,
    assignment_id: str | None = None,
    response_id: str | None = None,
    source_event_id: str | None = None,
    metadata: dict | None = None,
):
    if amount == 0:
        return None

    if response_id:
        existing = db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant.id,
                ParticipantCurrencyEvent.reason == reason,
                ParticipantCurrencyEvent.response_id == response_id,
            )
        ).first()
        if existing:
            return None

    if source_event_id:
        existing = db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant.id,
                ParticipantCurrencyEvent.reason == reason,
                ParticipantCurrencyEvent.source_event_id == source_event_id,
            )
        ).first()
        if existing:
            return None

    wallet = get_or_create_wallet(db, participant)
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
        source=source,
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
        "metadata": event.currency_metadata,
    }


def award_response_currency(
    db: Session,
    participant,
    response,
    *,
    is_first_answer: bool | None = None,
):
    if response is None:
        return None

    if is_first_answer is None:
        is_first_answer = (participant.completed_count or 0) == 1
    amount = FIRST_ANSWER_COMPLETED_COINS if is_first_answer else ANSWER_COMPLETED_COINS
    return award_currency(
        db,
        participant,
        amount,
        reason="answer_completed",
        source="engagement",
        assignment_id=response.assignment_id,
        response_id=response.id,
        metadata={
            "qa_item_id": response.qa_item_id,
            "response_type": response.response_type,
            "first_answer_bonus": is_first_answer,
        },
    )


def latest_batch_completed_event(db: Session, participant_id: str):
    db.flush()
    event = db.scalars(
        select(ParticipantEvent)
        .where(
            ParticipantEvent.participant_id == participant_id,
            ParticipantEvent.event_type == "batch_completed",
        )
        .order_by(ParticipantEvent.created_at.desc(), ParticipantEvent.id.desc())
    ).first()
    if event and not event.id:
        db.flush()
    return event


def award_batch_completion_currency(
    db: Session,
    participant,
    completed_batch_size: int,
    *,
    response_id: str | None = None,
):
    event = latest_batch_completed_event(db, participant.id)
    # Deferred Telegram post-processing keys the bonus to the response that
    # closed the batch. This remains unambiguous even if several batches finish
    # before the outbox drains; synchronous callers retain the event key.
    source_event_id = None if response_id else (event.id if event else None)
    metadata = dict(event.event_metadata or {}) if event else {}
    metadata["completed_batch_size"] = completed_batch_size

    return award_currency(
        db,
        participant,
        BATCH_COMPLETED_BONUS_COINS,
        reason="batch_completed_bonus",
        source="engagement",
        response_id=response_id,
        source_event_id=source_event_id,
        metadata=metadata,
    )
