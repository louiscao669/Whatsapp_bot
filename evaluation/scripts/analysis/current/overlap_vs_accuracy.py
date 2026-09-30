#!/usr/bin/env python3
"""Is the option-overlap cue actually exploited, or only theoretically available?

audit_option_overlap.py measures how much of each option is lifted verbatim from the
window. This joins that to the model runs: if accuracy rises with the KEY'S MARGIN over
its best distractor, the cue is live; if it is flat, the leak is theoretical.

Overlap is recomputed from the SAME output tree the scores come from, rather than read
from the audit's JSON, so the strings measured are the ones the model actually saw --
tier1_strong is pseudonymized, and its options and passage differ from the canonical set
even though the item ids match.

  gold72   outputs/tier1_bsb_unblinded_5opt  windows from tier1_qa_verse_windows_canonical
  hard66   outputs/tier1_strong              windows from tier1_hard66_canonical

Clean condition only (omission/0%): a defect rewrites the window, which would change the
overlap being tested.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO / "human_pilot"))

MODELS = ("llama321b", "qwen2515b", "qwen317b")
LETTERS = "ABCD"
HARD_DIR = REPO / "evaluation/datasets/qa/tier1_hard66_canonical"
WINDOWS = REPO / "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"


def longest_shared_span(option: str, window: str) -> int:
    best = 0
    for start in range(len(option)):
        for end in range(start + best + 1, len(option) + 1):
            if option[start:end] in window:
                best = end - start
            else:
                break
    return best


def ratio(option: str, window: str) -> float:
    option = re.sub(r"\s+", "", option or "")
    return longest_shared_span(option, window) / len(option) if option else 0.0


def base_id(raw: str) -> str:
    return re.sub(r"-(open|mcq)$", "", str(raw or "")).replace("uw-", "")


def build(outputs: Path, root: str, windows_by_item: dict, metadata: dict) -> dict:
    """{item: {'margin': float, 'key': float}} computed inside `root`."""
    import pilot_import as pi
    out = {}
    for passage_id, meta in metadata.items():
        clean = outputs / root / passage_id / "omission" / "0%"
        qa = next((clean / n for n in ("qa_target_decanonicalized.json", "qa_target.json")
                   if (clean / n).exists()), None)
        passage = clean / "passage_target.txt"
        if qa is None or not passage.exists():
            continue
        try:
            verses = dict(pi.parse_tier1_verses(passage.read_text(encoding="utf-8"), meta))
        except Exception:
            continue
        for record in json.loads(qa.read_text(encoding="utf-8")):
            if record.get("q_type") != "mcq":
                continue
            item = base_id(record.get("passage_id"))
            labels = windows_by_item.get(item)
            if not labels:
                continue
            text = []
            for label in labels:
                label = str(label)
                if label in verses:
                    text.append(verses[label])
                    continue
                for key, value in verses.items():
                    if key.split(":")[-1] == label:
                        text.append(value)
                        break
            window = re.sub(r"\s+", "", "".join(text))
            options = record.get("A") or {}
            correct = str(record.get("correct") or "A").strip()[:1]
            if not window or correct not in options:
                continue
            key_ratio = ratio(options[correct], window)
            others = [ratio(v, window) for k, v in options.items()
                      if k in LETTERS and k != correct]
            ranked = sorted(((ratio(v, window), k) for k, v in options.items()
                             if k in LETTERS), reverse=True)
            out[item] = {"key": key_ratio,
                         "margin": key_ratio - (max(others) if others else 0.0),
                         "correct": correct,
                         "top_letter": ranked[0][1] if ranked else None,
                         "top_distractor": next((k for _r, k in ranked if k != correct), None)}
    return out


def scores(outputs: Path, root: str, model: str) -> dict:
    """{item: bool} MCQ correctness in the clean condition."""
    out = {}
    for path in glob.glob(str(outputs / root / "t1_*" / model / "omission" / "0%"
                              / "scores_target_llama.json")):
        for item in json.loads(Path(path).read_text(encoding="utf-8")).get("items", []):
            if item.get("q_type") == "mcq" and item.get("direct_correct") is not None:
                out[base_id(item.get("id"))] = (bool(item["direct_correct"]),
                                                item.get("selected_choice"))
    return out


def report(name: str, overlap: dict, per_model: dict) -> None:
    print(f"\n=== {name}")
    joined = [(o["margin"], o["key"], item) for item, o in overlap.items()
              if any(item in s for s in per_model.values())]
    if not joined:
        print("   nothing joined")
        return
    margins = sorted(m for m, _, _ in joined)
    lo, hi = margins[len(margins) // 3], margins[2 * len(margins) // 3]
    print(f"   {len(joined)} items joined; margin tertiles at {lo:.2f} / {hi:.2f}")
    print(f"   {'model':12s} {'low margin':>14s} {'mid':>14s} {'high':>14s}"
          f" {'flagged':>14s} {'rest':>14s}")
    for model, correct in per_model.items():
        buckets = {"low": [], "mid": [], "high": [], "flag": [], "rest": []}
        for margin, key, item in joined:
            if item not in correct:
                continue
            ok = correct[item][0]
            buckets["low" if margin <= lo else "mid" if margin <= hi else "high"].append(ok)
            buckets["flag" if (key >= 0.8 and margin >= 0.3) else "rest"].append(ok)
        def cell(values):
            return f"{sum(values)/len(values)*100:>8.0f}% ({len(values):2d})" if values else f"{'—':>14s}"
        print(f"   {model:12s} {cell(buckets['low'])} {cell(buckets['mid'])} "
              f"{cell(buckets['high'])} {cell(buckets['flag'])} {cell(buckets['rest'])}")
    # pooled point-biserial between margin and correctness
    xs, ys = [], []
    for margin, _key, item in joined:
        for correct in per_model.values():
            if item in correct:
                xs.append(margin)
                ys.append(1.0 if correct[item][0] else 0.0)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    r = cov / (vx * vy) if vx and vy else 0.0
    print(f"   pooled across models: r(margin, correct) = {r:+.3f} over {n} responses")

    # The decisive test: when the model is WRONG, does it land on the distractor that
    # shares the most text with the window? Chance is 1/3 among three distractors.
    print("   when wrong, chose the highest-overlap distractor:")
    for model, correct in per_model.items():
        hits = total = 0
        for _margin, _key, item in joined:
            row = correct.get(item)
            if not row or row[0] or not row[1]:
                continue
            info = overlap[item]
            total += 1
            hits += (row[1] == info.get("top_distractor"))
        if total:
            print(f"      {model:12s} {hits}/{total} = {hits/total*100:.0f}%   (chance 33%)")
    # and: how often is the most-overlapping option the key at all?
    key_is_top = sum(1 for _m, _k, i in joined if overlap[i]["top_letter"] == overlap[i]["correct"])
    print(f"   the most-overlapping option IS the key in {key_is_top}/{len(joined)} items "
          f"({key_is_top/len(joined)*100:.0f}%)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outputs", type=Path, default=Path(os.path.expanduser(
        "~/mnt/eten-research-outputs/evaluation/outputs")))
    args = ap.parse_args()

    import pilot_import as pi
    metadata = {m["id"]: m for m in pi.load_tier1_metadata(REPO / "evaluation")}

    gold_windows = {w["content_id"]: w["window"]
                    for w in json.loads(WINDOWS.read_text(encoding="utf-8"))["windows"]}
    hard_windows = {}
    for path in sorted(HARD_DIR.glob("t1_*.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            if record.get("window_verses"):
                hard_windows[base_id(record.get("passage_id"))] = record["window_verses"]

    for name, root, windows in (("gold72  (tier1_bsb_unblinded_5opt)", "tier1_bsb_unblinded_5opt", gold_windows),
                                ("hard66  (tier1_strong, pseudonymized)", "tier1_strong", hard_windows)):
        overlap = build(args.outputs, root, windows, metadata)
        per_model = {m: scores(args.outputs, root, m) for m in MODELS}
        report(name, overlap, per_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
