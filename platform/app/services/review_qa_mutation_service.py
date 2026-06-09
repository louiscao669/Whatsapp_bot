"""Write operations for Review QA workflow."""

from eten_shared.models import QAItem
from app.services.qa_review_service import (
    bulk_clear_chapter_reviewed,
    bulk_mark_all_reviewed,
    bulk_mark_chapter_reviewed,
    clear_qa_item_reviewed,
    mark_qa_item_reviewed,
    qa_item_is_removed,
    remove_qa_item_from_review,
    restore_qa_item_from_removed,
    revert_qa_item_to_original,
    review_qa_tab_for_item,
    update_qa_item_review_text,
)


class ReviewQaMutationError(Exception):
    pass


def parse_update_payload(payload):
    payload = payload or {}
    question_text = payload.get("question_text", "")
    expected_answer = payload.get("expected_answer", "")
    question_type = payload.get("question_type", "open")
    mcq_choices = payload.get("mcq_choices")
    if mcq_choices is None:
        mcq_choices = [
            payload.get(f"mcq_choice_{index}", "")
            for index in range(4)
        ]
    mcq_correct_choice = payload.get("mcq_correct_choice", "")
    return question_text, expected_answer, question_type, mcq_choices, mcq_correct_choice


def update_review_qa_item(db, qa_item_id, payload):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise ReviewQaMutationError("QA item not found")

    question_text, expected_answer, question_type, mcq_choices, mcq_correct_choice = (
        parse_update_payload(payload)
    )
    try:
        update_qa_item_review_text(
            qa_item,
            question_text,
            expected_answer,
            question_type=question_type,
            mcq_choices=mcq_choices,
            mcq_correct_choice=mcq_correct_choice,
        )
    except ValueError as exc:
        raise ReviewQaMutationError(str(exc)) from exc
    return qa_item


def mark_reviewed(db, qa_item_id):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise ReviewQaMutationError("QA item not found")
    if qa_item_is_removed(qa_item):
        raise ReviewQaMutationError("Cannot review a removed QA item.")
    mark_qa_item_reviewed(qa_item)
    return qa_item


def return_unreviewed(db, qa_item_id):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise ReviewQaMutationError("QA item not found")
    if qa_item_is_removed(qa_item):
        raise ReviewQaMutationError("Cannot change review status of a removed QA item.")
    clear_qa_item_reviewed(qa_item)
    return qa_item


def revert_review_qa_item(db, qa_item_id):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise ReviewQaMutationError("QA item not found")
    try:
        revert_qa_item_to_original(qa_item)
    except ValueError as exc:
        raise ReviewQaMutationError(str(exc)) from exc
    return qa_item


def remove_review_qa_item(db, qa_item_id):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise ReviewQaMutationError("QA item not found")
    remove_qa_item_from_review(qa_item)
    return qa_item


def restore_review_qa_item(db, qa_item_id):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise ReviewQaMutationError("QA item not found")
    restore_qa_item_from_removed(qa_item)
    return qa_item


def bulk_review_qa_chapter(db, action, chapter=None):
    if action == "mark_all_reviewed":
        count = bulk_mark_all_reviewed(db)
        if count == 0:
            raise ReviewQaMutationError("No unreviewed questions found.")
        return "reviewed", f"Marked {count} question(s) as reviewed."

    chapter = (chapter or "").strip()
    if not chapter:
        raise ReviewQaMutationError("Chapter name is required.")

    if action == "mark_reviewed":
        count = bulk_mark_chapter_reviewed(db, chapter)
        if count == 0:
            raise ReviewQaMutationError(f"No unreviewed questions found in {chapter}.")
        return "unreviewed", f"Marked {count} question(s) in {chapter} as reviewed."

    if action == "clear_reviewed":
        count = bulk_clear_chapter_reviewed(db, chapter)
        if count == 0:
            raise ReviewQaMutationError(f"No reviewed questions found in {chapter}.")
        return "unreviewed", f"Returned {count} question(s) in {chapter} to unreviewed."

    raise ReviewQaMutationError("Unknown bulk action.")


def target_tab_for_item(qa_item):
    return review_qa_tab_for_item(qa_item)
