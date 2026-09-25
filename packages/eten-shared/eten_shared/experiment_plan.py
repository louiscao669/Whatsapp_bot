"""Latin-square plan for the human pilot, shared by the CLI and the admin platform.

The plan design is documented in ``human_pilot/build_experiment_plan.py`` (the CLI
that plans real participants in bulk). This module holds the pieces both callers
need so the admin "Create test participant" action writes exactly the plan the CLI
would, rather than a second copy of the rules that could drift.

Test participants are flagged in ``participants.dashboard_preferences`` (a JSON
column that already exists) under ``TEST_PARTICIPANT_KEY``. No schema change: the
flag only has to be readable by the plan builder and the pilot export, which both
skip flagged participants so a test run can neither shift a real participant's
Latin-square block nor leak into results.
"""

import random

from sqlalchemy import func, select

from eten_shared.models import (
    ExperimentPassage,
    ExperimentPlanCell,
    ExperimentWindow,
    Participant,
)

# 8 condition slots. Two "clean" anchors (pooled). The strings MUST match
# experiment_passages.condition written by human_pilot/pilot_import.py.
# [CHANGED 2026-07-27b] Two matched adequacy ladders ({15,30}% each) replace the old
# omission{10,20,30}+mistranslation20 slate. See HUMAN_PILOT_DESIGN_2026-07-27.md §4.
SLOTS = [
    "clean",            # A1 anchor
    "clean",            # A2 anchor (same passage; pooled)
    "omission15",
    "omission30",
    "mistranslation15",
    "mistranslation30",
    "grammar30",
    "wbw",
]
# ``chapter`` in the legacy schema now stores the balanced window-group index.
GROUPS = list(range(1, 9))
LANGUAGE = "zh"

TEST_PARTICIPANT_KEY = "test_participant"


class ExperimentPlanError(Exception):
    pass


def build_cells(participant_id: str, block_index: int):
    """Return the list of (chapter, condition, sequence_index) for one participant."""
    chapter_order = GROUPS.copy()
    random.Random(str(participant_id)).shuffle(chapter_order)  # stable per participant
    cells = []
    for seq, chapter in enumerate(chapter_order):
        condition = SLOTS[(chapter - 1 + block_index) % len(SLOTS)]
        cells.append((chapter, condition, seq))
    return cells


def is_test_participant(participant) -> bool:
    prefs = getattr(participant, "dashboard_preferences", None) or {}
    return bool(prefs.get(TEST_PARTICIPANT_KEY))


def passage_index(db, language):
    idx = {}
    for p in db.scalars(select(ExperimentPassage).where(ExperimentPassage.language == language)).all():
        idx[(p.chapter, p.condition)] = p.id
    return idx


def tier1_mode(db) -> bool:
    return bool(db.scalar(select(func.count(ExperimentWindow.id))))


def tier1_variant_gaps(db, language):
    """Missing (source passage, condition) variants required by imported windows."""
    source_ids = set(db.scalars(select(ExperimentWindow.source_passage_id).distinct()).all())
    present = set(db.execute(
        select(ExperimentPassage.source_passage_id, ExperimentPassage.condition).where(
            ExperimentPassage.language == language,
            ExperimentPassage.source_passage_id.in_(source_ids),
        )
    ).all()) if source_ids else set()
    return {
        (source_id, condition)
        for source_id in source_ids
        for condition in set(SLOTS)
        if (source_id, condition) not in present
    }


def write_participant_plan(db, participant, block_index: int, language: str = LANGUAGE):
    """Stage one participant's plan cells (caller commits). Returns the cell tuples.

    Same checks as the CLI: refuses when nothing is imported, when a tier-1 variant is
    missing, or when the participant already has a plan.
    """
    existing = db.scalar(
        select(ExperimentPlanCell.id).where(ExperimentPlanCell.participant_id == participant.id)
    )
    if existing:
        raise ExperimentPlanError("Participant already has a plan")

    is_tier1 = tier1_mode(db)
    pidx = {} if is_tier1 else passage_index(db, language)
    if not is_tier1 and not pidx:
        raise ExperimentPlanError(
            f"No pilot passages imported for language '{language}'. "
            "Run human_pilot/pilot_import.py first."
        )
    if is_tier1:
        gaps = tier1_variant_gaps(db, language)
        if gaps:
            raise ExperimentPlanError(
                f"{len(gaps)} tier-1 passage/condition variants are missing for "
                f"'{language}' (first: {sorted(gaps)[:3]}). Re-run the pilot import."
            )

    cells = build_cells(participant.id, block_index % len(SLOTS))
    for chapter, condition, seq in cells:
        db.add(ExperimentPlanCell(
            participant_id=participant.id,
            chapter=chapter,
            condition=condition,
            # Tier-1 groups can span passages; delivery resolves per QA item.
            experiment_passage_id=None if is_tier1 else pidx.get((chapter, condition)),
            sequence_index=seq,
            status="pending",
        ))
    db.flush()
    return cells


def next_test_block_index(db) -> int:
    """Rotate test participants through the 8 slot rotations (0, 1, ..., 7, 0, ...)."""
    rows = db.scalars(select(Participant.dashboard_preferences)).all()
    count = sum(1 for prefs in rows if (prefs or {}).get(TEST_PARTICIPANT_KEY))
    return count % len(SLOTS)
