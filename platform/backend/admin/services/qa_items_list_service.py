"""QA items list data for admin dashboards and JSON API."""

from collections import defaultdict
from datetime import timezone

from sqlalchemy import select

from eten_shared.models import ExperimentWindow, ParticipantResponse, QAItem
from backend.admin.services.qa_review_service import (
    format_qa_item_review_status_label,
    review_qa_tab_for_item,
    sort_qa_items_by_passage,
)
from backend.admin.utils.admin_formatters import format_correctness_score


def question_bank(passage_id):
    """Keep reviewed releases and their prepared/from-scratch subsets separate."""
    namespace, _, source = (passage_id or "").partition("/")
    if namespace in {"reviewed122", "reviewed122_sol"}:
        label = "Sol Chinese" if namespace == "reviewed122_sol" else "Reviewed Chinese"
        subset = source.split("/", 1)[0]
        if subset in {"Prepared60", "Hard77"}:
            return f"{namespace}/{subset}", f"{label} · {'prepared' if subset == 'Prepared60' else 'from scratch'}"
        return namespace, label
    if namespace == "hard66":
        return "hard66", "Strong-66"
    if namespace.startswith("t1_"):
        return "gold72", "Gold-72 · prepared"
    if namespace.lower().startswith("luke"):
        return "luke", "Luke questions"
    return f"other/{namespace}", namespace or "Other questions"


def _created_at(item):
    value = item.created_at
    if value and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat() if value else ""


def _current_version_ids(qa_items, delivery_ids):
    revisions = defaultdict(list)
    for item in qa_items:
        # Without an explicit group, do not infer revisions from similar wording.
        revisions[(item.passage_id, item.form_group_id or item.id,
                   (item.question_type or "open").strip().lower())].append(item)
    current = set()
    for versions in revisions.values():
        linked = {item.id for item in versions if item.id in delivery_ids}
        # The delivery pointer is authoritative, even if an unused draft is newer.
        current.update(linked or {max(versions, key=lambda item: (_created_at(item), item.id)).id})
    return current


def _answer_text(item):
    if (item.question_type or "open").strip().lower() in {"mcq", "tf"}:
        key = (item.mcq_correct_choice or "").strip().upper()
        choices = item.mcq_choices or []
        if len(key) == 1 and 0 <= ord(key) - ord("A") < len(choices):
            return str(choices[ord(key) - ord("A")])
    return item.expected_answer or ""


def list_qa_items_with_stats(db):
    qa_items = sort_qa_items_by_passage(db.scalars(select(QAItem)).all())
    delivery_ids = set(db.scalars(select(ExperimentWindow.qa_item_id)))
    current_ids = _current_version_ids(qa_items, delivery_ids)

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
        bank_id, bank_label = question_bank(qa_item.passage_id)
        scored = score_counts.get(qa_item.id, 0)
        average_score = (
            format_correctness_score(score_totals[qa_item.id] / scored) if scored else None
        )
        items.append(
            {
                "id": qa_item.id,
                "passage_id": qa_item.passage_id,
                "bank_id": bank_id,
                "bank_label": bank_label,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": qa_item.question_text,
                "answer": _answer_text(qa_item),
                "mcq_choices": list(qa_item.mcq_choices or []),
                "mcq_correct_choice": qa_item.mcq_correct_choice,
                "is_current": qa_item.id in current_ids,
                "created_at": _created_at(qa_item),
                "question_type": (qa_item.question_type or "open").strip().lower(),
                "form_group_id": qa_item.form_group_id,
                "automatic_form": qa_item.automatic_form,
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
