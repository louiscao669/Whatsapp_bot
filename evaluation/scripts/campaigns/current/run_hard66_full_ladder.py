#!/usr/bin/env python3
"""Bind reviewed Hard 66 QA to the repaired passages, then run all three models.

--prepare-only copies and validates inputs without API calls or model answering.
The default runs in the foreground and resumes only this Hard 66 campaign.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.campaigns.current import run_overnight_ladder as ladder

DEFAULT_QA = REPO / "evaluation/datasets/qa/tier1_hard66_canonical"
DEFAULT_RUN = REPO / "evaluation/runs/hard66_full_ladder_2026-10-23"
CANNOT_TELL = "根据这段文字无法判断"
CONDITIONS = ["omission/0%", "google_word_by_word"] + [
    f"{family}/{rate}%" for family in ["omission", "mistranslation", "grammar"]
    for rate in [5, 10, 15, 20, 25, 30]
]


def base_id(row):
    return row["passage_id"].removeprefix("uw-").removesuffix("-open").removesuffix("-mcq")


def reviewed_rows(rows):
    """Honor the same exclusions/form restrictions used by the human pilot."""
    groups = {}
    for row in rows:
        groups.setdefault(base_id(row), {})[row["q_type"]] = row
    result, omitted = [], []
    for content_id, forms in groups.items():
        decision = forms.get("mcq") or forms["open"]
        for form, original in forms.items():
            if decision.get("status") == "exclude" or (
                decision.get("force_form") and decision["force_form"] != form
            ):
                omitted.append({"id": original["passage_id"], "reason": decision.get("review_note")})
                continue
            row = copy.deepcopy(original)
            row["id"] = row["passage_id"]
            if row.get("local_passage") or row.get("answer_passage") or row.get("qa_passage"):
                raise ValueError(f"Unexpected embedded passage override: {row['id']}")
            if form == "mcq":
                if row["correct"] not in "ABCD" or set(row["A"]) not in [set("ABCD"), set("ABCDE")]:
                    raise ValueError(f"Unexpected MCQ key/options: {row['id']}")
                row["A"]["E"] = CANNOT_TELL
            result.append(row)
    return result, omitted


def item_window(row, clean_order):
    chapter = int(row["reference"].split(":")[0])
    keys = [(chapter, int(v)) for v in row["window_verses"]]
    if not keys or any(k not in clean_order for k in keys):
        raise ValueError(f"Invalid reviewed window: {row['passage_id']}")
    if row.get("window_start"):
        start = tuple(map(int, row["window_start"].split(":")))
        if start not in clean_order:
            raise ValueError(f"Invalid reviewed window start: {row['passage_id']}")
        if clean_order.index(start) < clean_order.index(keys[0]):
            keys = clean_order[clean_order.index(start):clean_order.index(keys[-1]) + 1]
    return keys


def save_input(path, value):
    # Window keys are tuples in memory and arrays in JSON. Compare the saved
    # representation so a second preparation is an identical, resumable no-op.
    value = json.loads(json.dumps(value, ensure_ascii=False))
    if path.exists() and ladder.read(path) != value:
        raise ValueError(f"Prepared Hard 66 input changed: {path}; use a new --run-root")
    if not path.exists():
        ladder.write_atomic(path, value)


def prepare(source: Path, root: Path, qa_dir: Path):
    from evaluation.agents.generate_chinese_answers import (
        chapters_from_reference, index_passage_verses, public_questions,
        curated_window_for_item, local_passage_for_question,
    )
    if source.resolve() == root.resolve():
        raise ValueError("Hard 66 needs a separate output directory from Gold 72")
    release = ladder.read(source / "release.json")
    for name, expected in release["input_hashes"].items():
        if ladder.fingerprint(source / name) != expected:
            raise ValueError(f"Repaired source changed: {name}")
    report = {"qa_set": "hard66_canonical_reviewed", "source_release": str(source),
              "passages": {}, "excluded_forms": [], "window_extensions": []}
    windows = {}
    for pid, filename in ladder.PASSAGES.items():
        raw = ladder.read(qa_dir / f"{pid}.json")
        rows, omitted = reviewed_rows(raw)
        if not rows:
            raise ValueError(f"No Hard 66 questions for {pid}")
        chapters = chapters_from_reference(rows[0]["passage_reference"])
        text = (source / pid / "omission/0%/passage_target_decanonicalized.txt").read_text()
        _, clean_order = index_passage_verses(text, chapters)
        indexes = {}
        for method in CONDITIONS:
            variant = (source / pid / method / "passage_target_decanonicalized.txt").read_text()
            indexes[method] = index_passage_verses(variant, chapters)
        for row in rows:
            key = base_id(row)
            keys = item_window(row, clean_order)
            original = keys[:]
            # Use one common window across all conditions, as in the pilot.
            while any(not set(keys).intersection(index) for index, _ in indexes.values()):
                first, last = clean_order.index(keys[0]), clean_order.index(keys[-1])
                if last + 1 < len(clean_order):
                    keys.append(clean_order[last + 1])
                elif first:
                    keys.insert(0, clean_order[first - 1])
                else:
                    raise ValueError(f"Empty variant passage for {key}")
            if key in windows and windows[key] != keys:
                raise ValueError(f"Open/MCQ window mismatch: {key}")
            if key not in windows and original != keys:
                report["window_extensions"].append({"content_id": key, "before": original, "after": keys})
            windows[key] = keys
        # Verify the actual answerer's resolution for every row and condition.
        questions = public_questions(rows)
        if len(questions) != len(rows):
            raise ValueError(f"Unexpected question expansion: {pid}")
        for question in questions:
            keys = curated_window_for_item(windows, question)
            if not keys:
                raise ValueError(f"Unbound Hard 66 question: {question['id']}")
            for method, (index, order) in indexes.items():
                expected = "\n".join(index[k] for k in keys if k in index).strip()
                supplied = local_passage_for_question("UNEXPECTED WHOLE-PASSAGE FALLBACK", index, question, 2, order, windows)
                if not expected or supplied != expected:
                    raise ValueError(f"Window delivery mismatch: {pid}/{method}/{question['id']}")
        report["excluded_forms"].extend(omitted)
        report["passages"][pid] = {"questions": len({base_id(r) for r in rows}),
            "open": sum(r["q_type"] == "open" for r in rows),
            "mcq": sum(r["q_type"] == "mcq" for r in rows), "window_checks": len(rows) * len(CONDITIONS)}
        for method in ["_base/llm_prompt_high", *CONDITIONS]:
            for path in (source / pid / method).iterdir():
                if path.is_file() and path.name not in ["qa_target.json", "qa_target_decanonicalized.json"] and (
                    path.name in ladder.ARTIFACTS or path.name.endswith("_metadata.json")
                ):
                    ladder.snapshot(path, root / pid / method / path.name)
            for name in ["qa_target.json", "qa_target_decanonicalized.json"]:
                save_input(root / pid / method / name, rows)
        for suffix in ["qa_zh.json", "qa_zh_decanonicalized.json"]:
            save_input(root / pid / "_base/_shared" / f"{pid}_base_{suffix}", rows)
        save_input(root / "_inputs/qa" / f"{pid}_all_formats.json", rows)
        ladder.snapshot(qa_dir / f"{pid}.json", root / "_inputs/original_hard66" / f"{pid}.json")
        ladder.snapshot(source / "_inputs/passages" / filename, root / "_inputs/passages" / filename)
    save_input(root / "_inputs/windows.json", {"schema_version": 2, "qa_set": "hard66", "windows": [
        {"content_id": key, "window": [f"{c}:{v}" for c, v in keys]} for key, keys in windows.items()
    ]})
    ladder.snapshot(source / "_inputs/map.json", root / "_inputs/map.json")
    result = ladder.check_inputs(root, list(ladder.PASSAGES))
    if not result["ready"]:
        raise ValueError(str(result["errors"]))
    report.update(ready=True, models=ladder.MODELS, conditions=len(CONDITIONS), cells=600,
        question_forms=sum(p["open"] + p["mcq"] for p in report["passages"].values()))
    report["total_responses"] = report["question_forms"] * len(CONDITIONS) * len(ladder.MODELS)
    ladder.write_atomic(root / "readiness.json", {**result, "hard66_binding": report})
    hashes = {}
    for path in (root / "_inputs").rglob("*"):
        if path.is_file():
            hashes[str(path.relative_to(root))] = ladder.fingerprint(path)
    for pid in ladder.PASSAGES:
        for method in ["_base/llm_prompt_high", "_base/_shared", *CONDITIONS]:
            for path in (root / pid / method).iterdir():
                if path.is_file():
                    hashes[str(path.relative_to(root))] = ladder.fingerprint(path)
    save_input(root / "release.json", {**report, "input_hashes": hashes})
    print(f"INPUTS READY: reviewed Hard 66, {report['question_forms']} question forms, 600 available cells", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-release", type=Path, default=ladder.DEFAULT_RUN)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--qa-dir", type=Path, default=DEFAULT_QA)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--exclude-grammar", action="store_true",
                        help="Run clean, omission, mistranslation, and word-by-word only (420 cells)")
    args = parser.parse_args()
    os.environ.update(QA_FORMATS="open,mcq", MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E")
    root = args.run_root.resolve()
    report = prepare(args.source_release.resolve(), root, args.qa_dir.resolve())
    cells = list(ladder.campaign_cells(exclude_grammar=args.exclude_grammar))
    conditions = len({method for _, _, _, method in cells})
    responses = report["question_forms"] * conditions * len(ladder.MODELS)
    print(f"SELECTED: {conditions} conditions, {len(cells)} cells, {responses} responses"
          + ("; grammar excluded" if args.exclude_grammar else ""), flush=True)
    if not args.prepare_only:
        command = [sys.executable, "-u", str(Path(ladder.__file__).resolve()),
                   "--phase", "evaluate", "--run-root", str(root)]
        if args.exclude_grammar:
            command.append("--exclude-grammar")
        os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
