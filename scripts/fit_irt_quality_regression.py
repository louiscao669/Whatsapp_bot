#!/usr/bin/env python3
"""Fit IRT-style quality regressions for QA item scores.

With --quality-predictor, the model is:

    logit(P(success[j, i])) =
        intercept
        + D * a * (ability[j] - difficulty[i])
        + beta_quality * quality[i]

This differs from fit_irt_ptq.py: translation quality is not multiplied by the
IRT probability. It enters as an item-level predictor in the logistic regression
linear predictor.

Without --quality-predictor, the script estimates a latent item quality/PTQ
effect directly from the score matrix while controlling for fixed difficulty:

    logit(P(success[j, i])) =
        intercept
        + D * a * (ability[j] - difficulty[i])
        + item_quality[i]
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from fit_irt_ptq import logit, read_difficulties, read_matrix, sigmoid


EPS = 1e-7


def read_quality_predictor(path: Path, item_ids: list[str]) -> list[float]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if not rows:
        raise ValueError(f"{path} has no rows")
    if "item" not in rows[0]:
        raise ValueError(f"{path} must include an item column")

    quality_column = None
    for candidate in ("quality", "translation_quality", "ptq"):
        if candidate in rows[0]:
            quality_column = candidate
            break
    if quality_column is None:
        raise ValueError(
            f"{path} must include one of these quality columns: quality, "
            "translation_quality, ptq"
        )

    by_item = {row["item"]: float(row[quality_column]) for row in rows}
    missing = [item_id for item_id in item_ids if item_id not in by_item]
    if missing:
        raise ValueError(f"{path} is missing quality values for: {', '.join(missing)}")

    qualities = [by_item[item_id] for item_id in item_ids]
    for item_id, quality in zip(item_ids, qualities):
        if quality < 0.0 or quality > 1.0:
            raise ValueError(f"{path} has quality outside [0, 1] for {item_id}: {quality}")
    return qualities


def standardize(values: list[float]) -> tuple[list[float], float, float]:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = math.sqrt(variance)
    if std < EPS:
        return [0.0 for _ in values], mean, 0.0
    return [(value - mean) / std for value in values], mean, std


def negative_log_likelihood(
    scores: list[list[float]],
    abilities: list[float],
    difficulties: list[float],
    quality_features: list[float],
    intercept: float,
    beta_quality: float,
    discrimination: float,
    d_constant: float,
    ability_l2: float,
    coefficient_l2: float,
) -> float:
    total = 0.0
    scale = discrimination * d_constant

    for participant_index, row in enumerate(scores):
        ability = abilities[participant_index]
        for item_index, observed in enumerate(row):
            eta = (
                intercept
                + scale * (ability - difficulties[item_index])
                + beta_quality * quality_features[item_index]
            )
            probability = min(max(sigmoid(eta), EPS), 1.0 - EPS)
            total -= observed * math.log(probability)
            total -= (1.0 - observed) * math.log(1.0 - probability)

    if ability_l2:
        total += 0.5 * ability_l2 * sum(ability * ability for ability in abilities)
    if coefficient_l2:
        total += 0.5 * coefficient_l2 * (
            intercept * intercept + beta_quality * beta_quality
        )
    return total


def fit_model(
    scores: list[list[float]],
    difficulties: list[float],
    quality_features: list[float],
    discrimination: float,
    d_constant: float,
    epochs: int,
    learning_rate: float,
    ability_l2: float,
    coefficient_l2: float,
) -> tuple[list[float], float, float, list[list[float]], float]:
    participant_count = len(scores)
    item_count = len(scores[0])
    scale = discrimination * d_constant

    row_means = [sum(row) / item_count for row in scores]
    global_mean = min(max(sum(row_means) / participant_count, EPS), 1.0 - EPS)
    abilities = [
        math.log(min(max(mean, EPS), 1.0 - EPS) / (1.0 - min(max(mean, EPS), 1.0 - EPS)))
        / max(scale, EPS)
        for mean in row_means
    ]
    mean_ability = sum(abilities) / participant_count
    abilities = [ability - mean_ability for ability in abilities]

    intercept = math.log(global_mean / (1.0 - global_mean))
    beta_quality = 0.0

    ability_m = [0.0] * participant_count
    ability_v = [0.0] * participant_count
    intercept_m = 0.0
    intercept_v = 0.0
    beta_m = 0.0
    beta_v = 0.0
    beta_1 = 0.9
    beta_2 = 0.999

    for epoch in range(1, epochs + 1):
        grad_abilities = [0.0] * participant_count
        grad_intercept = 0.0
        grad_beta_quality = 0.0

        for participant_index, row in enumerate(scores):
            ability = abilities[participant_index]
            for item_index, observed in enumerate(row):
                eta = (
                    intercept
                    + scale * (ability - difficulties[item_index])
                    + beta_quality * quality_features[item_index]
                )
                probability = sigmoid(eta)
                grad_eta = probability - observed
                grad_abilities[participant_index] += grad_eta * scale
                grad_intercept += grad_eta
                grad_beta_quality += grad_eta * quality_features[item_index]

        if ability_l2:
            for participant_index, ability in enumerate(abilities):
                grad_abilities[participant_index] += ability_l2 * ability

        if coefficient_l2:
            grad_intercept += coefficient_l2 * intercept
            grad_beta_quality += coefficient_l2 * beta_quality

        for participant_index, gradient in enumerate(grad_abilities):
            ability_m[participant_index] = beta_1 * ability_m[participant_index] + (
                1.0 - beta_1
            ) * gradient
            ability_v[participant_index] = beta_2 * ability_v[participant_index] + (
                1.0 - beta_2
            ) * gradient * gradient
            m_hat = ability_m[participant_index] / (1.0 - beta_1**epoch)
            v_hat = ability_v[participant_index] / (1.0 - beta_2**epoch)
            abilities[participant_index] -= learning_rate * m_hat / (
                math.sqrt(v_hat) + EPS
            )

        mean_ability = sum(abilities) / participant_count
        abilities = [ability - mean_ability for ability in abilities]

        intercept_m = beta_1 * intercept_m + (1.0 - beta_1) * grad_intercept
        intercept_v = beta_2 * intercept_v + (1.0 - beta_2) * grad_intercept * grad_intercept
        intercept -= learning_rate * (intercept_m / (1.0 - beta_1**epoch)) / (
            math.sqrt(intercept_v / (1.0 - beta_2**epoch)) + EPS
        )

        beta_m = beta_1 * beta_m + (1.0 - beta_1) * grad_beta_quality
        beta_v = beta_2 * beta_v + (1.0 - beta_2) * grad_beta_quality * grad_beta_quality
        beta_quality -= learning_rate * (beta_m / (1.0 - beta_1**epoch)) / (
            math.sqrt(beta_v / (1.0 - beta_2**epoch)) + EPS
        )

    predictions = [
        [
            sigmoid(
                intercept
                + scale * (abilities[participant_index] - difficulties[item_index])
                + beta_quality * quality_features[item_index]
            )
            for item_index in range(item_count)
        ]
        for participant_index in range(participant_count)
    ]
    loss = negative_log_likelihood(
        scores,
        abilities,
        difficulties,
        quality_features,
        intercept,
        beta_quality,
        discrimination,
        d_constant,
        ability_l2,
        coefficient_l2,
    )
    return abilities, intercept, beta_quality, predictions, loss


def negative_log_likelihood_with_item_ptq(
    scores: list[list[float]],
    abilities: list[float],
    difficulties: list[float],
    item_quality_logits: list[float],
    intercept: float,
    discrimination: float,
    d_constant: float,
    ability_l2: float,
    coefficient_l2: float,
) -> float:
    total = 0.0
    scale = discrimination * d_constant

    for participant_index, row in enumerate(scores):
        ability = abilities[participant_index]
        for item_index, observed in enumerate(row):
            eta = (
                intercept
                + scale * (ability - difficulties[item_index])
                + item_quality_logits[item_index]
            )
            probability = min(max(sigmoid(eta), EPS), 1.0 - EPS)
            total -= observed * math.log(probability)
            total -= (1.0 - observed) * math.log(1.0 - probability)

    if ability_l2:
        total += 0.5 * ability_l2 * sum(ability * ability for ability in abilities)
    if coefficient_l2:
        total += 0.5 * coefficient_l2 * (
            intercept * intercept
            + sum(value * value for value in item_quality_logits)
        )
    return total


def fit_item_ptq_model(
    scores: list[list[float]],
    difficulties: list[float],
    discrimination: float,
    d_constant: float,
    epochs: int,
    learning_rate: float,
    ability_l2: float,
    coefficient_l2: float,
) -> tuple[list[float], float, list[float], list[float], list[list[float]], float]:
    participant_count = len(scores)
    item_count = len(scores[0])
    scale = discrimination * d_constant

    row_means = [sum(row) / item_count for row in scores]
    global_mean = min(max(sum(row_means) / participant_count, EPS), 1.0 - EPS)
    abilities = [
        logit(min(max(mean, EPS), 1.0 - EPS)) / max(scale, EPS)
        for mean in row_means
    ]
    mean_ability = sum(abilities) / participant_count
    abilities = [ability - mean_ability for ability in abilities]

    intercept = logit(global_mean)
    col_means = [
        sum(scores[participant_index][item_index] for participant_index in range(participant_count))
        / participant_count
        for item_index in range(item_count)
    ]
    item_quality_logits = [
        logit(min(max(mean, EPS), 1.0 - EPS)) - intercept + scale * difficulties[item_index]
        for item_index, mean in enumerate(col_means)
    ]
    mean_item_quality = sum(item_quality_logits) / item_count
    item_quality_logits = [value - mean_item_quality for value in item_quality_logits]
    intercept += mean_item_quality

    ability_m = [0.0] * participant_count
    ability_v = [0.0] * participant_count
    item_m = [0.0] * item_count
    item_v = [0.0] * item_count
    intercept_m = 0.0
    intercept_v = 0.0
    beta_1 = 0.9
    beta_2 = 0.999

    for epoch in range(1, epochs + 1):
        grad_abilities = [0.0] * participant_count
        grad_items = [0.0] * item_count
        grad_intercept = 0.0

        for participant_index, row in enumerate(scores):
            ability = abilities[participant_index]
            for item_index, observed in enumerate(row):
                eta = (
                    intercept
                    + scale * (ability - difficulties[item_index])
                    + item_quality_logits[item_index]
                )
                probability = sigmoid(eta)
                grad_eta = probability - observed
                grad_abilities[participant_index] += grad_eta * scale
                grad_items[item_index] += grad_eta
                grad_intercept += grad_eta

        if ability_l2:
            for participant_index, ability in enumerate(abilities):
                grad_abilities[participant_index] += ability_l2 * ability

        if coefficient_l2:
            grad_intercept += coefficient_l2 * intercept
            for item_index, item_quality_logit in enumerate(item_quality_logits):
                grad_items[item_index] += coefficient_l2 * item_quality_logit

        for participant_index, gradient in enumerate(grad_abilities):
            ability_m[participant_index] = beta_1 * ability_m[participant_index] + (
                1.0 - beta_1
            ) * gradient
            ability_v[participant_index] = beta_2 * ability_v[participant_index] + (
                1.0 - beta_2
            ) * gradient * gradient
            m_hat = ability_m[participant_index] / (1.0 - beta_1**epoch)
            v_hat = ability_v[participant_index] / (1.0 - beta_2**epoch)
            abilities[participant_index] -= learning_rate * m_hat / (
                math.sqrt(v_hat) + EPS
            )

        mean_ability = sum(abilities) / participant_count
        abilities = [ability - mean_ability for ability in abilities]

        intercept_m = beta_1 * intercept_m + (1.0 - beta_1) * grad_intercept
        intercept_v = beta_2 * intercept_v + (1.0 - beta_2) * grad_intercept * grad_intercept
        intercept -= learning_rate * (intercept_m / (1.0 - beta_1**epoch)) / (
            math.sqrt(intercept_v / (1.0 - beta_2**epoch)) + EPS
        )

        for item_index, gradient in enumerate(grad_items):
            item_m[item_index] = beta_1 * item_m[item_index] + (1.0 - beta_1) * gradient
            item_v[item_index] = beta_2 * item_v[item_index] + (
                1.0 - beta_2
            ) * gradient * gradient
            m_hat = item_m[item_index] / (1.0 - beta_1**epoch)
            v_hat = item_v[item_index] / (1.0 - beta_2**epoch)
            item_quality_logits[item_index] -= learning_rate * m_hat / (
                math.sqrt(v_hat) + EPS
            )

        mean_item_quality = sum(item_quality_logits) / item_count
        item_quality_logits = [
            item_quality_logit - mean_item_quality
            for item_quality_logit in item_quality_logits
        ]
        intercept += mean_item_quality

    ptqs = [sigmoid(intercept + value) for value in item_quality_logits]
    predictions = [
        [
            sigmoid(
                intercept
                + scale * (abilities[participant_index] - difficulties[item_index])
                + item_quality_logits[item_index]
            )
            for item_index in range(item_count)
        ]
        for participant_index in range(participant_count)
    ]
    loss = negative_log_likelihood_with_item_ptq(
        scores,
        abilities,
        difficulties,
        item_quality_logits,
        intercept,
        discrimination,
        d_constant,
        ability_l2,
        coefficient_l2,
    )
    return abilities, intercept, item_quality_logits, ptqs, predictions, loss


def write_abilities(path: Path, abilities: list[float]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["participant", "ability"])
        for index, ability in enumerate(abilities, start=1):
            writer.writerow([f"p{index}", f"{ability:.6f}"])


def write_item_effects(
    path: Path,
    item_ids: list[str],
    qualities: list[float],
    quality_features: list[float],
    difficulties: list[float],
    beta_quality: float,
) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "item",
                "translation_quality",
                "quality_feature",
                "quality_logit_contribution",
                "difficulty",
            ]
        )
        for item_id, quality, feature, difficulty in zip(
            item_ids, qualities, quality_features, difficulties
        ):
            writer.writerow(
                [
                    item_id,
                    f"{quality:.6f}",
                    f"{feature:.6f}",
                    f"{beta_quality * feature:.6f}",
                    f"{difficulty:.6f}",
                ]
            )


def write_ptqs(
    path: Path,
    item_ids: list[str],
    ptqs: list[float],
    item_quality_logits: list[float],
    difficulties: list[float],
    intercept: float,
    discrimination: float,
    d_constant: float,
) -> None:
    scale = discrimination * d_constant
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "item",
                "ptq",
                "item_quality_logit",
                "difficulty_adjusted_probability",
                "difficulty",
            ]
        )
        for item_id, ptq, item_quality_logit, difficulty in zip(
            item_ids, ptqs, item_quality_logits, difficulties
        ):
            writer.writerow(
                [
                    item_id,
                    f"{ptq:.6f}",
                    f"{item_quality_logit:.6f}",
                    f"{sigmoid(intercept - scale * difficulty + item_quality_logit):.6f}",
                    f"{difficulty:.6f}",
                ]
            )


def write_predictions(path: Path, item_ids: list[str], predictions: list[list[float]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(item_ids)
        for row in predictions:
            writer.writerow([f"{value:.6f}" for value in row])


def write_coefficients(
    path: Path,
    intercept: float,
    beta_quality: float,
    quality_mean: float,
    quality_std: float,
    loss: float,
) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["parameter", "value"])
        writer.writerow(["intercept", f"{intercept:.6f}"])
        writer.writerow(["beta_quality", f"{beta_quality:.6f}"])
        writer.writerow(["quality_mean", f"{quality_mean:.6f}"])
        writer.writerow(["quality_std", f"{quality_std:.6f}"])
        writer.writerow(["loss", f"{loss:.6f}"])


def write_item_ptq_coefficients(
    path: Path,
    intercept: float,
    mean_ptq: float,
    loss: float,
) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["parameter", "value"])
        writer.writerow(["model", "latent_item_ptq"])
        writer.writerow(["intercept", f"{intercept:.6f}"])
        writer.writerow(["mean_ptq", f"{mean_ptq:.6f}"])
        writer.writerow(["loss", f"{loss:.6f}"])


def output_prefix(path: Path) -> Path:
    if path.is_absolute() or path.parent != Path("."):
        return path
    return Path("output") / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scores_csv",
        type=Path,
        help="CSV with participants as rows and QA items as columns.",
    )
    parser.add_argument(
        "--difficulties",
        type=Path,
        required=True,
        help="CSV of fixed item difficulties.",
    )
    parser.add_argument(
        "--quality-predictor",
        type=Path,
        help=(
            "Optional CSV with item and quality/translation_quality/ptq columns. "
            "If omitted, item-level PTQ is estimated from scores and difficulties."
        ),
    )
    parser.add_argument(
        "--out-prefix",
        type=Path,
        default=Path("quality_regression_fit"),
        help=(
            "Output filename prefix. Bare names are written under output/; "
            "explicit directories are respected."
        ),
    )
    parser.add_argument("--discrimination", type=float, default=1.0, help="IRT a parameter.")
    parser.add_argument("--d-constant", type=float, default=1.7, help="IRT D scaling constant.")
    parser.add_argument("--epochs", type=int, default=5000)
    parser.add_argument("--learning-rate", type=float, default=0.02)
    parser.add_argument("--ability-l2", type=float, default=0.02)
    parser.add_argument("--coefficient-l2", type=float, default=0.02)
    parser.add_argument(
        "--no-standardize-quality",
        action="store_true",
        help="Use raw quality values instead of centered/scaled quality features.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_prefix = output_prefix(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    item_ids, scores = read_matrix(args.scores_csv)
    difficulties = read_difficulties(args.difficulties, item_ids)

    if args.quality_predictor is None:
        abilities, intercept, item_quality_logits, ptqs, predictions, loss = (
            fit_item_ptq_model(
                scores=scores,
                difficulties=difficulties,
                discrimination=args.discrimination,
                d_constant=args.d_constant,
                epochs=args.epochs,
                learning_rate=args.learning_rate,
                ability_l2=args.ability_l2,
                coefficient_l2=args.coefficient_l2,
            )
        )

        write_abilities(
            out_prefix.with_name(out_prefix.name + "_abilities.csv"),
            abilities,
        )
        write_ptqs(
            out_prefix.with_name(out_prefix.name + "_ptq.csv"),
            item_ids,
            ptqs,
            item_quality_logits,
            difficulties,
            intercept,
            args.discrimination,
            args.d_constant,
        )
        write_predictions(
            out_prefix.with_name(out_prefix.name + "_predictions.csv"),
            item_ids,
            predictions,
        )
        write_item_ptq_coefficients(
            out_prefix.with_name(out_prefix.name + "_coefficients.csv"),
            intercept,
            mean_ptq=sum(ptqs) / len(ptqs),
            loss=loss,
        )

        print(f"participants={len(scores)}")
        print(f"items={len(item_ids)}")
        print(f"loss={loss:.6f}")
        print(f"mean_ability={sum(abilities) / len(abilities):.6f}")
        print(f"intercept={intercept:.6f}")
        print(f"mean_ptq={sum(ptqs) / len(ptqs):.6f}")
        return

    qualities = read_quality_predictor(args.quality_predictor, item_ids)

    if args.no_standardize_quality:
        quality_features = qualities
        quality_mean = 0.0
        quality_std = 1.0
    else:
        quality_features, quality_mean, quality_std = standardize(qualities)

    abilities, intercept, beta_quality, predictions, loss = fit_model(
        scores=scores,
        difficulties=difficulties,
        quality_features=quality_features,
        discrimination=args.discrimination,
        d_constant=args.d_constant,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        ability_l2=args.ability_l2,
        coefficient_l2=args.coefficient_l2,
    )

    write_abilities(
        out_prefix.with_name(out_prefix.name + "_abilities.csv"),
        abilities,
    )
    write_item_effects(
        out_prefix.with_name(out_prefix.name + "_item_effects.csv"),
        item_ids,
        qualities,
        quality_features,
        difficulties,
        beta_quality,
    )
    write_predictions(
        out_prefix.with_name(out_prefix.name + "_predictions.csv"),
        item_ids,
        predictions,
    )
    write_coefficients(
        out_prefix.with_name(out_prefix.name + "_coefficients.csv"),
        intercept,
        beta_quality,
        quality_mean,
        quality_std,
        loss,
    )

    print(f"participants={len(scores)}")
    print(f"items={len(item_ids)}")
    print(f"loss={loss:.6f}")
    print(f"mean_ability={sum(abilities) / len(abilities):.6f}")
    print(f"intercept={intercept:.6f}")
    print(f"beta_quality={beta_quality:.6f}")
    print(f"quality_mean={quality_mean:.6f}")
    print(f"quality_std={quality_std:.6f}")


if __name__ == "__main__":
    main()
