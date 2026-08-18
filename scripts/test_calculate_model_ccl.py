#!/usr/bin/env python3
"""Regression checks for the tier-1 model-level CCL calculator."""

import json
import tempfile
from pathlib import Path

from calculate_model_ccl import (
    DEFAULT_EVAL_ROOT,
    build_report,
    mean,
    write_outputs,
)


CONDITIONS = (
    "omission15",
    "omission30",
    "mistranslation15",
    "mistranslation30",
    "grammar30",
)
MODELS = ("llama321b", "qwen2515b", "qwen317b")


def check(name: str, condition: bool, failures: list[str]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
    if not condition:
        failures.append(name)


def main() -> int:
    failures = []
    report = build_report(
        DEFAULT_EVAL_ROOT, MODELS, CONDITIONS, iterations=200, seed=2026
    )
    check("the five-condition estimand is labeled full CCL",
          report["is_full_ccl"] is True, failures)
    check("all three proxy models are calculated",
          [row["model"] for row in report["models"]] == list(MODELS), failures)

    for row in report["models"]:
        check(f"{row['model']} uses 10 passages and 78 selected items",
              row["n_passages"] == 10 and row["n_items"] == 78, failures)
        check(f"{row['model']} has a complete 78 x 5 paired grid",
              row["n_item_condition_pairs"] == 390, failures)
        check(f"{row['model']} obeys clean-minus-degraded identity",
              abs(row["ccl"] - (
                  row["clean_accuracy"] - row["degraded_accuracy"]
              )) < 1e-12, failures)
        check(f"{row['model']} equally weights condition contrasts",
              abs(row["ccl"] - mean(row["condition_contrasts"].values())) < 1e-12,
              failures)
        check(f"{row['model']} reports bootstrap uncertainty",
              row["ccl_uncertainty"]["se"] >= 0
              and row["ccl_uncertainty"]["ci95_lower"]
              <= row["ccl_uncertainty"]["ci95_upper"], failures)

    expected_ensemble = mean(row["ccl"] for row in report["models"])
    check("ensemble is the equal-weight mean of model CCLs",
          abs(report["ensemble"]["ccl"] - expected_ensemble) < 1e-12, failures)

    with tempfile.TemporaryDirectory() as tmp:
        paths = write_outputs(report, Path(tmp))
        loaded = json.loads(paths[0].read_text(encoding="utf-8"))
        check("JSON and both CSV reports are written",
              all(path.exists() for path in paths), failures)
        check("serialized report retains the CCL estimate",
              loaded["models"][0]["ccl"] == report["models"][0]["ccl"], failures)

    print("\n" + ("ALL TESTS PASSED" if not failures else f"FAILED: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
