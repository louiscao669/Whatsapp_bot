"""The pilot results export: CSV shape, and agreement with the existing slate."""

import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.pilot.service import (
    get_pilot_state,
    mark_pilot_question_viewed,
    submit_pilot_answer,
)
from eten_shared.models import (
    Assignment,
    Base,
    ExperimentPlanCell,
    Participant,
    QAItem,
)
from eten_shared.pilot_metrics import compute_pilot_metrics
from eten_shared.pilot_trials import CONDITION_DEFECTS, defect_for_condition

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from export_pilot_metrics import (  # noqa: E402
    SUMMARY_SCALARS,
    build_csv_tables,
    flatten_summary,
    session_factory_for,
)
from export_pilot_responses import CONDITION_TO_EVAL  # noqa: E402


class ConditionSlateTests(unittest.TestCase):
    def test_pilot_defect_map_agrees_with_the_response_export(self):
        """Two exports, one slate. A condition present in one but not the other
        would silently drop or misroute a whole experimental cell."""

        self.assertEqual(set(CONDITION_DEFECTS), set(CONDITION_TO_EVAL))
        for condition, (defect, level) in CONDITION_TO_EVAL.items():
            with self.subTest(condition=condition):
                pilot_defect, pilot_rate = defect_for_condition(condition)
                self.assertEqual(pilot_defect, defect)
                expected_rate = None if level is None else float(level.rstrip("%")) / 100
                self.assertEqual(pilot_rate, expected_rate)

    def test_an_unknown_condition_resolves_to_nothing_rather_than_guessing(self):
        self.assertEqual(defect_for_condition("not-a-condition"), (None, None))
        self.assertEqual(defect_for_condition(None), (None, None))


class PilotExportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

        participant = Participant(display_name="P1", consented=True)
        qa_item = QAItem(
            passage_id="t1_luke1",
            passage_reference="1:1",
            question_text="What happened?",
            expected_answer="Something",
            question_type="open",
        )
        self.db.add_all([participant, qa_item])
        self.db.flush()
        cell = ExperimentPlanCell(
            participant_id=participant.id,
            chapter=3,
            condition="omission30",
            sequence_index=0,
        )
        self.db.add(cell)
        self.db.flush()
        assignment = Assignment(
            participant_id=participant.id,
            qa_item_id=qa_item.id,
            batch_id="pilot-batch",
            passage_text="Verse one.",
            experiment_cell_id=cell.id,
        )
        self.db.add(assignment)
        self.db.flush()

        get_pilot_state(self.db, participant.id)
        mark_pilot_question_viewed(self.db, participant.id, assignment.id)
        submit_pilot_answer(
            self.db, participant.id, assignment.id,
            submission_id="sub-1", answer="An answer", active_time_ms=4_000,
        )
        self.participant_id = participant.id
        self.report = compute_pilot_metrics(self.db)

    def test_the_experiment_cell_supplies_condition_and_defect_provenance(self):
        row = self.report["trials"][0]

        self.assertEqual(row["condition"], "omission30")
        self.assertEqual(row["defect_type"], "omission")
        self.assertEqual(row["defect_rate"], 0.30)
        self.assertEqual(
            [group["condition"] for group in self.report["by_condition"]], ["omission30"]
        )

    def test_flatten_summary_expands_every_reported_metric(self):
        flat = flatten_summary(self.report["overall"])

        for name in SUMMARY_SCALARS:
            self.assertIn(name, flat)
        for block in ("active_time_ms", "wall_clock_time_ms",
                      "active_time_ms_open", "active_time_ms_mcq"):
            for suffix in ("n", "p25", "median", "p75"):
                self.assertIn(f"{block}_{suffix}", flat)
        self.assertEqual(flat["questions_answered"], 1)
        self.assertEqual(flat["active_time_ms_median"], 4_000)

    def test_csv_tables_cover_every_required_grouping(self):
        tables = build_csv_tables(self.report, include_trials=True)

        self.assertEqual(
            set(tables),
            {
                "pilot_overall.csv",
                "pilot_by_participant.csv",
                "pilot_by_condition.csv",
                "pilot_by_question_type.csv",
                "pilot_by_question.csv",
                "pilot_trials.csv",
            },
        )
        for name, (fieldnames, rows) in tables.items():
            with self.subTest(table=name):
                buffer = io.StringIO()
                writer = csv.DictWriter(
                    buffer, fieldnames=fieldnames, extrasaction="ignore"
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
                parsed = list(csv.DictReader(io.StringIO(buffer.getvalue())))
                self.assertTrue(parsed, f"{name} should not be empty")

        participant_rows = list(
            csv.DictReader(
                io.StringIO(_render(*tables["pilot_by_participant.csv"]))
            )
        )
        self.assertEqual(participant_rows[0]["participant_id"], self.participant_id)
        self.assertEqual(participant_rows[0]["questions_answered"], "1")

    def test_a_scratch_sqlite_url_skips_the_postgres_startup_migrations(self):
        """The export is read-only, so a local run must not need Postgres DDL."""
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'scratch.db'}"
            Base.metadata.create_all(create_engine(url))

            with patch("export_pilot_metrics.get_session_factory") as shared:
                factory = session_factory_for(url)
            shared.assert_not_called()

            with factory() as db:
                report = compute_pilot_metrics(db)
        self.assertEqual(report["overall"]["questions_presented"], 0)

    def test_a_postgres_url_still_goes_through_the_shared_factory(self):
        with patch("export_pilot_metrics.get_session_factory") as shared:
            session_factory_for("postgres://user:pw@host:5432/db")
        shared.assert_called_once_with("postgresql+psycopg://user:pw@host:5432/db")

    def test_unscored_accuracy_is_blank_rather_than_zero_in_csv(self):
        rendered = _render(*build_csv_tables(self.report, include_trials=False)[
            "pilot_overall.csv"
        ])
        row = list(csv.DictReader(io.StringIO(rendered)))[0]

        # Nothing has been scored yet: accuracy must be empty, not "0".
        self.assertEqual(row["accuracy_open"], "")
        self.assertEqual(row["accuracy_mcq"], "")
        self.assertEqual(row["open_unscored"], "1")


def _render(fieldnames, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
