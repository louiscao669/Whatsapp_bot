#!/usr/bin/env python3
"""Clear designed-experiment state so a re-slated pilot can be re-imported cleanly.

WHY THIS EXISTS (2026-07-27b re-slate). ``pilot_import.py`` upserts passages keyed by
(chapter, condition, language): re-running it after a slate change INSERTs the new conditions
and REFRESHes the surviving ones, but leaves the retired conditions' passages behind. Those
stale rows are not inert -- a plan rebuilt from a stale slate would happily point at them.

Worse, the two relevant foreign keys are ``ondelete="SET NULL"``, so deleting rows in the wrong
order corrupts quietly instead of erroring:

  * delete an ExperimentPassage  -> any ExperimentPlanCell pointing at it SURVIVES with a NULL
    ``experiment_passage_id``; the selector then serves that cell with no variant passage.
  * delete an ExperimentPlanCell -> any Assignment stamped with it SURVIVES with a NULL
    ``experiment_cell_id``, losing its condition label, so ``export_pilot_responses.py``
    silently drops the response from the export.

So this script deletes in dependency order and REFUSES by default to run if experiment
assignments already exist (i.e. the pilot has started and responses would be orphaned).

ExperimentPassageVerse rows cascade with their passage and need no explicit handling.

Order of operations for a re-slate:

  1. python scripts/reset_experiment_plan.py --dry-run          # inspect, writes nothing
  2. python scripts/reset_experiment_plan.py                    # plan cells + retired passages
  3. python scripts/pilot_import.py --eval-root <...>/evaluation
  4. python scripts/build_experiment_plan.py --all-consented

Usage:
  --dry-run              report only (ALWAYS run this first)
  --keep-plan-cells      delete retired passages only, leave the plan alone
  --all-passages         delete EVERY experiment passage, not just retired conditions
                         (pilot_import will recreate them; use for a full rebuild)
  --participant-ids      limit plan-cell deletion to these participants
  --force                proceed even though experiment assignments exist (DESTRUCTIVE:
                         those assignments lose their condition label and drop out of the
                         response export). Requires typing the confirmation phrase.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_message_bot  # noqa: E402

use_message_bot()

from sqlalchemy import delete, func, select  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.models import (  # noqa: E402
    Assignment,
    ExperimentPassage,
    ExperimentPassageVerse,
    ExperimentPlanCell,
)
from build_experiment_plan import SLOTS  # noqa: E402

CURRENT_CONDITIONS = set(SLOTS)
CONFIRM_PHRASE = "delete experiment data"


def summarize(db):
    """Report current state without touching anything."""
    passages = db.execute(
        select(ExperimentPassage.condition, func.count(ExperimentPassage.id))
        .group_by(ExperimentPassage.condition)
        .order_by(ExperimentPassage.condition)
    ).all()
    cells = db.execute(
        select(ExperimentPlanCell.condition, func.count(ExperimentPlanCell.id))
        .group_by(ExperimentPlanCell.condition)
        .order_by(ExperimentPlanCell.condition)
    ).all()
    n_assign = db.scalar(
        select(func.count(Assignment.id)).where(Assignment.experiment_cell_id.is_not(None))
    ) or 0
    n_participants = db.scalar(
        select(func.count(func.distinct(ExperimentPlanCell.participant_id)))
    ) or 0
    return passages, cells, n_assign, n_participants


def perform_reset(db, *, doomed_conditions, keep_plan_cells=False, participant_ids=None):
    """Delete in dependency order: plan cells first (they reference passages), then the
    passages themselves. Returns (deleted_cells, deleted_passages). Caller commits."""
    deleted_cells = 0
    if not keep_plan_cells:
        stmt = delete(ExperimentPlanCell)
        if participant_ids:
            stmt = stmt.where(ExperimentPlanCell.participant_id.in_(participant_ids))
        deleted_cells = db.execute(stmt).rowcount or 0
        db.flush()

    deleted_passages = 0
    if doomed_conditions:
        ids = db.scalars(
            select(ExperimentPassage.id)
            .where(ExperimentPassage.condition.in_(doomed_conditions))
        ).all()
        if ids:
            # Verses cascade via FK, but delete explicitly so the count is reported and the
            # behaviour does not depend on the backend honouring ON DELETE CASCADE.
            db.execute(delete(ExperimentPassageVerse).where(
                ExperimentPassageVerse.experiment_passage_id.in_(ids)))
            deleted_passages = db.execute(
                delete(ExperimentPassage).where(ExperimentPassage.id.in_(ids))
            ).rowcount or 0
    return deleted_cells, deleted_passages


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    ap.add_argument("--keep-plan-cells", action="store_true",
                    help="do not delete experiment_plan_cells")
    ap.add_argument("--all-passages", action="store_true",
                    help="delete every experiment passage, not just retired conditions")
    ap.add_argument("--participant-ids",
                    help="comma-separated participant ids; limits plan-cell deletion")
    ap.add_argument("--force", action="store_true",
                    help="proceed even if experiment assignments exist (destructive)")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    args = ap.parse_args()

    from app.config import load_configurations  # loads .env  # noqa: E402
    from flask import Flask

    app = Flask(__name__)
    load_configurations(app)
    database_url = args.database_url or app.config.get("DATABASE_URL")
    if not database_url:
        sys.exit("No DATABASE_URL (set it in the environment or .env).")
    factory = get_session_factory(database_url)

    participant_ids = (
        [p.strip() for p in args.participant_ids.split(",") if p.strip()]
        if args.participant_ids else None
    )

    with factory() as db:
        passages, cells, n_assign, n_participants = summarize(db)

        print("current experiment_passages by condition:")
        for cond, n in passages:
            tag = "" if cond in CURRENT_CONDITIONS else "   <-- RETIRED"
            print(f"   {cond:22} {n:>4}{tag}")
        print(f"\ncurrent experiment_plan_cells: {sum(n for _, n in cells)} "
              f"across {n_participants} participant(s)")
        for cond, n in cells:
            tag = "" if cond in CURRENT_CONDITIONS else "   <-- RETIRED"
            print(f"   {cond:22} {n:>4}{tag}")
        print(f"\nassignments stamped with an experiment cell: {n_assign}")
        print(f"current slate: {sorted(CURRENT_CONDITIONS)}\n")

        retired = [c for c, _ in passages if c not in CURRENT_CONDITIONS]
        if args.all_passages:
            doomed = [c for c, _ in passages]
            what = "ALL passages"
        else:
            doomed = retired
            what = "retired-condition passages"

        if n_assign and not args.force:
            sys.exit(
                f"REFUSING: {n_assign} assignment(s) are stamped with an experiment cell, so "
                "the pilot has already collected data. Deleting plan cells would NULL those "
                "stamps (ondelete=SET NULL) and the responses would silently vanish from "
                "export_pilot_responses.py.\n"
                "  - to reset anyway (destroys the link to collected responses): --force\n"
                "  - to remove only stale passages and keep the plan:            --keep-plan-cells"
            )

        if args.dry_run:
            print(f"[dry-run] would delete {what}: {doomed or 'none'}")
            if not args.keep_plan_cells:
                scope = f"{len(participant_ids)} participant(s)" if participant_ids else "ALL"
                print(f"[dry-run] would delete experiment_plan_cells for {scope}")
            print("[dry-run] no changes written")
            return 0

        if n_assign and args.force:
            typed = input(f'Type "{CONFIRM_PHRASE}" to confirm destroying {n_assign} '
                          f"assignment stamp(s): ")
            if typed.strip() != CONFIRM_PHRASE:
                sys.exit("aborted")

        deleted_cells, deleted_passages = perform_reset(
            db, doomed_conditions=doomed, keep_plan_cells=args.keep_plan_cells,
            participant_ids=participant_ids)
        db.commit()

        print(f"deleted {deleted_cells} plan cell(s) and {deleted_passages} passage(s) "
              f"({what}: {doomed or 'none'})")
        # Print a runnable command, not a placeholder: --eval-root is a real path and pasting
        # a "<repo>" template produces a confusing "no clean-variant dir" failure downstream.
        print("\nnext:")
        print(f"  python scripts/pilot_import.py --eval-root {REPO_ROOT / 'evaluation'}")
        print("  python scripts/build_experiment_plan.py --all-consented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
