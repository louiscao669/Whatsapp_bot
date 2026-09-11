"""Assignment selection shared by dashboard and pilot surfaces."""

from sqlalchemy import select

from eten_shared.domain.assignments import (
    ExperimentPassageMissingError,
    experiment_assignment_enabled,
    experiment_passage_assignment_kwargs,
    resolve_experiment_passage,
)
from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.models import Assignment, QAItem
from eten_shared.question_discovery import (
    experiment_batch_should_reset,
    select_next_experiment_cell_item,
    select_next_qa_item,
)
from eten_shared.recordings import participant_language_code


def select_next_participant_qa_item(db, participant):
    """Return ``(qa_item, cell)``. In designed-assignment (pilot) mode the item comes
    from the participant's plan and ``cell`` is the ``ExperimentPlanCell``; otherwise
    ``cell`` is None (coverage / fallback path)."""
    if experiment_assignment_enabled():
        return select_next_experiment_cell_item(db, participant)

    qa_item = select_next_qa_item(db, participant)
    if qa_item:
        return qa_item, None

    assigned_qa_item_ids = set(
        db.scalars(
            select(Assignment.qa_item_id).where(
                Assignment.participant_id == participant.id
            )
        ).all()
    )
    candidates = [
        row
        for row in db.scalars(
            select(QAItem)
            .where(
                QAItem.active.is_(True),
                QAItem.review_removed_at.is_(None),
            )
            .order_by(QAItem.review_priority.desc(), QAItem.created_at.asc())
        ).all()
        if row.id not in assigned_qa_item_ids
        and (not row.automatic_form or row.question_type == row.automatic_form)
        and qa_item_is_assignable(row)
    ]
    return (candidates[0] if candidates else None), None


def experiment_assignment_kwargs(db, participant_session, cell, qa_item):
    """create_assignment_for_qa_item kwargs for a designed-assignment cell (empty for
    the production path). Clears the batch at a cell boundary so a batch never mixes
    conditions, and stamps the cell + its variant passage text."""
    if cell is None:
        return {}
    if experiment_batch_should_reset(db, participant_session.current_batch_id, cell):
        participant_session.current_batch_id = None
    result = {"experiment_cell_id": cell.id}
    # [2026-08-12] Mirrors the message-bot guard. The condition reaches the
    # participant only through this passage (QA is shared across a chapter's
    # conditions), so an unresolvable passage must fail rather than silently
    # fall through to the condition-invariant qa_item.passage_text.
    experiment_passage = resolve_experiment_passage(
        db, cell, qa_item, participant_language_code(participant_session.participant)
    )
    if experiment_passage is None:
        raise ExperimentPassageMissingError(
            f"plan cell {cell.id} (group {cell.chapter}, condition "
            f"{cell.condition!r}) has no variant for source passage "
            f"{qa_item.passage_id!r}. Run human_pilot/verify_experiment_delivery.py."
        )
    if experiment_passage.condition != cell.condition:
        raise ExperimentPassageMissingError(
            f"plan cell {cell.id} is condition {cell.condition!r} but its passage "
            f"is condition {experiment_passage.condition!r}."
        )
    result.update(
        experiment_passage_assignment_kwargs(db, experiment_passage, qa_item)
    )
    if not (result.get("passage_text") or "").strip():
        raise ExperimentPassageMissingError(
            f"experiment_passage {experiment_passage.id} (chapter {cell.chapter}, "
            f"condition {cell.condition!r}) has empty passage text."
        )
    return result

