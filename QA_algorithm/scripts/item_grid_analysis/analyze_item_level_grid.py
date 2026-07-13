#!/usr/bin/env python3
"""Analyze translation-quality signals from reports/item_level_grid.csv."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import average_ranks_desc


_REPO = Path(__file__).resolve().parents[3]          # repo root (script now in QA_algorithm/scripts)
DEFAULT_INPUT = _REPO / "QA_algorithm" / "outputs" / "reports" / "item_level_grid_analysis" / "item_level_grid.csv"
DEFAULT_OUT_DIR = _REPO / "QA_algorithm" / "outputs" / "reports" / "item_level_grid_analysis"


def read_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            row["score_value"] = float(row["score"]) if row.get("score") not in (None, "") else None
            row["item_uid"] = f"{row['chapter']}:item{row['item_index']}"
            rows.append(row)
    return rows


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def grouped_mean(rows: list[dict], keys: list[str]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if row["score_value"] is not None:
            grouped[tuple(row[key] for key in keys)].append(row)
    out = []
    for key, group in sorted(grouped.items()):
        scores = [row["score_value"] for row in group if row["score_value"] is not None]
        result = {field: value for field, value in zip(keys, key)}
        result.update(
            {
                "row_count": len(group),
                "mean_score": mean(scores),
                "open_mean": mean([row["score_value"] for row in group if row["q_type"] == "open"]),
                "mcq_mean": mean([row["score_value"] for row in group if row["q_type"] == "mcq"]),
                "open_count": sum(1 for row in group if row["q_type"] == "open"),
                "mcq_count": sum(1 for row in group if row["q_type"] == "mcq"),
            }
        )
        out.append(result)
    return out


def complete_item_uids(rows: list[dict], methods: list[str], models: list[str]) -> set[str]:
    required = {(method, model) for method in methods for model in models}
    present: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        if row["score_value"] is not None:
            present[row["item_uid"]].add((row["method"], row["model"]))
    return {item_uid for item_uid, cells in present.items() if required.issubset(cells)}


def missing_cells(rows: list[dict], methods: list[str], models: list[str]) -> list[dict]:
    by_item: dict[str, dict] = {}
    present: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        by_item[row["item_uid"]] = row
        present[row["item_uid"]].add((row["method"], row["model"]))
    missing = []
    for item_uid, meta in sorted(by_item.items()):
        for method in methods:
            for model in models:
                if (method, model) not in present[item_uid]:
                    missing.append(
                        {
                            "chapter": meta["chapter"],
                            "item_id": meta["item_id"],
                            "item_index": meta["item_index"],
                            "q_type": meta["q_type"],
                            "reference": meta["reference"],
                            "method": method,
                            "model": model,
                        }
                    )
    return missing


def rank_order(values: dict[str, float]) -> str:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    groups = []
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and math.isclose(ordered[end][1], ordered[index][1]):
            end += 1
        groups.append("=".join(sorted(method for method, _ in ordered[index:end])))
        index = end
    return " > ".join(groups)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(x * x for x in dx)) * math.sqrt(sum(y * y for y in dy))
    if not denom:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denom


def spearman(a: dict[str, float], b: dict[str, float]) -> float | None:
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return None
    ra = average_ranks_desc({key: a[key] for key in common})
    rb = average_ranks_desc({key: b[key] for key in common})
    return pearson([ra[key] for key in common], [rb[key] for key in common])


def ranking_analysis(rows: list[dict], methods: list[str], models: list[str]) -> tuple[list[dict], list[dict]]:
    means = grouped_mean(rows, ["model", "method"])
    scores_by_model: dict[str, dict[str, float]] = defaultdict(dict)
    for row in means:
        if row["mean_score"] is not None:
            scores_by_model[row["model"]][row["method"]] = row["mean_score"]

    ranking_rows = []
    for model in models:
        scores = scores_by_model.get(model, {})
        ranking_rows.append(
            {
                "model": model,
                "rank_order": rank_order(scores),
                **{f"mean_{method}": scores.get(method) for method in methods},
            }
        )

    agreement_rows = []
    for left, right in combinations(models, 2):
        left_scores = scores_by_model.get(left, {})
        right_scores = scores_by_model.get(right, {})
        common = sorted(set(left_scores) & set(right_scores))
        agreement_rows.append(
            {
                "model_a": left,
                "model_b": right,
                "method_count": len(common),
                "spearman_rho": spearman(left_scores, right_scores),
                "order_a": rank_order({method: left_scores[method] for method in common}),
                "order_b": rank_order({method: right_scores[method] for method in common}),
            }
        )
    return ranking_rows, agreement_rows


def diagnostic_items(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    item_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["score_value"] is not None:
            item_groups[row["item_uid"]].append(row)

    item_rows = []
    method_sensitivity = []
    model_sensitivity = []
    for item_uid, group in item_groups.items():
        scores = [row["score_value"] for row in group]
        meta = group[0]
        item_rows.append(
            {
                "chapter": meta["chapter"],
                "item_id": meta["item_id"],
                "item_index": meta["item_index"],
                "q_type": meta["q_type"],
                "reference": meta["reference"],
                "question": meta["question"],
                "standard_answer": meta["standard_answer"],
                "row_count": len(group),
                "mean_score": mean(scores),
                "zero_rate": sum(1 for score in scores if score == 0) / len(scores),
                "perfect_rate": sum(1 for score in scores if score >= 0.999) / len(scores),
            }
        )
        by_method = defaultdict(list)
        by_model = defaultdict(list)
        for row in group:
            by_method[row["method"]].append(row["score_value"])
            by_model[row["model"]].append(row["score_value"])
        method_means = {key: mean(vals) for key, vals in by_method.items()}
        model_means = {key: mean(vals) for key, vals in by_model.items()}
        method_values = [value for value in method_means.values() if value is not None]
        model_values = [value for value in model_means.values() if value is not None]
        method_sensitivity.append(
            {
                "chapter": meta["chapter"],
                "item_id": meta["item_id"],
                "item_index": meta["item_index"],
                "q_type": meta["q_type"],
                "reference": meta["reference"],
                "question": meta["question"],
                "method_score_range": max(method_values) - min(method_values) if method_values else None,
                "method_order": rank_order({k: v for k, v in method_means.items() if v is not None}),
            }
        )
        model_sensitivity.append(
            {
                "chapter": meta["chapter"],
                "item_id": meta["item_id"],
                "item_index": meta["item_index"],
                "q_type": meta["q_type"],
                "reference": meta["reference"],
                "question": meta["question"],
                "model_score_range": max(model_values) - min(model_values) if model_values else None,
                "model_order": rank_order({k: v for k, v in model_means.items() if v is not None}),
            }
        )
    return (
        sorted(item_rows, key=lambda row: (row["mean_score"] or 0, -row["row_count"]))[:25],
        sorted(method_sensitivity, key=lambda row: row["method_score_range"] or 0, reverse=True)[:25],
        sorted(model_sensitivity, key=lambda row: row["model_score_range"] or 0, reverse=True)[:25],
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_table(rows: list[dict], columns: list[str], limit: int | None = None) -> str:
    selected = rows[:limit] if limit is not None else rows
    if not selected:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(fmt(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def write_report(
    path: Path,
    *,
    rows: list[dict],
    methods: list[str],
    models: list[str],
    missing: list[dict],
    balanced_rows: list[dict],
    method_summary: list[dict],
    balanced_method_summary: list[dict],
    chapter_summary: list[dict],
    model_method_summary: list[dict],
    ranking_rows: list[dict],
    agreement_rows: list[dict],
    hardest_items: list[dict],
    method_sensitive_items: list[dict],
    model_sensitive_items: list[dict],
) -> None:
    best_available = max(method_summary, key=lambda row: row["mean_score"] or -math.inf)
    best_balanced = max(balanced_method_summary, key=lambda row: row["mean_score"] or -math.inf)
    min_rho = min(
        (row["spearman_rho"] for row in agreement_rows if row["spearman_rho"] is not None),
        default=None,
    )
    invariant = (
        len({row["rank_order"] for row in ranking_rows if row.get("rank_order")}) == 1
        and all(row["spearman_rho"] == 1.0 for row in agreement_rows if row["spearman_rho"] is not None)
    )

    missing_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in missing:
        missing_counts[(row["chapter"], row["method"], row["model"])] += 1
    missing_summary = [
        {
            "chapter": chapter,
            "method": method,
            "model": model,
            "row_count": count,
        }
        for (chapter, method, model), count in sorted(missing_counts.items())
    ]
    lines = [
        "# Item-Level Translation Quality Analysis",
        "",
        f"Input rows: {len(rows)}",
        f"Methods: {', '.join(methods)}",
        f"Models: {', '.join(models)}",
        f"Unique chapter-items: {len({row['item_uid'] for row in rows})}",
        f"Missing method/model/item cells: {len(missing)}",
        f"Balanced rows used for fair rank tests: {len(balanced_rows)}",
        "",
        "## Main Takeaway",
        "",
        f"- Best method on all available rows: `{best_available['method']}` at {fmt(best_available['mean_score'])}.",
        f"- Best method on the balanced item grid: `{best_balanced['method']}` at {fmt(best_balanced['mean_score'])}.",
        f"- Rank invariance across answer models: {'yes' if invariant else 'no'}; minimum pairwise Spearman rho is {fmt(min_rho)}.",
        "- Because rankings change by answer model, item-level QA score is not a pure translation-quality measure; it includes method × answerer interaction.",
        "",
        "## Method Summary, All Available Rows",
        "",
        markdown_table(
            sorted(method_summary, key=lambda row: row["mean_score"] or -math.inf, reverse=True),
            ["method", "row_count", "mean_score", "open_mean", "mcq_mean", "open_count", "mcq_count"],
        ),
        "",
        "## Method Summary, Balanced Grid",
        "",
        markdown_table(
            sorted(balanced_method_summary, key=lambda row: row["mean_score"] or -math.inf, reverse=True),
            ["method", "row_count", "mean_score", "open_mean", "mcq_mean", "open_count", "mcq_count"],
        ),
        "",
        "## Chapter Summary",
        "",
        markdown_table(
            sorted(chapter_summary, key=lambda row: row["mean_score"] or -math.inf, reverse=True),
            ["chapter", "row_count", "mean_score", "open_mean", "mcq_mean"],
        ),
        "",
        "## Model x Method Means",
        "",
        markdown_table(
            sorted(model_method_summary, key=lambda row: (row["model"], -(row["mean_score"] or -math.inf))),
            ["model", "method", "row_count", "mean_score", "open_mean", "mcq_mean"],
        ),
        "",
        "## Rank Stability Across Answer Models, Balanced Grid",
        "",
        markdown_table(ranking_rows, ["model", "rank_order"]),
        "",
        markdown_table(agreement_rows, ["model_a", "model_b", "method_count", "spearman_rho", "order_a", "order_b"]),
        "",
        "## Hardest Items",
        "",
        markdown_table(hardest_items, ["chapter", "item_index", "q_type", "reference", "mean_score", "zero_rate", "question"], limit=12),
        "",
        "## Most Method-Sensitive Items",
        "",
        markdown_table(method_sensitive_items, ["chapter", "item_index", "q_type", "reference", "method_score_range", "question", "method_order"], limit=12),
        "",
        "## Most Model-Sensitive Items",
        "",
        markdown_table(model_sensitive_items, ["chapter", "item_index", "q_type", "reference", "model_score_range", "question", "model_order"], limit=12),
        "",
        "## Missing Cells",
        "",
        markdown_table(missing_summary, ["chapter", "method", "model", "row_count"], limit=20),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze reports/item_level_grid.csv.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = read_rows(args.input)
    methods = sorted({row["method"] for row in rows})
    models = sorted({row["model"] for row in rows})
    missing = missing_cells(rows, methods, models)
    complete_uids = complete_item_uids(rows, methods, models)
    balanced_rows = [row for row in rows if row["item_uid"] in complete_uids]

    method_summary = grouped_mean(rows, ["method"])
    balanced_method_summary = grouped_mean(balanced_rows, ["method"])
    chapter_summary = grouped_mean(rows, ["chapter"])
    model_method_summary = grouped_mean(rows, ["model", "method"])
    ranking_rows, agreement_rows = ranking_analysis(balanced_rows, methods, models)
    hardest_items, method_sensitive_items, model_sensitive_items = diagnostic_items(rows)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "method_summary.csv", method_summary)
    write_csv(args.out_dir / "balanced_method_summary.csv", balanced_method_summary)
    write_csv(args.out_dir / "chapter_summary.csv", chapter_summary)
    write_csv(args.out_dir / "model_method_summary.csv", model_method_summary)
    write_csv(args.out_dir / "rankings_by_model.csv", ranking_rows)
    write_csv(args.out_dir / "rank_agreement.csv", agreement_rows)
    write_csv(args.out_dir / "missing_cells.csv", missing)
    write_csv(args.out_dir / "hardest_items.csv", hardest_items)
    write_csv(args.out_dir / "method_sensitive_items.csv", method_sensitive_items)
    write_csv(args.out_dir / "model_sensitive_items.csv", model_sensitive_items)

    payload = {
        "input_rows": len(rows),
        "methods": methods,
        "models": models,
        "unique_items": len({row["item_uid"] for row in rows}),
        "missing_cells": len(missing),
        "balanced_rows": len(balanced_rows),
        "method_summary": method_summary,
        "balanced_method_summary": balanced_method_summary,
        "chapter_summary": chapter_summary,
        "rankings_by_model": ranking_rows,
        "rank_agreement": agreement_rows,
    }
    (args.out_dir / "analysis_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(
        args.out_dir / "analysis_report.md",
        rows=rows,
        methods=methods,
        models=models,
        missing=missing,
        balanced_rows=balanced_rows,
        method_summary=method_summary,
        balanced_method_summary=balanced_method_summary,
        chapter_summary=chapter_summary,
        model_method_summary=model_method_summary,
        ranking_rows=ranking_rows,
        agreement_rows=agreement_rows,
        hardest_items=hardest_items,
        method_sensitive_items=method_sensitive_items,
        model_sensitive_items=model_sensitive_items,
    )
    print(f"wrote {args.out_dir / 'analysis_report.md'}")
    print(f"rows: {len(rows)}; balanced rows: {len(balanced_rows)}; missing cells: {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
