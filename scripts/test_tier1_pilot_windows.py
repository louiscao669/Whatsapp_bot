#!/usr/bin/env python3
"""Regression checks for the tier-1 Gate-1 pool and runtime delivery."""

import os
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("REQUIRE_QUESTION_AUDIO", "false")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eten_shared.domain.assignments import (
    experiment_passage_assignment_kwargs,
    resolve_experiment_passage,
)
from eten_shared.models import (
    Base,
    ExperimentPassage,
    ExperimentPassageVerse,
    ExperimentPlanCell,
    ExperimentWindow,
    Participant,
)
from eten_shared.question_discovery import select_next_experiment_cell_item
from pilot_import import (
    build_tier1_pool,
    load_tier1_metadata,
    load_tier1_passage,
    parse_tier1_verses,
    tier1_collision_rank,
)
from mark_tier1_window_selection import build_annotations

EVAL_ROOT = REPO_ROOT / "evaluation"
fails = []


def check(name, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
    if not condition:
        fails.append(name)


def main():
    qa_rows, window_rows, report = build_tier1_pool(EVAL_ROOT, 0.75, 2026)
    check("90 translated questions intersect the curated map", report["translated"] == 90)
    ranking = report["question_ranking"]
    check("global ranking contains every translated question exactly once",
          len(ranking) == 90
          and len({row["base_id"] for row in ranking}) == 90
          and [row["rank"] for row in ranking] == list(range(1, 91)))
    check("global ranking is ordered by the same p/s_i-primary key",
          all(
              tier1_collision_rank(left) >= tier1_collision_rank(right)
              for left, right in zip(ranking, ranking[1:])
          ))
    check("12 colliding questions are removed", len(report["collisions"]) == 12)
    check("pool has 78 unique windows and 78 QA items",
          report["unique"] == len(window_rows) == len(qa_rows) == 78)
    check("groups are balanced 10/10/10/10/10/10/9/9",
          [report["group_sizes"][i] for i in range(1, 9)] == [10] * 6 + [9, 9])
    identities = [
        (row["source_passage_id"], tuple(row["window_ordinals"]))
        for row in window_rows
    ]
    check("one question per exact source window", len(identities) == len(set(identities)))
    by_group = defaultdict(set)
    for row in window_rows:
        by_group[row["group_index"]].add(row["source_passage_id"])
    check("balanced groups may cross passage boundaries",
          any(len(passages) > 1 for passages in by_group.values()))
    decisions = report["collision_decisions"]
    ranked_decisions = [
        decision for decision in decisions
        if decision["selection_reason"] != "exact_duplicate_first_copy"
    ]
    check("every collision choice follows p/s_i primary + feature secondary rank",
          all(
              tier1_collision_rank(decision["chosen"])
              > tier1_collision_rank(rejected)
              for decision in ranked_decisions
              for rejected in decision["rejected"]
          ))
    check("p/s_i primary gate can override the clean-floor secondary feature",
          any(
              decision["chosen"]["base_id"] == "uw-t1_judg9:w5fv"
              and decision["chosen"]["passes_p_gate"]
              and not rejected["passes_p_gate"]
              for decision in decisions
              for rejected in decision["rejected"]
              if rejected["base_id"] == "uw-t1_judg9:s8bw"
          ))
    check("two byte-identical QA collisions keep their first copy deterministically",
          sum(d["selection_reason"] == "exact_duplicate_first_copy" for d in decisions) == 2)

    by_content_id, by_window_key = build_annotations(EVAL_ROOT)
    qa_annotations = {}
    for path in (EVAL_ROOT / "datasets" / "qa" / "tier1_QAs_easy").glob(
        "*_all_formats.json"
    ):
        for record in json.loads(path.read_text(encoding="utf-8")):
            if "pilot_window_selection" in record:
                qa_annotations[record["content_id"]] = record["pilot_window_selection"]
    window_document = json.loads(
        (REPO_ROOT / "QA_algorithm" / "inputs" / "tier1_qa_verse_windows.json")
        .read_text(encoding="utf-8")
    )
    window_annotations = {
        record["key"]: record["pilot_window_selection"]
        for record in window_document["windows"]
        if "pilot_window_selection" in record
    }
    check("all collision candidates carry canonical QA selection metadata",
          qa_annotations == by_content_id)
    check("all collision candidates carry curated-window selection metadata",
          window_annotations == by_window_key)
    check("metadata marks exactly 12 questions removed/not chosen",
          sum(a["status"] == "not_chosen" and a["removed_from_human_pilot"]
              for a in qa_annotations.values()) == 12)

    # Runtime proof: a plan cell has no single passage FK, yet the chosen QA
    # resolves the right source variant and receives its curated labeled window.
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Participant(id="p1", consented=True, target_language="zh"))
        for qa in qa_rows:
            db.add(qa)
        db.flush()
        for row in window_rows:
            db.add(ExperimentWindow(**row))

        first = window_rows[0]
        metadata = next(m for m in load_tier1_metadata(EVAL_ROOT)
                        if m["id"] == first["source_passage_id"])
        text = load_tier1_passage(EVAL_ROOT, first["source_passage_id"], "omission/0%")
        passage = ExperimentPassage(
            source_passage_id=first["source_passage_id"],
            chapter=1,
            condition="clean",
            language="zh",
            passage_reference=metadata["reference"],
            passage_text=text,
        )
        db.add(passage)
        db.flush()
        for position, (number, verse_text) in enumerate(
            parse_tier1_verses(text, metadata), start=1
        ):
            db.add(ExperimentPassageVerse(
                experiment_passage_id=passage.id,
                verse_number=number,
                position=position,
                text=verse_text,
            ))
        cell = ExperimentPlanCell(
            id="cell1",
            participant_id="p1",
            chapter=first["group_index"],
            condition="clean",
            experiment_passage_id=None,
            sequence_index=0,
            status="pending",
        )
        db.add(cell)
        db.commit()

        item, selected_cell = select_next_experiment_cell_item(db, db.get(Participant, "p1"))
        check("selector scopes by window group, not Luke chapter",
              item is not None and selected_cell.id == "cell1")
        resolved = resolve_experiment_passage(db, selected_cell, item, "zh")
        check("multi-passage cell resolves variant from QA passage id", resolved.id == passage.id)
        kwargs = experiment_passage_assignment_kwargs(db, resolved, item)
        expected = db.get(ExperimentWindow, next(
            w.id for w in db.query(ExperimentWindow).all() if w.qa_item_id == item.id
        ))
        recoverable = [n for n in expected.verse_numbers
                       if n in {v.verse_number for v in passage.verses}]
        check("delivery uses the curated chapter-qualified window labels",
              kwargs["passage_verse_numbers"] == recoverable
              and bool(kwargs["passage_text"].strip()))

    print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
