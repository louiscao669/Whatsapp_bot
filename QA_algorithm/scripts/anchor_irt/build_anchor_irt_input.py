#!/usr/bin/env python3
"""Build anchor IRT input JSON from existing scored model outputs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_MODELS = ("llama 1b", "1.5b", "1.7b")
DEFAULT_CHAPTERS = tuple(range(1, 9))
DEFAULT_METHOD = "llm_prompt_high"
SCORE_FILE = "scores_target_llama.json"


class AnchorInputBuildError(Exception):
    """Raised when score outputs cannot be converted to anchor IRT input."""


def load_json(path: Path) -> Any:
    """Load a JSON file with a clear error if it is missing."""
    if not path.exists():
        raise AnchorInputBuildError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def extract_items(data: Any) -> list[dict]:
    """Extract item dictionaries from a score or QA JSON payload."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "qa_items", "questions", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data]
    return []


def normalize_q_type(value: Any) -> str:
    """Normalize question type values to open or mcq."""
    raw = str(value or "").strip().lower()
    if raw in {"mcq", "multiple_choice", "multiple-choice"}:
        return "mcq"
    return "open"


def item_q_type(item: dict) -> str:
    """Return the scored item's normalized question type."""
    return normalize_q_type(item.get("q_type") or item.get("question_type"))


def include_q_type(item_type: str, requested: str) -> bool:
    """Return whether a question type should be included."""
    return requested == "all" or item_type == requested


def difficulty_label_from_bucket(value: Any) -> str | None:
    """Map dataset difficulty bucket labels to IRT labels."""
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    aliases = {
        "easy": "easy",
        "low": "easy",
        "simple": "easy",
        "median": "medium",
        "medium": "medium",
        "med": "medium",
        "moderate": "medium",
        "hard": "hard",
        "high": "hard",
        "difficult": "hard",
    }
    return aliases.get(raw)


def difficulty_label_from_value(value: Any) -> str | None:
    """Map numeric difficulty values to IRT labels when buckets are unavailable."""
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return "easy"
    if number <= 1:
        return "medium"
    return "hard"


def base_content_id(value: Any) -> str | None:
    """Normalize scored ids such as uw-174316-open to content id 174316."""
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("uw-"):
        text = text[3:]
    for suffix in ("-open", "-mcq"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text or None


def question_id_for_item(chapter: int, item: dict) -> str:
    """Build a stable question id for scored item rows."""
    item_type = item_q_type(item)
    item_index = str(item.get("item_index") or "").strip()
    if not item_index:
        raise AnchorInputBuildError(f"Could not build question id for item: {item}")
    return f"luke{chapter}:item{item_index}:{item_type}"


def qa_question_key(chapter: int, item_index: int, q_type: str) -> str:
    """Build the question id key for a source QA item and requested format."""
    return f"luke{chapter}:item{item_index}:{q_type}"


def source_question_text(item: dict, q_type: str) -> str:
    """Extract source-language question text from a source QA item."""
    nested = item.get(q_type)
    if isinstance(nested, dict):
        tagged = question_from_tagged_content(nested.get("content"))
        return str(
            nested.get("original_question")
            or nested.get("question")
            or nested.get("mcq_stem")
            or tagged
            or item.get("question")
            or ""
        ).strip()
    return str(item.get("question") or item.get("Q") or "").strip()


def source_correct_answer(item: dict, q_type: str) -> str:
    """Extract source-language correct answer from a source QA item."""
    nested = item.get(q_type)
    if isinstance(nested, dict):
        tagged = answer_from_tagged_content(nested.get("content"))
        if q_type == "mcq":
            options = nested.get("mcq_options") or []
            answer = nested.get("original_answer") or nested.get("answer")
            if answer:
                return str(answer).strip()
            correct = str(nested.get("correct") or "").strip().upper()
            labels = ("A", "B", "C", "D")
            if correct in labels:
                index = labels.index(correct)
                if index < len(options):
                    return str(options[index]).strip()
        return str(
            nested.get("original_answer")
            or nested.get("answer")
            or nested.get("expected_answer")
            or tagged
            or ""
        ).strip()
    return str(item.get("standard_answer") or item.get("answer") or "").strip()


def question_from_tagged_content(content: Any) -> str | None:
    """Extract text between <question> tags from generated QA content."""
    match = re.search(r"<question>\s*(.*?)\s*<question>", str(content or ""), re.DOTALL)
    if not match:
        return None
    question = re.sub(r"\n\s*[A-D]\.\s+.*$", "", match.group(1).strip(), flags=re.DOTALL)
    return question.strip() or None


def answer_from_tagged_content(content: Any) -> str | None:
    """Extract text between <answer> tags from generated QA content."""
    match = re.search(r"<answer>\s*(.*?)\s*<answer>", str(content or ""), re.DOTALL)
    if not match:
        return None
    return match.group(1).strip() or None


def source_difficulty_label(item: dict, q_type: str) -> str:
    """Extract or infer an IRT difficulty label from a source QA item."""
    nested = item.get(q_type)
    candidates = []
    if isinstance(nested, dict):
        candidates.append(nested)
    candidates.append(item)
    for candidate in candidates:
        label = difficulty_label_from_bucket(
            candidate.get("difficulty_bucket")
            or candidate.get("difficulty")
            or candidate.get("difficulty_label")
        )
        if label:
            return label
        label = difficulty_label_from_value(candidate.get("difficulty_value"))
        if label:
            return label
    return "medium"


def load_source_questions(
    *,
    qa_dir: Path,
    chapters: list[int],
    q_type: str,
) -> dict[str, dict]:
    """Load source QA metadata indexed by generated IRT question id."""
    questions = {}
    for chapter in chapters:
        path = qa_dir / f"qa_output_luke_ch{chapter}_all_formats.json"
        if not path.exists():
            continue
        expanded_index = 0
        for item in extract_items(load_json(path)):
            for current_type in ("open", "mcq"):
                expanded_index += 1
                if not include_q_type(current_type, q_type):
                    continue
                key = qa_question_key(chapter, expanded_index, current_type)
                questions[key] = {
                    "question_id": key,
                    "question_text": source_question_text(item, current_type),
                    "correct_answer": source_correct_answer(item, current_type),
                    "diffiel": source_difficulty_label(item, current_type),
                    "chapter": chapter,
                    "q_type": current_type,
                    "source_content_id": str(item.get("content_id") or ""),
                    "passage_reference": item.get("title"),
                }
    return questions


def score_item_correct(item: dict) -> bool | None:
    """Convert a scored output item to binary correctness."""
    q_type = item_q_type(item)
    if q_type == "mcq":
        value = item.get("direct_correct")
        if isinstance(value, bool):
            return value
        return None
    score = item.get("llm_score")
    if score is None:
        return None
    try:
        return float(score) >= 0.5
    except (TypeError, ValueError):
        return None


def score_path(root: Path, chapter: int, model: str, method: str) -> Path:
    """Return the score file path for a model/chapter/method."""
    return root / f"luke{chapter}" / model / method / SCORE_FILE


def build_anchor_irt_input(
    *,
    root: Path,
    qa_dir: Path,
    chapters: list[int],
    models: list[str],
    method: str,
    q_type: str,
) -> dict:
    """Build the anchor IRT input payload from scored answer files."""
    source_questions = load_source_questions(qa_dir=qa_dir, chapters=chapters, q_type=q_type)
    questions: dict[str, dict] = {}
    responses: list[dict] = []
    missing_score_files = []
    skipped_items = 0

    for chapter in chapters:
        for model in models:
            path = score_path(root, chapter, model, method)
            if not path.exists():
                missing_score_files.append(str(path))
                continue
            for item in extract_items(load_json(path)):
                current_type = item_q_type(item)
                if not include_q_type(current_type, q_type):
                    continue
                question_id = question_id_for_item(chapter, item)
                source_question = source_questions.get(question_id)
                if not source_question:
                    source_question = {
                        "question_id": question_id,
                        "question_text": str(item.get("question") or "").strip(),
                        "correct_answer": str(item.get("standard_answer") or "").strip(),
                        "diffiel": "medium",
                        "chapter": chapter,
                        "q_type": current_type,
                        "passage_reference": item.get("passage_reference"),
                    }
                questions[question_id] = source_question
                is_correct = score_item_correct(item)
                if is_correct is None:
                    skipped_items += 1
                    continue
                responses.append(
                    {
                        "model_id": model,
                        "question_id": question_id,
                        "response": str(item.get("generated_answer") or "").strip(),
                        "is_correct": bool(is_correct),
                    }
                )

    ordered_questions = sorted(
        questions.values(),
        key=lambda item: (int(item.get("chapter") or 0), str(item.get("question_id") or "")),
    )
    return {
        "anchor_passage": (
            "Gold-standard anchor responses converted from existing Luke 1-8 "
            f"{method} scored outputs."
        ),
        "questions": ordered_questions,
        "model_responses": responses,
        "metadata": {
            "source_root": str(root),
            "qa_dir": str(qa_dir),
            "chapters": chapters,
            "models": models,
            "method": method,
            "q_type": q_type,
            "missing_score_files": missing_score_files,
            "skipped_items_without_score": skipped_items,
            "question_count": len(ordered_questions),
            "response_count": len(responses),
        },
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Convert scored model outputs into anchor_irt_input.json."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--qa-dir", type=Path, default=Path("evaluation/datasets"))
    parser.add_argument("--chapters", type=int, nargs="+", default=list(DEFAULT_CHAPTERS))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--method", default=DEFAULT_METHOD)
    parser.add_argument(
        "--q-type",
        choices=("open", "mcq", "all"),
        default="open",
        help="Question type to include. Default: open.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("QA_algorithm/inputs/anchor_irt_input.json"),
    )
    return parser.parse_args()


def main() -> int:
    """Run the converter."""
    args = parse_args()
    payload = build_anchor_irt_input(
        root=args.root,
        qa_dir=args.qa_dir,
        chapters=args.chapters,
        models=args.models,
        method=args.method,
        q_type=args.q_type,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metadata = payload["metadata"]
    print(f"wrote: {args.output_json}")
    print(
        "questions={question_count} responses={response_count} skipped={skipped_items_without_score}".format(
            **metadata
        )
    )
    if metadata["missing_score_files"]:
        print(f"missing score files: {len(metadata['missing_score_files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
