#!/usr/bin/env python3
"""Create name and style inconsistency variants from existing translated passages."""

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
DEFAULT_RATES = (0.0, 0.05, 0.10, 0.15, 0.20)
DEFAULT_TYPES = ("name", "style")
COPY_FILES = (
    "passage_source_decanonicalized.txt",
    "qa_target.json",
    "qa_target_decanonicalized.json",
)

NAME_VARIANTS = {
    "约翰": ["阿伦", "贝诺"],
    "耶稣": ["赛恩", "米洛"],
    "撒迦利亚": ["诺兰", "达恩"],
    "伊丽莎白": ["莉娜", "艾拉"],
    "玛利亚": ["米娜", "露雅"],
    "加百列": ["卡文", "罗恩"],
    "人物甲": ["诺兰甲", "达恩甲"],
    "人物乙": ["莉娜乙", "艾拉乙"],
    "人物丙": ["阿伦丙", "贝诺丙"],
    "人物丁": ["米娜丁", "露雅丁"],
    "人物戊": ["约兰戊", "凯文戊"],
    "人物己": ["赛恩己", "米洛己"],
    "主人甲": ["尊者甲", "导师甲"],
    "至高者甲": ["天尊甲", "至者甲"],
    "圣灵": ["清灵", "明灵"],
    "灵甲": ["清灵甲", "明灵甲"],
}

STYLE_REPLACEMENTS = {
    "您": ["你"],
    "不可": ["别"],
    "不要": ["别"],
    "应当": ["该"],
    "愿": ["希望"],
    "诸位": ["你们"],
    "众人": ["大家"],
    "赐": ["给"],
    "临到": ["来到"],
    "成就": ["办成"],
    "称为": ["叫作"],
    "无所畏惧": ["不用怕"],
    "欢欣": ["高兴"],
    "蒙恩": ["被照顾"],
    "义行无瑕": ["表现不错"],
    "尊贵": ["厉害"],
    "记述": ["记录"],
    "诫命": ["规矩"],
    "律例": ["规则"],
    "显现": ["出现"],
    "惊慌害怕": ["吓到了"],
    "已蒙垂听": ["已经听见"],
    "大有作为": ["很厉害"],
    "欢喜": ["开心"],
    "归向": ["回到"],
    "奉差遣": ["被派"],
    "美事": ["好消息"],
    "闭口不能言语": ["说不了话"],
    "无法言语": ["说不了话"],
    "应验": ["实现"],
    "眷顾": ["照顾"],
    "羞辱": ["丢脸事"],
    "至尊者": ["最高的那位"],
    "绝不会落空": ["肯定会成"],
    "问安": ["打招呼"],
    "有福": ["好运"],
    "欢跃": ["开心跳起来"],
    "称赞": ["夸"],
    "救赎": ["救出来"],
    "怜悯": ["照顾"],
    "圣约": ["神圣约定"],
    "事奉": ["服务"],
    "仆人": ["手下"],
    "后裔": ["后代"],
    "诞生": ["出生"],
    "临产": ["快生"],
    "割礼": ["仪式"],
    "命名": ["取名"],
    "预言": ["说以后会发生的事"],
}


class InconsistencyError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise InconsistencyError(f"File not found: {path}")
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


def targets_for_type(inconsistency_type: str) -> dict[str, list[str]]:
    if inconsistency_type == "name":
        return NAME_VARIANTS
    if inconsistency_type == "style":
        return STYLE_REPLACEMENTS
    raise InconsistencyError(f"Unknown inconsistency type: {inconsistency_type}")


def unit_has_target(unit: dict, targets: dict[str, list[str]]) -> bool:
    text = str(unit.get("text") or "")
    return any(target in text for target in targets)


def choose_affected_units(
    units: list[dict],
    *,
    rate: float,
    seed: int,
    targets: dict[str, list[str]],
) -> set[int]:
    if rate <= 0:
        return set()
    total = sum(int(unit.get("content_chars") or 0) for unit in units)
    target_chars = max(1, round(total * rate))
    eligible = [
        (index, unit)
        for index, unit in enumerate(units)
        if int(unit.get("content_chars") or 0) > 0 and unit_has_target(unit, targets)
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


def replace_one_target(
    text: str,
    *,
    targets: dict[str, list[str]],
    rng: random.Random,
) -> tuple[str, dict] | None:
    matches = []
    for target, variants in targets.items():
        start = 0
        while True:
            index = text.find(target, start)
            if index == -1:
                break
            matches.append((index, index + len(target), target, variants))
            start = index + len(target)
    if not matches:
        return None

    start, end, target, variants = rng.choice(matches)
    choices = [variant for variant in variants if variant != target] or variants
    replacement = rng.choice(choices)
    updated = text[:start] + replacement + text[end:]
    return updated, {
        "source": target,
        "replacement": replacement,
        "span": [start, end],
    }


def apply_inconsistency(
    text: str,
    *,
    inconsistency_type: str,
    rate: float,
    seed: int,
) -> tuple[str, dict]:
    units = passage_units(text)
    targets = targets_for_type(inconsistency_type)
    selected = choose_affected_units(units, rate=rate, seed=seed, targets=targets)
    rng = random.Random(seed + 1)
    output = []
    affected_units = []
    total_chars = sum(int(unit.get("content_chars") or 0) for unit in units)
    affected_chars = 0

    for index, unit in enumerate(units):
        original = str(unit.get("text") or "")
        if index in selected:
            current = original
            replacements = []
            replacement_count = 1 + int(rate >= 0.15 and rng.random() < 0.6)
            for _ in range(replacement_count):
                result = replace_one_target(current, targets=targets, rng=rng)
                if not result:
                    break
                current, replacement = result
                replacements.append(replacement)
            if replacements and current != original:
                affected_chars += int(unit.get("content_chars") or 0)
                affected_units.append(
                    {
                        "unit_index": index,
                        "verse": unit.get("verse"),
                        "content_chars": int(unit.get("content_chars") or 0),
                        "original_text": original.strip(),
                        "inconsistent_text": current.strip(),
                        "replacements": replacements,
                    }
                )
                output.append(current)
                continue
        output.append(original)

    actual_rate = affected_chars / total_chars if total_chars else 0.0
    return "".join(output), {
        "type": inconsistency_type,
        "requested_rate": rate,
        "actual_affected_rate": actual_rate,
        "seed": seed,
        "total_content_chars": total_chars,
        "affected_content_chars": affected_chars,
        "affected_unit_count": len(affected_units),
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
    inconsistency_type: str,
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
    data["inconsistency_type"] = inconsistency_type
    data["inconsistency_rate"] = rate
    data["inconsistency_metadata"] = metadata
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
        clean_dir / "inconsistency_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "inconsistency_0%",
            "seed": None,
            "files": {},
        },
    )
    write_json(
        clean_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{clean_dir.parent.parent.name}_0%_inconsistency",
            "method": "0%",
            "inconsistency_metadata_file": str(clean_dir / "inconsistency_metadata.json"),
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
    inconsistency_type: str,
    rate: float,
    seed: int,
    force: bool,
) -> Path:
    variant_name = f"{inconsistency_type}_{format_rate(rate)}"
    variant_dir = output_dir / variant_name
    if variant_dir.exists() and not force:
        print(f"reuse inconsistency variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"inconsistency_{variant_name}"
    metadata = {
        "schema_version": 1,
        "source_method_dir": str(source_method_dir),
        "variant": variant_name,
        "type": inconsistency_type,
        "method": method_name,
        "seed": seed,
        "files": {},
    }

    for filename in COPY_FILES:
        copy_if_exists(source_method_dir / filename, variant_dir / filename)

    raw_text = load_text(source_method_dir / "passage_target.txt")
    raw_output, raw_meta = apply_inconsistency(
        raw_text,
        inconsistency_type=inconsistency_type,
        rate=rate,
        seed=seed,
    )
    write_text(variant_dir / "passage_target.txt", raw_output)
    metadata["files"]["passage_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    if decan_path.exists():
        decan_text = load_text(decan_path)
        decan_output, decan_meta = apply_inconsistency(
            decan_text,
            inconsistency_type=inconsistency_type,
            rate=rate,
            seed=seed,
        )
        write_text(variant_dir / "passage_target_decanonicalized.txt", decan_output)
        metadata["files"]["passage_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        inconsistency_type=inconsistency_type,
        rate=rate,
        text=raw_output,
        metadata=raw_meta,
    )
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "inconsistency_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        {
            "dataset_id": f"{variant_dir.parent.parent.name}_{variant_name}_inconsistency",
            "method": variant_name,
            "inconsistency_metadata_file": str(variant_dir / "inconsistency_metadata.json"),
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
    print(f"wrote inconsistency variant: {variant_dir}")
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
            raise InconsistencyError(f"Inconsistency rate must be between 0 and 1: {value}")
        rates.append(rate)
    return rates


def parse_types(values: list[str]) -> list[str]:
    output = []
    for value in values:
        normalized = str(value).strip().lower()
        if normalized not in DEFAULT_TYPES:
            raise InconsistencyError("Inconsistency type must be name or style.")
        output.append(normalized)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create name/style inconsistency variants from llm_prompt_high outputs."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="inconsistency")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--types",
        nargs="+",
        default=list(DEFAULT_TYPES),
        help="Inconsistency types to create: name style. Default: both.",
    )
    parser.add_argument(
        "--rates",
        nargs="+",
        default=[format_rate(rate) for rate in DEFAULT_RATES],
        help="Affected-clause rates, e.g. 5%% 10%%. Default: 0%% 5%% 10%% 15%% 20%%.",
    )
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
                    force=args.force,
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
