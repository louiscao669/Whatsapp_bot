"""Designed-assignment selector for the human pilot (prereq #4).

Unlike ``selection.py`` (a coverage optimizer that spreads scarce responses across
under-answered items), this serves a **prescribed** per-participant Latin square: each
chapter is shown under exactly one condition, in a per-participant randomized chapter
order, one condition's passage per chapter. The plan lives in ``experiment_plan_cells``
(written once by ``human_pilot/build_experiment_plan.py``); this module only reads it and
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

Question-type arm: setting ``WH_TYPE_PREFERENCE=why`` (or ``why,how``) makes selection
PREFER items whose stem asks that interrogative, falling back to the cell's other items
when it holds none. Off by default; see ``wh_preference_strategy`` for why it is a
preference rather than a filter. Adding ``WH_TYPE_STRICT=1`` turns it into a hard filter:
cells holding no matching item are skipped, which yields a single-stem stream at the cost
of the Latin square -- test participants only, see ``wh_type_strict``.

Adaptive hook: item ordering within a cell is delegated to a pluggable ``strategy``.
The default is the designed order (MCQ-first, deterministic per participant). An adaptive
Fisher-information strategy can be swapped in later WITHOUT touching the plan/cell
machinery — see ``adaptive_fisher_strategy`` (a guarded stub) and the pilot's exploratory
H-T7 / P2 per-item-s_i results, which must license per-item selection first.
"""

from __future__ import annotations

import hashlib
import os
from typing import Callable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.models import Assignment, ExperimentPlanCell, ExperimentWindow, QAItem
from eten_shared.recordings import participant_question_audio_satisfied
from eten_shared.wh_type import classify_wh_type, parse_wh_types

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


def wh_type_preference() -> frozenset:
    """Stem types this deployment prefers, from WH_TYPE_PREFERENCE. Empty = unrestricted.

    Opt-in and default OFF, like ENABLE_EXPERIMENT_ASSIGNMENT: unset, selection behaves
    exactly as before. Set to e.g. "why" or "why,how" for a question-type arm.
    """
    return parse_wh_types(os.getenv("WH_TYPE_PREFERENCE", ""))


def wh_preference_strategy(keep, inner: Strategy = designed_order_strategy) -> Strategy:
    """Prefer items whose stem asks one of ``keep``; fall back to the cell's full set.

    SOFT, not a hard filter, and that is the design decision. gold72 holds 12 `why` items
    across ten passages, so some cells contain none; a hard filter would exhaust those
    cells and either strand the participant mid-plan or silently drop chapters from the
    Latin square, which is the balance the design exists to protect. Falling back keeps
    every cell answerable and every chapter represented -- the stream is why-weighted
    rather than why-only, and analysis reads the realised composition per participant
    rather than assuming it.

    Ordering within the preferred subset is delegated to ``inner``, so resumption
    stability and the MCQ-first split are unchanged.
    """
    keep = frozenset(keep)

    def strategy(cell: ExperimentPlanCell, remaining: List[QAItem], participant) -> QAItem:
        preferred = [i for i in remaining if classify_wh_type(i.question_text) in keep]
        return inner(cell, preferred or remaining, participant)

    return strategy


def wh_type_strict() -> bool:
    """True when ``WH_TYPE_PREFERENCE`` should FILTER the pool rather than weight it.

    Off by default. The soft preference cannot produce a single-stem stream: gold72 holds
    12 `why` items and SIX of its ten passages contain none, so those cells fall back and
    the realised stream is why-weighted at best. Strict mode drops the non-matching items
    from the candidate pool *before* the emptiness check, so a stem-less cell is flipped
    to ``done`` and skipped entirely.

    DESTRUCTIVE TO THE PLAN, and deliberately so: the skipped cells are persisted as
    ``done``, so unsetting the flag later does NOT bring those chapters back for that
    participant. It sacrifices the Latin square to get a single-stem stream -- fine for a
    throwaway test participant inspecting question quality, never for an analysed arm.
    """
    return os.getenv("WH_TYPE_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}


def filter_candidates_by_wh_type(items: List[QAItem], keep) -> List[QAItem]:
    """Items whose stem asks one of ``keep``. Empty ``keep`` -> unchanged (no-op)."""
    if not keep:
        return list(items)
    keep = frozenset(keep)
    return [item for item in items if classify_wh_type(item.question_text) in keep]


def active_strategy() -> Strategy:
    """DEFAULT_STRATEGY, or a wh-preferring wrapper when WH_TYPE_PREFERENCE is set.

    Resolved per call rather than at import, so the flag can be set by a test or a
    per-process launch without re-importing the module.
    """
    keep = wh_type_preference()
    return wh_preference_strategy(keep) if keep else DEFAULT_STRATEGY


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
    """Eligible, not-yet-assigned QAItems for this cell's window group.

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
    window_items = db.scalars(
        select(QAItem)
        .join(ExperimentWindow, ExperimentWindow.qa_item_id == QAItem.id)
        .where(
            ExperimentWindow.group_index == cell.chapter,
            QAItem.active.is_(True),
            QAItem.review_removed_at.is_(None),
        )
        .order_by(ExperimentWindow.sequence_index)
    ).all()
    # Backwards-compatible Luke path for databases that have not imported the
    # tier-1 experiment_windows table/pool.
    items = window_items or db.scalars(
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
    db: Session, participant, strategy: Optional[Strategy] = None
) -> Tuple[Optional[QAItem], Optional[ExperimentPlanCell]]:
    """Return the next ``(QAItem, ExperimentPlanCell)`` from the participant's designed
    plan, or ``(None, None)`` when the plan is complete / no eligible item remains.

    Advances the plan: the first cell with eligible items becomes ``active``; exhausted
    cells are flipped to ``done`` and skipped. Status changes are staged on the session
    (not committed) so they land in the same transaction as the created assignment.
    """
    strategy = strategy or active_strategy()
    # Strict arm: filter BEFORE the emptiness check, so a cell holding no item of the
    # wanted stem is treated as exhausted and advanced past rather than falling back.
    strict_keep = wh_type_preference() if wh_type_strict() else frozenset()
    cells = _plan_cells(db, participant)
    cell = _current_cell(cells)
    while cell is not None:
        remaining = _cell_candidates(db, cell, participant)
        if strict_keep:
            remaining = filter_candidates_by_wh_type(remaining, strict_keep)
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
