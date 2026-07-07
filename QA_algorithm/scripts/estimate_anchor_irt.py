#!/usr/bin/env python3
"""Estimate language-model ability from gold anchor-passage responses.

This implements a small joint MAP estimator for a 1PL/Rasch IRT model:

    P(correct | theta_j, b_i) = sigmoid(theta_j - b_i)

The anchor passage is assumed perfectly translated, so no passage-quality term
is included. Item difficulty priors come from easy/medium/hard labels, and
model abilities use a standard Normal prior.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize


LABEL_TO_PRIOR_MEAN = {"easy": -1.0, "medium": 0.0, "hard": 1.0}
LABEL_TO_PRIOR_STD = {"easy": 0.5, "medium": 0.5, "hard": 0.5}
DEFAULT_MAX_ITERATIONS = 50
DEFAULT_TOLERANCE = 1e-4


class AnchorIrtError(Exception):
    """Raised when anchor IRT inputs are malformed or estimation fails."""


def sigmoid(value: float) -> float:
    """Return a numerically stable logistic sigmoid."""
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def clip_probability(value: float) -> float:
    """Clip a probability away from exactly 0 and 1 for log-likelihood safety."""
    return min(1.0 - 1e-12, max(1e-12, value))


def normalize_label(value: Any) -> str:
    """Normalize a difficulty label to easy, medium, or hard."""
    label = str(value or "").strip().lower()
    aliases = {
        "med": "medium",
        "moderate": "medium",
        "difficult": "hard",
    }
    label = aliases.get(label, label)
    if label not in LABEL_TO_PRIOR_MEAN:
        raise AnchorIrtError(f"Unknown difficulty label: {value!r}")
    return label


def question_difficulty_label(question: dict) -> str:
    """Extract a question difficulty label, accepting the requested diffiel typo."""
    for key in ("diffiel", "difficulty", "difficulty_label", "difficulty_bucket"):
        if key in question and question.get(key) is not None:
            return normalize_label(question.get(key))
    raise AnchorIrtError(
        f"Question {question.get('question_id')!r} has no difficulty label."
    )


def validate_inputs(inputs: dict) -> tuple[dict[str, dict], list[dict], list[str]]:
    """Validate input payload and return indexed questions, responses, and model ids."""
    if not isinstance(inputs, dict):
        raise AnchorIrtError("Inputs must be a dictionary.")
    questions = inputs.get("questions")
    responses = inputs.get("model_responses")
    if not isinstance(questions, list) or not questions:
        raise AnchorIrtError("inputs['questions'] must be a non-empty list.")
    if not isinstance(responses, list) or not responses:
        raise AnchorIrtError("inputs['model_responses'] must be a non-empty list.")

    question_by_id: dict[str, dict] = {}
    for question in questions:
        if not isinstance(question, dict):
            raise AnchorIrtError("Each question must be a dictionary.")
        question_id = str(question.get("question_id") or "").strip()
        if not question_id:
            raise AnchorIrtError("Each question must have question_id.")
        question_difficulty_label(question)
        question_by_id[question_id] = question

    model_ids = []
    seen_models = set()
    for response in responses:
        if not isinstance(response, dict):
            raise AnchorIrtError("Each model response must be a dictionary.")
        model_id = str(response.get("model_id") or "").strip()
        question_id = str(response.get("question_id") or "").strip()
        if not model_id:
            raise AnchorIrtError("Each model response must have model_id.")
        if question_id not in question_by_id:
            raise AnchorIrtError(f"Response references unknown question_id: {question_id}")
        if "is_correct" not in response:
            raise AnchorIrtError("Each model response must include is_correct.")
        if model_id not in seen_models:
            seen_models.add(model_id)
            model_ids.append(model_id)

    return question_by_id, responses, model_ids


def responses_by_item_and_model(
    responses: list[dict],
) -> tuple[dict[str, list[tuple[str, int]]], dict[str, list[tuple[str, int]]]]:
    """Group binary responses by question and by model."""
    by_item: dict[str, list[tuple[str, int]]] = defaultdict(list)
    by_model: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for response in responses:
        model_id = str(response["model_id"])
        question_id = str(response["question_id"])
        correct = 1 if bool(response["is_correct"]) else 0
        by_item[question_id].append((model_id, correct))
        by_model[model_id].append((question_id, correct))
    return by_item, by_model


def item_negative_log_posterior(
    b_value: float,
    observations: list[tuple[str, int]],
    theta: dict[str, float],
    prior_mean: float,
    prior_std: float,
) -> float:
    """Return negative log posterior for one item difficulty."""
    b = float(b_value)
    log_likelihood = 0.0
    for model_id, correct in observations:
        p = clip_probability(sigmoid(theta[model_id] - b))
        log_likelihood += correct * math.log(p) + (1 - correct) * math.log(1.0 - p)
    log_prior = -((b - prior_mean) ** 2) / (2.0 * prior_std**2)
    return -(log_likelihood + log_prior)


def estimate_item_difficulty(
    observations: list[tuple[str, int]],
    theta: dict[str, float],
    prior_mean: float,
    prior_std: float,
) -> float:
    """Estimate one item difficulty MAP value using L-BFGS-B."""
    result = minimize(
        lambda x: item_negative_log_posterior(
            float(x[0]), observations, theta, prior_mean, prior_std
        ),
        x0=np.array([prior_mean], dtype=float),
        method="L-BFGS-B",
    )
    if not result.success:
        raise AnchorIrtError(f"Item difficulty optimization failed: {result.message}")
    return float(result.x[0])


def ability_negative_log_posterior(
    theta_value: float,
    observations: list[tuple[str, int]],
    item_b: dict[str, float],
) -> float:
    """Return negative log posterior for one model ability."""
    theta = float(theta_value)
    log_likelihood = 0.0
    for question_id, correct in observations:
        p = clip_probability(sigmoid(theta - item_b[question_id]))
        log_likelihood += correct * math.log(p) + (1 - correct) * math.log(1.0 - p)
    log_prior = -(theta**2) / 2.0
    return -(log_likelihood + log_prior)


def estimate_model_ability(
    observations: list[tuple[str, int]],
    item_b: dict[str, float],
    start_theta: float,
) -> float:
    """Estimate one model ability MAP value using L-BFGS-B."""
    result = minimize(
        lambda x: ability_negative_log_posterior(float(x[0]), observations, item_b),
        x0=np.array([start_theta], dtype=float),
        method="L-BFGS-B",
    )
    if not result.success:
        raise AnchorIrtError(f"Model ability optimization failed: {result.message}")
    return float(result.x[0])


def ability_standard_error(
    theta: float,
    observations: list[tuple[str, int]],
    item_b: dict[str, float],
) -> float:
    """Compute approximate standard error from Fisher information."""
    fisher = 0.0
    for question_id, _correct in observations:
        p = sigmoid(theta - item_b[question_id])
        fisher += p * (1.0 - p)
    if fisher <= 0:
        return float("inf")
    return 1.0 / math.sqrt(fisher)


def estimate_anchor_irt(
    inputs: dict,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict:
    """Estimate item difficulties and model abilities from anchor responses.

    Args:
        inputs: Dictionary with anchor_passage, questions, and model_responses.
        max_iterations: Maximum alternating MAP iterations.
        tolerance: Convergence threshold for max absolute parameter change.

    Returns:
        Dictionary with model_abilities, item_difficulties, and convergence.
    """
    question_by_id, responses, model_ids = validate_inputs(inputs)
    by_item, by_model = responses_by_item_and_model(responses)

    theta = {model_id: 0.0 for model_id in model_ids}
    item_b = {}
    item_priors = {}
    for question_id, question in question_by_id.items():
        label = question_difficulty_label(question)
        item_priors[question_id] = {
            "label": label,
            "mean": LABEL_TO_PRIOR_MEAN[label],
            "std": LABEL_TO_PRIOR_STD[label],
        }
        item_b[question_id] = LABEL_TO_PRIOR_MEAN[label]

    final_delta = float("inf")
    converged = False
    n_iterations = 0
    for iteration in range(1, max_iterations + 1):
        previous_theta = dict(theta)
        previous_b = dict(item_b)

        for question_id in question_by_id:
            prior = item_priors[question_id]
            item_b[question_id] = estimate_item_difficulty(
                by_item.get(question_id, []),
                theta,
                prior["mean"],
                prior["std"],
            )

        for model_id in model_ids:
            theta[model_id] = estimate_model_ability(
                by_model.get(model_id, []),
                item_b,
                previous_theta.get(model_id, 0.0),
            )

        deltas = [
            abs(theta[model_id] - previous_theta[model_id]) for model_id in model_ids
        ]
        deltas.extend(
            abs(item_b[question_id] - previous_b[question_id])
            for question_id in question_by_id
        )
        final_delta = max(deltas) if deltas else 0.0
        n_iterations = iteration
        if final_delta < tolerance:
            converged = True
            break

    return {
        "model_abilities": {
            model_id: {
                "theta": theta[model_id],
                "se": ability_standard_error(
                    theta[model_id],
                    by_model.get(model_id, []),
                    item_b,
                ),
                "n_items": len(by_model.get(model_id, [])),
            }
            for model_id in model_ids
        },
        "item_difficulties": {
            question_id: {
                "b_prior_mean": item_priors[question_id]["mean"],
                "b_prior_std": item_priors[question_id]["std"],
                "b_posterior": item_b[question_id],
                "label": item_priors[question_id]["label"],
            }
            for question_id in question_by_id
        },
        "convergence": {
            "n_iterations": n_iterations,
            "converged": converged,
            "final_max_delta": final_delta,
        },
    }


def write_json(path: Path, data: dict) -> None:
    """Write a dictionary as pretty JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def synthetic_inputs() -> dict:
    """Build a small synthetic dataset where A is strongest and C is weakest."""
    questions = [
        {"question_id": "easy_1", "question_text": "E1", "correct_answer": "x", "diffiel": "easy"},
        {"question_id": "easy_2", "question_text": "E2", "correct_answer": "x", "diffiel": "easy"},
        {"question_id": "medium_1", "question_text": "M1", "correct_answer": "x", "diffiel": "medium"},
        {"question_id": "medium_2", "question_text": "M2", "correct_answer": "x", "diffiel": "medium"},
        {"question_id": "hard_1", "question_text": "H1", "correct_answer": "x", "diffiel": "hard"},
        {"question_id": "hard_2", "question_text": "H2", "correct_answer": "x", "diffiel": "hard"},
    ]
    patterns = {
        "model_A": [1, 1, 1, 1, 1, 0],
        "model_B": [1, 1, 1, 0, 0, 0],
        "model_C": [1, 0, 0, 0, 0, 0],
    }
    responses = []
    for model_id, correct_values in patterns.items():
        for question, correct in zip(questions, correct_values):
            responses.append(
                {
                    "model_id": model_id,
                    "question_id": question["question_id"],
                    "response": "x" if correct else "wrong",
                    "is_correct": bool(correct),
                }
            )
    return {
        "anchor_passage": "Synthetic anchor passage.",
        "questions": questions,
        "model_responses": responses,
    }


def run_synthetic_test() -> None:
    """Run a minimal synthetic test and assert theta ordering A > B > C."""
    result = estimate_anchor_irt(synthetic_inputs())
    abilities = result["model_abilities"]
    theta_a = abilities["model_A"]["theta"]
    theta_b = abilities["model_B"]["theta"]
    theta_c = abilities["model_C"]["theta"]
    assert theta_a > theta_b > theta_c, (
        "Expected model_A > model_B > model_C, got "
        f"{theta_a:.4f}, {theta_b:.4f}, {theta_c:.4f}"
    )
    print("synthetic test passed")
    print(json.dumps(result["model_abilities"], indent=2))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Estimate model ability theta from anchor-passage IRT responses."
    )
    parser.add_argument("--input-json", type=Path, help="Input JSON payload.")
    parser.add_argument("--output-json", type=Path, help="Output JSON path.")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Run CLI entrypoint."""
    args = parse_args()
    if args.self_test:
        run_synthetic_test()
        return 0
    if not args.input_json or not args.output_json:
        raise SystemExit("--input-json and --output-json are required unless --self-test.")
    inputs = json.loads(args.input_json.read_text(encoding="utf-8"))
    result = estimate_anchor_irt(
        inputs,
        max_iterations=args.max_iterations,
        tolerance=args.tolerance,
    )
    write_json(args.output_json, result)
    print(f"wrote: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
