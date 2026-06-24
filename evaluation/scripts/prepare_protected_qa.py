#!/usr/bin/env python3
"""Create compact QA JSON with protected source tokens.

This prepares mixed LLM QA output for translation by extracting q_type, Q, and A
and replacing canonical English terms with protected tokens such as
__PERSON_C__. The translation step later preserves those tokens, and the
decanonicalization step maps them to Chinese placeholders.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.decanonicalize_chinese_dataset import (  # noqa: E402
    DEFAULT_ENGLISH_TOKEN_MAPPING,
    replace_english_terms,
)
from evaluation.scripts.translate_llm_qa_to_chinese import (  # noqa: E402
    CHOICE_LABELS,
    TranslationError,
    load_json,
    normalize_items,
    write_json,
)


def protect_value(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return replace_english_terms(value, mapping)
    if isinstance(value, list):
        return [protect_value(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: protect_value(item, mapping) for key, item in value.items()}
    return value


def compact_protected_items(items: list[dict], mapping: dict[str, str]) -> list[dict]:
    protected = []
    for item in items:
        entry: dict[str, Any] = {
            "q_type": item["q_type"],
            "Q": protect_value(item["Q"], mapping),
        }
        if item["q_type"] == "open":
            entry["A"] = protect_value(item["A"], mapping)
        else:
            entry["A"] = {
                label: protect_value(item["A"][label], mapping)
                for label in CHOICE_LABELS
            }
            if "correct" in item:
                entry["correct"] = item["correct"]
        protected.append(entry)
    return protected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract q_type, question, and answer fields from mixed QA JSON and "
            "replace canonical English terms with protected tokens."
        )
    )
    parser.add_argument("input_json", type=Path, help="Input mixed QA JSON file.")
    parser.add_argument("output_json", type=Path, help="Output compact protected QA JSON.")
    parser.add_argument(
        "--mapping-json",
        type=Path,
        help=(
            "Optional JSON object mapping additional English source strings to "
            "protected tokens."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        mapping = dict(DEFAULT_ENGLISH_TOKEN_MAPPING)
        if args.mapping_json:
            mapping.update(json.loads(args.mapping_json.read_text(encoding="utf-8")))
        items = normalize_items(load_json(args.input_json))
        protected = compact_protected_items(items, mapping)
        write_json(args.output_json, protected)
    except (OSError, json.JSONDecodeError, TranslationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(protected)} protected QA item(s) to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
