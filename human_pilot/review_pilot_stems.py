"""Review Chinese pilot questions without choices and publish grounding retirements."""
import argparse
import fcntl
import json
import os
import stat
import sys
from pathlib import Path

from openai import OpenAI
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, selectinload

import pilot_import_reviewed122 as pilot
sys.path.insert(0, str(pilot.ROOT))
from eten_shared.experiment_plan import qa_set_groups
from eten_shared.models import ExperimentPassage, ExperimentWindow, QAItem
from evaluation.scripts.mcq.diagnostics.audit_reviewed_mcq_targets import save
from qa_generation.services.mcq_target import grounding_version, review_stem_grounding


def collect(rows, client, model, output):
    results = {}
    for row in rows:
        signature = pilot.stem_signature(row)
        path = output / "checks" / f"{signature}.json"
        decision = json.loads(path.read_text()) if path.exists() else {}
        if not (decision.get("model") == model and decision.get("version") == grounding_version()
                and decision.get("stem_signature") == signature and decision.get("id") == row["id"]
                and decision.get("verdict") in ("pass", "review", "retire")):
            result = review_stem_grounding(client, model, row["question"], "\n".join(row["verses"].values()))
            decision = dict(result, stem_signature=signature, id=row["id"])
            save(path, decision)
        results[row["id"]] = decision
    return results


def apply_decisions(roster, rows, findings):
    by_id = {r["id"]: r for r in rows}
    updated = []
    for entry in roster:
        finding = findings.get(entry["id"])
        if finding and (finding["id"] != entry["id"] or finding["stem_signature"] != pilot.stem_signature(by_id[entry["id"]])):
            raise ValueError(f"Review is for a different released stem: {entry['id']}")
        if entry["status"] == "eligible" and finding and finding["verdict"] == "retire":
            entry = dict(entry, status="withheld", retired_from_pilot=True, reason=finding["reason"],
                         grounding_review=finding)
        updated.append(entry)
    pilot.validate_sol_dispositions(updated, rows)
    return updated


def live_windows(db):
    values = db.execute(select(ExperimentWindow.content_id, ExperimentWindow.id, ExperimentWindow.qa_item_id,
                               ExperimentWindow.group_index, ExperimentWindow.sequence_index).where(
        ExperimentWindow.group_index.in_(qa_set_groups(pilot.SOL_SET))))
    return {cid: tuple(fields) for cid, *fields in values}


def related_copies(db, source_ids):
    """Resolve each live sibling to its own Chinese clean window and wording."""
    copies = {}
    statement = (select(ExperimentWindow, QAItem, ExperimentPassage)
                 .join(QAItem, QAItem.id == ExperimentWindow.qa_item_id)
                 .join(ExperimentPassage, ExperimentPassage.source_passage_id == ExperimentWindow.source_passage_id)
                 .options(selectinload(ExperimentPassage.verses))
                 .where(ExperimentWindow.content_id.in_(source_ids),
                        ExperimentWindow.group_index.not_in(qa_set_groups(pilot.SOL_SET)),
                        ExperimentPassage.condition == "clean", ExperimentPassage.language == "zh",
                        QAItem.review_removed_at.is_(None)).order_by(ExperimentWindow.sequence_index))
    for window, item, passage in db.execute(statement):
        verses = {v.verse_number: v.text for v in passage.verses}
        if not window.verse_numbers or any(n not in verses for n in window.verse_numbers):
            raise ValueError(f"Missing clean verses for {window.source_passage_id}/{window.content_id}")
        copies[item.id] = dict(id=item.id, source_id=window.content_id, passage_id=window.source_passage_id,
                               group=window.group_index, question=item.question_text,
                               verses={n: verses[n] for n in window.verse_numbers})
    return copies


def publish_copy_reviews(engine, rows, findings):
    retire = {qid for qid, finding in findings.items() if finding["verdict"] == "retire"}
    if not retire:
        return []
    with Session(engine) as db, db.begin():
        if db.get_bind().dialect.name == "postgresql":
            db.execute(select(func.pg_advisory_xact_lock(742908122)))
        pilot.lock_retiring_participants(db, {rows[qid]["group"] for qid in retire}, retire)
        current = related_copies(db, {rows[qid]["source_id"] for qid in retire})
        for qid in sorted(retire):
            item = db.get(QAItem, qid, with_for_update=True)
            if item is not None and item.review_removed_at is not None:
                continue
            row = current.get(qid)
            finding = findings[qid]
            if (row != rows[qid] or item is None or item.question_text != row["question"]
                    or finding["id"] != qid or finding["stem_signature"] != pilot.stem_signature(row)
                    or finding["requested_fact"] != "speech_time" or finding["timing_evidence"] != "dated_content_only"
                    or not finding["stem_quote"] or finding["stem_quote"] not in row["question"]
                    or not finding["quote"] or not any(finding["quote"] in verse for verse in row["verses"].values())):
                raise ValueError(f"Retirement evidence does not match the current pilot copy {qid}")
            # Archive the item in place so its recorded answers retain their window.
            pilot.remove_qa_item_from_review(item)
        pilot.skip_unanswered_retired(db, retire)
    return sorted(retire)


def publish(engine, findings, selected):
    # Hold a stable lock across atomic file replacement. The roster is durable intent:
    # a retry or a normal bank import completes a DB transaction interrupted after the write.
    directory = os.open(pilot.SOL_BANK, os.O_RDONLY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        with Session(engine) as db, db.begin():
            if db.get_bind().dialect.name == "postgresql":
                db.execute(select(func.pg_advisory_xact_lock(742908122)))
            pilot.load_bank(pilot.SOL_SET)
            rows = json.loads((pilot.SOL_BANK / "zh.json").read_text())
            path = pilot.SOL_BANK / "pilot_review.json"
            roster = json.loads(path.read_text())
            updated = apply_decisions(roster, rows, findings)
            retires = {r["id"] for r in updated if r["id"] in selected and r.get("retired_from_pilot")}
            eligible = {r["id"] for r in updated if r["status"] == "eligible"}
            before = live_windows(db)
            if set(before) - retires != eligible:
                raise ValueError("Live delivery roster differs outside the requested retirements")
            if updated != roster:
                original_mode = stat.S_IMODE(path.stat().st_mode)
                save(path, updated)
                path.chmod(original_mode)
            if retires:
                pilot.install(db, pilot.load_bank(pilot.SOL_SET), qa_set=pilot.SOL_SET, apply=True)
            expected = {cid: value for cid, value in before.items() if cid not in retires}
            if live_windows(db) != expected:
                raise ValueError("Unexpected change in pilot delivery windows")
        with Session(engine) as db:
            if live_windows(db) != expected:
                raise ValueError("Post-publication verification failed")
        return {"retired": sorted(retires), "live_questions": len(expected)}
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-id", action="append", help="Scope this run to a source ID. Default: all eligible items.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Publish retire verdicts to the release and live pilot.")
    parser.add_argument("--check-copies", action="store_true",
                        help="Preview related live copies using their own passages. Automatic with --apply.")
    parser.add_argument("--local", action="store_true", help="Use the local Ollama service.")
    parser.add_argument("--model", help="Default: gpt-6-astra, or qwen3:8b with --local.")
    args = parser.parse_args()
    rows = pilot.load_bank(pilot.SOL_SET)
    roster = json.loads((pilot.SOL_BANK / "pilot_review.json").read_text())
    previous = {r["id"]: r["grounding_review"] for r in roster if r.get("grounding_review")}
    available = {r["id"] for r in rows} | previous.keys()
    selected = set(args.item_id) if args.item_id else available
    if selected - available:
        parser.error("Unknown or unreleased item ID")
    model = args.model or ("qwen3:8b" if args.local else "gpt-6-astra")
    settings = {"base_url": "http://127.0.0.1:11434/v1", "api_key": "ollama"} if args.local else {}
    review_rows = [r for r in rows if r["id"] in selected]
    findings = {}
    if review_rows:
        findings = collect(review_rows, OpenAI(timeout=180, **settings), model, args.output)
    report = {"findings": {**{cid: previous[cid] for cid in selected & previous.keys()}, **findings}}
    retired_sources = {cid for cid, decision in report["findings"].items() if decision["verdict"] == "retire"}
    engine = create_engine(pilot.get_database_url()) if args.apply or args.check_copies else None
    copies, copy_findings = {}, {}
    if engine is not None and retired_sources:
        with Session(engine) as db:
            copies = related_copies(db, retired_sources)
        if copies:
            copy_findings = collect(copies.values(), OpenAI(timeout=180, **settings), model, args.output)
        report["related_copies"] = [
            {**row, "finding": copy_findings[qid]} for qid, row in copies.items()
        ]
    if args.apply:
        report["publication"] = publish(engine, findings, selected)
        report["publication"]["retired_related_copies"] = publish_copy_reviews(engine, copies, copy_findings)
    save(args.output / ("publication.json" if args.apply else "review.json"), report)
    for cid, finding in findings.items():
        print(cid, finding["verdict"], finding["reason"])
    if args.apply:
        print(report["publication"])


if __name__ == "__main__":
    main()
