#!/usr/bin/env python3
"""Build a quality x ability x item grid and test method-rank stability."""

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


DEFAULT_CHAPTERS = tuple(range(1, 9))
DEFAULT_MODELS = ("llama 1b", "1.5b", "1.7b")
DEFAULT_METHODS = (
    "google_word_by_word",
    "llm_prompt_high",
    "llm_prompt_low",
    "mBART-50",
    "nllb-200-1.3B",
)
DEFAULT_OUT_DIR = Path("evaluation/outputs/model_comparison/quality_ability_grid")
SCORE_FILE = "scores_target_llama.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def item_id(chapter: int, item: dict) -> str:
    raw_id = item.get("id") or item.get("passage_id") or item.get("item_index")
    return f"luke{chapter}:item{item.get('item_index')}:{raw_id}:{item.get('q_type')}"


def collect_grid(
    *,
    root: Path,
    chapters: list[int],
    models: list[str],
    methods: list[str],
) -> list[dict]:
    rows = []
    for chapter in chapters:
        for method in methods:
            for model in models:
                path = score_path(root, chapter, model, method)
                if not path.exists():
                    continue
                data = load_json(path)
                items = data.get("items") if isinstance(data, dict) else None
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        {
                            "chapter": chapter,
                            "quality_method": method,
                            "ability_model": model,
                            "item_uid": item_id(chapter, item),
                            "item_index": item.get("item_index"),
                            "source_id": item.get("id") or item.get("passage_id"),
                            "passage_reference": item.get("passage_reference"),
                            "q_type": item.get("q_type"),
                            "score": item_score(item),
                            "direct_correct": item.get("direct_correct"),
                            "llm_score": numeric(item.get("llm_score")),
                            "embedding_similarity": numeric(item.get("embedding_similarity")),
                            "answer_confidence": numeric(item.get("answer_confidence")),
                            "insufficient_information": item.get("insufficient_information"),
                            "evidence_quality": item.get("evidence_quality"),
                            "score_file": str(path),
                        }
                    )
    return rows


def complete_item_uids(rows: list[dict], models: list[str], methods: list[str]) -> set[str]:
    required = {(method, model) for method in methods for model in models}
    present_by_item: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        if row.get("score") is None:
            continue
        present_by_item[row["item_uid"]].add(
            (row["quality_method"], row["ability_model"])
        )
    return {
        uid
        for uid, present in present_by_item.items()
        if required.issubset(present)
    }


def summarize_methods(rows: list[dict], item_uids: set[str]) -> list[dict]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    item_counts: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        score = row.get("score")
        if row["item_uid"] not in item_uids or score is None:
            continue
        key = (row["ability_model"], row["quality_method"])
        groups[key].append(float(score))
        item_counts[key].add(row["item_uid"])

    out = []
    for (model, method), scores in sorted(groups.items()):
        out.append(
            {
                "ability_model": model,
                "quality_method": method,
                "item_count": len(item_counts[(model, method)]),
                "mean_score": statistics.fmean(scores) if scores else None,
            }
        )
    return out


def average_ranks_desc(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and math.isclose(ordered[end][1], ordered[index][1]):
            end += 1
        average_rank = (index + 1 + end) / 2
        for key, _ in ordered[index:end]:
            ranks[key] = average_rank
        index = end
    return ranks


def rank_groups_desc(values: dict[str, float]) -> str:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    groups = []
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and math.isclose(ordered[end][1], ordered[index][1]):
            end += 1
        methods = sorted(method for method, _ in ordered[index:end])
        groups.append("=".join(methods))
        index = end
    return " > ".join(groups)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    dx = [value - mean_x for value in xs]
    dy = [value - mean_y for value in ys]
    denom_x = math.sqrt(sum(value * value for value in dx))
    denom_y = math.sqrt(sum(value * value for value in dy))
    if not denom_x or not denom_y:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / (denom_x * denom_y)


def spearman_from_scores(a: dict[str, float], b: dict[str, float]) -> float | None:
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return None
    ranks_a = average_ranks_desc({key: a[key] for key in common})
    ranks_b = average_ranks_desc({key: b[key] for key in common})
    return pearson([ranks_a[key] for key in common], [ranks_b[key] for key in common])


def rank_positions(order: dict[str, float]) -> dict[str, int]:
    return {
        method: index + 1
        for index, (method, _) in enumerate(
            sorted(order.items(), key=lambda item: (-item[1], item[0]))
        )
    }


def pairwise_rank_stats(summary_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    by_model: dict[str, dict[str, float]] = defaultdict(dict)
    for row in summary_rows:
        if row["mean_score"] is not None:
            by_model[row["ability_model"]][row["quality_method"]] = row["mean_score"]

    ranking_rows = []
    for model, scores in sorted(by_model.items()):
        positions = rank_positions(scores)
        ranking_rows.append(
            {
                "ability_model": model,
                "rank_order": rank_groups_desc(scores),
                **{f"rank_{method}": positions.get(method) for method in sorted(scores)},
            }
        )

    pairwise_rows = []
    for left, right in combinations(sorted(by_model), 2):
        left_scores = by_model[left]
        right_scores = by_model[right]
        common = sorted(set(left_scores) & set(right_scores))
        left_pos = rank_positions({method: left_scores[method] for method in common})
        right_pos = rank_positions({method: right_scores[method] for method in common})
        exact = [method for method in common if left_pos[method] == right_pos[method]]
        pairwise_rows.append(
            {
                "ability_model_a": left,
                "ability_model_b": right,
                "method_count": len(common),
                "spearman_rho": spearman_from_scores(left_scores, right_scores),
                "same_rank_count": len(exact),
                "same_rank_fraction": len(exact) / len(common) if common else None,
                "order_a": rank_groups_desc({method: left_scores[method] for method in common}),
                "order_b": rank_groups_desc({method: right_scores[method] for method in common}),
            }
        )
    return ranking_rows, pairwise_rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def write_markdown(
    path: Path,
    *,
    models: list[str],
    methods: list[str],
    full_rows: list[dict],
    complete_uids: set[str],
    summary_rows: list[dict],
    ranking_rows: list[dict],
    pairwise_rows: list[dict],
) -> None:
    min_rho = min(
        (row["spearman_rho"] for row in pairwise_rows if row["spearman_rho"] is not None),
        default=None,
    )
    invariant = bool(
        pairwise_rows
        and all(row["spearman_rho"] == 1.0 for row in pairwise_rows)
        and len({row["rank_order"] for row in ranking_rows}) == 1
    )
    verdict = (
        "The quality ranking is invariant across the selected answerer ability tiers."
        if invariant
        else "The quality ranking is not invariant across the selected answerer ability tiers; the QA proxy is entangled with answerer ability and should be corrected before treating it as pure translation quality."
    )
    complete_cells = len(complete_uids) * len(models) * len(methods)
    scored_cells = sum(1 for row in full_rows if row.get("score") is not None)
    lines = [
        "# Quality x Ability x Item Rank-Stability Check",
        "",
        f"Models: {', '.join(models)}",
        f"Quality methods: {', '.join(methods)}",
        f"Full scored grid cells: {scored_cells}",
        f"Balanced item count: {len(complete_uids)}",
        f"Balanced scored cells: {complete_cells}",
        "",
        f"**Verdict:** {verdict}",
        "",
        f"Minimum pairwise Spearman rho: {fmt(min_rho)}",
        "",
        "## Method Means On Balanced Grid",
        "",
        markdown_table(
            summary_rows,
            ["ability_model", "quality_method", "item_count", "mean_score"],
        ),
        "",
        "## Ranking Within Each Ability Tier",
        "",
        markdown_table(ranking_rows, ["ability_model", "rank_order"]),
        "",
        "## Pairwise Rank Agreement",
        "",
        markdown_table(
            pairwise_rows,
            [
                "ability_model_a",
                "ability_model_b",
                "method_count",
                "spearman_rho",
                "same_rank_count",
                "same_rank_fraction",
                "order_a",
                "order_b",
            ],
        ),
        "",
        "Interpretation: Spearman rho is computed over method rankings within each answer model. A pure translation-quality proxy should preserve the same method ordering across ability tiers; disagreement means the proxy is partly measuring the answerer's interaction with a translation method.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a quality x ability x item grid and test rank stability."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--chapters", type=int, nargs="+", default=list(DEFAULT_CHAPTERS))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--methods", nargs="+", default=list(DEFAULT_METHODS))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = list(args.models)
    methods = list(args.methods)
    rows = collect_grid(
        root=args.root,
        chapters=list(args.chapters),
        models=models,
        methods=methods,
    )
    complete_uids = complete_item_uids(rows, models, methods)
    summary_rows = summarize_methods(rows, complete_uids)
    ranking_rows, pairwise_rows = pairwise_rank_stats(summary_rows)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.out_dir / "quality_ability_item_grid.csv", rows)
    write_csv(
        args.out_dir / "quality_ability_item_grid_balanced.csv",
        [row for row in rows if row["item_uid"] in complete_uids],
    )
    write_csv(args.out_dir / "method_means_by_ability.csv", summary_rows)
    write_csv(args.out_dir / "rankings_by_ability.csv", ranking_rows)
    write_csv(args.out_dir / "pairwise_rank_agreement.csv", pairwise_rows)
    write_markdown(
        args.out_dir / "rank_stability_report.md",
        models=models,
        methods=methods,
        full_rows=rows,
        complete_uids=complete_uids,
        summary_rows=summary_rows,
        ranking_rows=ranking_rows,
        pairwise_rows=pairwise_rows,
    )
    print(f"wrote {args.out_dir / 'rank_stability_report.md'}")
    print(f"balanced items: {len(complete_uids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
