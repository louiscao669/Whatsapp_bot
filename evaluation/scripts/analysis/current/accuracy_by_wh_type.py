#!/usr/bin/env python3
"""Clean-condition model accuracy broken out by the question's interrogative.

Matched comparison: the same three models and the same 5-option prompt mode on both QA
sets, so the only difference is the set itself.
  gold72   -> outputs/tier1_bsb_unblinded_5opt   (71 items x open+mcq = 142 rows)
  strong66 -> outputs/tier1_strong               (66 items x open+mcq = 132 rows)

MCQ is scored by ``direct_correct``; open by the mean ``llm_score``. They are reported
separately because they are not the same measurement.

Stems are classified on the CHINESE question, which is what the model saw. Two known
limits of classify_wh_type apply: a stem opening with a subordinate clause ("When Joash
sat..., how did the people respond?") is labelled by the subordinator, and 有何 is not a
recognised cue, so a few items land in `other`.

  python3 evaluation/scripts/analysis/current/accuracy_by_wh_type.py
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "packages" / "eten-shared"))
from eten_shared.wh_type import WH_TYPES, UNKNOWN, classify_wh_type  # noqa: E402

SETS = {"gold72": "tier1_bsb_unblinded_5opt", "strong66": "tier1_strong"}
MODELS = ("llama321b", "qwen2515b", "qwen317b")
ORDER = list(WH_TYPES) + [UNKNOWN]


def collect(outputs: Path, root: str, model: str) -> dict:
    """{wh_type: {mcq_n, mcq_ok, open_n, open_score}} for the clean condition."""
    stats = {t: {"mcq_n": 0, "mcq_ok": 0, "open_n": 0, "open_score": 0.0} for t in ORDER}
    for path in sorted(glob.glob(str(outputs / root / "t1_*" / model / "omission" / "0%"
                                    / "scores_target_llama.json"))):
        for item in json.loads(Path(path).read_text(encoding="utf-8")).get("items", []):
            bucket = stats[classify_wh_type(item.get("question"))]
            if item.get("q_type") == "mcq":
                if item.get("direct_correct") is None:
                    continue
                bucket["mcq_n"] += 1
                bucket["mcq_ok"] += bool(item["direct_correct"])
            else:
                score = item.get("llm_score")
                if score is None:
                    continue
                bucket["open_n"] += 1
                bucket["open_score"] += float(score)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outputs", type=Path,
                    default=Path(os.path.expanduser("~/mnt/eten-research-outputs/evaluation/outputs")))
    args = ap.parse_args()

    for metric, label in (("mcq", "MCQ accuracy (direct_correct)"),
                          ("open", "Open mean llm_score")):
        print(f"\n=== {label} — clean condition (omission/0%)")
        header = f"{'set / model':26s}" + "".join(f"{t:>12s}" for t in ORDER) + f"{'all':>12s}"
        print(header)
        print("-" * len(header))
        for set_name, root in SETS.items():
            for model in MODELS:
                stats = collect(args.outputs, root, model)
                cells, num, den = [], 0.0, 0
                for t in ORDER:
                    s = stats[t]
                    n = s[f"{metric}_n"]
                    if not n:
                        cells.append(f"{'—':>12s}")
                        continue
                    value = (s["mcq_ok"] if metric == "mcq" else s["open_score"]) / n
                    num += (s["mcq_ok"] if metric == "mcq" else s["open_score"])
                    den += n
                    cells.append(f"{value * 100:>8.0f}% ({n:2d})")
                overall = f"{num / den * 100:>8.1f}% ({den:3d})" if den else f"{'—':>12s}"
                print(f"{set_name + ' / ' + model:26s}" + "".join(cells) + overall)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
