#!/usr/bin/env python3
"""Prepare a reviewed six-dose release, then run a resumable ordered campaign."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import traceback

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.analysis.current.check_full_conditions_5opt import PASSAGES, check_inputs
from evaluation.scripts.variants.banks.extend_mistranslation_coverage import extend_bank
from evaluation.scripts.variants.banks.mistranslation_validation import write_atomic
from evaluation.scripts.variants.current import create_grammar_variants as grammar
from evaluation.scripts.variants.current import create_mistranslation_variants as mis
from evaluation.scripts.variants.current import create_omission_variants as omission
from evaluation.scripts.variants.current.create_grammar_candidate_variants import plan_nested_selections

RATES = [.05, .10, .15, .20, .25, .30]
MODELS = ["llama3.2:1b", "qwen2.5:1.5b", "qwen3:1.7b"]
TEXTS = ["passage_target.txt", "passage_target_decanonicalized.txt"]
ARTIFACTS = [*TEXTS, "passage_source_decanonicalized.txt", "passage_translation.json",
             "qa_target.json", "qa_target_decanonicalized.json", "decanonicalized_metadata.json"]
RESULTS = ["generated_answers_target_llama.json", "generated_answers_target_llama_backtranslated.json", "scores_target_llama.json"]
DEFAULT_SOURCE = REPO / "evaluation/outputs/tier1_bsb_unblinded_5opt_think"
DEFAULT_RUN = REPO / "evaluation/runs/full_ladder_2026-10-23"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(source: Path, destination: Path):
    if destination.is_file():
        if fingerprint(source) != fingerprint(destination):
            raise ValueError(f"Snapshot changed: {source}; use a new run directory")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def initialize(source: Path, root: Path):
    for pid, filename in PASSAGES.items():
        for name in ARTIFACTS:
            for method in ["_base/llm_prompt_high", "google_word_by_word"]:
                path = source / pid / method / name
                if path.is_file():
                    snapshot(path, root / pid / method / name)
        for suffix in ["qa_zh.json", "qa_zh_decanonicalized.json"]:
            name = f"{pid}_base_{suffix}"
            snapshot(source / pid / "_base/_shared" / name, root / pid / "_base/_shared" / name)
        snapshot(source / pid / "_base/_shared/mistranslation_bank_sol_length_zh.json",
                 root / pid / "_base/_shared/mistranslation_bank_parent_zh.json")
        snapshot(REPO / "evaluation/datasets/qa/tier1_gold72_canonical_5opt" / f"{pid}_all_formats.json",
                 root / "_inputs/qa" / f"{pid}_all_formats.json")
        snapshot(REPO / "evaluation/datasets/passages/tier1_bsb" / filename, root / "_inputs/passages" / filename)
        family = "grammar_sol_nested_test" if pid == "t1_acts20" else "grammar_sol_phrase_test"
        bank_dir = root / pid / "grammar/_grammar_bank"
        # Copy caches once; the release may subsequently extend its own copies.
        if not (bank_dir / "snapshot_complete.json").exists():
            bank_dir.mkdir(parents=True, exist_ok=True)
            for path in (source / pid / family / "_grammar_bank").glob("*.json"):
                if not (bank_dir / path.name).exists():
                    shutil.copy2(path, bank_dir / path.name)
            original = read(source / pid / family / "30%/grammar_metadata.json")
            write_atomic(bank_dir / "snapshot_complete.json", {"source": str(source / pid / family), "metadata": original})
    snapshot(REPO / "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json", root / "_inputs/windows.json")
    snapshot(REPO / "evaluation/datasets/pseudonym_remap/empty_map_unblinded.json", root / "_inputs/map.json")


def weighted_plan(weights, total):
    bank = {"entries": [{"content_chars": w} for w in weights], "total_content_chars": total, "max_rate": .3}
    return plan_nested_selections(bank, RATES, tolerance_pp=2)


def prepare_passage(source: Path, root: Path, pid: str, exclusions: list[dict], offline: bool):
    marker = root / "_preparation" / f"{pid}.json"
    if marker.exists() and read(marker).get("status") == "complete":
        result = check_inputs(root, [pid])
        if result["ready"]:
            return read(marker)
        raise ValueError(f"Previously prepared inputs changed: {result['errors']}")
    base = root / pid / "_base/llm_prompt_high"
    clean = {name: (base / name).read_text() for name in TEXTS}
    if len(set(clean.values())) != 1:
        raise ValueError("This unblinded release requires identical raw/decanonicalized texts")
    text = clean[TEXTS[0]]
    report = {"passage": pid, "status": "preparing", "families": {}}
    omission.create_clean_copy(base, root / pid / "omission", force=False)

    units = omission.passage_units(text)
    candidates = [i for i, u in enumerate(units) if u["omittable"] and u["content_chars"]]
    random.Random(2026 + omission.seed_offset(pid)).shuffle(candidates)
    plan = weighted_plan([units[i]["content_chars"] for i in candidates], sum(units[i]["content_chars"] for i in candidates))
    for rate in RATES:
        omission.create_variant(source_method_dir=base, output_dir=root / pid / "omission", rate=rate,
            seed=2026 + omission.seed_offset(pid), force=True,
            selections={name: [candidates[i] for i in plan[rate]] for name in TEXTS})
    report["families"]["omission"] = "complete"
    write_atomic(marker, report)

    bank_dir = root / pid / "grammar/_grammar_bank"
    prior = read(bank_dir / "snapshot_complete.json")["metadata"]
    banks = {name: read(bank_dir / f"bank_{prior['files'][Path(name).stem]['bank_id']}.json") for name in TEXTS}
    eligible = sum(bool(u["affectable"] and u["content_chars"]) for u in grammar.passage_units(text))
    for attempt in range(8):
        try:
            for bank in banks.values():
                grammar.validate_grammar_bank(text, bank)
            plans = {name: plan_nested_selections(bank, RATES) for name, bank in banks.items()}
            break
        except grammar.GrammarError:
            target = min(eligible, max(8, max(len(b["entries"]) for b in banks.values()) + 4))
            print(f"{pid}: expanding grammar pool to {target} approved clauses", flush=True)
            banks = grammar.prepare_grammar_banks(base, root / pid / "grammar",
                seed=prior["seed"], bank_rate=.3, model="gpt-6.1-sol", generator_model="gpt-6.1-sol",
                max_candidates=3, proposal_batch_size=8, offline=offline, min_approved_candidates=target)
    else:
        raise ValueError(f"Unable to plan six grammar levels for {pid}")
    for rate in RATES:
        grammar.create_variant(source_method_dir=base, output_dir=root / pid / "grammar", rate=rate,
            seed=prior["seed"], force=True, banks=banks,
            selections={name: plan[rate] for name, plan in plans.items()})
    report["families"]["grammar"] = "complete"
    write_atomic(marker, report)

    parent = read(root / pid / "_base/_shared/mistranslation_bank_parent_zh.json")
    bank = extend_bank(passage=text, parent=parent, cache_dir=root / pid / "_coverage_cache",
        output=root / pid / "_base/_shared/mistranslation_bank_coverage_zh.json", exclusions=exclusions,
        offline=offline, workers=4)
    groups = mis.candidate_groups(mis.find_occurrences(text, mis.normalized_replacements(bank)))
    plan = weighted_plan([g["changed_chars"] for g in groups], mis.content_len(text))
    for rate in RATES:
        mis.create_variant(source_method_dir=base, output_dir=root / pid / "mistranslation", rate=rate,
            seed=2036 + mis.seed_offset(pid), force=True, bank=bank,
            selections={name: plan[rate] for name in TEXTS})
    report["families"]["mistranslation"] = "complete"
    result = check_inputs(root, [pid])
    if not result["ready"]:
        raise ValueError(str(result["errors"]))
    # Provenance records both the metric and the exact nested units selected.
    report.update(status="complete", finished_at=time.time(), cells=result["cells"])
    write_atomic(marker, report)
    return report


def prepare(source, root, offline=False):
    initialize(source, root)
    exclusions = []
    for pid in PASSAGES:
        exclusions.extend(read(root / pid / "_base/_shared/mistranslation_bank_parent_zh.json").get("curation", {}).get("excluded_pairs", []))
    failures = []

    def work(pid):
        for attempt in range(3):
            try:
                return prepare_passage(source, root, pid, exclusions, offline)
            except Exception:
                if offline or attempt == 2:
                    raise
                print(f"{pid}: preparation interrupted; retrying from cache ({attempt+1}/2)", flush=True)
                traceback.print_exc()
                time.sleep(5)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(work, pid): pid for pid in PASSAGES}
        for future in as_completed(futures):
            pid = futures[future]
            try:
                future.result()
                print(f"PREPARED {pid}", flush=True)
            except Exception as exc:
                failures.append({"passage": pid, "error": str(exc)})
                traceback.print_exc()
    result = check_inputs(root, list(PASSAGES))
    result["preparation_failures"] = failures
    write_atomic(root / "readiness.json", result)
    if failures or not result["ready"]:
        raise ValueError(f"Release is not ready; see {root / 'readiness.json'}")
    write_atomic(root / "release.json", {"status": "ready", "created_at": time.time(),
        "source": str(source), "rates": RATES, "models": MODELS, "cells": 600,
        "metrics": {"grammar": "source content characters in affected clauses", "omission": "removed clause content characters",
                    "mistranslation": "replaced source-span content characters"},
        "input_hashes": {str(p.relative_to(root)): fingerprint(p) for pid in PASSAGES
                         for condition in ["omission/0%", "google_word_by_word"] + [f"{f}/{r}%" for f in ["omission", "mistranslation", "grammar"] for r in [5,10,15,20,25,30]]
                         for p in (root / pid / condition).glob("*.txt")}})


def campaign_cells(exclude_grammar=False):
    # Finish clean for every passage/model before starting any omission cell.
    for stage in ["clean", "omission", "mistranslation", "grammar", "wbw"]:
        if exclude_grammar and stage == "grammar":
            continue
        methods = ["omission/0%"] if stage == "clean" else ["google_word_by_word"] if stage == "wbw" else [f"{stage}/{r}%" for r in [5,10,15,20,25,30]]
        for model in MODELS:
            for pid in PASSAGES:
                for method in methods:
                    yield stage, model, pid, method


def verify_cell(destination: Path, expected: set[tuple], *, no_think=False) -> dict:
    outputs = [read(destination / name) for name in RESULTS]
    counts = {}
    for name, data in zip(RESULTS, outputs):
        rows = data["items"] if isinstance(data, dict) else data
        keys = [(r.get("id"), r["q_type"]) for r in rows]
        if len(keys) != len(expected) or set(keys) != expected:
            raise ValueError(f"Incomplete or duplicate question rows: {destination / name}")
        counts[name] = len(keys)
    errors = [r for r in outputs[0] if r.get("generation_error")]
    if no_think and (errors or any(
        r.get("answer_effort", {}).get("thinking_chars") != 0 for r in outputs[0]
    )):
        raise ValueError(f"No-thinking verification failed: {destination}")
    return {"row_counts": counts, "generation_error_count": len(errors),
            "result_hashes": {name: fingerprint(destination / name) for name in RESULTS}}


def evaluate(root: Path, exclude_grammar=False, *, selected_cells=None, no_think=False):
    from evaluation.agents.generate_chinese_answers import load_qa_items, public_questions
    state_path = root / "campaign_state.json"
    state = read(state_path) if state_path.exists() else {"cells": {}, "started_at": time.time()}
    if state.get("cells") and state.get("no_think", False) != no_think:
        raise ValueError("Cannot mix thinking modes in one campaign")
    cells = list(campaign_cells(exclude_grammar=exclude_grammar) if selected_cells is None else selected_cells)
    if not cells or len(cells) != len(set(cells)):
        raise ValueError("Campaign cells must be nonempty and unique")
    selected_keys = {f"{stage}/{model}/{pid}/{method}" for stage, model, pid, method in cells}
    state.update(status="running", pid=os.getpid(), excluded_stages=["grammar"] if exclude_grammar else [],
                 total_cells=len(cells), no_think=no_think)
    consecutive_failures = 0
    for stage, model, pid, method in cells:
        slug = model.replace(":", "").replace(".", "") + ("_nothink" if no_think else "_think")
        key = f"{stage}/{model}/{pid}/{method}"
        destination = root / pid / slug / method
        shared = root / pid / "_base/_shared"
        qa_dec = shared / f"{pid}_base_qa_zh_decanonicalized.json"
        expected = {(q.get("id"), q["q_type"]) for q in public_questions(load_qa_items(qa_dec))}
        if state["cells"].get(key, {}).get("status") == "complete":
            verified = verify_cell(destination, expected, no_think=no_think)
            if verified["result_hashes"] != state["cells"][key]["result_hashes"]:
                raise ValueError(f"Completed results changed: {key}")
            continue
        state.update(stage=stage, current_cell=key, updated_at=time.time())
        destination.mkdir(parents=True, exist_ok=True)
        source = root / pid / method
        for path in source.iterdir():
            if path.is_file() and (path.name in ARTIFACTS or path.name.endswith("_metadata.json")):
                shutil.copy2(path, destination / path.name)
        command = [sys.executable, "-u", str(REPO / "evaluation/main.py"),
            str(root / "_inputs/passages" / PASSAGES[pid]), str(root / "_inputs/qa" / f"{pid}_all_formats.json"),
            "--output-dir", str(root / pid / slug), "--run-name", f"{pid}_{slug}", "--methods", method,
            "--answer-provider", "ollama", "--answer-model", model, "--mcq-choice-mapper", "openai",
            "--skip-entity-discovery", "--pre-blinded", "--pseudonym-map", str(root / "_inputs/map.json"),
            "--answer-verse-window", "2", "--temperature", "0.0", "--allow-partial-answers",
            "--translated-qa-json", str(shared / f"{pid}_base_qa_zh.json"), "--decanonicalized-qa-json", str(qa_dec),
            "--answer-verse-windows-json", str(root / "_inputs/windows.json")]
        if no_think:
            command.append("--ollama-no-think")
        log = root / "logs" / f"{stage}_{slug}_{pid}_{method.replace('/', '_')}.log"
        log.parent.mkdir(exist_ok=True)
        success = False
        for attempt in range(2):
            state["cells"][key] = {"status": "running", "started_at": time.time(), "log": str(log), "attempt": attempt+1}
            write_atomic(state_path, state)
            print(f"RUN {key}", flush=True)
            with log.open("a") as handle:
                result = subprocess.run(command, cwd=REPO, stdout=handle, stderr=subprocess.STDOUT, timeout=7200)
            try:
                if result.returncode:
                    raise ValueError(f"Pipeline exited {result.returncode}; see {log}")
                verified = verify_cell(destination, expected, no_think=no_think)
                state["cells"][key].update(status="complete", finished_at=time.time(), **verified)
                success = True
                break
            except Exception as exc:
                state["cells"][key].update(status="failed", error=str(exc))
                print(f"FAILED {key}: {exc}", flush=True)
                # Reuse valid stages on transient API failures. Missing/invalid
                # files are retained under an attempt directory before rerunning.
                if not result.returncode:
                    archived = destination / f"invalid_attempt_{int(time.time())}"
                    archived.mkdir()
                    for name in RESULTS:
                        if (destination / name).exists():
                            shutil.move(destination / name, archived / name)
                time.sleep(5)
        consecutive_failures = 0 if success else consecutive_failures + 1
        state["completed_cells"] = sum(state["cells"].get(k, {}).get("status") == "complete" for k in selected_keys)
        state["updated_at"] = time.time()
        write_atomic(state_path, state)
        if consecutive_failures >= 3:
            raise ValueError("Three consecutive pipeline failures; paused to avoid repeating a system-wide failure")
    state["completed_cells"] = sum(state["cells"].get(k, {}).get("status") == "complete" for k in selected_keys)
    state.update(status="complete" if state["completed_cells"] == len(cells) else "complete_with_errors", finished_at=time.time())
    write_atomic(state_path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--phase", choices=["all", "prepare", "evaluate"], default="all")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--exclude-grammar", action="store_true",
                        help="Skip grammar model evaluations; prepared passage inputs remain available")
    args = parser.parse_args()
    root = args.run_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.background:
        command = [sys.executable, "-u", str(Path(__file__).resolve()), "--source", str(args.source.resolve()),
                   "--run-root", str(root), "--phase", args.phase]
        if args.offline:
            command.append("--offline")
        if args.exclude_grammar:
            command.append("--exclude-grammar")
        with (root / "overnight.log").open("a") as log:
            process = subprocess.Popen(command, cwd=REPO, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps({"pid": process.pid, "log": str(root / "overnight.log")}))
        return
    lock = (root / "run.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
    os.environ.update(QA_FORMATS="open,mcq", MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E")
    caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-is", "-w", str(os.getpid())]) if sys.platform == "darwin" else None
    job_path = root / "job.json"
    write_atomic(job_path, {"status": "running", "phase": args.phase, "pid": os.getpid(), "started_at": time.time()})
    try:
        if args.phase in ["all", "prepare"]:
            prepare(args.source.resolve(), root, args.offline)
        if args.phase in ["all", "evaluate"]:
            release = read(root / "release.json")
            for relative, expected in release["input_hashes"].items():
                if fingerprint(root / relative) != expected:
                    raise ValueError(f"Release input changed: {relative}")
            if not check_inputs(root, list(PASSAGES))["ready"]:
                raise ValueError("Full input check failed")
            write_atomic(job_path, {"status": "running", "phase": "evaluate", "pid": os.getpid(), "updated_at": time.time()})
            evaluate(root, exclude_grammar=args.exclude_grammar)
        write_atomic(job_path, {"status": "complete", "phase": args.phase, "pid": os.getpid(), "finished_at": time.time()})
    except Exception as exc:
        write_atomic(job_path, {"status": "failed", "phase": args.phase, "pid": os.getpid(), "error": str(exc), "updated_at": time.time()})
        raise
    finally:
        if caffeinate:
            caffeinate.terminate()


if __name__ == "__main__":
    main()
