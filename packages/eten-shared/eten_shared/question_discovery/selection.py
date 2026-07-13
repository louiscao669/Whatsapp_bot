"""Select the next eligible QA item for a participant."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.models import Assignment, ParticipantResponse, QAItem
from eten_shared.recordings import participant_question_audio_satisfied


def get_qa_item_distribution_metrics(db: Session, qa_item):
    responses = db.scalars(
        select(ParticipantResponse).where(ParticipantResponse.qa_item_id == qa_item.id)
    ).all()
    actual_response_count = len(responses)
    response_gap = max(qa_item.min_responses_required - actual_response_count, 0)

    scored_responses = [
        response.correctness_score
        for response in responses
        if response.correctness_score is not None
    ]
    average_correctness = (
        sum(scored_responses) / len(scored_responses) if scored_responses else None
    )
    low_accuracy_risk = (
        1 - average_correctness if average_correctness is not None else 0
    )
    flag_rate = (
        sum(1 for response in responses if response.is_correct == "pending")
        / actual_response_count
        if actual_response_count
        else 0
    )
    accuracy_risk = max(low_accuracy_risk, flag_rate)

    return {
        "actual_response_count": actual_response_count,
        "response_gap": response_gap,
        "average_correctness": average_correctness,
        "flag_rate": flag_rate,
        "accuracy_risk": accuracy_risk,
    }


def get_qa_item_priority(db: Session, qa_item):
    metrics = get_qa_item_distribution_metrics(db, qa_item)
    return (
        -metrics["response_gap"],
        -metrics["accuracy_risk"],
        -qa_item.review_priority,
        metrics["actual_response_count"],
        qa_item.created_at,
    )


def select_next_qa_item(db: Session, participant):
    assigned_qa_item_ids = set(
        db.scalars(
            select(Assignment.qa_item_id).where(
                Assignment.participant_id == participant.id
            )
        ).all()
    )

    statement = select(QAItem).where(
        QAItem.active.is_(True),
        QAItem.review_removed_at.is_(None),
    )

    candidates = [
        qa_item
        for qa_item in db.scalars(statement).all()
        if qa_item.id not in assigned_qa_item_ids
        and participant_question_audio_satisfied(db, qa_item.id, participant)
        and qa_item_is_assignable(qa_item)
    ]
    if not candidates:
        return None

    return sorted(candidates, key=lambda item: get_qa_item_priority(db, item))[0]
