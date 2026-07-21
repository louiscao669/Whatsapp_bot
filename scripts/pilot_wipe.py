#!/usr/bin/env python3
"""Remove ALL QA items and experiment passages (clean slate before re-import).

Companion to pilot_import.py. Destructive:

  * Deletes every QAItem. Via ORM cascade this also removes the assignments,
    participant responses, question/keyword recordings, and per-language
    keywords attached to them.
  * Deletes every ExperimentPassage. Plan cells that reference a passage have
    their experiment_passage_id set to NULL (ON DELETE SET NULL); the plan cells
    themselves are NOT deleted.
  * With --include-passage-translations, also deletes PassageTranslation rows
    (and their verses).

Safe by default: prints what WOULD be deleted and exits. Pass --confirm to
actually delete.

Usage:
  python scripts/pilot_wipe.py                    # dry run (counts only)
  python scripts/pilot_wipe.py --confirm          # delete QA + experiment passages
  python scripts/pilot_wipe.py --confirm --include-passage-translations
"""

import argparse
import sys

from _bootstrap import use_message_bot

use_message_bot()

from eten_shared.models import (  # noqa: E402
    Assignment,
    ExperimentPassage,
    ParticipantResponse,
    PassageTranslation,
    PassageVerse,
    QAItem,
)


def _counts(db):
    from sqlalchemy import func, select

    def n(model):
        return db.scalar(select(func.count()).select_from(model)) or 0

    return {
        "QAItem": n(QAItem),
        "  -> Assignment (cascade)": n(Assignment),
        "  -> ParticipantResponse (cascade)": n(ParticipantResponse),
        "ExperimentPassage": n(ExperimentPassage),
        "PassageTranslation": n(PassageTranslation),
        "PassageVerse": n(PassageVerse),
    }


def wipe(db, include_passage_translations):
    from sqlalchemy import select

    # QAItems: ORM delete so cascade removes assignments/responses/recordings/keywords.
    qa_items = db.scalars(select(QAItem)).all()
    for item in qa_items:
        db.delete(item)

    passages = db.scalars(select(ExperimentPassage)).all()
    for p in passages:
        db.delete(p)

    if include_passage_translations:
        for t in db.scalars(select(PassageTranslation)).all():
            db.delete(t)  # cascade removes its verses

    db.flush()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--confirm", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--include-passage-translations", action="store_true",
                    help="also delete PassageTranslation rows and their verses")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    args = ap.parse_args()

    from eten_shared.database import get_session_factory

    factory = get_session_factory(args.database_url)
    with factory() as db:
        before = _counts(db)
        print("Current rows:")
        for k, v in before.items():
            print(f"  {k:38s} {v}")

        if not args.confirm:
            print("\n[dry-run] nothing deleted. Re-run with --confirm to delete "
                  "QAItem + ExperimentPassage"
                  + (" + PassageTranslation." if args.include_passage_translations else "."))
            return

        wipe(db, args.include_passage_translations)
        db.commit()

        after = _counts(db)
        print("\nDeleted. Remaining rows:")
        for k, v in after.items():
            print(f"  {k:38s} {v}")


if __name__ == "__main__":
    sys.exit(main())
