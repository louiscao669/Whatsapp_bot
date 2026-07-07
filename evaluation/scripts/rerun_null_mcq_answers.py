#!/usr/bin/env python3
"""Rerun only null MCQ answers in existing generated-answer files.

This is for older outputs that have selected_choice null but do not have enough
saved raw answer data for repair_null_mcq_choices.py. It reloads the method's
decanonicalized passage and QA, reruns only those MCQ items, and merges the new
rows back into generated_answers_target_llama.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.agents.generate_chinese_answers import (  # noqa: E402
    generate_answers,
    load_passage,
    load_qa_items,
    public_questions,
)


DEFAULT_ANSWER_FILE = "generated_answers_target_llama.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def selected_is_null(item: dict) -> bool:
    return item.get("selected_choice") in (None, "")


def discover_answer_files(args: argparse.Namespace) -> list[Path]:
    if args.files:
        return sorted({Path(path) for path in args.files})

    files: list[Path] = []
    for chapter in args.chapters:
        chapter_root = args.root / f"luke{chapter}"
        if not chapter_root.exists():
            continue
        model_roots = (
            [chapter_root / model_dir for model_dir in args.model_dirs]
            if args.model_dirs
            else [path for path in chapter_root.iterdir() if path.is_dir()]
        )
        for model_root in model_roots:
            if not model_root.exists():
                continue
            if args.methods:
                files.extend(
                    model_root / method / args.answer_file
                    for method in args.methods
                )
            else:
                files.extend(model_root.glob(f"*/{args.answer_file}"))
    return sorted({path for path in files if path.exists()})


def key_for_item(item: dict) -> tuple[str, str]:
    if item.get("item_index") not in (None, ""):
        return ("item_index", str(item["item_index"]))
    if item.get("id") not in (None, ""):
        return ("id", str(item["id"]))
    raise ValueError(f"Answer item has no item_index or id: {item}")


def rerun_file(path: Path, args: argparse.Namespace) -> dict[str, int]:
    method_dir = path.parent
    passage_path = method_dir / args.passage_file
    qa_path = method_dir / args.qa_file
    if not passage_path.exists():
        raise FileNotFoundError(f"missing passage file: {passage_path}")
    if not qa_path.exists():
        raise FileNotFoundError(f"missing QA file: {qa_path}")

    answers = load_json(path)
    if not isinstance(answers, list):
        raise ValueError(f"{path} must contain a JSON list.")

    null_keys = {
        key_for_item(item)
        for item in answers
        if isinstance(item, dict)
        and item.get("q_type") == "mcq"
        and selected_is_null(item)
    }
    if not null_keys:
        return {"null": 0, "rerun": 0, "updated": 0, "failed": 0, "changed": 0}

    passage = load_passage(passage_path)
    questions = public_questions(load_qa_items(qa_path))
    questions_by_key = {}
    for question in questions:
        try:
            questions_by_key[key_for_item(question)] = question
        except ValueError:
            continue

    rerun_questions = [
        questions_by_key[key]
        for key in sorted(null_keys)
        if key in questions_by_key
    ]
    missing = len(null_keys) - len(rerun_questions)
    if missing:
        print(f"warning: {path}: {missing} null MCQ item(s) missing from QA file")
    if not rerun_questions:
        return {"null": len(null_keys), "rerun": 0, "updated": 0, "failed": missing, "changed": 0}

    if args.dry_run:
        return {
            "null": len(null_keys),
            "rerun": len(rerun_questions),
            "updated": 0,
            "failed": missing,
            "changed": 0,
        }

    new_answers = generate_answers(
        passage,
        rerun_questions,
        provider=args.provider,
        model=args.model,
        ollama_base_url=args.ollama_base_url,
        batch_size=args.batch_size,
        verse_window=None if args.verse_window < 0 else args.verse_window,
        retries=args.retries,
        dry_run=False,
        allow_partial_answers=args.allow_partial_answers,
        ollama_no_think=args.ollama_no_think,
        expanded_answer_format=args.expanded_answer_format,
        mcq_choice_mapper=args.mcq_choice_mapper,
        mcq_choice_model=args.mcq_choice_model,
    )
    new_by_key = {key_for_item(item): item for item in new_answers}

    updated = 0
    still_failed = missing
    merged = []
    for item in answers:
        if (
            isinstance(item, dict)
            and item.get("q_type") == "mcq"
            and selected_is_null(item)
            and key_for_item(item) in new_by_key
        ):
            replacement = new_by_key[key_for_item(item)]
            if replacement.get("selected_choice") in (None, ""):
                still_failed += 1
            else:
                updated += 1
            merged.append(replacement)
        else:
            merged.append(item)

    write_json(path, merged)
    return {
        "null": len(null_keys),
        "rerun": len(rerun_questions),
        "updated": updated,
        "failed": still_failed,
        "changed": 1,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rerun only null MCQ items in existing answer outputs."
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific generated_answers_target_llama.json files to patch.",
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument(
        "--chapters",
        nargs="+",
        default=[str(chapter) for chapter in range(1, 9)],
    )
    parser.add_argument(
        "--model-dirs",
        nargs="+",
        default=["1.5b"],
        help='Model output dirs under each chapter. Default: "1.5b".',
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=None,
        help="Method dirs to patch. Default scans all methods.",
    )
    parser.add_argument("--answer-file", default=DEFAULT_ANSWER_FILE)
    parser.add_argument("--passage-file", default="passage_target_decanonicalized.txt")
    parser.add_argument("--qa-file", default="qa_target_decanonicalized.json")
    parser.add_argument(
        "--provider",
        choices=("openai", "ollama"),
        default="ollama",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("ANSWER_MODEL", "qwen2.5:1.5b"),
        help="Answer model to rerun for null MCQs. Default: ANSWER_MODEL or qwen2.5:1.5b.",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--verse-window", type=int, default=2)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--allow-partial-answers", action="store_true", default=True)
    parser.add_argument("--ollama-no-think", action="store_true")
    parser.add_argument("--expanded-answer-format", action="store_true")
    parser.add_argument(
        "--mcq-choice-mapper",
        choices=("rules", "openai"),
        default=os.getenv("MCQ_CHOICE_MAPPER", "openai"),
        help="Use rules only, or rules plus OpenAI closest-choice fallback. Default: openai.",
    )
    parser.add_argument(
        "--mcq-choice-model",
        default=os.getenv("OPENAI_MCQ_CHOICE_MODEL", "gpt-4.1-mini"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_answer_files(args)
    if not files:
        print("no answer files found")
        return 1

    totals = {
        "files": 0,
        "changed_files": 0,
        "null": 0,
        "rerun": 0,
        "updated": 0,
        "failed": 0,
    }
    for path in files:
        stats = rerun_file(path, args)
        totals["files"] += 1
        totals["changed_files"] += stats["changed"]
        for key in ("null", "rerun", "updated", "failed"):
            totals[key] += stats[key]
        if stats["null"]:
            action = "would rerun" if args.dry_run else "reran"
            print(
                f"{action}: {path} "
                f"null={stats['null']} "
                f"rerun={stats['rerun']} "
                f"updated={stats['updated']} "
                f"failed={stats['failed']}"
            )

    print(json.dumps(totals, ensure_ascii=False, indent=2))
    return 0 if totals["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
