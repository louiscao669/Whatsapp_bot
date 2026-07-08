#!/usr/bin/env python3
"""Summarize score outputs across translation methods."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from _common import extract_items


DEFAULT_OUTPUT_ROOT = Path("evaluation/outputs/decanonicalized")
DEFAULT_SCORE_FILE = "scores_target_llama.json"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def mean(values: Iterable[float]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def pct(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return float(numerator) / float(denominator)


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def label_counts(items: list[dict]) -> dict[str, int]:
    counts = {"correct": 0, "partial": 0, "incorrect": 0, "other": 0}
    for item in items:
        if item.get("q_type") == "mcq":
            continue
        label = str(item.get("llm_label") or "").strip().lower()
        if label in counts and label != "other":
            counts[label] += 1
        elif label:
            counts["other"] += 1
    return counts


def summarize_score_file(score_path: Path, root: Path) -> dict:
    data = load_json(score_path)
    summary = data.get("summary", {}) if isinstance(data, dict) else {}
    items = extract_items(data)
    counts = label_counts(items)

    method = score_path.parent.name
    try:
        method = str(score_path.parent.relative_to(root))
    except ValueError:
        pass

    mcq_count = int(summary.get("mcq_count") or 0)
    mcq_correct = int(summary.get("mcq_correct") or 0)
    open_count = int(summary.get("open_count") or 0)
    open_llm_scores = [
        float(item["llm_score"])
        for item in items
        if item.get("q_type") != "mcq" and item.get("llm_score") is not None
    ]
    open_embedding_scores = [
        float(item["embedding_similarity"])
        for item in items
        if item.get("q_type") != "mcq" and item.get("embedding_similarity") is not None
    ]

    open_llm_mean = summary.get("open_llm_score_mean")
    if open_llm_mean is None:
        open_llm_mean = mean(open_llm_scores)
    open_embedding_mean = summary.get("open_embedding_mean")
    if open_embedding_mean is None:
        open_embedding_mean = mean(open_embedding_scores)

    scored_total = mcq_count + len(open_llm_scores)
    combined_score = (
        (mcq_correct + sum(open_llm_scores)) / scored_total if scored_total else None
    )

    return {
        "method": method,
        "score_file": str(score_path),
        "total": int(summary.get("total") or len(items)),
        "mcq_count": mcq_count,
        "mcq_correct": mcq_correct,
        "mcq_accuracy": pct(mcq_correct, mcq_count),
        "open_count": open_count,
        "open_llm_scored": len(open_llm_scores),
        "open_llm_score_mean": open_llm_mean,
        "open_embedding_scored": len(open_embedding_scores),
        "open_embedding_mean": open_embedding_mean,
        "llm_correct": counts["correct"],
        "llm_partial": counts["partial"],
        "llm_incorrect": counts["incorrect"],
        "llm_other": counts["other"],
        "combined_score": combined_score,
        "answer_confidence_mean": summary.get("answer_confidence_mean"),
        "insufficient_information_rate": summary.get("insufficient_information_rate"),
        "direct_evidence_rate": summary.get("direct_evidence_rate"),
        "evidence_supported_rate": summary.get("evidence_supported_rate"),
        "wrong_high_confidence_count": summary.get("wrong_high_confidence_count"),
        "correct_low_confidence_count": summary.get("correct_low_confidence_count"),
    }


def find_score_files(root: Path, score_file_name: str) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(
        path
        for path in root.rglob(score_file_name)
        if path.is_file() and not any(part.startswith(".") for part in path.parts)
    )


def sort_rows(rows: list[dict], sort_key: str) -> list[dict]:
    def key(row: dict):
        value = row.get(sort_key)
        return (value is None, value if value is not None else -1, row["method"])

    return sorted(rows, key=key, reverse=True)


def print_table(rows: list[dict]) -> None:
    columns = [
        ("method", "method"),
        ("combined_score", "combined"),
        ("open_llm_score_mean", "open_llm"),
        ("open_embedding_mean", "embed"),
        ("mcq_accuracy", "mcq_acc"),
        ("total", "total"),
        ("open_llm_scored", "open_n"),
        ("mcq_count", "mcq_n"),
        ("llm_correct", "correct"),
        ("llm_partial", "partial"),
        ("llm_incorrect", "wrong"),
        ("answer_confidence_mean", "conf"),
        ("insufficient_information_rate", "insuff"),
        ("direct_evidence_rate", "direct_ev"),
        ("wrong_high_confidence_count", "wrong_hi"),
    ]
    table = []
    for row in rows:
        table.append(
            [
                row[key] if key == "method" else fmt(row.get(key))
                for key, _heading in columns
            ]
        )
    widths = [
        max(len(heading), *(len(str(row[index])) for row in table))
        for index, (_key, heading) in enumerate(columns)
    ]
    print("  ".join(heading.ljust(widths[index]) for index, (_key, heading) in enumerate(columns)))
    print("  ".join("-" * width for width in widths))
    for row in table:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize scores_target_llama.json files across method folders."
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Output root or one score JSON file. Default: {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument(
        "--score-file",
        default=DEFAULT_SCORE_FILE,
        help=f"Score filename to find under root. Default: {DEFAULT_SCORE_FILE}",
    )
    parser.add_argument(
        "--sort",
        default="combined_score",
        choices=[
            "combined_score",
            "open_llm_score_mean",
            "open_embedding_mean",
            "mcq_accuracy",
            "method",
        ],
        help="Column to sort by. Default: combined_score",
    )
    parser.add_argument("--csv", type=Path, help="Optional CSV output path.")
    parser.add_argument("--json", type=Path, help="Optional JSON output path.")
    args = parser.parse_args()

    score_files = find_score_files(args.root, args.score_file)
    if not score_files:
        raise SystemExit(f"No {args.score_file} files found under {args.root}")

    root = args.root.parent if args.root.is_file() else args.root
    rows = sort_rows(
        [summarize_score_file(score_file, root) for score_file in score_files],
        args.sort,
    )
    print_table(rows)

    if args.csv:
        write_csv(args.csv, rows)
        print(f"\nWrote CSV: {args.csv}")
    if args.json:
        write_json(args.json, rows)
        print(f"\nWrote JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
