#!/usr/bin/env python3
"""Export the /pilot background & eligibility questionnaire.

One row per participant who passed Section A (screened-out participants leave
no row by design -- only the anonymous count, printed at the end and written to
``pilot_screenouts.json``). Columns are the stable item codes from
``eten_shared.pilot_questionnaire``; values are option codes, free text, or
blank for a skipped item. ``religion_consent`` is blank if Section C was not
reached, ``False`` if the participant declined it (C columns then stay blank).
``familiarity_score`` = correct / 7 (Section D; never shown to participants).

Test participants are left out unless ``--include-test-participants``.

Usage (from repo root; needs DATABASE_URL or .env):
  python human_pilot/export_pilot_background.py
  python human_pilot/export_pilot_background.py --out-dir evaluation/reports/pilot
  python human_pilot/export_pilot_background.py --database-url sqlite:///local.db --stdout
"""

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "human_pilot"))
from _bootstrap import use_message_bot, use_platform  # noqa: E402

use_message_bot()
use_platform()

from eten_shared.pilot_questionnaire import SECTIONS  # noqa: E402

from export_pilot_metrics import non_test_participant_ids, session_factory_for  # noqa: E402

FIXED = [
    "participant_id",
    "instrument_version",
    "language",
    "complete",
    "eligible_at",
    "completed_at",
    "religion_consent",
    "familiarity_correct",
    "familiarity_answered",
    "familiarity_score",
]
SECTION_FIELD = {
    "eligibility": "eligibility",
    "background": "background",
    "religion": "religion",
    "familiarity": "familiarity",
}


def item_columns():
    columns = []
    for section in SECTIONS:
        for item in section["items"]:
            columns.append(item["id"])
            if item.get("specify"):
                columns.append(item["specify"]["id"])
    return columns


def flatten(row):
    flat = {key: row.get(key) for key in FIXED}
    for section in SECTIONS:
        answers = row.get(SECTION_FIELD[section["id"]]) or {}
        for item in section["items"]:
            flat[item["id"]] = answers.get(item["id"])
            if item.get("specify"):
                flat[item["specify"]["id"]] = answers.get(item["specify"]["id"])
    return flat


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out-dir", type=Path, default=REPO_ROOT / "evaluation" / "reports" / "pilot"
    )
    parser.add_argument("--participant-ids", help="comma-separated; default is every participant")
    parser.add_argument("--include-test-participants", action="store_true")
    parser.add_argument("--stdout", action="store_true", help="print JSON instead of writing files")
    parser.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    args = parser.parse_args()

    from flask import Flask  # noqa: E402
    from backend.shared.config import load_configurations  # noqa: E402
    from backend.pilot.questionnaire import get_questionnaire_results  # noqa: E402

    flask_app = Flask(__name__)
    load_configurations(flask_app)
    database_url = args.database_url or flask_app.config.get("DATABASE_URL")
    if not database_url:
        sys.exit("No DATABASE_URL (set it in the environment or .env).")

    participant_ids = [
        value.strip() for value in (args.participant_ids or "").split(",") if value.strip()
    ] or None
    with session_factory_for(database_url)() as db:
        if participant_ids is None and not args.include_test_participants:
            participant_ids = non_test_participant_ids(db)
        results = get_questionnaire_results(db, participant_ids)

    if args.stdout:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / "pilot_background.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIXED + item_columns())
        writer.writeheader()
        for row in results["responses"]:
            writer.writerow(flatten(row))
    counts_path = args.out_dir / "pilot_screenouts.json"
    counts_path.write_text(json.dumps(results["screenouts"], indent=2), encoding="utf-8")

    complete = sum(1 for row in results["responses"] if row["complete"])
    print(
        f"background export: {len(results['responses'])} eligible "
        f"({complete} complete); screen-outs {results['screenouts'] or 0}"
    )
    print(f"  wrote {csv_path}\n  wrote {counts_path}")


if __name__ == "__main__":
    main()
