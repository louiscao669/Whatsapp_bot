"""Designed-assignment selector for the human pilot (prereq #4).

Unlike ``selection.py`` (a coverage optimizer that spreads scarce responses across
under-answered items), this serves a **prescribed** per-participant Latin square: each
chapter is shown under exactly one condition, in a per-participant randomized chapter
order, one condition's passage per chapter. The plan lives in ``experiment_plan_cells``
(written once by ``scripts/build_experiment_plan.py``); this module only reads it and
flips a cell ``pending -> active -> done``.

Schema note: QA is imported once per chapter as ``QAItem`` rows keyed by
``passage_id == "luke{chapter}"`` (shared across conditions); only the *passage* varies
per condition and lives in ``experiment_passages`` (referenced by the plan cell's
``experiment_passage_id``). So the selector scopes candidates by the cell's **chapter**,
not by a per-condition passage_id.

Public API:
    select_next_experiment_cell_item(db, participant, strategy=...) -> (QAItem|None, ExperimentPlanCell|None)
        The primary entry point. Returns the next (item, cell) so the caller can stamp
        ``Assignment.experiment_cell_id`` and copy the variant passage onto the assignment.
    select_next_experiment_qa_item(db, participant) -> QAItem | None
        Thin wrapper with the same signature as ``select_next_qa_item`` for drop-in
        branching at the call sites.

Adaptive hook: item ordering within a cell is delegated to a pluggable ``strategy``.
The default is the designed order (MCQ-first, deterministic per participant). An adaptive
Fisher-information strategy can be swapped in later WITHOUT touching the plan/cell
machinery — see ``adaptive_fisher_strategy`` (a guarded stub) and the pilot's exploratory
H-T7 / P2 per-item-s_i results, which must license per-item selection first.
"""

from __future__ import annotations

import hashlib
from typing import Callable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.models import Assignment, ExperimentPlanCell, QAItem
from eten_shared.recordings import participant_question_audio_satisfied

# A strategy picks ONE item from the eligible remaining items of the active cell.
# (cell, remaining_items, participant) -> chosen QAItem
Strategy = Callable[[ExperimentPlanCell, List[QAItem], object], QAItem]


# --------------------------------------------------------------------- strategies
def designed_order_strategy(
    cell: ExperimentPlanCell, remaining: List[QAItem], participant
) -> QAItem:
    """Default: deterministic per (participant, item) so resumption is stable, MCQ
    before open to front-load the pilot's ~75/25 split. NOT coverage priority."""
    def key(item: QAItem):
        digest = hashlib.md5(f"{cell.participant_id}:{item.id}".encode()).hexdigest()
        return (0 if item.question_type == "mcq" else 1, digest)

    return sorted(remaining, key=key)[0]


def adaptive_fisher_strategy(
    cell: ExperimentPlanCell, remaining: List[QAItem], participant
) -> QAItem:
    """Placeholder for Fisher-information-maximizing per-item selection.

    Deliberately unimplemented: per-item adaptive selection requires human-validated
    per-item sensitivity s_i. P2 (EXPERIMENT_ABILITY_DEPENDENT_SENSITIVITY §9) revived
    per-item s_i for adequacy on the LLM grid, but transfer to humans is unproven — that
    is the pilot's exploratory H-T7. Only wire this in once H-T7 (and a dedicated
    calibration study) license item-level selection; then compute per-item Fisher info
    s_i^2 * p(1-p) at the participant's ability and return argmax over ``remaining``.
    """
    raise NotImplementedError(
        "Adaptive per-item selection needs human-validated s_i (pilot H-T7 + calibration "
        "study). Use designed_order_strategy until then."
    )


DEFAULT_STRATEGY: Strategy = designed_order_strategy


# ----------------------------------------------------------------------- internals
def _plan_cells(db: Session, participant) -> List[ExperimentPlanCell]:
    return list(
        db.scalars(
            select(ExperimentPlanCell)
            .where(ExperimentPlanCell.participant_id == participant.id)
            .order_by(ExperimentPlanCell.sequence_index)
        ).all()
    )


def _current_cell(cells: List[ExperimentPlanCell]) -> Optional[ExperimentPlanCell]:
    """The cell in progress: the first 'active' one, else the first 'pending'."""
    active = [c for c in cells if c.status == "active"]
    if active:
        return active[0]
    pending = [c for c in cells if c.status == "pending"]
    return pending[0] if pending else None


def _cell_candidates(db: Session, cell: ExperimentPlanCell, participant) -> List[QAItem]:
    """Eligible, not-yet-assigned QAItems for this cell's CHAPTER (shared QA pool).

    Keeps the production eligibility filters verbatim: ``qa_item_is_assignable`` (active +
    not review-removed) and ``participant_question_audio_satisfied`` — the latter IS the
    flag-parameterized gate (honors REQUIRE_QUESTION_AUDIO; text mode passes everything,
    audio mode requires matching-language question audio).
    """
    assigned_ids = set(
        db.scalars(
            select(Assignment.qa_item_id).where(
                Assignment.participant_id == participant.id
            )
        ).all()
    )
    items = db.scalars(
        select(QAItem).where(
            QAItem.passage_id == f"luke{cell.chapter}",
            QAItem.active.is_(True),
            QAItem.review_removed_at.is_(None),
        )
    ).all()
    return [
        item
        for item in items
        if item.id not in assigned_ids
        and (not item.automatic_form or item.question_type == item.automatic_form)
        and qa_item_is_assignable(item)
        and participant_question_audio_satisfied(db, item.id, participant)
    ]


# -------------------------------------------------------------------------- public
def select_next_experiment_cell_item(
    db: Session, participant, strategy: Strategy = DEFAULT_STRATEGY
) -> Tuple[Optional[QAItem], Optional[ExperimentPlanCell]]:
    """Return the next ``(QAItem, ExperimentPlanCell)`` from the participant's designed
    plan, or ``(None, None)`` when the plan is complete / no eligible item remains.

    Advances the plan: the first cell with eligible items becomes ``active``; exhausted
    cells are flipped to ``done`` and skipped. Status changes are staged on the session
    (not committed) so they land in the same transaction as the created assignment.
    """
    cells = _plan_cells(db, participant)
    cell = _current_cell(cells)
    while cell is not None:
        remaining = _cell_candidates(db, cell, participant)
        if remaining:
            if cell.status != "active":
                cell.status = "active"
            return strategy(cell, remaining, participant), cell
        # cell exhausted (all assigned / none eligible) -> advance
        cell.status = "done"
        cell = _current_cell(cells)
    return None, None


def select_next_experiment_qa_item(db: Session, participant) -> Optional[QAItem]:
    """Signature-compatible wrapper (mirrors ``select_next_qa_item``) for the call-site
    branch. Callers that need to stamp ``experiment_cell_id`` / copy the variant passage
    should use ``select_next_experiment_cell_item`` instead."""
    item, _cell = select_next_experiment_cell_item(db, participant)
    return item


def experiment_batch_cell_id(db: Session, batch_id: Optional[str]) -> Optional[str]:
    """The experiment cell an open batch already belongs to (None if none / not experiment)."""
    if not batch_id:
        return None
    return db.scalars(
        select(Assignment.experiment_cell_id)
        .where(
            Assignment.batch_id == batch_id,
            Assignment.experiment_cell_id.is_not(None),
        )
        .limit(1)
    ).first()


def experiment_batch_should_reset(
    db: Session, batch_id: Optional[str], cell: ExperimentPlanCell
) -> bool:
    """True when the open batch already carries a DIFFERENT experiment cell, so the caller
    must mint a fresh batch — keeping one condition (one chapter's variant passage) per
    batch (design §7a). False for an empty batch or a batch already on this cell.
    """
    existing = experiment_batch_cell_id(db, batch_id)
    return existing is not None and existing != cell.id
