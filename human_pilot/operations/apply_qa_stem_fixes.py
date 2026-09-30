#!/usr/bin/env python3
"""Push corrected QA stems/options from the dataset files into already-imported QAItem rows.

WHY THIS EXISTS INSTEAD OF A RE-IMPORT. pilot_import is idempotent by SKIPPING QA that is
already present -- it looks a row up by its planned id and counts it as ``qa_skip`` without
touching it (its own docstring: "re-running skips existing QA items and refreshes existing
passages"). So a corrected stem in the dataset never reaches participants through a plain
re-run. ``--prune-stale-qa`` is worse: it matches on question_text, so a corrected stem
makes the existing row look stale and eligible for DELETION.

This reads the translated QA the importer reads, matches rows by id only, and updates
question_text / mcq_choices / expected_answer where they differ. Idempotent, and it prints
every change before writing.

  python3 human_pilot/operations/apply_qa_stem_fixes.py --dry-run
  python3 human_pilot/operations/apply_qa_stem_fixes.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "human_pilot"))

DEFAULT_ROOT = "tier1_bsb_unblinded_5opt_think"
LETTERS = "ABCDE"


def translated_records(eval_root: Path, tier1_root: str):
    """Every clean-condition translated QA record, from the file the importer prefers."""
    base = eval_root / "outputs" / tier1_root
    for passage_dir in sorted(base.glob("t1_*")):
        clean = passage_dir / "omission" / "0%"
        for name in ("qa_target_decanonicalized.json", "qa_target.json"):
            path = clean / name
            if path.exists():
                for record in json.loads(path.read_text(encoding="utf-8")):
                    yield passage_dir.name, record
                break


def wanted_fields(record: dict) -> dict:
    """The QAItem columns this record implies (mirrors build_tier1_qa_item)."""
    if record.get("q_type") == "open":
        return {"question_text": str(record.get("Q") or "").strip()}
    options = record.get("A") or {}
    letters = [l for l in LETTERS if l in options]
    correct = str(record.get("correct") or "A").strip()[:1]
    return {
        "question_text": str(record.get("Q") or "").strip(),
        "mcq_choices": [options[l] for l in letters],
        "expected_answer": options.get(correct, ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-root", type=Path, default=REPO_ROOT / "evaluation")
    ap.add_argument("--tier1-root", default=DEFAULT_ROOT)
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set (source your .env, or pass --database-url)")

    from eten_shared.database import get_session_factory       # imported late: needs the URL
    from eten_shared.models import QAItem

    changed = skipped = missing = 0
    with get_session_factory()() as db:
        for passage_name, record in translated_records(args.eval_root, args.tier1_root):
            item_id = str(record.get("passage_id") or "")
            if not item_id:
                continue
            row = db.get(QAItem, item_id)
            if row is None:
                missing += 1
                continue
            diffs = {field: value for field, value in wanted_fields(record).items()
                     if getattr(row, field) != value}
            if not diffs:
                skipped += 1
                continue
            changed += 1
            print(f"\n  {passage_name} / {item_id}")
            for field, value in diffs.items():
                print(f"      {field}")
                print(f"        was  {getattr(row, field)!r}")
                print(f"        now  {value!r}")
                if not args.dry_run:
                    setattr(row, field, value)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    print(f"\n{changed} row(s) {'would be' if args.dry_run else ''} updated, "
          f"{skipped} already current, {missing} not in the database")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
