#!/usr/bin/env python3
"""Calculate passage-balanced model-level CCL for the tier-1 pilot pool.

Operational definition used here::

    CCL_m = mean_passage(mean_condition(mean_item(
        score_m,item,clean - score_m,item,condition
    )))

The five CCL conditions receive equal weight, every passage receives
equal weight, and only the exact one-question-per-window forms selected by
``pilot_import.build_tier1_pool`` are used. Positive CCL means comprehension is
worse under the standardized degraded-condition mixture than under clean text.
Word-by-word is deliberately excluded from CCL; it remains a separate canary.

Uncertainty is a paired passage-cluster bootstrap. The same resampled passages
are used for every model and for the equal-weight model ensemble.

Full CCL calculation::

    python scripts/calculate_model_ccl.py
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from collections import OrderedDict
from pathlib import Path

from pilot_import import build_tier1_pool


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_ROOT = REPO_ROOT / "evaluation"
DEFAULT_OUT_DIR = REPO_ROOT / "QA_algorithm" / "outputs" / "reports" / "ccl"
DEFAULT_MODELS = ("llama321b", "qwen2515b", "qwen317b")
CONDITION_PATHS = OrderedDict([
    ("omission15", "omission/15%"),
    ("omission30", "omission/30%"),
    ("mistranslation15", "mistranslation/15%"),
    ("mistranslation30", "mistranslation/30%"),
    ("grammar30", "grammar/30%"),
    ("wbw", "google_word_by_word"),
])
FULL_CCL_CONDITIONS = (
    "omission15",
    "omission30",
    "mistranslation15",
    "mistranslation30",
    "grammar30",
)
CLEAN_PATH = "omission/0%"
SCORE_FILENAME = "scores_target_llama.json"


class CCLDataError(RuntimeError):
    """The requested CCL cannot be identified from the available score grid."""


def mean(values) -> float:
    values = list(values)
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values) / len(values)


def quantile(sorted_values: list[float], probability: float) -> float:
    """Linearly interpolated quantile without a numpy dependency."""
    if not sorted_values:
        raise ValueError("quantile requires at least one value")
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def item_score(item: dict) -> float | None:
    """Return open judge score or direct MCQ correctness on a common 0--1 scale."""
    item_id = str(item.get("id") or item.get("passage_id") or "")
    q_type = str(item.get("q_type") or "").lower()
    is_open = q_type == "open" or item_id.endswith("-open")
    value = item.get("llm_score") if is_open else item.get("direct_correct")
    if value is None:
        return None
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise CCLDataError(f"score outside [0,1] for {item_id}: {score}")
    return score


def read_score_items(path: Path) -> dict[str, float | None]:
    document = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for item in document.get("items", []):
        item_id = str(item.get("id") or item.get("passage_id") or "").strip()
        if not item_id:
            continue
        if item_id in out:
            raise CCLDataError(f"duplicate item id {item_id} in {path}")
        out[item_id] = item_score(item)
    return out


def selected_pilot_items(eval_root: Path) -> dict[str, set[str]]:
    """Exact 78 tier-1 item forms delivered by the current pilot importer."""
    qa_rows, _window_rows, report = build_tier1_pool(eval_root, 0.75, 2026)
    by_passage: dict[str, set[str]] = {}
    for item in qa_rows:
        by_passage.setdefault(item.passage_id, set()).add(item.id)
    if report["unique"] != sum(map(len, by_passage.values())):
        raise CCLDataError("pilot item identities are not unique")
    return by_passage


def _score_path(
    eval_root: Path,
    passage: str,
    model: str,
    relative_condition: str,
    score_filename: str,
) -> Path:
    return (
        eval_root / "outputs" / "tier1" / passage / model
        / relative_condition / score_filename
    )


def collect_model(
    eval_root: Path,
    model: str,
    conditions: tuple[str, ...],
    selected: dict[str, set[str]],
    score_filename: str = SCORE_FILENAME,
) -> dict:
    """Load a complete paired grid and return passage/condition summaries."""
    errors = []
    passage_condition_loss = {}
    passage_condition_degraded = {}
    passage_clean = {}
    n_pairs = 0

    for passage, wanted_ids in sorted(selected.items()):
        clean_path = _score_path(
            eval_root, passage, model, CLEAN_PATH, score_filename
        )
        if not clean_path.exists():
            errors.append(f"missing clean file: {clean_path}")
            continue
        clean = read_score_items(clean_path)
        missing_clean = sorted(wanted_ids - clean.keys())
        unscored_clean = sorted(i for i in wanted_ids if clean.get(i) is None)
        if missing_clean:
            errors.append(
                f"{model}/{passage}/clean missing {len(missing_clean)} selected items: "
                + ", ".join(missing_clean[:3])
            )
        if unscored_clean:
            errors.append(
                f"{model}/{passage}/clean has {len(unscored_clean)} unscored items: "
                + ", ".join(unscored_clean[:3])
            )
        if missing_clean or unscored_clean:
            continue

        passage_clean[passage] = mean(clean[item_id] for item_id in wanted_ids)
        passage_condition_loss[passage] = {}
        passage_condition_degraded[passage] = {}
        for condition in conditions:
            degraded_path = _score_path(
                eval_root,
                passage,
                model,
                CONDITION_PATHS[condition],
                score_filename,
            )
            if not degraded_path.exists():
                errors.append(f"missing {condition} file: {degraded_path}")
                continue
            degraded = read_score_items(degraded_path)
            missing = sorted(wanted_ids - degraded.keys())
            unscored = sorted(i for i in wanted_ids if degraded.get(i) is None)
            if missing:
                errors.append(
                    f"{model}/{passage}/{condition} missing {len(missing)} selected items: "
                    + ", ".join(missing[:3])
                )
            if unscored:
                errors.append(
                    f"{model}/{passage}/{condition} has {len(unscored)} unscored items: "
                    + ", ".join(unscored[:3])
                )
            if missing or unscored:
                continue
            losses = [clean[item_id] - degraded[item_id] for item_id in wanted_ids]
            passage_condition_loss[passage][condition] = mean(losses)
            passage_condition_degraded[passage][condition] = mean(
                degraded[item_id] for item_id in wanted_ids
            )
            n_pairs += len(wanted_ids)

    if errors:
        shown = "\n  - ".join(errors[:24])
        remainder = len(errors) - min(len(errors), 24)
        suffix = f"\n  ... and {remainder} more" if remainder else ""
        raise CCLDataError(
            "CCL requires a complete paired item x condition grid.\n"
            f"  - {shown}{suffix}\n"
            "Run the missing score cells or explicitly request a different "
            "--conditions estimand."
        )

    passages = sorted(selected)
    for passage in passages:
        observed = set(passage_condition_loss.get(passage, {}))
        if observed != set(conditions):
            raise CCLDataError(
                f"internal incomplete grid for {model}/{passage}: {sorted(observed)}"
            )

    passage_ccl = {
        passage: mean(passage_condition_loss[passage][c] for c in conditions)
        for passage in passages
    }
    condition_contrasts = {
        condition: mean(passage_condition_loss[p][condition] for p in passages)
        for condition in conditions
    }
    ccl = mean(passage_ccl.values())
    clean_accuracy = mean(passage_clean[p] for p in passages)
    degraded_accuracy = mean(
        mean(passage_condition_degraded[p][c] for c in conditions)
        for p in passages
    )
    # Identity check for the probability-difference CCL definition.
    if abs(ccl - (clean_accuracy - degraded_accuracy)) > 1e-12:
        raise AssertionError("CCL aggregation identity failed")

    return {
        "model": model,
        "ccl": ccl,
        "clean_accuracy": clean_accuracy,
        "degraded_accuracy": degraded_accuracy,
        "passage_ccl": passage_ccl,
        "passage_condition_loss": passage_condition_loss,
        "condition_contrasts": condition_contrasts,
        "n_passages": len(passages),
        "n_items": sum(len(ids) for ids in selected.values()),
        "n_item_condition_pairs": n_pairs,
    }


def bootstrap(
    calculations: dict[str, dict],
    conditions: tuple[str, ...],
    iterations: int,
    seed: int,
) -> tuple[dict[str, dict], dict]:
    """Paired passage bootstrap for individual models and their ensemble."""
    if iterations < 2:
        raise ValueError("--bootstrap must be at least 2")
    passage_sets = {tuple(sorted(result["passage_ccl"])) for result in calculations.values()}
    if len(passage_sets) != 1:
        raise CCLDataError("models do not share the same passage set")
    passages = next(iter(passage_sets))
    rng = random.Random(seed)
    samples = {
        model: {"ccl": [], **{condition: [] for condition in conditions}}
        for model in calculations
    }
    ensemble_samples = []

    for _ in range(iterations):
        sampled = [rng.choice(passages) for _ in passages]
        replicate_model_ccl = []
        for model, result in calculations.items():
            value = mean(result["passage_ccl"][p] for p in sampled)
            samples[model]["ccl"].append(value)
            replicate_model_ccl.append(value)
            for condition in conditions:
                samples[model][condition].append(mean(
                    result["passage_condition_loss"][p][condition]
                    for p in sampled
                ))
        ensemble_samples.append(mean(replicate_model_ccl))

    def interval(values: list[float]) -> dict:
        ordered = sorted(values)
        return {
            "se": statistics.stdev(values),
            "ci95_lower": quantile(ordered, 0.025),
            "ci95_upper": quantile(ordered, 0.975),
        }

    uncertainty = {}
    for model, metrics in samples.items():
        uncertainty[model] = {
            "ccl": interval(metrics["ccl"]),
            "condition_contrasts": {
                condition: interval(metrics[condition]) for condition in conditions
            },
        }
    return uncertainty, interval(ensemble_samples)


def build_report(
    eval_root: Path,
    models: tuple[str, ...],
    conditions: tuple[str, ...],
    iterations: int,
    seed: int,
    score_filename: str = SCORE_FILENAME,
) -> dict:
    unknown = sorted(set(conditions) - set(CONDITION_PATHS))
    if unknown:
        raise ValueError(f"unknown conditions: {unknown}")
    if not conditions:
        raise ValueError("at least one degraded condition is required")
    if not models:
        raise ValueError("at least one model is required")

    selected = selected_pilot_items(eval_root)
    calculations = {
        model: collect_model(
            eval_root, model, conditions, selected, score_filename=score_filename
        )
        for model in models
    }
    uncertainty, ensemble_uncertainty = bootstrap(
        calculations, conditions, iterations, seed
    )
    model_results = []
    for model in models:
        result = calculations[model]
        serialized = {
            key: value
            for key, value in result.items()
            if key not in {"passage_ccl", "passage_condition_loss"}
        }
        serialized["ccl_uncertainty"] = uncertainty[model]["ccl"]
        serialized["condition_contrast_uncertainty"] = uncertainty[model][
            "condition_contrasts"
        ]
        model_results.append(serialized)

    ensemble_ccl = mean(result["ccl"] for result in calculations.values())
    return {
        "schema_version": 1,
        "estimand": (
            "equal-passage mean of equal-condition mean selected-item "
            "clean-minus-degraded score"
        ),
        "scale": "probability difference; positive means comprehension loss",
        "is_full_ccl": conditions == FULL_CCL_CONDITIONS,
        "clean_condition": CLEAN_PATH,
        "degraded_conditions": [
            {"key": condition, "path": CONDITION_PATHS[condition],
             "weight": 1 / len(conditions)}
            for condition in conditions
        ],
        "item_pool": "current tier-1 pilot: one selected form per unique window",
        "models": model_results,
        "ensemble": {
            "model": "ensemble_equal_weight",
            "ccl": ensemble_ccl,
            "model_weight": 1 / len(models),
            **ensemble_uncertainty,
        },
        "uncertainty": {
            "method": "paired passage-cluster bootstrap",
            "iterations": iterations,
            "seed": seed,
            "note": (
                "For deterministic model responses, uncertainty generalizes over "
                "passages; it is not model-sampling variance."
            ),
        },
    }


def write_outputs(report: dict, out_dir: Path) -> tuple[Path, Path, Path]:
    """Write JSON, overall CSV, and diagnostic condition-contrast CSV."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "model_level_ccl.json"
    overall_path = out_dir / "model_level_ccl.csv"
    condition_path = out_dir / "model_level_ccl_condition_contrasts.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    overall_fields = [
        "model", "ccl", "se", "ci95_lower", "ci95_upper",
        "clean_accuracy", "degraded_accuracy", "n_passages", "n_items",
        "n_item_condition_pairs", "is_full_ccl",
    ]
    with overall_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=overall_fields)
        writer.writeheader()
        for result in report["models"]:
            interval = result["ccl_uncertainty"]
            writer.writerow({
                "model": result["model"],
                "ccl": result["ccl"],
                **interval,
                "clean_accuracy": result["clean_accuracy"],
                "degraded_accuracy": result["degraded_accuracy"],
                "n_passages": result["n_passages"],
                "n_items": result["n_items"],
                "n_item_condition_pairs": result["n_item_condition_pairs"],
                "is_full_ccl": report["is_full_ccl"],
            })
        writer.writerow({
            "model": report["ensemble"]["model"],
            "ccl": report["ensemble"]["ccl"],
            "se": report["ensemble"]["se"],
            "ci95_lower": report["ensemble"]["ci95_lower"],
            "ci95_upper": report["ensemble"]["ci95_upper"],
            "is_full_ccl": report["is_full_ccl"],
        })

    condition_fields = [
        "model", "condition", "clean_minus_condition", "se",
        "ci95_lower", "ci95_upper",
    ]
    with condition_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=condition_fields)
        writer.writeheader()
        for result in report["models"]:
            for condition, contrast in result["condition_contrasts"].items():
                writer.writerow({
                    "model": result["model"],
                    "condition": condition,
                    "clean_minus_condition": contrast,
                    **result["condition_contrast_uncertainty"][condition],
                })
    return json_path, overall_path, condition_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=Path, default=DEFAULT_EVAL_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=list(CONDITION_PATHS),
        default=list(FULL_CCL_CONDITIONS),
    )
    parser.add_argument("--score-file", default=SCORE_FILENAME)
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    conditions = tuple(dict.fromkeys(args.conditions))
    try:
        report = build_report(
            args.eval_root,
            tuple(dict.fromkeys(args.models)),
            conditions,
            args.bootstrap,
            args.seed,
            score_filename=args.score_file,
        )
    except (CCLDataError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    paths = write_outputs(report, args.out_dir)
    qualifier = "FULL CCL" if report["is_full_ccl"] else "NONSTANDARD CONDITION-SUBSET CCL"
    print(qualifier)
    for result in report["models"]:
        interval = result["ccl_uncertainty"]
        print(
            f"  {result['model']}: CCL={result['ccl']:.4f}, "
            f"SE={interval['se']:.4f}, "
            f"95% CI [{interval['ci95_lower']:.4f}, {interval['ci95_upper']:.4f}]"
        )
    ensemble = report["ensemble"]
    print(
        f"  ensemble_equal_weight: CCL={ensemble['ccl']:.4f}, "
        f"SE={ensemble['se']:.4f}, "
        f"95% CI [{ensemble['ci95_lower']:.4f}, {ensemble['ci95_upper']:.4f}]"
    )
    print("Wrote:")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
