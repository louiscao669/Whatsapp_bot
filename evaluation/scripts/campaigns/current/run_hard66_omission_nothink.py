#!/usr/bin/env python3
"""Evaluate saved Hard66 defect levels with Qwen3 1.7B, thinking disabled.

Defaults to omission; --family selects another saved defect arm.
--variant-source permits positive levels from a separate, verified campaign.
--reuse-clean-from imports a verified, identical no-thinking clean baseline.
"""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.campaigns.current import run_overnight_ladder as ladder
from evaluation.scripts.campaigns.current.run_hard66_full_ladder import save_input
from evaluation.scripts.campaigns.current.run_hard66_grammar import verify_hashes

MODEL = "qwen3:1.7b"
RATES = [0, 5, 10, 15, 20, 25, 30]
INFERENCE = {"model": MODEL, "think": False, "temperature": 0,
             "num_ctx": 8192, "num_predict": 2500, "timeout_seconds": 150}


def conditions(family):
    if family == "google_word_by_word":
        return [("clean", "clean", "omission/0%"), (family, "wbw", family)]
    return [(rate, "clean" if rate == 0 else family,
             f"{'omission' if rate == 0 else family}/{rate}%") for rate in RATES]


def prepare(source, root, *, family="omission", variant_source=None):
    from evaluation.agents.generate_chinese_answers import (
        chapters_from_reference, index_passage_verses, public_questions,
        curated_window_for_item, local_passage_for_question, load_verse_windows,
    )
    previous = ladder.read(source / "release.json")
    verify_hashes(source, previous["input_hashes"])
    if variant_source is not None:
        variants = ladder.read(variant_source / "release.json")
        verify_hashes(variant_source, variants["input_hashes"])
        for path in (source / "_inputs").rglob("*"):
            if path.is_file() and path.read_bytes() != (variant_source / path.relative_to(source)).read_bytes():
                raise ValueError(f"Variant campaign has different QA/windows/source: {path}")
        for pid in ladder.PASSAGES:
            relatives = [Path(pid) / "_base/llm_prompt_high" / name for name in ladder.TEXTS]
            relatives += [Path(pid) / "_base/_shared" / f"{pid}_base_{suffix}"
                          for suffix in ["qa_zh.json", "qa_zh_decanonicalized.json"]]
            for relative in relatives:
                if (source / relative).read_bytes() != (variant_source / relative).read_bytes():
                    raise ValueError(f"Variant campaign has different baseline: {relative}")
    windows = load_verse_windows(source / "_inputs/windows.json")
    cells, counts, window_checks = [], {}, 0
    for pid in ladder.PASSAGES:
        shared = source / pid / "_base/_shared"
        for suffix in ["qa_zh.json", "qa_zh_decanonicalized.json"]:
            name = f"{pid}_base_{suffix}"
            rows = [row for row in ladder.read(shared / name) if row["q_type"] == "mcq"]
            save_input(root / pid / "_base/_shared" / name, rows)
        rows = ladder.read(root / pid / "_base/_shared" / f"{pid}_base_qa_zh_decanonicalized.json")
        questions = public_questions(rows)
        counts[pid] = len(questions)
        for level, stage, method in conditions(family):
            directory = (source if stage == "clean" or variant_source is None else variant_source) / pid / method
            for name in ladder.ARTIFACTS:
                if name in ["qa_target.json", "qa_target_decanonicalized.json"]:
                    save_input(root / pid / method / name, rows)
                else:
                    ladder.snapshot(directory / name, root / pid / method / name)
            metadata_name = f"{'omission' if stage == 'clean' else family}_metadata.json"
            if (directory / metadata_name).exists():
                ladder.snapshot(directory / metadata_name, root / pid / method / metadata_name)
            text = (root / pid / method / ladder.TEXTS[1]).read_text()
            index, order = index_passage_verses(text, chapters_from_reference(rows[0]["passage_reference"]))
            for question in questions:
                keys = curated_window_for_item(windows, question)
                expected = "\n".join(index[k] for k in keys if k in index).strip() if keys else ""
                actual = local_passage_for_question("UNEXPECTED FULL PASSAGE", index, question, 2, order, windows)
                if not expected or actual != expected:
                    raise ValueError(f"Invalid answer window: {pid}/{method}/{question['id']}")
                window_checks += 1
    for path in (source / "_inputs").rglob("*"):
        if path.is_file():
            ladder.snapshot(path, root / path.relative_to(source))
    cells = [[stage, MODEL, pid, method]
             for level, stage, method in conditions(family) for pid in ladder.PASSAGES]
    directories = [root / "_inputs"] + [root / pid / part for pid in ladder.PASSAGES
                                        for part in dict.fromkeys(["_base", "omission", family])]
    manifest = {"source_evaluation": str(source), "qa_set": "hard66_canonical_reviewed",
                "qa_formats": ["mcq"], "inference": INFERENCE, "rates": RATES,
                "passages": list(ladder.PASSAGES), "cells": cells, "total_cells": len(cells),
                "questions_per_level": sum(counts.values()), "total_responses": len(conditions(family)) * sum(counts.values()),
                "window_checks": window_checks,
                "input_hashes": {str(p.relative_to(root)): ladder.fingerprint(p)
                                 for directory in directories for p in directory.rglob("*") if p.is_file()}}
    if family != "omission":
        manifest["condition_family"] = family
    if family == "google_word_by_word":
        manifest.pop("rates")
        manifest["conditions"] = [level for level, stage, method in conditions(family)]
    if variant_source is not None:
        manifest["variant_source"] = str(variant_source)
    save_input(root / "release.json", manifest)
    return manifest


def summarize(root, manifest):
    state = ladder.read(root / "campaign_state.json")
    family = manifest.get("condition_family", "omission")
    summaries = []
    for level, stage, method in conditions(family):
        rows, answers = [], []
        for pid in manifest["passages"]:
            directory = root / pid / "qwen317b_nothink" / method
            qa = ladder.read(root / pid / "_base/_shared" / f"{pid}_base_qa_zh_decanonicalized.json")
            expected = {(q["id"], "mcq") for q in qa}
            verified = ladder.verify_cell(directory, expected, no_think=True)
            key = f"{stage}/{MODEL}/{pid}/{method}"
            if verified["result_hashes"] != state["cells"][key]["result_hashes"]:
                raise ValueError(f"Results changed: {key}")
            for name in ladder.TEXTS:
                if (directory / name).read_bytes() != (root / pid / method / name).read_bytes():
                    raise ValueError(f"Input changed: {key}/{name}")
            scores = ladder.read(directory / "scores_target_llama.json")["items"]
            gold = {q["id"]: q["correct"] for q in qa}
            for row in scores:
                if row["correct_choice"] != gold[row["id"]] or row["direct_correct"] != (row["selected_choice"] == row["correct_choice"]):
                    raise ValueError(f"MCQ answer key mismatch: {row['id']}")
            rows.extend(scores)
            answers.extend(ladder.read(directory / "generated_answers_target_llama.json"))
        if len(rows) != manifest["questions_per_level"] or len({r["id"] for r in rows}) != len(rows):
            raise ValueError(f"Missing or duplicate MCQ rows at {level}")
        level_field = {"condition": level} if family == "google_word_by_word" else {f"nominal_{family}_percent": level}
        summaries.append({"model": MODEL, "thinking_enabled": False, **level_field,
                          "correct": sum(r["direct_correct"] for r in rows), "n": len(rows),
                          "accuracy_percent": 100 * sum(r["direct_correct"] for r in rows) / len(rows),
                          "thinking_chars": sum(r["answer_effort"]["thinking_chars"] for r in answers),
                          "generation_errors": sum(bool(r.get("generation_error")) for r in answers),
                          "truncated_answers": sum(r["answer_effort"].get("done_reason") == "length" for r in answers)})
    verify_hashes(root, manifest["input_hashes"])
    ladder.write_atomic(root / "results_summary.json", {"status": "complete", "levels": summaries,
                                                       "input_and_result_hashes_verified": True})
    return summaries


def reuse_clean(previous, root, manifest):
    old_manifest = ladder.read(previous / "release.json")
    if old_manifest["inference"] != manifest["inference"] or old_manifest["qa_formats"] != ["mcq"]:
        raise ValueError("Clean baseline has different inference settings or question formats")
    verify_hashes(previous, old_manifest["input_hashes"])
    for path in (root / "_inputs").rglob("*"):
        if path.is_file() and path.read_bytes() != (previous / path.relative_to(root)).read_bytes():
            raise ValueError(f"Clean baseline has different QA/windows/source: {path}")
    old_state = ladder.read(previous / "campaign_state.json")
    if old_state.get("no_think") is not True:
        raise ValueError("Clean baseline was not run with thinking disabled")
    state_path = root / "campaign_state.json"
    state = ladder.read(state_path) if state_path.exists() else {"status": "prepared", "cells": {}, "no_think": True}
    reused = []
    for stage, model, pid, method in manifest["cells"]:
        if stage != "clean":
            continue
        key = f"{stage}/{model}/{pid}/{method}"
        saved = old_state["cells"].get(key, {})
        if saved.get("status") != "complete":
            raise ValueError(f"Clean baseline not complete: {pid}")
        old = previous / pid / "qwen317b_nothink" / method
        target = root / pid / "qwen317b_nothink" / method
        for name in ladder.ARTIFACTS:
            path = root / pid / method / name
            if path.read_bytes() != (old / name).read_bytes():
                raise ValueError(f"Clean baseline input differs: {pid}/{name}")
            ladder.snapshot(path, target / name)
        qa = ladder.read(root / pid / method / "qa_target_decanonicalized.json")
        expected = {(r["id"], "mcq") for r in qa}
        if ladder.verify_cell(old, expected, no_think=True)["result_hashes"] != saved["result_hashes"]:
            raise ValueError(f"Clean baseline results changed: {pid}")
        for name in ladder.RESULTS:
            ladder.snapshot(old / name, target / name)
        checked = ladder.verify_cell(target, expected, no_think=True)
        if key not in state["cells"]:
            state["cells"][key] = {**saved, **checked, "reused_from": str(old)}
        elif state["cells"][key]["result_hashes"] != checked["result_hashes"]:
            raise ValueError(f"Existing clean result differs: {pid}")
        reused.append(key)
    state.update(total_cells=manifest["total_cells"],
                 completed_cells=sum(c.get("status") == "complete" for c in state["cells"].values()))
    ladder.write_atomic(state_path, state)
    save_input(root / "reused_clean.json", {"source": str(previous), "cells": reused})
    print(f"Reused {len(reused)} verified clean passage cells", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO / "evaluation/runs/hard66_full_ladder_2026-10-23")
    parser.add_argument("--family", choices=["omission", "mistranslation", "grammar", "google_word_by_word"], default="omission")
    parser.add_argument("--variant-source", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--reuse-clean-from", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    variant_source = args.variant_source.resolve() if args.variant_source else None
    root = (args.run_root or REPO / f"evaluation/runs/hard66_{args.family}_mcq_qwen317b_nothink_2026-10-26").resolve()
    if any(root == parent or root.is_relative_to(parent) for parent in [source, variant_source] if parent is not None):
        raise ValueError("Use a separate output directory")
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "run.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ["QA_FORMATS"] = "mcq"
    manifest = prepare(source, root, family=args.family, variant_source=variant_source)
    if args.reuse_clean_from:
        reuse_clean(args.reuse_clean_from.resolve(), root, manifest)
    print(f"Verified {manifest['total_cells']} passage/level cells and {manifest['total_responses']} MCQ responses", flush=True)
    if args.prepare_only:
        return
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
    os.environ.update(QA_FORMATS="mcq", MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E", MCQ_KEEP_THINKING="1",
                      OLLAMA_NUM_CTX=str(INFERENCE["num_ctx"]), OLLAMA_NUM_PREDICT=str(INFERENCE["num_predict"]),
                      OLLAMA_TIMEOUT=str(INFERENCE["timeout_seconds"]))
    job = {"status": "running", "pid": os.getpid(), "started_at": time.time(), **INFERENCE}
    ladder.write_atomic(root / "job.json", job)
    caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-is", "-w", str(os.getpid())]) if sys.platform == "darwin" else None
    try:
        ladder.evaluate(root, selected_cells=[tuple(c) for c in manifest["cells"]], no_think=True)
        if ladder.read(root / "campaign_state.json")["status"] != "complete":
            raise RuntimeError(f"Some {args.family} levels did not complete")
        for summary in summarize(root, manifest):
            label = summary["condition"] if "condition" in summary else f"{summary[f'nominal_{args.family}_percent']}%"
            print(f"{label}: {summary['correct']}/{summary['n']}", flush=True)
        job.update(status="complete", finished_at=time.time())
    except Exception as exc:
        job.update(status="failed", error=str(exc), finished_at=time.time())
        raise
    finally:
        ladder.write_atomic(root / "job.json", job)
        if caffeinate:
            caffeinate.terminate()


if __name__ == "__main__":
    main()
