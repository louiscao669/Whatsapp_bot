#!/usr/bin/env python3
"""Write the per-participant Latin-square plan for the human pilot (prereq #4).

Populates ``experiment_plan_cells``: one row per (participant, chapter) fixing the
condition that participant sees for that chapter, plus the FK to the variant passage
(``experiment_passages``, imported by ``scripts/pilot_import.py``). The designed selector
(``question_discovery.experiment_selection``) then serves questions strictly from this
plan when ``ENABLE_EXPERIMENT_ASSIGNMENT`` is set.

Design (HUMAN_PILOT_DESIGN_2026-07-12 §5; DESIGNED_ASSIGNMENT_EXTENSION_2026-07-20 §4):
  * 8 condition SLOTS = two clean anchors + omission{10,20,30} + mistranslation20 +
    grammar30 + wbw. Both anchor slots resolve to the single "clean" passage (they are
    pooled anchors: one supplies theta-hat, one supplies the re-zeroing baseline).
  * condition = SLOTS[(chapter - 1 + block_index) mod 8]  -> a balanced Latin square:
    across each 8-participant block every chapter is paired with every slot exactly once.
  * chapter ORDER is shuffled independently per participant (seeded by participant_id, so
    it is stable across re-runs / resumption) -> breaks order x condition confounding.

Block assignment: participants are taken in a fixed order (explicit --participant-ids, or
all consented participants without a plan) and given block_index = position mod 8. 16
participants -> two full balanced blocks. A non-multiple-of-8 count leaves the last block
partial (the design tolerates down to N=12); a warning is printed.

Idempotent: a participant that already has plan cells is skipped.

Usage (from repo root):
  # dry run -- prints the plan + balance table, no DB writes
  python scripts/build_experiment_plan.py --all-consented --dry-run

  # specific participants, in the order given (position => block index)
  python scripts/build_experiment_plan.py --participant-ids id0,id1,id2,...

  # real write needs DATABASE_URL (or .env on the host)
  python scripts/build_experiment_plan.py --all-consented
"""

import argparse
import random
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
    ExperimentPlanCell,
    Participant,
)

# 8 condition slots. Two "clean" anchors (pooled). The strings MUST match
# experiment_passages.condition written by scripts/pilot_import.py.
SLOTS = [
    "clean",            # A1 anchor
    "clean",            # A2 anchor (same passage; pooled)
    "omission10",
    "omission20",
    "omission30",
    "mistranslation20",
    "grammar30",
    "wbw",
]
CHAPTERS = list(range(1, 9))
LANGUAGE = "zh"


def build_cells(participant_id: str, block_index: int):
    """Return the list of (chapter, condition, sequence_index) for one participant."""
    chapter_order = CHAPTERS.copy()
    random.Random(str(participant_id)).shuffle(chapter_order)  # stable per participant
    cells = []
    for seq, chapter in enumerate(chapter_order):
        condition = SLOTS[(chapter - 1 + block_index) % len(SLOTS)]
        cells.append((chapter, condition, seq))
    return cells


def resolve_participants(db, args):
    if args.participant_ids:
        ids = [s.strip() for s in args.participant_ids.split(",") if s.strip()]
        parts = []
        for pid in ids:
            p = db.get(Participant, pid)
            if p is None:
                print(f"  [warn] participant {pid} not found -- skipped")
                continue
            parts.append(p)
        return parts
    # all consented participants without an existing plan, oldest first (stable block order)
    rows = db.scalars(
        select(Participant).where(Participant.consented.is_(True)).order_by(Participant.created_at)
    ).all()
    return list(rows)


def passage_index(db, language):
    idx = {}
    for p in db.scalars(select(ExperimentPassage).where(ExperimentPassage.language == language)).all():
        idx[(p.chapter, p.condition)] = p.id
    return idx


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--participant-ids", help="comma-separated participant ids, in block order")
    grp.add_argument("--all-consented", action="store_true",
                     help="plan every consented participant without an existing plan")
    ap.add_argument("--language", default=LANGUAGE)
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true", help="build + print, no DB writes")
    args = ap.parse_args()

    # DB session (skip only if we can build the plan without it -> we always need
    # participants + passage FKs, so a session is required even for --dry-run).
    from app.config import load_configurations  # loads .env  # noqa: E402
    from flask import Flask

    app = Flask(__name__)
    load_configurations(app)
    database_url = args.database_url or app.config.get("DATABASE_URL")
    if not database_url:
        sys.exit("No DATABASE_URL (set it in the environment or .env).")
    factory = get_session_factory(database_url)

    written = skipped = 0
    balance = defaultdict(Counter)          # chapter -> Counter(condition)
    per_participant_slots = {}
    missing_passage = set()

    with factory() as db:
        participants = resolve_participants(db, args)
        if not participants:
            print("No participants to plan.")
            return
        if len(participants) % 8 != 0:
            print(f"  [warn] {len(participants)} participants is not a multiple of 8 -- "
                  f"the last block is partial (Latin square unbalanced; design tolerates >=12).")
        pidx = passage_index(db, args.language)

        for position, participant in enumerate(participants):
            existing = db.scalar(
                select(ExperimentPlanCell.id).where(
                    ExperimentPlanCell.participant_id == participant.id
                )
            )
            if existing:
                skipped += 1
                continue
            block_index = position % len(SLOTS)
            cells = build_cells(participant.id, block_index)
            per_participant_slots[participant.id] = Counter(c[1] for c in cells)
            for chapter, condition, seq in cells:
                passage_id = pidx.get((chapter, condition))
                if passage_id is None:
                    missing_passage.add((chapter, condition))
                balance[chapter][condition] += 1
                if not args.dry_run:
                    db.add(ExperimentPlanCell(
                        participant_id=participant.id,
                        chapter=chapter,
                        condition=condition,
                        experiment_passage_id=passage_id,
                        sequence_index=seq,
                        status="pending",
                    ))
                written += 1
            if not args.dry_run:
                db.commit()

    # ---- report ----
    print(f"Planned {len(per_participant_slots)} participants "
          f"({written} cells{' [DRY-RUN]' if args.dry_run else ''}); "
          f"{skipped} already had a plan.")
    print("\nLatin-square balance (chapter -> condition counts across planned participants):")
    conds = SLOTS[:1] + SLOTS[2:]  # unique condition keys, clean once
    print("  ch  " + "  ".join(f"{c[:9]:>9}" for c in conds))
    for ch in CHAPTERS:
        row = "  ".join(f"{balance[ch][c]:>9}" for c in conds)
        print(f"  {ch:<3} {row}")
    # each participant should see all 8 slots (2 clean + 6 others)
    bad = {pid: dict(sl) for pid, sl in per_participant_slots.items()
           if sl.get("clean") != 2 or any(sl.get(c, 0) != 1 for c in conds if c != "clean")}
    print(f"\nPer-participant slot check (want clean=2, each other=1): "
          f"{'ALL OK' if not bad else f'{len(bad)} PARTICIPANTS OFF'}")
    for pid, sl in list(bad.items())[:3]:
        print(f"  off: {pid} -> {sl}")
    if missing_passage:
        print(f"\n  [warn] {len(missing_passage)} (chapter,condition) cells had NO experiment_passage "
              f"(FK left null -- run scripts/pilot_import.py first): "
              f"{sorted(missing_passage)[:6]}{' ...' if len(missing_passage) > 6 else ''}")


if __name__ == "__main__":
    main()
