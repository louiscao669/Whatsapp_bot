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
from eten_shared.models import (  # noqa: E402
    Assignment, ExperimentPlanCell, ExperimentWindow, Participant, QAItem,
)
from eten_shared.recordings import (  # noqa: E402
    has_question_recording_for_participant, question_audio_required,
)
from eten_shared.question_forms import filter_candidates_by_form, participant_question_forms  # noqa: E402
from eten_shared.wh_type import classify_wh_type, participant_wh_types  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("participant_id", nargs="?")
    ap.add_argument("--latest-test", action="store_true")
    ap.add_argument("--database-url", default=None)
    args = ap.parse_args()

    from sqlalchemy import func

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
        # REQUIRE_QUESTION_AUDIO is read from THIS machine's environment (default True when
        # unset). The VM has its own .env, and that is the value serving actually used.
        print(f"  REQUIRE_QUESTION_AUDIO here: {question_audio_required()}   "
              f"(audio_ok = servable AND has a question recording in the participant's language)")

        cells = db.scalars(select(ExperimentPlanCell)
                           .where(ExperimentPlanCell.participant_id == participant.id)
                           .order_by(ExperimentPlanCell.sequence_index)).all()
        print(f"\n{'seq':>3} {'group':>5} {'condition':<18} {'all':>4} {'mcq':>4} {'open':>4} "
              f"{'servable':>8} {'audio_ok':>8} {'assigned':>8}  status")
        tot = [0, 0, 0, 0, 0, 0]
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
            audio_ok = sum(1 for i in keep
                           if has_question_recording_for_participant(db, i.id, participant))
            assigned = db.scalar(select(func.count(Assignment.id))
                                 .where(Assignment.experiment_cell_id == c.id)) or 0
            row = [len(items), mcq, len(items) - mcq, len(keep), audio_ok, assigned]
            tot = [a + b for a, b in zip(tot, row)]
            print(f"{c.sequence_index + 1:>3} {c.chapter:>5} {c.condition:<18} "
                  f"{row[0]:>4} {row[1]:>4} {row[2]:>4} {row[3]:>8} {row[4]:>8} {row[5]:>8}  {c.status}")
        print(f"{'':>3} {'':>5} {'TOTAL':<18} {tot[0]:>4} {tot[1]:>4} {tot[2]:>4} {tot[3]:>8} {tot[4]:>8} {tot[5]:>8}")
        rows = db.execute(select(Assignment.assigned_at, Assignment.experiment_cell_id)
                          .where(Assignment.participant_id == participant.id)
                          .order_by(Assignment.assigned_at)).all()
        span = (f"  (first {rows[0][0]:%Y-%m-%d %H:%M}, last {rows[-1][0]:%Y-%m-%d %H:%M})"
                if rows else "")
        print(f"\nall assignments: {len(rows)}{span}")
        no_cell = sum(1 for r in rows if r[1] is None)
        if no_cell:
            print(f"  {no_cell} assignment(s) have no plan cell (served outside the plan)")


if __name__ == "__main__":
    main()
