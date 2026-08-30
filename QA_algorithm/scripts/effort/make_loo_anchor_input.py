#!/usr/bin/env python3
"""Write a leave-one-model-out anchor-IRT input, so item difficulty can be
estimated WITHOUT the model whose token spend G1 correlates against.

Why this exists. `anchor_irt_input_{mcq,open}.json` carries `model_responses`
for all three answerers (llama 1b, 1.5b, 1.7b), so `b_posterior` is fitted
partly from the 1.7b's own correctness. Correlating the 1.7b's token spend
against that b_hat drifts from "tokens track difficulty" toward "tokens track
what this model got wrong" -- a weaker claim, and one that would make G1 look
better than it is. Dropping the answer model's rows leaves difficulty estimated
from the OTHER two answerers only, which breaks the shared source.

Cost of doing it: b_hat is then fitted on 2 models instead of 3, so the
posteriors are noisier and lean harder on the easy/medium/hard priors
(mean -1.0/0.0/+1.0, sd 0.5). That is the right trade -- a noisier but
independent difficulty estimate ATTENUATES the correlation, so a G1 pass
against it is conservative.

Usage:
  python3 QA_algorithm/scripts/effort/make_loo_anchor_input.py --exclude '1.7b'
  # then, per q_type:
  python3 QA_algorithm/scripts/anchor_irt/estimate_anchor_irt.py \
      --input-json  QA_algorithm/inputs/anchor_irt_input_loo_open.json \
      --output-json QA_algorithm/outputs/anchor_irt_estimates_loo_open.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

QA_ROOT = Path(__file__).resolve().parents[2]
IN_DIR = QA_ROOT / "inputs"
Q_TYPES = ("mcq", "open")


def rewrite(src: Path, dst: Path, exclude: str) -> tuple[int, int, int]:
    payload = json.loads(src.read_text(encoding="utf-8"))
    responses = payload.get("model_responses")
    if not isinstance(responses, list):
        raise SystemExit(f"{src}: expected a list at 'model_responses', got "
                         f"{type(responses).__name__}")
    present = Counter(r.get("model_id") for r in responses)
    if exclude not in present:
        raise SystemExit(f"{src}: no responses from model_id={exclude!r}. "
                         f"Present: {dict(present)}")
    kept = [r for r in responses if r.get("model_id") != exclude]
    remaining = {r.get("model_id") for r in kept}
    if len(remaining) < 2:
        raise SystemExit(f"{src}: dropping {exclude!r} leaves {len(remaining)} "
                         f"model(s); a 1PL fit needs at least 2 to separate "
                         f"ability from difficulty.")
    # An item answered by nobody has no likelihood term and falls back to its
    # prior. Keep it (estimate_anchor_irt handles priors) but report the count,
    # because those items carry no information and inflate the apparent n.
    answered = {r.get("question_id") for r in kept}
    orphaned = sum(1 for q in payload.get("questions", [])
                   if q.get("question_id") not in answered)
    payload["model_responses"] = kept
    meta = payload.setdefault("metadata", {})
    meta["leave_one_out_excluded"] = exclude
    meta["leave_one_out_note"] = (
        f"Responses from {exclude!r} removed so item difficulty is independent "
        f"of that model's outcomes (G1 shared-source check).")
    payload["anchor_passage"] = (str(payload.get("anchor_passage", "")).rstrip()
                                 + f" [leave-one-out: {exclude} excluded]")
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return len(responses), len(kept), orphaned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exclude", default="1.7b",
                        help="model_id to drop. Default '1.7b' -- the answer "
                             "model whose tokens G1 uses.")
    parser.add_argument("--in-dir", type=Path, default=IN_DIR)
    parser.add_argument("--q-types", nargs="+", default=list(Q_TYPES))
    args = parser.parse_args(argv)

    written = []
    for q_type in args.q_types:
        src = args.in_dir / f"anchor_irt_input_{q_type}.json"
        if not src.exists():
            print(f"[skip] {src} not found")
            continue
        dst = args.in_dir / f"anchor_irt_input_loo_{q_type}.json"
        before, after, orphaned = rewrite(src, dst, args.exclude)
        note = f" ({orphaned} item(s) now unanswered -> prior only)" if orphaned else ""
        print(f"{q_type:<5} {before} -> {after} responses{note}\n"
              f"      wrote {dst}")
        written.append(q_type)

    if not written:
        print("[fatal] nothing written")
        return 2
    print("\nNext:")
    for q_type in written:
        print(f"  python3 QA_algorithm/scripts/anchor_irt/estimate_anchor_irt.py \\\n"
              f"      --input-json  QA_algorithm/inputs/anchor_irt_input_loo_{q_type}.json \\\n"
              f"      --output-json QA_algorithm/outputs/anchor_irt_estimates_loo_{q_type}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
