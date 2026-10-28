#!/usr/bin/env python3
"""Generate a separately audited grammar condition affecting every sentence.

Sentences end at 。！？.!?; a sentence crossing verse boundaries is split into
verse-bounded fragments. Every content-bearing fragment needs an approved edit.
100% means all sentence units contain an error, not all characters are changed.
Only complete passages are exported as grammar/100%; incomplete work remains a
clearly labelled draft. Cached proposals and judgments make reruns resumable.
Prefer multiple disruptions; accept a single clear structural error as fallback
when further disruption is unsafe or infeasible. Meaning checks still apply.
"""

from __future__ import annotations

import argparse
import fcntl
import html
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.variants.current import create_grammar_variants as grammar
from evaluation.scripts.variants.current import sentence_retry


def sentence_audit(text: str, bank: dict) -> dict:
    grammar.validate_grammar_bank(text, bank)
    if bank["spec"].get("unit_mode") != "sentence":
        raise grammar.GrammarError("Every-sentence export requires a sentence bank.")
    edits = {entry["unit_index"]: entry for entry in bank["entries"]}
    rows = []
    for index, unit in enumerate(grammar.passage_units(text, unit_mode="sentence")):
        if not unit["affectable"]:
            continue
        edit = edits.get(index)
        rows.append({
            "sentence_number": len(rows) + 1, "unit_index": index,
            "verse": unit["verse"], "boundary": unit["boundary"],
            "original": unit["text"],
            "edited": edit["corrupted_text"] if edit else None,
            "status": "approved" if edit else "unresolved",
            "grammar_judgment": edit["judgment"] if edit else None,
            "meaning_review": edit["meaning_review"] if edit else None,
        })
    approved = sum(row["status"] == "approved" for row in rows)
    return {
        "definition": __doc__, "source_sha256": grammar.json_digest(text),
        "bank_id": bank["bank_id"], "total_sentence_units": len(rows),
        "approved_sentence_units": approved,
        "sentence_coverage": approved / len(rows) if rows else 0,
        "complete": bool(rows) and approved == len(rows), "sentences": rows,
    }


def write_review(output: Path, reports: dict) -> None:
    pieces = ["<!doctype html><meta charset='utf-8'><title>Every-sentence grammar review</title>",
              "<style>body{max-width:1100px;margin:40px auto;font:17px/1.7 system-ui;padding:0 20px}"
              "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:12px;"
              "vertical-align:top;white-space:pre-wrap}details{margin:18px 0}.missing{color:#a21}</style>",
              "<h1>Every-sentence grammar review</h1><p>Every sentence, including quoted speech, "
              "requires an approved structural error. Sentences spanning verses are checked as "
              "separate fragments. Unresolved sentences are never counted as changed. "
              "All words and meaning must be preserved; 100% refers to sentence coverage.</p>"]
    seen = set()
    for filename, report in reports.items():
        if report["source_sha256"] in seen:
            continue
        seen.add(report["source_sha256"])
        pieces.append(f"<h2>{html.escape(filename)}: {report['approved_sentence_units']}/"
                      f"{report['total_sentence_units']} approved</h2>")
        for row in report["sentences"]:
            pieces.append(f"<details open><summary>Sentence {row['sentence_number']} · verse "
                          f"{row['verse']} · {row['status']}</summary><table>"
                          "<tr><th>Clean</th><th>Grammar variant</th></tr><tr>"
                          f"<td>{html.escape(row['original'])}</td>"
                          f"<td>{html.escape(row['edited'] or 'UNRESOLVED — no approved edit')}</td>"
                          "</tr></table>")
            if row["grammar_judgment"]:
                pieces.append("<p>" + html.escape(row["grammar_judgment"]["explanation"]) + "</p>")
            pieces.append("</details>")
    grammar.write_text(output / "sentence_review.html", "\n".join(pieces))


def build_passage(args, passage: str) -> dict:
    source_model = args.source_root / passage / "_base"
    source = source_model / "llm_prompt_high"
    output = args.output_root / passage / "grammar"
    bank_dir = output / "_grammar_bank"
    state_path = output / "progress.json"
    state = {"passage": passage, "status": "running", "started_at": time.time()}
    grammar.write_json_atomic(state_path, state)
    try:
        seed = args.seed + grammar.seed_offset(passage)
        judgments = grammar.GrammarJudgmentCache(
            bank_dir / "judgments.json", model=args.judge_model, offline=args.offline,
            unit_mode="sentence")
        proposals = grammar.GrammarProposalCache(
            bank_dir / "proposals.json", model=args.generator_model, offline=args.offline,
            unit_mode="sentence")
        meaning = grammar.GrammarMeaningCache(bank_dir, model=args.judge_model, offline=args.offline)
        banks, reports = {}, {}
        for filename in ("passage_target.txt", "passage_target_decanonicalized.txt"):
            path = source / filename
            if filename != "passage_target.txt" and not path.exists():
                continue
            text = grammar.load_text(path)
            preserved_bank, historical_attempts = None, None
            if args.resume_from:
                preserved_bank, historical_attempts = sentence_retry.load_retry_seed(
                    text, args.output_root / "_resume_snapshot", passage)
                print(f"{passage}: preserving {len(preserved_bank['entries'])} approved sentence edits", flush=True)
            bank = grammar.build_grammar_bank(
                text, bank_dir=bank_dir, seed=seed, max_rate=1.0,
                cache=judgments, proposal_cache=proposals, meaning_cache=meaning,
                max_candidates=args.candidates, proposal_batch_size=args.batch_size,
                retry_rounds=args.retry_rounds, unit_mode="sentence",
                preserved_bank=preserved_bank, historical_attempts=historical_attempts,
            )
            banks[filename] = bank
            reports[filename] = sentence_audit(text, bank)
            draft, _ = grammar.apply_grammar_bank(text, rate=1.0, seed=seed, bank=bank)
            grammar.write_text(output / ("draft_" + filename), draft)
        grammar.write_json_atomic(output / "sentence_review.json", {"files": reports})
        write_review(output, reports)
        complete = all(report["complete"] for report in reports.values())
        if complete:
            grammar.copy_shared_files(source_model / "_shared", output / "_shared")
            grammar.create_variant(source_method_dir=source, output_dir=output,
                                   rate=1.0, seed=seed, force=False, banks=banks)
        state.update(status="complete" if complete else "incomplete", files={
            name: {key: value for key, value in report.items() if key != "sentences"}
            for name, report in reports.items()
        })
    except Exception as exc:
        state.update(status="error", error=f"{type(exc).__name__}: {exc}")
    state["finished_at"] = time.time()
    grammar.write_json_atomic(state_path, state)
    print(f"{passage}: {state['status']}", flush=True)
    return state


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path,
                        help="Preserve approved sentences from this prior run; retry unresolved units only.")
    parser.add_argument("--passage-dirs", nargs="+")
    parser.add_argument("--generator-model", default="gpt-6.1-sol")
    parser.add_argument("--judge-model", default="gpt-6.1-sol")
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--retry-rounds", type=int, default=4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    if min(args.candidates, args.batch_size, args.workers) < 1 or args.retry_rounds < 0:
        parser.error("Counts must be positive and retry rounds nonnegative.")
    args.source_root = args.source_root.resolve()
    args.output_root = args.output_root.resolve()
    if args.resume_from:
        args.resume_from = args.resume_from.resolve()
        if args.output_root == args.resume_from or args.output_root.is_relative_to(args.resume_from):
            parser.error("Use a separate output root outside the run being resumed.")
    if args.source_root == args.output_root:
        parser.error("Use a separate output root to preserve existing experiments.")
    return args


def main(argv=None):
    args = parse_args(argv)
    passages = args.passage_dirs or sorted(
        p.name for p in args.source_root.glob("t1_*")
        if (p / "_base/llm_prompt_high/passage_target.txt").is_file())
    if not passages or len(set(passages)) != len(passages) or any(Path(p).name != p for p in passages):
        raise grammar.GrammarError("Select unique passage directory names with clean sources.")
    args.output_root.mkdir(parents=True, exist_ok=True)
    with (args.output_root / ".generation.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume_from:
            snapshot = args.output_root / "_resume_snapshot"
            if not snapshot.exists():
                # Hold the source lock only while freezing its durable results.
                with (args.resume_from / ".generation.lock").open("r") as source_lock:
                    fcntl.flock(source_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    staging = args.output_root / "_resume_snapshot.tmp"
                    shutil.copytree(args.resume_from, staging, dirs_exist_ok=True)
                    grammar.write_json_atomic(staging / "retry_source.json", {"path": str(args.resume_from)})
                    staging.rename(snapshot)
            if grammar.read_json_object(snapshot / "retry_source.json")["path"] != str(args.resume_from):
                raise grammar.GrammarError("Output directory belongs to a different retry source.")
        state = {"status": "running", "started_at": time.time(),
                 "configuration": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                 "passages": passages, "results": {}}
        grammar.write_json_atomic(args.output_root / "run_state.json", state)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            tasks = {pool.submit(build_passage, args, passage): passage for passage in passages}
            for task in as_completed(tasks):
                passage = tasks[task]
                state["results"][passage] = task.result()
                grammar.write_json_atomic(args.output_root / "run_state.json", state)
        state["status"] = "complete" if all(
            result["status"] == "complete" for result in state["results"].values()) else "incomplete"
        state["finished_at"] = time.time()
        grammar.write_json_atomic(args.output_root / "run_state.json", state)
        return 0 if state["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
