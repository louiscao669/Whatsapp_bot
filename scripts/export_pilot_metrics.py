#!/usr/bin/env python3
"""Export human-pilot results: accuracy, response volume and active-page timing.

Reports the same summary block per participant, per question, per condition,
per question type and overall, plus (optionally) the per-trial rows the
summaries are computed from.

Everything is recomputed from source records at export time -- pilot question
trials, immutable answer receipts and the responses the scorer writes back --
so nothing here can drift from the database, and re-running after the scoring
outbox drains simply produces better-populated numbers.

Two definitions worth knowing before reading a report:

  * ``questions_answered`` counts assignments with an ACCEPTED ANSWER RECEIPT,
    not scored responses. Scoring runs after intake and can lag, so counting
    scored rows would under-report how much work participants actually did.
  * unscored responses are excluded from accuracy denominators and are NEVER
    counted as wrong. A nonzero ``open_unscored`` / ``mcq_unscored`` means the
    export is partial: drain the outbox and export again.

Usage (from repo root; needs DATABASE_URL or .env):
  python scripts/export_pilot_metrics.py --stdout
  python scripts/export_pilot_metrics.py --out-dir evaluation/reports/pilot
  python scripts/export_pilot_metrics.py --format csv --out-dir /tmp/pilot
  python scripts/export_pilot_metrics.py --participant-ids id0,id1 --include-trials
  python scripts/export_pilot_metrics.py --database-url sqlite:///local.db --stdout
"""

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_message_bot, use_platform  # noqa: E402

use_message_bot()
use_platform()

from eten_shared.database import get_session_factory, normalize_database_url  # noqa: E402
from eten_shared.pilot_metrics import compute_pilot_metrics  # noqa: E402

#: Flat summary columns, in report order. Timing summaries are expanded into
#: ``<metric>_p25`` / ``_median`` / ``_p75`` so the CSV stays one row per group.
SUMMARY_SCALARS = [
    "questions_presented",
    "questions_started",
    "questions_answered",
    "questions_incomplete",
    "completion_rate",
    "open_count",
    "open_scored_count",
    "open_unscored",
    "correct_open",
    "accuracy_open",
    "open_score_mean",
    "mcq_count",
    "mcq_scored_count",
    "mcq_unscored",
    "correct_mcq",
    "accuracy_mcq",
]

TIMING_BLOCKS = [
    "active_time_ms",
    "focused_time_ms",
    "passage_onscreen_ms",
    "wall_clock_time_ms",
    "active_time_ms_open",
    "active_time_ms_mcq",
    "focused_time_ms_open",
    "focused_time_ms_mcq",
    "wall_clock_time_ms_open",
    "wall_clock_time_ms_mcq",
]

TRIAL_COLUMNS = [
    "participant_id",
    "pilot_session_id",
    "assignment_id",
    "qa_item_id",
    "sequence_index",
    "question_type",
    "question_bucket",
    "question_version",
    "condition",
    "defect_type",
    "defect_rate",
    "passage_id",
    "window_key",
    "status",
    "started_at",
    "submitted_at",
    "active_time_ms",
    "focused_time_ms",
    "passage_onscreen_ms",
    "wall_clock_time_ms",
    "visibility_change_count",
    "focus_change_count",
    "reload_count",
    "submission_id",
    "answer_receipt_id",
    "raw_answer",
    "selected_choice",
    "correctness_score",
    "score_value",
    "is_scored",
    "is_correct",
    "is_correct_label",
    "scoring_method",
    "scoring_version",
    "scored_at",
    "consent_version",
    "consented_at",
]


def flatten_summary(summary: dict) -> dict:
    """Summary dict -> one flat row (nested timing blocks expanded)."""

    row = {name: summary.get(name) for name in SUMMARY_SCALARS}
    for block in TIMING_BLOCKS:
        values = summary.get(block) or {}
        row[f"{block}_n"] = values.get("n")
        row[f"{block}_p25"] = values.get("p25")
        row[f"{block}_median"] = values.get("median")
        row[f"{block}_p75"] = values.get("p75")
    return row


def _summary_fieldnames(key_columns):
    row = flatten_summary({})
    return list(key_columns) + list(row.keys())


def _write_csv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_csv_tables(report: dict, include_trials: bool) -> dict:
    """``{filename: (fieldnames, rows)}`` for the CSV export."""

    tables = {
        "pilot_overall.csv": (
            _summary_fieldnames(["scope"]),
            [{"scope": "overall", **flatten_summary(report["overall"])}],
        ),
        "pilot_by_participant.csv": (
            _summary_fieldnames(["participant_id"]),
            [
                {"participant_id": row["participant_id"], **flatten_summary(row)}
                for row in report["by_participant"]
            ],
        ),
        "pilot_by_condition.csv": (
            _summary_fieldnames(["condition"]),
            [
                {"condition": row["condition"], **flatten_summary(row)}
                for row in report["by_condition"]
            ],
        ),
        "pilot_by_question_type.csv": (
            _summary_fieldnames(["question_type"]),
            [
                {"question_type": row["question_type"], **flatten_summary(row)}
                for row in report["by_question_type"]
            ],
        ),
        "pilot_by_question.csv": (
            _summary_fieldnames(
                [
                    "qa_item_id",
                    "question_version",
                    "question_type",
                    "question_bucket",
                    "passage_id",
                    "window_key",
                ]
            ),
            [
                {
                    "qa_item_id": row["qa_item_id"],
                    "question_version": row["question_version"],
                    "question_type": row["question_type"],
                    "question_bucket": row["question_bucket"],
                    "passage_id": row["passage_id"],
                    "window_key": row["window_key"],
                    **flatten_summary(row),
                }
                for row in report["by_question"]
            ],
        ),
    }
    if include_trials:
        tables["pilot_trials.csv"] = (TRIAL_COLUMNS, report.get("trials", []))
    return tables


def session_factory_for(database_url):
    """Read-only session factory for the export.

    Postgres goes through the shared ``get_session_factory`` so it shares the
    app's engine cache and startup migrations, exactly like the sibling
    exports. Anything else (a scratch SQLite file from a local run) binds
    directly: those startup migrations are Postgres-only DDL and would fail,
    and this export never writes, so it does not need them.
    """

    resolved = normalize_database_url(database_url)
    if resolved.startswith("postgresql"):
        return get_session_factory(resolved)

    from sqlalchemy import create_engine  # noqa: E402
    from sqlalchemy.orm import sessionmaker  # noqa: E402

    return sessionmaker(create_engine(resolved), autoflush=False, expire_on_commit=False)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out-dir", type=Path, default=REPO_ROOT / "evaluation" / "reports" / "pilot"
    )
    parser.add_argument("--format", choices=["json", "csv", "both"], default="both")
    parser.add_argument(
        "--participant-ids", help="comma-separated; default is every pilot participant"
    )
    parser.add_argument(
        "--include-trials",
        action="store_true",
        help="also emit the per-trial rows the summaries are computed from",
    )
    parser.add_argument(
        "--stdout", action="store_true", help="print the JSON report instead of writing files"
    )
    parser.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    args = parser.parse_args()

    participant_ids = [
        value.strip()
        for value in (args.participant_ids or "").split(",")
        if value.strip()
    ] or None

    # Same bootstrap as the sibling exports: the Flask config loader is what
    # reads the repo-root .env, so a bare `python scripts/...` run works.
    from flask import Flask  # noqa: E402
    from app.config import load_configurations  # noqa: E402

    flask_app = Flask(__name__)
    load_configurations(flask_app)
    database_url = args.database_url or flask_app.config.get("DATABASE_URL")
    if not database_url:
        sys.exit("No DATABASE_URL (set it in the environment or .env).")

    with session_factory_for(database_url)() as db:
        report = compute_pilot_metrics(db, participant_ids=participant_ids)

    if not args.include_trials:
        report.pop("trials", None)

    if args.stdout:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return

    written = []
    if args.format in ("json", "both"):
        json_path = args.out_dir / "pilot_results.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        written.append(json_path)
    if args.format in ("csv", "both"):
        for name, (fieldnames, rows) in build_csv_tables(
            report, args.include_trials
        ).items():
            path = args.out_dir / name
            _write_csv(path, fieldnames, rows)
            written.append(path)

    overall = report["overall"]
    print(
        f"pilot export: {overall['questions_presented']} presented, "
        f"{overall['questions_answered']} answered, "
        f"{overall['questions_incomplete']} incomplete, "
        f"{overall['open_unscored']} open + {overall['mcq_unscored']} mcq unscored"
    )
    for path in written:
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
