#!/usr/bin/env python3
"""Tests for verify_experiment_delivery + the delivery guard in build_assignment_prompt.

The property under test: a participant assigned to a defect condition must receive that
condition's passage, and any failure to do so must be LOUD.

This matters more than a normal integrity check because the pilot's QA is
variant-agnostic -- one QAItem set per chapter, shared across all conditions. The
passage is the only carrier of the manipulation, so a wrong passage produces data that
is indistinguishable from correct data at every downstream stage: the response scores
fine, the export writes the cell's condition label, and the analysis reads a defect
condition that was never actually shown.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_message_bot  # noqa: E402

use_message_bot()

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from eten_shared.models import (  # noqa: E402
    Base,
    ExperimentPassage,
    ExperimentPassageVerse,
    ExperimentPlanCell,
)
from eten_shared.domain.assignments import (  # noqa: E402
    ExperimentPassageMissingError,
    build_assignment_prompt,
)

from verify_experiment_delivery import verify  # noqa: E402
from build_experiment_plan import SLOTS, build_cells  # noqa: E402

FAILURES = []


def check(label, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        FAILURES.append(label)


def _session():
    _SEQ.clear()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _passage(db, pid, chapter, condition, text, verses=True):
    passage = ExperimentPassage(
        id=pid, chapter=chapter, condition=condition, language="zh",
        passage_reference=f"Luke {chapter}", passage_text=text,
    )
    db.add(passage)
    if verses:
        db.add(ExperimentPassageVerse(
            experiment_passage_id=pid, verse_number="1", position=0, text=text,
        ))
    return passage


_SEQ = {}


def _cell(db, cid, chapter, condition, passage_id, participant_id="p1"):
    # sequence_index is unique per participant, so hand out fresh ones.
    seq = _SEQ.get(participant_id, 0)
    _SEQ[participant_id] = seq + 1
    cell = ExperimentPlanCell(
        id=cid, participant_id=participant_id, chapter=chapter, condition=condition,
        experiment_passage_id=passage_id, sequence_index=seq, status="pending",
    )
    db.add(cell)
    return cell


# NOTE: the old minimal "clean plan" fixture (8 participants x 1 cell each) was
# removed when Gate 2 landed -- the design checks correctly reject it as eight
# incomplete slates. test_a_real_latin_square_passes covers the happy path using
# the production build_cells(), which is a stronger test anyway.


def test_passages_only_still_runs_the_distinctness_check():
    """Tier 1 must work with NO plan cells and NO participants.

    This is the state right after pilot_import.py: passages imported, nobody
    consented yet, no plan built. It is also the cheapest moment to discover a
    bad import -- before recruitment rather than after the study.
    """
    db = _session()
    same = "IDENTICAL text -- import took the wrong files."
    for i, condition in enumerate(sorted(set(SLOTS))):
        # every condition present (so check 8 is satisfied) but two share text
        text = same if condition in ("clean", "omission30") else f"text {condition}"
        _passage(db, f"p{i}", 1, condition, text)
    db.commit()

    problems, notes, n_cells, n_passages = verify(db, "zh")
    check("runs with zero plan cells", n_cells == 0)
    check("sees the passages", n_passages == len(set(SLOTS)))
    check("distinctness still evaluated without any cells",
          "identical_variants" in problems)
    check("explains that per-cell checks were skipped",
          any("PASSAGE-LEVEL" in note for note in notes))


def test_passages_only_clean_slate_passes():
    db = _session()
    for i, condition in enumerate(sorted(set(SLOTS))):
        _passage(db, f"p{i}", 1, condition, f"chapter one text for {condition}")
    db.commit()
    problems, _, n_cells, _ = verify(db, "zh")
    check("a good import with no plan yet reports no problems", not problems)
    check("and reports zero cells", n_cells == 0)


def test_no_passages_reports_cleanly():
    db = _session()
    problems, notes, n_cells, n_passages = verify(db, "zh")
    check("empty DB reports no passages rather than crashing",
          n_passages == 0 and not problems)
    check("tells you to run pilot_import first",
          any("pilot_import" in note for note in notes))


def test_null_passage_fk_is_caught():
    """build_experiment_plan writes this cell when pilot_import has not run."""
    db = _session()
    _passage(db, "pa", 1, "clean", "CLEAN text.")
    _cell(db, "c1", 1, "omission30", None)
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("NULL experiment_passage_id flagged", "null_passage_fk" in problems)


def test_condition_mismatch_is_caught():
    """The subtle one: a real variant, just not the assigned participant's."""
    db = _session()
    _passage(db, "pa", 1, "clean", "CLEAN text.")
    _cell(db, "c1", 1, "omission30", "pa")   # cell says omission30, passage is clean
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("cell/passage condition mismatch flagged", "condition_mismatch" in problems)


def test_identical_variants_are_caught():
    """Byte-identical clean/defect text means the import took the wrong files.

    Nothing else in the stack notices: both cells resolve, both deliver, and the
    export labels one of them a defect condition.
    """
    db = _session()
    same = "IDENTICAL text for both conditions."
    _passage(db, "pa", 2, "clean", same)
    _passage(db, "pb", 2, "omission30", same)
    _cell(db, "c1", 2, "clean", "pa", participant_id="p1")
    _cell(db, "c2", 2, "omission30", "pb", participant_id="p2")
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("byte-identical variants flagged", "identical_variants" in problems)


def test_missing_verse_rows_are_warned():
    db = _session()
    _passage(db, "pa", 3, "clean", "text", verses=False)
    _cell(db, "c1", 3, "clean", "pa")
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("passage without verse rows flagged", "no_verse_rows" in problems)


def test_dangling_passage_is_caught():
    db = _session()
    _cell(db, "c1", 4, "clean", "does-not-exist")
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("dangling passage FK flagged", "dangling_passage" in problems)


# --------------------------------------------------------------- GATE 2 (design)

def _full_plan(db, n_participants=8, chapters=range(1, 9)):
    """Build a real plan using the production build_cells(), for n participants.

    Uses the actual planner rather than a hand-rolled fixture so the test fails
    if the design itself changes.
    """
    for chapter in chapters:
        for i, condition in enumerate(sorted(set(SLOTS))):
            pid = f"p{chapter}_{i}"
            _passage(db, pid, chapter, condition, f"ch{chapter} text for {condition}")
    db.flush()
    lookup = {
        (p.chapter, p.condition): p.id
        for p in db.query(ExperimentPassage).all()
    }
    for position in range(n_participants):
        participant_id = f"pt{position:02d}"
        for chapter, condition, seq in build_cells(participant_id, position % len(SLOTS)):
            db.add(ExperimentPlanCell(
                id=f"c_{participant_id}_{chapter}",
                participant_id=participant_id, chapter=chapter, condition=condition,
                experiment_passage_id=lookup[(chapter, condition)],
                sequence_index=seq, status="pending",
            ))
    db.commit()


def test_a_real_latin_square_passes():
    db = _session()
    _full_plan(db, n_participants=8)
    problems, notes, n_cells, _ = verify(db, "zh")
    check("a real 8-participant Latin square reports no problems", not problems)
    check("counts 8 x 8 cells", n_cells == 64)
    check("reports the design summary", any("design:" in n for n in notes))


def test_each_participant_gets_clean_twice_and_others_once():
    """The slate property Tier 2b exists to protect."""
    db = _session()
    _full_plan(db, n_participants=8)
    from collections import Counter as C
    cells = db.query(ExperimentPlanCell).filter_by(participant_id="pt00").all()
    got = C(c.condition for c in cells)
    check("clean appears exactly twice (two pooled anchors)", got["clean"] == 2)
    check("every other condition appears exactly once",
          all(got[c] == 1 for c in set(SLOTS) if c != "clean"))


def test_wrong_slate_is_caught():
    """A participant holding a duplicate condition, missing another."""
    db = _session()
    _full_plan(db, n_participants=8)
    victim = db.query(ExperimentPlanCell).filter_by(
        participant_id="pt00", condition="mistranslation15").first()
    victim.condition = "omission30"          # now omission30 x2, no mistranslation15
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("broken per-participant slate flagged", "wrong_slate" in problems)
    check("and the cell/passage mismatch is flagged too",
          "condition_mismatch" in problems)


def test_incomplete_slate_is_caught():
    db = _session()
    _full_plan(db, n_participants=8)
    doomed = db.query(ExperimentPlanCell).filter_by(participant_id="pt03").first()
    db.delete(doomed)
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("participant with a missing cell flagged", "incomplete_slate" in problems)
    check("sequence gap flagged as well", "sequence_gap" in problems)


def test_unbalanced_design_is_caught():
    """A full block whose chapter x condition counts fall below the floor."""
    db = _session()
    _full_plan(db, n_participants=8)
    # Re-point every pt07 cell at chapter-matched 'clean', destroying balance.
    for cell in db.query(ExperimentPlanCell).filter_by(participant_id="pt07").all():
        cell.condition = "clean"
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("chapter x condition imbalance flagged", "unbalanced_design" in problems)


def test_partial_block_warns():
    db = _session()
    _full_plan(db, n_participants=5)      # not a multiple of 8
    problems, notes, _, _ = verify(db, "zh")
    check("partial trailing block warns", any("not a multiple" in n for n in notes))
    check("but a partial block is not itself an error",
          "unbalanced_design" not in problems)


def test_identical_chapter_order_is_caught():
    """If the per-participant shuffle degenerates, order is confounded.

    Rebuilt rather than mutated in place: (participant, sequence_index) is
    unique, so reassigning indices row-by-row collides mid-update.
    """
    db = _session()
    _full_plan(db, n_participants=8)
    lookup = {
        (p.chapter, p.condition): p.id for p in db.query(ExperimentPassage).all()
    }
    db.query(ExperimentPlanCell).delete()
    db.flush()
    for position in range(8):
        participant_id = f"pt{position:02d}"
        for chapter, condition, _seq in build_cells(participant_id, position % len(SLOTS)):
            db.add(ExperimentPlanCell(
                id=f"c_{participant_id}_{chapter}",
                participant_id=participant_id, chapter=chapter, condition=condition,
                experiment_passage_id=lookup[(chapter, condition)],
                sequence_index=chapter - 1,          # same order for everyone
                status="pending",
            ))
    db.commit()
    problems, _, _, _ = verify(db, "zh")
    check("degenerate chapter order flagged", "identical_chapter_order" in problems)


def test_prompt_refuses_to_deliver_clean_text_for_an_experiment_assignment():
    """THE regression test.

    Before 2026-08-12 build_assignment_prompt fell through to
    qa_item.passage_text -- the condition-invariant chapter text -- whenever an
    experiment assignment had no stamped snapshot. The participant then read the
    CLEAN passage while their plan cell, and therefore the export, said
    'omission30'.
    """
    db = _session()
    qa_item = SimpleNamespace(
        id="q1", question_text="Q", passage_reference="Luke 1",
        passage_text="CLEAN chapter text -- must never be delivered here",
        question_type="open", mcq_choices=[], audio_url=None,
    )
    assignment = SimpleNamespace(
        id="a1", experiment_cell_id="c1", passage_text=None,
        passage_verse_numbers=[], passage_translation_id=None,
    )
    participant = SimpleNamespace(id="p1", target_language="zh", preferred_language="zh")

    raised = False
    try:
        build_assignment_prompt(db, assignment, qa_item, participant)
    except ExperimentPassageMissingError:
        raised = True
    check("experiment assignment without a variant snapshot RAISES", raised)

    # Non-experiment assignments keep the old lenient fallback.
    plain = SimpleNamespace(
        id="a2", experiment_cell_id=None, passage_text=None,
        passage_verse_numbers=[], passage_translation_id=None,
    )
    prompt = build_assignment_prompt(db, plain, qa_item, participant)
    check("non-experiment assignment still falls back to qa_item.passage_text",
          prompt.passage_text == qa_item.passage_text)

    # And a properly stamped experiment assignment delivers the VARIANT.
    stamped = SimpleNamespace(
        id="a3", experiment_cell_id="c1",
        passage_text="OMISSION30 variant text", passage_verse_numbers=[],
        passage_translation_id=None,
    )
    prompt = build_assignment_prompt(db, stamped, qa_item, participant)
    check("stamped experiment assignment delivers the variant, not the clean text",
          prompt.passage_text == "OMISSION30 variant text")


def main():
    print("verify_experiment_delivery():")

    test_passages_only_still_runs_the_distinctness_check()
    test_passages_only_clean_slate_passes()
    test_no_passages_reports_cleanly()
    test_null_passage_fk_is_caught()
    test_condition_mismatch_is_caught()
    test_identical_variants_are_caught()
    test_missing_verse_rows_are_warned()
    test_dangling_passage_is_caught()
    print("GATE 2 -- design integrity:")
    test_a_real_latin_square_passes()
    test_each_participant_gets_clean_twice_and_others_once()
    test_wrong_slate_is_caught()
    test_incomplete_slate_is_caught()
    test_unbalanced_design_is_caught()
    test_partial_block_warns()
    test_identical_chapter_order_is_caught()
    print("delivery guard in build_assignment_prompt():")
    test_prompt_refuses_to_deliver_clean_text_for_an_experiment_assignment()

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        return 1
    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
