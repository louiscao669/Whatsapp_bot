#!/usr/bin/env python3
"""Add option E ("根据这段文字无法判断", cannot tell from this passage) to an imported set's MCQs.

hard66 carries E on every MCQ (``pilot_import_hard66.py --cannot-tell``); a gold72 import
taken from a 4-option source does not. ``pilot_import.py`` skips questions that already
exist (matched on passage + question text), so re-running the import will not add E to
rows already in the database. This script patches those rows in place instead.

What it changes: for every MCQ ``QAItem`` linked to the set's windows whose
``mcq_choices`` has exactly four options, it appends E. Options A-D, the correct letter
and the expected answer are untouched, so responses already recorded keep their meaning.
Items that already have five options are skipped, so re-running is a no-op.

Usage (on the VM, from the repo root, with DATABASE_URL in .env or the environment):
  python human_pilot/add_cannot_tell_option.py --dry-run           # count only
  python human_pilot/add_cannot_tell_option.py                     # gold72 (default)
  python human_pilot/add_cannot_tell_option.py --qa-set hard66
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "human_pilot"))
from _bootstrap import use_platform  # noqa: E402

use_platform()

from sqlalchemy import select  # noqa: E402

from eten_shared.experiment_plan import DEFAULT_QA_SET, QA_SETS, qa_set_groups  # noqa: E402
from eten_shared.models import ExperimentWindow, QAItem  # noqa: E402

CANNOT_TELL = "根据这段文字无法判断"  # identical to pilot_import_hard66.CANNOT_TELL


def add_cannot_tell(db, qa_set):
    """Append E to the set's 4-option MCQs. Returns (patched, already_five, other)."""
    items = db.scalars(
        select(QAItem)
        .join(ExperimentWindow, ExperimentWindow.qa_item_id == QAItem.id)
        .where(
            ExperimentWindow.group_index.in_(qa_set_groups(qa_set)),
            QAItem.question_type == "mcq",
        )
        .distinct()
    ).all()
    patched, already, other = [], 0, []
    for item in items:
        choices = list(item.mcq_choices or [])
        if len(choices) == 5:
            already += 1
        elif len(choices) == 4:
            item.mcq_choices = choices + [CANNOT_TELL]  # reassign so the JSON change is tracked
            patched.append(item)
        else:
            other.append(item)
    db.flush()
    return patched, already, other


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qa-set", default=DEFAULT_QA_SET, choices=sorted(QA_SETS))
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    args = ap.parse_args()

    from eten_shared.database import get_session_factory

    factory = get_session_factory(args.database_url)
    with factory() as db:
        patched, already, other = add_cannot_tell(db, args.qa_set)
        print(f"{args.qa_set}: {len(patched)} MCQs get E, {already} already have 5 options, "
              f"{len(other)} have an unexpected option count")
        for item in other:
            print(f"  ! {item.id} ({item.passage_id}): {len(item.mcq_choices or [])} options -- left alone")
        if args.dry_run:
            db.rollback()
            print("dry run: nothing written")
        else:
            db.commit()
            print("committed")


if __name__ == "__main__":
    main()
