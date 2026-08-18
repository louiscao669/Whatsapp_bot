#!/usr/bin/env python3
"""Build and import the selected Tier-1 QAs missing from all-format artifacts.

The gold-72 optimizer can select questions that were removed before the
90-record all-format dataset was built.  Those questions have a reviewed open
question and answer, but no executable open/MCQ record.  This command combines
the reviewed gold records with a checked-in distractor bank, upserts the result
into the canonical master and per-passage QA files, then regenerates the
BSB-pseudonymized per-passage QA artifacts.

The import is idempotent: a second run replaces the same content IDs rather
than appending duplicates.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[3]
PASSAGE_ORDER = (
    "t1_judg9",
    "t1_judg17_18",
    "t1_2kgs6_7",
    "t1_1kgs13",
    "t1_2kgs11",
    "t1_2chr26",
    "t1_2sam21",
    "t1_acts19",
    "t1_acts20",
    "t1_acts23",
)
PASSAGE_SCOPE = {
    "t1_judg9": "judg_9_1-57",
    "t1_judg17_18": "judg_17_1-18_31",
    "t1_2kgs6_7": "2kgs_6_24-7_20",
    "t1_1kgs13": "1kgs_13_1-34",
    "t1_2kgs11": "2kgs_11_1-21",
    "t1_2chr26": "2chr_26_1-23",
    "t1_2sam21": "2sam_21_15-22",
    "t1_acts19": "acts_19_11-20",
    "t1_acts20": "acts_20_7-12",
    "t1_acts23": "acts_23_12-35",
}
LETTERS = "ABCD"


class ImportError_(RuntimeError):
    pass


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportError_(f"cannot read {path}: {exc}") from exc


def records_from(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        rows = payload["items"]
    else:
        raise ImportError_(f"{path}: expected a JSON list or an object with items[]")
    if not all(isinstance(row, dict) for row in rows):
        raise ImportError_(f"{path}: every item must be an object")
    return rows


def detect_indent(path: Path) -> int:
    for line in path.read_text(encoding="utf-8").splitlines()[1:20]:
        stripped = line.lstrip(" ")
        if stripped and stripped != "]":
            return max(1, len(line) - len(stripped))
    return 2


def write_records(path: Path, rows: list[dict[str, Any]]) -> None:
    indent = detect_indent(path) if path.exists() else 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )


def normalized(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return text.rstrip(".?!")


def tagged(question: str, answer: str) -> str:
    return f"<question>{question}\n<question><answer>{answer}<answer>"


def load_bank(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(path)
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, dict):
        raise ImportError_(f"{path}: expected an object with items keyed by content_id")
    return items


def validate_bank_item(content_id: str, gold: dict[str, Any], bank: dict[str, Any]) -> None:
    options = bank.get("options")
    correct = str(bank.get("correct") or "").upper()
    if not isinstance(options, dict) or set(options) != set(LETTERS):
        raise ImportError_(f"{content_id}: MCQ options must contain exactly A, B, C, D")
    values = [str(options[label]).strip() for label in LETTERS]
    if any(not value for value in values):
        raise ImportError_(f"{content_id}: MCQ options cannot be blank")
    if len({normalized(value) for value in values}) != 4:
        raise ImportError_(f"{content_id}: MCQ options must be distinct")
    if correct not in LETTERS:
        raise ImportError_(f"{content_id}: invalid correct letter {correct!r}")
    if normalized(options[correct]) != normalized(gold.get("answer")):
        raise ImportError_(
            f"{content_id}: correct option does not equal the reviewed gold answer"
        )


def build_record(
    gold: dict[str, Any], bank: dict[str, Any], template: dict[str, Any]
) -> dict[str, Any]:
    content_id = str(gold["content_id"])
    passage_id = str(gold["passage_id"])
    question = str(gold.get("question") or "").strip()
    answer = str(gold.get("answer") or "").strip()
    if not question or not answer:
        raise ImportError_(f"{content_id}: reviewed question and answer are required")
    validate_bank_item(content_id, gold, bank)

    options_by_letter = {label: str(bank["options"][label]).strip() for label in LETTERS}
    correct = str(bank["correct"]).upper()
    options = [options_by_letter[label] for label in LETTERS]
    keywords = [str(value).strip().lower() for value in bank.get("required_keywords", [])]
    optional = [str(value).strip().lower() for value in bank.get("optional_keywords", [])]
    anchors = {"required_keywords": keywords, "optional_keywords": optional}
    mcq_text = question + "\n\n" + "\n".join(
        f"{label}. {options_by_letter[label]}" for label in LETTERS
    )

    record: dict[str, Any] = {
        "passage_id": passage_id,
        "passage_reference": template.get("passage_reference"),
        "book": template.get("book"),
        "book_code": template.get("book_code"),
        "reference": gold.get("reference"),
        "id": content_id.split(":", 1)[-1],
        "question": question,
        "answer": answer,
        "tags": "",
        "quote": "",
        "occurrence": "0",
        "content_id": content_id,
        "needs_review": False,
        "selection_tier": "gold72_import",
        "auto_decision": {
            "question_type": "open",
            "reason": "Human-reviewed Gold-72 item with open and multiple-choice variants.",
        },
        "open": {
            "content": tagged(question, answer),
            "question_type": "open",
            "required_keywords": keywords,
            "optional_keywords": optional,
            "anchors": dict(anchors),
            "original_question": question,
            "original_answer": answer,
        },
        "mcq": {
            "content": f"<question>{mcq_text}\n<question><answer>{correct}<answer>",
            "question_type": "multiple_choice",
            "required_keywords": keywords,
            "optional_keywords": optional,
            "anchors": dict(anchors),
            "mcq_options": options,
            "mcq_stem": question,
            "original_question": question,
            "original_answer": answer,
        },
        "gold72_selection": {
            "selected": True,
            "window_ordinals": list(gold.get("window_ordinals") or []),
            "has_grid_data": bool(gold.get("has_grid_data")),
            "global_rank": gold.get("global_rank"),
        },
        "artifact_provenance": {
            "builder": "evaluation/scripts/data_prep/import_tier1_gold_qa.py",
            "gold_source": "evaluation/datasets/tier1_gold_72_missing.json",
            "mcq_source": "evaluation/datasets/qa/tier1_gold_72_missing_mcq.json",
        },
    }
    return {key: value for key, value in record.items() if value is not None}


def validate_record(record: dict[str, Any]) -> None:
    content_id = str(record.get("content_id") or "<missing-id>")
    if not isinstance(record.get("open"), dict) or not isinstance(record.get("mcq"), dict):
        raise ImportError_(f"{content_id}: both open and mcq blocks are required")
    options = record["mcq"].get("mcq_options")
    if not isinstance(options, list) or len(options) != 4:
        raise ImportError_(f"{content_id}: mcq_options must contain four choices")
    answer_match = re.search(
        r"<answer>\s*([A-D])\s*<answer>", str(record["mcq"].get("content") or "")
    )
    if not answer_match:
        raise ImportError_(f"{content_id}: MCQ content has no keyed A-D answer")
    if not str(record["open"].get("content") or "").startswith("<question>"):
        raise ImportError_(f"{content_id}: malformed open content")


def load_item_order(path: Path) -> dict[str, tuple[int, int, int]]:
    payload = read_json(path)
    rows = payload.get("windows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ImportError_(f"{path}: expected windows[]")
    passage_rank = {passage_id: index for index, passage_id in enumerate(PASSAGE_ORDER)}
    return {
        str(row["content_id"]): (
            passage_rank.get(str(row.get("passage_id")), len(passage_rank)),
            int(row.get("item_index", 10**9)),
            int(row.get("occurrence", 0)),
        )
        for row in rows
        if row.get("content_id")
    }


def upsert_records(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    item_order: dict[str, tuple[int, int, int]],
) -> tuple[list[dict[str, Any]], int, int]:
    existing_ids = [str(row.get("content_id") or "") for row in existing]
    nonempty = [content_id for content_id in existing_ids if content_id]
    if len(nonempty) != len(set(nonempty)):
        raise ImportError_("destination contains duplicate content_id values")
    replacement = {str(row["content_id"]): row for row in additions}
    replaced = sum(content_id in replacement for content_id in existing_ids)
    output = [replacement.pop(content_id, row) for content_id, row in zip(existing_ids, existing)]
    added = len(replacement)
    output.extend(replacement.values())
    original_position = {id(row): index for index, row in enumerate(output)}
    output.sort(
        key=lambda row: item_order.get(
            str(row.get("content_id") or ""),
            (len(PASSAGE_ORDER), 10**9, original_position[id(row)]),
        )
    )
    return output, added, replaced


def validate_gold_coverage(
    selected: list[dict[str, Any]], rows_by_passage: dict[str, list[dict[str, Any]]]
) -> None:
    available = {
        str(row.get("content_id"))
        for rows in rows_by_passage.values()
        for row in rows
        if row.get("content_id")
        and isinstance(row.get("open"), dict)
        and isinstance(row.get("mcq"), dict)
    }
    wanted = {str(row["content_id"]) for row in selected}
    missing = sorted(wanted - available)
    if missing:
        raise ImportError_(f"Gold-72 artifact coverage is incomplete: {missing}")


def pseudonymize(
    *,
    qa_dir: Path,
    output_dir: Path,
    map_path: Path,
    passage_ids: list[str],
) -> None:
    script = REPO / "evaluation/scripts/pseudonyms/pseudonymize_english_source.py"
    output_dir.mkdir(parents=True, exist_ok=True)
    for passage_id in passage_ids:
        command = [
            sys.executable,
            str(script),
            "--table",
            str(map_path),
            "--passage-id",
            PASSAGE_SCOPE[passage_id],
            "--qa",
            str(qa_dir / f"{passage_id}_all_formats.json"),
            "--out-qa",
            str(output_dir / f"{passage_id}_all_formats.json"),
        ]
        subprocess.run(command, cwd=REPO, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold-missing",
        default="evaluation/datasets/tier1_gold_72_missing.json",
    )
    parser.add_argument(
        "--gold-all",
        default="evaluation/datasets/tier1_gold_72.json",
        help="full selected set used for the final 72/72 coverage check",
    )
    parser.add_argument(
        "--mcq-bank",
        default="evaluation/datasets/qa/tier1_gold_72_missing_mcq.json",
    )
    parser.add_argument(
        "--qa-dir",
        default="evaluation/datasets/qa/tier1_QAs_easy",
    )
    parser.add_argument(
        "--windows",
        default="QA_algorithm/inputs/tier1_qa_verse_windows.json",
    )
    parser.add_argument(
        "--pseudonym-map",
        default="evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json",
    )
    parser.add_argument(
        "--pseudonymized-qa-dir",
        default="evaluation/datasets/pseudonymized/qa/tier1_bsb",
    )
    parser.add_argument(
        "--skip-pseudonymize",
        action="store_true",
        help="only update canonical QA files",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate and report without writing")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    gold_missing_path = repo_path(args.gold_missing)
    gold_all_path = repo_path(args.gold_all)
    bank_path = repo_path(args.mcq_bank)
    qa_dir = repo_path(args.qa_dir)
    windows_path = repo_path(args.windows)
    pseudonym_map = repo_path(args.pseudonym_map)
    pseudonymized_dir = repo_path(args.pseudonymized_qa_dir)

    missing = records_from(gold_missing_path)
    selected = records_from(gold_all_path)
    bank = load_bank(bank_path)
    item_order = load_item_order(windows_path)
    missing_ids = [str(row.get("content_id") or "") for row in missing]
    if not missing_ids or any(not content_id for content_id in missing_ids):
        raise ImportError_(f"{gold_missing_path}: content_id is required for every item")
    if len(missing_ids) != len(set(missing_ids)):
        raise ImportError_(f"{gold_missing_path}: duplicate content_id")
    unknown_bank = sorted(set(bank) - set(missing_ids))
    absent_bank = sorted(set(missing_ids) - set(bank))
    if unknown_bank or absent_bank:
        raise ImportError_(
            f"MCQ bank mismatch; missing={absent_bank}, not selected={unknown_bank}"
        )

    affected = sorted({str(row["passage_id"]) for row in missing}, key=PASSAGE_ORDER.index)
    rows_by_passage: dict[str, list[dict[str, Any]]] = {}
    imported_by_passage: dict[str, list[dict[str, Any]]] = {passage_id: [] for passage_id in affected}
    stats: dict[str, tuple[int, int, int]] = {}

    for passage_id in PASSAGE_ORDER:
        path = qa_dir / f"{passage_id}_all_formats.json"
        rows = records_from(path)
        additions: list[dict[str, Any]] = []
        if passage_id in imported_by_passage:
            if not rows:
                raise ImportError_(f"{path}: cannot derive passage metadata from an empty file")
            additions = [
                build_record(row, bank[str(row["content_id"])], rows[0])
                for row in missing
                if row["passage_id"] == passage_id
            ]
            for record in additions:
                validate_record(record)
            imported_by_passage[passage_id] = additions
        merged, added, replaced = upsert_records(rows, additions, item_order)
        rows_by_passage[passage_id] = merged
        stats[passage_id] = (len(merged), added, replaced)

    validate_gold_coverage(selected, rows_by_passage)
    master_path = qa_dir / "tier1_all_formats.json"
    master = records_from(master_path)
    additions = [record for passage_id in affected for record in imported_by_passage[passage_id]]
    merged_master, master_added, master_replaced = upsert_records(master, additions, item_order)
    validate_gold_coverage(selected, {"master": merged_master})

    print(f"validated {len(missing)} missing Gold-72 question(s); each has open + MCQ")
    for passage_id in affected:
        total, added, replaced = stats[passage_id]
        print(f"  {passage_id}: {total} total ({added} add, {replaced} replace)")
    print(
        f"  master: {len(merged_master)} total "
        f"({master_added} add, {master_replaced} replace)"
    )
    print(f"Gold coverage after merge: {len(selected)}/{len(selected)}")
    if args.dry_run:
        print("dry run: no files written")
        return 0

    for passage_id in PASSAGE_ORDER:
        write_records(qa_dir / f"{passage_id}_all_formats.json", rows_by_passage[passage_id])
    write_records(master_path, merged_master)

    if not args.skip_pseudonymize:
        pseudonymize(
            qa_dir=qa_dir,
            output_dir=pseudonymized_dir,
            map_path=pseudonym_map,
            passage_ids=affected,
        )
        pseudo_by_passage = {
            passage_id: records_from(pseudonymized_dir / f"{passage_id}_all_formats.json")
            for passage_id in PASSAGE_ORDER
        }
        validate_gold_coverage(selected, pseudo_by_passage)
        print(f"BSB-pseudonymized Gold coverage: {len(selected)}/{len(selected)}")

    print(f"wrote canonical QA artifacts under {qa_dir}")
    if not args.skip_pseudonymize:
        print(f"wrote BSB-pseudonymized QA artifacts under {pseudonymized_dir}")
    return 0


def main() -> int:
    try:
        return run(parse_args())
    except (ImportError_, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
