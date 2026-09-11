#!/usr/bin/env python3
"""Fit participant abilities and item PTQ values from response scores.

The model is:

    P(success[j, i]) = PTQ[i] * sigmoid(D * a * (ability[j] - difficulty[i]))

Item difficulties are treated as precomputed inputs. The response CSV can contain
binary 0/1 values or continuous values in [0, 1]; continuous values are fit with
the same fractional Bernoulli cross-entropy objective.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


EPS = 1e-7


def sigmoid(value: float) -> float:
    if value >= 0:
        exp_neg = math.exp(-value)
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(value)
    return exp_pos / (1.0 + exp_pos)


def logit(value: float) -> float:
    value = min(max(value, EPS), 1.0 - EPS)
    return math.log(value / (1.0 - value))


def read_matrix(path: Path) -> tuple[list[str], list[list[float]]]:
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = [[float(cell) for cell in row] for row in reader if row]

    if not header:
        raise ValueError(f"{path} has no header")
    if not rows:
        raise ValueError(f"{path} has no data rows")

    expected_cols = len(header)
    for row_index, row in enumerate(rows, start=2):
        if len(row) != expected_cols:
            raise ValueError(
                f"{path}:{row_index} has {len(row)} columns; expected {expected_cols}"
            )
        for value in row:
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{path}:{row_index} has value outside [0, 1]: {value}")

    return header, rows


def read_difficulties(path: Path | None, item_ids: list[str]) -> list[float]:
    if path is None:
        return [0.0] * len(item_ids)

    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if row]

    if not rows:
        raise ValueError(f"{path} has no difficulty values")

    if len(rows) == 1 and len(rows[0]) == len(item_ids):
        return [float(value) for value in rows[0]]

    header = [cell.strip() for cell in rows[0]]
    if len(header) == len(item_ids) and header == item_ids and len(rows) >= 2:
        return [float(value) for value in rows[1]]

    if {"item", "difficulty"}.issubset(set(header)):
        item_col = header.index("item")
        difficulty_col = header.index("difficulty")
        by_item = {
            row[item_col]: float(row[difficulty_col])
            for row in rows[1:]
            if len(row) > max(item_col, difficulty_col)
        }
        missing = [item_id for item_id in item_ids if item_id not in by_item]
        if missing:
            raise ValueError(f"{path} is missing difficulties for: {', '.join(missing)}")
        return [by_item[item_id] for item_id in item_ids]

    if all(len(row) == 2 for row in rows):
        by_item = {row[0]: float(row[1]) for row in rows}
        missing = [item_id for item_id in item_ids if item_id not in by_item]
        if missing:
            raise ValueError(f"{path} is missing difficulties for: {', '.join(missing)}")
        return [by_item[item_id] for item_id in item_ids]

    raise ValueError(
        f"{path} must be either one row of {len(item_ids)} values, a header row "
        "matching the response CSV plus one value row, item,difficulty columns, "
        "or headerless item,difficulty rows"
    )


def negative_log_likelihood(
    scores: list[list[float]],
    abilities: list[float],
    ptq_logits: list[float],
    difficulties: list[float],
    discrimination: float,
    d_constant: float,
    ability_l2: float,
    ptq_prior: float | None,
    ptq_prior_l2: float,
) -> float:
    total = 0.0
    scale = discrimination * d_constant

    for participant_index, row in enumerate(scores):
        ability = abilities[participant_index]
        for item_index, observed in enumerate(row):
            ptq = sigmoid(ptq_logits[item_index])
            irt = sigmoid(scale * (ability - difficulties[item_index]))
            probability = min(max(ptq * irt, EPS), 1.0 - EPS)
            total -= observed * math.log(probability)
            total -= (1.0 - observed) * math.log(1.0 - probability)

    if ability_l2:
        total += 0.5 * ability_l2 * sum(ability * ability for ability in abilities)

    if ptq_prior is not None and ptq_prior_l2:
        prior_logit = logit(ptq_prior)
        total += 0.5 * ptq_prior_l2 * sum(
            (ptq_logit - prior_logit) ** 2 for ptq_logit in ptq_logits
        )

    return total


def fit_model(
    scores: list[list[float]],
    difficulties: list[float],
    discrimination: float,
    d_constant: float,
    epochs: int,
    learning_rate: float,
    ability_l2: float,
    ptq_prior: float | None,
    ptq_prior_l2: float,
) -> tuple[list[float], list[float], list[list[float]], float]:
    participant_count = len(scores)
    item_count = len(scores[0])
    scale = discrimination * d_constant

    row_means = [sum(row) / item_count for row in scores]
    global_mean = sum(row_means) / participant_count
    abilities = [logit(0.25 + 0.5 * mean) - logit(0.25 + 0.5 * global_mean) for mean in row_means]

    col_means = [
        sum(scores[participant_index][item_index] for participant_index in range(participant_count))
        / participant_count
        for item_index in range(item_count)
    ]
    initial_ptq = [
        min(0.99, max(0.05, mean / max(sigmoid(-scale * difficulties[item_index]), 0.05)))
        for item_index, mean in enumerate(col_means)
    ]
    ptq_logits = [logit(value) for value in initial_ptq]

    ability_m = [0.0] * participant_count
    ability_v = [0.0] * participant_count
    ptq_m = [0.0] * item_count
    ptq_v = [0.0] * item_count
    beta_1 = 0.9
    beta_2 = 0.999

    for epoch in range(1, epochs + 1):
        grad_abilities = [0.0] * participant_count
        grad_ptq_logits = [0.0] * item_count

        for participant_index, row in enumerate(scores):
            ability = abilities[participant_index]
            for item_index, observed in enumerate(row):
                ptq = sigmoid(ptq_logits[item_index])
                irt = sigmoid(scale * (ability - difficulties[item_index]))
                probability = min(max(ptq * irt, EPS), 1.0 - EPS)
                grad_probability = (probability - observed) / (
                    probability * (1.0 - probability)
                )

                grad_abilities[participant_index] += (
                    grad_probability * ptq * irt * (1.0 - irt) * scale
                )
                grad_ptq_logits[item_index] += (
                    grad_probability * irt * ptq * (1.0 - ptq)
                )

        if ability_l2:
            for participant_index, ability in enumerate(abilities):
                grad_abilities[participant_index] += ability_l2 * ability

        if ptq_prior is not None and ptq_prior_l2:
            prior_logit = logit(ptq_prior)
            for item_index, ptq_logit in enumerate(ptq_logits):
                grad_ptq_logits[item_index] += ptq_prior_l2 * (ptq_logit - prior_logit)

        for participant_index, gradient in enumerate(grad_abilities):
            ability_m[participant_index] = beta_1 * ability_m[participant_index] + (1.0 - beta_1) * gradient
            ability_v[participant_index] = beta_2 * ability_v[participant_index] + (1.0 - beta_2) * gradient * gradient
            m_hat = ability_m[participant_index] / (1.0 - beta_1**epoch)
            v_hat = ability_v[participant_index] / (1.0 - beta_2**epoch)
            abilities[participant_index] -= learning_rate * m_hat / (math.sqrt(v_hat) + EPS)

        mean_ability = sum(abilities) / participant_count
        abilities = [ability - mean_ability for ability in abilities]

        for item_index, gradient in enumerate(grad_ptq_logits):
            ptq_m[item_index] = beta_1 * ptq_m[item_index] + (1.0 - beta_1) * gradient
            ptq_v[item_index] = beta_2 * ptq_v[item_index] + (1.0 - beta_2) * gradient * gradient
            m_hat = ptq_m[item_index] / (1.0 - beta_1**epoch)
            v_hat = ptq_v[item_index] / (1.0 - beta_2**epoch)
            ptq_logits[item_index] -= learning_rate * m_hat / (math.sqrt(v_hat) + EPS)

    ptqs = [sigmoid(value) for value in ptq_logits]
    predictions = [
        [
            ptqs[item_index]
            * sigmoid(scale * (abilities[participant_index] - difficulties[item_index]))
            for item_index in range(item_count)
        ]
        for participant_index in range(participant_count)
    ]
    loss = negative_log_likelihood(
        scores,
        abilities,
        ptq_logits,
        difficulties,
        discrimination,
        d_constant,
        ability_l2,
        ptq_prior,
        ptq_prior_l2,
    )
    return abilities, ptqs, predictions, loss


def write_abilities(path: Path, abilities: list[float]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["participant", "ability"])
        for index, ability in enumerate(abilities, start=1):
            writer.writerow([f"p{index}", f"{ability:.6f}"])


def write_ptqs(path: Path, item_ids: list[str], ptqs: list[float], difficulties: list[float]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item", "ptq", "difficulty"])
        for item_id, ptq, difficulty in zip(item_ids, ptqs, difficulties):
            writer.writerow([item_id, f"{ptq:.6f}", f"{difficulty:.6f}"])


def write_predictions(path: Path, item_ids: list[str], predictions: list[list[float]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(item_ids)
        for row in predictions:
            writer.writerow([f"{value:.6f}" for value in row])


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
        help="CSV of fixed item difficulties. Omit only for exploratory runs.",
    )
    parser.add_argument(
        "--out-prefix",
        type=Path,
        default=Path("fit_irt_ptq"),
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
    parser.add_argument(
        "--ptq-prior",
        type=float,
        default=0.9,
        help="Weak prior center for PTQ. Use --ptq-prior-l2 0 to disable.",
    )
    parser.add_argument("--ptq-prior-l2", type=float, default=0.02)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_prefix = output_prefix(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    item_ids, scores = read_matrix(args.scores_csv)
    difficulties = read_difficulties(args.difficulties, item_ids)

    abilities, ptqs, predictions, loss = fit_model(
        scores=scores,
        difficulties=difficulties,
        discrimination=args.discrimination,
        d_constant=args.d_constant,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        ability_l2=args.ability_l2,
        ptq_prior=args.ptq_prior,
        ptq_prior_l2=args.ptq_prior_l2,
    )

    write_abilities(out_prefix.with_name(out_prefix.name + "_abilities.csv"), abilities)
    write_ptqs(out_prefix.with_name(out_prefix.name + "_ptq.csv"), item_ids, ptqs, difficulties)
    write_predictions(
        out_prefix.with_name(out_prefix.name + "_predictions.csv"),
        item_ids,
        predictions,
    )

    print(f"participants={len(scores)}")
    print(f"items={len(item_ids)}")
    print(f"loss={loss:.6f}")
    print(f"mean_ability={sum(abilities) / len(abilities):.6f}")
    print(f"mean_ptq={sum(ptqs) / len(ptqs):.6f}")


if __name__ == "__main__":
    main()
