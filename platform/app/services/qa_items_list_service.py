"""QA items list data for admin dashboards and JSON API."""

from sqlalchemy import select

from eten_shared.models import ParticipantResponse, QAItem
from app.services.qa_review_service import (
    format_qa_item_review_status_label,
    review_qa_tab_for_item,
    sort_qa_items_by_passage,
)
from app.utils.admin_formatters import format_correctness_score


def list_qa_items_with_stats(db):
    qa_items = sort_qa_items_by_passage(db.scalars(select(QAItem)).all())

    response_counts = {}
    flagged_counts = {}
    score_totals = {}
    score_counts = {}
    for qa_item_id, is_correct, correctness_score in db.execute(
        select(
            ParticipantResponse.qa_item_id,
            ParticipantResponse.is_correct,
            ParticipantResponse.correctness_score,
        )
    ):
        response_counts[qa_item_id] = response_counts.get(qa_item_id, 0) + 1
        if is_correct in {"pending", "no (expert)"}:
            flagged_counts[qa_item_id] = flagged_counts.get(qa_item_id, 0) + 1
        if correctness_score is not None:
            score_totals[qa_item_id] = score_totals.get(qa_item_id, 0) + correctness_score
            score_counts[qa_item_id] = score_counts.get(qa_item_id, 0) + 1

    items = []
    for qa_item in qa_items:
        scored = score_counts.get(qa_item.id, 0)
        average_score = (
            format_correctness_score(score_totals[qa_item.id] / scored) if scored else None
        )
        items.append(
            {
                "id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": qa_item.question_text,
                "question_type": (qa_item.question_type or "open").strip().lower(),
                "review_status": format_qa_item_review_status_label(qa_item),
                "review_tab": review_qa_tab_for_item(qa_item),
                "response_count": response_counts.get(qa_item.id, 0),
                "flagged_count": flagged_counts.get(qa_item.id, 0),
                "average_score": average_score,
                "min_responses_required": qa_item.min_responses_required,
                "review_priority": qa_item.review_priority,
                "active": qa_item.active,
            }
        )
    return items
