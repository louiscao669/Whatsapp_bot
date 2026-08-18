#!/usr/bin/env python3
"""Tests for the pilot_import item exclusions (2026-07-27b) + stale-QA prune.

pilot_import imports Flask/platform at module scope, so the pure planning helpers are
extracted via AST -- the same trick the slate-consistency test uses.
"""
import ast
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


class FakeQAItem:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def load_planning_helpers():
    """exec just the DB-free planning functions out of pilot_import.py."""
    src = (REPO_ROOT / "scripts" / "pilot_import.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = {"_open_suitability_key", "choose_question_types", "allowed_forms",
             "load_chapter_qa", "_variant_dir", "_pick", "_base_id", "build_qa_item",
             "build_plan", "load_mcq_rewrites", "load_passage", "validate_eval_root"}
    consts = {"ANSWER_MODELS", "MCQ_FRACTION", "_warned", "EXCLUDED_OPEN_STEMS",
              "MCQ_REWRITES_FILENAME", "CHAPTERS", "CONDITIONS", "LANGUAGE"}
    keep = [n for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name in funcs)
            or (isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) in consts for t in n.targets))]
    ns = {"json": json, "hashlib": hashlib, "Path": Path, "sys": sys, "QAItem": FakeQAItem}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "<pilot_import>", "exec"), ns)
    return ns


NS = load_planning_helpers()
EVAL = REPO_ROOT / "evaluation"
# the three items retired upstream: 2 MCQs with no rewrite + 1 unscoped open form
RETIRED_MCQ = {"uw-174346", "uw-174388"}
AMBIGUOUS_OPEN = "uw-174382"


def test_allowed_forms():
    rewrites = NS["load_mcq_rewrites"](EVAL)
    qa2 = NS["load_chapter_qa"](EVAL, 2)
    qa4 = NS["load_chapter_qa"](EVAL, 4)
    a2 = NS["allowed_forms"](qa2, rewrites)
    a4 = NS["allowed_forms"](qa4, rewrites)
    check("retired MCQ (uw-174346) may only be delivered as open",
          a2["uw-174346"] == {"open"})
    check("retired MCQ (uw-174388) may only be delivered as open",
          a4["uw-174388"] == {"open"})
    check("ambiguous open (uw-174382) may only be delivered as mcq",
          a4[AMBIGUOUS_OPEN] == {"mcq"})
    normal = [f for bid, f in a2.items() if bid not in RETIRED_MCQ]
    check("every other chapter-2 item keeps both forms",
          all(f == {"open", "mcq"} for f in normal))


def test_forced_across_seeds():
    """The pre-fix behaviour was correct only by luck of the seeded quota."""
    rewrites = NS["load_mcq_rewrites"](EVAL)
    ok = True
    for seed in (1, 7, 99, 2026, 31337):
        for ch, bid, want in [(2, "uw-174346", "open"), (4, "uw-174388", "open"),
                              (4, AMBIGUOUS_OPEN, "mcq")]:
            qa = NS["load_chapter_qa"](EVAL, ch)
            types = NS["choose_question_types"](qa, 0.75, seed,
                                                allowed=NS["allowed_forms"](qa, rewrites))
            ok &= types.get(bid) == want
    check("retired forms never selected, across 5 seeds", ok)


def test_unconstrained_default_unchanged():
    """Omitting `allowed` must preserve the original behaviour."""
    qa = NS["load_chapter_qa"](EVAL, 1)
    before = NS["choose_question_types"](qa, 0.75, 2026)
    n_open = sum(1 for v in before.values() if v == "open")
    check("no-allowed call still assigns every item", len(before) == len(qa))
    check("no-allowed call still hits the ~25% open quota",
          n_open == max(1, min(round(len(qa) * 0.25), len(qa) - 1)))


def test_build_plan_pool_guard():
    # Gate 1 now builds tier 1. The Luke helper/exclusion tests above remain as
    # regression coverage for historical data, but the executable pool is the
    # translated tier-1/window-map intersection.
    from pilot_import import build_plan
    qa_rows, window_rows, passage_rows, summary, missing = build_plan(EVAL, 0.75, 2026)
    mcq = [r for r in qa_rows if r.question_type == "mcq"]
    check("build_plan produces 78 QA rows and 78 one-to-one windows",
          len(qa_rows) == len(window_rows) == 78)
    check("MCQ fraction remains ~75%", abs(len(mcq) / len(qa_rows) - 0.75) < 0.02)
    identities = {(r["source_passage_id"], tuple(r["window_ordinals"])) for r in window_rows}
    check("no two imported questions share an exact window", len(identities) == 78)
    check("six available variants x ten passages are staged", len(passage_rows) == 60)
    check("the ten missing WBW variants are reported and block a real write",
          len(missing) == 10 and all(row[1] == "wbw" for row in missing))
    check("summary records the 12 removed window collisions",
          "removed 12 extra question" in "\n".join(summary))


def test_prune_identifies_stale_form():
    """prune_stale_qa must target a row whose FORM is wrong while its text matches, and
    must refuse when responses would CASCADE."""
    from sqlalchemy import create_engine, event, select, func
    from sqlalchemy.orm import Session
    from eten_shared.models import (
        Assignment, Base, Participant, ParticipantResponse, QAItem,
    )
    src = (REPO_ROOT / "scripts" / "pilot_import.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = [n for n in tree.body
          if isinstance(n, ast.FunctionDef) and n.name == "prune_stale_qa"]
    ns = {}
    exec(compile(ast.Module(body=fn, type_ignores=[]), "<p>", "exec"), ns)
    prune = ns["prune_stale_qa"]

    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine)
    # stale MCQ row: same (passage_id, question_text) as the wanted OPEN row
    db.add(QAItem(id="stale", passage_id="luke2", question_text="Q-shared",
                  question_type="mcq", expected_answer="a",
                  mcq_choices=["a", "b", "c", "d"], mcq_correct_choice="A"))
    # correct row, already in the right form
    db.add(QAItem(id="good", passage_id="luke1", question_text="Q-good",
                  question_type="mcq", expected_answer="a",
                  mcq_choices=["a", "b", "c", "d"], mcq_correct_choice="A"))
    # unrelated row outside the pilot pool
    db.add(QAItem(id="other", passage_id="luke9", question_text="Q-other",
                  question_type="open", expected_answer="a"))
    db.commit()

    wanted = [FakeQAItem(passage_id="luke2", question_text="Q-shared", question_type="open"),
              FakeQAItem(passage_id="luke1", question_text="Q-good", question_type="mcq")]
    deleted, blocked = prune(db, wanted)
    db.commit()
    left = set(db.scalars(select(QAItem.id)).all())
    check("stale wrong-form row deleted", "stale" not in left and len(deleted) == 1)
    check("correct-form row kept", "good" in left)
    check("row outside the pilot pool untouched", "other" in left)

    # now the same situation but WITH a response -> must be reported, not deleted
    db.add(Participant(id="p1", display_name="p1", consented=True, target_language="zh"))
    db.add(QAItem(id="stale2", passage_id="luke3", question_text="Q-resp",
                  question_type="mcq", expected_answer="a",
                  mcq_choices=["a", "b", "c", "d"], mcq_correct_choice="A"))
    db.flush()
    db.add(Assignment(id="a1", participant_id="p1", qa_item_id="stale2", status="completed"))
    db.flush()
    db.add(ParticipantResponse(participant_id="p1", qa_item_id="stale2", assignment_id="a1",
                               response_type="text", response_text="x"))
    db.commit()
    deleted2, blocked2 = prune(db, [FakeQAItem(passage_id="luke3", question_text="Q-resp",
                                               question_type="open")])
    db.commit()
    check("row with collected responses is BLOCKED, not deleted",
          not deleted2 and len(blocked2) == 1
          and db.get(QAItem, "stale2") is not None)
    check("blocked row reports its assignment/response counts",
          blocked2[0][3] == 1 and blocked2[0][4] == 1)


def main():
    for label, fn in [("allowed_forms", test_allowed_forms),
                      ("forced selection across seeds", test_forced_across_seeds),
                      ("unconstrained default unchanged", test_unconstrained_default_unchanged),
                      ("tier-1 build_plan + window guard", test_build_plan_pool_guard),
                      ("prune_stale_qa", test_prune_identifies_stale_form)]:
        print(f"{label}:")
        fn()
    print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
