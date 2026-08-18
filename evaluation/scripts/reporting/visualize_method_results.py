#!/usr/bin/env python3
"""Build an HTML report comparing translation methods across Luke chapters."""

import argparse
import html
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import extract_items, load_json


METHODS = [
    "google_word_by_word",
    "llm_prompt_low",
    "llm_prompt_medium",
    "llm_prompt_high",
    "helsinki",
    "mBART-50",
    "nllb-200-distilled-600M",
    "nllb-200-1.3B",
]
DEFAULT_CHAPTERS = list(range(2, 9))
DEFAULT_SCORE_FILE = "scores_target_llama.json"


def safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def cell_class(value: float | None) -> str:
    if value is None:
        return "missing"
    if value >= 0.75:
        return "high"
    if value >= 0.5:
        return "mid"
    if value >= 0.25:
        return "low"
    return "very-low"


def score_row(chapter: int, method: str, score_path: Path) -> dict:
    data = load_json(score_path)
    items = extract_items(data)
    summary = data.get("summary", {}) if isinstance(data, dict) else {}

    mcq_items = [item for item in items if item.get("q_type") == "mcq"]
    open_items = [item for item in items if item.get("q_type") != "mcq"]
    open_scores = [
        float(item["llm_score"])
        for item in open_items
        if item.get("llm_score") is not None
    ]
    embed_scores = [
        float(item["embedding_similarity"])
        for item in open_items
        if item.get("embedding_similarity") is not None
    ]

    mcq_count = int(summary.get("mcq_count") or len(mcq_items))
    mcq_correct = int(
        summary.get("mcq_correct")
        if summary.get("mcq_correct") is not None
        else sum(1 for item in mcq_items if item.get("direct_correct"))
    )
    open_count = int(summary.get("open_count") or len(open_items))
    open_mean = summary.get("open_llm_score_mean")
    if open_mean is None:
        open_mean = mean(open_scores) if open_scores else None
    embed_mean = summary.get("open_embedding_mean")
    if embed_mean is None:
        embed_mean = mean(embed_scores) if embed_scores else None

    scored_total = mcq_count + len(open_scores)
    combined = safe_div(mcq_correct + sum(open_scores), scored_total)
    null_mcq = sum(1 for item in mcq_items if item.get("selected_choice") in (None, ""))
    generation_errors = sum(1 for item in items if item.get("generation_error"))

    return {
        "chapter": chapter,
        "method": method,
        "score_file": str(score_path),
        "total": len(items),
        "mcq_count": mcq_count,
        "mcq_correct": mcq_correct,
        "mcq_accuracy": safe_div(mcq_correct, mcq_count),
        "null_mcq": null_mcq,
        "open_count": open_count,
        "open_scored": len(open_scores),
        "open_score_sum": sum(open_scores),
        "open_llm_mean": open_mean,
        "embedding_mean": embed_mean,
        "generation_errors": generation_errors,
        "combined_score": combined,
    }


def aggregate(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["method"]].append(row)

    output = []
    for method, method_rows in grouped.items():
        mcq_count = sum(row["mcq_count"] for row in method_rows)
        mcq_correct = sum(row["mcq_correct"] for row in method_rows)
        open_scored = sum(row["open_scored"] for row in method_rows)
        open_sum = sum(row["open_score_sum"] for row in method_rows)
        scored_total = mcq_count + open_scored
        values = [
            row["combined_score"]
            for row in method_rows
            if row["combined_score"] is not None
        ]
        output.append(
            {
                "method": method,
                "chapters": len(method_rows),
                "total": sum(row["total"] for row in method_rows),
                "combined_score": safe_div(mcq_correct + open_sum, scored_total),
                "chapter_avg_combined": mean(values) if values else None,
                "chapter_std_combined": pstdev(values) if len(values) > 1 else 0.0,
                "open_llm_mean": safe_div(open_sum, open_scored),
                "mcq_accuracy": safe_div(mcq_correct, mcq_count),
                "mcq_count": mcq_count,
                "mcq_correct": mcq_correct,
                "null_mcq": sum(row["null_mcq"] for row in method_rows),
                "generation_errors": sum(row["generation_errors"] for row in method_rows),
            }
        )
    return sorted(output, key=lambda row: (row["combined_score"] is None, -(row["combined_score"] or -1), row["method"]))


def chapter_aggregate(rows: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["chapter"]].append(row)

    output = []
    for chapter, chapter_rows in grouped.items():
        values = [
            row["combined_score"]
            for row in chapter_rows
            if row["combined_score"] is not None
        ]
        output.append(
            {
                "chapter": chapter,
                "methods": len(chapter_rows),
                "combined_mean": mean(values) if values else None,
                "combined_min": min(values) if values else None,
                "combined_max": max(values) if values else None,
            }
        )
    return sorted(output, key=lambda row: row["chapter"])


def find_rows(
    root: Path,
    model_dir: str,
    chapters: list[int],
    methods: list[str],
    score_file: str,
) -> tuple[list[dict], list[str]]:
    rows = []
    missing = []
    for chapter in chapters:
        for method in methods:
            score_path = root / f"luke{chapter}" / model_dir / method / score_file
            if not score_path.exists():
                missing.append(str(score_path))
                continue
            rows.append(score_row(chapter, method, score_path))
    return rows, missing


def analysis_bullets(method_rows: list[dict], chapter_rows: list[dict], missing: list[str]) -> list[str]:
    bullets = []
    complete_methods = [row for row in method_rows if row["combined_score"] is not None]
    if complete_methods:
        best = max(complete_methods, key=lambda row: row["combined_score"] or -math.inf)
        bullets.append(
            f"Best overall method by weighted combined score is "
            f"<strong>{html.escape(best['method'])}</strong> at {fmt(best['combined_score'])}."
        )
        best_open = max(complete_methods, key=lambda row: row["open_llm_mean"] or -math.inf)
        bullets.append(
            f"Best open-question mean is <strong>{html.escape(best_open['method'])}</strong> "
            f"at {fmt(best_open['open_llm_mean'])}."
        )
        best_mcq = max(complete_methods, key=lambda row: row["mcq_accuracy"] or -math.inf)
        bullets.append(
            f"Best MCQ accuracy is <strong>{html.escape(best_mcq['method'])}</strong> "
            f"at {pct(best_mcq['mcq_accuracy'])}."
        )
        most_consistent = min(complete_methods, key=lambda row: row["chapter_std_combined"] or math.inf)
        bullets.append(
            f"Most consistent method by chapter-to-chapter combined-score standard deviation is "
            f"<strong>{html.escape(most_consistent['method'])}</strong> "
            f"({fmt(most_consistent['chapter_std_combined'])})."
        )
    if chapter_rows:
        hardest = min(chapter_rows, key=lambda row: row["combined_mean"] or math.inf)
        easiest = max(chapter_rows, key=lambda row: row["combined_mean"] or -math.inf)
        bullets.append(
            f"Hardest chapter on average is <strong>Luke {hardest['chapter']}</strong> "
            f"({fmt(hardest['combined_mean'])}); easiest is "
            f"<strong>Luke {easiest['chapter']}</strong> ({fmt(easiest['combined_mean'])})."
        )
    error_rows = [row for row in method_rows if row["generation_errors"] or row["null_mcq"]]
    if error_rows:
        worst = max(error_rows, key=lambda row: row["generation_errors"] + row["null_mcq"])
        bullets.append(
            f"Failed/partial answer records are present. The largest count is in "
            f"<strong>{html.escape(worst['method'])}</strong> "
            f"({worst['generation_errors']} generation errors, {worst['null_mcq']} null MCQs)."
        )
    if missing:
        bullets.append(
            f"{len(missing)} expected score file(s) are missing, so the report is partial."
        )
    return bullets


def render_bar(value: float | None) -> str:
    width = max(0, min(100, int(round((value or 0) * 100))))
    return f'<div class="bar"><span style="width:{width}%"></span></div>'


def render_heatmap(
    *,
    by_pair: dict[tuple[int, str], dict],
    chapters: list[int],
    methods: list[str],
    metric: str,
    formatter,
) -> str:
    heat_header = "".join(f"<th>Luke {chapter}</th>" for chapter in chapters)
    heat_rows = []
    for method in methods:
        cells = []
        for chapter in chapters:
            row = by_pair.get((chapter, method))
            value = row.get(metric) if row else None
            cells.append(f'<td class="{cell_class(value)}">{formatter(value)}</td>')
        heat_rows.append(f"<tr><th>{html.escape(method)}</th>{''.join(cells)}</tr>")
    return (
        "<table>"
        f"<thead><tr><th>Method</th>{heat_header}</tr></thead>"
        f"<tbody>{''.join(heat_rows)}</tbody>"
        "</table>"
    )


def render_report(
    rows: list[dict],
    missing: list[str],
    root: Path,
    model_dir: str,
    chapters: list[int],
    methods: list[str],
) -> str:
    method_rows = aggregate(rows)
    chapter_rows = chapter_aggregate(rows)
    by_pair = {(row["chapter"], row["method"]): row for row in rows}
    bullets = analysis_bullets(method_rows, chapter_rows, missing)

    method_table = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['method'])}</td>"
        f"<td>{fmt(row['combined_score'])}{render_bar(row['combined_score'])}</td>"
        f"<td>{fmt(row['open_llm_mean'])}</td>"
        f"<td>{pct(row['mcq_accuracy'])}</td>"
        f"<td>{row['mcq_correct']}/{row['mcq_count']}</td>"
        f"<td>{row['null_mcq']}</td>"
        f"<td>{row['generation_errors']}</td>"
        f"<td>{fmt(row['chapter_std_combined'])}</td>"
        "</tr>"
        for row in method_rows
    )

    chapter_table = "\n".join(
        "<tr>"
        f"<td>Luke {row['chapter']}</td>"
        f"<td>{fmt(row['combined_mean'])}</td>"
        f"<td>{fmt(row['combined_min'])}</td>"
        f"<td>{fmt(row['combined_max'])}</td>"
        f"<td>{row['methods']}</td>"
        "</tr>"
        for row in chapter_rows
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Luke 1-8 Translation Method Results</title>
  <style>
    :root {{
      --ink: #202124;
      --muted: #667085;
      --line: #d9dee7;
      --panel: #f7f8fa;
      --high: #2e7d32;
      --mid: #8a6d1f;
      --low: #b45309;
      --very-low: #b42318;
      --accent: #315fbd;
    }}
    body {{
      margin: 0;
      color: var(--ink);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #fff;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    h1, h2 {{
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    h1 {{ font-size: 28px; }}
    h2 {{ margin-top: 28px; font-size: 18px; }}
    .subtle {{ color: var(--muted); margin-bottom: 22px; }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px 16px;
      margin: 16px 0;
    }}
    .analysis li {{ margin: 7px 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0 20px;
      background: #fff;
    }}
    th, td {{
      border: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #eef1f5; font-weight: 650; }}
    .bar {{
      height: 6px;
      background: #e6eaf0;
      border-radius: 999px;
      margin-top: 5px;
      overflow: hidden;
    }}
    .bar span {{
      display: block;
      height: 100%;
      background: var(--accent);
    }}
    .high {{ background: #dff0df; color: var(--high); font-weight: 650; }}
    .mid {{ background: #fff3cd; color: var(--mid); font-weight: 650; }}
    .low {{ background: #fdebd3; color: var(--low); font-weight: 650; }}
    .very-low {{ background: #f8d7da; color: var(--very-low); font-weight: 650; }}
    .missing {{ background: #f3f4f6; color: var(--muted); }}
    code {{ background: #eef1f5; padding: 1px 4px; border-radius: 4px; }}
    .note {{ color: var(--muted); font-size: 13px; }}
  </style>
</head>
<body>
<main>
  <h1>Luke 1-8 Translation Method Results</h1>

  <section class="panel">
    <h2>High-Level Analysis</h2>
    <ul class="analysis">
      {''.join(f'<li>{bullet}</li>' for bullet in bullets)}
    </ul>
  </section>

  <h2>Method Ranking</h2>
  <table>
    <thead>
      <tr>
        <th>Method</th>
        <th>Combined</th>
        <th>Open LLM Mean</th>
        <th>MCQ Accuracy</th>
        <th>MCQ Correct</th>
        <th>Null MCQ</th>
        <th>Generation Errors</th>
        <th>Chapter Std Dev</th>
      </tr>
    </thead>
    <tbody>
      {method_table}
    </tbody>
  </table>

  <h2>Combined Score Heatmap</h2>
  {render_heatmap(by_pair=by_pair, chapters=chapters, methods=methods, metric="combined_score", formatter=fmt)}

  <h2>MCQ Accuracy Heatmap</h2>
  {render_heatmap(by_pair=by_pair, chapters=chapters, methods=methods, metric="mcq_accuracy", formatter=pct)}

  <h2>Open LLM Score Heatmap</h2>
  {render_heatmap(by_pair=by_pair, chapters=chapters, methods=methods, metric="open_llm_mean", formatter=fmt)}

  <h2>Chapter Difficulty</h2>
  <table>
    <thead>
      <tr><th>Chapter</th><th>Mean Combined</th><th>Min</th><th>Max</th><th>Methods</th></tr>
    </thead>
    <tbody>{chapter_table}</tbody>
  </table>

  <p class="note">
    Interpretation note: because QA text is shared across methods, method differences
    should mainly reflect the translated passage quality plus answer-model behavior.
    MCQ failures with null selected choices are counted as incorrect.
  </p>
</main>
</body>
</html>
"""


def write_json_summary(path: Path, rows: list[dict], missing: list[str]) -> None:
    payload = {
        "rows": rows,
        "methods": aggregate(rows),
        "chapters": chapter_aggregate(rows),
        "missing": missing,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an HTML visualization report for Luke method scores."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--model-dir", default="1.5b")
    parser.add_argument("--chapters", nargs="+", type=int, default=DEFAULT_CHAPTERS)
    parser.add_argument(
        "--methods",
        nargs="+",
        default=METHODS,
        help="Method folders to include. Default: standard translation methods.",
    )
    parser.add_argument("--score-file", default=DEFAULT_SCORE_FILE)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/outputs/luke_2_8_method_report_1.5b.html"),
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=Path("evaluation/outputs/luke_2_8_method_report_1.5b.json"),
    )
    args = parser.parse_args()

    rows, missing = find_rows(
        args.root,
        args.model_dir,
        args.chapters,
        args.methods,
        args.score_file,
    )
    if not rows:
        raise SystemExit(f"No {args.score_file} files found for requested chapters.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_report(
            rows,
            missing,
            args.root,
            args.model_dir,
            args.chapters,
            args.methods,
        ),
        encoding="utf-8",
    )
    write_json_summary(args.json, rows, missing)
    print(f"Wrote HTML report: {args.output}")
    print(f"Wrote JSON summary: {args.json}")
    if missing:
        print(f"Missing score files: {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
