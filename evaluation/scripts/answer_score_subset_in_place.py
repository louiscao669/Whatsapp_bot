#!/usr/bin/env python3
"""Answer and score a question subset into existing method folders.

This is an incremental runner for artifact folders that already contain
passage_target_decanonicalized.txt and qa_target_decanonicalized.json. It selects
N source question records per chapter, answers only missing/unscored target
items by default, scores them, and merges the scored rows into the method's
scores_target_llama.json.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.agents.generate_chinese_answers import (
    GenerationError,
    generate_answers,
    load_passage,
    public_questions,
)
from evaluation.scripts.score_generated_answers import (
    ScoreError,
    backtranslate_generated_answers,
    extract_items,
    score_items,
    summarize,
)


DEFAULT_CHAPTERS = list(range(1, 9))
DEFAULT_STANDARD_TEMPLATE = "evaluation/datasets/qa_output_luke_ch{chapter}_all_formats.json"
DEFAULT_ARTIFACT_ROOT_TEMPLATE = "evaluation/outputs/luke{chapter}/local_inconsistency"
CHOICE_FORMATS = {"open", "mcq"}


class SubsetRunError(Exception):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SubsetRunError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SubsetRunError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def optional_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item for item in data["items"] if isinstance(item, dict)]
    return extract_items(data)


def strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix) :] if value.startswith(prefix) else value


def base_question_id(item: dict, fallback_index: int) -> str:
    for key in ("content_id", "id", "passage_id", "qa_item_id", "item_id"):
        value = item.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            text = strip_prefix(text, "uw-")
            for suffix in ("-open", "-mcq"):
                if text.endswith(suffix):
                    text = text[: -len(suffix)]
            return text
    return f"index:{fallback_index}"


def item_format(item: dict) -> str | None:
    q_type = str(item.get("q_type") or item.get("question_type") or "").strip().lower()
    if q_type in CHOICE_FORMATS:
        return q_type
    text = str(item.get("passage_id") or item.get("id") or item.get("content_id") or "")
    if text.endswith("-open"):
        return "open"
    if text.endswith("-mcq"):
        return "mcq"
    if isinstance(item.get("A"), dict):
        return "mcq"
    return None


def full_item_key(item: dict, fallback_index: int) -> str:
    for key in ("id", "passage_id", "content_id", "qa_item_id", "item_id"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return f"{base_question_id(item, fallback_index)}:{item_format(item) or 'unknown'}"


def filter_by_base_ids(
    items: list[dict],
    base_ids: set[str],
    *,
    formats: set[str] | None,
) -> list[dict]:
    selected = []
    for index, item in enumerate(items, start=1):
        if base_question_id(item, index) not in base_ids:
            continue
        fmt = item_format(item)
        if formats is not None and fmt is not None and fmt not in formats:
            continue
        selected.append(item)
    return selected


def ordered_source_base_ids(standard_items: list[dict]) -> list[str]:
    output = []
    seen = set()
    for index, item in enumerate(standard_items, start=1):
        key = base_question_id(item, index)
        if key not in seen:
            seen.add(key)
            output.append(key)
    return output


def scored_full_keys(score_items_existing: list[dict]) -> set[str]:
    return {
        full_item_key(item, index)
        for index, item in enumerate(score_items_existing, start=1)
    }


def empty_generation_error_keys(items: list[dict]) -> set[str]:
    return {
        full_item_key(item, index)
        for index, item in enumerate(items, start=1)
        if item.get("generation_error")
        and not str(item.get("generated_answer") or "").strip()
    }


def base_has_unscored_target(
    base_id: str,
    target_items: list[dict],
    scored_keys: set[str],
    *,
    formats: set[str] | None,
) -> bool:
    matching = filter_by_base_ids(target_items, {base_id}, formats=formats)
    if not matching:
        return False
    return any(
        full_item_key(item, index) not in scored_keys
        for index, item in enumerate(matching, start=1)
    )


def choose_base_ids(
    standard_items: list[dict],
    target_items: list[dict],
    score_items_existing: list[dict],
    *,
    count: int,
    seed: int,
    chapter: int,
    formats: set[str] | None,
    skip_scored: bool,
    allow_fewer: bool = False,
) -> list[str]:
    candidates = ordered_source_base_ids(standard_items)
    target_base_ids = {
        base_question_id(item, index)
        for index, item in enumerate(target_items, start=1)
        if formats is None or item_format(item) in formats or item_format(item) is None
    }
    candidates = [key for key in candidates if key in target_base_ids]
    if skip_scored:
        scored_keys = scored_full_keys(score_items_existing)
        candidates = [
            key
            for key in candidates
            if base_has_unscored_target(
                key,
                target_items,
                scored_keys,
                formats=formats,
            )
        ]
    if count > len(candidates):
        if allow_fewer:
            count = len(candidates)
        else:
            raise SubsetRunError(
                f"Luke {chapter}: requested {count} question(s), but only "
                f"{len(candidates)} candidate(s) are available."
            )
    rng = random.Random(seed + chapter)
    selected = set(rng.sample(candidates, count))
    return [key for key in candidates if key in selected]


def merge_items(existing: list[dict], new_items: list[dict]) -> list[dict]:
    merged = list(existing)
    positions = {
        full_item_key(item, index): index - 1
        for index, item in enumerate(merged, start=1)
    }
    for new_index, item in enumerate(new_items, start=1):
        key = full_item_key(item, new_index)
        if key in positions:
            merged[positions[key]] = item
        else:
            positions[key] = len(merged)
            merged.append(item)
    return merged


def parse_formats(values: list[str]) -> set[str] | None:
    normalized = {value.strip().lower() for value in values}
    if "both" in normalized or "all" in normalized:
        return None
    unknown = normalized - CHOICE_FORMATS
    if unknown:
        raise SubsetRunError(f"Unknown format value(s): {', '.join(sorted(unknown))}")
    return normalized


def answer_score_method_subset(
    *,
    chapter: int,
    method_dir: Path,
    standard_path: Path,
    count: int,
    seed: int,
    formats: set[str] | None,
    skip_scored: bool,
    args: argparse.Namespace,
) -> dict:
    passage_path = method_dir / "passage_target_decanonicalized.txt"
    qa_path = method_dir / "qa_target_decanonicalized.json"
    generated_path = method_dir / "generated_answers_target_llama.json"
    backtranslated_path = method_dir / "generated_answers_target_llama_backtranslated.json"
    scores_path = method_dir / "scores_target_llama.json"
    subset_dir = method_dir / "_subset_runs"

    if not passage_path.exists():
        raise SubsetRunError(f"Missing passage file: {passage_path}")
    if not qa_path.exists():
        raise SubsetRunError(f"Missing QA file: {qa_path}")

    standard_items = extract_items(load_json(standard_path))
    target_items = extract_items(load_json(qa_path))
    existing_scores = optional_items(scores_path)
    if args.only_empty_generation_errors:
        existing_generated = optional_items(generated_path)
        retry_keys = empty_generation_error_keys(existing_generated) | empty_generation_error_keys(
            existing_scores
        )
        selected_target_items = [
            item
            for index, item in enumerate(target_items, start=1)
            if full_item_key(item, index) in retry_keys
            and (
                formats is None
                or item_format(item) in formats
                or item_format(item) is None
            )
        ]
        base_ids = ordered_source_base_ids(selected_target_items)
        if count < len(base_ids):
            rng = random.Random(seed + chapter)
            selected_base_id_set = set(rng.sample(base_ids, count))
            base_ids = [key for key in base_ids if key in selected_base_id_set]
            selected_target_items = filter_by_base_ids(
                selected_target_items,
                set(base_ids),
                formats=formats,
            )
    else:
        base_ids = choose_base_ids(
            standard_items,
            target_items,
            existing_scores,
            count=count,
            seed=seed,
            chapter=chapter,
            formats=formats,
            skip_scored=skip_scored,
            allow_fewer=args.allow_fewer,
        )
        base_id_set = set(base_ids)
        selected_target_items = filter_by_base_ids(target_items, base_id_set, formats=formats)

    selected_standard_items = filter_by_base_ids(standard_items, set(base_ids), formats=None)

    if skip_scored and existing_scores and not args.only_empty_generation_errors:
        scored_keys = scored_full_keys(existing_scores)
        selected_target_items = [
            item
            for index, item in enumerate(selected_target_items, start=1)
            if full_item_key(item, index) not in scored_keys
        ]
    if not selected_target_items:
        return {
            "chapter": chapter,
            "method_dir": str(method_dir),
            "selected_base_question_ids": base_ids,
            "answered_item_count": 0,
            "new_score_item_count": 0,
            "merged_score_item_count": len(existing_scores),
            "scores_path": str(scores_path),
        }

    passage = load_passage(passage_path)
    questions = public_questions(selected_target_items)
    answers = generate_answers(
        passage,
        questions,
        provider=args.answer_provider,
        model=args.answer_model,
        ollama_base_url=args.ollama_base_url,
        batch_size=args.answer_batch_size,
        verse_window=None if args.answer_verse_window < 0 else args.answer_verse_window,
        retries=args.retries,
        dry_run=False,
        allow_partial_answers=args.allow_partial_answers,
        ollama_no_think=args.ollama_no_think,
        expanded_answer_format=args.expanded_answer_format,
        mcq_choice_mapper=args.mcq_choice_mapper,
        mcq_choice_model=args.mcq_choice_model,
    )
    backtranslated = backtranslate_generated_answers(
        answers,
        selected_standard_items,
        translation_model=args.translation_model,
        retries=args.retries,
        batch_size=args.backtranslation_batch_size,
    )
    scored = score_items(
        backtranslated,
        selected_standard_items,
        judge_model=args.judge_model,
        translation_model=args.translation_model,
        retries=args.retries,
        skip_llm=args.skip_llm,
        placeholder_standard_answers=True,
        judge_batch_size=args.judge_batch_size,
    )

    existing_generated = optional_items(generated_path)
    existing_backtranslated = optional_items(backtranslated_path)
    merged_generated = merge_items(existing_generated, answers)
    merged_backtranslated = merge_items(existing_backtranslated, backtranslated)
    merged_scores = merge_items(existing_scores, scored)

    write_json(generated_path, merged_generated)
    write_json(backtranslated_path, merged_backtranslated)
    write_json(
        scores_path,
        {
            "summary": summarize(merged_scores),
            "items": merged_scores,
        },
    )

    subset_name = f"luke{chapter}_{method_dir.name}_seed{args.seed}_n{count}"
    write_json(
        subset_dir / f"{subset_name}_metadata.json",
        {
            "chapter": chapter,
            "method_dir": str(method_dir),
            "standard_path": str(standard_path),
            "selected_base_question_ids": base_ids,
            "selected_target_item_count": len(selected_target_items),
            "new_score_item_count": len(scored),
            "merged_score_item_count": len(merged_scores),
            "scores_path": str(scores_path),
        },
    )

    return {
        "chapter": chapter,
        "method_dir": str(method_dir),
        "selected_base_question_ids": base_ids,
        "answered_item_count": len(answers),
        "new_score_item_count": len(scored),
        "merged_score_item_count": len(merged_scores),
        "scores_path": str(scores_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Select N questions per chapter, answer/score them, and merge the "
            "results into each method folder's scores_target_llama.json."
        )
    )
    parser.add_argument("questions_per_chapter", type=int)
    parser.add_argument(
        "--allow-fewer",
        action="store_true",
        help="If a chapter has fewer candidate questions than requested, use "
        "all of them instead of failing (chapter pools range 7-22).",
    )
    parser.add_argument("--chapters", type=int, nargs="+", default=DEFAULT_CHAPTERS)
    parser.add_argument("--methods", nargs="+", default=["name_5%"])
    parser.add_argument(
        "--artifact-root-template",
        default=DEFAULT_ARTIFACT_ROOT_TEMPLATE,
        help="Format string with {chapter}; method folders live below this root.",
    )
    parser.add_argument(
        "--standard-template",
        default=DEFAULT_STANDARD_TEMPLATE,
        help="Format string with {chapter} for the standard English QA JSON.",
    )
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["both"],
        help="Question formats to answer: both, open, mcq. Default: both.",
    )
    parser.add_argument(
        "--include-scored",
        action="store_true",
        help="Allow replacing already scored items. Default is to select unscored items.",
    )
    parser.add_argument(
        "--only-empty-generation-errors",
        action="store_true",
        help=(
            "Retry only existing items whose generated_answer is empty and "
            "generation_error is set. This replaces those failed rows in the "
            "generated/backtranslated/scores files."
        ),
    )
    parser.add_argument(
        "--answer-provider",
        choices=("openai", "ollama"),
        default=os.getenv("EVALUATOR_PROVIDER", "ollama"),
    )
    parser.add_argument("--answer-model", default="qwen3:1.7b")
    parser.add_argument(
        "--ollama-base-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    parser.add_argument("--ollama-no-think", action="store_true")
    parser.add_argument("--allow-partial-answers", action="store_true")
    parser.add_argument("--expanded-answer-format", action="store_true")
    parser.add_argument(
        "--answer-batch-size",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--answer-verse-window",
        type=int,
        default=2,
        help="Use -1 to send the full passage. local_passage fields still take precedence.",
    )
    parser.add_argument(
        "--mcq-choice-mapper",
        choices=("rules", "openai"),
        default=os.getenv("MCQ_CHOICE_MAPPER", "rules"),
    )
    parser.add_argument(
        "--mcq-choice-model",
        default=os.getenv("OPENAI_MCQ_CHOICE_MODEL", "gpt-4.1-mini"),
    )
    parser.add_argument(
        "--translation-model",
        default=os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini"),
    )
    parser.add_argument(
        "--judge-model",
        default=os.getenv("OPENAI_JUDGE_MODEL", "gpt-4.1-mini"),
    )
    parser.add_argument("--backtranslation-batch-size", type=int, default=20)
    parser.add_argument("--judge-batch-size", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="Optional path for a JSON summary of this subset run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.questions_per_chapter < 1:
        print("questions_per_chapter must be at least 1", file=sys.stderr)
        return 2
    if args.answer_verse_window < -1:
        print("--answer-verse-window must be -1 or greater", file=sys.stderr)
        return 2
    for field in ("answer_batch_size", "backtranslation_batch_size", "judge_batch_size"):
        if getattr(args, field) < 1:
            print(f"--{field.replace('_', '-')} must be at least 1", file=sys.stderr)
            return 2

    try:
        formats = parse_formats(args.formats)
        results = []
        for chapter in args.chapters:
            standard_path = Path(args.standard_template.format(chapter=chapter))
            artifact_root = Path(args.artifact_root_template.format(chapter=chapter))
            for method in args.methods:
                method_dir = artifact_root / method
                print(f"run subset: Luke {chapter} {method_dir}")
                result = answer_score_method_subset(
                    chapter=chapter,
                    method_dir=method_dir,
                    standard_path=standard_path,
                    count=args.questions_per_chapter,
                    seed=args.seed,
                    formats=formats,
                    skip_scored=not args.include_scored,
                    args=args,
                )
                results.append(result)
                print(
                    f"wrote {result['new_score_item_count']} new score item(s) "
                    f"to {result['scores_path']}"
                )
        if args.summary_json:
            write_json(args.summary_json, results)
    except (GenerationError, ScoreError, SubsetRunError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
