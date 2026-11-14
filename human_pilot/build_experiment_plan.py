#!/usr/bin/env python3
"""Write the per-participant Latin-square plan for the human pilot (prereq #4).

Populates ``experiment_plan_cells``: one row per (participant, window group) fixing the
condition that participant sees for that group. A group contains 9-10 tier-1 windows and
may span source passages, so delivery resolves its variant per QA rather than storing one
misleading passage FK on the group. The designed selector
(``question_discovery.experiment_selection``) then serves questions strictly from this
plan when ``ENABLE_EXPERIMENT_ASSIGNMENT`` is set.

Design (HUMAN_PILOT_DESIGN_2026-07-27 §4/§5; DESIGNED_ASSIGNMENT_EXTENSION_2026-07-20 §4):
  * 8 condition SLOTS = two clean anchors + omission{15,30} + mistranslation{15,30} +
    grammar30 + wbw. Both anchor slots resolve to the single "clean" passage (they are
    pooled anchors: one supplies theta-hat, one supplies the re-zeroing baseline) and the
    clean cell is also the 0% dose of BOTH adequacy ladders.
    [CHANGED 2026-07-27b] was omission{10,20,30} + mistranslation20.
  * condition = SLOTS[(group - 1 + block_index) mod 8]  -> a balanced Latin square:
    across each 8-participant block every window group is paired with every slot once.
  * group ORDER is shuffled independently per participant (seeded by participant_id, so
    it is stable across re-runs / resumption) -> breaks order x condition confounding.

For Sol scratch, rotations continue from the saved regular-participant plans, including
when enrolling readers in separate batches. The next four after the first eight alternate
rotations so that at twelve readers each group has three clean observations. Sixteen
readers complete two full squares.

Idempotent: a participant that already has plan cells is skipped.

Usage (from repo root):
  # dry run -- prints the plan + balance table, no DB writes
  python human_pilot/build_experiment_plan.py --all-consented --dry-run

  # specific participants, in the order given (position => block index)
  python human_pilot/build_experiment_plan.py --participant-ids id0,id1,id2,...

  # real write needs DATABASE_URL (or .env on the host)
  python human_pilot/build_experiment_plan.py --all-consented
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "human_pilot"))
from _bootstrap import use_message_bot, use_platform  # noqa: E402

use_message_bot()
use_platform()  # backend.shared.config (loads .env) lives in platform/

from sqlalchemy import select  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.models import (  # noqa: E402
    ExperimentPlanCell,
    Participant,
)

# Plan rules (slots, groups, per-participant cells) live in eten_shared.experiment_plan
# so the admin "Create test participant" action writes the identical plan.
from eten_shared.experiment_plan import (  # noqa: E402
    GROUPS,
    LANGUAGE,
    QA_SETS,
    QA_SUBSETS,
    SOL_SCRATCH_SET,
    SLOTS,
    build_cells,
    ExperimentPlanError,
    is_study_qa_set,
    is_test_participant,
    qa_set_groups,
    write_participant_plan,
    scratch_rotation_counts,
    write_next_scratch_plan,
)

CHAPTERS = GROUPS  # compatibility for older tests/imports


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
    # Test participants (admin "Create test participant") never count toward block
    # positions: including them would shift every later real participant's slot rotation.
    return [p for p in rows if not is_test_participant(p)]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--participant-ids", help="comma-separated participant ids, in block order")
    grp.add_argument("--all-consented", action="store_true",
                     help="plan every consented participant without an existing plan")
    ap.add_argument("--language", default=LANGUAGE)
    study_sets = sorted(key for key in (*QA_SETS, *QA_SUBSETS) if is_study_qa_set(key))
    ap.add_argument("--qa-set", choices=study_sets, default=SOL_SCRATCH_SET,
                    help="question set to serve these participants (default: %(default)s; "
                         "hard66 needs human_pilot/pilot_import_hard66.py first)")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true", help="build + print, no DB writes")
    args = ap.parse_args()

    # DB session (skip only if we can build the plan without it -> we always need
    # participants + passage FKs, so a session is required even for --dry-run).
    from backend.shared.config import load_configurations  # loads .env  # noqa: E402
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

    with factory() as db:
        if args.qa_set == SOL_SCRATCH_SET:
            rotations = scratch_rotation_counts(db, for_update=not args.dry_run)
        participants = resolve_participants(db, args)
        if not participants:
            print("No participants to plan.")
            return
        if len(participants) % 8 != 0 and args.qa_set != SOL_SCRATCH_SET:
            print(f"  [warn] {len(participants)} participants is not a multiple of 8 -- "
                  f"the last block is partial (Latin square unbalanced; design tolerates >=12).")
        for position, participant in enumerate(participants):
            existing = db.scalar(
                select(ExperimentPlanCell.id).where(
                    ExperimentPlanCell.participant_id == participant.id
                )
            )
            if existing:
                skipped += 1
                continue
            try:
                if args.qa_set == SOL_SCRATCH_SET:
                    if is_test_participant(participant):
                        skipped += 1
                        continue
                    cells = write_next_scratch_plan(db, participant, rotations, args.language,
                                                    dry_run=args.dry_run)
                else:
                    cells = write_participant_plan(db, participant, position % len(SLOTS),
                                                   args.language, qa_set=args.qa_set, dry_run=args.dry_run)
            except ExperimentPlanError as exc:
                sys.exit(f"Cannot create the participant plan: {exc}")
            per_participant_slots[participant.id] = Counter(c[1] for c in cells)
            for chapter, condition, _ in cells:
                balance[chapter][condition] += 1
                written += 1
        if not args.dry_run:
            db.commit()

    # ---- report ----
    print(f"Planned {len(per_participant_slots)} participants "
          f"({written} cells{' [DRY-RUN]' if args.dry_run else ''}); "
          f"{skipped} skipped.")
    print("\nLatin-square balance (chapter -> condition counts across planned participants):")
    conds = SLOTS[:1] + SLOTS[2:]  # unique condition keys, clean once
    print("  ch  " + "  ".join(f"{c[:9]:>9}" for c in conds))
    for ch in qa_set_groups(args.qa_set):
        row = "  ".join(f"{balance[ch][c]:>9}" for c in conds)
        print(f"  {ch:<3} {row}")
    # each participant should see all 8 slots (2 clean + 6 others)
    bad = {pid: dict(sl) for pid, sl in per_participant_slots.items()
           if sl.get("clean") != 2 or any(sl.get(c, 0) != 1 for c in conds if c != "clean")}
    print(f"\nPer-participant slot check (want clean=2, each other=1): "
          f"{'ALL OK' if not bad else f'{len(bad)} PARTICIPANTS OFF'}")
    for pid, sl in list(bad.items())[:3]:
        print(f"  off: {pid} -> {sl}")


if __name__ == "__main__":
    main()
