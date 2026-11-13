"""Read-only QA item eligibility checks shared by bot and platform."""

from eten_shared.models import QAItem
from eten_shared.experiment_plan import is_test_bank_passage


def qa_item_is_removed(qa_item: QAItem) -> bool:
    return qa_item.review_removed_at is not None


def qa_item_is_reviewed(qa_item: QAItem) -> bool:
    return qa_item.qa_reviewed_at is not None


def qa_item_is_assignable(qa_item: QAItem, *, test_plan=False) -> bool:
    if is_test_bank_passage(qa_item.passage_id):
        # Preview items stay inactive in the general pool, including on older deployments.
        return test_plan and not qa_item_is_removed(qa_item)
    return bool(qa_item.active) and not qa_item_is_removed(qa_item)


def qa_item_is_recordable(qa_item: QAItem) -> bool:
    return qa_item_is_reviewed(qa_item) and not qa_item_is_removed(qa_item)
