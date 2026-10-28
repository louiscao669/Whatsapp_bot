#!/usr/bin/env python3
"""Evaluate every-sentence grammar variants with Qwen3 1.7B, thinking off.

Partial variants require --include-partial and retain their measured coverage.
Use --all-passages --qa-formats mcq for the complete MCQ arm.
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
from evaluation.scripts.variants.current import create_grammar_variants as grammar

MODEL = "qwen3:1.7b"
METHOD = "grammar/100%"
INFERENCE = {"model": MODEL, "think": False, "temperature": 0,
             "num_ctx": 8192, "num_predict": 2500, "timeout_seconds": 150}


def prepare(source, previous, root, passages, *, include_partial=False, qa_formats=("open", "mcq")):
    from evaluation.agents.generate_chinese_answers import (
        chapters_from_reference, index_passage_verses, public_questions,
        curated_window_for_item, local_passage_for_question, load_verse_windows,
    )
    if root in (source, previous):
        raise ValueError("Use a separate evaluation output directory")
    verify_hashes(previous, ladder.read(previous / "release.json")["input_hashes"])
    clean_root = Path(ladder.read(source / "run_state.json")["configuration"]["source_root"])
    windows = load_verse_windows(previous / "_inputs/windows.json")
    coverage, counts, methods, window_checks = {}, {}, {}, 0
    for pid in passages:
        audit_path = source / pid / "grammar/sentence_review.json"
        audit = ladder.read(audit_path)
        complete = all(audit["files"][name]["complete"] for name in ladder.TEXTS)
        if not complete and not include_partial:
            raise ValueError(f"Not a complete every-sentence variant: {pid}; use --include-partial")
        method = methods[pid] = METHOD if complete else "grammar/max_approved"
        directory = source / pid / (METHOD if complete else "grammar")
        meta = ladder.read(directory / "grammar_metadata.json") if complete else {
            "schema_version": 2, "generation_mode": "validated_bank",
            "variant": "max_approved", "unit_mode": "sentence", "complete": False,
            "source_method_dir": str(clean_root / pid / "_base/llm_prompt_high"), "files": {},
        }
        for name in ladder.TEXTS:
            review = audit["files"][name]
            clean_path = clean_root / pid / "_base/llm_prompt_high" / name
            if clean_path.read_bytes() != (previous / pid / "_base/llm_prompt_high" / name).read_bytes():
                raise ValueError(f"Clean passage changed: {pid}/{name}")
            bank_path = source / pid / "grammar/_grammar_bank" / f"bank_{review['bank_id']}.json"
            bank = ladder.read(bank_path)
            clean = clean_path.read_text()
            regenerated, regenerated_meta = grammar.apply_grammar_bank(
                clean, rate=1.0, seed=bank["spec"]["seed"], bank=bank)
            total = sum(unit["affectable"] for unit in grammar.passage_units(clean, unit_mode="sentence"))
            variant_path = directory / (name if complete else "draft_" + name)
            if (bank["spec"].get("unit_mode") != "sentence"
                or total != review["total_sentence_units"]
                or len(bank["entries"]) != review["approved_sentence_units"]
                or review["complete"] != (len(bank["entries"]) == total)
                or review["sentence_coverage"] != len(bank["entries"]) / total
                or review["source_sha256"] != grammar.json_digest(clean)
                or regenerated != variant_path.read_text()
                or (complete and (regenerated_meta["actual_affected_rate"] != 1.0
                    or meta["files"][Path(name).stem]["output_sha256"] != grammar.json_digest(regenerated)))):
                raise ValueError(f"Variant failed bank verification: {pid}/{name}")
            ladder.snapshot(bank_path, root / "_provenance" / pid / bank_path.name)
            ladder.snapshot(variant_path, root / pid / method / name)
            if not complete:
                meta["files"][Path(name).stem] = {
                    **regenerated_meta, "total_sentence_units": total,
                    "approved_sentence_units": len(bank["entries"]),
                    "sentence_coverage": review["sentence_coverage"],
                }
        ladder.snapshot(audit_path, root / "_provenance" / pid / audit_path.name)
        coverage[pid] = {key: audit["files"][ladder.TEXTS[1]][key] for key in
                         ["total_sentence_units", "approved_sentence_units", "sentence_coverage"]}
        shared = previous / pid / "_base/_shared"
        for suffix in ["qa_zh.json", "qa_zh_decanonicalized.json"]:
            name = f"{pid}_base_{suffix}"
            if tuple(qa_formats) == ("open", "mcq"):
                ladder.snapshot(shared / name, root / pid / "_base/_shared" / name)
            else:
                save_input(root / pid / "_base/_shared" / name,
                           [row for row in ladder.read(shared / name) if row["q_type"] in qa_formats])
        rows = ladder.read(root / pid / "_base/_shared" / f"{pid}_base_qa_zh_decanonicalized.json")
        questions = public_questions(rows)
        counts[pid] = len(questions)
        for name in ladder.ARTIFACTS + ["grammar_metadata.json"]:
            if name in ["qa_target.json", "qa_target_decanonicalized.json"]:
                save_input(root / pid / method / name, rows)
            elif complete:
                ladder.snapshot(directory / name, root / pid / method / name)
            elif name not in ladder.TEXTS:
                base = clean_root / pid / "_base/llm_prompt_high"
                if name == "grammar_metadata.json":
                    save_input(root / pid / method / name, meta)
                elif name == "passage_translation.json":
                    save_input(root / pid / method / name, grammar.build_passage_translation_json(
                        base / name, method=method,
                        rate=meta["files"]["passage_target"]["actual_affected_rate"],
                        grammar_text=(root / pid / method / ladder.TEXTS[0]).read_text(),
                        metadata=meta["files"]["passage_target"]))
                elif name == "decanonicalized_metadata.json":
                    save_input(root / pid / method / name, {
                        "method": method, "source_method_dir": str(base),
                        "grammar_metadata_file": str(root / pid / method / "grammar_metadata.json"),
                        "sentence_coverage": coverage[pid]["sentence_coverage"],
                        "source": "Validated saved draft; unresolved sentences unchanged",
                    })
                else:
                    ladder.snapshot(base / name, root / pid / method / name)
        text = (root / pid / method / ladder.TEXTS[1]).read_text()
        index, order = index_passage_verses(text, chapters_from_reference(rows[0]["passage_reference"]))
        for question in questions:
            keys = curated_window_for_item(windows, question)
            expected = "\n".join(index[k] for k in keys if k in index).strip() if keys else ""
            actual = local_passage_for_question("UNEXPECTED FULL PASSAGE", index, question, 2, order, windows)
            if not expected or actual != expected:
                raise ValueError(f"Invalid answer window: {pid}/{question['id']}")
            window_checks += 1
    for path in (previous / "_inputs").rglob("*"):
        if path.is_file():
            ladder.snapshot(path, root / path.relative_to(previous))
    directories = [root / "_inputs", root / "_provenance"]
    directories += [root / pid / part for pid in passages for part in ["_base", methods[pid]]]
    manifest = {
        "qa_set": "hard66_canonical_reviewed", "grammar_source": str(source), "previous_run": str(previous),
        "inference": INFERENCE, "passages": passages, "coverage": coverage,
        "coverage_definition": ("Fraction of sentence units containing an approved structural defect; unresolved units unchanged"
                                if include_partial else "Every sentence unit contains at least one approved structural defect"),
        "omitted_passages": [pid for pid in ladder.PASSAGES if pid not in passages],
        "cells": [["grammar", MODEL, pid, methods[pid]] for pid in passages],
        "total_cells": len(passages), "total_responses": sum(counts.values()), "window_checks": window_checks,
        "input_hashes": {str(path.relative_to(root)): ladder.fingerprint(path)
                         for directory in directories for path in directory.rglob("*") if path.is_file()},
    }
    if include_partial or tuple(qa_formats) != ("open", "mcq"):
        manifest.update(include_partial=include_partial, qa_formats=list(qa_formats))
    save_input(root / "release.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grammar-source", type=Path, default=REPO / "evaluation/runs/grammar_every_sentence_retry_2026-10-25")
    parser.add_argument("--previous-run", type=Path, default=REPO / "evaluation/runs/hard66_full_ladder_2026-10-23")
    parser.add_argument("--run-root", type=Path, default=REPO / "evaluation/runs/hard66_grammar_sentence_qwen317b_nothink_2026-10-25")
    parser.add_argument("--passages", nargs="+", default=["t1_2sam21", "t1_acts23"], choices=list(ladder.PASSAGES))
    parser.add_argument("--all-passages", action="store_true")
    parser.add_argument("--include-partial", action="store_true")
    parser.add_argument("--qa-formats", nargs="+", choices=["open", "mcq"], default=["open", "mcq"])
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    source, previous, root = [p.resolve() for p in [args.grammar_source, args.previous_run, args.run_root]]
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "run.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ["QA_FORMATS"] = ",".join(args.qa_formats)
    passages = list(ladder.PASSAGES) if args.all_passages else args.passages
    manifest = prepare(source, previous, root, passages,
                       include_partial=args.include_partial, qa_formats=args.qa_formats)
    print(f"Verified {manifest['total_cells']} passages and {manifest['total_responses']} question responses", flush=True)
    if args.prepare_only:
        return
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
    os.environ.update(QA_FORMATS=",".join(args.qa_formats), MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E",
                      OLLAMA_NUM_PREDICT=str(INFERENCE["num_predict"]), OLLAMA_NUM_CTX=str(INFERENCE["num_ctx"]),
                      OLLAMA_TIMEOUT=str(INFERENCE["timeout_seconds"]), MCQ_KEEP_THINKING="1")
    job = {"status": "running", "pid": os.getpid(), "started_at": time.time(),
           "qa_formats": args.qa_formats, **INFERENCE}
    ladder.write_atomic(root / "job.json", job)
    caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-is", "-w", str(os.getpid())]) if sys.platform == "darwin" else None
    try:
        ladder.evaluate(root, selected_cells=[tuple(c) for c in manifest["cells"]], no_think=True)
        verify_hashes(root, manifest["input_hashes"])
        state = ladder.read(root / "campaign_state.json")
        job.update(status=state["status"], finished_at=time.time())
        if job["status"] != "complete":
            raise RuntimeError("Some evaluations failed; inspect campaign_state.json")
    except Exception as exc:
        job.update(status="failed", error=str(exc), finished_at=time.time())
        raise
    finally:
        ladder.write_atomic(root / "job.json", job)
        if caffeinate:
            caffeinate.terminate()


if __name__ == "__main__":
    main()
