#!/usr/bin/env python3
"""Evaluate a verified grammar release with the previous Hard66 questions/windows.

Inputs and results live in a separate resumable directory. Missing levels require
--available-only; the exact omissions are recorded in the release manifest.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.campaigns.current import run_overnight_ladder as ladder
from evaluation.scripts.campaigns.current.run_hard66_full_ladder import save_input

DEFAULT_GRAMMAR = REPO / "evaluation/runs/grammar_0_30_2026-10-24"
DEFAULT_PREVIOUS = REPO / "evaluation/runs/hard66_full_ladder_2026-10-23"
DEFAULT_RUN = REPO / "evaluation/runs/hard66_grammar_2026-10-24"
RATES = [5, 10, 15, 20, 25, 30]


def select_variants(source: Path, available_only: bool):
    present, missing = [], []
    for pid in ladder.PASSAGES:
        for rate in RATES:
            method = f"grammar/{rate}%"
            (present if (source / pid / method / ladder.TEXTS[1]).is_file() else missing).append((pid, method))
    if missing and not available_only:
        raise ValueError(f"Missing grammar levels: {missing}. Use --available-only to explicitly omit them.")
    if not present:
        raise ValueError("No grammar variants are available")
    return present, missing


def verify_hashes(root, hashes):
    for name, expected in hashes.items():
        if ladder.fingerprint(root / name) != expected:
            raise ValueError(f"Input changed: {root / name}")


def prepare(source: Path, previous: Path, root: Path, available_only=False):
    from evaluation.agents.generate_chinese_answers import (
        chapters_from_reference, index_passage_verses, public_questions,
        curated_window_for_item, local_passage_for_question, load_verse_windows,
    )
    if root in (source, previous):
        raise ValueError("Grammar evaluation needs its own output directory")
    verified = ladder.read(source / "verification.json")
    if not verified["ready"] or verified["verified_passages"] != len(ladder.PASSAGES):
        raise ValueError("Grammar build verification did not pass for every passage")
    verify_hashes(source, verified["output_hashes"])
    verify_hashes(previous, ladder.read(previous / "release.json")["input_hashes"])
    variants, missing = select_variants(source, available_only)
    cells = [("grammar", model, pid, method) for model in ladder.MODELS for pid, method in variants]
    windows = load_verse_windows(previous / "_inputs/windows.json")
    counts, coverage, window_checks = {}, [], 0
    for pid in ladder.PASSAGES:
        base = "_base/llm_prompt_high"
        for name in ladder.TEXTS:
            if (source / pid / base / name).read_bytes() != (previous / pid / base / name).read_bytes():
                raise ValueError(f"Clean sources differ: {pid}/{name}")
        for method in [base, "_base/_shared"]:
            for path in (previous / pid / method).iterdir():
                if path.is_file():
                    ladder.snapshot(path, root / pid / method / path.name)
        rows = ladder.read(previous / pid / "_base/_shared" / f"{pid}_base_qa_zh_decanonicalized.json")
        questions = public_questions(rows)
        counts[pid] = len(questions)
        chapters = chapters_from_reference(rows[0]["passage_reference"])
        for _, method in (v for v in variants if v[0] == pid):
            directory = source / pid / method
            for path in directory.iterdir():
                if path.is_file() and path.name not in ["qa_target.json", "qa_target_decanonicalized.json"] and (
                    path.name in ladder.ARTIFACTS or path.name.endswith("_metadata.json")
                ):
                    ladder.snapshot(path, root / pid / method / path.name)
            for name in ["qa_target.json", "qa_target_decanonicalized.json"]:
                save_input(root / pid / method / name, rows)
            text = (root / pid / method / ladder.TEXTS[1]).read_text()
            index, order = index_passage_verses(text, chapters)
            for question in questions:
                keys = curated_window_for_item(windows, question)
                if not keys:
                    raise ValueError(f"Missing Hard66 window: {question['id']}")
                expected = "\n".join(index[k] for k in keys if k in index).strip()
                actual = local_passage_for_question("UNEXPECTED FULL PASSAGE", index, question, 2, order, windows)
                if not expected or actual != expected:
                    raise ValueError(f"Bad answer window: {pid}/{method}/{question['id']}")
                window_checks += 1
            meta = ladder.read(directory / "grammar_metadata.json")
            coverage.append({"passage": pid, "method": method,
                             "actual_affected_rate": meta["files"]["passage_target"]["actual_affected_rate"]})
    for path in (previous / "_inputs").rglob("*"):
        if path.is_file():
            ladder.snapshot(path, root / path.relative_to(previous))
    input_hashes = {}
    for directory in [root / "_inputs", *[root / p / "_base" for p in ladder.PASSAGES],
                      *[root / p / m for p, m in variants]]:
        for path in directory.rglob("*"):
            if path.is_file():
                input_hashes[str(path.relative_to(root))] = ladder.fingerprint(path)
    manifest = {"qa_set": "hard66_canonical_reviewed", "grammar_source": str(source),
                "previous_run": str(previous), "clean_baseline": "reuse previous completed clean results",
                "grammar_selection_plan": verified.get("level_plan"),
                "grammar_verification_sha256": ladder.fingerprint(source / "verification.json"),
                "models": ladder.MODELS, "variants": variants, "missing_variants": missing,
                "cells": cells, "total_cells": len(cells),
                "total_responses": sum(counts[p] for _, _, p, _ in cells),
                "question_forms": sum(counts.values()), "window_checks": window_checks,
                "coverage": coverage, "input_hashes": input_hashes}
    save_input(root / "release.json", manifest)
    print(json.dumps({k: manifest[k] for k in ["total_cells", "total_responses", "question_forms", "missing_variants", "window_checks"]}), flush=True)
    return manifest


def reuse_completed(root: Path, previous: Path, manifest: dict):
    """Reuse only completed cells with identical answer inputs and saved hashes."""
    from evaluation.agents.generate_chinese_answers import load_qa_items, public_questions
    if root == previous:
        raise ValueError("Cannot import results from the destination campaign")
    old_job = ladder.read(previous / "job.json")
    if (old_job.get("num_predict"), old_job.get("timeout_seconds")) != (
        int(os.environ["OLLAMA_NUM_PREDICT"]), float(os.environ["OLLAMA_TIMEOUT"])
    ):
        raise ValueError("Completed results used different inference limits")
    for file in (root / "_inputs").rglob("*"):
        if file.is_file() and ladder.fingerprint(file) != ladder.fingerprint(previous / file.relative_to(root)):
            raise ValueError(f"Completed campaign used different QA/windows/source: {file}")
    old_state = ladder.read(previous / "campaign_state.json")
    state_path = root / "campaign_state.json"
    state = ladder.read(state_path) if state_path.exists() else {
        "status": "prepared", "started_at": time.time(), "cells": {},
    }
    report = {"source": str(previous), "reused": [], "changed_inputs": [], "not_complete": []}
    required = [*ladder.TEXTS, "passage_source_decanonicalized.txt", "qa_target.json", "qa_target_decanonicalized.json"]
    for stage, model, pid, method in manifest["cells"]:
        key = f"{stage}/{model}/{pid}/{method}"
        saved = old_state["cells"].get(key, {})
        if saved.get("status") != "complete":
            report["not_complete"].append(key)
            continue
        slug = model.replace(":", "").replace(".", "") + "_think"
        old, source, destination = previous / pid / slug / method, root / pid / method, root / pid / slug / method
        if any(not (old / name).is_file() or not (source / name).is_file()
               or ladder.fingerprint(old / name) != ladder.fingerprint(source / name) for name in required):
            report["changed_inputs"].append(key)
            continue
        qa = root / pid / "_base/_shared" / f"{pid}_base_qa_zh_decanonicalized.json"
        if qa.read_bytes() != (previous / qa.relative_to(root)).read_bytes():
            raise ValueError(f"Shared QA changed: {pid}")
        expected = {(q.get("id"), q["q_type"]) for q in public_questions(load_qa_items(qa))}
        if ladder.verify_cell(old, expected)["result_hashes"] != saved["result_hashes"]:
            raise ValueError(f"Completed source results changed: {key}")
        if key not in state["cells"]:
            destination.mkdir(parents=True, exist_ok=True)
            for path in source.iterdir():
                if path.is_file() and (path.name in ladder.ARTIFACTS or path.name.endswith("_metadata.json")):
                    ladder.snapshot(path, destination / path.name)
            for name in ladder.RESULTS:
                ladder.snapshot(old / name, destination / name)
            verified = ladder.verify_cell(destination, expected)
            state["cells"][key] = {**saved, **verified, "reused_from": str(old), "imported_at": time.time()}
        report["reused"].append(key)
    state.update(total_cells=manifest["total_cells"],
                 completed_cells=sum(c.get("status") == "complete" for c in state["cells"].values()))
    ladder.write_atomic(state_path, state)
    ladder.write_atomic(root / "reused_results.json", report)
    print(f"REUSED {len(report['reused'])} completed cells; {len(report['changed_inputs'])} changed cells require evaluation", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grammar-source", type=Path, default=DEFAULT_GRAMMAR)
    parser.add_argument("--previous-run", type=Path, default=DEFAULT_PREVIOUS)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--reuse-completed-from", type=Path)
    parser.add_argument("--available-only", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    source, previous, root = (p.resolve() for p in [args.grammar_source, args.previous_run, args.run_root])
    root.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
    os.environ.update(QA_FORMATS="open,mcq", MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E")
    os.environ.setdefault("OLLAMA_NUM_PREDICT", "2500")
    os.environ.setdefault("OLLAMA_TIMEOUT", "150")
    os.environ["MCQ_KEEP_THINKING"] = "1"
    lock = (root / "run.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (root / "release.json").exists():
        manifest = ladder.read(root / "release.json")
        verify_hashes(root, manifest["input_hashes"])
        if manifest["grammar_source"] != str(source) or manifest["previous_run"] != str(previous):
            raise ValueError("Sources differ from this campaign's saved release")
        if manifest["missing_variants"] and not args.available_only:
            raise ValueError("This campaign omits missing variants; resume with --available-only")
    else:
        manifest = prepare(source, previous, root, args.available_only)
    if args.reuse_completed_from:
        reuse_completed(root, args.reuse_completed_from.resolve(), manifest)
    if args.prepare_only:
        return
    if args.background:
        command = [sys.executable, "-u", str(Path(__file__).resolve()),
                   "--grammar-source", str(source), "--previous-run", str(previous), "--run-root", str(root)]
        if args.available_only:
            command.append("--available-only")
        # Transfer the lock to the child before it starts its own validation.
        fcntl.flock(lock, fcntl.LOCK_UN)
        with (root / "grammar_run.log").open("a") as log:
            process = subprocess.Popen(command, cwd=REPO, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps({"pid": process.pid, "log": str(root / "grammar_run.log"),
                          "cells": manifest["total_cells"], "responses": manifest["total_responses"]}), flush=True)
        return
    job = {"status": "running", "pid": os.getpid(), "started_at": time.time(),
           "num_predict": int(os.environ["OLLAMA_NUM_PREDICT"]),
           "timeout_seconds": float(os.environ["OLLAMA_TIMEOUT"]), "keep_thinking": True}
    ladder.write_atomic(root / "job.json", job)
    caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-is", "-w", str(os.getpid())]) if sys.platform == "darwin" else None
    try:
        ladder.evaluate(root, selected_cells=[tuple(c) for c in manifest["cells"]])
        job.update(status=ladder.read(root / "campaign_state.json")["status"], finished_at=time.time())
    except Exception as exc:
        job.update(status="failed", error=str(exc), finished_at=time.time())
        raise
    finally:
        ladder.write_atomic(root / "job.json", job)
        if caffeinate:
            caffeinate.terminate()


if __name__ == "__main__":
    main()
