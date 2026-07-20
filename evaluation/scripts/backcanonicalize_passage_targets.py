#!/usr/bin/env python3
"""Restore protected passage placeholders to their canonical Chinese terms.

The source ``passage_target.txt`` files are never modified.  By default, this
script writes ``passage_target_backcanonicalized.txt`` beside every matching
file under ``evaluation/outputs/luke{chapter}/{model}``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.decanonicalize_chinese_dataset import (
    DEFAULT_MAPPING,
    MACHINE_TRANSLATED_PROTECTED_TOKEN_MAPPING,
    PROTECTED_TOKEN_MAPPING,
)


TOKEN_RE = re.compile(r"__[A-Za-z0-9_%]+__")


def preferred_global_terms() -> dict[str, str]:
    """Return token/placeholder spellings mapped to the preferred Chinese term."""
    placeholder_to_chinese: dict[str, str] = {}
    # Dict order is intentional: the first spelling in DEFAULT_MAPPING is the
    # project's preferred spelling (for example, 人物丙 -> 约翰).
    for chinese, placeholder in DEFAULT_MAPPING.items():
        placeholder_to_chinese.setdefault(placeholder, chinese)

    replacements: dict[str, str] = {}
    for token, placeholder in PROTECTED_TOKEN_MAPPING.items():
        chinese = placeholder_to_chinese.get(placeholder)
        if chinese:
            replacements[token] = chinese
            replacements[placeholder] = chinese
    for token, placeholder in MACHINE_TRANSLATED_PROTECTED_TOKEN_MAPPING.items():
        chinese = placeholder_to_chinese.get(placeholder)
        if chinese:
            replacements[token] = chinese
    return replacements


def inventory_replacements(inventory_path: Path) -> dict[str, str]:
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    replacements: dict[str, str] = {}
    for entity in data.get("entities", []):
        hints = [str(x).strip() for x in entity.get("chinese_alias_hints", []) if str(x).strip()]
        if not hints:
            continue
        chinese = hints[0]
        token = str(entity.get("protected_token", "")).strip()
        placeholder = str(entity.get("placeholder", "")).strip()
        if token:
            replacements[token] = chinese
        # Some translation methods turn a name into an ad-hoc protected token
        # instead of preserving the inventory token (for example,
        # __QUIRINIUS__ rather than __LOCAL_PERSON_02__).
        source = str(entity.get("source", "")).strip()
        synthetic = re.sub(r"[^A-Za-z0-9]+", "_", source).strip("_").upper()
        if synthetic:
            replacements[f"__{synthetic}__"] = chinese
        if placeholder:
            replacements[placeholder] = chinese
    return replacements


def replace_once(text: str, replacements: dict[str, str]) -> str:
    keys = sorted((key for key in replacements if key), key=len, reverse=True)
    if not keys:
        return text
    by_casefold = {key.casefold(): value for key, value in replacements.items()}
    pattern = re.compile("|".join(re.escape(key) for key in keys), re.IGNORECASE)
    return pattern.sub(lambda match: by_casefold[match.group(0).casefold()], text)


def chapter_inventory(model_root: Path) -> Path:
    candidates = sorted((model_root / "_shared").glob("*entity_inventory.json"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one chapter entity inventory in {model_root / '_shared'}, "
            f"found {len(candidates)}"
        )
    return candidates[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs-root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--model", default="1.7b")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument("--output-name", default="passage_target_backcanonicalized.txt")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    global_replacements = preferred_global_terms()
    written = 0
    unresolved_files = 0
    unresolved_tokens: set[str] = set()

    for chapter in args.chapters:
        model_root = args.outputs_root / f"luke{chapter}" / args.model
        inventory_path = chapter_inventory(model_root)
        replacements = dict(global_replacements)
        replacements.update(inventory_replacements(inventory_path))

        for source_path in sorted(model_root.rglob("passage_target.txt")):
            output_path = source_path.with_name(args.output_name)
            result = replace_once(source_path.read_text(encoding="utf-8"), replacements)
            remaining = set(TOKEN_RE.findall(result))
            if remaining:
                unresolved_files += 1
                unresolved_tokens.update(remaining)
            if not args.dry_run:
                output_path.write_text(result, encoding="utf-8")
            written += 1

    action = "would write" if args.dry_run else "wrote"
    print(f"{action} {written} back-canonicalized passage(s)")
    print(f"files with unresolved protected tokens: {unresolved_files}")
    if unresolved_tokens:
        print("unresolved tokens: " + ", ".join(sorted(unresolved_tokens)))
    return 1 if unresolved_tokens else 0


if __name__ == "__main__":
    raise SystemExit(main())
