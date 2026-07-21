#!/usr/bin/env python3
"""Build a Markdown/CSV report for synthetic perturbation experiments."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from _common import extract_items, load_json, numeric


DEFAULT_ROOT = Path("evaluation/outputs")
DEFAULT_SCORE_FILE = "scores_target_llama.json"
DEFAULT_REPORT = Path("evaluation/outputs/reports/synthetic_perturbation_report.md")
DEFAULT_CSV = Path("evaluation/outputs/reports/synthetic_perturbation_report.csv")
RATE_VARIANTS = ("0%", "5%", "10%", "15%", "20%", "30%")
INCONSISTENCY_VARIANTS = (
    "0%",
    "name_5%",
    "style_5%",
    "name_10%",
    "style_10%",
    "name_15%",
    "style_15%",
    "name_20%",
    "style_20%",
)
LOCAL_INCONSISTENCY_VARIANTS = (
    "style_5%",
    "style_10%",
    "style_15%",
    "style_20%",
)
ADDITION_VARIANTS = (
    "0%",
    "neutral_5%",
    "bad_5%",
    "adversarial_5%",
    "neutral_10%",
    "bad_10%",
    "adversarial_10%",
    "neutral_15%",
    "bad_15%",
    "adversarial_15%",
    "neutral_20%",
    "bad_20%",
    "adversarial_20%",
    "neutral_30%",
    "bad_30%",
    "adversarial_30%",
)
EXPERIMENTS = {
    "addition": {
        "variants": ADDITION_VARIANTS,
        "description": "MQM Accuracy > Addition: neutral, bad, or MCQ-adversarial inserted clauses.",
    },
    "omission": {
        "variants": RATE_VARIANTS,
        "description": "MQM Accuracy > Omission: clause-level removals.",
    },
    "mistranslation": {
        "variants": RATE_VARIANTS,
        "description": "MQM Accuracy > Mistranslation: same-role phrase substitutions.",
    },
    "grammar": {
        "variants": RATE_VARIANTS,
        "description": "MQM Fluency > Grammar: rule-based grammar degradation.",
    },
    "inconsistency": {
        "variants": INCONSISTENCY_VARIANTS,
        "description": "MQM Inconsistency: separate name/entity and style/register inconsistency.",
    },
    "local_inconsistency": {
        "variants": LOCAL_INCONSISTENCY_VARIANTS,
        "description": (
            "MQM Inconsistency: question-local style/register inconsistency "
            "inside each QA verse window."
        ),
    },
    "awkward": {
        "variants": RATE_VARIANTS,
        "description": "MQM Style > Awkward: literalized/source-like phrasing replacements.",
    },
}


def safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def fmt(value: Any, digits: int = 3) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value * 100:.1f}%"


def discover_chapters(root: Path) -> list[int]:
    chapters = []
    for path in root.glob("luke*"):
        if not path.is_dir():
            continue
        match = re.fullmatch(r"luke(\d+)", path.name)
        if match:
            chapters.append(int(match.group(1)))
    return sorted(chapters)


def experiment_chapters(
    root: Path, experiment: str, requested: list[int], model_subdir: str = "1.7b"
) -> list[int]:
    chapters = []
    for chapter in requested:
        if experiment_dir(root, chapter, experiment, model_subdir).is_dir():
            chapters.append(chapter)
    return chapters


def experiment_dir(
    root: Path, chapter: int, experiment: str, model_subdir: str = "1.7b"
) -> Path:
    chapter_dir = root / f"luke{chapter}"
    if model_subdir:
        nested = chapter_dir / model_subdir / experiment
        if nested.is_dir():
            return nested
    direct = chapter_dir / experiment
    if direct.is_dir():
        return direct
    return direct


def score_metrics(score_path: Path) -> dict:
    data = load_json(score_path)
    items = extract_items(data)
    summary = data.get("summary", {}) if isinstance(data, dict) else {}
    mcq_items = [item for item in items if item.get("q_type") == "mcq"]
    open_items = [item for item in items if item.get("q_type") != "mcq"]
    open_scores = [
        float(item["llm_score"])
        for item in open_items
        if numeric(item.get("llm_score")) is not None
    ]

    mcq_count = int(summary.get("mcq_count") or len(mcq_items))
    mcq_correct = int(
        summary.get("mcq_correct")
        if summary.get("mcq_correct") is not None
        else sum(1 for item in mcq_items if item.get("direct_correct"))
    )
    open_count = int(summary.get("open_count") or len(open_items))
    open_scored = len(open_scores)
    open_sum = sum(open_scores)
    combined = safe_div(mcq_correct + open_sum, mcq_count + open_scored)

    confidence = numeric(summary.get("answer_confidence_mean"))
    insufficient_rate = numeric(summary.get("insufficient_information_rate"))
    evidence_rate = numeric(summary.get("evidence_supported_rate"))
    generation_errors = int(
        summary.get("generation_errors")
        if summary.get("generation_errors") is not None
        else sum(1 for item in items if item.get("generation_error"))
    )

    return {
        "total": int(summary.get("total") or len(items)),
        "mcq_count": mcq_count,
        "mcq_correct": mcq_correct,
        "mcq_accuracy": safe_div(mcq_correct, mcq_count),
        "open_count": open_count,
        "open_scored": open_scored,
        "open_sum": open_sum,
        "open_llm_score_mean": numeric(summary.get("open_llm_score_mean"))
        if summary.get("open_llm_score_mean") is not None
        else safe_div(open_sum, open_scored),
        "combined_score": combined,
        "answer_confidence_mean": confidence,
        "insufficient_information_rate": insufficient_rate,
        "evidence_supported_rate": evidence_rate,
        "generation_errors": generation_errors,
    }


def find_metadata(path: Path) -> dict:
    candidates = sorted(path.glob("*metadata.json"))
    for candidate in candidates:
        if candidate.name == "decanonicalized_metadata.json":
            continue
        try:
            data = load_json(candidate)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data["_metadata_file"] = str(candidate)
            return data
    return {}


def extract_actual_rate(metadata: dict) -> float | None:
    files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
    # Answering/scoring uses the decanonicalized passage. Prefer its metadata
    # when available; raw protected-token passages can undercount name/entity
    # perturbations because many names are still placeholders there.
    for file_key in ("passage_target_decanonicalized", "passage_target"):
        passage = files.get(file_key) if isinstance(files.get(file_key), dict) else {}
        for key in (
            "actual_rate",
            "actual_affected_rate",
            "actual_replacement_rate",
            "actual_untranslated_rate",
        ):
            value = numeric(passage.get(key))
            if value is not None:
                return value
    for file_key in ("qa_target_decanonicalized", "qa_target"):
        qa = files.get(file_key) if isinstance(files.get(file_key), dict) else {}
        for key in ("actual_rate", "actual_affected_rate"):
            value = numeric(qa.get(key))
            if value is not None:
                return value
    for key in ("actual_rate", "actual_affected_rate"):
        value = numeric(metadata.get(key))
        if value is not None:
            return value
    return None


def collect_variant(
    *,
    root: Path,
    experiment: str,
    variant: str,
    chapters: list[int],
    score_file: str,
    blank: bool,
    model_subdir: str = "1.7b",
) -> dict:
    if blank:
        return {
            "experiment": experiment,
            "variant": variant,
            "status": "TBD",
            "chapters_scored": "",
            "chapter_count": 0,
            "missing_count": len(chapters),
            "actual_rate_mean": None,
            "combined_score": None,
            "mcq_accuracy": None,
            "open_llm_score_mean": None,
            "answer_confidence_mean": None,
            "insufficient_information_rate": None,
            "evidence_supported_rate": None,
            "generation_errors": None,
            "total_items": None,
        }

    rows = []
    missing = []
    actual_rates = []
    for chapter in chapters:
        variant_dir = experiment_dir(root, chapter, experiment, model_subdir) / variant
        path = variant_dir / score_file
        if path.exists():
            metrics = score_metrics(path)
            metrics["chapter"] = chapter
            rows.append(metrics)
            actual_rate = extract_actual_rate(find_metadata(variant_dir))
            if actual_rate is not None:
                actual_rates.append(actual_rate)
        else:
            missing.append(chapter)

    if not rows:
        return {
            "experiment": experiment,
            "variant": variant,
            "status": "missing",
            "chapters_scored": "",
            "chapter_count": 0,
            "missing_count": len(missing),
            "actual_rate_mean": mean(actual_rates) if actual_rates else None,
            "combined_score": None,
            "mcq_accuracy": None,
            "open_llm_score_mean": None,
            "answer_confidence_mean": None,
            "insufficient_information_rate": None,
            "evidence_supported_rate": None,
            "generation_errors": None,
            "total_items": None,
        }

    mcq_count = sum(row["mcq_count"] for row in rows)
    mcq_correct = sum(row["mcq_correct"] for row in rows)
    open_scored = sum(row["open_scored"] for row in rows)
    open_sum = sum(row["open_sum"] for row in rows)
    total_items = sum(row["total"] for row in rows)
    conf_values = [row["answer_confidence_mean"] for row in rows if row["answer_confidence_mean"] is not None]
    insuff_values = [
        row["insufficient_information_rate"]
        for row in rows
        if row["insufficient_information_rate"] is not None
    ]
    evidence_values = [
        row["evidence_supported_rate"]
        for row in rows
        if row["evidence_supported_rate"] is not None
    ]

    status = "complete" if not missing else "partial"
    return {
        "experiment": experiment,
        "variant": variant,
        "status": status,
        "chapters_scored": ",".join(str(row["chapter"]) for row in rows),
        "chapter_count": len(rows),
        "missing_count": len(missing),
        "actual_rate_mean": mean(actual_rates) if actual_rates else None,
        "combined_score": safe_div(mcq_correct + open_sum, mcq_count + open_scored),
        "mcq_accuracy": safe_div(mcq_correct, mcq_count),
        "open_llm_score_mean": safe_div(open_sum, open_scored),
        "answer_confidence_mean": mean(conf_values) if conf_values else None,
        "insufficient_information_rate": mean(insuff_values) if insuff_values else None,
        "evidence_supported_rate": mean(evidence_values) if evidence_values else None,
        "generation_errors": sum(row["generation_errors"] for row in rows),
        "total_items": total_items,
    }


def collect_report(
    root: Path,
    chapters: list[int],
    experiments: list[str],
    score_file: str,
    blank_experiments: set[str],
    model_subdir: str = "1.7b",
) -> tuple[list[dict], dict[str, list[int]]]:
    rows = []
    chapter_map = {}
    for experiment in experiments:
        config = EXPERIMENTS[experiment]
        exp_chapters = experiment_chapters(root, experiment, chapters, model_subdir)
        chapter_map[experiment] = exp_chapters
        for variant in config["variants"]:
            rows.append(
                collect_variant(
                    root=root,
                    experiment=experiment,
                    variant=variant,
                    chapters=exp_chapters,
                    score_file=score_file,
                    blank=experiment in blank_experiments,
                    model_subdir=model_subdir,
                )
            )
    return rows, chapter_map


def markdown_table(rows: list[dict]) -> str:
    headers = [
        "Variant",
        "Status",
        "Ch",
        "Actual",
        "Combined",
        "MCQ",
        "Open",
        "Conf",
        "Insuff",
        "Evidence",
        "Errors",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["variant"],
                    row["status"],
                    row["chapters_scored"],
                    pct(row["actual_rate_mean"]),
                    fmt(row["combined_score"]),
                    pct(row["mcq_accuracy"]),
                    fmt(row["open_llm_score_mean"]),
                    fmt(row["answer_confidence_mean"]),
                    pct(row["insufficient_information_rate"]),
                    pct(row["evidence_supported_rate"]),
                    fmt(row["generation_errors"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def build_analysis(rows: list[dict], blank_experiments: set[str]) -> list[str]:
    bullets = []
    by_experiment: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_experiment[row["experiment"]].append(row)

    for experiment, exp_rows in by_experiment.items():
        scored = [
            row
            for row in exp_rows
            if row["combined_score"] is not None and row["status"] != "TBD"
        ]
        if experiment in blank_experiments:
            bullets.append(f"`{experiment}` is intentionally blank in this report; rerun without blanking it after the run finishes.")
            continue
        if not scored:
            bullets.append(f"`{experiment}` has no scored variants yet.")
            continue
        baseline = next((row for row in scored if row["variant"] == "0%"), None)
        if baseline and baseline["combined_score"] is not None:
            worst = min(scored, key=lambda row: row["combined_score"])
            delta = (worst["combined_score"] or 0.0) - (baseline["combined_score"] or 0.0)
            bullets.append(
                f"`{experiment}` baseline combined score is {fmt(baseline['combined_score'])}; "
                f"lowest scored variant is `{worst['variant']}` at {fmt(worst['combined_score'])} "
                f"({delta:+.3f} vs baseline)."
            )
        else:
            best = max(scored, key=lambda row: row["combined_score"])
            bullets.append(
                f"`{experiment}` has scored variants; best observed combined score is "
                f"`{best['variant']}` at {fmt(best['combined_score'])}."
            )
    return bullets


def write_markdown(
    path: Path,
    *,
    rows: list[dict],
    chapter_map: dict[str, list[int]],
    blank_experiments: set[str],
    score_file: str,
) -> None:
    by_experiment: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_experiment[row["experiment"]].append(row)

    lines = [
        "# Synthetic Perturbation Results Report",
        "",
        f"Score file: `{score_file}`",
        "",
        "This report aggregates whatever scored perturbation outputs currently exist.",
        "Blank experiments are wired into the table and can be filled by rerunning the script after their runs finish.",
        "",
        "## High-Level Notes",
        "",
    ]
    for bullet in build_analysis(rows, blank_experiments):
        lines.append(f"- {bullet}")
    lines.extend(["", "## Experiment Tables", ""])

    for experiment in EXPERIMENTS:
        if experiment not in by_experiment:
            continue
        lines.extend(
            [
                f"### {experiment}",
                "",
                EXPERIMENTS[experiment]["description"],
                "",
                f"Experiment chapters present: `{','.join(str(ch) for ch in chapter_map.get(experiment, [])) or 'none'}`",
                "",
                markdown_table(by_experiment[experiment]),
                "",
            ]
        )

    lines.extend(
        [
            "## Columns",
            "",
            "- `Ch`: chapters with scored results included in that row.",
            "- `Actual`: mean actual perturbation rate from variant metadata, when available.",
            "- `Combined`: weighted score using MCQ correctness plus open-question LLM scores.",
            "- `MCQ`: MCQ direct accuracy.",
            "- `Open`: mean open-question LLM score.",
            "- `Conf`: mean answer-model confidence, if the run used expanded answer format.",
            "- `Insuff`: mean insufficient-information rate.",
            "- `Evidence`: mean evidence-supported rate.",
            "- `Errors`: answer generation errors counted in score files.",
            "",
            "To fill currently blank inconsistency results later, rerun this script without `--blank-experiments inconsistency`.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "experiment",
        "variant",
        "status",
        "chapters_scored",
        "chapter_count",
        "missing_count",
        "actual_rate_mean",
        "combined_score",
        "mcq_accuracy",
        "open_llm_score_mean",
        "answer_confidence_mean",
        "insufficient_information_rate",
        "evidence_supported_rate",
        "generation_errors",
        "total_items",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a report for synthetic translation perturbation results."
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
    parser.add_argument(
        "--model-subdir",
        default="1.7b",
        help=(
            "Answer-model subdirectory under each luke<ch>/ folder "
            "(e.g. '1.7b', '1.5b', 'llama 1b'). Empty string reads the "
            "legacy flat layout with no model subdir."
        ),
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--blank-experiments",
        nargs="*",
        choices=sorted(EXPERIMENTS),
        default=[],
        help="Render these experiments as TBD even if partial scores already exist.",
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
        model_subdir=args.model_subdir,
    )
    write_markdown(
        args.out,
        rows=rows,
        chapter_map=chapter_map,
        blank_experiments=set(args.blank_experiments),
        score_file=args.score_file,
    )
    write_csv(args.csv, rows)
    print(f"wrote {args.out}")
    print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
