#!/usr/bin/env python3
"""Create controlled addition variants from existing translated passages."""

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
DEFAULT_CATEGORIES = ("neutral", "bad", "adversarial")
COPY_FILES = (
    "passage_source_decanonicalized.txt",
    "qa_target.json",
    "qa_target_decanonicalized.json",
)
DEFAULT_BANK = {
    "schema_version": 1,
    "categories": {
        "neutral": {
            "sentences": [
                "旁边的人也留意到这件事。",
                "这话传到附近的人那里。",
                "众人仍在一旁听着。",
                "这事以后，人们继续议论。",
                "同行的人暂时停在那里。",
                "附近的人也听见了这些话。",
                "他们把这些事记在心里。",
                "有人在旁边安静观看。",
            ],
        },
        "bad": {
            "sentences": [
                "有人说这件事可能发生在另一个日子。",
                "旁边又提到一件无关的路程。",
                "也有人把这事归因于普通的安排。",
                "有传言说他们正在等待一位官员。",
                "另有人说众人只是因为天气改变而惊讶。",
                "有人误把这事和市场上的争论联系起来。",
                "旁边的人提到一笔无关的交易。",
                "有些人说这只是城里的普通消息。",
            ],
        },
        "adversarial": {
            "templates": [
                "有人误以为：{choice}。",
                "旁边也有人说：{choice}。",
                "另一个说法却是：{choice}。",
                "有人把这件事说成：{choice}。",
            ],
        },
    },
}


class AdditionError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise AdditionError(f"File not found: {path}")
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


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def format_rate(rate: float) -> str:
    value = rate * 100
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}%"
    return f"{value:g}%"


def content_len(text: str) -> int:
    return len(CONTENT_CHAR_PATTERN.findall(text or ""))


def normalize_category(value: str) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "neural": "neutral",
        "neutral": "neutral",
        "bad": "bad",
        "noisy": "bad",
        "adversarial": "adversarial",
        "adversial": "adversarial",
        "mcq": "adversarial",
    }
    if raw not in aliases:
        raise AdditionError(
            f"Unknown addition category: {value}. Use neutral, bad, or adversarial."
        )
    return aliases[raw]


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
                "insertable": bool(content_len(raw)),
                "content_chars": content_len(raw),
            }
        )
    if not units:
        units.append(
            {
                "kind": "clause",
                "verse": block.get("verse"),
                "text": text,
                "insertable": bool(content_len(text)),
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
                    "insertable": False,
                    "content_chars": 0,
                }
            )
    return units


def extract_items(data: Any) -> list[dict]:
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item for item in data["items"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def verse_from_reference(reference: Any) -> int | None:
    text = str(reference or "")
    match = re.search(r"(?:(?:Luke|LUK|文本甲)\s*)?\d+:(\d+)", text)
    if match:
        return int(match.group(1))
    return None


def item_q_type(item: dict) -> str:
    return str(item.get("q_type") or item.get("question_type") or "").lower()


def item_choices(item: dict) -> dict[str, str]:
    choices = item.get("A") or item.get("choices") or item.get("options")
    if isinstance(choices, dict):
        return {str(key).upper(): str(value) for key, value in choices.items()}
    return {}


def item_correct_choice(item: dict) -> str | None:
    value = item.get("correct") or item.get("correct_choice")
    if value in (None, ""):
        return None
    return str(value).strip().upper()


def build_adversarial_sentences(qa_path: Path, bank: dict) -> dict[int, list[str]]:
    data = load_json(qa_path)
    templates = (
        bank.get("categories", {})
        .get("adversarial", {})
        .get("templates", DEFAULT_BANK["categories"]["adversarial"]["templates"])
    )
    by_verse: dict[int, list[str]] = {}
    for item in extract_items(data):
        if item_q_type(item) != "mcq":
            continue
        verse = verse_from_reference(item.get("passage_reference") or item.get("title"))
        if verse is None:
            continue
        choices = item_choices(item)
        correct = item_correct_choice(item)
        wrong_choices = [
            choice
            for key, choice in choices.items()
            if key != correct and content_len(choice) > 0
        ]
        for choice in wrong_choices:
            for template in templates:
                by_verse.setdefault(verse, []).append(template.format(choice=choice))
    return by_verse


def load_bank(path: Path | None) -> dict:
    if not path:
        return DEFAULT_BANK
    data = load_json(path)
    if not isinstance(data, dict):
        raise AdditionError(f"Addition bank must be a JSON object: {path}")
    return data


def bank_sentences(category: str, bank: dict) -> list[str]:
    values = bank.get("categories", {}).get(category, {}).get("sentences")
    if not isinstance(values, list) or not values:
        values = DEFAULT_BANK["categories"][category]["sentences"]
    return [str(value).strip() for value in values if str(value).strip()]


def sentence_for_unit(
    *,
    category: str,
    unit: dict,
    rng: random.Random,
    bank: dict,
    adversarial_by_verse: dict[int, list[str]],
) -> str | None:
    if category == "adversarial":
        verse = unit.get("verse")
        local = adversarial_by_verse.get(int(verse), []) if verse is not None else []
        pool = local or [
            sentence
            for sentences in adversarial_by_verse.values()
            for sentence in sentences
        ]
        if not pool:
            return None
        return rng.choice(pool)
    return rng.choice(bank_sentences(category, bank))


def apply_additions(
    text: str,
    *,
    category: str,
    rate: float,
    seed: int,
    bank: dict,
    adversarial_by_verse: dict[int, list[str]],
) -> tuple[str, dict]:
    units = passage_units(text)
    insertable = [
        (index, unit)
        for index, unit in enumerate(units)
        if unit.get("insertable") and int(unit.get("content_chars") or 0) > 0
    ]
    total_chars = sum(int(unit["content_chars"]) for _, unit in insertable)
    target = round(total_chars * rate)
    rng = random.Random(seed)
    shuffled = insertable[:]
    rng.shuffle(shuffled)

    additions_by_index: dict[int, str] = {}
    added_units = []
    added_chars = 0
    for index, unit in shuffled:
        if added_chars >= target:
            break
        sentence = sentence_for_unit(
            category=category,
            unit=unit,
            rng=rng,
            bank=bank,
            adversarial_by_verse=adversarial_by_verse,
        )
        if not sentence:
            continue
        addition = " " + sentence
        additions_by_index[index] = addition
        chars = content_len(addition)
        added_chars += chars
        added_units.append(
            {
                "unit_index": index,
                "verse": unit.get("verse"),
                "content_chars": chars,
                "text": sentence,
                "after": str(unit.get("text") or "").strip(),
            }
        )

    output = []
    for index, unit in enumerate(units):
        output.append(str(unit.get("text") or ""))
        if index in additions_by_index:
            output.append(additions_by_index[index])

    actual_rate = added_chars / total_chars if total_chars else 0.0
    return "".join(output), {
        "category": category,
        "requested_rate": rate,
        "actual_rate": actual_rate,
        "seed": seed,
        "total_content_chars": total_chars,
        "added_content_chars": added_chars,
        "added_unit_count": len(added_units),
        "added_units": added_units,
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
    category: str,
    rate: float,
    added_text: str,
    metadata: dict,
) -> dict:
    data = {}
    if source_json_path.exists():
        try:
            data = json.loads(source_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["method"] = method
    data["addition_category"] = category
    data["addition_rate"] = rate
    data["addition_metadata"] = metadata
    data["translations"] = [added_text]
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
        clean_dir / "addition_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "addition_0%",
            "seed": None,
            "files": {},
        },
    )
    write_json(
        clean_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{clean_dir.parent.parent.name}_0%_addition",
            "method": "0%",
            "addition_metadata_file": str(clean_dir / "addition_metadata.json"),
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
    category: str,
    rate: float,
    seed: int,
    force: bool,
    bank: dict,
) -> Path:
    variant_name = f"{category}_{format_rate(rate)}"
    variant_dir = output_dir / variant_name
    if variant_dir.exists() and not force:
        print(f"reuse addition variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"addition_{variant_name}"
    metadata = {
        "schema_version": 1,
        "source_method_dir": str(source_method_dir),
        "variant": variant_name,
        "category": category,
        "method": method_name,
        "seed": seed,
        "files": {},
    }

    for filename in COPY_FILES:
        copy_if_exists(source_method_dir / filename, variant_dir / filename)

    raw_adversarial = build_adversarial_sentences(source_method_dir / "qa_target.json", bank)
    decan_adversarial = build_adversarial_sentences(
        source_method_dir / "qa_target_decanonicalized.json", bank
    )

    raw_text = load_text(source_method_dir / "passage_target.txt")
    raw_added, raw_meta = apply_additions(
        raw_text,
        category=category,
        rate=rate,
        seed=seed,
        bank=bank,
        adversarial_by_verse=raw_adversarial,
    )
    write_text(variant_dir / "passage_target.txt", raw_added)
    metadata["files"]["passage_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    if decan_path.exists():
        decan_text = load_text(decan_path)
        decan_added, decan_meta = apply_additions(
            decan_text,
            category=category,
            rate=rate,
            seed=seed,
            bank=bank,
            adversarial_by_verse=decan_adversarial,
        )
        write_text(variant_dir / "passage_target_decanonicalized.txt", decan_added)
        metadata["files"]["passage_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        category=category,
        rate=rate,
        added_text=raw_added,
        metadata=raw_meta,
    )
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "addition_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{variant_dir.parent.parent.name}_{variant_name}_addition",
            "method": variant_name,
            "addition_metadata_file": str(variant_dir / "addition_metadata.json"),
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
    print(f"wrote addition variant: {variant_dir}")
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
            raise AdditionError(f"Addition rate must be between 0 and 1: {value}")
        rates.append(rate)
    return rates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create controlled addition variants from llm_prompt_high outputs."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="addition")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(DEFAULT_CATEGORIES),
        help="Addition categories: neutral, bad, adversarial. Alias: neural=neutral.",
    )
    parser.add_argument(
        "--rates",
        nargs="+",
        default=[format_rate(rate) for rate in DEFAULT_RATES],
        help="Addition rates, e.g. 5%% 10%% 0.15. Default: 0%% 5%% 10%% 15%% 20%% 30%%.",
    )
    parser.add_argument(
        "--bank-json",
        type=Path,
        default=Path("evaluation/datasets/addition_bank.json"),
        help="Addition bank JSON. Default: evaluation/datasets/addition_bank.json.",
    )
    parser.add_argument(
        "--write-default-bank",
        type=Path,
        help="Write the built-in bank to this path and exit.",
    )
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.write_default_bank:
        write_json(args.write_default_bank, DEFAULT_BANK)
        print(f"wrote addition bank: {args.write_default_bank}")
        return 0

    try:
        rates = parse_rates(args.rates)
        categories = [normalize_category(category) for category in args.categories]
        bank = load_bank(args.bank_json)
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
            for category in categories:
                create_variant(
                    source_method_dir=source_method_dir,
                    output_dir=output_dir,
                    category=category,
                    rate=rate,
                    seed=args.seed + chapter,
                    force=args.force,
                    bank=bank,
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
