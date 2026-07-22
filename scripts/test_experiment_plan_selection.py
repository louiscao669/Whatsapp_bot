#!/usr/bin/env python3
"""In-memory SQLite test for the designed-assignment plan + selector.

Exercises the two new pieces against the real ORM:
  * build_experiment_plan.build_cells -> Latin-square balance + per-participant slots
  * experiment_selection.select_next_experiment_cell_item -> cell-scoping, plan-ordered
    advance, resumption stability, already-assigned exclusion, (item, cell) return, gate.

Run: python scripts/test_experiment_plan_selection.py   (needs no DB / env)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("REQUIRE_QUESTION_AUDIO", "false")  # text-mode gate (pilot default)
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eten_shared.models import (
    Assignment, Base, ExperimentPassage, ExperimentPlanCell, Participant, QAItem,
)
from eten_shared.question_discovery import select_next_experiment_cell_item
from build_experiment_plan import SLOTS, CHAPTERS, build_cells

CONDS = ["clean", "omission10", "omission20", "omission30",
         "mistranslation20", "grammar30", "wbw"]
fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def seed(db):
    # variant passages: 8 chapters x 7 conditions
    for ch in CHAPTERS:
        for c in CONDS:
            db.add(ExperimentPassage(chapter=ch, condition=c, language="zh",
                                     name=f"Luke {ch} {c}", passage_text=f"text {ch} {c}"))
    # QA: per chapter, 4 items (3 mcq / 1 open), passage_id = luke{ch}
    for ch in CHAPTERS:
        for k in range(4):
            qtype = "open" if k == 3 else "mcq"
            db.add(QAItem(
                id=f"luke{ch}-q{k}", passage_id=f"luke{ch}",
                question_text=f"Q{k} ch{ch}", question_type=qtype,
                expected_answer="a", mcq_choices=(["a", "b", "c", "d"] if qtype == "mcq" else []),
                mcq_correct_choice=("A" if qtype == "mcq" else None),
                required_keywords=[], optional_keywords=[], active=True,
            ))
    # 16 participants
    for i in range(16):
        db.add(Participant(id=f"p{i:02d}", display_name=f"P{i}", consented=True, target_language="zh"))
    db.commit()


def write_plan(db):
    pidx = {(p.chapter, p.condition): p.id
            for p in db.scalars(select(ExperimentPassage)).all()}
    parts = db.scalars(select(Participant).order_by(Participant.id)).all()
    for pos, part in enumerate(parts):
        for chapter, condition, seq in build_cells(part.id, pos % len(SLOTS)):
            db.add(ExperimentPlanCell(
                participant_id=part.id, chapter=chapter, condition=condition,
                experiment_passage_id=pidx.get((chapter, condition)),
                sequence_index=seq, status="pending"))
    db.commit()


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        write_plan(db)

        # 1. Latin-square balance: each (chapter, condition) count; clean 2x per block
        cells = db.scalars(select(ExperimentPlanCell)).all()
        by_ch_cond = {}
        for c in cells:
            by_ch_cond[(c.chapter, c.condition)] = by_ch_cond.get((c.chapter, c.condition), 0) + 1
        # 16 participants = 2 blocks; non-clean condition appears once/block => 2 total per chapter
        nonclean_ok = all(by_ch_cond.get((ch, c), 0) == 2 for ch in CHAPTERS for c in CONDS if c != "clean")
        clean_ok = all(by_ch_cond.get((ch, "clean"), 0) == 4 for ch in CHAPTERS)  # 2 slots x 2 blocks
        check("Latin square: each non-clean (chapter,condition) hit 2x (2 blocks)", nonclean_ok)
        check("Latin square: clean anchor hit 4x/chapter (2 anchor slots x 2 blocks)", clean_ok)

        # per-participant: exactly one condition per chapter, all 8 slots (clean=2)
        pcells = db.scalars(select(ExperimentPlanCell).where(
            ExperimentPlanCell.participant_id == "p00").order_by(ExperimentPlanCell.sequence_index)).all()
        check("participant has 8 cells, one per chapter", len({c.chapter for c in pcells}) == 8 and len(pcells) == 8)
        slots = {}
        for c in pcells:
            slots[c.condition] = slots.get(c.condition, 0) + 1
        check("participant sees clean=2 and each other condition=1",
              slots.get("clean") == 2 and all(slots.get(c) == 1 for c in CONDS if c != "clean"))
        check("every cell has a resolved passage FK", all(c.experiment_passage_id for c in pcells))

        # 2. Selector: serve p00's plan end-to-end, simulating answers
        served = []
        guard = 0
        while guard < 200:
            guard += 1
            part = db.get(Participant, "p00")
            item, cell = select_next_experiment_cell_item(db, part)
            if item is None:
                break
            served.append((cell.chapter, cell.condition, item.id, item.question_type))
            # simulate an answered assignment (stamped to the cell)
            db.add(Assignment(participant_id="p00", qa_item_id=item.id,
                              status="completed", experiment_cell_id=cell.id))
            db.commit()

        # returns (item, cell)
        check("selector returns (item, cell) tuples", served and all(len(s) == 4 for s in served))
        # cell-scoping: each served item's chapter matches its cell's chapter (luke{ch})
        item_ch_ok = True
        for ch, cond, iid, qt in served:
            it = db.get(QAItem, iid)
            if it.passage_id != f"luke{ch}":
                item_ch_ok = False
        check("cell-scoping: served item passage_id == luke{cell.chapter}", item_ch_ok)
        # serves whole plan: 8 chapters x 4 items = 32
        check("serves entire plan (8 chapters x 4 items = 32)", len(served) == 32)
        # plan order: chapters appear in the participant's sequence_index order, grouped
        plan_order = [c.chapter for c in pcells]
        served_chapter_runs = [ch for ch, _, _, _ in served]
        grouped = [k for k, _ in __import__("itertools").groupby(served_chapter_runs)]
        check("chapters served in plan order, one contiguous block each", grouped == plan_order)
        # MCQ-before-open within a chapter (designed strategy front-loads 75/25)
        first_chapter = plan_order[0]
        fc_types = [qt for ch, _, _, qt in served if ch == first_chapter]
        check("within a chapter, all MCQ precede open (designed order)",
              fc_types == sorted(fc_types, key=lambda t: 0 if t == "mcq" else 1))
        # all cells done at completion
        done = db.scalars(select(ExperimentPlanCell).where(
            ExperimentPlanCell.participant_id == "p00")).all()
        check("all plan cells flipped to 'done' at plan completion", all(c.status == "done" for c in done))

        # 3. Resumption stability: re-deriving the order for a fresh participant is identical
        a = build_cells("p07", 3)
        b = build_cells("p07", 3)
        check("plan build is deterministic per participant (resumption-stable)", a == b)

        # 4. Isolation: another participant's plan is untouched by p00's run
        p01_cells = db.scalars(select(ExperimentPlanCell).where(
            ExperimentPlanCell.participant_id == "p01")).all()
        check("other participants' cells remain 'pending' (isolation)",
              all(c.status == "pending" for c in p01_cells))

    print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
