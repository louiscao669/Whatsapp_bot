#!/usr/bin/env python3
"""Build a standalone HTML report from compact MQM translation score CSVs."""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_CSV = Path("evaluation/outputs/mqm_translation_scores.csv")
CATEGORY_LABELS = {
    "accuracy_addition": "Accuracy/Addition",
    "accuracy_mistranslation": "Accuracy/Mistranslation",
    "accuracy_omission": "Accuracy/Omission",
    "fluency_grammar": "Fluency/Grammar",
    "other": "Other",
    "terminology": "Terminology",
    "untranslated_non_translation": "Untranslated/Non-translation",
}
SEVERITY_COLUMNS = ["critical_count", "major_count", "minor_count"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize compact MQM scores across Luke chapters and methods."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"MQM CSV from mqm_score_translations.py. Default: {DEFAULT_CSV}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="HTML report path. Default: same path as --csv with .html suffix.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Optional path for the aggregated summary JSON.",
    )
    parser.add_argument(
        "--title",
        default="Luke 1-8 MQM Translation Scores",
        help="Report title.",
    )
    return parser.parse_args()


def as_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "None", "null"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    return int(round(as_float(value, float(default))))


def fmt(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def chapter_key(value: Any) -> tuple[int, str]:
    text = str(value)
    try:
        return (int(text), text)
    except ValueError:
        return (10_000, text)


def category_key_from_column(column: str) -> str:
    return column.removesuffix("_penalty")


def category_label(key: str) -> str:
    if key in CATEGORY_LABELS:
        return CATEGORY_LABELS[key]
    return key.replace("_", " ").title()


def category_penalty_columns(fieldnames: list[str]) -> list[str]:
    return [
        field
        for field in fieldnames
        if field.endswith("_penalty") and field != "weighted_penalty"
    ]


def load_rows(path: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if not path.exists():
        raise SystemExit(f"error: MQM CSV not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    if not rows:
        raise SystemExit(f"error: MQM CSV has no rows: {path}")

    categories = category_penalty_columns(fieldnames)
    for row in rows:
        row["chapter"] = str(row.get("chapter", ""))
        row["method"] = str(row.get("method", ""))
        row["source_words"] = as_float(row.get("source_words"))
        row["error_count"] = as_int(row.get("error_count"))
        row["weighted_penalty"] = as_float(row.get("weighted_penalty"))
        row["penalty_per_1000_words"] = as_float(row.get("penalty_per_1000_words"))
        row["mqm_quality_0_1"] = as_float(row.get("mqm_quality_0_1"))
        for column in categories + SEVERITY_COLUMNS:
            row[column] = as_float(row.get(column))
    return rows, fieldnames, categories


def aggregate_methods(
    rows: list[dict[str, Any]], categories: list[str]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["method"]].append(row)

    output = []
    for method, method_rows in grouped.items():
        source_words = sum(row["source_words"] for row in method_rows)
        weighted_penalty = sum(row["weighted_penalty"] for row in method_rows)
        penalty_per_1000 = (
            weighted_penalty / source_words * 1000 if source_words else None
        )
        category_penalties = {
            category_key_from_column(column): sum(row[column] for row in method_rows)
            for column in categories
        }
        dominant_category = max(
            category_penalties.items(), key=lambda item: item[1], default=(None, 0)
        )[0]
        output.append(
            {
                "method": method,
                "chapters": sorted(
                    {row["chapter"] for row in method_rows}, key=chapter_key
                ),
                "source_words": source_words,
                "error_count": sum(row["error_count"] for row in method_rows),
                "weighted_penalty": weighted_penalty,
                "penalty_per_1000_words": penalty_per_1000,
                "mqm_quality_0_1": (
                    1 / (1 + penalty_per_1000)
                    if penalty_per_1000 is not None
                    else None
                ),
                "category_penalties": category_penalties,
                "dominant_category": dominant_category,
                "severity_counts": {
                    column.removesuffix("_count"): sum(row[column] for row in method_rows)
                    for column in SEVERITY_COLUMNS
                },
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["penalty_per_1000_words"] is None,
            row["penalty_per_1000_words"] or 0,
            row["method"],
        ),
    )


def aggregate_chapters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["chapter"]].append(row)

    output = []
    for chapter, chapter_rows in grouped.items():
        source_words = sum(row["source_words"] for row in chapter_rows)
        weighted_penalty = sum(row["weighted_penalty"] for row in chapter_rows)
        penalties = [row["penalty_per_1000_words"] for row in chapter_rows]
        output.append(
            {
                "chapter": chapter,
                "methods": len({row["method"] for row in chapter_rows}),
                "weighted_penalty": weighted_penalty,
                "penalty_per_1000_words": (
                    weighted_penalty / source_words * 1000 if source_words else None
                ),
                "mean_method_penalty_per_1000": mean(penalties) if penalties else None,
                "best_method": min(
                    chapter_rows,
                    key=lambda row: row["penalty_per_1000_words"],
                )["method"],
                "worst_method": max(
                    chapter_rows,
                    key=lambda row: row["penalty_per_1000_words"],
                )["method"],
            }
        )
    return sorted(output, key=lambda row: chapter_key(row["chapter"]))


def rgb_for_penalty(value: float | None, max_value: float) -> str:
    if value is None:
        return "background:#f3f4f6;color:#6b7280"
    ratio = min(max(value / max_value, 0.0), 1.0) if max_value else 0.0
    red = int(235 + 10 * ratio)
    green = int(245 - 95 * ratio)
    blue = int(232 - 92 * ratio)
    return f"background:rgb({red},{green},{blue})"


def render_cards(
    rows: list[dict[str, Any]],
    method_summary: list[dict[str, Any]],
    categories: list[str],
) -> str:
    best = method_summary[0] if method_summary else None
    worst = method_summary[-1] if method_summary else None
    category_totals = {
        category_key_from_column(column): sum(row[column] for row in rows)
        for column in categories
    }
    dominant = max(category_totals.items(), key=lambda item: item[1], default=(None, 0))
    cards = [
        ("Rows", len(rows)),
        ("Chapters", len({row["chapter"] for row in rows})),
        ("Methods", len({row["method"] for row in rows})),
        (
            "Best Method",
            f"{best['method']} ({fmt(best['penalty_per_1000_words'])})" if best else "-",
        ),
        (
            "Worst Method",
            f"{worst['method']} ({fmt(worst['penalty_per_1000_words'])})"
            if worst
            else "-",
        ),
        (
            "Dominant Error",
            f"{category_label(dominant[0])} ({fmt(dominant[1], 0)})"
            if dominant[0]
            else "-",
        ),
    ]
    return "\n".join(
        f"<div class='card'><div class='label'>{escape(label)}</div>"
        f"<div class='value'>{escape(value)}</div></div>"
        for label, value in cards
    )


def render_method_table(method_summary: list[dict[str, Any]]) -> str:
    rows = []
    for row in method_summary:
        rows.append(
            "<tr>"
            f"<td>{escape(row['method'])}</td>"
            f"<td>{len(row['chapters'])}</td>"
            f"<td>{fmt(row['penalty_per_1000_words'])}</td>"
            f"<td>{fmt(row['weighted_penalty'], 0)}</td>"
            f"<td>{fmt(row['error_count'], 0)}</td>"
            f"<td>{fmt(row['severity_counts']['critical'], 0)}</td>"
            f"<td>{fmt(row['severity_counts']['major'], 0)}</td>"
            f"<td>{fmt(row['severity_counts']['minor'], 0)}</td>"
            f"<td>{escape(category_label(row['dominant_category']))}</td>"
            "</tr>"
        )
    return table(
        ["Method", "Ch.", "Penalty/1k", "Penalty", "Errors", "Critical", "Major", "Minor", "Top Category"],
        rows,
    )


def render_chapter_table(chapter_summary: list[dict[str, Any]]) -> str:
    rows = []
    for row in chapter_summary:
        rows.append(
            "<tr>"
            f"<td>Luke {escape(row['chapter'])}</td>"
            f"<td>{row['methods']}</td>"
            f"<td>{fmt(row['penalty_per_1000_words'])}</td>"
            f"<td>{fmt(row['mean_method_penalty_per_1000'])}</td>"
            f"<td>{escape(row['best_method'])}</td>"
            f"<td>{escape(row['worst_method'])}</td>"
            "</tr>"
        )
    return table(
        ["Chapter", "Methods", "Weighted Penalty/1k", "Mean Method Penalty/1k", "Best", "Worst"],
        rows,
    )


def render_heatmap(rows: list[dict[str, Any]], method_summary: list[dict[str, Any]]) -> str:
    chapters = sorted({row["chapter"] for row in rows}, key=chapter_key)
    methods = [row["method"] for row in method_summary]
    lookup = {(row["method"], row["chapter"]): row for row in rows}
    max_value = max((row["penalty_per_1000_words"] for row in rows), default=1.0) or 1.0

    body = []
    for method in methods:
        cells = [f"<td class='sticky'>{escape(method)}</td>"]
        for chapter in chapters:
            value = lookup.get((method, chapter), {}).get("penalty_per_1000_words")
            cells.append(
                f"<td class='heat' style='{rgb_for_penalty(value, max_value)}'>"
                f"{fmt(value)}</td>"
            )
        body.append("<tr>" + "".join(cells) + "</tr>")
    headers = ["Method"] + [f"Luke {chapter}" for chapter in chapters]
    return table(headers, body, extra_class="heatmap")


def render_category_table(
    method_summary: list[dict[str, Any]], categories: list[str]
) -> str:
    category_keys = [category_key_from_column(column) for column in categories]
    rows = []
    for row in method_summary:
        total = sum(row["category_penalties"].values())
        cells = [f"<td>{escape(row['method'])}</td>"]
        for key in category_keys:
            value = row["category_penalties"].get(key, 0)
            share = value / total if total else 0
            cells.append(
                f"<td><span>{fmt(value, 0)}</span>"
                f"<div class='bar'><i style='width:{share * 100:.1f}%'></i></div></td>"
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    headers = ["Method"] + [category_label(key) for key in category_keys]
    return table(headers, rows)


def table(headers: list[str], rows: list[str], extra_class: str = "") -> str:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_html = "\n".join(rows)
    class_attr = f" class='{extra_class}'" if extra_class else ""
    return f"<table{class_attr}><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def build_html(
    title: str,
    source_csv: Path,
    rows: list[dict[str, Any]],
    method_summary: list[dict[str, Any]],
    chapter_summary: list[dict[str, Any]],
    categories: list[str],
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #111827;
      --muted: #6b7280;
      --border: #d1d5db;
      --panel: #f9fafb;
      --accent: #0f766e;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: white;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 30px 0 10px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    p {{
      color: var(--muted);
      margin: 0 0 18px;
      line-height: 1.5;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 10px;
      margin: 18px 0 24px;
    }}
    .card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
      background: var(--panel);
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .value {{
      margin-top: 6px;
      font-size: 18px;
      font-weight: 650;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 760px;
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 9px 10px;
      text-align: right;
      vertical-align: middle;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    th {{
      background: #f3f4f6;
      font-weight: 650;
      color: #374151;
    }}
    tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .heatmap td.heat {{
      font-variant-numeric: tabular-nums;
      font-weight: 650;
    }}
    .sticky {{
      position: sticky;
      left: 0;
      background: white;
      z-index: 1;
      font-weight: 600;
    }}
    .bar {{
      height: 5px;
      margin-top: 4px;
      background: #e5e7eb;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar i {{
      display: block;
      height: 100%;
      background: var(--accent);
    }}
    .note {{
      margin-top: 22px;
      font-size: 12px;
    }}
  </style>
</head>
<body>
<main>
  <h1>{escape(title)}</h1>
  <p>Source CSV: {escape(source_csv)}. Lower MQM penalty is better; heatmap cells show penalty per 1,000 source words.</p>
  <section class="cards">
    {render_cards(rows, method_summary, categories)}
  </section>

  <h2>Method Ranking</h2>
  <div class="table-wrap">{render_method_table(method_summary)}</div>

  <h2>Chapter Summary</h2>
  <div class="table-wrap">{render_chapter_table(chapter_summary)}</div>

  <h2>Penalty Heatmap</h2>
  <div class="table-wrap">{render_heatmap(rows, method_summary)}</div>

  <h2>Error Category Penalties</h2>
  <div class="table-wrap">{render_category_table(method_summary, categories)}</div>

  <p class="note">MQM penalties use the scorer's compact severity weights. Category bars show each method's within-method penalty distribution.</p>
</main>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    rows, _fieldnames, categories = load_rows(args.csv)
    method_summary = aggregate_methods(rows, categories)
    chapter_summary = aggregate_chapters(rows)
    output = args.output or args.csv.with_suffix(".html")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        build_html(
            args.title,
            args.csv,
            rows,
            method_summary,
            chapter_summary,
            categories,
        ),
        encoding="utf-8",
    )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "source_csv": str(args.csv),
                    "rows": len(rows),
                    "methods": method_summary,
                    "chapters": chapter_summary,
                    "categories": [
                        category_label(category_key_from_column(column))
                        for column in categories
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print(f"wrote {output}")
    if args.json:
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
