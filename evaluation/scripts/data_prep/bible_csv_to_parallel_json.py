#!/usr/bin/env python3
"""Convert verse-aligned English/Chinese Bible CSV to parallel-corpus JSON."""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


class ParallelCorpusError(Exception):
    pass


def normalize_ref(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def book_code(ref: str) -> str:
    return (normalize_ref(ref).split() or [""])[0]


def convert_csv(
    input_csv: Path,
    *,
    source_column: str,
    target_column: str,
    ref_column: str,
    books: set[str],
    limit: int | None,
    include_ref: bool,
) -> list[dict[str, Any]]:
    rows = []
    with input_csv.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = [
            column
            for column in (source_column, target_column, ref_column)
            if column not in fieldnames
        ]
        if missing:
            raise ParallelCorpusError(
                f"CSV missing required column(s): {', '.join(missing)}"
            )

        for row in reader:
            ref = normalize_ref(row.get(ref_column, ""))
            if books and book_code(ref) not in books:
                continue
            source = str(row.get(source_column) or "").strip()
            target = str(row.get(target_column) or "").strip()
            if not source or not target:
                continue

            item: dict[str, Any] = {
                "source": source,
                "target": target,
            }
            if include_ref:
                item["ref"] = ref
            rows.append(item)
            if limit and len(rows) >= limit:
                break

    if not rows:
        raise ParallelCorpusError("No parallel rows matched the requested filters.")
    return rows


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert The_bible_en_zh.csv into the JSON shape expected by "
            "--parallel-corpus-json."
        )
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="Input verse-aligned Bible CSV.",
    )
    parser.add_argument(
        "output_json",
        type=Path,
        help="Output JSON file for --parallel-corpus-json.",
    )
    parser.add_argument(
        "--source-column",
        default="verse_eng",
        help="English/source column. Default: verse_eng.",
    )
    parser.add_argument(
        "--target-column",
        default="verse_zhcn",
        help="Chinese/target column. Default: verse_zhcn.",
    )
    parser.add_argument(
        "--ref-column",
        default="ref",
        help="Verse reference column. Default: ref.",
    )
    parser.add_argument(
        "--books",
        nargs="+",
        default=[],
        help="Optional book-code filter, e.g. --books Luk Jhn.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of verse pairs to write.",
    )
    parser.add_argument(
        "--no-ref",
        action="store_true",
        help="Do not include ref in output items.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        print("error: --limit must be at least 1", file=sys.stderr)
        return 2

    try:
        rows = convert_csv(
            args.input_csv,
            source_column=args.source_column,
            target_column=args.target_column,
            ref_column=args.ref_column,
            books=set(args.books),
            limit=args.limit,
            include_ref=not args.no_ref,
        )
        write_json(args.output_json, rows)
    except ParallelCorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(rows)} parallel verse pair(s) to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
