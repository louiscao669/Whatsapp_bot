#!/usr/bin/env python3
"""Tests for reset_experiment_plan: in-memory SQLite, real ORM.

Covers the two SET-NULL footguns the script exists to prevent, plus the retired-vs-current
condition split and the scoping flags.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session

from eten_shared.models import (
    Assignment, Base, ExperimentPassage, ExperimentPassageVerse, ExperimentPlanCell,
    Participant, QAItem,
)
from reset_experiment_plan import perform_reset, summarize, CURRENT_CONDITIONS

fails = []
RETIRED = ["omission10", "omission20", "mistranslation20"]


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def make_db():
    engine = create_engine("sqlite://")

    # SQLite ignores FK constraints unless asked; turn them on so ondelete=CASCADE/SET NULL
    # behave like Postgres and the test actually exercises the footguns.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return Session(engine)


def seed(db, *, with_assignment=False):
    conditions = sorted(CURRENT_CONDITIONS) + RETIRED
    passages = {}
    for ch in (1, 2):
        for cond in conditions:
            p = ExperimentPassage(chapter=ch, condition=cond, language="zh",
                                  name=f"L{ch} {cond}", passage_reference=f"Luke {ch}",
                                  passage_text="1 a\n2 b")
            db.add(p)
            db.flush()
            passages[(ch, cond)] = p.id
            db.add_all([ExperimentPassageVerse(experiment_passage_id=p.id, verse_number=n,
                                               position=n, text="x") for n in (1, 2)])
    for pid in ("P1", "P2"):
        db.add(Participant(id=pid, display_name=pid, consented=True, target_language="zh"))
    db.flush()
    cells = {}
    for pid in ("P1", "P2"):
        for seq, (ch, cond) in enumerate([(1, "omission15"), (2, "omission20")]):
            c = ExperimentPlanCell(participant_id=pid, chapter=ch, condition=cond,
                                   experiment_passage_id=passages[(ch, cond)],
                                   sequence_index=seq, status="pending")
            db.add(c)
            db.flush()
            cells[(pid, cond)] = c.id
    if with_assignment:
        db.add(QAItem(id="q1", passage_id="luke1", question_text="Q",
                      question_type="open", expected_answer="A"))
        db.flush()
        db.add(Assignment(id="a1", participant_id="P1", qa_item_id="q1", status="completed",
                          experiment_cell_id=cells[("P1", "omission15")]))
    db.commit()
    return passages, cells


def test_summarize_flags_retired():
    db = make_db()
    seed(db)
    passages, cells, n_assign, n_participants = summarize(db)
    conds = {c for c, _ in passages}
    check("summarize sees retired conditions still present",
          set(RETIRED) <= conds)
    check("summarize counts participants with a plan", n_participants == 2)
    check("summarize reports 0 stamped assignments on a fresh plan", n_assign == 0)


def test_retired_only_delete():
    db = make_db()
    seed(db)
    before = db.scalar(select(func.count(ExperimentPassage.id)))
    cells, passages = perform_reset(db, doomed_conditions=RETIRED)
    db.commit()
    left = {c for c in db.scalars(select(ExperimentPassage.condition)).all()}
    check("retired passages deleted (3 conditions x 2 chapters)", passages == 6)
    check("current-slate passages untouched", left == CURRENT_CONDITIONS)
    check("all plan cells deleted", db.scalar(select(func.count(ExperimentPlanCell.id))) == 0)
    check("passage count dropped by exactly the retired rows",
          db.scalar(select(func.count(ExperimentPassage.id))) == before - 6)
    check("verses of deleted passages are gone",
          db.scalar(select(func.count(ExperimentPassageVerse.id))) == len(CURRENT_CONDITIONS) * 2 * 2)


def test_keep_plan_cells():
    db = make_db()
    seed(db)
    cells, passages = perform_reset(db, doomed_conditions=RETIRED, keep_plan_cells=True)
    db.commit()
    check("--keep-plan-cells leaves the plan intact",
          cells == 0 and db.scalar(select(func.count(ExperimentPlanCell.id))) == 4)
    # This is the footgun the script's ordering exists to prevent: a surviving cell whose
    # passage was deleted is NOT removed, it is silently NULLed by ondelete=SET NULL.
    orphan = db.scalar(
        select(func.count(ExperimentPlanCell.id))
        .where(ExperimentPlanCell.condition == "omission20",
               ExperimentPlanCell.experiment_passage_id.is_(None)))
    check("FOOTGUN CONFIRMED: keeping cells while deleting passages orphans them (NULL FK)",
          orphan == 2)


def test_participant_scoping():
    db = make_db()
    seed(db)
    perform_reset(db, doomed_conditions=[], participant_ids=["P1"])
    db.commit()
    remaining = db.scalars(select(ExperimentPlanCell.participant_id)).all()
    check("--participant-ids limits plan-cell deletion to that participant",
          set(remaining) == {"P2"} and len(remaining) == 2)


def test_assignment_stamp_footgun():
    db = make_db()
    seed(db, with_assignment=True)
    _, _, n_assign, _ = summarize(db)
    check("summarize detects the stamped assignment (this is what --force guards)",
          n_assign == 1)
    perform_reset(db, doomed_conditions=[])
    db.commit()
    a = db.scalars(select(Assignment)).first()
    check("FOOTGUN CONFIRMED: deleting cells NULLs the assignment stamp, it does not error",
          a is not None and a.experiment_cell_id is None)


def main():
    for name, fn in [
        ("summarize", test_summarize_flags_retired),
        ("retired-only delete", test_retired_only_delete),
        ("--keep-plan-cells", test_keep_plan_cells),
        ("--participant-ids scoping", test_participant_scoping),
        ("assignment-stamp guard", test_assignment_stamp_footgun),
    ]:
        print(f"{name}:")
        fn()
    print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
