#!/usr/bin/env python3
"""Delete ALL passage_translations rows (and their verses) -- nothing else.

This clears the admin 'Passages' tab (which reads passage_translations /
passage_verses). It does NOT touch qa_items or experiment_passages, so your
pilot QA and the new 'Experiment passages' view are left intact.

Safe by default: prints counts and exits. Pass --confirm to actually delete.

Usage:
  python scripts/wipe_passage_translations.py            # dry run
  python scripts/wipe_passage_translations.py --confirm  # delete
"""

import argparse
import sys

from _bootstrap import use_message_bot

use_message_bot()

from eten_shared.models import PassageTranslation, PassageVerse  # noqa: E402


def _counts(db):
    from sqlalchemy import func, select

    return {
        "PassageTranslation": db.scalar(select(func.count()).select_from(PassageTranslation)) or 0,
        "PassageVerse": db.scalar(select(func.count()).select_from(PassageVerse)) or 0,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--confirm", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    args = ap.parse_args()

    from sqlalchemy import select

    from eten_shared.database import get_session_factory

    factory = get_session_factory(args.database_url)
    with factory() as db:
        before = _counts(db)
        print("Current rows:")
        for k, v in before.items():
            print(f"  {k:20s} {v}")

        if not args.confirm:
            print("\n[dry-run] nothing deleted. Re-run with --confirm to delete "
                  "PassageTranslation + PassageVerse (qa_items / experiment_passages untouched).")
            return

        # ORM delete so PassageVerse children cascade with the translation
        for translation in db.scalars(select(PassageTranslation)).all():
            db.delete(translation)
        db.commit()

        after = _counts(db)
        print("\nDeleted. Remaining rows:")
        for k, v in after.items():
            print(f"  {k:20s} {v}")


if __name__ == "__main__":
    sys.exit(main())
