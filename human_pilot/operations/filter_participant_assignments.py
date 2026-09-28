#!/usr/bin/env python3
"""Restrict one participant's queue to questions of a given interrogative type.

    python human_pilot/operations/filter_participant_assignments.py --participant-id ID
    python human_pilot/operations/filter_participant_assignments.py --participant-id ID --keep why --apply
    python human_pilot/operations/filter_participant_assignments.py --self-test

WHY THIS IS NOT A PLAN OPTION. build_experiment_plan selects at the level of QA SET
(gold72 / hard66) and window, never stem type, and QAItem has no wh_type column -- the
field added on 2026-09-26 lives in the dataset JSON and does not survive pilot_import.
Rather than migrate a live table for an exploratory arm, this classifies
qa_items.question_text at query time with the same cue table, and marks the assignments
that do not match as SKIPPED.

SKIPPED, not deleted, deliberately. Assignments form a chain through next_assignment_id;
deleting a node would strand it. get_chained_assignment returns None for any node that is
not ASSIGNED and get_incomplete_assignment then falls back to scanning the queue in order,
so a skipped node is simply passed over. Only ASSIGNED rows are touched -- anything
in_progress or completed is left exactly as it is, so no collected answer is disturbed.

The classifier is eten_shared.wh_type -- the same one the live assignment selector uses,
so a cue change cannot drift between what is served and what is counted.

A CAUTION ON THE DESIGN, not the code. gold72 holds 13 why items across ten passages
(21 pooling why+how). At preferred_batch_size 3 that is under five batches, scattered one
or two per passage. And the why/how sensitivity measured on 2026-09-26 was significant for
OMISSION only, and only for qwen3:1.7b -- for mistranslation the ordering reversed and WHO
items fell hardest. A why-only stream also removes the within-subject contrast, so it
cannot separate "why questions are more sensitive" from "this participant is weaker".
Prefer a stratified mix with the type recorded, unless the point is explicitly to pilot
the why items alone.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "eten-shared"))

# Imported inside run(), not here: the cue table and its self-test have to be runnable
# where sqlalchemy is not installed (the same reason audit_verdicts.py keeps its pure
# helpers separate). A module-level import would make --self-test require a database
# stack it never touches.

from eten_shared.wh_type import (  # noqa: E402
    UNKNOWN, WH_TYPES, classify_wh_type,
)


def run(participant_id, keep, apply_, database_url=None):
    from sqlalchemy import select
    from eten_shared.database import get_session_factory
    from eten_shared.models import Assignment, AssignmentStatus, Participant, QAItem

    try:
        factory = get_session_factory(database_url)
    except RuntimeError as exc:
        print(f"{exc}\n  set -a; source .env; set +a   (or pass --database-url)",
              file=sys.stderr)
        return 2
    with factory() as db:
        participant = db.get(Participant, participant_id)
        if participant is None:
            print(f"no participant {participant_id!r}", file=sys.stderr)
            return 2
        rows = list(db.execute(
            select(Assignment, QAItem)
            .join(QAItem, QAItem.id == Assignment.qa_item_id)
            .where(Assignment.participant_id == participant_id)
            .order_by(Assignment.assigned_at, Assignment.id)
        ))
        by_type, to_skip, protected = {}, [], 0
        for assignment, item in rows:
            t = classify_wh_type(item.question_text)
            by_type.setdefault(t, []).append(assignment.status)
            if assignment.status != AssignmentStatus.ASSIGNED.value:
                protected += 1
                continue
            if t not in keep:
                to_skip.append((assignment, t, item.question_text))

        print(f"participant {participant_id}  ({participant.display_name or 'unnamed'})")
        print(f"  {len(rows)} assignment(s); keeping: {', '.join(sorted(keep))}")
        for t in list(WH_TYPES) + [UNKNOWN]:
            st = by_type.get(t)
            if st:
                mark = "KEEP" if t in keep else "skip"
                print(f"    {t:7}{len(st):4d}  [{mark}]")
        print(f"  not ASSIGNED (left untouched): {protected}")
        print(f"  would mark skipped           : {len(to_skip)}")
        for _a, t, q in to_skip[:5]:
            print(f"      {t:6} {str(q)[:58]}")
        if len(to_skip) > 5:
            print(f"      … and {len(to_skip)-5} more")

        kept = sum(1 for a, i in rows
                   if a.status == AssignmentStatus.ASSIGNED.value
                   and classify_wh_type(i.question_text) in keep)
        print(f"  would remain answerable      : {kept}")
        if kept == 0:
            print("  REFUSING: that would leave the participant with nothing to answer.",
                  file=sys.stderr)
            return 2
        if not apply_:
            print("\ndry run: nothing written (pass --apply)")
            return 0
        for assignment, _t, _q in to_skip:
            assignment.status = AssignmentStatus.SKIPPED.value
        db.commit()
        print(f"\nmarked {len(to_skip)} assignment(s) skipped; {kept} remain")
        return 0


def self_test():
    cases = [("Why does God allow it?", "why"), ("为什么但人寻找地盘？", "why"),
             ("这件事什么时候发生？", "when"), ("米该偷了什么？", "what"),
             ("亚比米勒的父亲是谁？", "who"), ("百姓如何反应？", "how"),
             ("神人从哪里来？", "where"), ("Whose body is it?", "who"),
             ("", UNKNOWN), (None, UNKNOWN)]
    bad = [(s, w, classify_wh_type(s)) for s, w in cases if classify_wh_type(s) != w]
    for s, w, g in bad:
        print(f"  [FAIL] {s!r}: wanted {w}, got {g}")
    print(f"{len(cases)-len(bad)}/{len(cases)} self-tests passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--participant-id")
    ap.add_argument("--keep", action="append", choices=sorted(WH_TYPES),
                    help="stem types to keep (repeatable; default: why)")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.participant_id:
        ap.error("--participant-id is required")
    return run(a.participant_id, set(a.keep or ["why"]), a.apply, a.database_url)


if __name__ == "__main__":
    raise SystemExit(main())
