#!/usr/bin/env python3
"""Visualize answer-model comparison CSV outputs as a self-contained HTML page."""

from __future__ import annotations

import argparse
import csv
import html
from collections import defaultdict
from pathlib import Path
from typing import Any


MODEL_COLORS = {
    "llama 1b": "#ef6f6c",
    "1.5b": "#f7b32b",
    "1.7b": "#2fbf71",
    "llama 3b": "#3b82f6",
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fnum(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def pct(value: Any) -> str:
    number = fnum(value)
    return "" if number is None else f"{number * 100:.1f}%"


def model_color(model: str) -> str:
    return MODEL_COLORS.get(model, "#64748b")


def metric_bar(value: Any, *, width: int = 180) -> str:
    number = fnum(value)
    if number is None:
        return "<span class='muted'>n/a</span>"
    bounded = max(0.0, min(1.0, number))
    return (
        f"<div class='metric-bar' style='width:{width}px'>"
        f"<span style='width:{bounded * 100:.1f}%'></span>"
        f"</div><b>{bounded * 100:.1f}%</b>"
    )


def overall_cards(rows: list[dict]) -> str:
    cards = []
    for row in sorted(rows, key=lambda r: fnum(r.get("combined_mean")) or 0, reverse=True):
        model = row.get("model", "")
        cards.append(
            f"""
            <section class="model-card" style="--accent:{model_color(model)}">
              <div class="model-card-top">
                <h2>{esc(model)}</h2>
                <span>{esc(row.get("item_count"))} items</span>
              </div>
              <div class="big-score">{pct(row.get("combined_mean"))}</div>
              <div class="metric-row"><span>MCQ accuracy</span>{metric_bar(row.get("mcq_accuracy"))}</div>
              <div class="metric-row"><span>Open LLM mean</span>{metric_bar(row.get("open_llm_mean"))}</div>
            </section>
            """
        )
    return "\n".join(cards)


def grouped_chapter_chart(rows: list[dict], metric: str) -> str:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    models = []
    for row in rows:
        grouped[(row.get("chapter", ""), row.get("method", ""))].append(row)
        if row.get("model") not in models:
            models.append(row.get("model"))
    groups = sorted(grouped.items(), key=lambda item: (int(item[0][0]), item[0][1]))
    if not groups:
        return "<p class='muted'>No chapter/method rows.</p>"

    blocks = []
    for (chapter, method), group_rows in groups:
        by_model = {row.get("model"): row for row in group_rows}
        bars = []
        for model in models:
            value = fnum((by_model.get(model) or {}).get(metric))
            if value is None:
                bars.append(
                    f"""
                    <div class="chapter-bar">
                      <span class="bar-label">{esc(model)}</span>
                      <div class="bar-track empty"><i style="width:0%; background:{model_color(model)}"></i></div>
                      <b class="muted">n/a</b>
                    </div>
                    """
                )
            else:
                bars.append(
                    f"""
                    <div class="chapter-bar">
                      <span class="bar-label">{esc(model)}</span>
                      <div class="bar-track"><i style="width:{max(0, min(1, value)) * 100:.1f}%; background:{model_color(model)}"></i></div>
                      <b>{value * 100:.1f}%</b>
                    </div>
                    """
                )
        blocks.append(
            f"""
            <article class="chapter-group">
              <div class="chapter-title">Luke {esc(chapter)} <span>{esc(method)}</span></div>
              {''.join(bars)}
            </article>
            """
        )
    return "\n".join(blocks)


def disagreement_table(rows: list[dict], models: list[str], limit: int) -> str:
    disagreements = [
        row for row in rows
        if str(row.get("models_disagree")).lower() == "true"
    ]
    disagreements.sort(key=lambda r: fnum(r.get("score_range")) or 0, reverse=True)
    disagreements = disagreements[:limit]
    if not disagreements:
        return "<p class='muted'>No item-level disagreements.</p>"

    model_score_headers = "".join(f"<th>{esc(model)} score</th>" for model in models)
    answer_headers = "".join(f"<th>{esc(model)} answer</th>" for model in models)
    body = []
    for row in disagreements:
        model_scores = "".join(
            f"<td>{pct(row.get(f'{model}_score'))}</td>" for model in models
        )
        answers = "".join(
            f"<td class='answer-cell'>{esc(row.get(f'{model}_answer'))}</td>"
            for model in models
        )
        body.append(
            f"""
            <tr>
              <td>Luke {esc(row.get("chapter"))}</td>
              <td>{esc(row.get("method"))}</td>
              <td>{esc(row.get("passage_reference"))}</td>
              <td>{esc(row.get("q_type"))}</td>
              <td class="question-cell">{esc(row.get("question"))}</td>
              <td>{pct(row.get("score_range"))}</td>
              {model_scores}
              {answers}
            </tr>
            """
        )
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Chapter</th><th>Method</th><th>Reference</th><th>Type</th>"
        "<th>Question</th><th>Score range</th>"
        f"{model_score_headers}{answer_headers}"
        "</tr></thead><tbody>"
        + "\n".join(body)
        + "</tbody></table></div>"
    )


def method_summary_table(rows: list[dict], limit: int = 80) -> str:
    ordered = sorted(
        rows,
        key=lambda r: (
            int(r.get("chapter") or 0),
            r.get("method", ""),
            r.get("model", ""),
        ),
    )[:limit]
    body = []
    for row in ordered:
        model = row.get("model", "")
        body.append(
            f"""
            <tr>
              <td>Luke {esc(row.get("chapter"))}</td>
              <td>{esc(row.get("method"))}</td>
              <td><span class="dot" style="background:{model_color(model)}"></span>{esc(model)}</td>
              <td>{pct(row.get("combined_mean"))}</td>
              <td>{pct(row.get("mcq_accuracy"))}</td>
              <td>{pct(row.get("open_llm_mean"))}</td>
              <td>{esc(row.get("item_count"))}</td>
            </tr>
            """
        )
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Chapter</th><th>Method</th><th>Model</th><th>Combined</th>"
        "<th>MCQ</th><th>Open</th><th>Items</th>"
        "</tr></thead><tbody>"
        + "\n".join(body)
        + "</tbody></table></div>"
    )


def model_list(rows: list[dict], item_rows: list[dict]) -> list[str]:
    models = [row.get("model", "") for row in rows if row.get("model")]
    if models:
        return models
    output = []
    for row in item_rows:
        for key in row:
            if key.endswith("_score"):
                model = key[: -len("_score")]
                if model not in output:
                    output.append(model)
    return output


def filter_rows_by_methods(rows: list[dict], methods: list[str]) -> list[dict]:
    if not methods:
        return rows
    allowed = set(methods)
    return [row for row in rows if row.get("method") in allowed]


def build_html(
    *,
    summary_by_model: list[dict],
    summary_by_chapter_method_model: list[dict],
    item_comparison: list[dict],
    title: str,
    disagreement_limit: int,
) -> str:
    models = model_list(summary_by_model, item_comparison)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #687386;
      --line: #d9e1ec;
      --track: #e8eef6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1480px, calc(100% - 48px));
      margin: 0 auto;
      padding: 36px 0 56px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; letter-spacing: 0; }}
    h2.section-title {{ margin: 34px 0 14px; font-size: 22px; }}
    .subtle {{ color: var(--muted); margin: 0 0 24px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .model-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-top: 8px solid var(--accent);
      border-radius: 8px;
      padding: 18px;
    }}
    .model-card-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      color: var(--muted);
    }}
    .model-card h2 {{ margin: 0; color: var(--ink); font-size: 22px; }}
    .big-score {{ font-size: 46px; line-height: 1; font-weight: 850; margin: 18px 0; }}
    .metric-row {{
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 12px;
      align-items: center;
      margin-top: 10px;
      color: var(--muted);
    }}
    .metric-bar {{
      display: inline-block;
      height: 12px;
      background: var(--track);
      border-radius: 999px;
      overflow: hidden;
      vertical-align: middle;
      margin-right: 8px;
    }}
    .metric-bar span {{
      display: block;
      height: 100%;
      background: #2563eb;
      border-radius: 999px;
    }}
    .chapter-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
    }}
    .chapter-group {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .chapter-title {{
      font-weight: 800;
      margin-bottom: 10px;
    }}
    .chapter-title span {{
      color: var(--muted);
      font-weight: 650;
      margin-left: 8px;
    }}
    .chapter-bar {{
      display: grid;
      grid-template-columns: 74px 1fr 54px;
      align-items: center;
      gap: 8px;
      margin: 7px 0;
      font-size: 13px;
    }}
    .bar-label {{ color: var(--muted); }}
    .bar-track {{
      height: 12px;
      border-radius: 999px;
      background: var(--track);
      overflow: hidden;
    }}
    .bar-track.empty {{
      background: repeating-linear-gradient(
        135deg,
        #eef2f7,
        #eef2f7 6px,
        #dde5ef 6px,
        #dde5ef 12px
      );
    }}
    .bar-track i {{
      display: block;
      height: 100%;
      border-radius: 999px;
    }}
    .table-wrap {{
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      min-width: 920px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f1f5f9;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: #475569;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .question-cell {{ min-width: 240px; }}
    .answer-cell {{ min-width: 220px; max-width: 360px; }}
    .dot {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      margin-right: 7px;
    }}
    .muted {{ color: var(--muted); }}
  </style>
</head>
<body>
<main>
  <h1>{esc(title)}</h1>
  <p class="subtle">Generated from answer-model comparison CSVs. Scores are shown as percentages; open-answer scores use the LLM judge score.</p>

  <h2 class="section-title">Overall</h2>
  <div class="cards">{overall_cards(summary_by_model)}</div>

  <h2 class="section-title">Combined Score By Chapter And Method</h2>
  <div class="chapter-grid">{grouped_chapter_chart(summary_by_chapter_method_model, "combined_mean")}</div>

  <h2 class="section-title">Open Score By Chapter And Method</h2>
  <div class="chapter-grid">{grouped_chapter_chart(summary_by_chapter_method_model, "open_llm_mean")}</div>

  <h2 class="section-title">MCQ Score By Chapter And Method</h2>
  <div class="chapter-grid">{grouped_chapter_chart(summary_by_chapter_method_model, "mcq_accuracy")}</div>

  <h2 class="section-title">Run Summary</h2>
  {method_summary_table(summary_by_chapter_method_model)}

  <h2 class="section-title">Largest Disagreements</h2>
  {disagreement_table(item_comparison, models, disagreement_limit)}
</main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize compare_answer_models.py outputs as HTML."
    )
    parser.add_argument(
        "--comparison-dir",
        type=Path,
        default=Path("evaluation/outputs/model_comparison"),
        help="Directory containing summary_by_model.csv and item_comparison.csv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output HTML path. Default: <comparison-dir>/model_comparison.html.",
    )
    parser.add_argument("--title", default="Answer Model Comparison")
    parser.add_argument("--disagreement-limit", type=int, default=50)
    parser.add_argument(
        "--methods",
        nargs="+",
        default=[],
        help="Only include these methods in the HTML, e.g. llm_prompt_high nllb-200-1.3B.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or args.comparison_dir / "model_comparison.html"
    summary_by_model = read_csv(args.comparison_dir / "summary_by_model.csv")
    summary_by_chapter_method_model = read_csv(
        args.comparison_dir / "summary_by_chapter_method_model.csv"
    )
    item_comparison = read_csv(args.comparison_dir / "item_comparison.csv")
    if not summary_by_model or not summary_by_chapter_method_model:
        print(
            "Missing comparison CSVs. Run evaluation/scripts/analysis/compare_answer_models.py first."
        )
        return 1
    summary_by_chapter_method_model = filter_rows_by_methods(
        summary_by_chapter_method_model,
        args.methods,
    )
    item_comparison = filter_rows_by_methods(item_comparison, args.methods)
    html_text = build_html(
        summary_by_model=summary_by_model,
        summary_by_chapter_method_model=summary_by_chapter_method_model,
        item_comparison=item_comparison,
        title=args.title,
        disagreement_limit=args.disagreement_limit,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    print(f"wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
