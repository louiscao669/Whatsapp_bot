#!/usr/bin/env python3
"""Isolate LLM-judge variance by re-scoring one fixed set of answers.

Why this matters more than the translation-variance result
----------------------------------------------------------
``score_replicate_variance.py`` measured *passage translation* variance and
found it large enough to swamp the prompt-quality axis (luke5, llm_prompt_high,
temp 0: accuracy range 0.0962 vs a reported low->high gap of 0.087). That result
pinned the judge at temperature 0 deliberately, so it captured translation
variance only, and it therefore applies only to the three ``llm_prompt_*``
methods -- the deterministic translators (helsinki, mBART-50, NLLB, dropout,
google_word_by_word) do not have that component.

Judge variance is different: historical scoring ran the judge at the API default
temperature of 1.0, so it contaminates **every method's** score, including the
deterministic ones, and therefore the defect dose-response curves as well.

This script holds everything else fixed -- same passage, same answers, same
back-translations -- and only re-runs judging. Any spread observed is
attributable to the judge alone.

Reading the result:

* accuracy range small (<0.02) -- judging is stable; the deterministic methods'
  historical scores stand, and only the llm_prompt_* cells need replicates.
* accuracy range comparable to the translation-variance result (~0.09) -- every
  cell in the grid carries unrecorded noise of that size, and the defect
  dose-response curves need error bars before any monotonicity claim holds.

``flip_rate`` is the sharper diagnostic: the fraction of individual items that
changed label across runs. Accuracy can look stable while many items flip in
compensating directions.

Usage (from repo root), cheapest path -- reuse back-translated answers the
pipeline already wrote:

    export OPENAI_API_KEY=...
    python evaluation/scripts/analysis/measure_judge_variance.py \\
      --answers  .../generated_answers_target_llama_backtranslated.json \\
      --qa       .../qa_target_decanonicalized.json \\
      --runs 5 --judge-temperature 1.0 \\
      --out evaluation/outputs/_variance/judge_luke5.json

Then rerun with ``--judge-temperature 0`` to confirm the fix.

Cost is ``--runs`` judging passes. No translation, no answer generation.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reference points for interpretation.
REPORTED_PROMPT_GAP = 0.087
TRANSLATION_VARIANCE_RANGE = 0.0962  # luke5, llm_prompt_high, temp 0, 5 replicates


class JudgeVarianceError(Exception):
    pass


def combined_accuracy(summary: dict) -> float | None:
    """(mcq_correct + open score sum) / total, matching the metric used elsewhere."""
    total = summary.get("total") or summary.get("count")
    mcq_correct = summary.get("mcq_correct")
    if not total or mcq_correct is None:
        return None
    open_sum = summary.get("open_llm_score_sum")
    if open_sum is None:
        open_mean = summary.get("open_llm_score_mean")
        open_count = summary.get("open_count")
        if open_mean is None or open_count is None:
            return None
        open_sum = float(open_mean) * float(open_count)
    return (float(mcq_correct) + float(open_sum)) / float(total)


def item_labels(scored: list[dict]) -> dict[str, str]:
    """Per-item judge label, keyed stably so runs can be compared item by item."""
    labels = {}
    for index, item in enumerate(scored):
        key = str(
            item.get("item_index")
            or item.get("content_id")
            or item.get("passage_id")
            or index
        )
        label = item.get("llm_english_label")
        if label is not None:
            labels[key] = str(label)
    return labels


def flip_statistics(runs: list[dict[str, str]]) -> dict:
    """How many items did not hold the same label across every run."""
    if not runs:
        return {"items": 0, "flipped": 0, "flip_rate": 0.0, "examples": []}
    shared = set(runs[0])
    for run in runs[1:]:
        shared &= set(run)

    flipped = []
    for key in sorted(shared):
        seen = {run[key] for run in runs}
        if len(seen) > 1:
            counts = Counter(run[key] for run in runs)
            flipped.append({"item": key, "labels": dict(counts)})

    return {
        "items": len(shared),
        "flipped": len(flipped),
        "flip_rate": round(len(flipped) / len(shared), 4) if shared else 0.0,
        "examples": flipped[:10],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--answers",
        type=Path,
        required=True,
        help="Back-translated generated answers JSON (already contains English).",
    )
    parser.add_argument("--qa", type=Path, required=True, help="Standard QA set.")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--judge-temperature",
        type=float,
        default=1.0,
        help=(
            "Defaults to 1.0 to reproduce the historical scoring condition. Pass "
            "0 to confirm that pinning temperature removes the spread."
        ),
    )
    parser.add_argument("--judge-model", default="gpt-4.1-mini")
    parser.add_argument("--judge-batch-size", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--placeholder-standard-answers",
        action="store_true",
        help="Match the pipeline flag if the run being reproduced used it.",
    )
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs < 2:
        print("error: --runs must be at least 2", file=sys.stderr)
        return 1

    try:
        from evaluation.scripts.scoring.score_generated_answers import (
            extract_items,
            load_json,
            score_items,
            summarize,
        )

        generated = extract_items(load_json(args.answers))
        standards = extract_items(load_json(args.qa))

        missing = [
            item
            for item in generated
            if not str(item.get("generated_answer_english") or "").strip()
            and str(item.get("q_type") or "open") != "mcq"
        ]
        if missing:
            print(
                f"warning: {len(missing)} open item(s) lack "
                "generated_answer_english; they will be back-translated inside "
                "each run, which reintroduces back-translation variance and "
                "makes this no longer a pure judge measurement.",
                file=sys.stderr,
            )

        print(
            f"judging {len(generated)} item(s) x {args.runs} run(s) at "
            f"temperature {args.judge_temperature}"
        )

        accuracies = []
        label_runs = []
        for run in range(1, args.runs + 1):
            scored = score_items(
                generated,
                standards,
                judge_model=args.judge_model,
                translation_model=args.judge_model,
                retries=args.retries,
                skip_llm=False,
                placeholder_standard_answers=args.placeholder_standard_answers,
                judge_batch_size=args.judge_batch_size,
                temperature=args.judge_temperature,
            )
            summary = summarize(scored)
            accuracy = combined_accuracy(summary)
            if accuracy is None:
                raise JudgeVarianceError(
                    f"could not extract accuracy from summary: {summary}"
                )
            accuracies.append(accuracy)
            label_runs.append(item_labels(scored))
            print(f"  run {run}/{args.runs}: accuracy = {accuracy:.4f}")

    except JudgeVarianceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    flips = flip_statistics(label_runs)
    spread = max(accuracies) - min(accuracies)
    stats = {
        "runs": len(accuracies),
        "judge_temperature": args.judge_temperature,
        "min": round(min(accuracies), 4),
        "max": round(max(accuracies), 4),
        "mean": round(statistics.fmean(accuracies), 4),
        # Sample sd (n-1): these replicates are a sample used to estimate
        # the underlying spread, not the whole population.
        "stdev": round(statistics.stdev(accuracies), 4),
        "range": round(spread, 4),
        "range_vs_prompt_gap": round(spread / REPORTED_PROMPT_GAP, 2),
        "range_vs_translation_variance": round(
            spread / TRANSLATION_VARIANCE_RANGE, 2
        ),
        "flip_rate": flips["flip_rate"],
        "items_flipped": flips["flipped"],
        "items_compared": flips["items"],
    }

    payload = {
        "answers": str(args.answers),
        "qa": str(args.qa),
        "stats": stats,
        "accuracies": accuracies,
        "flips": flips,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")

    print()
    print(f"  accuracy per run   {[round(a, 4) for a in accuracies]}")
    print(f"  mean               {stats['mean']:.4f}")
    print(f"  stdev              {stats['stdev']:.4f}")
    print(f"  range              {stats['range']:.4f}")
    print(
        f"  items flipped      {stats['items_flipped']}/{stats['items_compared']} "
        f"({stats['flip_rate']:.1%})"
    )
    print()
    print(
        f"  vs reported prompt gap 0.087            {stats['range_vs_prompt_gap']}x"
    )
    print(
        f"  vs translation variance 0.0962          "
        f"{stats['range_vs_translation_variance']}x"
    )
    print()
    if spread >= 0.02 or flips["flip_rate"] >= 0.05:
        print(
            "  Judge variance is material. It applies to EVERY method in the grid,\n"
            "  including the deterministic translators, so defect dose-response\n"
            "  curves carry this noise too. Pin --temperature 0 for scoring and\n"
            "  treat existing single-scored cells as carrying this uncertainty."
        )
    else:
        print(
            "  Judge variance is small. Historical scores for the deterministic\n"
            "  methods stand; only the llm_prompt_* cells need replicates."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
