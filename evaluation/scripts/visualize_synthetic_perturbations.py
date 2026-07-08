#!/usr/bin/env python3
"""Create an HTML visualization for synthetic perturbation experiments."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path
from typing import Any

from report_synthetic_perturbations import (
    DEFAULT_ROOT,
    DEFAULT_SCORE_FILE,
    EXPERIMENTS,
    build_analysis,
    collect_report,
    discover_chapters,
    fmt,
    pct,
)


DEFAULT_OUTPUT = Path("evaluation/outputs/reports/synthetic_perturbation_visualization.html")
SERIES_COLORS = {
    "combined": "#1f5fbf",
    "open": "#2f855a",
    "mcq": "#b7791f",
    "neutral": "#1f5fbf",
    "bad": "#b83280",
    "adversarial": "#c2410c",
    "name": "#6b46c1",
    "style": "#2c7a7b",
    "single": "#1f5fbf",
}


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def rate_from_variant(variant: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)%", variant)
    if not match:
        return None
    return float(match.group(1))


def series_from_variant(experiment: str, variant: str) -> str:
    if variant == "0%":
        return "baseline"
    if experiment == "addition":
        return variant.split("_", 1)[0]
    if experiment in {"inconsistency", "local_inconsistency"}:
        return variant.split("_", 1)[0]
    return "single"


def row_rate(row: dict) -> float:
    value = row.get("actual_rate_mean")
    if isinstance(value, (int, float)):
        return float(value) * 100
    parsed = rate_from_variant(str(row.get("variant") or ""))
    return parsed if parsed is not None else 0.0


def sorted_chart_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (series_from_variant(row["experiment"], row["variant"]), row_rate(row), row["variant"]))


def chart_series(rows: list[dict], metric: str) -> dict[str, list[dict]]:
    scored = [
        row
        for row in rows
        if row.get(metric) is not None and row.get("status") != "TBD"
    ]
    if not scored:
        return {}

    baseline = next((row for row in scored if row.get("variant") == "0%"), None)
    grouped: dict[str, list[dict]] = {}
    non_baseline = [row for row in scored if row.get("variant") != "0%"]
    if non_baseline:
        series_names = sorted(
            {
                series_from_variant(row["experiment"], row["variant"])
                for row in non_baseline
            }
        )
    else:
        series_names = ["single"]

    for name in series_names:
        points = []
        if baseline:
            points.append({"x": 0.0, "y": baseline[metric], "label": "0%"})
        for row in non_baseline:
            if series_from_variant(row["experiment"], row["variant"]) != name:
                continue
            points.append(
                {
                    "x": row_rate(row),
                    "y": row[metric],
                    "label": row["variant"],
                }
            )
        grouped[name] = sorted(points, key=lambda point: point["x"])
    return grouped


def render_svg_chart(rows: list[dict], metric: str, title: str) -> str:
    grouped = chart_series(rows, metric)
    if not grouped:
        return '<div class="empty">No scored data yet.</div>'

    values = [point["y"] for points in grouped.values() for point in points]
    xs = [point["x"] for points in grouped.values() for point in points]
    min_y = max(0.0, min(values) - 0.05)
    max_y = min(1.0, max(values) + 0.05)
    if math.isclose(min_y, max_y):
        min_y = max(0.0, min_y - 0.1)
        max_y = min(1.0, max_y + 0.1)
    max_x = max(30.0, max(xs) if xs else 30.0)

    width = 780
    height = 250
    left = 54
    right = 20
    top = 24
    bottom = 42
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(value: float) -> float:
        return left + (value / max_x) * plot_w

    def sy(value: float) -> float:
        return top + ((max_y - value) / (max_y - min_y)) * plot_h

    grid = []
    for step in range(0, int(max_x) + 1, 5):
        x = sx(float(step))
        grid.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="grid"/>')
        grid.append(f'<text x="{x:.1f}" y="{height - 15}" class="axis" text-anchor="middle">{step}%</text>')
    for value in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        if value < min_y or value > max_y:
            continue
        y = sy(value)
        grid.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        grid.append(f'<text x="{left - 8}" y="{y + 4:.1f}" class="axis" text-anchor="end">{value:.1f}</text>')

    paths = []
    legend = []
    for index, (name, points) in enumerate(grouped.items()):
        color = SERIES_COLORS.get(name, SERIES_COLORS["single"])
        if len(points) == 1:
            point = points[0]
            d = f"M {sx(point['x']):.1f} {sy(point['y']):.1f}"
        else:
            d = " ".join(
                f"{'M' if i == 0 else 'L'} {sx(point['x']):.1f} {sy(point['y']):.1f}"
                for i, point in enumerate(points)
            )
        paths.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for point in points:
            x = sx(point["x"])
            y = sy(point["y"])
            label = f"{point['label']}: {point['y']:.3f}"
            paths.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}">'
                f"<title>{escape(label)}</title></circle>"
            )
        legend.append(
            f'<span><i style="background:{color}"></i>{escape(name)}</span>'
        )

    return f"""
<div class="chart">
  <div class="chart-title">{escape(title)}</div>
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
    <rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#fff"/>
    {''.join(grid)}
    <line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" class="axis-line"/>
    <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis-line"/>
    {''.join(paths)}
  </svg>
  <div class="legend">{''.join(legend)}</div>
</div>
"""


def render_table(rows: list[dict]) -> str:
    lines = [
        "<table>",
        "<thead><tr><th>Variant</th><th>Status</th><th>Chapters</th><th>Actual</th><th>Combined</th><th>MCQ</th><th>Open</th><th>Confidence</th><th>Insufficient</th><th>Evidence</th><th>Errors</th></tr></thead>",
        "<tbody>",
    ]
    for row in rows:
        lines.append(
            "<tr>"
            f"<td>{escape(row['variant'])}</td>"
            f"<td><span class=\"status {escape(row['status'].lower())}\">{escape(row['status'])}</span></td>"
            f"<td>{escape(row['chapters_scored'])}</td>"
            f"<td>{pct(row['actual_rate_mean'])}</td>"
            f"<td>{fmt(row['combined_score'])}</td>"
            f"<td>{pct(row['mcq_accuracy'])}</td>"
            f"<td>{fmt(row['open_llm_score_mean'])}</td>"
            f"<td>{fmt(row['answer_confidence_mean'])}</td>"
            f"<td>{pct(row['insufficient_information_rate'])}</td>"
            f"<td>{pct(row['evidence_supported_rate'])}</td>"
            f"<td>{fmt(row['generation_errors'])}</td>"
            "</tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return "\n".join(lines)


def render_experiment(
    name: str,
    rows: list[dict],
    chapters: list[int],
    *,
    title: str | None = None,
    description: str | None = None,
    section_id: str | None = None,
) -> str:
    rows = sorted_chart_rows(rows)
    display_title = title or name
    section_id = section_id or name
    description = description or EXPERIMENTS[name]["description"]
    chart_block = "\n".join(
        [
            render_svg_chart(rows, "combined_score", "Combined Score"),
            render_svg_chart(rows, "mcq_accuracy", "MCQ Accuracy"),
            render_svg_chart(rows, "open_llm_score_mean", "Open LLM Score"),
            render_svg_chart(rows, "answer_confidence_mean", "Answer Confidence"),
            render_svg_chart(
                rows,
                "insufficient_information_rate",
                "Insufficient Information Rate (Lower Is Better)",
            ),
            render_svg_chart(
                rows,
                "evidence_supported_rate",
                "Evidence Supported Rate",
            ),
        ]
    )
    chapter_text = ",".join(str(chapter) for chapter in chapters) or "none"
    definitions = ""
    if name == "addition":
        definitions = """
      <ul class="definitions">
        <li><strong>neutral</strong>: plausible but mostly irrelevant extra information.</li>
        <li><strong>bad</strong>: noisy or incorrect additions that are not directly MCQ distractors.</li>
        <li><strong>adversarial</strong>: misleading additions derived from wrong MCQ options and inserted near the referenced verse when possible.</li>
      </ul>
"""
    return f"""
<section class="experiment" id="{escape(section_id)}">
  <div class="section-head">
    <div>
      <h2>{escape(display_title)}</h2>
      <p>{escape(description)}</p>
      {definitions}
    </div>
    <span class="chapters">Chapters: {escape(chapter_text)}</span>
  </div>
  <div class="charts">{chart_block}</div>
  {render_table(rows)}
</section>
"""


def display_experiment_sections(
    by_experiment: dict[str, list[dict]],
    chapter_map: dict[str, list[int]],
) -> list[dict]:
    sections = []
    for name in EXPERIMENTS:
        if name not in by_experiment:
            continue
        if name not in {"inconsistency", "local_inconsistency"}:
            sections.append(
                {
                    "id": name,
                    "title": name,
                    "source_experiment": name,
                    "rows": by_experiment[name],
                    "chapters": chapter_map.get(name, []),
                    "description": EXPERIMENTS[name]["description"],
                }
            )
            continue

        rows = by_experiment[name]
        name_rows = [
            row
            for row in rows
            if row.get("variant") == "0%" or str(row.get("variant") or "").startswith("name_")
        ]
        style_rows = [
            row
            for row in rows
            if row.get("variant") == "0%" or str(row.get("variant") or "").startswith("style_")
        ]
        title_prefix = "local " if name == "local_inconsistency" else ""
        description_prefix = (
            "MQM Inconsistency > Question-local "
            if name == "local_inconsistency"
            else "MQM Inconsistency > "
        )
        sections.extend(
            [
                {
                    "id": f"{name}-name",
                    "title": f"{title_prefix}name inconsistency",
                    "source_experiment": name,
                    "rows": name_rows,
                    "chapters": chapter_map.get(name, []),
                    "description": (
                        f"{description_prefix}Name/entity: inconsistent entity names "
                        "or placeholder renderings."
                    ),
                },
                {
                    "id": f"{name}-style",
                    "title": f"{title_prefix}style inconsistency",
                    "source_experiment": name,
                    "rows": style_rows,
                    "chapters": chapter_map.get(name, []),
                    "description": (
                        f"{description_prefix}Style/register: inconsistent formality, "
                        "tone, or wording style."
                    ),
                },
            ]
        )
    return sections


def render_html(
    *,
    rows: list[dict],
    chapter_map: dict[str, list[int]],
    blank_experiments: set[str],
    score_file: str,
) -> str:
    by_experiment: dict[str, list[dict]] = {}
    for row in rows:
        by_experiment.setdefault(row["experiment"], []).append(row)
    analysis = build_analysis(rows, blank_experiments)
    display_sections = display_experiment_sections(by_experiment, chapter_map)
    nav = "".join(
        f'<a href="#{escape(section["id"])}">{escape(section["title"])}</a>'
        for section in display_sections
    )
    sections = "".join(
        render_experiment(
            section["source_experiment"],
            section["rows"],
            section["chapters"],
            title=section["title"],
            description=section["description"],
            section_id=section["id"],
        )
        for section in display_sections
    )
    data_json = json.dumps(rows, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Synthetic Perturbation Visualization</title>
  <style>
    :root {{
      --ink: #202124;
      --muted: #64748b;
      --line: #d8dee8;
      --panel: #f7f8fb;
      --blue: #1f5fbf;
      --green: #2f855a;
      --amber: #b7791f;
      --red: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #fff;
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 20px; }}
    p {{ margin: 6px 0 0; color: var(--muted); }}
    .definitions {{
      margin: 8px 0 0;
      padding-left: 18px;
      color: var(--muted);
      max-width: 760px;
    }}
    .definitions li {{ margin: 3px 0; }}
    .definitions strong {{ color: var(--ink); }}
    nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 18px 0;
    }}
    nav a {{
      color: var(--blue);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 5px 8px;
      text-decoration: none;
      background: #fff;
    }}
    .summary, .experiment {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
      margin: 18px 0;
    }}
    .summary ul {{
      margin: 10px 0 0;
      padding-left: 20px;
    }}
    .summary li {{ margin: 6px 0; }}
    .section-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .chapters {{
      color: var(--muted);
      white-space: nowrap;
      font-size: 13px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 4px 7px;
      background: #fff;
    }}
    .charts {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .chart {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px;
    }}
    .chart-title {{
      font-weight: 650;
      margin-bottom: 4px;
    }}
    svg {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .grid {{ stroke: #e6eaf0; stroke-width: 1; }}
    .axis-line {{ stroke: #9aa4b2; stroke-width: 1; }}
    .axis {{ fill: #667085; font-size: 11px; }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
    }}
    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .legend i {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }}
    .empty {{
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 6px;
      padding: 24px;
      background: #fff;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fff;
      overflow: hidden;
      border-radius: 8px;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #eef1f5;
      font-weight: 650;
    }}
    .status {{
      display: inline-block;
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      background: #e8eef8;
      color: var(--blue);
    }}
    .status.complete {{ background: #e2f4e8; color: var(--green); }}
    .status.partial {{ background: #fff5d6; color: var(--amber); }}
    .status.missing, .status.tbd {{ background: #f1f5f9; color: var(--muted); }}
    .data-note {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 16px;
    }}
  </style>
</head>
<body>
<main>
  <h1>Synthetic Perturbation Visualization</h1>
  <p>Score file: <code>{escape(score_file)}</code>. This HTML reads the currently available scored outputs; blank experiments can be filled by rerunning the script after those scores exist.</p>
  <nav>{nav}</nav>
  <section class="summary">
    <h2>High-Level Notes</h2>
    <ul>{''.join(f'<li>{escape(bullet)}</li>' for bullet in analysis)}</ul>
  </section>
  {sections}
  <p class="data-note">Raw aggregated rows are embedded in this file as JSON for inspection.</p>
  <script type="application/json" id="synthetic-perturbation-data">{escape(data_json)}</script>
</main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an HTML visualization for synthetic perturbation results."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--chapters", type=int, nargs="+")
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=sorted(EXPERIMENTS),
        default=list(EXPERIMENTS),
    )
    parser.add_argument("--score-file", default=DEFAULT_SCORE_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--blank-experiments",
        nargs="*",
        choices=sorted(EXPERIMENTS),
        default=[],
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chapters = args.chapters if args.chapters else discover_chapters(args.root)
    rows, chapter_map = collect_report(
        root=args.root,
        chapters=chapters,
        experiments=args.experiments,
        score_file=args.score_file,
        blank_experiments=set(args.blank_experiments),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_html(
            rows=rows,
            chapter_map=chapter_map,
            blank_experiments=set(args.blank_experiments),
            score_file=args.score_file,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
