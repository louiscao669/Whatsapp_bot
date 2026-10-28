#!/usr/bin/env python3
"""Bind the current Gold/Hard forms to clean campaign windows and review them.

Writes a separate audit, never edits the canonical question sets. The final
reviewer flags wording for revision; it does not generate replacement questions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from evaluation.agents.generate_chinese_answers import chapters_from_reference, index_passage_verses
from evaluation.scripts.analysis.review_qa_items import normalize_cases, write_json

SOURCE = ROOT / "evaluation/runs/full_ladder_2026-10-23"
HARD_RUN = ROOT / "evaluation/runs/hard66_full_ladder_2026-10-23"
GOLD_QA = ROOT / "evaluation/datasets/qa/tier1_gold72_canonical_5opt"
HARD_QA = ROOT / "evaluation/datasets/qa/tier1_hard66_canonical"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def window_map(path):
    records = read(path)["windows"]
    result = {x["content_id"]: x["window"] for x in records}
    if len(records) != len(result):
        raise ValueError("Duplicate window content IDs")
    return result


def source_context(pid, reference, language, keys, hashes):
    filename = "passage_source_decanonicalized.txt" if language == "en" else "passage_target_decanonicalized.txt"
    relative = f"{pid}/omission/0%/{filename}"
    path = SOURCE / relative
    sha = fingerprint(path)
    expected = read(SOURCE / "release.json")["input_hashes"].get(relative)
    if expected != sha:
        raise ValueError(f"Released clean passage changed: {relative}")
    hashes[str(path.relative_to(ROOT))] = sha
    verses, order = index_passage_verses(path.read_text(), chapters_from_reference(reference))
    parsed = [tuple(map(int, key.split(":"))) for key in keys]
    if not parsed or any(key not in verses for key in parsed):
        raise ValueError(f"Unresolved clean passage window: {pid}, {keys}")
    if sorted(parsed, key=order.index) != parsed or len(set(parsed)) != len(parsed):
        raise ValueError("Window keys must be unique and in passage order")
    return "\n".join(f"{c}:{v} " + re.sub(r"^\s*\d+\s+", "", verses[c, v]) for c, v in parsed)


def freeze(path, data):
    if path.exists() and read(path) != data:
        raise ValueError(f"Existing prepared input changed; use a new run directory: {path}")
    write_json(path, data)


def prepare(root):
    gold_windows_path = SOURCE / "_inputs/windows.json"
    hard_windows_path = HARD_RUN / "_inputs/windows.json"
    gold_windows = window_map(gold_windows_path)
    hard_windows = window_map(hard_windows_path)
    hashes = {str(p.relative_to(ROOT)): fingerprint(p) for p in (gold_windows_path, hard_windows_path)}
    cases = {"gold": [], "hard": []}
    bindings, excluded = [], []
    for path in sorted(GOLD_QA.glob("*.json")):
        hashes[str(path.relative_to(ROOT))] = fingerprint(path)
        for record in read(path):
            cid, pid = record["content_id"], record["passage_id"]
            # Same suffix fallback used by curated_window_for_item in the answerer.
            window_id = cid if cid in gold_windows else cid.split("#", 1)[0]
            keys = gold_windows[window_id]
            passage = source_context(pid, record["passage_reference"], "en", keys, hashes)
            open_q = record["open"]["original_question"]
            open_a = record["open"]["original_answer"]
            for form in ("open", "mcq"):
                item = {"id": f"gold:{cid}:{form}", "passage": passage, "form": form,
                        "question": open_q, "expected_answer": open_a, "options": {},
                        "correct_option": "", "intended_target": "",
                        "original_question": "", "original_answer": ""}
                if form == "mcq":
                    block = record["mcq"]
                    choices = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", block["mcq_options"]))
                    match = re.search(r"<answer>\s*([A-Z])\s*<answer>", block["content"])
                    if not match or match[1] not in choices:
                        raise ValueError(f"Cannot resolve MCQ key: {cid}")
                    item.update(question=block["mcq_stem"], options=choices,
                                expected_answer=choices[match[1]], correct_option=match[1],
                                original_question=open_q, original_answer=open_a)
                cases["gold"].append(item)
                bindings.append({"id": item["id"], "language": "English", "window": keys,
                                 "window_id": window_id, "source_file": str(path.relative_to(ROOT))})

    for path in sorted(HARD_QA.glob("*.json")):
        hashes[str(path.relative_to(ROOT))] = fingerprint(path)
        pid = path.stem
        forms = {}
        for record in read(path):
            cid = record["passage_id"].removeprefix("uw-").rsplit("-", 1)[0]
            forms.setdefault(cid, {})[record["q_type"]] = record
        prepared_path = HARD_RUN / "_inputs/qa" / f"{pid}_all_formats.json"
        prepared = {r["passage_id"]: r for r in read(prepared_path)}
        for cid, group in forms.items():
            restriction = group.get("mcq") or group["open"]
            for form, record in group.items():
                if restriction.get("status") == "exclude" or (
                    restriction.get("force_form") and restriction["force_form"] != form
                ):
                    excluded.append({"id": f"hard:{cid}:{form}", "reason": restriction.get("review_note")})
                    continue
                active = prepared[record["passage_id"]]
                if record["Q"] != active["Q"]:
                    raise ValueError(f"Canonical/prepared Hard question changed: {cid}")
                keys = hard_windows[cid]
                passage = source_context(pid, record["passage_reference"], "zh", keys, hashes)
                item = {"id": f"hard:{cid}:{form}", "passage": passage, "form": form,
                        "question": record["Q"], "expected_answer": record["A"] if form == "open" else "",
                        "options": {}, "correct_option": "", "intended_target": "",
                        "original_question": "", "original_answer": ""}
                if form == "mcq":
                    choices = dict(record["A"])
                    choices.setdefault("E", "根据这段文字无法判断")
                    if choices != active["A"] or record["correct"] != active["correct"]:
                        raise ValueError(f"Canonical/prepared Hard options changed: {cid}")
                    item.update(options=choices, correct_option=record["correct"],
                                expected_answer=choices[record["correct"]])
                    if "open" in group and not restriction.get("force_form"):
                        item.update(original_question=group["open"]["Q"], original_answer=group["open"]["A"])
                elif item["expected_answer"] != active["A"]:
                    raise ValueError(f"Canonical/prepared Hard answer changed: {cid}")
                cases["hard"].append(item)
                bindings.append({"id": item["id"], "language": "Chinese", "window": keys,
                                 "window_id": cid, "source_file": str(path.relative_to(ROOT))})
    for dataset, items in cases.items():
        cases[dataset] = normalize_cases(items)
    assert Counter(x["form"] for x in cases["gold"]) == {"open": 71, "mcq": 71}
    assert Counter(x["form"] for x in cases["hard"]) == {"open": 64, "mcq": 65}
    assert len(excluded) == 3
    root.mkdir(parents=True, exist_ok=True)
    for dataset, items in cases.items():
        freeze(root / f"{dataset}_input.json", items)
    freeze(root / "provenance.json", {
        "source_hashes": hashes, "bindings": bindings, "excluded_forms": excluded,
        "notes": ["Gold English; Hard Chinese; no between-language quality comparison.",
                  "Use campaign window snapshots and hash-verified clean release passages.",
                  "Open-form semantic targets inferred; no unsupported explicit design targets invented.",
                  "MCQ target preservation compared with corresponding open Q/A where active.",
                  "Earlier forecasts used some different contexts; this run uses campaign windows.",
                  "No source questions rewritten or removed; output is a revision queue."]})
    print("Prepared 142 Gold forms and 129 Hard forms; three inactive Hard forms excluded.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = args.run_root.resolve()
    prepare(root)
    if args.prepare_only:
        return 0

    def run(dataset):
        command = [sys.executable, "-u", str(ROOT / "evaluation/scripts/analysis/review_qa_items.py"),
                   "--input", str(root / f"{dataset}_input.json"), "--output-dir", str(root / dataset),
                   "--batch-size", "12", "--repeats", "2", "--workers", "3", "--review-stage",
                   "final_source" if dataset == "gold" else "final_translation"]
        if args.env_file:
            command += ["--env-file", str(args.env_file)]
        with (root / f"{dataset}.log").open("a") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        print(f"{dataset}: reviewer exited {completed.returncode}", flush=True)
        return dataset, completed.returncode

    status = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(run, d) for d in ("gold", "hard")]):
            dataset, code = future.result()
            status[dataset] = code
    write_json(root / "completion.json", status)
    return int(any(status.values()))


if __name__ == "__main__":
    raise SystemExit(main())
