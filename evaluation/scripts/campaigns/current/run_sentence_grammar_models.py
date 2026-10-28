#!/usr/bin/env python3
"""Run saved sentence-defect MCQs on 1B, 1.5B, then Qwen3 1.7B with thinking."""
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

MODEL_ORDER = ["llama3.2:1b", "qwen2.5:1.5b", "qwen3:1.7b"]


def prepare(source, root):
    release = ladder.read(source / "release.json")
    verify_hashes(source, release["input_hashes"])
    if release.get("qa_formats") != ["mcq"] or set(release["passages"]) != set(ladder.PASSAGES):
        raise ValueError("Source must contain the reviewed MCQ arm for every passage")
    stages = []
    for model in MODEL_ORDER:
        name = model.replace(":", "").replace(".", "")
        directory = root / name
        for filename in release["input_hashes"]:
            ladder.snapshot(source / filename, directory / filename)
        manifest = {**release, "source_evaluation": str(source),
                    "inference": {**release["inference"], "model": model,
                                  "think": True if model == "qwen3:1.7b" else None,
                                  "mode": "thinking" if model == "qwen3:1.7b" else "standard"},
                    "cells": [[stage, model, pid, method] for stage, _, pid, method in release["cells"]]}
        save_input(directory / "release.json", manifest)
        stages.append({"model": model, "run_root": str(directory),
                       "responses": manifest["total_responses"], "inference": manifest["inference"]})
    plan = {"source_evaluation": str(source), "model_order": MODEL_ORDER,
            "stages": stages, "total_responses": sum(s["responses"] for s in stages),
            "coverage": release["coverage"], "qa_formats": ["mcq"]}
    save_input(root / "plan.json", plan)
    return plan


def summarize(root, manifest):
    answers, scores, passages = [], [], []
    model = manifest["inference"]["model"]
    slug = model.replace(":", "").replace(".", "") + "_think"
    state = ladder.read(root / "campaign_state.json")
    for stage, _, pid, method in manifest["cells"]:
        directory = root / pid / slug / method
        qa = ladder.read(root / pid / "_base/_shared" / f"{pid}_base_qa_zh_decanonicalized.json")
        expected = {(q["id"], q["q_type"]) for q in qa}
        checked = ladder.verify_cell(directory, expected)
        if checked["result_hashes"] != state["cells"][f"{stage}/{model}/{pid}/{method}"]["result_hashes"]:
            raise ValueError(f"Completed results changed: {pid}")
        rows = ladder.read(directory / "generated_answers_target_llama.json")
        scored = ladder.read(directory / "scores_target_llama.json")["items"]
        gold = {q["id"]: q["correct"] for q in qa}
        for row in scored:
            if row["q_type"] != "mcq" or row["correct_choice"] != gold[row["id"]] or row["direct_correct"] != (
                row["selected_choice"] == row["correct_choice"]
            ):
                raise ValueError(f"MCQ scoring differs from reviewed answer key: {row['id']}")
        for filename in ladder.TEXTS:
            if (directory / filename).read_bytes() != (root / pid / method / filename).read_bytes():
                raise ValueError(f"Model input changed: {pid}/{filename}")
        answers.extend(rows)
        scores.extend(scored)
        passages.append({"passage": pid, **manifest["coverage"][pid],
                         "correct": sum(r["direct_correct"] for r in scored), "total": len(scored)})
    thinking = [r.get("answer_effort", {}).get("thinking_chars") for r in answers]
    if model == "qwen3:1.7b" and not any(isinstance(n, int) and n > 0 for n in thinking):
        raise ValueError("Qwen3 returned no thinking output; requested mode was not verified")
    summary = {"model": model, "mode": manifest["inference"]["mode"],
               "correct": sum(r["direct_correct"] for r in scores), "total": len(scores),
               "accuracy": sum(r["direct_correct"] for r in scores) / len(scores),
               "generation_errors": sum(bool(r.get("generation_error")) for r in answers),
               "responses_with_thinking": sum(isinstance(n, int) and n > 0 for n in thinking),
               "thinking_chars": sum(n for n in thinking if isinstance(n, int)),
               "missing_effort_records": sum(n is None for n in thinking),
               "truncated_answers": sum(r.get("answer_effort", {}).get("done_reason") == "length" for r in answers),
               "passages": passages, "input_and_result_hashes_verified": True}
    verify_hashes(root, manifest["input_hashes"])
    ladder.write_atomic(root / "results_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO / "evaluation/runs/hard66_grammar_sentence_all_mcq_qwen317b_nothink_2026-10-25")
    parser.add_argument("--run-root", type=Path, default=REPO / "evaluation/runs/hard66_grammar_sentence_all_mcq_models_2026-10-25")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root, source = args.run_root.resolve(), args.source.resolve()
    if root == source or root.is_relative_to(source):
        raise ValueError("Use a separate output root")
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "run.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = prepare(source, root)
    print(f"Prepared {plan['total_responses']} responses in model order: {', '.join(MODEL_ORDER)}", flush=True)
    if args.prepare_only:
        return
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
    os.environ.update(QA_FORMATS="mcq", MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E", MCQ_KEEP_THINKING="1")
    job = {"status": "running", "pid": os.getpid(), "started_at": time.time(), "models": {}}
    ladder.write_atomic(root / "job.json", job)
    caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-is", "-w", str(os.getpid())]) if sys.platform == "darwin" else None
    summaries = []
    try:
        for stage in plan["stages"]:
            directory = Path(stage["run_root"])
            model = stage["model"]
            inference = stage["inference"]
            os.environ.update(OLLAMA_NUM_CTX=str(inference["num_ctx"]),
                              OLLAMA_NUM_PREDICT=str(inference["num_predict"]),
                              OLLAMA_TIMEOUT=str(inference["timeout_seconds"]))
            job["current_model"] = model
            job["models"][model] = {"status": "running", "started_at": time.time()}
            ladder.write_atomic(root / "job.json", job)
            manifest = ladder.read(directory / "release.json")
            ladder.evaluate(directory, selected_cells=[tuple(c) for c in manifest["cells"]])
            if ladder.read(directory / "campaign_state.json")["status"] != "complete":
                raise RuntimeError(f"{model} did not finish; remaining models have not started")
            summary = summarize(directory, manifest)
            summaries.append(summary)
            job["models"][model].update(status="complete", finished_at=time.time(),
                                        correct=summary["correct"], total=summary["total"])
            ladder.write_atomic(root / "job.json", job)
            print(f"COMPLETE {model}: {summary['correct']}/{summary['total']}", flush=True)
        ladder.write_atomic(root / "results_summary.json", {"models": summaries, "coverage": plan["coverage"]})
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
