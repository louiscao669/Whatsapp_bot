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

# Question sets that can live side by side in one database. A set is identified by
# the window-group range its ExperimentWindows use: plan cells store the group in
# ``chapter`` and the selector matches ``ExperimentWindow.group_index == cell.chapter``,
# so offsetting a set's groups keeps its questions separate with no schema change.
# A set's passages are imported under ``<passage_prefix><source id>`` (e.g.
# ``hard66/t1_judg9``) so its windows and condition variants never collide with
# another set's rows for the same source passage.
QA_SETS = {
    "gold72": {"group_offset": 0, "passage_prefix": "", "label": "gold72 (prepared set)"},
    "hard66": {"group_offset": 100, "passage_prefix": "hard66/", "label": "hard66 (strong set)"},
}
DEFAULT_QA_SET = "gold72"


class ExperimentPlanError(Exception):
    pass


def qa_set_config(qa_set):
    try:
        return QA_SETS[qa_set or DEFAULT_QA_SET]
    except KeyError:
        raise ExperimentPlanError(
            f"Unknown question set {qa_set!r} (known: {', '.join(QA_SETS)})"
        ) from None


def qa_set_groups(qa_set=DEFAULT_QA_SET):
    offset = qa_set_config(qa_set)["group_offset"]
    return [offset + group for group in GROUPS]


def build_cells(participant_id: str, block_index: int, qa_set: str = DEFAULT_QA_SET):
    """Return the list of (chapter, condition, sequence_index) for one participant.

    ``chapter`` is the window-group index the selector matches; for a non-default
    question set it is offset (hard66 -> 101..108). The Latin-square rotation uses the
    set-relative group (1..8), so every set gets the identical condition schedule.
    """
    offset = qa_set_config(qa_set)["group_offset"]
    chapter_order = GROUPS.copy()
    random.Random(str(participant_id)).shuffle(chapter_order)  # stable per participant
    cells = []
    for seq, group in enumerate(chapter_order):
        condition = SLOTS[(group - 1 + block_index) % len(SLOTS)]
        cells.append((offset + group, condition, seq))
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


def qa_set_window_count(db, qa_set) -> int:
    groups = qa_set_groups(qa_set)
    return db.scalar(
        select(func.count(ExperimentWindow.id)).where(ExperimentWindow.group_index.in_(groups))
    ) or 0


def available_qa_sets(db):
    """Question sets with imported windows, in QA_SETS order: [(key, label, n_windows)]."""
    out = []
    for key, config in QA_SETS.items():
        count = qa_set_window_count(db, key)
        if count:
            out.append((key, config["label"], count))
    return out


def tier1_variant_gaps(db, language, qa_set=None):
    """Missing (source passage, condition) variants required by imported windows.

    With ``qa_set`` only that set's windows are checked.
    """
    stmt = select(ExperimentWindow.source_passage_id).distinct()
    if qa_set is not None:
        stmt = stmt.where(ExperimentWindow.group_index.in_(qa_set_groups(qa_set)))
    source_ids = set(db.scalars(stmt).all())
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


def write_participant_plan(db, participant, block_index: int, language: str = LANGUAGE,
                           qa_set: str = DEFAULT_QA_SET):
    """Stage one participant's plan cells (caller commits). Returns the cell tuples.

    Same checks as the CLI: refuses when nothing is imported, when a tier-1 variant is
    missing, or when the participant already has a plan. ``qa_set`` picks which
    imported question set the participant is served.
    """
    config = qa_set_config(qa_set)
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
    if not is_tier1 and config["group_offset"]:
        raise ExperimentPlanError(f"Question set '{qa_set}' needs the tier-1 window import")
    if is_tier1:
        if not qa_set_window_count(db, qa_set):
            raise ExperimentPlanError(
                f"Question set '{qa_set}' has no imported questions. Run its pilot import first."
            )
        gaps = tier1_variant_gaps(db, language, qa_set)
        if gaps:
            raise ExperimentPlanError(
                f"{len(gaps)} tier-1 passage/condition variants are missing for "
                f"'{qa_set}' / '{language}' (first: {sorted(gaps)[:3]}). Re-run the pilot import."
            )

    cells = build_cells(participant.id, block_index % len(SLOTS), qa_set)
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


def qa_set_for_group(group):
    """Question set owning a window-group index (highest offset below it)."""
    if group is None:
        return None
    for key, config in sorted(QA_SETS.items(), key=lambda kv: -kv[1]["group_offset"]):
        if group > config["group_offset"]:
            return key
    return None


def participants_qa_sets(db, participant_ids):
    """{participant_id: question set} from each participant's plan cells (one query)."""
    if not participant_ids:
        return {}
    rows = db.execute(
        select(ExperimentPlanCell.participant_id, func.min(ExperimentPlanCell.chapter))
        .where(ExperimentPlanCell.participant_id.in_(list(participant_ids)))
        .group_by(ExperimentPlanCell.participant_id)
    ).all()
    return {pid: qa_set_for_group(group) for pid, group in rows}


def participant_qa_set(db, participant_id):
    """The question set a participant's plan cells point at, or None without a plan."""
    return participants_qa_sets(db, [participant_id]).get(participant_id)


def next_test_block_index(db, qa_set=None) -> int:
    """Rotate test participants through the 8 slot rotations (0, 1, ..., 7, 0, ...).

    With ``qa_set`` the rotation counts only test participants already planned on that
    set, so each set's test runs cycle through every rotation on their own.
    """
    participants = db.scalars(select(Participant)).all()
    test_ids = [p.id for p in participants if is_test_participant(p)]
    if qa_set is None:
        return len(test_ids) % len(SLOTS)
    sets = participants_qa_sets(db, test_ids)
    return sum(1 for pid in test_ids if sets.get(pid) == qa_set) % len(SLOTS)
