#!/usr/bin/env python3
"""Generate chapter-specific awkward-style replacement banks with an LLM.

The LLM proposes candidate literalization replacements. This script validates
that each source phrase appears in the chapter and freezes the bank as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


CONTENT_CHAR_PATTERN = re.compile(r"[\w\u3400-\u9fff]")
PROTECTED_TOKEN_PATTERN = re.compile(r"__[A-Za-z0-9_]+__")
DEFAULT_MODEL = (
    os.getenv("OPENAI_BANK_MODEL")
    or os.getenv("OPENAI_EVALUATION_MODEL")
    or os.getenv("OPENAI_TRANSLATION_MODEL")
    or "gpt-4.1-mini"
)
DEFAULT_CATEGORIES = {
    "light_verb_inflation",
    "nominalization",
    "source_like_possessive",
    "redundant_explicitness",
    "literal_prepositional_padding",
    "awkward_passive_or_naming",
    "bible_domain_awkward",
}


class AwkwardBankError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise AwkwardBankError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def content_len(text: str) -> int:
    return len(CONTENT_CHAR_PATTERN.findall(text or ""))


def has_protected_token(text: str) -> bool:
    return bool(PROTECTED_TOKEN_PATTERN.search(text or ""))


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
    raise AwkwardBankError("OpenAI response did not include text output.")


def extract_json_object(text: str) -> dict:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise AwkwardBankError("LLM bank response must be a JSON object.")
    return data


def flatten_global_examples(global_bank: dict, limit: int = 20) -> list[dict]:
    examples = []
    categories = global_bank.get("categories", {}) if isinstance(global_bank, dict) else {}
    for category, value in categories.items():
        replacements = value.get("replacements", []) if isinstance(value, dict) else []
        for item in replacements:
            if not isinstance(item, dict):
                continue
            examples.append(
                {
                    "category": category,
                    "source": item.get("source"),
                    "target": item.get("target"),
                }
            )
            if len(examples) >= limit:
                return examples
    return examples


def build_prompt(
    *,
    chapter: int,
    target_passage: str,
    source_passage: str,
    examples: list[dict],
    max_items: int,
) -> str:
    return f"""
You are creating a chapter-specific replacement bank for an MQM Style > Awkward
experiment in Chinese Bible translation.

Goal:
- Propose up to {max_items} rule-based replacements for this exact Chinese
  translated chapter.
- Each replacement should make the Chinese sound awkward, literal, redundant,
  or translationese.
- The replacement must preserve the core meaning and answer-bearing facts.
- This is Style/Awkward only, not Accuracy, Omission, Addition, Grammar,
  Register, Inconsistency, or Untranslated text.

Allowed categories:
light_verb_inflation
nominalization
source_like_possessive
redundant_explicitness
literal_prepositional_padding
awkward_passive_or_naming
bible_domain_awkward

Rules:
- source must be an exact substring from the Chinese target passage.
- source must not contain protected placeholders like __PERSON_A__.
- target should also avoid protected placeholders unless the source has visible
  Chinese placeholder text that must be preserved.
- Do not change names, placeholders, numbers, negation, entities, or event facts.
- Do not omit information.
- Do not add new facts.
- Do not leave English/source text.
- Do not create ungrammatical text; create awkward but understandable Chinese.
- Prefer sources that are useful in this chapter and likely to occur in the text.
- Return JSON only. No Markdown.

Examples of the intended style:
{json.dumps(examples, ensure_ascii=False, indent=2)}

Output schema:
{{
  "schema_version": 1,
  "chapter": {chapter},
  "language": "zh",
  "description": "chapter-specific LLM-assisted MQM Style/Awkward bank",
  "categories": {{
    "light_verb_inflation": {{
      "replacements": [
        {{
          "source": "说",
          "target": "进行说话",
          "rationale": "literal light-verb construction"
        }}
      ]
    }}
  }}
}}

English source passage is provided only to help identify source-language
interference patterns. The source field must still come from the Chinese target.

English source passage:
{source_passage}

Chinese target passage:
{target_passage}
""".strip()


def get_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AwkwardBankError("Install the openai package to generate banks.") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise AwkwardBankError("OPENAI_API_KEY is required to generate banks.")
    return OpenAI()


def generate_bank_with_openai(
    *,
    client: Any,
    model: str,
    chapter: int,
    target_passage: str,
    source_passage: str,
    examples: list[dict],
    max_items: int,
) -> dict:
    response = client.responses.create(
        model=model,
        input=build_prompt(
            chapter=chapter,
            target_passage=target_passage,
            source_passage=source_passage,
            examples=examples,
            max_items=max_items,
        ),
        temperature=0.2,
    )
    return extract_json_object(extract_response_text(response))


def normalize_replacement(item: dict, target_passage: str) -> dict | None:
    source = str(item.get("source") or "").strip()
    target = str(item.get("target") or "").strip()
    if not source or not target or source == target:
        return None
    if source not in target_passage:
        return None
    if has_protected_token(source) or has_protected_token(target):
        return None
    if content_len(source) == 0 or content_len(target) == 0:
        return None
    if content_len(source) > 30 or content_len(target) > 60:
        return None
    return {
        "source": source,
        "target": target,
        "rationale": str(item.get("rationale") or "").strip(),
        "source_content_chars": content_len(source),
        "target_content_chars": content_len(target),
        "occurrence_count": target_passage.count(source),
    }


def validate_bank(
    data: dict,
    *,
    chapter: int,
    target_passage: str,
    source_file: Path,
    target_file: Path,
    model: str,
) -> dict:
    raw_categories = data.get("categories")
    if not isinstance(raw_categories, dict):
        raise AwkwardBankError("LLM output missing categories object.")

    categories = {}
    seen = set()
    for category, raw_value in raw_categories.items():
        category_name = str(category or "").strip()
        if category_name not in DEFAULT_CATEGORIES:
            continue
        replacements = []
        raw_replacements = (
            raw_value.get("replacements", []) if isinstance(raw_value, dict) else []
        )
        if not isinstance(raw_replacements, list):
            continue
        for item in raw_replacements:
            if not isinstance(item, dict):
                continue
            normalized = normalize_replacement(item, target_passage)
            if not normalized:
                continue
            key = (category_name, normalized["source"], normalized["target"])
            if key in seen:
                continue
            seen.add(key)
            replacements.append(normalized)
        if replacements:
            categories[category_name] = {
                "description": f"Chapter-specific {category_name} replacements.",
                "replacements": replacements,
            }

    total = sum(len(value["replacements"]) for value in categories.values())
    if total == 0:
        raise AwkwardBankError("No valid replacements remained after validation.")

    return {
        "schema_version": 1,
        "chapter": chapter,
        "language": "zh",
        "description": "chapter-specific LLM-assisted MQM Style/Awkward bank",
        "model": model,
        "source_file": str(source_file),
        "target_file": str(target_file),
        "validation": {
            "source_must_appear_in_target_passage": True,
            "protected_openai_placeholders_disallowed": True,
            "valid_replacement_count": total,
        },
        "categories": categories,
    }


def load_global_bank(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate chapter-specific awkward-style banks with an LLM."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/datasets/chapter_awkward_style_banks"),
    )
    parser.add_argument(
        "--global-bank",
        type=Path,
        default=Path("evaluation/datasets/awkward_style_bank.json"),
        help="Optional global bank used as examples.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-items", type=int, default=80)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_items < 1:
        print("--max-items must be at least 1", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("--retries must be zero or greater", file=sys.stderr)
        return 2

    try:
        client = get_openai_client()
        examples = flatten_global_examples(load_global_bank(args.global_bank))
        for chapter in args.chapters:
            output_path = args.output_dir / f"luke{chapter}_awkward_style_bank.json"
            if output_path.exists() and not args.force:
                print(f"reuse bank: {output_path}")
                continue

            method_dir = (
                args.root
                / f"luke{chapter}"
                / args.source_model_dir
                / args.source_method
            )
            source_file = method_dir / "passage_source_decanonicalized.txt"
            target_file = method_dir / "passage_target_decanonicalized.txt"
            source_passage = load_text(source_file)
            target_passage = load_text(target_file)

            last_error: Exception | None = None
            for attempt in range(args.retries + 1):
                try:
                    raw_bank = generate_bank_with_openai(
                        client=client,
                        model=args.model,
                        chapter=chapter,
                        target_passage=target_passage,
                        source_passage=source_passage,
                        examples=examples,
                        max_items=args.max_items,
                    )
                    bank = validate_bank(
                        raw_bank,
                        chapter=chapter,
                        target_passage=target_passage,
                        source_file=source_file,
                        target_file=target_file,
                        model=args.model,
                    )
                    write_json(output_path, bank)
                    count = bank["validation"]["valid_replacement_count"]
                    print(f"wrote bank: {output_path} ({count} replacements)")
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < args.retries:
                        time.sleep(2**attempt)
            if last_error:
                raise AwkwardBankError(
                    f"Failed to generate Luke {chapter} bank: {last_error}"
                ) from last_error
    except AwkwardBankError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
