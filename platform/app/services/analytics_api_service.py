"""Aggregate analytics dashboard payload."""

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from eten_shared.models import Participant, ParticipantResponse, QAItem
from app.services.qa_review_service import sort_qa_items_by_passage
from app.utils.admin_formatters import format_correctness_score


def _truncate_text(value, max_length=80):
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def get_analytics_dashboard(db):
    responses = db.scalars(
        select(ParticipantResponse)
        .options(selectinload(ParticipantResponse.qa_item))
        .order_by(ParticipantResponse.received_at.desc())
    ).all()

    participant_count = len(db.scalars(select(Participant.id)).all())
    qa_item_count = len(db.scalars(select(QAItem.id)).all())
    total_responses = len(responses)
    flagged_count = sum(
        1 for response in responses if response.is_correct in {"pending", "no (expert)"}
    )
    scored_responses = [
        response.correctness_score
        for response in responses
        if response.correctness_score is not None
    ]
    average_score = (
        format_correctness_score(sum(scored_responses) / len(scored_responses))
        if scored_responses
        else None
    )

    response_counts = dict(
        db.execute(
            select(ParticipantResponse.qa_item_id, func.count()).group_by(
                ParticipantResponse.qa_item_id
            )
        ).all()
    )
    qa_items = sort_qa_items_by_passage(db.scalars(select(QAItem)).all())
    response_count_rows = []
    for qa_item in qa_items:
        count = int(response_counts.get(qa_item.id, 0))
        response_count_rows.append(
            {
                "qa_item_id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": _truncate_text(qa_item.question_text),
                "response_count": count,
                "min_required": qa_item.min_responses_required,
                "meets_target": count >= qa_item.min_responses_required,
            }
        )

    qa_metrics = {}
    for response in responses:
        if not response.qa_item:
            continue
        metrics = qa_metrics.setdefault(
            response.qa_item.id,
            {
                "passage": response.qa_item.passage_reference or response.qa_item.passage_id,
                "question": response.qa_item.question_text,
                "responses": 0,
                "flagged": 0,
                "score_sum": 0.0,
                "scored": 0,
            },
        )
        metrics["responses"] += 1
        metrics["flagged"] += 1 if response.is_correct in {"pending", "no (expert)"} else 0
        if response.correctness_score is not None:
            metrics["score_sum"] += response.correctness_score
            metrics["scored"] += 1

    per_qa_rows = []
    for metrics in qa_metrics.values():
        per_qa_rows.append(
            {
                "passage": metrics["passage"],
                "question": metrics["question"],
                "responses": metrics["responses"],
                "flagged": metrics["flagged"],
                "flag_rate": round(metrics["flagged"] / metrics["responses"], 3)
                if metrics["responses"]
                else None,
                "average_score": format_correctness_score(
                    metrics["score_sum"] / metrics["scored"]
                )
                if metrics["scored"]
                else None,
            }
        )

    return {
        "summary": {
            "participants": participant_count,
            "qa_items": qa_item_count,
            "responses": total_responses,
            "flagged": flagged_count,
            "average_score": average_score,
        },
        "response_counts": response_count_rows,
        "per_qa_metrics": per_qa_rows,
    }
