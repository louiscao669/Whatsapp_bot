#!/usr/bin/env python3
"""Create untranslated-text variants by replacing translated clauses with source text."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from pathlib import Path
from typing import Any


VERSE_MARKER_PATTERN = re.compile(r"(?<![\w\]])(\d{1,3})\s+")
CLAUSE_SPLIT_PATTERN = re.compile(r"([，。！？；：,.!?;:])")
CONTENT_CHAR_PATTERN = re.compile(r"[\w\u3400-\u9fff]")
DEFAULT_RATES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
COPY_FILES = (
    "passage_source_decanonicalized.txt",
    "qa_target.json",
    "qa_target_decanonicalized.json",
)


class UntranslatedError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise UntranslatedError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def format_rate(rate: float) -> str:
    value = rate * 100
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}%"
    return f"{value:g}%"


def content_len(text: str) -> int:
    return len(CONTENT_CHAR_PATTERN.findall(text or ""))


def parse_verse_blocks(text: str) -> list[dict]:
    matches = list(VERSE_MARKER_PATTERN.finditer(text))
    if not matches:
        return [{"kind": "text", "verse": None, "text": text}]

    blocks = []
    if matches[0].start() > 0:
        blocks.append(
            {
                "kind": "heading",
                "verse": None,
                "text": text[: matches[0].start()],
            }
        )

    for index, match in enumerate(matches):
        verse = int(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(
            {
                "kind": "verse",
                "verse": verse,
                "text": text[start:end],
            }
        )
    return blocks


def clause_units_for_verse(block: dict) -> list[dict]:
    text = str(block.get("text") or "")
    marker = ""
    body = text
    match = re.match(r"(\s*\d{1,3}\s+)(.*)", text, flags=re.DOTALL)
    if match:
        marker = match.group(1)
        body = match.group(2)

    parts = CLAUSE_SPLIT_PATTERN.split(body)
    units = []
    prefix = marker
    for index in range(0, len(parts), 2):
        clause = parts[index]
        punct = parts[index + 1] if index + 1 < len(parts) else ""
        raw = clause + punct
        if not raw:
            continue
        unit_text = prefix + raw
        prefix = ""
        units.append(
            {
                "kind": "clause",
                "verse": block.get("verse"),
                "text": unit_text,
                "replaceable": bool(content_len(raw)),
                "content_chars": content_len(raw),
            }
        )
    if not units:
        units.append(
            {
                "kind": "clause",
                "verse": block.get("verse"),
                "text": text,
                "replaceable": bool(content_len(text)),
                "content_chars": content_len(text),
            }
        )
    return units


def passage_units(text: str) -> list[dict]:
    units = []
    for block in parse_verse_blocks(text):
        if block["kind"] == "verse":
            units.extend(clause_units_for_verse(block))
        else:
            units.append(
                {
                    "kind": block["kind"],
                    "verse": block.get("verse"),
                    "text": block.get("text") or "",
                    "replaceable": False,
                    "content_chars": 0,
                }
            )
    return units


def source_unit_index(source_text: str) -> dict[int, list[dict]]:
    by_verse: dict[int, list[dict]] = {}
    for unit in passage_units(source_text):
        verse = unit.get("verse")
        if verse is None or not unit.get("replaceable"):
            continue
        by_verse.setdefault(int(verse), []).append(unit)
    return by_verse


def choose_replacements(
    units: list[dict],
    *,
    rate: float,
    seed: int,
    source_by_verse: dict[int, list[dict]],
) -> set[int]:
    if rate <= 0:
        return set()
    replaceable = [
        (index, unit)
        for index, unit in enumerate(units)
        if unit.get("replaceable")
        and int(unit.get("content_chars") or 0) > 0
        and unit.get("verse") is not None
        and source_by_verse.get(int(unit["verse"]))
    ]
    total = sum(int(unit["content_chars"]) for _, unit in replaceable)
    target = max(1, round(total * rate))
    rng = random.Random(seed)
    shuffled = replaceable[:]
    rng.shuffle(shuffled)

    selected = set()
    replaced = 0
    for index, unit in shuffled:
        if replaced >= target:
            break
        selected.add(index)
        replaced += int(unit["content_chars"])
    return selected


def source_replacement_text(
    *,
    target_unit: dict,
    source_by_verse: dict[int, list[dict]],
    rng: random.Random,
) -> str:
    verse = int(target_unit["verse"])
    source_units = source_by_verse.get(verse) or []
    if not source_units:
        return str(target_unit.get("text") or "")
    source = rng.choice(source_units)
    replacement = str(source.get("text") or "").strip()
    target_text = str(target_unit.get("text") or "")
    marker_match = re.match(r"(\s*\d{1,3}\s+)", target_text)
    if marker_match and not re.match(r"\s*\d{1,3}\s+", replacement):
        replacement = marker_match.group(1) + replacement
    return replacement + (" " if target_text.endswith(" ") else "")


def apply_untranslated(
    target_text: str,
    source_text: str,
    *,
    rate: float,
    seed: int,
) -> tuple[str, dict]:
    units = passage_units(target_text)
    source_by_verse = source_unit_index(source_text)
    selected = choose_replacements(
        units,
        rate=rate,
        seed=seed,
        source_by_verse=source_by_verse,
    )
    rng = random.Random(seed + 1)
    output = []
    replaced_units = []
    total_chars = sum(
        int(unit.get("content_chars") or 0)
        for unit in units
        if unit.get("replaceable")
        and unit.get("verse") is not None
        and source_by_verse.get(int(unit["verse"]))
    )
    replaced_chars = 0
    for index, unit in enumerate(units):
        if index in selected:
            replacement = source_replacement_text(
                target_unit=unit,
                source_by_verse=source_by_verse,
                rng=rng,
            )
            replaced_chars += int(unit.get("content_chars") or 0)
            replaced_units.append(
                {
                    "unit_index": index,
                    "verse": unit.get("verse"),
                    "content_chars": int(unit.get("content_chars") or 0),
                    "original_text": str(unit.get("text") or "").strip(),
                    "replacement_text": replacement.strip(),
                }
            )
            output.append(replacement)
            continue
        output.append(str(unit.get("text") or ""))
    actual_rate = replaced_chars / total_chars if total_chars else 0.0
    return "".join(output), {
        "requested_rate": rate,
        "actual_rate": actual_rate,
        "seed": seed,
        "total_replaceable_content_chars": total_chars,
        "replaced_content_chars": replaced_chars,
        "replaced_unit_count": len(replaced_units),
        "replaced_units": replaced_units,
    }


def copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def copy_shared_files(source_shared: Path, target_shared: Path) -> None:
    if not source_shared.exists():
        return
    target_shared.mkdir(parents=True, exist_ok=True)
    for path in source_shared.iterdir():
        if path.is_file():
            shutil.copy2(path, target_shared / path.name)


def build_passage_translation_json(
    source_json_path: Path,
    *,
    method: str,
    rate: float,
    untranslated_text: str,
    metadata: dict,
) -> dict:
    data = {}
    if source_json_path.exists():
        try:
            data = json.loads(source_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["method"] = method
    data["untranslated_rate"] = rate
    data["untranslated_metadata"] = metadata
    data["translations"] = [untranslated_text]
    return data


def create_clean_copy(source_method_dir: Path, output_dir: Path, force: bool) -> Path:
    clean_dir = output_dir / "0%"
    if clean_dir.exists() and not force:
        print(f"reuse clean copy: {clean_dir}")
        return clean_dir
    clean_dir.mkdir(parents=True, exist_ok=True)
    for path in source_method_dir.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith("generated_answers") or path.name == "scores_target_llama.json":
            continue
        shutil.copy2(path, clean_dir / path.name)
    write_json(
        clean_dir / "untranslated_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "untranslated_0%",
            "seed": None,
            "files": {},
        },
    )
    write_json(
        clean_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{clean_dir.parent.parent.name}_0%_untranslated",
            "method": "0%",
            "untranslated_metadata_file": str(clean_dir / "untranslated_metadata.json"),
            "source_method_dir": str(source_method_dir),
            "inputs": {
                "source_decanonicalized_passage_file": str(
                    clean_dir / "passage_source_decanonicalized.txt"
                ),
                "translated_passage_file": str(clean_dir / "passage_target.txt"),
                "shared_decanonicalized_qa_file": str(
                    clean_dir / "qa_target_decanonicalized.json"
                ),
            },
            "outputs": {
                "passage_file": str(clean_dir / "passage_target_decanonicalized.txt"),
                "qa_file": str(clean_dir / "qa_target_decanonicalized.json"),
            },
        },
    )
    print(f"wrote clean copy: {clean_dir}")
    return clean_dir


def create_variant(
    *,
    source_method_dir: Path,
    output_dir: Path,
    rate: float,
    seed: int,
    force: bool,
) -> Path:
    variant_name = format_rate(rate)
    variant_dir = output_dir / variant_name
    if variant_dir.exists() and not force:
        print(f"reuse untranslated variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"untranslated_{variant_name}"
    metadata = {
        "schema_version": 1,
        "source_method_dir": str(source_method_dir),
        "variant": variant_name,
        "method": method_name,
        "seed": seed,
        "files": {},
    }

    for filename in COPY_FILES:
        copy_if_exists(source_method_dir / filename, variant_dir / filename)

    source_text = load_text(source_method_dir / "passage_source_decanonicalized.txt")
    raw_text = load_text(source_method_dir / "passage_target.txt")
    raw_untranslated, raw_meta = apply_untranslated(
        raw_text,
        source_text,
        rate=rate,
        seed=seed,
    )
    write_text(variant_dir / "passage_target.txt", raw_untranslated)
    metadata["files"]["passage_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    if decan_path.exists():
        decan_text = load_text(decan_path)
        decan_untranslated, decan_meta = apply_untranslated(
            decan_text,
            source_text,
            rate=rate,
            seed=seed,
        )
        write_text(variant_dir / "passage_target_decanonicalized.txt", decan_untranslated)
        metadata["files"]["passage_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        rate=rate,
        untranslated_text=raw_untranslated,
        metadata=raw_meta,
    )
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "untranslated_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{variant_dir.parent.parent.name}_{variant_name}_untranslated",
            "method": variant_name,
            "untranslated_metadata_file": str(variant_dir / "untranslated_metadata.json"),
            "source_method_dir": str(source_method_dir),
            "inputs": {
                "source_decanonicalized_passage_file": str(
                    variant_dir / "passage_source_decanonicalized.txt"
                ),
                "translated_passage_file": str(variant_dir / "passage_target.txt"),
                "shared_decanonicalized_qa_file": str(
                    variant_dir / "qa_target_decanonicalized.json"
                ),
            },
            "outputs": {
                "passage_file": str(variant_dir / "passage_target_decanonicalized.txt"),
                "qa_file": str(variant_dir / "qa_target_decanonicalized.json"),
            },
        },
    )
    print(f"wrote untranslated variant: {variant_dir}")
    return variant_dir


def parse_rates(values: list[str]) -> list[float]:
    rates = []
    for value in values:
        raw = str(value).strip()
        if raw.endswith("%"):
            rate = float(raw[:-1]) / 100
        else:
            rate = float(raw)
            if rate > 1:
                rate = rate / 100
        if rate < 0 or rate > 1:
            raise UntranslatedError(f"Untranslated rate must be between 0 and 1: {value}")
        rates.append(rate)
    return rates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create untranslated-text variants from llm_prompt_high outputs."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="untranslated")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--rates",
        nargs="+",
        default=[format_rate(rate) for rate in DEFAULT_RATES],
        help="Untranslated rates, e.g. 5%% 10%% 0.15. Default: 0%% 5%% 10%% 15%% 20%% 30%%.",
    )
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rates = parse_rates(args.rates)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for chapter in args.chapters:
        chapter_dir = args.root / f"luke{chapter}"
        source_model_dir = chapter_dir / args.source_model_dir
        source_method_dir = source_model_dir / args.source_method
        output_dir = chapter_dir / args.output_model_dir
        if not source_method_dir.exists():
            print(f"warning: source method folder missing: {source_method_dir}", file=sys.stderr)
            continue

        copy_shared_files(source_model_dir / "_shared", output_dir / "_shared")
        if any(rate == 0 for rate in rates):
            create_clean_copy(source_method_dir, output_dir, args.force)
        for rate in rates:
            if rate == 0:
                continue
            create_variant(
                source_method_dir=source_method_dir,
                output_dir=output_dir,
                rate=rate,
                seed=args.seed + chapter,
                force=args.force,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
