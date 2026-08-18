#!/usr/bin/env python3
"""Score chosen tier-1 QAs on the hard-QA selection dimensions, using gpt-5.

Scores each item 1-10 on the four dimensions from
``qa_generation/prompts/scored_qa.py`` (``ScoredJSONStructure``):

    structure_dependence  answer findable by spotting a word (low) vs requires
                          following the structure (high)
    statement_uniqueness  fact carried in one place (high) vs restated elsewhere (low)
    answer_certainty      exactly one defensible answer given a clear translation
    centrality            how central the fact is to what the window is about

Why gpt-5 specifically, and not a cheaper judge: the thresholds in
``services/hard_qa_recovery.py`` (``min_structure``, ``fallback_structure``) are
calibrated against gpt-5's distribution. The measured caveat in scored_qa.py:
on Luke 2, gpt-4o-mini used only FOUR distinct values of structure_dependence
with mean 2.4, against gpt-5's 5.9 over the full scale -- which silently
tightened the gate and cut usable items from 3.8 per window to 0.9. A cheaper
judge does not produce a slightly noisier version of the same number; it
produces a differently-scaled number that the thresholds misread.

READ THE SCORES AS DESCRIPTION, NOT AS A PASS/FAIL GATE. This rubric was built
to filter candidates the hard-QA pipeline GENERATED -- questions deliberately
constructed on confusable sets with verbatim distractors. These items are
unfoldingWord questions, which were not built that way, so a low
structure_dependence may reflect provenance rather than a defect.

Usage (from repo root, needs OPENAI_API_KEY):
  python scripts/score_tier1_good_items.py \
      --items evaluation/datasets/tier1_gold_72.json \
      --only  t1_judg9:iw06,t1_1kgs13:trr6,... \
      --out   evaluation/datasets/tier1_good_item_scores.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# The nine that cleared usable-at-pilot-doses + p<=0.05 + separates 15 from 30.
DEFAULT_ITEMS = [
    "t1_judg9:iw06", "t1_1kgs13:trr6", "t1_2chr26:mv16", "t1_2kgs6_7:dbzo",
    "t1_judg17_18:tyai", "t1_2kgs6_7:pb1x", "t1_judg9:lt0r",
    "t1_2kgs11:w4ys", "t1_judg17_18:e4u2",
]
DIMENSIONS = ("structure_dependence", "statement_uniqueness",
              "answer_certainty", "centrality")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qa-generation", type=Path, required=True,
                    help="path to the qa_generation package root")
    ap.add_argument("--items", type=Path, required=True,
                    help="tier1_gold_72.json (carries question, answer, window)")
    ap.add_argument("--only", help="comma list of content_ids; default the 9")
    ap.add_argument("--model", default="gpt-5",
                    help="judge model. Do NOT change without recalibrating the "
                         "thresholds in hard_qa_recovery.py")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required")
    sys.path.insert(0, str(args.qa_generation.resolve().parent))

    from qa_generation.prompts.scored_qa import score_structure_prompt, ScoredJSONStructure
    from qa_generation.prompts.hard_qa import _build_llm

    payload = json.loads(args.items.read_text(encoding="utf-8"))
    records = payload.get("items", payload)
    wanted = [s.strip() for s in args.only.split(",")] if args.only else DEFAULT_ITEMS
    chosen = [r for r in records if r.get("content_id") in set(wanted)]
    missing = set(wanted) - {r.get("content_id") for r in chosen}
    if missing:
        print(f"[warn] not found in --items: {sorted(missing)}")
    if not chosen:
        raise SystemExit("no items to score")

    judge = _build_llm(args.model)
    chain = score_structure_prompt | judge.with_structured_output(ScoredJSONStructure)

    results = []
    for rec in chosen:
        # One call per item so a single malformed response cannot take down the
        # batch, and so each score is attributable to its own window.
        window = rec.get("window_text") or ""
        if not window:
            print(f"[warn] {rec['content_id']}: no window_text in --items; the judge "
                  "will score without passage context and the numbers will not be "
                  "comparable. Populate window_text first.")
        # Prompt slots are `window` and `Qs` (scored_qa.py ~L336). `Qs` expects
        # the plain-text shape produced by format_candidates -- "Question: ...\n
        # Answer: ..." -- not JSON; the prompt asks the judge to copy Q back
        # verbatim so scores can be matched, which JSON quoting would disturb.
        out = chain.invoke({
            "window": window,
            "Qs": f"Question: {rec.get('question')}\nAnswer: {rec.get('answer')}",
        })
        # ScoredJSONStructure wraps the per-question scores in `qa_pairs`.
        pairs = getattr(out, "qa_pairs", None) or []
        if not pairs:
            print(f"[warn] {rec['content_id']}: judge returned no qa_pairs")
        for scored in pairs:
            row = {"content_id": rec["content_id"], "question": rec.get("question")}
            row.update({d: getattr(scored, d, None) for d in DIMENSIONS})
            row["reason"] = getattr(scored, "reason", None)
            results.append(row)

    header = f"{'item':22}" + "".join(f"{d[:14]:>16}" for d in DIMENSIONS)
    print("\n" + header)
    print("-" * len(header))
    for r in sorted(results, key=lambda x: -(x.get("structure_dependence") or 0)):
        print(f"{r['content_id']:22}" +
              "".join(f"{str(r.get(d)):>16}" for d in DIMENSIONS))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(
            {"judge_model": args.model, "dimensions": list(DIMENSIONS),
             "note": "descriptive; thresholds were tuned on hard-QA-pipeline "
                     "candidates, these are unfoldingWord items",
             "scores": results}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
