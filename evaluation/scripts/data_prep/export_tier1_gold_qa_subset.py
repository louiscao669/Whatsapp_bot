#!/usr/bin/env python3
"""Export exactly the selected Gold-72 QAs and their disjoint verse windows."""

from __future__ import annotations

import argparse
import csv
import json
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


class ExportError(RuntimeError):
    pass


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"cannot read {path}: {exc}") from exc


def records(path: Path, key: str | None = None) -> list[dict[str, Any]]:
    payload = read_json(path)
    if key and isinstance(payload, dict):
        payload = payload.get(key)
    elif isinstance(payload, dict):
        payload = payload.get("items")
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ExportError(f"{path}: expected a JSON record list")
    return payload


def passage_metadata(path: Path) -> dict[str, dict[str, int]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return {
                row["id"]: {
                    "chapter_start": int(row["chapter_start"]),
                    "verse_start": int(row["verse_start"]),
                    "chapter_end": int(row["chapter_end"]),
                    "verse_end": int(row["verse_end"]),
                }
                for row in csv.DictReader(handle)
            }
    except (OSError, KeyError, ValueError) as exc:
        raise ExportError(f"cannot parse passage metadata {path}: {exc}") from exc


def verse_labels_by_ordinal(
    source_windows: list[dict[str, Any]],
    metadata: dict[str, dict[str, int]],
) -> dict[str, dict[int, str]]:
    observed: dict[str, dict[int, str]] = {}
    for row in source_windows:
        passage_id = str(row.get("passage_id") or "")
        labels = row.get("window") or []
        ordinals = row.get("window_ordinals") or []
        target = observed.setdefault(passage_id, {})
        for ordinal, label in zip(ordinals, labels):
            ordinal = int(ordinal)
            label = str(label)
            previous = target.get(ordinal)
            if previous is not None and previous != label:
                raise ExportError(
                    f"{passage_id}: ordinal {ordinal} maps to both {previous} and {label}"
                )
            target[ordinal] = label

    complete: dict[str, dict[int, str]] = {}
    for passage_id, meta in metadata.items():
        start_chapter = meta["chapter_start"]
        start_verse = meta["verse_start"]
        end_chapter = meta["chapter_end"]
        end_verse = meta["verse_end"]
        labels: dict[int, str] = {}
        if start_chapter == end_chapter:
            for ordinal, verse in enumerate(range(start_verse, end_verse + 1)):
                labels[ordinal] = f"{start_chapter}:{verse}"
        else:
            next_chapter_anchors = []
            for ordinal, label in observed.get(passage_id, {}).items():
                chapter_text, verse_text = label.split(":", 1)
                if int(chapter_text) == end_chapter:
                    next_chapter_anchors.append(ordinal - (int(verse_text) - 1))
            if not next_chapter_anchors or len(set(next_chapter_anchors)) != 1:
                raise ExportError(
                    f"{passage_id}: cannot infer the cross-chapter boundary"
                )
            boundary = next_chapter_anchors[0]
            for ordinal in range(boundary):
                labels[ordinal] = f"{start_chapter}:{start_verse + ordinal}"
            for ordinal in range(boundary, boundary + end_verse):
                labels[ordinal] = f"{end_chapter}:{ordinal - boundary + 1}"

        for ordinal, label in observed.get(passage_id, {}).items():
            if labels.get(ordinal) != label:
                raise ExportError(
                    f"{passage_id}: inferred {labels.get(ordinal)} for ordinal {ordinal}, "
                    f"but source windows say {label}"
                )
        complete[passage_id] = labels
    return complete


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", default="evaluation/datasets/tier1_gold_72.json")
    parser.add_argument(
        "--source-dir",
        default="evaluation/datasets/pseudonymized/qa/tier1_bsb",
    )
    parser.add_argument(
        "--out-dir",
        default="evaluation/datasets/pseudonymized/qa/tier1_bsb_gold72",
    )
    parser.add_argument(
        "--source-windows",
        default="QA_algorithm/inputs/tier1_qa_verse_windows.json",
    )
    parser.add_argument(
        "--passage-csv",
        default="evaluation/datasets/obscure_narrative_passages_tier1.csv",
    )
    parser.add_argument(
        "--windows-out",
        default="evaluation/datasets/tier1_gold_72_windows.json",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    selection_path = repo_path(args.selection)
    source_dir = repo_path(args.source_dir)
    out_dir = repo_path(args.out_dir)
    source_windows_path = repo_path(args.source_windows)
    passage_csv = repo_path(args.passage_csv)
    windows_out = repo_path(args.windows_out)

    selected = records(selection_path)
    if len(selected) != 72 or len({row.get("content_id") for row in selected}) != 72:
        raise ExportError(f"{selection_path}: expected 72 unique content IDs")
    wanted = {str(row["content_id"]): row for row in selected}
    output_by_passage: dict[str, list[dict[str, Any]]] = {}
    found: set[str] = set()

    for passage_id in PASSAGE_ORDER:
        source_path = source_dir / f"{passage_id}_all_formats.json"
        rows = records(source_path, key=None)
        subset = []
        for row in rows:
            content_id = str(row.get("content_id") or "")
            if content_id not in wanted:
                continue
            if not isinstance(row.get("open"), dict) or not isinstance(row.get("mcq"), dict):
                raise ExportError(f"{content_id}: open and MCQ artifacts are both required")
            subset.append(row)
            found.add(content_id)
        output_by_passage[passage_id] = subset

    missing = sorted(set(wanted) - found)
    if missing:
        raise ExportError(f"selected QA artifacts are missing: {missing}")
    if sum(map(len, output_by_passage.values())) != 72:
        raise ExportError("selected QA export did not resolve to exactly 72 records")

    source_windows = records(source_windows_path, key="windows")
    label_map = verse_labels_by_ordinal(source_windows, passage_metadata(passage_csv))
    window_rows = []
    for item in selected:
        passage_id = str(item["passage_id"])
        ordinals = [int(value) for value in item.get("window_ordinals") or []]
        if len(ordinals) != 3:
            raise ExportError(f"{item['content_id']}: expected a three-verse window")
        try:
            labels = [label_map[passage_id][ordinal] for ordinal in ordinals]
        except KeyError as exc:
            raise ExportError(f"{item['content_id']}: cannot label window ordinal {exc}") from exc
        window_rows.append(
            {
                "content_id": item["content_id"],
                "passage_id": passage_id,
                "window": labels,
                "window_ordinals": ordinals,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    for passage_id, rows in output_by_passage.items():
        (out_dir / f"{passage_id}_all_formats.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"  {passage_id}: {len(rows)}")
    windows_out.parent.mkdir(parents=True, exist_ok=True)
    windows_out.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "window_size": 3,
                "selection_source": str(selection_path.relative_to(REPO)),
                "windows": window_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"exported 72/72 QAs to {out_dir}")
    print(f"exported 72 disjoint windows to {windows_out}")
    return 0


def main() -> int:
    try:
        return run(parse_args())
    except (ExportError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
