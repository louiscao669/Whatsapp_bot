#!/usr/bin/env python3
"""Re-score only MCQ items into an existing scores file, without re-judging.

Use after rerun_null_mcq_answers.py has repaired MCQ answers. It reads the
patched generated-answers file, updates each MCQ row's selected_choice /
direct_correct / generation_error in scores_target_llama.json, and recomputes
the summary.

Why not just re-run the pipeline with --force-score:

  * Cost. Re-scoring re-judges every open item, which is the expensive stage.
  * Stability. The judge flips ~18% of open labels run to run (4.5% at
    temperature 0), so re-judging would silently move open scores that have
    nothing to do with the MCQ repair, and the before/after comparison would no
    longer isolate the repair.

MCQ scoring needs no model: it is a comparison of selected_choice against
correct_choice, both already present. So this is deterministic and offline, and
open items are copied through untouched.

Usage (from repo root):

    python evaluation/scripts/mcq/rescore_mcq_in_place.py \\
      evaluation/outputs/tier1/*/llama321b/llm_prompt_high/scores_target_llama.json

    python evaluation/scripts/mcq/rescore_mcq_in_place.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.scoring.score_generated_answers import summarize

DEFAULT_ANSWER_FILE = "generated_answers_target_llama.json"


def item_key(item: dict) -> str:
    """Stable identity for pairing a scored row with an answer row."""
    for field in ("id", "passage_id"):
        value = str(item.get(field) or "").strip()
        if value:
            return value
    return f"#{item.get('item_index')}"


def load_items(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for key in ("items", "questions", "qa_items"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    raise ValueError(f"unrecognised structure: {path}")


def merge_mcq(scored: list[dict], answers: list[dict]) -> tuple[list[dict], int]:
    by_key = {item_key(a): a for a in answers if a.get("q_type") == "mcq"}
    changed = 0
    for row in scored:
        if row.get("q_type") != "mcq":
            continue  # open items are the judge's; never touched here
        answer = by_key.get(item_key(row))
        if not answer:
            continue
        selected = answer.get("selected_choice")
        if selected in (None, "") or selected == row.get("selected_choice"):
            continue
        row["selected_choice"] = selected
        row["generated_answer"] = answer.get("generated_answer")
        row["generation_error"] = answer.get("generation_error")
        correct = row.get("correct_choice")
        row["direct_correct"] = bool(correct and selected == correct)
        changed += 1
    return scored, changed


def self_test() -> int:
    scored = [
        {"item_index": 1, "id": "a-mcq", "q_type": "mcq", "correct_choice": "B",
         "selected_choice": None, "direct_correct": False,
         "generation_error": "Item 1: MCQ answer must be A, B, C, or D."},
        {"item_index": 2, "id": "b-mcq", "q_type": "mcq", "correct_choice": "A",
         "selected_choice": "A", "direct_correct": True, "generation_error": None},
        {"item_index": 3, "id": "c-open", "q_type": "open", "llm_score": 0.5,
         "llm_label": "partial", "llm_core_claim_found": True},
    ]
    answers = [
        {"id": "a-mcq", "q_type": "mcq", "selected_choice": "B",
         "generated_answer": "B", "generation_error": None},
        {"id": "b-mcq", "q_type": "mcq", "selected_choice": "A"},
        {"id": "c-open", "q_type": "open", "generated_answer": "changed!"},
    ]
    merged, changed = merge_mcq([dict(r) for r in scored], answers)
    checks = [
        ("repaired item updated", merged[0]["selected_choice"] == "B"),
        ("direct_correct recomputed", merged[0]["direct_correct"] is True),
        ("stale generation_error cleared", merged[0]["generation_error"] is None),
        ("already-correct item untouched", merged[1]["direct_correct"] is True),
        ("changed count", changed == 1),
        ("open item untouched", merged[2].get("llm_score") == 0.5
         and "generated_answer" not in merged[2]),
    ]
    summary = summarize(merged)
    checks.append(("summary recomputed", summary["mcq_correct"] == 2))
    failed = 0
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed += not ok
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("scores", nargs="*", type=Path,
                        help="scores_target_llama.json files to patch.")
    parser.add_argument("--answer-file", default=DEFAULT_ANSWER_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if not args.scores:
        print("error: pass one or more scores_target_llama.json paths", file=sys.stderr)
        return 2

    total_changed = 0
    for path in args.scores:
        answers_path = path.parent / args.answer_file
        if not path.exists() or not answers_path.exists():
            print(f"  skip {path.parent}: missing scores or answers", file=sys.stderr)
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        scored = payload["items"] if isinstance(payload, dict) else payload
        before = sum(
            1 for r in scored if r.get("q_type") == "mcq" and r.get("direct_correct")
        )
        merged, changed = merge_mcq(scored, load_items(answers_path))
        summary = summarize(merged)
        after = summary["mcq_correct"]
        cell = "/".join(path.parts[-4:-1])
        print(f"  {cell:44s} repaired {changed:2d}  mcq {before} -> {after}"
              f"  acc {summary.get('mcq_correct')}/{summary.get('mcq_count')}")
        total_changed += changed
        if not args.dry_run:
            out = {"summary": summary, "items": merged} if isinstance(payload, dict) else merged
            path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    print(f"\n{total_changed} MCQ item(s) repaired"
          + ("  (dry run, nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
