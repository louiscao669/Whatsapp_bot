#!/usr/bin/env python3
"""Create controlled MQM Accuracy > Mistranslation variants.

The script injects targeted meaning-changing substitutions into existing
translated passages. It avoids omission/addition by replacing one content
phrase with another phrase of the same broad syntactic role.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sys
from pathlib import Path
from typing import Any


CONTENT_CHAR_PATTERN = re.compile(r"[\w\u3400-\u9fff]")
PROTECTED_TOKEN_PATTERN = re.compile(r"__[A-Za-z0-9_]+__")
DEFAULT_RATES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
COPY_FILES = (
    "passage_source_decanonicalized.txt",
    "qa_target.json",
    "qa_target_decanonicalized.json",
)
SKIP_OUTPUT_FILES = {
    "scores_target_llama.json",
}
DEFAULT_BANK = {
    "schema_version": 1,
    "description": (
        "Same-role lexical substitutions intended to create MQM Accuracy > "
        "Mistranslation without omission, addition, or fluency errors."
    ),
    "replacements": [
        {"source": "天使", "target": "祭司", "category": "entity", "mode": "systematic"},
        {"source": "祭司", "target": "士兵", "category": "entity", "mode": "systematic"},
        {"source": "牧羊人", "target": "渔夫", "category": "entity", "mode": "systematic"},
        {"source": "羊群", "target": "马群", "category": "entity", "mode": "systematic"},
        {"source": "门徒", "target": "仆人", "category": "entity", "mode": "systematic"},
        {"source": "法利赛人", "target": "撒都该人", "category": "entity", "mode": "systematic"},
        {"source": "税吏", "target": "商人", "category": "entity", "mode": "systematic"},
        {"source": "罪人", "target": "义人", "category": "entity", "mode": "systematic"},
        {"source": "婴儿", "target": "少年", "category": "entity", "mode": "contextual"},
        {"source": "教师", "target": "士兵", "category": "entity", "mode": "systematic"},
        {"source": "仆人", "target": "主人", "category": "entity", "mode": "systematic"},
        {"source": "救世主", "target": "先知", "category": "role", "mode": "systematic"},
        {"source": "弥赛亚", "target": "教师", "category": "role", "mode": "systematic"},
        {"source": "拿撒勒", "target": "耶路撒冷", "category": "location", "mode": "systematic"},
        {"source": "耶路撒冷", "target": "伯利恒", "category": "location", "mode": "systematic"},
        {"source": "伯利恒", "target": "拿撒勒", "category": "location", "mode": "systematic"},
        {"source": "加利利", "target": "犹太", "category": "location", "mode": "systematic"},
        {"source": "犹太", "target": "加利利", "category": "location", "mode": "systematic"},
        {"source": "约旦河", "target": "加利利海", "category": "location", "mode": "systematic"},
        {"source": "旷野", "target": "城里", "category": "location", "mode": "systematic"},
        {"source": "会堂", "target": "圣殿", "category": "location", "mode": "systematic"},
        {"source": "圣殿", "target": "会堂", "category": "location", "mode": "systematic"},
        {"source": "今天", "target": "明天", "category": "time", "mode": "contextual"},
        {"source": "明天", "target": "昨天", "category": "time", "mode": "contextual"},
        {"source": "三天", "target": "七天", "category": "number_time", "mode": "contextual"},
        {"source": "七天", "target": "三天", "category": "number_time", "mode": "contextual"},
        {"source": "八天", "target": "三天", "category": "number_time", "mode": "contextual"},
        {"source": "八十四", "target": "四十四", "category": "number_time", "mode": "contextual"},
        {"source": "十二", "target": "七", "category": "number_time", "mode": "contextual"},
        {"source": "四十", "target": "二十", "category": "number_time", "mode": "contextual"},
    ],
}
SYSTEMATIC_CATEGORIES = {"entity", "location", "role", "term", "theological_term"}
VALID_MODES = {"systematic", "contextual"}


class MistranslationError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise MistranslationError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def load_bank(path: Path | None) -> dict:
    if not path:
        return DEFAULT_BANK
    data = load_json(path)
    if not isinstance(data, dict):
        raise MistranslationError(f"Mistranslation bank must be a JSON object: {path}")
    if not isinstance(data.get("replacements"), list):
        raise MistranslationError(f"Mistranslation bank missing replacements list: {path}")
    return data


def chapter_bank_path(source_model_dir: Path, bank_name: str) -> Path:
    return source_model_dir / "_shared" / bank_name


def load_bank_for_chapter(args: argparse.Namespace, source_model_dir: Path) -> tuple[dict, str]:
    if args.bank:
        return load_bank(args.bank), str(args.bank)

    path = chapter_bank_path(source_model_dir, args.chapter_bank_name)
    if path.exists():
        return load_bank(path), str(path)

    return DEFAULT_BANK, "built_in_default"


def normalized_replacements(bank: dict) -> list[dict]:
    replacements = []
    for index, item in enumerate(bank.get("replacements") or []):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        category = str(item.get("category") or "semantic_substitution")
        mode = str(item.get("mode") or item.get("mistranslation_type") or "").strip().lower()
        if mode not in VALID_MODES:
            mode = "systematic" if category in SYSTEMATIC_CATEGORIES else "contextual"
        replacements.append(
            {
                "bank_index": index,
                "source": source,
                "target": target,
                "category": category,
                "mode": mode,
                "rationale": str(item.get("rationale") or "").strip() or None,
                "source_content_chars": content_len(source),
            }
        )
    replacements.sort(key=lambda row: len(row["source"]), reverse=True)
    if not replacements:
        raise MistranslationError("No usable mistranslation replacements found")
    return replacements


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def protected_token_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in PROTECTED_TOKEN_PATTERN.finditer(text)]


def find_occurrences(text: str, replacements: list[dict]) -> list[dict]:
    occurrences = []
    occupied: list[tuple[int, int]] = []
    protected_spans = protected_token_spans(text)
    for replacement in replacements:
        source = replacement["source"]
        for match in re.finditer(re.escape(source), text):
            start, end = match.span()
            if any(
                overlaps(start, end, protected_start, protected_end)
                for protected_start, protected_end in protected_spans
            ):
                continue
            if any(overlaps(start, end, other_start, other_end) for other_start, other_end in occupied):
                continue
            occupied.append((start, end))
            occurrences.append(
                {
                    **replacement,
                    "start": start,
                    "end": end,
                }
            )
    return occurrences


def candidate_groups(occurrences: list[dict]) -> list[dict]:
    systematic: dict[tuple[int, str, str], list[dict]] = {}
    groups = []
    for occurrence in occurrences:
        if occurrence["mode"] == "systematic":
            key = (
                int(occurrence["bank_index"]),
                occurrence["source"],
                occurrence["target"],
            )
            systematic.setdefault(key, []).append(occurrence)
            continue
        groups.append(
            {
                "bank_index": occurrence["bank_index"],
                "source": occurrence["source"],
                "target": occurrence["target"],
                "category": occurrence["category"],
                "mode": "contextual",
                "rationale": occurrence.get("rationale"),
                "occurrences": [occurrence],
                "changed_chars": int(occurrence.get("source_content_chars") or 0),
            }
        )

    for grouped in systematic.values():
        first = grouped[0]
        groups.append(
            {
                "bank_index": first["bank_index"],
                "source": first["source"],
                "target": first["target"],
                "category": first["category"],
                "mode": "systematic",
                "rationale": first.get("rationale"),
                "occurrences": sorted(grouped, key=lambda row: row["start"]),
                "changed_chars": sum(
                    int(row.get("source_content_chars") or 0) for row in grouped
                ),
            }
        )
    return groups


def group_overlaps_selected(group: dict, occupied: list[tuple[int, int]]) -> bool:
    for occurrence in group["occurrences"]:
        start = int(occurrence["start"])
        end = int(occurrence["end"])
        if any(overlaps(start, end, other_start, other_end) for other_start, other_end in occupied):
            return True
    return False


def occupy_group(group: dict, occupied: list[tuple[int, int]]) -> None:
    for occurrence in group["occurrences"]:
        occupied.append((int(occurrence["start"]), int(occurrence["end"])))


def choose_groups_once(groups: list[dict], target_chars: int, rng: random.Random) -> list[dict]:
    shuffled = groups[:]
    rng.shuffle(shuffled)
    selected = []
    occupied: list[tuple[int, int]] = []
    changed_chars = 0

    for group in shuffled:
        if group_overlaps_selected(group, occupied):
            continue
        group_chars = int(group.get("changed_chars") or 0)
        if group_chars <= 0:
            continue
        before = abs(target_chars - changed_chars)
        after = abs(target_chars - (changed_chars + group_chars))
        if changed_chars < target_chars or after <= before:
            selected.append(group)
            occupy_group(group, occupied)
            changed_chars += group_chars
        if changed_chars >= target_chars and after <= max(1, target_chars * 0.05):
            break

    return selected


def choose_groups(
    occurrences: list[dict],
    *,
    total_content_chars: int,
    rate: float,
    seed: int,
) -> tuple[list[dict], int]:
    if rate <= 0 or not occurrences or total_content_chars <= 0:
        return [], 0
    target_chars = max(1, round(total_content_chars * rate))
    groups = candidate_groups(occurrences)
    if not groups:
        return [], target_chars

    best: list[dict] = []
    best_delta: int | None = None
    rng = random.Random(seed)
    trial_count = min(500, max(80, len(groups) * 20))
    for _ in range(trial_count):
        selected = choose_groups_once(groups, target_chars, rng)
        changed_chars = sum(int(group.get("changed_chars") or 0) for group in selected)
        delta = abs(target_chars - changed_chars)
        if best_delta is None or delta < best_delta:
            best = selected
            best_delta = delta
            if delta == 0:
                break

    return sorted(
        best,
        key=lambda group: min(int(row["start"]) for row in group["occurrences"]),
    ), target_chars


def apply_mistranslations(
    text: str,
    *,
    rate: float,
    seed: int,
    bank: dict,
) -> tuple[str, dict]:
    replacements = normalized_replacements(bank)
    total_chars = content_len(text)
    occurrences = find_occurrences(text, replacements)
    selected_groups, target_chars = choose_groups(
        occurrences,
        total_content_chars=total_chars,
        rate=rate,
        seed=seed,
    )

    selected_occurrences = [
        occurrence
        for group in selected_groups
        for occurrence in group["occurrences"]
    ]
    selected_occurrences.sort(key=lambda row: row["start"])
    output = []
    last_end = 0
    changed_chars = 0
    applied_occurrences = []
    for occurrence in selected_occurrences:
        start = int(occurrence["start"])
        end = int(occurrence["end"])
        output.append(text[last_end:start])
        output.append(occurrence["target"])
        last_end = end
        changed_chars += int(occurrence.get("source_content_chars") or 0)
        applied_occurrences.append(
            {
                "start": start,
                "end": end,
                "source": occurrence["source"],
                "target": occurrence["target"],
                "category": occurrence["category"],
                "mode": occurrence["mode"],
                "source_content_chars": int(
                    occurrence.get("source_content_chars") or 0
                ),
            }
        )
    output.append(text[last_end:])
    actual_rate = changed_chars / total_chars if total_chars else 0.0
    return "".join(output), {
        "requested_rate": rate,
        "actual_rate": actual_rate,
        "seed": seed,
        "total_content_chars": total_chars,
        "target_content_chars": target_chars,
        "eligible_occurrence_count": len(occurrences),
        "eligible_group_count": len(candidate_groups(occurrences)),
        "changed_content_chars": changed_chars,
        "substitution_group_count": len(selected_groups),
        "substitution_occurrence_count": len(applied_occurrences),
        "substitution_groups": [
            {
                "bank_index": group["bank_index"],
                "source": group["source"],
                "target": group["target"],
                "category": group["category"],
                "mode": group["mode"],
                "rationale": group.get("rationale"),
                "changed_content_chars": int(group.get("changed_chars") or 0),
                "occurrence_count": len(group["occurrences"]),
                "occurrences": [
                    {"start": int(row["start"]), "end": int(row["end"])}
                    for row in group["occurrences"]
                ],
            }
            for group in selected_groups
        ],
        "substitutions": applied_occurrences,
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
    mistranslated_text: str,
    metadata: dict,
) -> dict:
    data = {}
    if source_json_path.exists():
        try:
            data = json.loads(source_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["method"] = method
    data["mistranslation_rate"] = rate
    data["mistranslation_metadata"] = metadata
    data["translations"] = [mistranslated_text]
    return data


def decanonicalized_metadata(variant_dir: Path, source_method_dir: Path) -> dict:
    return {
        "dataset_id": f"{variant_dir.parent.parent.name}_{variant_dir.name}_mistranslation",
        "method": variant_dir.name,
        "mistranslation_metadata_file": str(
            variant_dir / "mistranslation_metadata.json"
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
    }


def create_variant(
    *,
    source_method_dir: Path,
    output_dir: Path,
    rate: float,
    seed: int,
    bank: dict,
    force: bool,
) -> Path:
    variant_name = format_rate(rate)
    variant_dir = output_dir / variant_name
    if variant_dir.exists() and not force:
        print(f"reuse mistranslation variant: {variant_dir}")
        return variant_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    method_name = f"mistranslation_{variant_name}"
    metadata = {
        "schema_version": 1,
        "source_method_dir": str(source_method_dir),
        "variant": variant_name,
        "method": method_name,
        "seed": seed,
        "bank_description": bank.get("description"),
        "files": {},
    }

    for filename in COPY_FILES:
        copy_if_exists(source_method_dir / filename, variant_dir / filename)

    raw_text = load_text(source_method_dir / "passage_target.txt")
    raw_mutated, raw_meta = apply_mistranslations(
        raw_text,
        rate=rate,
        seed=seed,
        bank=bank,
    )
    write_text(variant_dir / "passage_target.txt", raw_mutated)
    metadata["files"]["passage_target"] = raw_meta

    decan_path = source_method_dir / "passage_target_decanonicalized.txt"
    if decan_path.exists():
        decan_text = load_text(decan_path)
        decan_mutated, decan_meta = apply_mistranslations(
            decan_text,
            rate=rate,
            seed=seed,
            bank=bank,
        )
        write_text(variant_dir / "passage_target_decanonicalized.txt", decan_mutated)
        metadata["files"]["passage_target_decanonicalized"] = decan_meta

    passage_json = build_passage_translation_json(
        source_method_dir / "passage_translation.json",
        method=method_name,
        rate=rate,
        mistranslated_text=raw_mutated,
        metadata=raw_meta,
    )
    write_json(variant_dir / "passage_translation.json", passage_json)
    write_json(variant_dir / "mistranslation_metadata.json", metadata)
    write_json(
        variant_dir / "decanonicalized_metadata.json",
        decanonicalized_metadata(variant_dir, source_method_dir),
    )
    print(f"wrote mistranslation variant: {variant_dir}")
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
        if path.name.startswith("generated_answers") or path.name in SKIP_OUTPUT_FILES:
            continue
        shutil.copy2(path, clean_dir / path.name)
    write_json(
        clean_dir / "mistranslation_metadata.json",
        {
            "schema_version": 1,
            "source_method_dir": str(source_method_dir),
            "variant": "0%",
            "method": "mistranslation_0%",
            "seed": None,
            "files": {},
        },
    )
    write_json(
        clean_dir / "decanonicalized_metadata.json",
        decanonicalized_metadata(clean_dir, source_method_dir),
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
            raise MistranslationError(
                f"Mistranslation rate must be between 0 and 1: {value}"
            )
        rates.append(rate)
    return rates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create controlled lexical mistranslation variants from existing "
            "translation outputs."
        )
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--source-model-dir", default="1.7b")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="mistranslation")
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument(
        "--rates",
        nargs="+",
        default=[format_rate(rate) for rate in DEFAULT_RATES],
        help=(
            "Mistranslation rates, e.g. 5%% 10%% 0.15. Default: "
            "0%% 5%% 10%% 15%% 20%% 30%%."
        ),
    )
    parser.add_argument(
        "--bank",
        type=Path,
        help=(
            "Optional global JSON bank with a replacements list of "
            "{source, target, category, mode} entries. Overrides chapter banks."
        ),
    )
    parser.add_argument(
        "--chapter-bank-name",
        default="mistranslation_bank_zh.json",
        help=(
            "When --bank is omitted, use this file from each chapter's "
            "<source-model-dir>/_shared folder if it exists."
        ),
    )
    parser.add_argument("--seed", type=int, default=2036)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rates = parse_rates(args.rates)
        if args.bank:
            normalized_replacements(load_bank(args.bank))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for chapter in args.chapters:
        chapter_dir = args.root / f"luke{chapter}"
        source_model_dir = chapter_dir / args.source_model_dir
        source_method_dir = source_model_dir / args.source_method
        output_dir = chapter_dir / args.output_model_dir
        if not source_method_dir.exists():
            print(
                f"warning: source method folder missing: {source_method_dir}",
                file=sys.stderr,
            )
            continue
        try:
            bank, bank_source = load_bank_for_chapter(args, source_model_dir)
            normalized_replacements(bank)
        except Exception as exc:
            print(f"warning: invalid bank for {source_method_dir}: {exc}", file=sys.stderr)
            continue

        copy_shared_files(source_model_dir / "_shared", output_dir / "_shared")
        print(f"using mistranslation bank for luke{chapter}: {bank_source}")
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
                bank=bank,
                force=args.force,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
