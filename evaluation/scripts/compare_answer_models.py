#!/usr/bin/env python3
"""Compare answer-model results across Luke chapters.

The script reads existing `scores_target_llama.json` files and produces:
- a model summary CSV,
- a chapter/method summary CSV,
- an item-level comparison CSV,
- and a compact Markdown report.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

from _common import load_json, numeric


DEFAULT_MODELS = ("llama 1b", "1.5b", "1.7b")
DEFAULT_CHAPTERS = tuple(range(1, 9))
SCORE_FILE = "scores_target_llama.json"


def item_score(item: dict) -> float | None:
    q_type = str(item.get("q_type") or "").lower()
    if q_type == "mcq":
        return 1.0 if item.get("direct_correct") is True else 0.0
    score = numeric(item.get("llm_score"))
    if score is not None:
        return score
    return numeric(item.get("embedding_similarity"))


def score_path(root: Path, chapter: int, model: str, method: str) -> Path:
    return root / f"luke{chapter}" / model / method / SCORE_FILE


def available_methods(root: Path, chapters: list[int], models: list[str]) -> list[str]:
    method_sets = []
    for chapter in chapters:
        for model in models:
            model_dir = root / f"luke{chapter}" / model
            if not model_dir.exists():
                method_sets.append(set())
                continue
            methods = {
                path.name
                for path in model_dir.iterdir()
                if path.is_dir() and (path / SCORE_FILE).exists()
            }
            method_sets.append(methods)
    if not method_sets:
        return []
    common = set.intersection(*method_sets)
    return sorted(common)


def read_result(root: Path, chapter: int, model: str, method: str) -> dict | None:
    path = score_path(root, chapter, model, method)
    if not path.exists():
        return None
    data = load_json(path)
    return {
        "path": path,
        "summary": data.get("summary") or {},
        "items": data.get("items") or [],
    }


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def summarize_rows(rows: list[dict], group_fields: list[str]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)

    output = []
    for key, group in sorted(groups.items()):
        mcq_scores = [
            row["score"]
            for row in group
            if row["q_type"] == "mcq" and row["score"] is not None
        ]
        open_scores = [
            row["score"]
            for row in group
            if row["q_type"] == "open" and row["score"] is not None
        ]
        all_scores = [row["score"] for row in group if row["score"] is not None]
        out = {field: value for field, value in zip(group_fields, key)}
        out.update(
            {
                "item_count": len(group),
                "scored_count": len(all_scores),
                "combined_mean": mean(all_scores),
                "mcq_count": len(mcq_scores),
                "mcq_accuracy": mean(mcq_scores),
                "open_count": len(open_scores),
                "open_llm_mean": mean(open_scores),
            }
        )
        output.append(out)
    return output


def collect_rows(
    *,
    root: Path,
    chapters: list[int],
    models: list[str],
    methods: list[str],
) -> tuple[list[dict], list[dict]]:
    summary_rows = []
    item_rows = []
    for chapter in chapters:
        for model in models:
            for method in methods:
                result = read_result(root, chapter, model, method)
                if result is None:
                    summary_rows.append(
                        {
                            "chapter": chapter,
                            "model": model,
                            "method": method,
                            "status": "missing",
                        }
                    )
                    continue
                summary = result["summary"]
                summary_rows.append(
                    {
                        "chapter": chapter,
                        "model": model,
                        "method": method,
                        "status": "ok",
                        "total": summary.get("total"),
                        "mcq_count": summary.get("mcq_count"),
                        "mcq_correct": summary.get("mcq_correct"),
                        "mcq_accuracy": (
                            numeric(summary.get("mcq_correct"))
                            / numeric(summary.get("mcq_count"))
                            if numeric(summary.get("mcq_count"))
                            else None
                        ),
                        "open_count": summary.get("open_count"),
                        "open_llm_score_mean": numeric(summary.get("open_llm_score_mean")),
                        "open_embedding_mean": numeric(summary.get("open_embedding_mean")),
                        "answer_confidence_mean": numeric(summary.get("answer_confidence_mean")),
                        "insufficient_information_rate": numeric(summary.get("insufficient_information_rate")),
                        "evidence_supported_rate": numeric(summary.get("evidence_supported_rate")),
                    }
                )
                for item in result["items"]:
                    score = item_score(item)
                    item_rows.append(
                        {
                            "chapter": chapter,
                            "model": model,
                            "method": method,
                            "item_index": item.get("item_index"),
                            "id": item.get("id") or item.get("passage_id"),
                            "passage_reference": item.get("passage_reference"),
                            "q_type": item.get("q_type"),
                            "question": item.get("question"),
                            "standard_answer": item.get("standard_answer"),
                            "generated_answer": item.get("generated_answer"),
                            "generated_answer_english": item.get("generated_answer_english"),
                            "selected_choice": item.get("selected_choice"),
                            "correct_choice": item.get("correct_choice"),
                            "direct_correct": item.get("direct_correct"),
                            "llm_score": numeric(item.get("llm_score")),
                            "embedding_similarity": numeric(item.get("embedding_similarity")),
                            "score": score,
                        }
                    )
    return summary_rows, item_rows


def pivot_item_rows(item_rows: list[dict], models: list[str]) -> list[dict]:
    grouped: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for row in item_rows:
        key = (
            row["chapter"],
            row["method"],
            row["item_index"],
            row["id"],
            row["q_type"],
        )
        grouped[key][row["model"]] = row

    output = []
    for key, model_rows in sorted(grouped.items()):
        chapter, method, item_index, row_id, q_type = key
        base = next(iter(model_rows.values()))
        scores = {
            model: model_rows.get(model, {}).get("score")
            for model in models
        }
        present_scores = [value for value in scores.values() if value is not None]
        score_range = max(present_scores) - min(present_scores) if present_scores else None
        row = {
            "chapter": chapter,
            "method": method,
            "item_index": item_index,
            "id": row_id,
            "passage_reference": base.get("passage_reference"),
            "q_type": q_type,
            "question": base.get("question"),
            "standard_answer": base.get("standard_answer"),
            "score_range": score_range,
            "models_disagree": bool(score_range and score_range > 0),
        }
        for model in models:
            model_row = model_rows.get(model, {})
            row[f"{model}_score"] = model_row.get("score")
            row[f"{model}_answer"] = model_row.get("generated_answer")
            row[f"{model}_choice"] = model_row.get("selected_choice")
        output.append(row)
    return output


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        seen = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        fieldnames = seen
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict], columns: list[str], limit: int | None = None) -> str:
    selected = rows[:limit] if limit else rows
    if not selected:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        cells = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, float):
                value = f"{value:.4f}"
            cells.append(str(value if value is not None else ""))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_markdown_report(
    path: Path,
    *,
    models: list[str],
    chapters: list[int],
    methods: list[str],
    model_summary: list[dict],
    chapter_method_summary: list[dict],
    item_pivot: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    disagreements = [row for row in item_pivot if row.get("models_disagree")]
    top_disagreements = sorted(
        disagreements,
        key=lambda row: (row.get("score_range") or 0),
        reverse=True,
    )[:30]
    content = [
        "# Answer Model Comparison",
        "",
        f"Models: {', '.join(models)}",
        f"Chapters: {', '.join(str(chapter) for chapter in chapters)}",
        f"Methods: {', '.join(methods)}",
        "",
        "## Overall By Model",
        "",
        markdown_table(
            model_summary,
            ["model", "item_count", "combined_mean", "mcq_accuracy", "open_llm_mean"],
        ),
        "",
        "## By Chapter And Method",
        "",
        markdown_table(
            chapter_method_summary,
            [
                "chapter",
                "method",
                "model",
                "item_count",
                "combined_mean",
                "mcq_accuracy",
                "open_llm_mean",
            ],
            limit=80,
        ),
        "",
        "## Largest Item-Level Disagreements",
        "",
        markdown_table(
            top_disagreements,
            [
                "chapter",
                "method",
                "item_index",
                "q_type",
                "passage_reference",
                "score_range",
                *[f"{model}_score" for model in models],
            ],
        ),
        "",
    ]
    path.write_text("\n".join(content), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare 1b, 1.5b, and 1.7b answer-model scores for Luke 1-8."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--chapters", type=int, nargs="+", default=list(DEFAULT_CHAPTERS))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument(
        "--methods",
        nargs="+",
        help=(
            "Methods to compare. Default: intersection of methods with scores for "
            "all selected chapters/models."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("evaluation/outputs/model_comparison"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chapters = list(args.chapters)
    models = list(args.models)
    methods = list(args.methods or available_methods(args.root, chapters, models))
    if not methods:
        print("No common scored methods found. Pass --methods explicitly if needed.")
        return 1

    summary_rows, item_rows = collect_rows(
        root=args.root,
        chapters=chapters,
        models=models,
        methods=methods,
    )
    ok_item_rows = [row for row in item_rows if row.get("score") is not None]
    model_summary = summarize_rows(ok_item_rows, ["model"])
    chapter_method_summary = summarize_rows(ok_item_rows, ["chapter", "method", "model"])
    item_pivot = pivot_item_rows(item_rows, models)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "summary_by_run.csv", summary_rows)
    write_csv(args.out_dir / "summary_by_model.csv", model_summary)
    write_csv(args.out_dir / "summary_by_chapter_method_model.csv", chapter_method_summary)
    write_csv(args.out_dir / "item_comparison.csv", item_pivot)
    write_markdown_report(
        args.out_dir / "model_comparison.md",
        models=models,
        chapters=chapters,
        methods=methods,
        model_summary=model_summary,
        chapter_method_summary=chapter_method_summary,
        item_pivot=item_pivot,
    )
    print(f"methods: {', '.join(methods)}")
    print(f"wrote: {args.out_dir / 'model_comparison.md'}")
    print(f"wrote: {args.out_dir / 'summary_by_model.csv'}")
    print(f"wrote: {args.out_dir / 'item_comparison.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
