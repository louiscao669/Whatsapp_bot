#!/usr/bin/env python3
"""Restore Tier-1 clean cells after a forced run used the default output root.

The six pre-existing 0% defect cells preserve the old clean inputs.  The old
backtranslated answer file preserves the generated-answer record and adds only
``generated_answer_english``.  This utility validates those independent copies,
snapshots the accidentally overwritten cells, and reconstructs only cells for
which both the old backtranslation and score artifacts still exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


PASSAGES = (
    "t1_judg9",
    "t1_judg17_18",
    "t1_2kgs6_7",
    "t1_1kgs13",
    "t1_2kgs11",
    "t1_2chr26",
    "t1_2sam21",
    "t1_acts19",
    "t1_acts20",
    "t1_acts23",
)
MODELS = ("llama321b", "qwen2515b", "qwen317b")
DEFECTS = (
    "omission",
    "mistranslation",
    "grammar",
    "awkward",
    "addition",
    "inconsistency",
)
CORE_FILES = (
    "passage_source_decanonicalized.txt",
    "passage_target.txt",
    "passage_target_decanonicalized.txt",
    "passage_translation.json",
    "qa_target.json",
    "qa_target_decanonicalized.json",
)


def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".restore-tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item_id(item: dict) -> str:
    return str(item.get("passage_id") or item.get("id"))


def validate_cell(root: Path, passage: str, model: str) -> tuple[bool, int]:
    baselines = [root / passage / model / defect / "0%" for defect in DEFECTS]
    for filename in CORE_FILES:
        candidates = [directory / filename for directory in baselines]
        missing = [str(path) for path in candidates if not path.is_file()]
        if missing:
            raise RuntimeError(f"Missing 0% baseline artifact(s): {missing}")
        if len({digest(path) for path in candidates}) != 1:
            raise RuntimeError(
                f"0% baselines disagree for {passage}/{model}/{filename}"
            )

    clean = root / passage / model / "llm_prompt_high"
    backtranslated_path = clean / "generated_answers_target_llama_backtranslated.json"
    scores_path = clean / "scores_target_llama.json"
    if not backtranslated_path.is_file() or not scores_path.is_file():
        return False, 0

    qa = read_json(baselines[0] / "qa_target_decanonicalized.json")
    backtranslated = read_json(backtranslated_path)
    score_document = read_json(scores_path)
    scores = score_document.get("items") if isinstance(score_document, dict) else None
    if not all(isinstance(value, list) for value in (qa, backtranslated, scores)):
        raise RuntimeError(f"Unexpected JSON shape for {passage}/{model}")
    if not (len(qa) == len(backtranslated) == len(scores)):
        raise RuntimeError(
            f"Item counts disagree for {passage}/{model}: "
            f"QA={len(qa)}, backtranslated={len(backtranslated)}, scores={len(scores)}"
        )

    for position, (question, answer, score) in enumerate(
        zip(qa, backtranslated, scores), start=1
    ):
        if len({item_id(question), item_id(answer), item_id(score)}) != 1:
            raise RuntimeError(
                f"Item ID mismatch at {passage}/{model} item {position}"
            )
        if answer.get("q_type") == "open":
            if answer.get("generated_answer") != score.get("generated_answer"):
                raise RuntimeError(
                    f"Open answer mismatch at {passage}/{model} item {position}"
                )
        elif answer.get("selected_choice"):
            if answer.get("selected_choice") != score.get("selected_choice"):
                raise RuntimeError(
                    f"Resolved MCQ mismatch at {passage}/{model} item {position}"
                )
    return True, len(backtranslated)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def snapshot(root: Path, backup: Path) -> None:
    if backup.exists():
        raise RuntimeError(f"Backup destination already exists: {backup}")
    for passage in PASSAGES:
        passage_root = root / passage
        base_root = passage_root / "_base"
        shutil.copytree(
            base_root / "llm_prompt_high",
            backup / passage / "_base" / "llm_prompt_high",
        )
        for shared in (base_root / "_shared").glob("*_qa_zh*.json"):
            copy_file(shared, backup / passage / "_base" / "_shared" / shared.name)
        for model in MODELS:
            model_root = passage_root / model
            shutil.copytree(
                model_root / "llm_prompt_high",
                backup / passage / model / "llm_prompt_high",
            )
            for shared in (model_root / "_shared").glob("*_qa_zh*.json"):
                copy_file(shared, backup / passage / model / "_shared" / shared.name)


def restore_base_inputs(root: Path, passage: str) -> None:
    source = root / passage / MODELS[0] / DEFECTS[0] / "0%"
    base = root / passage / "_base"
    for filename in CORE_FILES:
        copy_file(source / filename, base / "llm_prompt_high" / filename)
    copy_file(
        source / "qa_target.json",
        base / "_shared" / f"{passage}_base_qa_zh.json",
    )
    copy_file(
        source / "qa_target_decanonicalized.json",
        base / "_shared" / f"{passage}_base_qa_zh_decanonicalized.json",
    )


def restore_cell(root: Path, passage: str, model: str) -> int:
    source = root / passage / model / DEFECTS[0] / "0%"
    model_root = root / passage / model
    clean = model_root / "llm_prompt_high"
    for filename in CORE_FILES:
        copy_file(source / filename, clean / filename)
    copy_file(
        source / "qa_target.json",
        model_root / "_shared" / f"{passage}_{model}_qa_zh.json",
    )
    copy_file(
        source / "qa_target_decanonicalized.json",
        model_root / "_shared" / f"{passage}_{model}_qa_zh_decanonicalized.json",
    )

    old_answers = read_json(
        clean / "generated_answers_target_llama_backtranslated.json"
    )
    reconstructed = []
    for old_answer in old_answers:
        answer = dict(old_answer)
        answer.pop("generated_answer_english", None)
        reconstructed.append(answer)
    write_json(clean / "generated_answers_target_llama.json", reconstructed)
    return len(reconstructed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path("evaluation/outputs/tier1")
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=Path(
            "evaluation/outputs/recovery/tier1_wrong_default_20260817_1550"
        ),
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reconstructable: list[tuple[str, str]] = []
    unavailable: list[tuple[str, str]] = []
    item_count = 0
    for passage in PASSAGES:
        for model in MODELS:
            available, count = validate_cell(args.root, passage, model)
            if available:
                reconstructable.append((passage, model))
                item_count += count
            else:
                unavailable.append((passage, model))

    print(
        f"validated {len(reconstructable)}/30 reconstructable clean cells "
        f"({item_count} answer records)"
    )
    for passage, model in unavailable:
        print(f"unavailable: {passage}/{model}")
    if not args.apply:
        print("dry run: no files written")
        return

    snapshot(args.root, args.backup)
    for passage in PASSAGES:
        restore_base_inputs(args.root, passage)
    restored_items = 0
    for passage, model in reconstructable:
        restored_items += restore_cell(args.root, passage, model)
    print(f"backup: {args.backup}")
    print(
        f"restored {len(reconstructable)} clean cells "
        f"({restored_items} answer records)"
    )


if __name__ == "__main__":
    main()
