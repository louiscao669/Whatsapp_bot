"""QA pair review workflow (accuracy / cultural appropriateness)."""

import re
from typing import Dict, List, Literal, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.models import QAItem, utc_now
from eten_shared.domain.qa_eligibility import (
    qa_item_is_assignable,
    qa_item_is_recordable,
    qa_item_is_removed,
    qa_item_is_reviewed,
)
from eten_shared.domain.chapter_labels import chapter_label_from_reference
from eten_shared.mcq import (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_TF,
    validate_question_fields,
)

ReviewQATab = Literal["unreviewed", "reviewed", "removed"]


def ensure_qa_item_originals(qa_item: QAItem):
    if not (qa_item.original_question_text or "").strip():
        qa_item.original_question_text = qa_item.question_text
    if not (qa_item.original_expected_answer or "").strip():
        qa_item.original_expected_answer = qa_item.expected_answer
    if not (qa_item.original_question_type or "").strip():
        qa_item.original_question_type = qa_item.question_type or QUESTION_TYPE_OPEN
    if not qa_item.original_mcq_choices and qa_item.mcq_choices:
        qa_item.original_mcq_choices = list(qa_item.mcq_choices)
    if not (qa_item.original_mcq_correct_choice or "").strip() and (
        qa_item.mcq_correct_choice or ""
    ).strip():
        qa_item.original_mcq_correct_choice = qa_item.mcq_correct_choice


def review_qa_tab_for_item(qa_item: QAItem) -> ReviewQATab:
    if qa_item_is_removed(qa_item):
        return "removed"
    if qa_item_is_reviewed(qa_item):
        return "reviewed"
    return "unreviewed"


def format_review_qa_standard_answer(qa_item: QAItem) -> str:
    """Standard answer text for reviewed/removed tables (multiline for MCQ/TF)."""
    question_type = (qa_item.question_type or QUESTION_TYPE_OPEN).strip().lower()
    if question_type not in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF}:
        answer = (qa_item.expected_answer or "").strip() or "…"
        return f"Standard Answer: {answer}"

    choice_slots = 4 if question_type == QUESTION_TYPE_MCQ else 2
    choices = list(qa_item.mcq_choices or [])
    correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
    lines = ["Standard Answer:"]
    for index in range(choice_slots):
        letter = chr(ord("A") + index)
        raw = choices[index] if index < len(choices) else ""
        text = str(raw).strip() or "…"
        star = "*" if letter == correct_letter else ""
        lines.append(f"{star}{letter}: {text}")
    return "\n".join(lines)


def format_qa_item_review_status_label(qa_item: QAItem, *, include_timestamp=False) -> str:
    """QA text review state (Review QA workflow), not participant response review."""
    from app.utils.admin_formatters import format_display_datetime

    tab = review_qa_tab_for_item(qa_item)
    if tab == "removed":
        if include_timestamp and qa_item.review_removed_at:
            return f"Removed ({format_display_datetime(qa_item.review_removed_at)})"
        return "Removed"
    if tab == "reviewed":
        if include_timestamp and qa_item.qa_reviewed_at:
            return f"Reviewed ({format_display_datetime(qa_item.qa_reviewed_at)})"
        return "Reviewed"
    return "Unreviewed"


def qa_item_passage_sort_key(qa_item: QAItem) -> Tuple:
    """Sort by book, chapter, verse (numeric), then created_at."""
    reference = (qa_item.passage_reference or qa_item.passage_id or "").strip()
    normalized = re.sub(r"\s+", " ", reference)
    match = re.search(r"^(.*?)(\d+):(\d+)\s*$", normalized)
    if not match:
        return (1, normalized.lower(), float("inf"), float("inf"), qa_item.created_at, qa_item.id)

    book_part = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
    chapter = int(match.group(2))
    verse = int(match.group(3))
    return (0, book_part, chapter, verse, qa_item.created_at, qa_item.id)


def chapter_label_sort_key(chapter_label: str) -> Tuple:
    """Sort chapter headings like Luke 2, Luke 10 by book then chapter number."""
    normalized = re.sub(r"\s+", " ", (chapter_label or "").strip())
    match = re.search(r"^(.*?)(\d+)\s*$", normalized)
    if not match:
        return (1, normalized.lower())

    book_part = re.sub(r"[^a-z0-9]+", " ", match.group(1).lower()).strip()
    chapter = int(match.group(2))
    return (0, book_part, chapter)


def sort_qa_items_by_passage(qa_items: List[QAItem]) -> List[QAItem]:
    return sorted(qa_items, key=qa_item_passage_sort_key)


def group_qa_items_by_chapter(qa_items: List[QAItem]) -> List[tuple[str, List[QAItem]]]:
    grouped: Dict[str, List[QAItem]] = {}
    for qa_item in qa_items:
        chapter = qa_item_chapter_label(qa_item)
        grouped.setdefault(chapter, []).append(qa_item)

    chapters = sorted(grouped.keys(), key=chapter_label_sort_key)
    return [
        (chapter, sort_qa_items_by_passage(grouped[chapter]))
        for chapter in chapters
    ]


def qa_item_chapter_label(qa_item: QAItem) -> str:
    return chapter_label_from_reference(qa_item.passage_reference or qa_item.passage_id)


def filter_qa_items_by_chapter(qa_items: List[QAItem], chapter_label: str) -> List[QAItem]:
    target = (chapter_label or "").strip()
    if not target:
        return []
    return [item for item in qa_items if qa_item_chapter_label(item) == target]


def bulk_mark_chapter_reviewed(db: Session, chapter_label: str) -> int:
    items = filter_qa_items_by_chapter(
        load_review_qa_items(db, "unreviewed"), chapter_label
    )
    for qa_item in items:
        ensure_qa_item_originals(qa_item)
        mark_qa_item_reviewed(qa_item)
    return len(items)


def bulk_mark_all_reviewed(db: Session) -> int:
    items = load_review_qa_items(db, "unreviewed")
    for qa_item in items:
        ensure_qa_item_originals(qa_item)
        mark_qa_item_reviewed(qa_item)
    return len(items)


def bulk_clear_chapter_reviewed(db: Session, chapter_label: str) -> int:
    items = filter_qa_items_by_chapter(
        load_review_qa_items(db, "reviewed"), chapter_label
    )
    for qa_item in items:
        clear_qa_item_reviewed(qa_item)
    return len(items)


def load_review_qa_items(db: Session, tab: ReviewQATab) -> List[QAItem]:
    statement = select(QAItem).order_by(QAItem.passage_reference, QAItem.created_at)
    if tab == "removed":
        statement = statement.where(QAItem.review_removed_at.isnot(None))
    elif tab == "reviewed":
        statement = statement.where(
            QAItem.review_removed_at.is_(None),
            QAItem.qa_reviewed_at.isnot(None),
        )
    else:
        statement = statement.where(
            QAItem.review_removed_at.is_(None),
            QAItem.qa_reviewed_at.is_(None),
        )
    return sort_qa_items_by_passage(db.scalars(statement).all())


def load_recordable_qa_items(db: Session) -> List[QAItem]:
    """QA items approved in Review QA and not removed."""
    items = db.scalars(
        select(QAItem)
        .where(
            QAItem.review_removed_at.is_(None),
            QAItem.qa_reviewed_at.isnot(None),
        )
        .order_by(QAItem.passage_reference, QAItem.created_at)
    ).all()
    return sort_qa_items_by_passage(items)


def mark_qa_item_reviewed(qa_item: QAItem):
    qa_item.qa_reviewed_at = utc_now()
    qa_item.updated_at = utc_now()


def clear_qa_item_reviewed(qa_item: QAItem):
    qa_item.qa_reviewed_at = None
    qa_item.updated_at = utc_now()


def update_qa_item_review_text(
    qa_item: QAItem,
    question_text: str,
    expected_answer: str,
    *,
    question_type: str = QUESTION_TYPE_OPEN,
    mcq_choices=None,
    mcq_correct_choice=None,
    mark_reviewed: bool = True,
):
    question = (question_text or "").strip()
    if not question:
        raise ValueError("Question text is required.")
    normalized_type, choices, correct_letter, answer = validate_question_fields(
        question_type,
        mcq_choices,
        mcq_correct_choice,
        expected_answer=expected_answer,
    )
    ensure_qa_item_originals(qa_item)
    qa_item.question_text = question
    qa_item.question_type = normalized_type
    qa_item.mcq_choices = choices
    qa_item.mcq_correct_choice = correct_letter
    qa_item.expected_answer = answer
    qa_item.updated_at = utc_now()
    if mark_reviewed:
        mark_qa_item_reviewed(qa_item)


def revert_qa_item_to_original(qa_item: QAItem):
    ensure_qa_item_originals(qa_item)
    original_question = (qa_item.original_question_text or "").strip()
    original_answer = (qa_item.original_expected_answer or "").strip()
    if not original_question or not original_answer:
        raise ValueError("Original question and answer are not available for this item.")
    qa_item.question_text = original_question
    qa_item.expected_answer = original_answer
    qa_item.question_type = (qa_item.original_question_type or QUESTION_TYPE_OPEN).strip()
    qa_item.mcq_choices = list(qa_item.original_mcq_choices or [])
    qa_item.mcq_correct_choice = qa_item.original_mcq_correct_choice
    clear_qa_item_reviewed(qa_item)


def remove_qa_item_from_review(qa_item: QAItem):
    if qa_item_is_removed(qa_item):
        return
    qa_item.review_removed_at = utc_now()
    qa_item.updated_at = utc_now()


def restore_qa_item_from_removed(qa_item: QAItem):
    if not qa_item_is_removed(qa_item):
        return
    qa_item.review_removed_at = None
    qa_item.updated_at = utc_now()
