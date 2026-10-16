#!/usr/bin/env python3
"""Create clause-level omission variants from existing translated passages."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.variants._common import (
    content_len as content_len,
)
from evaluation.scripts.variants._common import (
    copy_if_exists as copy_if_exists,
)
from evaluation.scripts.variants._common import (
    copy_shared_files as copy_shared_files,
)
from evaluation.scripts.variants._common import (
    format_rate as format_rate,
)
from evaluation.scripts.variants._common import (
    parse_verse_blocks as parse_verse_blocks,
)
from evaluation.scripts.variants._common import (
    seed_offset as seed_offset,
)
from evaluation.scripts.variants._common import (
    write_json as write_json,
)
from evaluation.scripts.variants._common import (
    write_text as write_text,
)

VERSE_MARKER_PATTERN = re.compile(r"(?<![\w\]])(\d{1,3})\s+")
CLAUSE_SPLIT_PATTERN = re.compile(r"([，。！？；：,.!?;:])")
CONTENT_CHAR_PATTERN = re.compile(r"[\w\u3400-\u9fff]")
DEFAULT_RATES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
COPY_FILES = (
    "passage_source_decanonicalized.txt",
    "qa_target.json",
    "qa_target_decanonicalized.json",
)


class OmissionError(Exception):
    pass



def load_text(path: Path) -> str:
    if not path.exists():
        raise OmissionError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


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
                "omittable": bool(content_len(raw)),
                "content_chars": content_len(raw),
            }
        )
    if not units:
        units.append(
            {
                "kind": "clause",
                "verse": block.get("verse"),
                "text": text,
                "omittable": bool(content_len(text)),
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
                    "omittable": False,
                    "content_chars": 0,
                }
            )
    return units


def choose_omissions(units: list[dict], rate: float, seed: int) -> set[int]:
    if rate <= 0:
        return set()
    omittable = [
        (index, unit)
        for index, unit in enumerate(units)
        if unit.get("omittable") and int(unit.get("content_chars") or 0) > 0
    ]
    total = sum(int(unit["content_chars"]) for _, unit in omittable)
    target = max(1, round(total * rate))
    rng = random.Random(seed)
    shuffled = omittable[:]
    rng.shuffle(shuffled)

    selected = set()
    omitted = 0
    for index, unit in shuffled:
        if omitted >= target:
            break
        selected.add(index)
        omitted += int(unit["content_chars"])
    return selected


def apply_omissions(text: str, *, rate: float, seed: int) -> tuple[str, dict]:
    units = passage_units(text)
    selected = choose_omissions(units, rate, seed)
    output = []
    omitted_units = []
    total_chars = sum(
        int(unit.get("content_chars") or 0)
        for unit in units
        if unit.get("omittable")
    )
    omitted_chars = 0
    for index, unit in enumerate(units):
        if index in selected:
            omitted_chars += int(unit.get("content_chars") or 0)
            omitted_units.append(
                {
                    "unit_index": index,
                    "verse": unit.get("verse"),
                    "content_chars": int(unit.get("content_chars") or 0),
                    "text": str(unit.get("text") or "").strip(),
                }
            )
            continue
        output.append(str(unit.get("text") or ""))
    actual_rate = omitted_chars / total_chars if total_chars else 0.0
    return "".join(output), {
        "requested_rate": rate,
        "actual_rate": actual_rate,
        "seed": seed,
        "total_content_chars": total_chars,
        "omitted_content_chars": omitted_chars,
        "omitted_unit_count": len(omitted_units),
        "omitted_units": omitted_units,
    }


def build_passage_translation_json(
    source_json_path: Path,
    *,
    method: str,
    rate: float,
    omitted_text: str,
    metadata: dict,
) -> dict:
    data = {}
    if source_json_path.exists():
        try:
            data = json.loads(source_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["method"] = method
    data["omission_rate"] = rate
    data["omission_metadata"] = metadata
    data["translations"] = [omitted_text]
    return data


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
        print(f"reuse omission variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"omission_{variant_name}"
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

    raw_text = load_text(source_method_dir / "passage_target.txt")
    raw_omitted, raw_meta = apply_omissions(raw_text, rate=rate, seed=seed)
    write_text(variant_dir / "passage_target.txt", raw_omitted)
    metadata["files"]["passage_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    if decan_path.exists():
        decan_text = load_text(decan_path)
        decan_omitted, decan_meta = apply_omissions(decan_text, rate=rate, seed=seed)
        write_text(variant_dir / "passage_target_decanonicalized.txt", decan_omitted)
        metadata["files"]["passage_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        rate=rate,
        omitted_text=raw_omitted,
        metadata=raw_meta,
    )
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "omission_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{variant_dir.parent.parent.name}_{variant_name}_omission",
            "method": variant_name,
            "omission_metadata_file": str(variant_dir / "omission_metadata.json"),
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
    print(f"wrote omission variant: {variant_dir}")
    return variant_dir


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
        clean_dir / "omission_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "omission_0%",
            "seed": None,
            "files": {},
        },
    )
    write_json(
        clean_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{clean_dir.parent.parent.name}_0%_omission",
            "method": "0%",
            "omission_metadata_file": str(clean_dir / "omission_metadata.json"),
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
            raise OmissionError(f"Omission rate must be between 0 and 1: {value}")
        rates.append(rate)
    return rates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create clause-level omission variants from llm_prompt_high outputs."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="omission")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--passage-dirs",
        nargs="+",
        help=(
            "Passage directory names under --root, e.g. tier1/t1_judg9. Overrides "
            "--chapters. The Luke grid keys cells by chapter number, but the Tier 1 "
            "passages are named (t1_judg9, t1_2kgs6_7), so they cannot be addressed "
            "as integers."
        ),
    )
    parser.add_argument(
        "--rates",
        nargs="+",
        default=[format_rate(rate) for rate in DEFAULT_RATES],
        help="Omission rates, e.g. 5%% 10%% 0.15. Default: 0%% 5%% 10%% 15%% 20%% 30%%.",
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

    targets = args.passage_dirs or [f"luke{chapter}" for chapter in args.chapters]
    for chapter in targets:
        chapter_dir = args.root / str(chapter)
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
                seed=args.seed + seed_offset(chapter),
                force=args.force,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
