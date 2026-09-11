#!/usr/bin/env python3
"""Show fitted PTQ values by item, optionally joined to verse metadata."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


PREFERRED_VERSE_COLUMNS = (
    "verse",
    "passage_reference",
    "passage",
    "reference",
    "passage_id",
)


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_mapping(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}

    rows = read_csv_dicts(path)
    if not rows:
        raise ValueError(f"{path} has no rows")
    if "item" not in rows[0]:
        raise ValueError(f"{path} must include an item column")

    return {row["item"]: row for row in rows}


def verse_label(row: dict[str, str], mapping_row: dict[str, str] | None) -> str:
    merged = {**row, **(mapping_row or {})}
    for column in PREFERRED_VERSE_COLUMNS:
        value = merged.get(column, "").strip()
        if value:
            return value
    return row["item"]


def load_ptq_rows(ptq_csv: Path, mapping_csv: Path | None) -> list[dict[str, str]]:
    ptq_rows = read_csv_dicts(ptq_csv)
    if not ptq_rows:
        raise ValueError(f"{ptq_csv} has no rows")
    if "item" not in ptq_rows[0] or "ptq" not in ptq_rows[0]:
        raise ValueError(f"{ptq_csv} must include item and ptq columns")

    mapping = read_mapping(mapping_csv)
    output_rows = []
    for row in ptq_rows:
        mapping_row = mapping.get(row["item"], {})
        output_rows.append(
            {
                "item": row["item"],
                "verse": verse_label(row, mapping_row),
                "ptq": f"{float(row['ptq']):.6f}",
                "difficulty": row.get("difficulty", mapping_row.get("difficulty", "")),
            }
        )
    return output_rows


def sort_rows(rows: list[dict[str, str]], sort_key: str) -> list[dict[str, str]]:
    if sort_key == "ptq":
        return sorted(rows, key=lambda row: float(row["ptq"]), reverse=True)
    if sort_key == "difficulty":
        return sorted(
            rows,
            key=lambda row: float(row["difficulty"]) if row["difficulty"] else 0.0,
        )
    return sorted(rows, key=lambda row: row[sort_key])


def print_table(rows: list[dict[str, str]]) -> None:
    columns = ["item", "verse", "ptq", "difficulty"]
    widths = {
        column: max(len(column), *(len(row[column]) for row in rows))
        for column in columns
    }
    header = "  ".join(column.ljust(widths[column]) for column in columns)
    print(header)
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(row[column].ljust(widths[column]) for column in columns))


def write_csv(rows: list[dict[str, str]], path: Path | None) -> None:
    handle = path.open("w", newline="") if path else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=["item", "verse", "ptq", "difficulty"])
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if path:
            handle.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "ptq_csv",
        type=Path,
        help=(
            "Fitted PTQ CSV, such as output/binary_fit_ptq.csv or "
            "output/continuous_fit_ptq.csv."
        ),
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        help=(
            "Optional CSV with item plus verse metadata. Supported columns include "
            "item,verse or item,passage_reference."
        ),
    )
    parser.add_argument(
        "--sort",
        choices=["item", "verse", "ptq", "difficulty"],
        default="item",
    )
    parser.add_argument("--limit", type=int, help="Show only the first N rows.")
    parser.add_argument("--csv", action="store_true", help="Print CSV instead of a table.")
    parser.add_argument("--output", type=Path, help="Write CSV output to this path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = sort_rows(load_ptq_rows(args.ptq_csv, args.mapping), args.sort)
    if args.limit is not None:
        rows = rows[: args.limit]

    if args.output or args.csv:
        write_csv(rows, args.output)
    else:
        print_table(rows)


if __name__ == "__main__":
    main()
