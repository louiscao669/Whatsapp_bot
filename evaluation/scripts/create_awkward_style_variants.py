#!/usr/bin/env python3
"""Create MQM Style/Awkward variants from awkward replacement banks."""

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


class AwkwardStyleError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise AwkwardStyleError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    if not path.exists():
        raise AwkwardStyleError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


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
            {"kind": "heading", "verse": None, "text": text[: matches[0].start()]}
        )

    for index, match in enumerate(matches):
        verse = int(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append({"kind": "verse", "verse": verse, "text": text[start:end]})
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
                "content_chars": content_len(raw),
            }
        )
    if not units:
        units.append(
            {
                "kind": "clause",
                "verse": block.get("verse"),
                "text": text,
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
                    "content_chars": 0,
                }
            )
    return units


def flatten_bank(bank: dict) -> list[dict]:
    replacements = []
    categories = bank.get("categories", {}) if isinstance(bank, dict) else {}
    for category, value in categories.items():
        raw_replacements = value.get("replacements", []) if isinstance(value, dict) else []
        for item in raw_replacements:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            if not source or not target or source == target:
                continue
            replacements.append(
                {
                    "category": str(category),
                    "source": source,
                    "target": target,
                    "rationale": str(item.get("rationale") or "").strip(),
                }
            )
    if not replacements:
        raise AwkwardStyleError("Awkward style bank contains no replacements.")
    return replacements


def replacements_for_text(text: str, replacements: list[dict]) -> list[dict]:
    return [item for item in replacements if item["source"] in text]


def choose_affected_units(
    units: list[dict],
    *,
    rate: float,
    seed: int,
    replacements: list[dict],
) -> set[int]:
    if rate <= 0:
        return set()
    total = sum(int(unit.get("content_chars") or 0) for unit in units)
    target_chars = max(1, round(total * rate))
    eligible = [
        (index, unit)
        for index, unit in enumerate(units)
        if int(unit.get("content_chars") or 0) > 0
        and replacements_for_text(str(unit.get("text") or ""), replacements)
    ]
    rng = random.Random(seed)
    rng.shuffle(eligible)

    selected = set()
    affected = 0
    for index, unit in eligible:
        if affected >= target_chars:
            break
        selected.add(index)
        affected += int(unit.get("content_chars") or 0)
    return selected


def apply_one_replacement(
    text: str,
    replacements: list[dict],
    rng: random.Random,
) -> tuple[str, dict] | None:
    candidates = replacements_for_text(text, replacements)
    if not candidates:
        return None
    replacement = rng.choice(candidates)
    source = replacement["source"]
    start_indexes = [match.start() for match in re.finditer(re.escape(source), text)]
    if not start_indexes:
        return None
    start = rng.choice(start_indexes)
    end = start + len(source)
    updated = text[:start] + replacement["target"] + text[end:]
    return updated, {
        "category": replacement["category"],
        "source": source,
        "target": replacement["target"],
        "span": [start, end],
        "rationale": replacement.get("rationale") or "",
    }


def replacement_count_for_rate(rate: float, rng: random.Random) -> int:
    if rate <= 0.10:
        return 1
    if rate <= 0.20:
        return 1 + int(rng.random() < 0.5)
    return 2


def apply_awkward_style(
    text: str,
    *,
    rate: float,
    seed: int,
    replacements: list[dict],
) -> tuple[str, dict]:
    units = passage_units(text)
    selected = choose_affected_units(
        units,
        rate=rate,
        seed=seed,
        replacements=replacements,
    )
    rng = random.Random(seed + 1)
    output = []
    affected_units = []
    total_chars = sum(int(unit.get("content_chars") or 0) for unit in units)
    affected_chars = 0
    replacement_total = 0

    for index, unit in enumerate(units):
        original = str(unit.get("text") or "")
        if index in selected:
            current = original
            applied = []
            for _ in range(replacement_count_for_rate(rate, rng)):
                result = apply_one_replacement(current, replacements, rng)
                if not result:
                    break
                current, replacement = result
                applied.append(replacement)
            if applied and current != original:
                affected_chars += int(unit.get("content_chars") or 0)
                replacement_total += len(applied)
                affected_units.append(
                    {
                        "unit_index": index,
                        "verse": unit.get("verse"),
                        "content_chars": int(unit.get("content_chars") or 0),
                        "original_text": original.strip(),
                        "awkward_text": current.strip(),
                        "replacements": applied,
                    }
                )
                output.append(current)
                continue
        output.append(original)

    actual_rate = affected_chars / total_chars if total_chars else 0.0
    return "".join(output), {
        "requested_rate": rate,
        "actual_affected_rate": actual_rate,
        "seed": seed,
        "total_content_chars": total_chars,
        "affected_content_chars": affected_chars,
        "affected_unit_count": len(affected_units),
        "replacement_count": replacement_total,
        "affected_units": affected_units,
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
    text: str,
    metadata: dict,
) -> dict:
    data = {}
    if source_json_path.exists():
        try:
            data = json.loads(source_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["method"] = method
    data["awkward_style_rate"] = rate
    data["awkward_style_metadata"] = metadata
    data["translations"] = [text]
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
        clean_dir / "awkward_style_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "awkward_style_0%",
            "seed": None,
            "files": {},
        },
    )
    write_json(
        clean_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{clean_dir.parent.parent.name}_0%_awkward_style",
            "method": "0%",
            "awkward_style_metadata_file": str(
                clean_dir / "awkward_style_metadata.json"
            ),
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


def bank_path_for_chapter(bank_dir: Path, chapter: int) -> Path:
    return bank_dir / f"luke{chapter}_awkward_style_bank.json"


def create_variant(
    *,
    source_method_dir: Path,
    output_dir: Path,
    bank_path: Path,
    rate: float,
    seed: int,
    force: bool,
) -> Path:
    variant_name = format_rate(rate)
    variant_dir = output_dir / variant_name
    if variant_dir.exists() and not force:
        print(f"reuse awkward style variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"awkward_style_{variant_name}"
    bank = load_json(bank_path)
    replacements = flatten_bank(bank)
    metadata = {
        "schema_version": 1,
        "source_method_dir": str(source_method_dir),
        "bank_file": str(bank_path),
        "variant": variant_name,
        "method": method_name,
        "seed": seed,
        "files": {},
    }

    for filename in COPY_FILES:
        copy_if_exists(source_method_dir / filename, variant_dir / filename)

    raw_text = load_text(source_method_dir / "passage_target.txt")
    raw_output, raw_meta = apply_awkward_style(
        raw_text,
        rate=rate,
        seed=seed,
        replacements=replacements,
    )
    write_text(variant_dir / "passage_target.txt", raw_output)
    metadata["files"]["passage_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    if decan_path.exists():
        decan_text = load_text(decan_path)
        decan_output, decan_meta = apply_awkward_style(
            decan_text,
            rate=rate,
            seed=seed,
            replacements=replacements,
        )
        write_text(variant_dir / "passage_target_decanonicalized.txt", decan_output)
        metadata["files"]["passage_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        rate=rate,
        text=raw_output,
        metadata=raw_meta,
    )
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "awkward_style_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{variant_dir.parent.parent.name}_{variant_name}_awkward_style",
            "method": variant_name,
            "awkward_style_metadata_file": str(
                variant_dir / "awkward_style_metadata.json"
            ),
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
    print(f"wrote awkward style variant: {variant_dir}")
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
            raise AwkwardStyleError(f"Awkward style rate must be between 0 and 1: {value}")
        rates.append(rate)
    return rates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create awkward-style variants from awkward replacement banks."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="awkward")
    parser.add_argument(
        "--bank-dir",
        type=Path,
        default=Path("evaluation/datasets/chapter_awkward_style_banks"),
        help="Directory containing lukeN_awkward_style_bank.json files.",
    )
    parser.add_argument(
        "--fallback-bank",
        type=Path,
        default=Path("evaluation/datasets/awkward_style_bank.json"),
        help="Fallback global bank if chapter-specific bank is missing.",
    )
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--rates",
        nargs="+",
        default=[format_rate(rate) for rate in DEFAULT_RATES],
        help="Awkward affected-clause rates, e.g. 5%% 10%%. Default: 0%% 5%% 10%% 15%% 20%% 30%%.",
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

        bank_path = bank_path_for_chapter(args.bank_dir, chapter)
        if not bank_path.exists():
            if args.fallback_bank and args.fallback_bank.exists():
                bank_path = args.fallback_bank
            else:
                print(f"warning: bank missing for Luke {chapter}: {bank_path}", file=sys.stderr)
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
                bank_path=bank_path,
                rate=rate,
                seed=args.seed + chapter,
                force=args.force,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
