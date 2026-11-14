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

from __future__ import annotations

import random
from collections import Counter

from sqlalchemy import func, select, text, update

from eten_shared.models import (
    ExperimentPassage,
    ExperimentPlanCell,
    ExperimentWindow,
    Participant,
    PilotRotationCount,
    QAItem,
)
from eten_shared.recordings import participant_language_code
from eten_shared.wh_type import group_by_wh_type

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
# Quality dimensions: which slot conditions probe ADEQUACY (meaning preservation) and
# which probe FLUENCY (target-language form). A test participant can be restricted to
# one dimension; the plan keeps only that dimension's cells. The clean anchors belong
# to both, because each ladder needs its own 0% dose for re-zeroing. ``wbw`` (word by
# word) is filed under fluency as the high-dose fluency canary, though it also damages
# open-answer production. Keys/order are what the admin form shows.
QUALITY_DIMENSIONS = {
    "adequacy": ("clean", "omission15", "omission30", "mistranslation15", "mistranslation30"),
    "fluency": ("clean", "grammar30", "wbw"),
}
PARTICIPANT_QUALITY_DIMENSIONS_KEY = "quality_dimensions"


def parse_quality_dimensions(value):
    """None / "" / [] -> []; "adequacy" / ["fluency"] -> sorted list; unknown refused."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    names = {str(v).strip().lower() for v in value if str(v).strip()}
    unknown = names - set(QUALITY_DIMENSIONS)
    if unknown:
        raise ValueError(
            f"unknown quality dimension(s) {sorted(unknown)}; known: {', '.join(QUALITY_DIMENSIONS)}"
        )
    return sorted(names)


def dimension_conditions(dimensions):
    """Conditions kept for the given dimensions; None (= keep all) when none given."""
    if not dimensions:
        return None
    return {c for d in dimensions for c in QUALITY_DIMENSIONS[d]}


# Individual conditions a test participant can be restricted to (e.g. clean +
# mistranslation only). Order and labels are what the admin form shows.
CONDITION_LABELS = {
    "clean": "Clean (2 anchor groups)",
    "omission15": "Omission 15%",
    "omission30": "Omission 30%",
    "mistranslation15": "Mistranslation 15%",
    "mistranslation30": "Mistranslation 30%",
    "grammar30": "Grammar 30%",
    "wbw": "Word-by-word (Google)",
}
PARTICIPANT_CONDITIONS_KEY = "conditions"


def parse_conditions(value):
    """None / "" / [] -> []; "clean,mistranslation30" / [...] -> list in slot order.

    Unknown names are refused, since a typo would otherwise silently shrink the plan.
    """
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    names = {str(v).strip().lower() for v in value if str(v).strip()}
    unknown = names - set(SLOTS)
    if unknown:
        raise ValueError(
            f"unknown condition(s) {sorted(unknown)}; known: {', '.join(dict.fromkeys(SLOTS))}"
        )
    return [c for c in dict.fromkeys(SLOTS) if c in names]


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
    "reviewed122": {"group_offset": 200, "passage_prefix": "reviewed122/",
                    "label": "Reviewed Chinese MCQs (earlier passages)", "language": "zh", "test_only": True},
    "reviewed122_sol": {"group_offset": 300, "passage_prefix": "reviewed122_sol/",
                        "label": "Sol Chinese · natural names", "language": "zh", "test_only": True},
}
DEFAULT_QA_SET = "gold72"
SOL_SCRATCH_SET = "reviewed122_sol_scratch"

# These choices share the original questions, passage variants, and window groups.
QA_SUBSETS = {
    "reviewed122_sol_prepared": ("reviewed122_sol", "Prepared60", "Sol Chinese · prepared QAs"),
    SOL_SCRATCH_SET: ("reviewed122_sol", "Hard77", "Sol Chinese · generated from scratch"),
}
QA_SUBSET_PREF = "qa_subset"


def is_test_bank_passage(passage_id):
    return any((passage_id or "").startswith(config["passage_prefix"])
               for config in QA_SETS.values() if config.get("test_only"))


class ExperimentPlanError(Exception):
    pass


def qa_set_config(qa_set):
    if qa_set in QA_SUBSETS:
        qa_set = QA_SUBSETS[qa_set][0]
    try:
        return QA_SETS[qa_set or DEFAULT_QA_SET]
    except KeyError:
        raise ExperimentPlanError(
            f"Unknown question set {qa_set!r} (known: {', '.join(QA_SETS)})"
        ) from None


def qa_set_groups(qa_set=DEFAULT_QA_SET):
    offset = qa_set_config(qa_set)["group_offset"]
    return [offset + group for group in GROUPS]


def is_study_qa_set(qa_set):
    """Only the scratch subset of the reviewed Sol bank is released for study plans."""
    return qa_set == SOL_SCRATCH_SET or not qa_set_config(qa_set).get("test_only")


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
        select(func.count(ExperimentWindow.id)).where(
            ExperimentWindow.group_index.in_(groups), *qa_source_filters(qa_set)
        )
    ) or 0


def qa_source_filters(qa_set):
    if qa_set not in QA_SUBSETS:
        return ()
    parent, source, _ = QA_SUBSETS[qa_set]
    prefix = QA_SETS[parent]["passage_prefix"] + source + "/"
    return (ExperimentWindow.source_passage_id.startswith(prefix, autoescape=True),)


def qa_set_wh_type_counts(db, qa_set, question_types=None) -> dict:
    """{wh_type: n} over a set's active, not-review-removed questions (every type keyed).

    Classified from the stored stem with the same classifier the selector uses, so a
    count here is exactly what a question-type-restricted participant can be served.
    ``question_types`` (e.g. {"mcq"}) limits the count to those forms.
    """
    stems = db.scalars(
        select(QAItem.question_text)
        .join(ExperimentWindow, ExperimentWindow.qa_item_id == QAItem.id)
        .where(
            ExperimentWindow.group_index.in_(qa_set_groups(qa_set)),
            *qa_source_filters(qa_set),
            *([] if qa_set_config(qa_set).get("test_only") else [QAItem.active.is_(True)]),
            QAItem.review_removed_at.is_(None),
            *([QAItem.question_type.in_(sorted(question_types))] if question_types else []),
        )
    ).all()
    return group_by_wh_type(stems)


def available_qa_sets(db):
    """Question sets with imported windows, in QA_SETS order: [(key, label, n_windows)]."""
    out = []
    labels = {key: config["label"] for key, config in QA_SETS.items()}
    labels.update({key: label for key, (_, _, label) in QA_SUBSETS.items()})
    for key, label in labels.items():
        count = qa_set_window_count(db, key)
        if count:
            out.append((key, label, count))
    return out


def tier1_variant_gaps(db, language, qa_set=None):
    """Missing (source passage, condition) variants required by imported windows.

    With ``qa_set`` only that set's windows are checked.
    """
    stmt = select(ExperimentWindow.source_passage_id).distinct()
    if qa_set is not None:
        stmt = stmt.where(ExperimentWindow.group_index.in_(qa_set_groups(qa_set)), *qa_source_filters(qa_set))
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
                           qa_set: str | None = None, conditions=None, *, dry_run=False):
    """Stage one participant's plan cells (caller commits). Returns the cell tuples.

    Same checks as the CLI: refuses when nothing is imported, when a tier-1 variant is
    missing, or when the participant already has a plan. ``qa_set`` picks which
    imported question set the participant is served. ``conditions`` (a set of slot
    condition names, see ``dimension_conditions``) keeps only those cells; the
    Latin-square rotation is unchanged, so the kept cells are exactly the full
    plan's cells for those conditions.
    """
    if qa_set is None:
        qa_set = DEFAULT_QA_SET if is_test_participant(participant) else SOL_SCRATCH_SET
    config = qa_set_config(qa_set)
    if not is_study_qa_set(qa_set) and not is_test_participant(participant):
        raise ExperimentPlanError(f"{qa_set} is available to test participants only")
    if config.get("language", language) != language:
        raise ExperimentPlanError(f"{qa_set} requires language {config['language']}")
    if qa_set == SOL_SCRATCH_SET and participant_language_code(participant) != language:
        raise ExperimentPlanError("Set the participant’s target language to Chinese (zh) before planning.")
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
    if conditions is not None:
        cells = [cell for cell in cells if cell[1] in conditions]
        if not cells:
            raise ExperimentPlanError("None of the plan's conditions were chosen")
    if not is_tier1:
        missing = [(chapter, condition) for chapter, condition, _ in cells if (chapter, condition) not in pidx]
        if missing:
            raise ExperimentPlanError(f"Missing passage variants for {language}: {missing}")
    if dry_run:
        return cells
    prefs = dict(participant.dashboard_preferences or {})
    if qa_set in QA_SUBSETS:
        prefs[QA_SUBSET_PREF] = qa_set
    else:
        prefs.pop(QA_SUBSET_PREF, None)
    if prefs != (participant.dashboard_preferences or {}):
        participant.dashboard_preferences = prefs
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


def scratch_rotation_counts(db, *, for_update=False):
    """Lock before allocating. The CLI and admin share this transaction and lock key."""
    if for_update:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(742908166)"))
        elif db.get_bind().dialect.name == "sqlite":
            # Acquire the write lock even when enrolling the very first reader.
            db.execute(update(PilotRotationCount).where(False).values(issued=0))
    saved = dict(db.execute(select(PilotRotationCount.rotation, PilotRotationCount.issued)).all())
    if saved:
        return Counter(saved)

    # Seed from existing real plans once. Afterwards screen-outs can delete all
    # personal records without changing the sequence of already issued rotations.
    # grammar30 occurs exactly once per plan and uniquely identifies its rotation.
    groups = qa_set_groups(SOL_SCRATCH_SET)
    rows = db.execute(
        select(ExperimentPlanCell.chapter, func.count())
        .join(Participant, Participant.id == ExperimentPlanCell.participant_id)
        .where(
            ExperimentPlanCell.chapter.in_(groups),
            ExperimentPlanCell.condition == "grammar30",
            Participant.dashboard_preferences[QA_SUBSET_PREF].as_string() == SOL_SCRATCH_SET,
            func.coalesce(Participant.dashboard_preferences[TEST_PARTICIPANT_KEY].as_boolean(), False).is_(False),
        )
        .group_by(ExperimentPlanCell.chapter)
    )
    counts = Counter({(SLOTS.index("grammar30") - (group - groups[0])) % len(SLOTS): n for group, n in rows})
    if for_update:
        db.add_all(PilotRotationCount(rotation=i, issued=counts[i]) for i in range(len(SLOTS)))
        db.flush()
    return counts


def write_next_scratch_plan(db, participant, counts, language=LANGUAGE, *, dry_run=False):
    """Use counts locked by scratch_rotation_counts, or simulated counts in a dry run."""
    if is_test_participant(participant):
        raise ExperimentPlanError("Study rotations are reserved for real participants.")
    rounds = min(counts[i] for i in range(len(SLOTS)))
    order = (0, 2, 4, 6, 1, 3, 5, 7) if rounds % 2 else range(len(SLOTS))
    rotation = next(i for i in order if counts[i] == rounds)
    cells = write_participant_plan(db, participant, rotation, language, qa_set=SOL_SCRATCH_SET,
                                   dry_run=dry_run)
    if not dry_run:
        participant.dashboard_preferences = {
            **participant.dashboard_preferences,
            "study_enrollment_number": sum(counts.values()) + 1,
            "study_rotation": rotation + 1,
        }
        db.execute(update(PilotRotationCount).where(PilotRotationCount.rotation == rotation)
                   .values(issued=PilotRotationCount.issued + 1))
    counts[rotation] += 1
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
        select(ExperimentPlanCell.participant_id, func.min(ExperimentPlanCell.chapter),
               Participant.dashboard_preferences[QA_SUBSET_PREF].as_string())
        .join(Participant, Participant.id == ExperimentPlanCell.participant_id)
        .where(ExperimentPlanCell.participant_id.in_(list(participant_ids)))
        .group_by(ExperimentPlanCell.participant_id, Participant.id)
    ).all()
    result = {}
    for pid, group, subset in rows:
        bank = qa_set_for_group(group)
        result[pid] = subset if subset in QA_SUBSETS and QA_SUBSETS[subset][0] == bank else bank
    return result


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
