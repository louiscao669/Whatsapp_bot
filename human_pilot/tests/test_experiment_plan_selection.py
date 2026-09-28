#!/usr/bin/env python3
"""In-memory SQLite test for the designed-assignment plan + selector.

Exercises the two new pieces against the real ORM:
  * build_experiment_plan.build_cells -> Latin-square balance + per-participant slots
  * experiment_selection.select_next_experiment_cell_item -> cell-scoping, plan-ordered
    advance, resumption stability, already-assigned exclusion, (item, cell) return, gate.

Run: python human_pilot/tests/test_experiment_plan_selection.py   (needs no DB / env)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("REQUIRE_QUESTION_AUDIO", "false")  # text-mode gate (pilot default)
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "human_pilot"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eten_shared.models import (
    Assignment, Base, ExperimentPassage, ExperimentPlanCell, Participant,
    ParticipantSession, QAItem,
)
from eten_shared.domain.assignments import create_assignment_for_qa_item
from eten_shared.question_discovery import (
    experiment_batch_should_reset, select_next_experiment_cell_item,
)
from eten_shared.question_discovery.experiment_selection import (
    DEFAULT_STRATEGY, active_strategy, filter_candidates_by_wh_type,
    wh_preference_strategy, wh_type_strict,
)
from build_experiment_plan import SLOTS, CHAPTERS, build_cells

# [CHANGED 2026-07-27b] Derive the condition set from SLOTS instead of restating it, so a
# re-slate of the design cannot silently drift away from what the tests assert against.
# dict.fromkeys keeps SLOTS order and collapses the two pooled "clean" anchors to one entry.
CONDS = list(dict.fromkeys(SLOTS))
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


# ------------------------------------------------------------------ strict wh arm
# WH_TYPE_STRICT=1 turns the preference into a filter. Its whole point is the thing the
# soft version refuses to do: SKIP a cell that holds no item of the wanted stem. These
# checks run on their own tiny fixture (3 chapters, hand-written cells) because the Latin
# square in main() deliberately has no stem variation to skip.
STRICT_STEMS = {
    101: [("why", "为什么这人离开？"), ("what", "他偷了什么？")],
    102: [("who", "他的父亲是谁？"), ("what", "他们带走了什么？")],   # holds no why
    103: [("why", "为什么他们逃走？"), ("when", "他们什么时候来？")],
}


class _Item:
    def __init__(self, ident, text, qtype="mcq"):
        self.id, self.question_text, self.question_type = ident, text, qtype


def strict_fixture():
    """Fresh in-memory DB: 3 chapters x 2 items, one chapter with no why item."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Participant(id="s00", display_name="S0", consented=True, target_language="zh"))
    for seq, (ch, stems) in enumerate(sorted(STRICT_STEMS.items())):
        for k, (_kind, text) in enumerate(stems):
            db.add(QAItem(
                id=f"luke{ch}-s{k}", passage_id=f"luke{ch}",
                question_text=text, question_type="mcq", expected_answer="a",
                mcq_choices=["a", "b", "c", "d"], mcq_correct_choice="A",
                required_keywords=[], optional_keywords=[], active=True,
            ))
        db.add(ExperimentPlanCell(participant_id="s00", chapter=ch, condition="clean",
                                  sequence_index=seq, status="pending"))
    db.commit()
    return db


def drain(db):
    """Serve the participant's whole plan, returning the stems served."""
    served = []
    for _ in range(50):
        part = db.get(Participant, "s00")
        item, cell = select_next_experiment_cell_item(db, part)
        if item is None:
            break
        served.append((cell.chapter, item.question_text))
        db.add(Assignment(participant_id="s00", qa_item_id=item.id,
                          status="completed", experiment_cell_id=cell.id))
        db.commit()
    return served


def strict_checks():
    prev_pref = os.environ.pop("WH_TYPE_PREFERENCE", None)
    prev_strict = os.environ.pop("WH_TYPE_STRICT", None)
    try:
        check("strict: flag off by default", not wh_type_strict())
        for truthy in ("1", "true", "YES", "on"):
            os.environ["WH_TYPE_STRICT"] = truthy
            if not wh_type_strict():
                check(f"strict: {truthy!r} reads as on", False)
                break
        else:
            check("strict: 1/true/yes/on all read as on", True)
        os.environ["WH_TYPE_STRICT"] = "0"
        check("strict: '0' reads as off", not wh_type_strict())

        # no-op guard: an empty keep set must never filter anything away
        check("strict: empty keep set is a no-op filter",
              len(filter_candidates_by_wh_type([_Item("a", "谁来了？")], frozenset())) == 1)

        # --- strict ON, why only
        os.environ["WH_TYPE_PREFERENCE"] = "why"
        os.environ["WH_TYPE_STRICT"] = "1"
        db = strict_fixture()
        served = drain(db)
        check("strict: serves ONLY why stems",
              served and all("为什么" in text for _ch, text in served))
        check("strict: serves every why item and nothing else (2 of 6)", len(served) == 2)
        check("strict: never serves from the why-less chapter",
              102 not in {ch for ch, _ in served})
        skipped = db.scalars(select(ExperimentPlanCell).where(
            ExperimentPlanCell.participant_id == "s00",
            ExperimentPlanCell.chapter == 102)).first()
        check("strict: the why-less cell is flipped to done, not left pending",
              skipped is not None and skipped.status == "done")
        check("strict: plan runs to completion (returns None, not a hang)",
              select_next_experiment_cell_item(db, db.get(Participant, "s00")) == (None, None))
        db.close()

        # --- strict ON for a stem NO cell holds: the plan yields nothing at all
        os.environ["WH_TYPE_PREFERENCE"] = "where"
        db = strict_fixture()
        check("strict: a stem absent from every cell yields (None, None), not a fallback",
              select_next_experiment_cell_item(db, db.get(Participant, "s00")) == (None, None))
        db.close()

        # --- strict OFF: the soft arm is untouched by any of this
        os.environ["WH_TYPE_PREFERENCE"] = "why"
        os.environ.pop("WH_TYPE_STRICT", None)
        db = strict_fixture()
        served = drain(db)
        check("soft arm unchanged: still serves all 6 items across all 3 chapters",
              len(served) == 6 and len({ch for ch, _ in served}) == 3)
        check("soft arm unchanged: why still served first in a chapter that holds one",
              [t for c, t in served if c == 101][0] == "为什么这人离开？")
        db.close()
    finally:
        for key, val in (("WH_TYPE_PREFERENCE", prev_pref), ("WH_TYPE_STRICT", prev_strict)):
            os.environ.pop(key, None)
            if val is not None:
                os.environ[key] = val



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

        # 5. Caller wiring: batch-boundary helper + passage stamping (mirrors the
        #    workflow/dashboard experiment branch) for a fresh participant p01.
        p01 = db.get(Participant, "p01")
        sess = ParticipantSession(participant_id="p01", state="idle")
        db.add(sess); db.commit()
        p01_plan = db.scalars(select(ExperimentPlanCell).where(
            ExperimentPlanCell.participant_id == "p01").order_by(
            ExperimentPlanCell.sequence_index)).all()

        # empty batch never resets
        check("batch-reset: empty batch -> no reset", experiment_batch_should_reset(db, None, p01_plan[0]) is False)

        # drive two chapters via the same branch logic the callers use
        batch_ids, stamped = [], []
        for _ in range(200):
            item, cell = select_next_experiment_cell_item(db, p01)
            if item is None:
                break
            if experiment_batch_should_reset(db, sess.current_batch_id, cell):
                sess.current_batch_id = None
            variant = db.get(ExperimentPassage, cell.experiment_passage_id)
            prompt = create_assignment_for_qa_item(
                db, p01, sess, item, assignment_source="experiment",
                experiment_cell_id=cell.id, passage_text=variant.passage_text,
            )
            a = db.get(Assignment, prompt.assignment_id)
            a.status = "completed"
            batch_ids.append((cell.chapter, cell.condition, a.batch_id))
            stamped.append((a.experiment_cell_id == cell.id,
                            a.passage_text == variant.passage_text))
            db.commit()

        check("every experiment assignment stamped experiment_cell_id + variant passage_text",
              stamped and all(all(s) for s in stamped))
        # one batch_id per (chapter,condition) cell; distinct across chapters
        by_cell = {}
        for ch, cond, bid in batch_ids:
            by_cell.setdefault((ch, cond), set()).add(bid)
        one_batch_per_cell = all(len(v) == 1 for v in by_cell.values())
        distinct_across_cells = len({next(iter(v)) for v in by_cell.values()}) == len(by_cell)
        check("batch never mixes conditions: one batch_id per cell", one_batch_per_cell)
        check("batch resets at cell boundary: distinct batch_id per cell", distinct_across_cells)

    # ---------------------------------------------------------------- wh-type arm
    # WH_TYPE_PREFERENCE weights selection toward one interrogative (the question-type
    # arm from 2026-09-26). It must be OFF unless set, must prefer rather than filter,
    # and must reject a typo instead of silently serving an unrestricted stream.
    prev = os.environ.pop("WH_TYPE_PREFERENCE", None)
    try:
        check("wh arm: unset -> the designed strategy, unchanged",
              active_strategy() is DEFAULT_STRATEGY)
        os.environ["WH_TYPE_PREFERENCE"] = "why,how"
        check("wh arm: set -> a different strategy is installed",
              active_strategy() is not DEFAULT_STRATEGY)
        os.environ["WH_TYPE_PREFERENCE"] = "wat"
        typo_rejected = False
        try:
            active_strategy()
        except ValueError:
            typo_rejected = True
        check("wh arm: an unknown stem type raises, never silently unrestricts",
              typo_rejected)
    finally:
        os.environ.pop("WH_TYPE_PREFERENCE", None)
        if prev is not None:
            os.environ["WH_TYPE_PREFERENCE"] = prev

    class _Cell:
        participant_id = "p00"

    why = _Item("w1", "为什么但人寻找地盘？")
    who = _Item("h1", "亚比米勒的父亲是谁？")
    what = _Item("t1", "米该偷了什么？")
    strat = wh_preference_strategy({"why"})
    check("wh arm: picks the why item when the cell holds one",
          strat(_Cell(), [who, what, why], None) is why)
    check("wh arm: FALLS BACK to the cell's items when it holds no why item",
          strat(_Cell(), [who, what], None) in (who, what))
    check("wh arm: a cell with only why items is unaffected",
          strat(_Cell(), [why], None) is why)
    # the fallback is what protects the Latin square: every cell stays answerable, so no
    # chapter silently drops out of a participant's plan.
    check("wh arm: never returns None for a non-empty cell",
          all(strat(_Cell(), c, None) is not None
              for c in ([who], [what, who], [why, who])))
    check("wh arm: ordering inside the preferred subset still delegates to inner",
          wh_preference_strategy({"why"}, inner=lambda c, r, p: r[-1])(
              _Cell(), [who, why, what], None) is why)

    strict_checks()

    print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
