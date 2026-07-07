#!/usr/bin/env python3
"""Create question-local name/style inconsistency variants.

Unlike chapter-level inconsistency variants, these variants attach a perturbed
local passage to each QA item. The answer generator will use that `local_passage`
field when present, so the model sees inconsistency inside the same verse window
used for the question.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from create_inconsistency_variants import (
    DEFAULT_RATES,
    DEFAULT_TYPES,
    InconsistencyError,
    apply_inconsistency,
    build_passage_translation_json,
    copy_if_exists,
    copy_shared_files,
    format_rate,
    load_text,
    parse_rates,
    parse_types,
    write_json,
    write_text,
)


PASSAGE_REFERENCE_RE = __import__("re").compile(r":\s*(\d+)(?:\s*[-–—]\s*(\d+))?")
VERSE_MARKER_RE = __import__("re").compile(r"(?<![\w\]])(\d{1,3})\s+")
COPY_FILES = (
    "passage_source_decanonicalized.txt",
    "passage_target.txt",
    "passage_target_decanonicalized.txt",
    "passage_translation.json",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_qa_container(path: Path) -> tuple[Any, list[dict]]:
    data = load_json(path)
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict):
        for key in ("items", "questions", "qa_pairs"):
            value = data.get(key)
            if isinstance(value, list):
                return data, value
    raise InconsistencyError(f"QA JSON must be a list or object with items/questions: {path}")


def write_qa_container(path: Path, container: Any) -> None:
    write_json(path, container)


def verse_range_from_reference(reference: Any) -> tuple[int, int] | None:
    match = PASSAGE_REFERENCE_RE.search(str(reference or ""))
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if end < start:
        start, end = end, start
    return start, end


def index_passage_verses(passage: str) -> dict[int, list[str]]:
    matches = []
    for match in VERSE_MARKER_RE.finditer(passage):
        verse_number = int(match.group(1))
        if 1 <= verse_number <= 200:
            matches.append((verse_number, match.start()))

    verses: dict[int, list[str]] = {}
    for index, (verse_number, start) in enumerate(matches):
        end = matches[index + 1][1] if index + 1 < len(matches) else len(passage)
        verse_text = passage[start:end].strip()
        if verse_text:
            verses.setdefault(verse_number, []).append(verse_text)
    return verses


def local_passage_for_reference(
    passage: str,
    verse_index: dict[int, list[str]],
    reference: Any,
    *,
    verse_window: int,
) -> tuple[str, dict]:
    reference_range = verse_range_from_reference(reference)
    if not reference_range or not verse_index:
        return passage, {
            "reference": reference,
            "reference_start": None,
            "reference_end": None,
            "window_start": None,
            "window_end": None,
        }

    reference_start, reference_end = reference_range
    first_verse = max(min(verse_index), reference_start - verse_window)
    last_verse = min(max(verse_index), reference_end + verse_window)
    selected: list[str] = []
    for verse_number in range(first_verse, last_verse + 1):
        selected.extend(verse_index.get(verse_number, []))
    return "\n".join(selected).strip() or passage, {
        "reference": reference,
        "reference_start": reference_start,
        "reference_end": reference_end,
        "window_start": first_verse,
        "window_end": last_verse,
    }


def stable_item_key(item: dict, fallback_index: int) -> str:
    passage_id = str(item.get("passage_id") or item.get("content_id") or "").strip()
    for suffix in ("-open", "-mcq"):
        if passage_id.endswith(suffix):
            passage_id = passage_id[: -len(suffix)]
    reference = str(item.get("passage_reference") or item.get("title") or "").strip()
    return passage_id or reference or str(fallback_index)


def stable_seed(base_seed: int, *parts: Any) -> int:
    digest = hashlib.sha256(
        "|".join([str(base_seed), *(str(part) for part in parts)]).encode("utf-8")
    ).hexdigest()
    return int(digest[:12], 16)


def mutate_qa_local_passages(
    qa_path: Path,
    passage_text: str,
    *,
    inconsistency_type: str,
    rate: float,
    seed: int,
    verse_window: int,
) -> tuple[Any, dict]:
    container, items = load_qa_container(qa_path)
    verse_index = index_passage_verses(passage_text)
    cache: dict[str, tuple[str, dict]] = {}
    mutated_items = 0
    total_chars = 0
    affected_chars = 0
    item_metadata = []

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        key = stable_item_key(item, index)
        reference = item.get("passage_reference") or item.get("title")
        cache_key = f"{key}|{reference}"
        if cache_key not in cache:
            local_passage, window_meta = local_passage_for_reference(
                passage_text,
                verse_index,
                reference,
                verse_window=verse_window,
            )
            mutated, local_meta = apply_inconsistency(
                local_passage,
                inconsistency_type=inconsistency_type,
                rate=rate,
                seed=stable_seed(seed, inconsistency_type, rate, key, reference),
            )
            local_meta["window"] = window_meta
            cache[cache_key] = (mutated, local_meta)

        mutated_passage, local_meta = cache[cache_key]
        item["local_passage"] = mutated_passage
        item["local_inconsistency"] = {
            "type": inconsistency_type,
            "requested_rate": rate,
            "actual_affected_rate": local_meta.get("actual_affected_rate", 0.0),
            "affected_unit_count": local_meta.get("affected_unit_count", 0),
            "window": local_meta.get("window", {}),
        }
        mutated_items += 1
        total_chars += int(local_meta.get("total_content_chars") or 0)
        affected_chars += int(local_meta.get("affected_content_chars") or 0)
        item_metadata.append(
            {
                "item_index": index,
                "id": item.get("id") or item.get("content_id") or item.get("passage_id"),
                "passage_reference": reference,
                **item["local_inconsistency"],
            }
        )

    actual_rate = affected_chars / total_chars if total_chars else 0.0
    return container, {
        "type": inconsistency_type,
        "requested_rate": rate,
        "actual_affected_rate": actual_rate,
        "seed": seed,
        "verse_window": verse_window,
        "window_verse_count": verse_window * 2 + 1,
        "mutated_item_count": mutated_items,
        "total_content_chars": total_chars,
        "affected_content_chars": affected_chars,
        "items": item_metadata,
    }


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
        clean_dir / "local_inconsistency_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "local_inconsistency_0%",
            "files": {},
        },
    )
    print(f"wrote clean copy: {clean_dir}")
    return clean_dir


def create_variant(
    *,
    source_method_dir: Path,
    output_dir: Path,
    inconsistency_type: str,
    rate: float,
    seed: int,
    verse_window: int,
    force: bool,
) -> Path:
    variant_name = f"{inconsistency_type}_{format_rate(rate)}"
    variant_dir = output_dir / variant_name
    if variant_dir.exists() and not force:
        print(f"reuse local inconsistency variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"local_inconsistency_{variant_name}"
    metadata = {
        "schema_version": 1,
        "source_method_dir": str(source_method_dir),
        "variant": variant_name,
        "type": inconsistency_type,
        "method": method_name,
        "seed": seed,
        "verse_window": verse_window,
        "window_verse_count": verse_window * 2 + 1,
        "files": {},
    }

    for filename in COPY_FILES:
        copy_if_exists(source_method_dir / filename, variant_dir / filename)

    raw_text = load_text(source_method_dir / "passage_target.txt")
    raw_qa, raw_meta = mutate_qa_local_passages(
        source_method_dir / "qa_target.json",
        raw_text,
        inconsistency_type=inconsistency_type,
        rate=rate,
        seed=seed,
        verse_window=verse_window,
    )
    write_qa_container(variant_dir / "qa_target.json", raw_qa)
    metadata["files"]["qa_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    decan_qa_path = source_method_dir / "qa_target_decanonicalized.json"
    if decan_path.exists() and decan_qa_path.exists():
        decan_text = load_text(decan_path)
        decan_qa, decan_meta = mutate_qa_local_passages(
            decan_qa_path,
            decan_text,
            inconsistency_type=inconsistency_type,
            rate=rate,
            seed=seed,
            verse_window=verse_window,
        )
        write_qa_container(variant_dir / "qa_target_decanonicalized.json", decan_qa)
        metadata["files"]["qa_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        inconsistency_type=inconsistency_type,
        rate=rate,
        text=raw_text,
        metadata=metadata["files"].get("qa_target", {}),
    )
    passage_json["local_inconsistency"] = True
    passage_json["local_inconsistency_metadata"] = metadata
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "local_inconsistency_metadata.json", metadata)
    write_json(variant_dir / "inconsistency_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{variant_dir.parent.parent.name}_{variant_name}_local_inconsistency",
            "method": variant_name,
            "local_inconsistency_metadata_file": str(
                variant_dir / "local_inconsistency_metadata.json"
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
    print(f"wrote local inconsistency variant: {variant_dir}")
    return variant_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create question-local name/style inconsistency variants."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="local_inconsistency")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument("--types", nargs="+", default=list(DEFAULT_TYPES))
    parser.add_argument(
        "--rates",
        nargs="+",
        default=[format_rate(rate) for rate in DEFAULT_RATES],
        help="Local 5-verse affected-clause rates, e.g. 5%% 10%%.",
    )
    parser.add_argument(
        "--verse-window",
        type=int,
        default=2,
        help="Verses before/after the question reference. Default 2 means 5 verses total.",
    )
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verse_window < 0:
        print("error: --verse-window must be non-negative", file=sys.stderr)
        return 2
    try:
        rates = parse_rates(args.rates)
        inconsistency_types = parse_types(args.types)
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
            for inconsistency_type in inconsistency_types:
                create_variant(
                    source_method_dir=source_method_dir,
                    output_dir=output_dir,
                    inconsistency_type=inconsistency_type,
                    rate=rate,
                    seed=args.seed + chapter,
                    verse_window=args.verse_window,
                    force=args.force,
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
