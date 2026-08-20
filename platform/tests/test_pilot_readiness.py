"""The pilot readiness preflight: what it refuses, and what it reports.

The DB-touching checks are exercised against the real database by running the
script; what is pinned here is the decision logic that decides whether an
automated repair is allowed to run at all.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verify_pilot_readiness import (  # noqa: E402
    FAIL,
    OK,
    WARN,
    Report,
    migration_rewrites,
)


class MigrationSafetyTests(unittest.TestCase):
    """`--fix` may only auto-apply migrations that ADD."""

    def test_the_pilot_migrations_are_purely_additive(self):
        for filename in ("pilot_question_trials.sql", "pilot_attention_measures.sql"):
            with self.subTest(migration=filename):
                self.assertEqual(
                    migration_rewrites(filename),
                    [],
                    f"{filename} must only add, so --fix can apply it unattended",
                )

    def test_a_migration_that_drops_or_rewrites_is_flagged(self):
        """tier1_experiment_windows.sql drops a unique constraint on
        experiment_passages and backfills a column -- on a table already holding
        the study's variant passages. It must never be applied unattended."""

        rewrites = migration_rewrites("tier1_experiment_windows.sql")

        self.assertTrue(rewrites)
        joined = " ".join(rewrites).lower()
        self.assertIn("drop constraint", joined)
        self.assertIn("update ", joined)

    def test_a_missing_migration_file_is_not_reported_as_risky(self):
        self.assertEqual(migration_rewrites("does-not-exist.sql"), [])

    def test_comments_mentioning_a_drop_do_not_trip_the_check(self):
        """The migrations explain themselves at length; prose must not count."""
        rewrites = migration_rewrites("pilot_question_trials.sql")
        self.assertEqual(rewrites, [])


class ReportTests(unittest.TestCase):
    def test_only_failures_contribute_a_migration_to_repair(self):
        report = Report()
        report.add("a", OK, migration="already_applied.sql")
        report.add("b", WARN, migration="not_blocking.sql")
        report.add("c", FAIL, migration="needed.sql")

        self.assertEqual(report.missing_migrations(), ["needed.sql"])

    def test_repeated_failures_request_each_migration_once(self):
        report = Report()
        report.add("a", FAIL, migration="needed.sql")
        report.add("b", FAIL, migration="needed.sql")

        self.assertEqual(report.missing_migrations(), ["needed.sql"])

    def test_warnings_do_not_block_readiness(self):
        report = Report()
        report.add("a", OK)
        report.add("b", WARN)

        self.assertEqual(report.failed, [])
        self.assertEqual(len(report.warned), 1)

    def test_a_single_failure_blocks_readiness(self):
        report = Report()
        report.add("a", OK)
        report.add("b", FAIL)

        self.assertEqual(len(report.failed), 1)


if __name__ == "__main__":
    unittest.main()
