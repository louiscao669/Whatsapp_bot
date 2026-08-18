#!/usr/bin/env python3
"""Convert translation replicate variance into accuracy units.

The question
------------
``measure_replicate_variance.py`` shows that re-translating the same passage
with ``llm_prompt_high`` produces materially different text: ~22% divergence at
the pipeline's historical setting (unseeded, API default temperature 1.0) and
~5.6% at temperature 0. Text divergence is not accuracy, so on its own it cannot
say whether the reported prompt-quality gap survives.

The reported gap is roughly 8.7 accuracy points (llm_prompt_low 0.642 ->
llm_prompt_high 0.729). This script scores each replicate through the real
answer-and-score path and reports the within-condition spread in the same units.

Reading the result:

* spread much smaller than 0.087 -- the prompt-quality axis is resolved, and
  single draws in the existing grid are acceptable.
* spread comparable to 0.087 -- the axis is not resolved. Those cells are single
  samples from overlapping distributions and need replicates before the ordering
  can be trusted.

Design notes
------------
Only the passage varies. The Chinese QA set is translated once and reused across
every replicate, so the measured spread is attributable to passage translation
rather than to question wording. Answer generation runs against Ollama at
temperature 0 already, so the answerer contributes no variance; the judge does,
which is why ``--judge-temperature`` defaults to 0 here.

Usage (from repo root), reusing translations already on disk:

    export OPENAI_API_KEY=...
    python evaluation/scripts/analysis/score_replicate_variance.py \\
      --replicate-dir /tmp/reps_t0 \\
      --qa evaluation/datasets/pseudonymized/qa/qa_output_luke_ch5_all_formats.json \\
      --answer-provider ollama --answer-model qwen3:1.7b --ollama-no-think \\
      --out evaluation/outputs/_variance/luke5_t0.json

Cost is one QA translation plus, per replicate, one answer pass, one
back-translation, and one judging pass. No passage translation calls.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVAL_DIR = Path(__file__).resolve().parents[2]

# Reference points from PROJECT_CONTEXT.md, used only to frame the result.
REPORTED_PROMPT_GAP = 0.087
REPORTED_METHOD_SPREAD = 0.186  # google_word_by_word 0.543 -> llm_prompt_high 0.729


class VarianceError(Exception):
    pass


def load_replicates(directory: Path) -> list[tuple[str, str]]:
    files = sorted(directory.glob("replicate_*.txt"))
    if len(files) < 2:
        raise VarianceError(
            f"need at least 2 replicate_*.txt files in {directory}, found {len(files)}"
        )
    return [(path.name, path.read_text(encoding="utf-8")) for path in files]


def translate_qa_once(
    qa_path: Path,
    target_language: str,
    model: str,
    batch_size: int,
    retries: int,
    temperature: float | None,
) -> list[dict]:
    """Translate the QA set a single time, shared by every replicate.

    Holding questions fixed is what makes the measured spread attributable to
    the passage rather than to question wording.
    """
    from evaluation.scripts.data_prep.translate_llm_qa_to_chinese import (
        load_json,
        normalize_items,
        translate_items,
    )

    items = normalize_items(load_json(qa_path))
    return translate_items(
        items,
        model=model,
        target_language=target_language,
        batch_size=batch_size,
        retries=retries,
        dry_run=False,
        temperature=temperature,
    )


def score_one_replicate(
    passage: str,
    qa_items: list[dict],
    args: argparse.Namespace,
) -> dict:
    from evaluation.agents.generate_chinese_answers import (
        generate_answers,
        public_questions,
    )
    from evaluation.scripts.scoring.score_generated_answers import (
        backtranslate_generated_answers,
        score_items,
        summarize,
    )

    generated = generate_answers(
        passage,
        public_questions(qa_items),
        provider=args.answer_provider,
        model=args.answer_model,
        ollama_base_url=args.ollama_base_url,
        batch_size=args.answer_batch_size,
        verse_window=None if args.answer_verse_window < 0 else args.answer_verse_window,
        retries=args.retries,
        dry_run=False,
        allow_partial_answers=True,
        ollama_no_think=args.ollama_no_think,
        expanded_answer_format=False,
        mcq_choice_mapper=args.mcq_choice_mapper,
        mcq_choice_model=args.judge_model,
    )
    backtranslated = backtranslate_generated_answers(
        generated,
        qa_items,
        translation_model=args.judge_model,
        retries=args.retries,
        temperature=args.judge_temperature,
    )
    scored = score_items(
        backtranslated,
        qa_items,
        judge_model=args.judge_model,
        translation_model=args.judge_model,
        retries=args.retries,
        skip_llm=False,
        judge_batch_size=args.judge_batch_size,
        temperature=args.judge_temperature,
    )
    return summarize(scored)


def combined_accuracy(summary: dict) -> float | None:
    """Reproduce the metric used elsewhere: (mcq_correct + open score sum)/total.

    ``summarize()`` reports ``open_llm_score_mean`` and ``open_count`` rather
    than a sum, so the sum is reconstructed. ``open_llm_score_sum`` is still
    accepted in case a caller supplies it directly.
    """
    for key in ("combined_accuracy", "accuracy", "overall_accuracy"):
        value = summary.get(key)
        if isinstance(value, (int, float)):
            return float(value)

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicate-dir", type=Path, required=True)
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--target-language", default="Simplified Chinese")
    parser.add_argument("--qa-translation-model", default="gpt-4.1-mini")
    parser.add_argument("--qa-batch-size", type=int, default=20)
    parser.add_argument(
        "--translated-qa",
        type=Path,
        help="Reuse a previously translated Chinese QA set instead of translating.",
    )
    parser.add_argument("--answer-provider", choices=("openai", "ollama"), default="ollama")
    parser.add_argument("--answer-model", default="qwen3:1.7b")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434")
    parser.add_argument("--ollama-no-think", action="store_true")
    parser.add_argument("--answer-batch-size", type=int, default=1)
    parser.add_argument("--answer-verse-window", type=int, default=2)
    parser.add_argument("--judge-model", default="gpt-4.1-mini")
    parser.add_argument("--judge-batch-size", type=int, default=20)
    parser.add_argument(
        "--judge-temperature",
        type=float,
        default=0.0,
        help=(
            "Temperature for back-translation and judging. Defaults to 0 so the "
            "measured spread reflects passage variance, not judge variance."
        ),
    )
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--mcq-choice-mapper", default="rules")
    parser.add_argument("--out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        replicates = load_replicates(args.replicate_dir)
        print(f"loaded {len(replicates)} replicate passage(s) from {args.replicate_dir}")

        if args.translated_qa:
            qa_items = json.loads(args.translated_qa.read_text(encoding="utf-8"))
            print(f"reusing translated QA: {args.translated_qa}")
        else:
            print("translating QA once (shared across replicates)")
            qa_items = translate_qa_once(
                args.qa,
                args.target_language,
                args.qa_translation_model,
                args.qa_batch_size,
                args.retries,
                args.judge_temperature,
            )
            cache = args.replicate_dir / "qa_translated.json"
            cache.write_text(
                json.dumps(qa_items, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
            )
            print(f"  cached to {cache} (pass --translated-qa to reuse)")

        rows = []
        for name, passage in replicates:
            print(f"scoring {name}")
            summary = score_one_replicate(passage, qa_items, args)
            accuracy = combined_accuracy(summary)
            rows.append({"replicate": name, "accuracy": accuracy, "summary": summary})
            print(f"  accuracy = {accuracy}")

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    accuracies = [row["accuracy"] for row in rows if row["accuracy"] is not None]
    if len(accuracies) < 2:
        print("error: could not extract accuracy from summaries", file=sys.stderr)
        print(json.dumps(rows[0]["summary"], ensure_ascii=False, indent=1)[:800])
        return 1

    spread = max(accuracies) - min(accuracies)
    stats = {
        "replicates": len(accuracies),
        "min": round(min(accuracies), 4),
        "max": round(max(accuracies), 4),
        "mean": round(statistics.fmean(accuracies), 4),
        # Sample sd (n-1): these replicates are a sample used to estimate
        # the underlying spread, not the whole population.
        "stdev": round(statistics.stdev(accuracies), 4),
        "range": round(spread, 4),
        "range_vs_prompt_gap": round(spread / REPORTED_PROMPT_GAP, 2),
        "range_vs_method_spread": round(spread / REPORTED_METHOD_SPREAD, 2),
    }

    payload = {
        "replicate_dir": str(args.replicate_dir),
        "qa": str(args.qa),
        "answer_model": args.answer_model,
        "judge_temperature": args.judge_temperature,
        "stats": stats,
        "rows": rows,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")

    print()
    print(f"  accuracy per replicate  {[round(a, 4) for a in accuracies]}")
    print(f"  mean                    {stats['mean']:.4f}")
    print(f"  stdev                   {stats['stdev']:.4f}")
    print(f"  range                   {stats['range']:.4f}")
    print()
    print(
        f"  reported low->high prompt gap   {REPORTED_PROMPT_GAP:.3f}  "
        f"({stats['range_vs_prompt_gap']}x the within-condition range)"
    )
    print(
        f"  reported full method spread     {REPORTED_METHOD_SPREAD:.3f}  "
        f"({stats['range_vs_method_spread']}x)"
    )
    print()
    if spread >= REPORTED_PROMPT_GAP * 0.5:
        print(
            "  Within-condition spread is a large fraction of the between-condition\n"
            "  gap. Single-draw llm_prompt_* cells cannot support the reported\n"
            "  ordering; those conditions need replicates and a mean."
        )
    else:
        print(
            "  Within-condition spread is small relative to the between-condition\n"
            "  gap. Single draws are defensible, though pinning temperature is\n"
            "  still worth doing for reproducibility."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
