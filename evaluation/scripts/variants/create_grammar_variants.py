#!/usr/bin/env python3
"""Create grammar-error variants while preserving core passage content."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
import zlib
from pathlib import Path
from typing import Any


VERSE_MARKER_PATTERN = re.compile(r"(?<![\w\]])(\d{1,3})\s+")
CLAUSE_SPLIT_PATTERN = re.compile(r"([，。！？；：,.!?;:])")
CONTENT_CHAR_PATTERN = re.compile(r"[\w\u3400-\u9fff]")
PLACEHOLDER_PATTERN = re.compile(
    r"__[^_]+(?:_[^_]+)*__|"
    r"(?:人物|地点|场所|角色|职员|族群|群体|主人|至高者|先祖|祖先|君王|统治者|"
    r"使者|先知|灵|材料|物件|请求|班次|称号|地区|村庄)[甲乙丙丁戊己庚辛壬癸]?"
    r"\d*"
)
DEFAULT_RATES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
COPY_FILES = (
    "passage_source_decanonicalized.txt",
    "qa_target.json",
    "qa_target_decanonicalized.json",
)
FUNCTION_WORDS = ("的", "了", "着", "过", "地", "得", "就", "也", "都")
ASPECT_MARKERS = ("了", "着", "过")
CLASSIFIERS = ("个", "位", "件", "些", "名", "群")
CONNECTIVE_REPLACEMENTS = {
    "并": "又",
    "并且": "又",
    "于是": "然后",
    "随后": "又",
    "当": "在",
    "就": "也",
}
PROTECTED_CHARS = set("不没无未非莫勿")


class GrammarError(Exception):
    pass



def seed_offset(chapter) -> int:
    """Deterministic per-cell seed offset.

    Cells used to be integer chapter numbers, so the seed was `args.seed +
    chapter`. Named passage dirs ("tier1/t1_judg9") broke that with a TypeError.
    Integers keep their exact previous offset, so every Luke variant reproduces
    bit-for-bit; names hash to a stable offset. crc32 rather than hash(), which
    is salted per process and would make runs non-reproducible.
    """
    if isinstance(chapter, int):
        return chapter
    text = str(chapter)
    if text.isdigit():
        return int(text)
    return zlib.crc32(text.encode("utf-8")) % 100000

def load_text(path: Path) -> str:
    if not path.exists():
        raise GrammarError(f"File not found: {path}")
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
                "affectable": bool(content_len(raw)),
                "content_chars": content_len(raw),
            }
        )
    if not units:
        units.append(
            {
                "kind": "clause",
                "verse": block.get("verse"),
                "text": text,
                "affectable": bool(content_len(text)),
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
                    "affectable": False,
                    "content_chars": 0,
                }
            )
    return units


def protected_spans(text: str) -> list[tuple[int, int]]:
    spans = [(match.start(), match.end()) for match in PLACEHOLDER_PATTERN.finditer(text)]
    spans.extend((match.start(), match.end()) for match in re.finditer(r"\d+", text))
    return spans


def is_protected_index(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def choose_affected_units(units: list[dict], rate: float, seed: int) -> set[int]:
    if rate <= 0:
        return set()
    affectable = [
        (index, unit)
        for index, unit in enumerate(units)
        if unit.get("affectable") and int(unit.get("content_chars") or 0) > 0
    ]
    total = sum(int(unit["content_chars"]) for _, unit in affectable)
    target = max(1, round(total * rate))
    rng = random.Random(seed)
    shuffled = affectable[:]
    rng.shuffle(shuffled)

    selected = set()
    affected = 0
    for index, unit in shuffled:
        if affected >= target:
            break
        selected.add(index)
        affected += int(unit["content_chars"])
    return selected


def operation_count_for_rate(rate: float, rng: random.Random) -> int:
    if rate <= 0.10:
        return 1
    if rate <= 0.15:
        return 1 + int(rng.random() < 0.5)
    if rate <= 0.20:
        return 2
    return 2 + int(rng.random() < 0.5)


def delete_function_word(text: str, rng: random.Random) -> tuple[str, str] | None:
    spans = protected_spans(text)
    candidates = [
        index
        for index, char in enumerate(text)
        if char in FUNCTION_WORDS and not is_protected_index(index, spans)
    ]
    if not candidates:
        return None
    index = rng.choice(candidates)
    return text[:index] + text[index + 1 :], "function_word_deletion"


def misuse_aspect_marker(text: str, rng: random.Random) -> tuple[str, str] | None:
    spans = protected_spans(text)
    candidates = [
        index
        for index, char in enumerate(text)
        if char in ASPECT_MARKERS and not is_protected_index(index, spans)
    ]
    if candidates:
        index = rng.choice(candidates)
        replacement = rng.choice([marker for marker in ASPECT_MARKERS if marker != text[index]])
        return text[:index] + replacement + text[index + 1 :], "aspect_marker_misuse"

    insert_positions = [
        index
        for index, char in enumerate(text)
        if "\u4e00" <= char <= "\u9fff"
        and char not in PROTECTED_CHARS
        and not is_protected_index(index, spans)
    ]
    if not insert_positions:
        return None
    index = rng.choice(insert_positions)
    marker = rng.choice(ASPECT_MARKERS)
    return text[: index + 1] + marker + text[index + 1 :], "aspect_marker_misuse"


def make_classifier_awkward(text: str, rng: random.Random) -> tuple[str, str] | None:
    spans = protected_spans(text)
    candidates = [
        index
        for index, char in enumerate(text)
        if char in CLASSIFIERS and not is_protected_index(index, spans)
    ]
    if candidates and rng.random() < 0.65:
        index = rng.choice(candidates)
        return text[:index] + text[index + 1 :], "classifier_measure_word_awkwardness"

    insert_positions = [
        index
        for index, char in enumerate(text)
        if "\u4e00" <= char <= "\u9fff"
        and char not in PROTECTED_CHARS
        and not is_protected_index(index, spans)
    ]
    if not insert_positions:
        return None
    index = rng.choice(insert_positions)
    classifier = rng.choice(CLASSIFIERS)
    return text[: index + 1] + classifier + text[index + 1 :], "classifier_measure_word_awkwardness"


def token_chunks(text: str) -> list[dict]:
    chunks = []
    last = 0
    for match in PLACEHOLDER_PATTERN.finditer(text):
        if match.start() > last:
            chunks.append({"text": text[last : match.start()], "protected": False})
        chunks.append({"text": match.group(0), "protected": True})
        last = match.end()
    if last < len(text):
        chunks.append({"text": text[last:], "protected": False})

    output = []
    for chunk in chunks:
        if chunk["protected"]:
            output.append(chunk)
            continue
        pieces = re.findall(r"\s+|[，。！？；：,.!?;:]|[^，。！？；：,.!?;:\s]{1,4}", chunk["text"])
        output.extend({"text": piece, "protected": False} for piece in pieces)
    return output


def local_phrase_order_disorder(text: str, rng: random.Random) -> tuple[str, str] | None:
    chunks = token_chunks(text)
    candidates = []
    for index in range(len(chunks) - 1):
        left = chunks[index]
        right = chunks[index + 1]
        if left["protected"] or right["protected"]:
            continue
        if not content_len(left["text"]) or not content_len(right["text"]):
            continue
        if any(char in PROTECTED_CHARS for char in left["text"] + right["text"]):
            continue
        candidates.append(index)
    if not candidates:
        return None
    index = rng.choice(candidates)
    chunks[index], chunks[index + 1] = chunks[index + 1], chunks[index]
    return "".join(chunk["text"] for chunk in chunks), "local_phrase_order_disorder"


def connective_awkwardness(text: str, rng: random.Random) -> tuple[str, str] | None:
    spans = protected_spans(text)
    candidates = []
    for source, target in CONNECTIVE_REPLACEMENTS.items():
        for match in re.finditer(re.escape(source), text):
            if any(is_protected_index(i, spans) for i in range(match.start(), match.end())):
                continue
            candidates.append((match.start(), match.end(), source, target))
    if not candidates:
        return None
    start, end, _source, target = rng.choice(candidates)
    return text[:start] + target + text[end:], "agreement_connective_awkwardness"


OPERATIONS = (
    delete_function_word,
    misuse_aspect_marker,
    make_classifier_awkward,
    local_phrase_order_disorder,
    connective_awkwardness,
)


def corrupt_clause(text: str, *, rate: float, rng: random.Random) -> tuple[str, list[str]]:
    current = text
    applied = []
    operations = list(OPERATIONS)
    rng.shuffle(operations)
    attempts = 0
    target_count = operation_count_for_rate(rate, rng)
    while len(applied) < target_count and attempts < len(OPERATIONS) * 3:
        attempts += 1
        operation = operations[attempts % len(operations)]
        result = operation(current, rng)
        if not result:
            continue
        updated, name = result
        if updated == current:
            continue
        current = updated
        applied.append(name)
    return current, applied


def apply_grammar_errors(text: str, *, rate: float, seed: int) -> tuple[str, dict]:
    units = passage_units(text)
    selected = choose_affected_units(units, rate, seed)
    rng = random.Random(seed + 1)
    output = []
    affected_units = []
    total_chars = sum(
        int(unit.get("content_chars") or 0)
        for unit in units
        if unit.get("affectable")
    )
    affected_chars = 0
    operation_count = 0
    for index, unit in enumerate(units):
        original = str(unit.get("text") or "")
        if index in selected:
            corrupted, operations = corrupt_clause(original, rate=rate, rng=rng)
            if operations:
                affected_chars += int(unit.get("content_chars") or 0)
                operation_count += len(operations)
                affected_units.append(
                    {
                        "unit_index": index,
                        "verse": unit.get("verse"),
                        "content_chars": int(unit.get("content_chars") or 0),
                        "original_text": original.strip(),
                        "corrupted_text": corrupted.strip(),
                        "operations": operations,
                    }
                )
                output.append(corrupted)
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
        "operation_count": operation_count,
        "operations_allowed": [
            "function_word_deletion",
            "aspect_marker_misuse",
            "classifier_measure_word_awkwardness",
            "local_phrase_order_disorder",
            "agreement_connective_awkwardness",
        ],
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
    grammar_text: str,
    metadata: dict,
) -> dict:
    data = {}
    if source_json_path.exists():
        try:
            data = json.loads(source_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["method"] = method
    data["grammar_rate"] = rate
    data["grammar_metadata"] = metadata
    data["translations"] = [grammar_text]
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
        clean_dir / "grammar_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "grammar_0%",
            "seed": None,
            "files": {},
        },
    )
    write_json(
        clean_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{clean_dir.parent.parent.name}_0%_grammar",
            "method": "0%",
            "grammar_metadata_file": str(clean_dir / "grammar_metadata.json"),
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
        print(f"reuse grammar variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"grammar_{variant_name}"
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
    raw_grammar, raw_meta = apply_grammar_errors(raw_text, rate=rate, seed=seed)
    write_text(variant_dir / "passage_target.txt", raw_grammar)
    metadata["files"]["passage_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    if decan_path.exists():
        decan_text = load_text(decan_path)
        decan_grammar, decan_meta = apply_grammar_errors(
            decan_text,
            rate=rate,
            seed=seed,
        )
        write_text(variant_dir / "passage_target_decanonicalized.txt", decan_grammar)
        metadata["files"]["passage_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        rate=rate,
        grammar_text=raw_grammar,
        metadata=raw_meta,
    )
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "grammar_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{variant_dir.parent.parent.name}_{variant_name}_grammar",
            "method": variant_name,
            "grammar_metadata_file": str(variant_dir / "grammar_metadata.json"),
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
    print(f"wrote grammar variant: {variant_dir}")
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
            raise GrammarError(f"Grammar rate must be between 0 and 1: {value}")
        rates.append(rate)
    return rates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create grammar-error variants from llm_prompt_high outputs."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="grammar")
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
        help="Grammar affected-clause rates, e.g. 5%% 10%% 0.15. Default: 0%% 5%% 10%% 15%% 20%% 30%%.",
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
