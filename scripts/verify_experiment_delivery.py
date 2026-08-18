#!/usr/bin/env python3
"""Preflight: does every planned participant actually receive the RIGHT passage variant?

Why this exists
---------------
In the human pilot the QA set is **variant-agnostic**: ``pilot_import.py`` writes one
QAItem per (chapter, question) with ``passage_id='luke{ch}'``, shared across all 8
conditions. Only the *passage* varies, via ``ExperimentPlanCell.experiment_passage_id``.

That means the passage is the ONLY carrier of the manipulation -- and nothing downstream
can detect a mismatch. If a participant in the ``omission30`` cell is shown the clean
chapter, their answers, scores, and export all look perfectly well-formed, and the
exported condition still reads ``omission30`` because it comes from the plan cell, not
from the text. The experiment would silently not happen.

Two reachable ways to get there, both leaving a plausible-looking plan:

  * ``build_experiment_plan.py`` writes a cell with ``experiment_passage_id=None`` when
    ``pilot_import.py`` has not imported that condition yet. It reports the gap at the
    end but creates the cell regardless.
  * ``reset_experiment_plan.py``'s ``ondelete=SET NULL`` FKs strip the passage from a
    live cell without erroring.

``build_assignment_prompt`` now raises on both rather than falling back to the
condition-invariant ``qa_item.passage_text``, so this script is the preflight that finds
them BEFORE a participant hits a runtime error.

Checks, in two tiers by what they require
-----------------------------------------
This reads ExperimentPassage, ExperimentPassageVerse and ExperimentPlanCell. It never
reads QAItem -- QA is variant-agnostic, so it carries no condition information and
cannot corroborate or contradict anything here.

TIER 1 -- passages only. Run right after ``pilot_import.py``, before any participant
has consented and before a plan exists:

  7. DISTINCTNESS: within a chapter, different conditions have different passage text.
     This is the check that actually proves the manipulation is present in what gets
     delivered. Byte-identical clean/omission30 means the import took the wrong files.
  8. every condition in the pilot slate is present for every chapter

TIER 2 -- DELIVERY wiring. Needs plan cells (and therefore consented participants).
Run after ``build_experiment_plan.py``. Asks: will this cell deliver the right text?

  1. every plan cell has an ``experiment_passage_id``
  2. that passage row still exists
  3. passage.condition == cell.condition        (right variant, not just some variant)
  4. passage.chapter   == cell.chapter
  5. passage text is non-empty
  6. the passage has ExperimentPassageVerse rows (else delivery silently widens from a
     3-verse window to the whole chapter -- condition-correct but not comparable)

TIER 2b -- DESIGN integrity. Same trigger, different question: is the plan still the
designed Latin square? A plan can be perfectly wired and still not be an experiment.
These faults survive delivery and scoring untouched and surface only as a confound at
analysis time, when nothing can be done about them.

  9.  every participant has a full slate of cells
  10. no participant sees a chapter twice
  11. each participant's condition multiset == SLOTS exactly (``clean`` twice -- the two
      pooled anchors -- every other condition once). NOT schema-enforced: the unique
      constraints cover (participant, chapter) and (participant, sequence_index) only,
      so a participant could hold omission30 twice and never see mistranslation15.
  12. sequence_index contiguous from 0
  13. chapter order varies across participants (the per-participant shuffle exists to
      decouple presentation order from condition; if it degenerates, order is confounded)
  14. participant count is a multiple of len(SLOTS), else the trailing block is partial
      and balance is incomplete (warning -- the design tolerates down to N=12)
  15. chapter x condition balance meets the floor implied by the number of full blocks
  16. no consented participant is missing a plan (build_experiment_plan skips anyone who
      already has cells, so late consenters are silently left out of the design)

Tier 1 is the highest-value half and the cheapest to act on: a bad import found before
recruitment costs a re-import; the same fault found after costs the study.

Usage (from repo root):
  python scripts/verify_experiment_delivery.py                 # needs DATABASE_URL
  python scripts/verify_experiment_delivery.py --language zh
  python scripts/verify_experiment_delivery.py --show-samples  # print text heads

Exit code 0 = clean, 1 = problems found.

NOT covered: a systematically mislabeled import. If ``pilot_import.CONDITIONS`` mapped
``omission15`` to the ``omission/30%`` directory, every check above passes -- the rows
are self-consistent, distinct and correctly labelled; they just came from the wrong
files. Detecting that requires comparing the stored text against the source variant
files on disk, which nothing in the database can do.
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_message_bot  # noqa: E402

use_message_bot()

from sqlalchemy import select  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.models import (  # noqa: E402
    ExperimentPassage,
    ExperimentPassageVerse,
    ExperimentPlanCell,
    ExperimentWindow,
    Participant,
)

try:
    from build_experiment_plan import SLOTS
except Exception:  # pragma: no cover - only if the plan builder moves
    SLOTS = []

LANGUAGE = "zh"


def _fail(problems, category, message):
    problems[category].append(message)


def _verify_plan_design(db, cells, problems, notes):
    """Checks 9-15: is the plan still the designed Latin square?

    ``build_cells`` assigns ``condition = SLOTS[(chapter - 1 + block_index) % 8]``
    over a per-participant shuffled chapter order. Two consequences define the
    design, and both are checkable only once cells exist:

      * within a participant, (chapter-1+block) mod 8 is a bijection over the 8
        chapters, so the participant's condition multiset must equal SLOTS
        exactly -- ``clean`` twice (the two pooled anchors), every other
        condition once;
      * across a full block of 8 participants, block_index runs 0..7, so every
        (chapter, condition) pair occurs a fixed number of times.

    Neither is enforced by the schema. The unique constraints cover
    (participant, chapter) and (participant, sequence_index) only.
    """
    by_participant = defaultdict(list)
    for cell in cells:
        by_participant[cell.participant_id].append(cell)

    expected_slate = Counter(SLOTS) if SLOTS else None
    n_slots = len(SLOTS) if SLOTS else 0
    chapter_orders = {}

    for participant_id, participant_cells in sorted(by_participant.items()):
        who = f"participant {participant_id}"

        # 9. slate size
        if n_slots and len(participant_cells) != n_slots:
            _fail(problems, "incomplete_slate",
                  f"{who}: {len(participant_cells)} cells, expected {n_slots} "
                  "-> this participant is missing conditions entirely")

        # 10. each chapter exactly once (DB-enforced, verified cheaply)
        chapters = [c.chapter for c in participant_cells]
        duplicates = [ch for ch, n in Counter(chapters).items() if n > 1]
        if duplicates:
            _fail(problems, "duplicate_chapter",
                  f"{who}: sees chapter(s) {sorted(duplicates)} more than once")

        # 11. condition multiset == SLOTS
        if expected_slate:
            got = Counter(c.condition for c in participant_cells)
            if got != expected_slate:
                missing = sorted((expected_slate - got).elements())
                extra = sorted((got - expected_slate).elements())
                _fail(problems, "wrong_slate",
                      f"{who}: condition slate is wrong "
                      f"(missing {missing or 'nothing'}, extra {extra or 'nothing'}) "
                      "-> this participant's within-subject contrasts are broken")

        # 12. sequence_index contiguous from 0
        sequences = sorted(c.sequence_index for c in participant_cells)
        if sequences != list(range(len(sequences))):
            _fail(problems, "sequence_gap",
                  f"{who}: sequence_index is {sequences}, expected "
                  f"{list(range(len(sequences)))} -> cells may be served out of order "
                  "or one was deleted")

        chapter_orders[participant_id] = tuple(
            c.chapter for c in sorted(participant_cells, key=lambda x: x.sequence_index)
        )

    # 13. chapter order must vary across participants, or presentation order is
    #     confounded with condition for everyone in the same way.
    if len(chapter_orders) > 1 and len(set(chapter_orders.values())) == 1:
        _fail(problems, "identical_chapter_order",
              f"all {len(chapter_orders)} participants share the SAME chapter order "
              f"{next(iter(chapter_orders.values()))} -> order effects are perfectly "
              "confounded with chapter, which the per-participant shuffle exists to break")

    # 14. block completeness. Balance is only guaranteed at multiples of 8.
    n_participants = len(by_participant)
    if n_slots and n_participants % n_slots:
        notes.append(
            f"WARNING: {n_participants} participants is not a multiple of {n_slots}; "
            f"the final block of {n_participants % n_slots} is partial, so "
            "chapter x condition balance is incomplete (design tolerates down to N=12)."
        )

    # 15. chapter x condition balance across participants
    pair_counts = Counter((c.chapter, c.condition) for c in cells)
    if expected_slate and n_participants >= n_slots:
        full_blocks = n_participants // n_slots
        chapters_seen = {c.chapter for c in cells}
        for chapter in sorted(chapters_seen):
            for condition, multiplicity in sorted(expected_slate.items()):
                expected_n = full_blocks * multiplicity
                actual = pair_counts.get((chapter, condition), 0)
                # Only assert the guaranteed floor: a partial trailing block can
                # add to a pair but never subtract from a completed block.
                if actual < expected_n:
                    _fail(problems, "unbalanced_design",
                          f"chapter {chapter} x {condition!r}: {actual} participants, "
                          f"expected at least {expected_n} from {full_blocks} full "
                          "block(s) -> Latin square is not balanced")

    # 16. consented participants with no plan at all. build_experiment_plan
    #     skips anyone who already has cells, so a participant who consented
    #     after the last run is silently left out -- they would be served by
    #     whatever the selector does with an empty plan, not by the design.
    try:
        consented = set(db.scalars(
            select(Participant.id).where(Participant.consented.is_(True))
        ).all())
    except Exception:  # column/table shape differs in some test fixtures
        consented = set()
    unplanned = sorted(consented - set(by_participant))
    if unplanned:
        _fail(problems, "consented_without_plan",
              f"{len(unplanned)} consented participant(s) have no plan cells: "
              f"{unplanned[:10]}{' ...' if len(unplanned) > 10 else ''} "
              "-> re-run build_experiment_plan.py --all-consented")

    notes.append(
        f"design: {n_participants} participants x {n_slots or '?'} cells; "
        f"{len(set(chapter_orders.values()))} distinct chapter orders."
    )


def verify(db, language, show_samples=False):
    problems = defaultdict(list)
    notes = []

    passages = {
        p.id: p
        for p in db.scalars(
            select(ExperimentPassage).where(ExperimentPassage.language == language)
        ).all()
    }
    cells = list(db.scalars(select(ExperimentPlanCell)).all())
    windows = list(db.scalars(select(ExperimentWindow)).all())
    tier1_mode = bool(windows)
    windows_by_group = defaultdict(list)
    for window in windows:
        windows_by_group[window.group_index].append(window)
    passage_by_source_condition = {
        (p.source_passage_id, p.condition): p for p in passages.values()
    }

    # TIER 1 -- passage-level (checks 7-8). Needs ONLY the passages, so it runs
    # straight after pilot_import.py, before any participant has consented and
    # before any plan exists. These are the checks that prove the manipulation
    # is actually present in the text that would be delivered, so run them as
    # early as possible: a bad import is far cheaper to fix before recruitment.
    if not passages and not cells:
        notes.append(f"No experiment passages for language {language!r} and no plan "
                     "cells -- run pilot_import.py first.")
        return problems, notes, 0, 0
    if not passages:
        # Cells but no passages: every cell is dangling. Fall through so the
        # per-cell loop reports them individually rather than returning early.
        notes.append(f"No experiment passages for language {language!r}, but "
                     f"{len(cells)} plan cells exist -- every cell is broken.")

    # TIER 2 -- per-cell integrity (checks 1-6). Needs plan cells, which need
    # consented participants. Skipped (not failed) when no plan exists yet.
    if not cells:
        notes.append(
            "No plan cells yet -- ran PASSAGE-LEVEL checks only. Re-run after "
            "build_experiment_plan.py to check per-cell wiring (NULL FKs, "
            "condition mismatch, dangling passages)."
        )

    for cell in cells:
        where = (f"cell {cell.id} [participant {cell.participant_id} "
                 f"ch{cell.chapter} {cell.condition!r}]")

        if tier1_mode:
            group_windows = windows_by_group.get(cell.chapter, [])
            if not group_windows:
                _fail(problems, "empty_window_group",
                      f"{where}: group has no experiment windows")
                continue
            for window in group_windows:
                passage = passage_by_source_condition.get(
                    (window.source_passage_id, cell.condition)
                )
                if passage is None:
                    _fail(problems, "missing_dynamic_passage",
                          f"{where}: no {cell.condition!r} variant for "
                          f"{window.source_passage_id}")
                    continue
                if not (passage.passage_text or "").strip():
                    _fail(problems, "empty_passage", f"{where}: passage text is empty")
                available = set(db.scalars(
                    select(ExperimentPassageVerse.verse_number).where(
                        ExperimentPassageVerse.experiment_passage_id == passage.id
                    )
                ).all())
                if not available.intersection(window.verse_numbers):
                    _fail(problems, "window_not_recoverable",
                          f"{where}: {window.window_key} has no recoverable verse in "
                          f"{window.source_passage_id}/{cell.condition}")
            continue

        if not cell.experiment_passage_id:
            _fail(problems, "null_passage_fk",
                  f"{where}: experiment_passage_id is NULL -> would deliver CLEAN text")
            continue

        passage = passages.get(cell.experiment_passage_id)
        if passage is None:
            passage = db.get(ExperimentPassage, cell.experiment_passage_id)
        if passage is None:
            _fail(problems, "dangling_passage",
                  f"{where}: passage {cell.experiment_passage_id} does not exist")
            continue

        if passage.condition != cell.condition:
            _fail(problems, "condition_mismatch",
                  f"{where}: passage is condition {passage.condition!r} "
                  "-> participant sees the WRONG variant")
        if passage.chapter != cell.chapter:
            _fail(problems, "chapter_mismatch",
                  f"{where}: passage is chapter {passage.chapter}")
        if not (passage.passage_text or "").strip():
            _fail(problems, "empty_passage", f"{where}: passage text is empty")

        verse_count = db.scalar(
            select(ExperimentPassageVerse)
            .where(ExperimentPassageVerse.experiment_passage_id == passage.id)
            .with_only_columns(ExperimentPassageVerse.id)
            .limit(1)
        )
        if verse_count is None:
            _fail(problems, "no_verse_rows",
                  f"{where}: passage has no verse rows -> delivery falls back to the "
                  "WHOLE passage instead of a 3-verse window (not comparable across cells)")

    # TIER 2b -- DESIGN integrity (checks 9-15).
    #
    # Tier 2 above asks "will this cell deliver the right text". These ask a
    # different question: "is the plan still the designed experiment". A plan can
    # be perfectly wired and still not be a Latin square -- every cell resolving
    # correctly says nothing about whether conditions are balanced across
    # chapters, or whether a participant got omission30 twice and never saw
    # mistranslation15. Those faults survive delivery, survive scoring, and only
    # surface as a confound at analysis time, when nothing can be done.
    if cells:
        _verify_plan_design(db, cells, problems, notes)

    # --- distinctness (check 7) ----------------------------------------------
    by_chapter = defaultdict(dict)
    for passage in passages.values():
        unit = passage.source_passage_id or passage.chapter
        by_chapter[unit][passage.condition] = passage.passage_text or ""

    for chapter in sorted(by_chapter, key=str):
        seen = {}
        for condition, text in sorted(by_chapter[chapter].items()):
            key = text.strip()
            if not key:
                continue
            if key in seen:
                # clean appears twice in the slate by design (two anchor slots),
                # but they resolve to ONE passage row, so this is a real collision.
                _fail(problems, "identical_variants",
                      f"chapter {chapter}: conditions {seen[key]!r} and {condition!r} "
                      "have BYTE-IDENTICAL passage text -> the manipulation is absent "
                      "from at least one of them")
            else:
                seen[key] = condition

    # --- slate coverage (check 8) --------------------------------------------
    expected = sorted(set(SLOTS)) if SLOTS else []
    if expected:
        for chapter in sorted(by_chapter, key=str):
            missing = [c for c in expected if c not in by_chapter[chapter]]
            if missing:
                _fail(problems, "missing_conditions",
                      f"chapter {chapter}: no passage imported for {missing}")

    # --- reporting -----------------------------------------------------------
    if show_samples:
        notes.append("passage text heads by chapter/condition:")
        for chapter in sorted(by_chapter, key=str):
            for condition in sorted(by_chapter[chapter]):
                head = by_chapter[chapter][condition].strip().replace("\n", " ")[:70]
                notes.append(f"    ch{chapter:>2} {condition:<20} {head}")

    return problems, notes, len(cells), len(passages)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--language", default=LANGUAGE)
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--show-samples", action="store_true",
                    help="print the first characters of each variant for eyeballing")
    args = ap.parse_args()

    session_factory = (
        get_session_factory(args.database_url) if args.database_url
        else get_session_factory()
    )
    with session_factory() as db:
        problems, notes, n_cells, n_passages = verify(
            db, args.language, args.show_samples
        )

    print(f"Checked {n_passages} passages and {n_cells} plan cells "
          f"(language {args.language!r}).")
    for note in notes:
        print(note)

    if not problems:
        if n_cells:
            print("\nOK: all variants are distinct, and every plan cell resolves to "
                  "its own condition's passage.")
        else:
            print("\nOK (passage-level): all variants are distinct and the slate is "
                  "complete. Per-cell wiring not yet checked -- re-run after "
                  "build_experiment_plan.py.")
        return 0

    print("\nPROBLEMS FOUND")
    severity = {
        "null_passage_fk": "CRITICAL -- delivers CLEAN text under a defect label",
        "condition_mismatch": "CRITICAL -- delivers the WRONG variant",
        "identical_variants": "CRITICAL -- manipulation absent from the delivered text",
        "dangling_passage": "CRITICAL -- assignment will fail at delivery",
        "empty_passage": "CRITICAL -- nothing to read",
        "chapter_mismatch": "CRITICAL -- wrong chapter",
        "no_verse_rows": "WARNING -- window widens to the whole passage",
        "incomplete_slate": "CRITICAL -- participant is missing conditions",
        "wrong_slate": "CRITICAL -- within-subject contrasts broken",
        "duplicate_chapter": "CRITICAL -- chapter repeated for one participant",
        "unbalanced_design": "CRITICAL -- Latin square not balanced",
        "identical_chapter_order": "CRITICAL -- order confounded with chapter",
        "sequence_gap": "WARNING -- cells may serve out of order",
        "consented_without_plan": "WARNING -- participant excluded from the design",
        "missing_conditions": "WARNING -- slate incomplete for this chapter",
        "empty_window_group": "CRITICAL -- plan group has no questions",
        "missing_dynamic_passage": "CRITICAL -- tier-1 QA cannot resolve its variant",
        "window_not_recoverable": "CRITICAL -- assigned window has no delivered verse",
    }
    for category, messages in sorted(problems.items()):
        print(f"\n[{category}] {severity.get(category, '')}  ({len(messages)})")
        for message in messages[:20]:
            print(f"  - {message}")
        if len(messages) > 20:
            print(f"  ... and {len(messages) - 20} more")

    print("\nRepair order: reset_experiment_plan.py --dry-run -> reset_experiment_plan.py "
          "-> pilot_import.py -> build_experiment_plan.py --all-consented")
    return 1


if __name__ == "__main__":
    sys.exit(main())
