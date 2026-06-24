#!/usr/bin/env python3
"""Translate mixed open-QA/MCQ LLM output into Chinese JSON.

Input may be either the compact pipeline shape:

  {"q_type": "open", "Q": "...", "A": "..."}
  {"q_type": "mcq", "Q": "...", "A": {"A": "...", "B": "...", "C": "...", "D": "..."}}

or the app's native QA-item shape with question_text/expected_answer/question_type.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


CHOICE_LABELS = ("A", "B", "C", "D")
QUESTION_TYPE_ALIASES = {
    "open": "open",
    "mcq": "mcq",
    "multiple_choice": "mcq",
    "multiple-choice": "mcq",
}


class TranslationError(Exception):
    pass


def load_json(path: Path) -> List[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TranslationError(f"Invalid JSON in {path}: {exc}") from exc

    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    raise TranslationError("Input JSON must be an object or an array of objects.")


def compact_choices(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        choices = {
            label: str(raw.get(label) or raw.get(label.lower()) or "").strip()
            for label in CHOICE_LABELS
        }
    elif isinstance(raw, list):
        choices = {
            label: str(raw[index]).strip() if index < len(raw) else ""
            for index, label in enumerate(CHOICE_LABELS)
        }
    else:
        choices = {label: "" for label in CHOICE_LABELS}

    missing = [label for label, text in choices.items() if not text]
    if missing:
        raise TranslationError(f"MCQ choices missing labels: {', '.join(missing)}")
    return choices


def answer_from_tagged_content(content: Any) -> Optional[str]:
    match = re.search(r"<answer>\s*(.*?)\s*<answer>", str(content or ""), re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def question_from_tagged_content(content: Any) -> Optional[str]:
    match = re.search(r"<question>\s*(.*?)\s*<question>", str(content or ""), re.DOTALL)
    if not match:
        return None
    question = re.sub(r"\n\s*[A-D]\.\s+.*$", "", match.group(1).strip(), flags=re.DOTALL)
    return question.strip() or None


def all_format_variants(item: dict) -> List[dict]:
    variants = []
    for q_type in ("open", "mcq"):
        nested = item.get(q_type)
        if not isinstance(nested, dict):
            continue
        merged = {
            key: value
            for key, value in item.items()
            if key not in {"open", "mcq"}
        }
        merged.update(nested)
        merged["q_type"] = q_type
        base_id = item.get("content_id") or item.get("id") or item.get("passage_id")
        if base_id:
            merged["content_id"] = f"{base_id}-{q_type}"
            merged["passage_id"] = f"uw-{base_id}-{q_type}"
        variants.append(merged)
    return variants


def normalize_item(item: dict, index: int) -> dict:
    q_type = (
        item.get("q_type")
        or item.get("question_type")
        or ("mcq" if item.get("mcq_choices") else "open")
    )
    q_type = str(q_type).strip().lower()
    q_type = QUESTION_TYPE_ALIASES.get(q_type, q_type)
    if q_type not in {"open", "mcq"}:
        raise TranslationError(
            f"Item {index}: q_type/question_type must be 'open' or 'mcq'."
        )

    question = (
        item.get("Q")
        or item.get("question_text")
        or item.get("question")
        or item.get("mcq_stem")
        or item.get("original_question")
        or question_from_tagged_content(item.get("content"))
    )
    question = str(question or "").strip()
    if not question:
        raise TranslationError(f"Item {index}: question text is required.")

    normalized = {"q_type": q_type, "Q": question}
    if q_type == "open":
        answer = item.get("A")
        if answer is None:
            answer = (
                item.get("expected_answer")
                or item.get("answer")
                or item.get("original_answer")
                or answer_from_tagged_content(item.get("content"))
            )
        answer = str(answer or "").strip()
        if not answer:
            raise TranslationError(f"Item {index}: open answer is required.")
        normalized["A"] = answer
    else:
        raw_choices = item.get("A")
        if raw_choices is None:
            raw_choices = (
                item.get("mcq_choices")
                or item.get("mcq_options")
                or item.get("choices")
            )
        normalized["A"] = compact_choices(raw_choices)

        correct = (
            item.get("correct")
            or item.get("correct_choice")
            or item.get("mcq_correct_choice")
        )
        if correct is None and item.get("expected_answer") is not None:
            expected_answer = str(item.get("expected_answer") or "").strip()
            for label, choice_text in normalized["A"].items():
                if expected_answer and expected_answer == choice_text:
                    correct = label
                    break
        if correct is None:
            tagged_answer = answer_from_tagged_content(item.get("content"))
            if tagged_answer:
                correct = tagged_answer
        if correct is not None:
            correct = str(correct).strip().upper()
            if correct not in CHOICE_LABELS:
                raise TranslationError(f"Item {index}: correct choice must be A, B, C, or D.")
            normalized["correct"] = correct

    for field in (
        "passage_id",
        "passage_reference",
        "passage_text",
        "audio_url",
        "required_keywords",
        "optional_keywords",
        "min_responses_required",
        "active",
        "review_priority",
    ):
        if field in item:
            normalized[field] = item[field]
    if "passage_id" not in normalized and item.get("content_id"):
        normalized["passage_id"] = f"uw-{item['content_id']}"
    if "passage_reference" not in normalized and item.get("title"):
        normalized["passage_reference"] = item["title"]
    return normalized


def normalize_items(items: Iterable[dict]) -> List[dict]:
    normalized = []
    index = 1
    for item in items:
        variants = all_format_variants(item)
        if not variants:
            variants = [item]
        for variant in variants:
            normalized.append(normalize_item(variant, index))
            index += 1
    return normalized


def batched(items: List[dict], batch_size: int) -> Iterable[List[dict]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text

    chunks = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    if chunks:
        return "\n".join(chunks)
    raise TranslationError("Model response did not include text output.")


def translate_batch(client: Any, model: str, batch: List[dict], target_language: str) -> List[dict]:
    prompt = {
        "task": (
            f"Translate questions into {target_language}. "
            "Preserve item order, q_type, choice labels, metadata fields, and any correct letter. "
            "For open questions, translate Q only and leave A exactly as the original English answer. "
            "For MCQ, translate Q and the A choice values because choices are part of the question; "
            "do not translate A/B/C/D keys. "
            "Preserve protected placeholder tokens such as __PERSON_A__, "
            "__MOST_HIGH_A__, __MASTER_A__, __SPIRIT_A__, __PLACE_A__, and "
            "__MATERIAL_A__ exactly; do not translate, transliterate, remove, or alter them. "
            "Return JSON only, as an array of objects with the same compact schema."
        ),
        "items": batch,
    }
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a precise translation engine. Return valid JSON only. "
                    "Do not add explanations or markdown."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    try:
        translated = json.loads(extract_response_text(response))
    except json.JSONDecodeError as exc:
        raise TranslationError(f"Model returned invalid JSON: {exc}") from exc

    if not isinstance(translated, list):
        raise TranslationError("Model response must be a JSON array.")
    normalized = normalize_items(translated)
    if len(normalized) != len(batch):
        raise TranslationError(
            f"Model returned {len(normalized)} item(s), expected {len(batch)}."
        )
    for original, translated_item in zip(batch, normalized):
        if original["q_type"] == "open":
            translated_item["A"] = original["A"]
    return normalized


def translate_items(
    items: List[dict],
    *,
    model: str,
    target_language: str,
    batch_size: int,
    retries: int,
    dry_run: bool,
) -> List[dict]:
    if dry_run:
        return items

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise TranslationError("Install the openai package before running this script.") from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise TranslationError("OPENAI_API_KEY is required unless --dry-run is used.")

    client = OpenAI()
    output: List[dict] = []
    for batch in batched(items, batch_size):
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                output.extend(translate_batch(client, model, batch, target_language))
                last_error = None
                break
            except Exception as exc:  # OpenAI SDK exceptions vary by version.
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(2**attempt)
        if last_error:
            raise TranslationError(str(last_error)) from last_error
    return output


def to_native_items(items: List[dict]) -> List[dict]:
    native = []
    for index, item in enumerate(items, start=1):
        passage_id = str(item.get("passage_id") or f"translated-{index}").strip()
        entry = {
            "passage_id": passage_id,
            "passage_reference": item.get("passage_reference") or passage_id,
            "passage_text": item.get("passage_text"),
            "question_type": item["q_type"],
            "question_text": item["Q"],
            "expected_answer": "",
            "mcq_choices": [],
            "mcq_correct_choice": None,
        }
        if item["q_type"] == "open":
            entry["expected_answer"] = item["A"]
        else:
            choices = item["A"]
            entry["mcq_choices"] = [choices[label] for label in CHOICE_LABELS]
            correct = item.get("correct")
            if not correct:
                raise TranslationError(
                    f"Item {index}: --format native requires a correct choice for MCQs."
                )
            entry["mcq_correct_choice"] = correct
            entry["expected_answer"] = choices[correct]

        for field in (
            "audio_url",
            "required_keywords",
            "optional_keywords",
            "min_responses_required",
            "active",
            "review_priority",
        ):
            if field in item:
                entry[field] = item[field]
        native.append(entry)
    return native


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate mixed open-QA/MCQ JSON output into Chinese."
    )
    parser.add_argument("input_json", type=Path, help="Input JSON file.")
    parser.add_argument("output_json", type=Path, help="Output JSON file.")
    parser.add_argument(
        "--target-language",
        default="Simplified Chinese",
        help="Translation target language. Default: Simplified Chinese.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini"),
        help="OpenAI model to use. Default: OPENAI_TRANSLATION_MODEL or gpt-4.1-mini.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Items to translate per model call. Default: 20.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retry count per batch. Default: 2.",
    )
    parser.add_argument(
        "--format",
        choices=("compact", "native"),
        default="compact",
        help="Output compact {q_type,Q,A} JSON or native importer JSON. Default: compact.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Normalize and write input shape without calling the model.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        print("--batch-size must be at least 1", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("--retries must be zero or greater", file=sys.stderr)
        return 2

    try:
        items = normalize_items(load_json(args.input_json))
        translated = translate_items(
            items,
            model=args.model,
            target_language=args.target_language,
            batch_size=args.batch_size,
            retries=args.retries,
            dry_run=args.dry_run,
        )
        output = to_native_items(translated) if args.format == "native" else translated
        write_json(args.output_json, output)
    except TranslationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(translated)} translated item(s) to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
