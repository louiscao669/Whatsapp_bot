#!/usr/bin/env python3
"""Generate chapter-specific mistranslation banks with an LLM.

The output is still a deterministic substitution bank. The LLM only proposes
candidate same-role substitutions; this script validates and freezes them.
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

# Decanonicalization placeholders: a short Chinese stem plus a \u5929\u5e72 suffix or a
# two-digit index (\u4eba\u7269\u7532, \u81f3\u9ad8\u8005\u7532, \u89d2\u827203, \u7fa4\u4f5305). Stem length is ambiguous -- in
# "\u5929\u4f7f \u89d2\u827206" a greedy 3-char stem would read "\u4f7f\u89d2\u827206" -- so we anchor on the
# SUFFIX and test every stem length, treating the token as resolved if any
# reading is known. Guessing a single stem length produces false positives.
PLACEHOLDER_SUFFIX_PATTERN = re.compile(r"(?:[\u7532\u4e59\u4e19\u4e01\u620a\u5df1\u5e9a\u8f9b\u58ec\u7678]|\d{2})(?![\u4e00-\u9fff])")
MAX_STEM_CHARS = 3
# Ordinary words the suffix scan can otherwise reach (\u5df1 is a \u5929\u5e72 character).
NON_PLACEHOLDER_WORDS = {"\u81ea\u5df1", "\u77e5\u5df1", "\u5f02\u5df1", "\u5229\u5df1", "\u800c\u5df2"}

VALID_MODES = {"systematic", "contextual"}
VALID_CATEGORIES = {
    "entity",
    "role",
    "location",
    "time",
    "number_time",
    "action",
    "attribute",
    "term",
    "theological_term",
    "semantic_substitution",
}


class BankGenerationError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise BankGenerationError(f"File not found: {path}")
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


def _token_readings(text: str, match: re.Match) -> list[str]:
    """Every stem+suffix reading of a placeholder ending at ``match``, short first."""
    readings = []
    for n in range(1, MAX_STEM_CHARS + 1):
        start = match.start() - n
        if start < 0:
            break
        stem = text[start:match.start()]
        if not all("一" <= c <= "鿿" for c in stem):
            break
        readings.append(stem + match.group(0))
    return readings


def unresolved_tokens(text: str, known) -> list[str]:
    """Placeholder-shaped tokens in ``text`` with no reading present in ``known``.

    ``known`` may be the passage (substring test) or a remap (key test).
    """
    bad = set()
    for m in PLACEHOLDER_SUFFIX_PATTERN.finditer(text or ""):
        readings = _token_readings(text, m)
        if not readings:
            continue
        if any(r in NON_PLACEHOLDER_WORDS for r in readings):
            continue
        if any(r in known for r in readings):
            continue
        bad.add(max(readings, key=len))
    return sorted(bad)


def invented_placeholders(target: str, passage: str) -> list[str]:
    """Placeholder tokens in ``target`` that do not exist in the passage.

    The bank is meant to swap one *existing* entity for another (人物甲 -> 人物乙
    is fine when both are real characters in the chapter). What it must never do
    is mint a token the decanonicalizer never issued -- 角色03 -> 角色04,
    至高者甲 -> 明主甲 -- because the pseudonym remap is built from the chapter's
    own entity mapping and has no entry for the invented token, so it survives
    into the participant-facing text as raw scaffolding.
    """
    return unresolved_tokens(target, passage)


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
    raise BankGenerationError("OpenAI response did not include text output.")


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
        raise BankGenerationError("LLM bank response must be a JSON object.")
    return data


def build_prompt(chapter: int, passage: str, max_items: int) -> str:
    return f"""
You are creating a controlled mistranslation substitution bank for an MQM
Accuracy > Mistranslation experiment.

Task:
- Read the Chinese Luke chapter passage below.
- Propose up to {max_items} substitution entries.
- Each entry must replace an exact source phrase that appears in the passage
  with a fluent same-role target phrase.
- The substitution should change meaning, but should not add content, omit
  content, damage grammar, change style/register, or paraphrase the sentence.

Classify each entry:
- mode = "systematic" when a translation model would likely make the same
  wrong mapping every time that source phrase appears. Use this mostly for
  entities, roles, places, and repeated terms.
- mode = "contextual" when the mistranslation is local to one occurrence or
  depends on sentence context. Use this mostly for actions, attributes, time,
  numbers, and short phrases.

Allowed categories:
entity, role, location, time, number_time, action, attribute, term,
theological_term, semantic_substitution.

Rules:
- source must appear exactly in the passage.
- source and target must not contain protected placeholders like __PERSON_A__.
- The passage uses anonymised entity tokens (人物甲, 至高者甲, 角色03, 群体05).
  NEVER invent a token that is not already in the passage. 角色03 -> 角色04 and
  至高者甲 -> 明主甲 are FORBIDDEN, because 角色04 and 明主甲 do not exist.
  To substitute one entity for another, the target token must itself appear
  somewhere in the passage (人物甲 -> 人物乙 is allowed only if 人物乙 is present).
  When in doubt, substitute an ordinary Chinese word instead of a token.
- Do not use punctuation-only, function-word-only, or extremely broad sources.
- Prefer source phrases with 2-8 Chinese characters when possible.
- For systematic entries, target should fit all occurrences of source in this
  chapter reasonably well.
- For contextual entries, source may be a longer local phrase that appears once.
- Return JSON only. No Markdown.

Output schema:
{{
  "schema_version": 1,
  "chapter": {chapter},
  "language": "zh",
  "description": "chapter-specific LLM-assisted MQM mistranslation bank",
  "replacements": [
    {{
      "source": "牧羊人",
      "target": "渔夫",
      "category": "entity",
      "mode": "systematic",
      "rationale": "same-role entity substitution"
    }}
  ]
}}

Passage:
{passage}
""".strip()


def generate_bank_with_openai(
    *,
    client: Any,
    model: str,
    chapter: int,
    passage: str,
    max_items: int,
) -> dict:
    response = client.responses.create(
        model=model,
        input=build_prompt(chapter, passage, max_items),
        temperature=0.2,
    )
    return extract_json_object(extract_response_text(response))


def normalize_replacement(item: dict, passage: str) -> dict | None:
    source = str(item.get("source") or "").strip()
    target = str(item.get("target") or "").strip()
    if not source or not target or source == target:
        return None
    if source not in passage:
        return None
    if has_protected_token(source) or has_protected_token(target):
        return None
    if invented_placeholders(target, passage):
        return None
    if content_len(source) == 0 or content_len(target) == 0:
        return None
    if content_len(source) > 24 or content_len(target) > 30:
        return None

    category = str(item.get("category") or "semantic_substitution").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "semantic_substitution"
    mode = str(item.get("mode") or "").strip().lower()
    if mode not in VALID_MODES:
        mode = "systematic" if category in {"entity", "role", "location", "term", "theological_term"} else "contextual"

    occurrence_count = passage.count(source)
    return {
        "source": source,
        "target": target,
        "category": category,
        "mode": mode,
        "rationale": str(item.get("rationale") or "").strip(),
        "source_content_chars": content_len(source),
        "target_content_chars": content_len(target),
        "occurrence_count": occurrence_count,
    }


def validate_bank(data: dict, *, chapter: int, passage: str, model: str) -> dict:
    raw_replacements = data.get("replacements")
    if not isinstance(raw_replacements, list):
        raise BankGenerationError("LLM output missing replacements list.")

    replacements = []
    seen = set()
    minted = []
    for item in raw_replacements:
        if not isinstance(item, dict):
            continue
        bad = invented_placeholders(str(item.get("target") or ""), passage)
        if bad:
            minted.append(f"{item.get('source')} -> {item.get('target')} [{','.join(bad)}]")
        normalized = normalize_replacement(item, passage)
        if not normalized:
            continue
        key = (
            normalized["source"],
            normalized["target"],
            normalized["mode"],
        )
        if key in seen:
            continue
        seen.add(key)
        replacements.append(normalized)

    if minted:
        print(
            f"  ch{chapter}: dropped {len(minted)} entry(ies) minting placeholder tokens "
            f"absent from the passage:",
            file=sys.stderr,
        )
        for row in minted:
            print(f"    {row}", file=sys.stderr)

    if not replacements:
        raise BankGenerationError("No valid replacements survived validation.")

    replacements.sort(
        key=lambda row: (
            row["mode"] != "systematic",
            -int(row["occurrence_count"]),
            -int(row["source_content_chars"]),
            row["source"],
        )
    )
    return {
        "schema_version": 1,
        "chapter": chapter,
        "language": "zh",
        "description": (
            "Chapter-specific LLM-assisted MQM mistranslation bank. "
            "Systematic entries are applied to all occurrences when selected; "
            "contextual entries are applied occurrence-by-occurrence."
        ),
        "generation": {
            "provider": "openai",
            "model": model,
            "validated_at_unix": int(time.time()),
        },
        "replacements": replacements,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate chapter-specific LLM-assisted mistranslation banks."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--output-name",
        default="mistranslation_bank_zh.json",
        help="Filename written under each chapter's <source-model-dir>/_shared folder.",
    )
    parser.add_argument(
        "--passage-file",
        choices=("passage_target_decanonicalized.txt", "passage_target.txt"),
        default="passage_target_decanonicalized.txt",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_EVALUATION_MODEL")
        or os.getenv("OPENAI_TRANSLATION_MODEL")
        or "gpt-4.1-mini",
    )
    parser.add_argument("--max-items", type=int, default=80)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("Install the openai package before running this script.") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required.")

    client = OpenAI()
    for chapter in args.chapters:
        source_model_dir = args.root / f"luke{chapter}" / args.source_model_dir
        source_method_dir = source_model_dir / args.source_method
        passage_path = source_method_dir / args.passage_file
        if not passage_path.exists() and args.passage_file == "passage_target_decanonicalized.txt":
            passage_path = source_method_dir / "passage_target.txt"
        output_path = source_model_dir / "_shared" / args.output_name
        if output_path.exists() and not args.force:
            print(f"reuse mistranslation bank: {output_path}")
            continue
        try:
            passage = load_text(passage_path)
            raw_bank = generate_bank_with_openai(
                client=client,
                model=args.model,
                chapter=chapter,
                passage=passage,
                max_items=args.max_items,
            )
            bank = validate_bank(
                raw_bank,
                chapter=chapter,
                passage=passage,
                model=args.model,
            )
            bank["source"] = {
                "source_method_dir": str(source_method_dir),
                "passage_file": str(passage_path),
            }
            write_json(output_path, bank)
            print(
                f"wrote mistranslation bank: {output_path} "
                f"({len(bank['replacements'])} replacements)"
            )
        except Exception as exc:
            print(f"warning: failed chapter {chapter}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
