#!/usr/bin/env python3
"""Repair null MCQ selected_choice values in existing answer outputs.

This script does not call the answer model again. It reads existing
generated_answers_target_l*.json files, finds MCQ items where selected_choice is
null/empty, and maps the saved raw_model_answer to the closest A-D choice.
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
    CHOICE_LABELS,
    GenerationError,
    clean_raw_answer,
    openai_closest_mcq_choice,
    selected_choice_from_raw_answer,
)


DEFAULT_ANSWER_FILE = "generated_answers_target_llama.json"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def selected_is_null(item: dict) -> bool:
    return item.get("selected_choice") in (None, "")


def usable_choices(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    choices = {
        label: str(value.get(label) or "").strip()
        for label in CHOICE_LABELS
    }
    if all(choices.values()):
        return choices
    return None


def raw_answer_for_item(item: dict) -> str:
    raw = item.get("raw_model_answer")
    if raw not in (None, ""):
        return clean_raw_answer(str(raw))
    generated = item.get("generated_answer")
    if generated not in (None, ""):
        return clean_raw_answer(str(generated))
    return ""


def discover_answer_files(args: argparse.Namespace) -> list[Path]:
    if args.files:
        return sorted({Path(path) for path in args.files})

    roots: list[Path] = []
    for chapter in args.chapters:
        chapter_root = args.root / f"luke{chapter}"
        if not chapter_root.exists():
            continue
        if args.model_dirs:
            roots.extend(chapter_root / model_dir for model_dir in args.model_dirs)
        else:
            roots.extend(path for path in chapter_root.iterdir() if path.is_dir())

    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if args.methods:
            files.extend(root / method / args.answer_file for method in args.methods)
        else:
            files.extend(root.glob(f"*/{args.answer_file}"))
    return sorted({path for path in files if path.exists()})


def make_openai_client(args: argparse.Namespace) -> Any | None:
    if args.mapper != "openai":
        return None
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise GenerationError("Install the openai package before using --mapper openai.") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise GenerationError("OPENAI_API_KEY is required for --mapper openai.")
    return OpenAI()


def repair_file(
    path: Path,
    *,
    mapper: str,
    openai_client: Any | None,
    openai_model: str,
    retries: int,
    dry_run: bool,
) -> dict[str, int]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list of answer items.")

    stats = {
        "mcq_null": 0,
        "repaired_rules": 0,
        "repaired_openai": 0,
        "skipped_missing_raw": 0,
        "skipped_missing_choices": 0,
        "failed": 0,
    }
    changed = False

    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("q_type") != "mcq" or not selected_is_null(item):
            continue
        stats["mcq_null"] += 1

        choices = usable_choices(item.get("mcq_choices"))
        if not choices:
            stats["skipped_missing_choices"] += 1
            continue

        raw_answer = raw_answer_for_item(item)
        if not raw_answer:
            stats["skipped_missing_raw"] += 1
            continue

        question = {
            "item_index": item.get("item_index"),
            "q_type": "mcq",
            "question": item.get("question") or "",
            "choices": choices,
        }

        choice = selected_choice_from_raw_answer(question, raw_answer)
        source = "rules"
        if not choice and mapper == "openai":
            try:
                choice = openai_closest_mcq_choice(
                    openai_client,
                    openai_model,
                    raw_answer=raw_answer,
                    choices=choices,
                    retries=retries,
                )
                source = "openai"
            except Exception as exc:
                item["mcq_choice_repair_error"] = str(exc)
                stats["failed"] += 1
                changed = True
                continue

        if not choice:
            stats["failed"] += 1
            continue

        if item.get("generation_error"):
            item["previous_generation_error"] = item.get("generation_error")
            item.pop("generation_error", None)
        item["generated_answer"] = choices[choice]
        item["selected_choice"] = choice
        item["selected_choice_text"] = choices[choice]
        item["selected_choice_source"] = source
        item["raw_model_answer"] = raw_answer
        item["mcq_choice_repaired"] = True
        item["mcq_choice_repair_source"] = source
        item.pop("mcq_choice_repair_error", None)
        stats[f"repaired_{source}"] += 1
        changed = True

    if changed and not dry_run:
        write_json(path, data)
    stats["changed"] = int(changed)
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Repair existing generated-answer files by filling null MCQ "
            "selected_choice values from raw_model_answer."
        )
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Specific generated_answers_target_llama.json files to repair.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("evaluation/outputs"),
        help="Evaluation output root used when files are not passed.",
    )
    parser.add_argument(
        "--chapters",
        nargs="+",
        default=[str(chapter) for chapter in range(1, 9)],
        help="Luke chapter numbers to scan when files are not passed.",
    )
    parser.add_argument(
        "--model-dirs",
        nargs="+",
        default=None,
        help='Model output dirs under each chapter, e.g. "llama 1b" 1.7b.',
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=None,
        help="Method dirs to repair. Default scans all method dirs.",
    )
    parser.add_argument(
        "--answer-file",
        default=DEFAULT_ANSWER_FILE,
        help=f"Answer filename to repair. Default: {DEFAULT_ANSWER_FILE}.",
    )
    parser.add_argument(
        "--mapper",
        choices=("rules", "openai"),
        default="openai",
        help="Use rules only, or rules then OpenAI closest-choice fallback.",
    )
    parser.add_argument(
        "--openai-model",
        default=os.getenv("OPENAI_MCQ_CHOICE_MODEL", "gpt-4.1-mini"),
        help="OpenAI model for --mapper openai.",
    )
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_answer_files(args)
    if not files:
        print("no answer files found")
        return 1

    openai_client = make_openai_client(args)
    totals = {
        "files": 0,
        "changed_files": 0,
        "mcq_null": 0,
        "repaired_rules": 0,
        "repaired_openai": 0,
        "skipped_missing_raw": 0,
        "skipped_missing_choices": 0,
        "failed": 0,
    }
    for path in files:
        stats = repair_file(
            path,
            mapper=args.mapper,
            openai_client=openai_client,
            openai_model=args.openai_model,
            retries=args.retries,
            dry_run=args.dry_run,
        )
        totals["files"] += 1
        totals["changed_files"] += stats["changed"]
        for key in (
            "mcq_null",
            "repaired_rules",
            "repaired_openai",
            "skipped_missing_raw",
            "skipped_missing_choices",
            "failed",
        ):
            totals[key] += stats[key]
        if stats["mcq_null"]:
            action = "would update" if args.dry_run else "updated"
            print(
                f"{action}: {path} "
                f"null={stats['mcq_null']} "
                f"rules={stats['repaired_rules']} "
                f"openai={stats['repaired_openai']} "
                f"failed={stats['failed']}"
            )

    print(json.dumps(totals, ensure_ascii=False, indent=2))
    return 0 if totals["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
