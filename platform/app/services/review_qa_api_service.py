"""Read payloads for Review QA JSON API."""

from datetime import timezone

from eten_shared.models import QAItem
from eten_shared.mcq import QUESTION_TYPE_MCQ, QUESTION_TYPE_OPEN, QUESTION_TYPE_TF
from app.services.qa_review_service import (
    format_review_qa_standard_answer,
    group_qa_items_by_chapter,
    load_review_qa_items,
    qa_item_chapter_label,
    qa_item_is_removed,
)
from app.utils.admin_formatters import format_display_datetime

VALID_TABS = frozenset({"unreviewed", "reviewed", "removed"})


def _iso_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _normalize_tab(tab: str) -> str:
    normalized = (tab or "unreviewed").strip().lower()
    return normalized if normalized in VALID_TABS else "unreviewed"


def _serialize_mcq_choices(qa_item: QAItem):
    question_type = (qa_item.question_type or QUESTION_TYPE_OPEN).strip().lower()
    slots = 4 if question_type == QUESTION_TYPE_MCQ else 2 if question_type == QUESTION_TYPE_TF else 0
    choices = list(qa_item.mcq_choices or [])
    while len(choices) < 4:
        choices.append("")
    return choices[:4], slots


def serialize_review_qa_item(qa_item: QAItem, *, tab: str):
    choices, choice_slots = _serialize_mcq_choices(qa_item)
    question_type = (qa_item.question_type or QUESTION_TYPE_OPEN).strip().lower()
    has_original = bool(
        (qa_item.original_question_text or "").strip()
        and (qa_item.original_expected_answer or "").strip()
    )
    return {
        "id": qa_item.id,
        "chapter": qa_item_chapter_label(qa_item),
        "passage": qa_item.passage_reference or qa_item.passage_id,
        "passage_text": qa_item.passage_text,
        "question_text": qa_item.question_text,
        "question_type": question_type,
        "expected_answer": qa_item.expected_answer or "",
        "mcq_choices": choices,
        "mcq_correct_choice": (qa_item.mcq_correct_choice or "").strip().upper() or None,
        "choice_slots": choice_slots,
        "standard_answer": format_review_qa_standard_answer(qa_item),
        "has_original": has_original,
        "qa_reviewed_at": _iso_datetime(qa_item.qa_reviewed_at),
        "review_removed_at": _iso_datetime(qa_item.review_removed_at),
        "removed_label": (
            format_display_datetime(qa_item.review_removed_at) if qa_item.review_removed_at else None
        ),
        "reviewed_label": (
            format_display_datetime(qa_item.qa_reviewed_at) if qa_item.qa_reviewed_at else None
        ),
        "tab": tab,
        "is_removed": qa_item_is_removed(qa_item),
    }


def _chapter_bulk_actions(tab: str):
    if tab == "unreviewed":
        return ["mark_reviewed"]
    if tab == "reviewed":
        return ["clear_reviewed"]
    return []


def get_review_qa_dashboard(db, tab: str):
    tab = _normalize_tab(tab)
    qa_items = load_review_qa_items(db, tab)

    if tab == "removed":
        return {
            "tab": tab,
            "chapters": [],
            "items": [serialize_review_qa_item(item, tab=tab) for item in qa_items],
        }

    chapters = []
    for chapter, items in group_qa_items_by_chapter(qa_items):
        chapters.append(
            {
                "chapter": chapter,
                "count": len(items),
                "bulk_actions": _chapter_bulk_actions(tab),
                "items": [serialize_review_qa_item(item, tab=tab) for item in items],
            }
        )

    return {"tab": tab, "chapters": chapters, "items": []}
