#!/usr/bin/env python3
"""Measure run-to-run variance in LLM translation cells.

The question
------------
The three ``llm_prompt_*`` methods call OpenAI without a temperature or seed, so
the API default of 1.0 applies. Every LLM passage in the grid is therefore a
single random draw, and no replicate has ever been taken. Reported spread across
the prompt-quality axis is roughly 8.7 accuracy points (llm_prompt_low 0.642 ->
llm_prompt_high 0.729). Nobody has measured how far one condition moves when it
is simply re-run.

If within-condition spread is comparable to the between-condition gap, the
prompt-quality axis is not resolved and those cells need replicates. If it is
small, the existing numbers stand and a seed is enough going forward.

What this does
--------------
Translates the same passage ``--replicates`` times under one method, then
reports how much the translations differ from each other. Text divergence is
measured directly; if a QA set is supplied and ``--score`` is passed, each
replicate is additionally run through answer generation and scoring so the
spread can be expressed in the same accuracy units as the headline result.

Text-only mode costs ``--replicates`` translation calls and no scoring calls,
which is enough to answer the first-order question cheaply.

Usage (from repo root):

    export OPENAI_API_KEY=...

    # cheap: text divergence only
    python evaluation/scripts/analysis/measure_replicate_variance.py \\
      --passage evaluation/datasets/pseudonymized/passages/test_passage_luke5.txt \\
      --method llm_prompt_high --replicates 5

    # compare against a pinned-temperature run
    python evaluation/scripts/analysis/measure_replicate_variance.py \\
      --passage ... --method llm_prompt_high --replicates 5 --temperature 0

    # deterministic controls should show zero spread
    python evaluation/scripts/analysis/measure_replicate_variance.py \\
      --passage ... --method nllb-200-1.3B --replicates 3
"""

from __future__ import annotations

import argparse
import difflib
import json
import statistics
import sys
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVAL_DIR = Path(__file__).resolve().parents[2]

# Reported between-condition spread on the prompt-quality axis, used only as a
# reference line when interpreting the measured within-condition spread.
REFERENCE_GAP = {
    "llm_prompt_low": 0.642,
    "llm_prompt_medium": 0.659,
    "llm_prompt_high": 0.729,
}


class ReplicateError(Exception):
    pass


def pairwise_similarity(texts: list[str]) -> list[float]:
    return [
        difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        for a, b in combinations(texts, 2)
    ]


def translate_replicates(
    passage: str,
    method: str,
    replicates: int,
    *,
    target_language: str,
    source_language: str,
    temperature: float | None,
    seed: int | None,
) -> list[str]:
    from evaluation.scripts.scoring.translation_quality import translate_with_method

    # One call per replicate rather than one batched call, so each draw is
    # independent in exactly the way a separate pipeline run would be.
    outputs = []
    for index in range(replicates):
        print(f"  replicate {index + 1}/{replicates}")
        result = translate_with_method(
            [passage],
            method,
            target_language=target_language,
            source_language=source_language,
            temperature=temperature,
            seed=seed,
        )
        outputs.append(result[0])
    return outputs


def summarize_text(outputs: list[str]) -> dict:
    similarities = pairwise_similarity(outputs)
    lengths = [len(text) for text in outputs]
    return {
        "replicates": len(outputs),
        "identical": len(set(outputs)) == 1,
        "distinct_outputs": len(set(outputs)),
        "similarity_min": round(min(similarities), 4) if similarities else 1.0,
        "similarity_mean": round(statistics.fmean(similarities), 4) if similarities else 1.0,
        "similarity_max": round(max(similarities), 4) if similarities else 1.0,
        "length_min": min(lengths),
        "length_max": max(lengths),
        "length_stdev": round(statistics.pstdev(lengths), 2) if len(lengths) > 1 else 0.0,
    }


def interpret(method: str, summary: dict) -> list[str]:
    notes = []
    if summary["identical"]:
        notes.append(
            "All replicates identical: this method is deterministic, so single "
            "draws in the existing grid carry no sampling variance."
        )
        return notes

    mean_divergence = 1.0 - summary["similarity_mean"]
    notes.append(
        f"Replicates differ: mean pairwise divergence {mean_divergence:.1%} of "
        f"the translated text."
    )
    if method in REFERENCE_GAP:
        gap = max(REFERENCE_GAP.values()) - min(REFERENCE_GAP.values())
        notes.append(
            f"For reference, the reported low->high accuracy gap is {gap:.3f}. "
            "Text divergence is not directly comparable to accuracy, so rerun "
            "with --qa and --score to express this spread in accuracy units "
            "before concluding anything about the prompt-quality axis."
        )
    notes.append(
        "Existing llm_prompt_* cells are single unseeded draws and are not "
        "reproducible. Pass --temperature 0 --seed N for future runs."
    )
    return notes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passage", type=Path, required=True)
    parser.add_argument("--method", default="llm_prompt_high")
    parser.add_argument("--replicates", type=int, default=5)
    parser.add_argument("--target-language", default="Simplified Chinese")
    parser.add_argument("--source-language", default="en")
    # Analysis scripts default to 0 because a differential measurement is
    # meaningless when the translator disagrees with itself. The pipeline's own
    # default is deliberately left alone: flipping it would make future runs
    # incomparable to the temperature-1.0 cells already in the grid.
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help=(
            "Sampling temperature for LLM methods. Defaults to 0 here for "
            "reproducibility. Pass --temperature 1.0 to reproduce the "
            "pipeline's historical unseeded behaviour."
        ),
    )
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--save-translations",
        type=Path,
        help="Directory to write each replicate translation for inspection.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.replicates < 2:
        print("error: --replicates must be at least 2", file=sys.stderr)
        return 1

    try:
        passage = args.passage.read_text(encoding="utf-8")
        setting = (
            "API default (1.0)"
            if args.temperature is None
            else f"temperature={args.temperature}, seed={args.seed}"
        )
        print(f"[{args.method}] {args.replicates} replicates, {setting}")
        outputs = translate_replicates(
            passage,
            args.method,
            args.replicates,
            target_language=args.target_language,
            source_language=args.source_language,
            temperature=args.temperature,
            seed=args.seed,
        )
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # translation backends raise their own types
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summary = summarize_text(outputs)
    notes = interpret(args.method, summary)

    if args.save_translations:
        args.save_translations.mkdir(parents=True, exist_ok=True)
        for index, text in enumerate(outputs, start=1):
            (args.save_translations / f"replicate_{index}.txt").write_text(
                text, encoding="utf-8"
            )
        print(f"wrote {len(outputs)} translation(s) to {args.save_translations}")

    payload = {
        "passage": str(args.passage),
        "method": args.method,
        "temperature": args.temperature,
        "seed": args.seed,
        "summary": summary,
        "notes": notes,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")

    print()
    print(f"  replicates          {summary['replicates']}")
    print(f"  distinct outputs    {summary['distinct_outputs']}")
    print(
        f"  similarity          min {summary['similarity_min']:.4f}  "
        f"mean {summary['similarity_mean']:.4f}  max {summary['similarity_max']:.4f}"
    )
    print(
        f"  length              {summary['length_min']}-{summary['length_max']} "
        f"chars (sd {summary['length_stdev']})"
    )
    print()
    for note in notes:
        print(f"  * {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
