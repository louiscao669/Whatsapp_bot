"""Durable, deduplicated intake for participant answers."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .models import (
    AnswerReceipt,
    Assignment,
    AssignmentDelivery,
    AssignmentStatus,
    new_id,
)


def record_assignment_delivery(
    db, *, participant_id, assignment_id, provider, provider_message_id
):
    message_id = str(provider_message_id)
    existing = db.scalar(
        select(AssignmentDelivery).where(
            AssignmentDelivery.participant_id == participant_id,
            AssignmentDelivery.provider == provider,
            AssignmentDelivery.provider_message_id == message_id,
        )
    )
    if existing:
        return existing
    delivery = AssignmentDelivery(
        id=new_id(),
        participant_id=participant_id,
        assignment_id=assignment_id,
        provider=provider,
        provider_message_id=message_id,
    )
    db.add(delivery)
    return delivery


def assignment_for_provider_message(db, *, participant_id, provider, provider_message_id):
    if provider_message_id is None:
        return None
    return db.scalar(
        select(Assignment)
        .join(AssignmentDelivery, AssignmentDelivery.assignment_id == Assignment.id)
        .where(
            AssignmentDelivery.participant_id == participant_id,
            AssignmentDelivery.provider == provider,
            AssignmentDelivery.provider_message_id == str(provider_message_id),
        )
    )


def assignment_has_delivery(db, *, participant_id, assignment_id, provider):
    return db.scalar(
        select(AssignmentDelivery.id).where(
            AssignmentDelivery.participant_id == participant_id,
            AssignmentDelivery.assignment_id == assignment_id,
            AssignmentDelivery.provider == provider,
        )
    ) is not None


def create_answer_receipt(
    db,
    *,
    participant_id,
    assignment,
    provider,
    provider_update_id,
    raw_answer,
    response_type="text",
    provider_question_message_id=None,
):
    """Insert one immutable receipt; return ``(receipt, created)``."""

    update_id = str(provider_update_id)
    existing = db.scalar(
        select(AnswerReceipt).where(
            (AnswerReceipt.assignment_id == assignment.id)
            | (
                (AnswerReceipt.participant_id == participant_id)
                & (AnswerReceipt.provider == provider)
                & (AnswerReceipt.provider_update_id == update_id)
            )
        )
    )
    if existing:
        return existing, False
    if assignment.participant_id != participant_id:
        raise ValueError("Assignment does not belong to participant")
    if assignment.status != AssignmentStatus.ASSIGNED.value:
        raise ValueError("Assignment is no longer answerable")
    receipt = AnswerReceipt(
        id=new_id(),
        participant_id=participant_id,
        assignment_id=assignment.id,
        qa_item_id=assignment.qa_item_id,
        provider=provider,
        provider_update_id=update_id,
        provider_question_message_id=(
            str(provider_question_message_id)
            if provider_question_message_id is not None
            else None
        ),
        response_type=response_type,
        raw_answer=raw_answer,
        status="pending",
    )
    savepoint = db.begin_nested()
    try:
        db.add(receipt)
        db.flush()
        savepoint.commit()
        return receipt, True
    except IntegrityError:
        savepoint.rollback()
        existing = db.scalar(
            select(AnswerReceipt).where(
                (AnswerReceipt.assignment_id == assignment.id)
                | (
                    (AnswerReceipt.participant_id == participant_id)
                    & (AnswerReceipt.provider == provider)
                    & (AnswerReceipt.provider_update_id == update_id)
                )
            )
        )
        if existing:
            return existing, False
        raise
