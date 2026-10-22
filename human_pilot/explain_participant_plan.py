#!/usr/bin/env python3
"""Explain how many questions a participant's plan can serve, cell by cell.

For each plan cell: the window group, condition, how many questions the group holds
(active, not review-removed), how many are MCQ / open, and how many survive the
participant's own filters (question form, question type). The last column is what the
selector can actually serve, so the TOTAL row is the participant's question count.

Usage (on the VM, from the repo root):
  .venv/bin/python human_pilot/explain_participant_plan.py <participant_id>
  .venv/bin/python human_pilot/explain_participant_plan.py --latest-test   # newest test participant
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "human_pilot"))
from _bootstrap import use_platform  # noqa: E402

use_platform()

from sqlalchemy import select  # noqa: E402

from eten_shared.experiment_plan import (  # noqa: E402
    PARTICIPANT_QUALITY_DIMENSIONS_KEY,
    is_test_participant,
)
from eten_shared.models import ExperimentPlanCell, ExperimentWindow, Participant, QAItem  # noqa: E402
from eten_shared.question_forms import filter_candidates_by_form, participant_question_forms  # noqa: E402
from eten_shared.wh_type import classify_wh_type, participant_wh_types  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("participant_id", nargs="?")
    ap.add_argument("--latest-test", action="store_true")
    ap.add_argument("--database-url", default=None)
    args = ap.parse_args()

    from eten_shared.database import get_session_factory

    with get_session_factory(args.database_url)() as db:
        if args.latest_test:
            people = db.scalars(select(Participant).order_by(Participant.created_at.desc())).all()
            participant = next((p for p in people if is_test_participant(p)), None)
        else:
            participant = db.get(Participant, args.participant_id)
        if participant is None:
            sys.exit("participant not found")

        prefs = participant.dashboard_preferences or {}
        forms = participant_question_forms(participant)
        whs = participant_wh_types(participant)
        print(f"{participant.display_name} ({participant.id})")
        print(f"  forms: {sorted(forms) or 'all'}   question types: {sorted(whs) or 'all'}   "
              f"quality dimension: {prefs.get(PARTICIPANT_QUALITY_DIMENSIONS_KEY) or 'all'}")

        cells = db.scalars(select(ExperimentPlanCell)
                           .where(ExperimentPlanCell.participant_id == participant.id)
                           .order_by(ExperimentPlanCell.sequence_index)).all()
        print(f"\n{'seq':>3} {'group':>5} {'condition':<18} {'all':>4} {'mcq':>4} {'open':>4} "
              f"{'servable':>8}  status")
        tot = [0, 0, 0, 0]
        for c in cells:
            items = db.scalars(select(QAItem)
                               .join(ExperimentWindow, ExperimentWindow.qa_item_id == QAItem.id)
                               .where(ExperimentWindow.group_index == c.chapter,
                                      QAItem.active.is_(True),
                                      QAItem.review_removed_at.is_(None))).all()
            mcq = sum(i.question_type == "mcq" for i in items)
            keep = filter_candidates_by_form(items, forms)
            if whs:
                keep = [i for i in keep if classify_wh_type(i.question_text) in whs]
            row = [len(items), mcq, len(items) - mcq, len(keep)]
            tot = [a + b for a, b in zip(tot, row)]
            print(f"{c.sequence_index + 1:>3} {c.chapter:>5} {c.condition:<18} "
                  f"{row[0]:>4} {row[1]:>4} {row[2]:>4} {row[3]:>8}  {c.status}")
        print(f"{'':>3} {'':>5} {'TOTAL':<18} {tot[0]:>4} {tot[1]:>4} {tot[2]:>4} {tot[3]:>8}")


if __name__ == "__main__":
    main()
