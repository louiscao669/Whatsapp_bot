#!/usr/bin/env python3
"""Preflight for the human pilot: is this database ready to run participants?

``verify_experiment_delivery.py`` answers "will a plan cell deliver the right
variant passage". This answers the broader question that has to be true before
anyone opens ``/pilot`` at all -- schema, content, per-participant plan,
runtime flags and leftover data -- and reports every failure at once with the
command that fixes it, rather than surfacing them one crash at a time.

Exit code is 0 only when nothing is FAIL.

  python scripts/verify_pilot_readiness.py
  python scripts/verify_pilot_readiness.py --participant-ids id0,id1
  python scripts/verify_pilot_readiness.py --participant-ids id0,id1 --fix

--fix performs ONLY the safe, idempotent, additive repairs: applying purely
additive pilot migrations and building missing plan cells (delegated to
``build_experiment_plan.py``, which owns the Latin square). A migration that
drops a constraint, drops a column or rewrites rows is printed and REFUSED
unless you pass ``--allow-schema-rewrite``. It also deliberately refuses to:

  * set ``participants.consented`` -- consent is a claim about what a human
    agreed to, not a database state to be manufactured. Record it where you
    actually collected it, then re-run.
  * change ``target_language`` -- it also steers dashboard/messenger passage
    delivery. Needs ``--set-language``.
  * delete anything -- use ``scripts/pilot_wipe.py`` deliberately.
  * edit ``.env`` -- the flags are printed for you to set.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_platform  # noqa: E402

use_platform()

from sqlalchemy import func, select, text  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.domain.assignments import (  # noqa: E402
    participant_language_code,
    resolve_experiment_passage,
)
from eten_shared.models import (  # noqa: E402
    AnswerReceipt,
    Assignment,
    ExperimentPassage,
    ExperimentPlanCell,
    Participant,
    ParticipantResponse,
    PilotQuestionTrial,
    QAItem,
)

# The plan builder owns the condition slate and the group count; importing them
# keeps this preflight from drifting into a second, disagreeing definition.
from build_experiment_plan import GROUPS, LANGUAGE, SLOTS  # noqa: E402

# The real candidate query the selector uses. Checking anything less faithful
# would pass while delivery still fails.
from eten_shared.question_discovery.experiment_selection import (  # noqa: E402
    _cell_candidates,
)

OK, WARN, FAIL = "OK", "WARN", "FAIL"
_SYMBOL = {OK: "PASS", WARN: "WARN", FAIL: "FAIL"}

MIGRATIONS = REPO_ROOT / "supabase" / "migrations"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    remedy: str = ""
    #: migration file this check's failure is repaired by, if any
    migration: Optional[str] = None


@dataclass
class Report:
    checks: List[Check] = field(default_factory=list)

    def add(self, *args, **kwargs):
        self.checks.append(Check(*args, **kwargs))
        return self.checks[-1]

    @property
    def failed(self):
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warned(self):
        return [c for c in self.checks if c.status == WARN]

    def missing_migrations(self):
        seen = []
        for check in self.failed:
            if check.migration and check.migration not in seen:
                seen.append(check.migration)
        return seen


# --------------------------------------------------------------------- schema
def _tables(db):
    return {
        row[0]
        for row in db.execute(
            text("select table_name from information_schema.tables where table_schema='public'")
        )
    }


def _columns(db, table):
    return {
        row[0]
        for row in db.execute(
            text(
                "select column_name from information_schema.columns "
                "where table_name = :t"
            ),
            {"t": table},
        )
    }


def check_schema(db, report):
    tables = _tables(db)

    # experiment_windows is queried UNCONDITIONALLY by the selector and by the
    # plan builder, before either falls back to the Luke path. A missing table
    # raises rather than returning empty, so the fallback is unreachable and
    # both crash. An empty table is fine -- that is what enables the fallback.
    if "experiment_windows" in tables:
        report.add("schema: experiment_windows", OK)
    else:
        report.add(
            "schema: experiment_windows",
            FAIL,
            "table missing -- the selector and plan builder query it before "
            "falling back to the Luke path, so both raise UndefinedTable",
            "apply tier1_experiment_windows.sql (an EMPTY table is fine)",
            migration="tier1_experiment_windows.sql",
        )

    for table in ("pilot_sessions", "pilot_question_trials"):
        if table in tables:
            report.add(f"schema: {table}", OK)
        else:
            report.add(
                f"schema: {table}",
                FAIL,
                "table missing -- /pilot cannot record trials",
                "apply pilot_question_trials.sql",
                migration="pilot_question_trials.sql",
            )

    if "pilot_question_trials" in tables:
        cols = _columns(db, "pilot_question_trials")
        missing = {"focused_time_ms", "passage_onscreen_ms", "focus_change_count"} - cols
        if missing:
            report.add(
                "schema: attention measures",
                FAIL,
                f"pilot_question_trials missing {sorted(missing)}",
                "apply pilot_attention_measures.sql",
                migration="pilot_attention_measures.sql",
            )
        else:
            report.add("schema: attention measures", OK)

    if "scored_at" in _columns(db, "participant_responses"):
        report.add("schema: participant_responses.scored_at", OK)
    else:
        report.add(
            "schema: participant_responses.scored_at",
            FAIL,
            "missing -- every response would export as unscored",
            "apply pilot_question_trials.sql",
            migration="pilot_question_trials.sql",
        )


# -------------------------------------------------------------------- content
def check_content(db, report, language):
    slate = sorted(set(SLOTS))
    present = {
        row[0]
        for row in db.execute(
            select(ExperimentPassage.condition).where(
                ExperimentPassage.language == language
            )
        )
    }
    missing = [c for c in slate if c not in present]
    if missing:
        report.add(
            "content: variant passages",
            FAIL,
            f"no {language!r} passages for conditions {missing}",
            "python scripts/pilot_import.py --eval-root evaluation",
        )
    else:
        report.add(
            "content: variant passages",
            OK,
            f"{len(slate)} conditions present in {language!r}",
        )

    qa_total = db.scalar(select(func.count(QAItem.id)).where(QAItem.active.is_(True))) or 0
    if qa_total:
        report.add("content: qa items", OK, f"{qa_total} active")
    else:
        report.add(
            "content: qa items",
            FAIL,
            "no active QA items",
            "python scripts/pilot_import.py --eval-root evaluation",
        )

    # Distinctness spot-check: if clean and a defect condition are byte-identical
    # the manipulation is not actually in the delivered text, and every
    # downstream number would look well-formed while measuring nothing.
    identical = []
    for defect in ("omission30", "mistranslation30"):
        rows = db.execute(
            select(ExperimentPassage.chapter, ExperimentPassage.condition,
                   ExperimentPassage.passage_text)
            .where(
                ExperimentPassage.language == language,
                ExperimentPassage.condition.in_(("clean", defect)),
            )
        ).all()
        by_chapter = {}
        for chapter, condition, body in rows:
            by_chapter.setdefault(chapter, {})[condition] = body
        for chapter, variants in by_chapter.items():
            if (
                "clean" in variants
                and defect in variants
                and variants["clean"] == variants[defect]
            ):
                identical.append(f"{chapter}/{defect}")
    if identical:
        report.add(
            "content: conditions are distinct",
            FAIL,
            f"clean == defect text for {identical[:5]}",
            "re-run pilot_import.py; the import read the wrong files",
        )
    else:
        report.add("content: conditions are distinct", OK)


# --------------------------------------------------------------- participants
def resolve_targets(db, participant_ids):
    if participant_ids:
        found = []
        for pid in participant_ids:
            participant = db.get(Participant, pid)
            if participant is None:
                print(f"  [warn] participant {pid} not found -- skipped")
                continue
            found.append(participant)
        return found
    return list(db.scalars(select(Participant).order_by(Participant.created_at)))


def check_participants(db, report, participants, language, tables):
    if not participants:
        report.add(
            "participants: cohort",
            FAIL,
            "no participants selected",
            "pass --participant-ids, or create participants first",
        )
        return

    report.add("participants: cohort", OK, f"{len(participants)} selected")

    unconsented = [p for p in participants if not p.consented]
    if unconsented:
        report.add(
            "participants: consent",
            FAIL,
            f"{len(unconsented)} of {len(participants)} have consented=False "
            f"(--all-consented would skip them)",
            "record consent where you actually collected it; --fix will NOT set it",
        )
    else:
        report.add("participants: consent", OK)

    no_language = [p for p in participants if not (p.target_language or "").strip()]
    if no_language:
        report.add(
            "participants: target_language",
            WARN,
            f"{len(no_language)} have no target_language",
            "set it, or pass --set-language <code> with --fix",
        )
    else:
        report.add("participants: target_language", OK)

    if "experiment_plan_cells" not in tables:
        return

    planless, partial = [], []
    for participant in participants:
        cells = db.scalar(
            select(func.count(ExperimentPlanCell.id)).where(
                ExperimentPlanCell.participant_id == participant.id
            )
        ) or 0
        if cells == 0:
            planless.append(participant)
        elif cells != len(GROUPS):
            partial.append((participant.id, cells))

    if planless:
        report.add(
            "participants: plan cells",
            FAIL,
            f"{len(planless)} of {len(participants)} have NO experiment_plan_cells "
            f"-- they are not in the experiment and /pilot would serve them no "
            f"condition",
            "python scripts/build_experiment_plan.py --participant-ids <ids>",
        )
    elif partial:
        report.add(
            "participants: plan cells",
            WARN,
            f"partial plans: {partial}",
            f"expected {len(GROUPS)} cells each",
        )
    else:
        report.add(
            "participants: plan cells",
            OK,
            f"{len(GROUPS)} cells each",
        )

    # The check that actually proves delivery: for every planned cell, does the
    # real selector find a question, and does it resolve to the CONDITION's
    # passage? This is where a language mismatch or a stripped FK surfaces.
    if "experiment_windows" not in tables:
        report.add(
            "participants: delivery resolves",
            WARN,
            "skipped -- experiment_windows is missing, so the selector cannot run",
            "fix the schema first, then re-run",
        )
        return

    broken = []
    for participant in participants:
        cells = db.scalars(
            select(ExperimentPlanCell)
            .where(ExperimentPlanCell.participant_id == participant.id)
            .order_by(ExperimentPlanCell.sequence_index)
        ).all()
        for cell in cells:
            candidates = _cell_candidates(db, cell, participant)
            if not candidates:
                broken.append(f"{participant.id[:8]}/group{cell.chapter}: no eligible QA")
                continue
            passage = resolve_experiment_passage(
                db, cell, candidates[0], participant_language_code(participant)
            )
            if passage is None:
                broken.append(
                    f"{participant.id[:8]}/group{cell.chapter}/{cell.condition}: "
                    f"no passage for language "
                    f"{participant_language_code(participant)!r}"
                )
            elif passage.condition != cell.condition:
                broken.append(
                    f"{participant.id[:8]}/group{cell.chapter}: cell is "
                    f"{cell.condition!r} but passage is {passage.condition!r}"
                )
            elif not (passage.passage_text or "").strip():
                broken.append(f"{participant.id[:8]}/group{cell.chapter}: empty passage")

    if broken:
        report.add(
            "participants: delivery resolves",
            FAIL,
            f"{len(broken)} cell(s) cannot deliver; first: {broken[:4]}",
            f"python scripts/verify_experiment_delivery.py --language {language}",
        )
    elif any(
        db.scalar(
            select(func.count(ExperimentPlanCell.id)).where(
                ExperimentPlanCell.participant_id == p.id
            )
        )
        for p in participants
    ):
        report.add("participants: delivery resolves", OK, "every planned cell resolves")


# -------------------------------------------------------------------- runtime
def check_runtime(report):
    if (os.getenv("ENABLE_EXPERIMENT_ASSIGNMENT", "") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }:
        report.add("runtime: ENABLE_EXPERIMENT_ASSIGNMENT", OK)
    else:
        report.add(
            "runtime: ENABLE_EXPERIMENT_ASSIGNMENT",
            FAIL,
            "not enabled -- /pilot will not mint questions from the plan and "
            "participants land straight on the completion page",
            "set ENABLE_EXPERIMENT_ASSIGNMENT=true in .env",
        )

    scoring_on = (os.getenv("ENABLE_LLM_ANSWER_SCORING", "") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    has_key = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    if scoring_on and has_key:
        report.add("runtime: answer scoring", OK)
    else:
        report.add(
            "runtime: answer scoring",
            WARN,
            f"ENABLE_LLM_ANSWER_SCORING={'on' if scoring_on else 'off'}, "
            f"OPENAI_API_KEY={'set' if has_key else 'missing'} -- answers are still "
            f"captured, but export as unscored",
            "set both, and run the message-bot process so the receipt drain runs",
        )

    if (os.getenv("DASHBOARD_LINK_SECRET") or os.getenv("SECRET_KEY") or "").strip():
        report.add("runtime: deep-link secret", OK)
    else:
        report.add(
            "runtime: deep-link secret",
            WARN,
            "no DASHBOARD_LINK_SECRET/SECRET_KEY -- /pilot/t/<token> links cannot "
            "be generated (bare /pilot/<participant_id> still works)",
            "set DASHBOARD_LINK_SECRET",
        )


# -------------------------------------------------------------------- hygiene
def check_hygiene(db, report, participants, tables):
    if not participants:
        return
    ids = [p.id for p in participants]

    prior_assignments = db.scalar(
        select(func.count(Assignment.id)).where(Assignment.participant_id.in_(ids))
    ) or 0
    prior_receipts = db.scalar(
        select(func.count(AnswerReceipt.id)).where(AnswerReceipt.participant_id.in_(ids))
    ) or 0
    prior_responses = db.scalar(
        select(func.count(ParticipantResponse.id)).where(
            ParticipantResponse.participant_id.in_(ids)
        )
    ) or 0
    if prior_assignments or prior_responses:
        report.add(
            "hygiene: pre-pilot data",
            WARN,
            f"{prior_assignments} assignments / {prior_receipts} receipts / "
            f"{prior_responses} responses already exist for this cohort and will "
            f"be pooled into the export",
            "python scripts/pilot_wipe.py  (deliberate; --fix will not delete)",
        )
    else:
        report.add("hygiene: pre-pilot data", OK, "clean slate")

    if "pilot_question_trials" in tables:
        trials = db.scalar(
            select(func.count(PilotQuestionTrial.id)).where(
                PilotQuestionTrial.participant_id.in_(ids)
            )
        ) or 0
        if trials:
            report.add(
                "hygiene: existing pilot trials",
                WARN,
                f"{trials} trial(s) already recorded for this cohort",
                "expected if you are resuming; unexpected before a first run",
            )
        else:
            report.add("hygiene: existing pilot trials", OK)


# ------------------------------------------------------------------------ fix
#: Statements that change or discard something already in the database, as
#: opposed to adding to it. A migration containing any of these is not safe to
#: run unattended just because a check failed -- e.g.
#: tier1_experiment_windows.sql drops a unique constraint on
#: experiment_passages and backfills a column, on a table already holding the
#: study's variant passages.
_REWRITING = ("drop constraint", "drop column", "drop table", "drop index", "update ")


def migration_rewrites(filename):
    """Lines in this migration that alter or discard existing data/schema."""

    path = MIGRATIONS / filename
    if not path.exists():
        return []
    risky = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lowered = stripped.lower()
        if any(token in lowered for token in _REWRITING):
            risky.append(f"{filename}:{number}  {stripped}")
    return risky


def apply_migration(db, filename):
    path = MIGRATIONS / filename
    if not path.exists():
        return False, f"{filename} not found"
    # Applied as one script: splitting on ";" would tear apart DO $$ ... $$
    # blocks, which are exactly how the additive migrations add constraints.
    db.execute(text("commit"))  # leave any implicit transaction before DDL
    db.connection().exec_driver_sql(path.read_text())
    db.commit()
    return True, f"applied {filename}"


def run_fix(report, factory, participants, args):
    print("\n--- fix ---")
    changed = False

    for filename in report.missing_migrations():
        rewrites = migration_rewrites(filename)
        if rewrites and not args.allow_schema_rewrite:
            print(f"  ! REFUSING to auto-apply {filename}: it does not only add.")
            for line in rewrites:
                print(f"      {line}")
            print(
                "    Review it, then re-run with --allow-schema-rewrite, or apply it "
                f"yourself:\n      psql \"$DATABASE_URL\" -f supabase/migrations/{filename}"
            )
            continue
        with factory() as db:
            ok, message = apply_migration(db, filename)
        print(f"  {'+' if ok else '!'} {message}")
        changed = changed or ok

    if args.set_language:
        with factory() as db:
            for participant in participants:
                row = db.get(Participant, participant.id)
                if (row.target_language or "") != args.set_language:
                    print(
                        f"  + target_language {row.target_language!r} -> "
                        f"{args.set_language!r} for {row.id}"
                    )
                    row.target_language = args.set_language
                    changed = True
            db.commit()

    # Plan cells are built by the real plan builder, never reimplemented here:
    # it owns the Latin square, the block ordering and the passage FKs.
    needs_plan = [c for c in report.failed if c.name == "participants: plan cells"]
    if needs_plan and participants:
        consented = [p for p in participants if p.consented]
        if not consented:
            print(
                "  ! skipping plan build: no selected participant has consented=True. "
                "Record consent first -- this script will not set it for you."
            )
        else:
            ids = ",".join(p.id for p in consented)
            print(f"  + building plan cells for {len(consented)} consented participant(s)")
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "build_experiment_plan.py"),
                 "--participant-ids", ids, "--language", args.language],
                cwd=REPO_ROOT,
            )
            changed = changed or result.returncode == 0
            if result.returncode != 0:
                print("  ! build_experiment_plan.py failed")

    if not changed:
        print("  (nothing to fix, or nothing fixable without your decision)")
    return changed


# ----------------------------------------------------------------------- main
def run_checks(factory, args):
    report = Report()
    with factory() as db:
        tables = _tables(db)
        check_schema(db, report)
        check_content(db, report, args.language)
        participants = resolve_targets(db, args.participant_ids)
        check_participants(db, report, participants, args.language, tables)
        check_hygiene(db, report, participants, tables)
    check_runtime(report)
    return report, participants


def print_report(report):
    width = max(len(c.name) for c in report.checks)
    print()
    for check in report.checks:
        print(f"  [{_SYMBOL[check.status]}] {check.name.ljust(width)}  {check.detail}")
        if check.status != OK and check.remedy:
            print(f"{'':>9}{'':{width}}  -> {check.remedy}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--participant-ids", help="comma-separated; default is every participant"
    )
    parser.add_argument("--language", default=LANGUAGE)
    parser.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="apply the safe, idempotent repairs (migrations, plan cells), then re-check",
    )
    parser.add_argument(
        "--allow-schema-rewrite",
        action="store_true",
        help="permit --fix to apply a migration that alters or drops existing "
             "schema/data, not just adds to it (it prints exactly which lines)",
    )
    parser.add_argument(
        "--set-language",
        help="with --fix, set target_language on the selected participants "
             "(also affects dashboard/messenger delivery -- opt in deliberately)",
    )
    args = parser.parse_args()
    args.participant_ids = [
        value.strip() for value in (args.participant_ids or "").split(",") if value.strip()
    ]

    from flask import Flask  # noqa: E402
    from app.config import load_configurations  # noqa: E402

    flask_app = Flask(__name__)
    load_configurations(flask_app)
    database_url = args.database_url or flask_app.config.get("DATABASE_URL")
    if not database_url:
        sys.exit("No DATABASE_URL (set it in the environment or .env).")
    factory = get_session_factory(database_url)

    report, participants = run_checks(factory, args)
    print_report(report)

    if args.fix:
        run_fix(report, factory, participants, args)
        print("\n--- re-check ---")
        report, _ = run_checks(factory, args)
        print_report(report)

    print()
    if report.failed:
        print(
            f"NOT READY: {len(report.failed)} blocking issue(s), "
            f"{len(report.warned)} warning(s)."
        )
        return 1
    print(f"READY. {len(report.warned)} warning(s) to review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
