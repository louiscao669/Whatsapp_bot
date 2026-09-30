#!/usr/bin/env python3
"""How much of each MCQ option is lifted verbatim from the window the reader sees.

WHY. A respondent who exploits surface overlap does not use the key's overlap, but the
CONTRAST between options: if the key is the only option lifted whole from the text, the
item is answerable by recognising what you just read. 2chr26 item 9860 is the case that
prompted this -- the key shares all 11 of its characters with the window, the three
distractors share 20-36% of theirs.

And the property is not translation-invariant, which is the real finding. In English that
item's key is a PARAPHRASE ("Jotham his son becomes king" against the passage's "his son
Jotham reigned in his place"); Chinese Bible register has one idiomatic rendering of the
event, so both collapsed onto 他的儿子约坦接续他作王. So an overlap rule enforced on the
English source does not hold in the language the participant reads, and this measures it
in both.

Metric: the longest CONTIGUOUS span an option shares with its window, over the option's
length. Contiguous rather than bag-of-words because recognition is what is being exploited.

  python3 evaluation/scripts/analysis/current/audit_option_overlap.py
  python3 evaluation/scripts/analysis/current/audit_option_overlap.py --json overlap.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO / "human_pilot"))

GOLD_ROOT = "tier1_bsb_unblinded_5opt_think"
HARD_DIR = REPO / "evaluation/datasets/qa/tier1_hard66_canonical"
GOLD_EN = REPO / "evaluation/datasets/qa/tier1_gold72_canonical_5opt"
WINDOWS = REPO / "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"
LETTERS = "ABCD"


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


def verse_map(text: str, metadata: dict) -> dict:
    """{chapter-qualified label: verse text}, using the importer's own parser."""
    import pilot_import as pi
    try:
        return dict(pi.parse_tier1_verses(text, metadata))
    except Exception:
        return {}


def window_text(verses: dict, labels) -> str:
    out = []
    for label in labels or []:
        label = str(label)
        if label in verses:
            out.append(verses[label])
            continue
        # hard66 stores bare verse numbers; match on the verse part
        for key, value in verses.items():
            if key.split(":")[-1] == label:
                out.append(value)
                break
    return re.sub(r"\s+", "", "".join(out))


def summarise(name: str, rows: list) -> None:
    if not rows:
        print(f"\n=== {name}: no items resolved")
        return
    key_outlier = [r for r in rows if r["key_ratio"] > r["max_distractor_ratio"]]
    blatant = [r for r in rows if r["key_ratio"] >= 0.8
               and r["key_ratio"] - r["max_distractor_ratio"] >= 0.3]
    print(f"\n=== {name}  ({len(rows)} items)")
    print(f"  mean key overlap          {sum(r['key_ratio'] for r in rows)/len(rows):.2f}")
    print(f"  mean max-distractor       {sum(r['max_distractor_ratio'] for r in rows)/len(rows):.2f}")
    print(f"  key is the highest option {len(key_outlier)} ({len(key_outlier)/len(rows)*100:.0f}%)")
    print(f"  key >=80% AND >=30pp above every distractor: {len(blatant)}"
          f" ({len(blatant)/len(rows)*100:.0f}%)  <- answerable by recognition")
    for r in sorted(blatant, key=lambda r: -(r["key_ratio"] - r["max_distractor_ratio"]))[:12]:
        extra = ""
        if r.get("en_key_ratio") is not None:
            extra = f"   EN key {r['en_key_ratio']:.2f} -> ZH {r['key_ratio']:.2f}"
        print(f"    {r['item']:22s} key {r['key_ratio']:.2f} vs best distractor "
              f"{r['max_distractor_ratio']:.2f}{extra}")
        print(f"        key: {r['key_text']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outputs", type=Path, default=Path(os.path.expanduser(
        "~/mnt/eten-research-outputs/evaluation/outputs")))
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    import pilot_import as pi
    metadata = {m["id"]: m for m in pi.load_tier1_metadata(REPO / "evaluation")}
    windows = {w["content_id"]: w["window"]
               for w in json.loads(WINDOWS.read_text(encoding="utf-8"))["windows"]}

    zh_verses, en_verses = {}, {}
    for passage_id, meta in metadata.items():
        base = args.outputs / GOLD_ROOT / passage_id / "_base" / "llm_prompt_high"
        for store, name in ((zh_verses, "passage_target.txt"),
                            (en_verses, "passage_source_decanonicalized.txt")):
            path = base / name
            if path.exists():
                store[passage_id] = verse_map(path.read_text(encoding="utf-8"), meta)

    gold, hard = [], []

    # ---- gold72: served Chinese options, plus the English source for comparison
    en_options = {}
    for path in sorted(GOLD_EN.glob("t1_*_all_formats.json")):
        for record in json.loads(path.read_text(encoding="utf-8")):
            en_options[f"{record.get('passage_id')}:{record.get('id')}"] = record
    for passage_id in sorted(metadata):
        clean = args.outputs / GOLD_ROOT / passage_id / "omission" / "0%"
        path = next((clean / n for n in ("qa_target_decanonicalized.json", "qa_target.json")
                     if (clean / n).exists()), None)
        if path is None:
            continue
        for record in json.loads(path.read_text(encoding="utf-8")):
            if record.get("q_type") != "mcq":
                continue
            item = re.sub(r"-(open|mcq)$", "", str(record.get("passage_id") or "")).replace("uw-", "")
            options = record.get("A") or {}
            correct = str(record.get("correct") or "A").strip()[:1]
            if correct not in options:
                continue
            window = window_text(zh_verses.get(passage_id, {}), windows.get(item))
            if not window:
                continue
            key_ratio = ratio(options[correct], window)
            others = [ratio(v, window) for k, v in options.items()
                      if k in LETTERS and k != correct]
            row = {"item": item, "key_text": options[correct], "key_ratio": key_ratio,
                   "max_distractor_ratio": max(others) if others else 0.0}
            source = en_options.get(item)
            en_window = window_text(en_verses.get(passage_id, {}), windows.get(item))
            if source and en_window:
                en_opts = ((source.get("mcq") or {}).get("mcq_options") or [])
                index = LETTERS.find(correct)
                if 0 <= index < len(en_opts):
                    row["en_key_ratio"] = ratio(en_opts[index], en_window.lower())
            gold.append(row)

    # ---- hard66: Chinese options and window verses come from the canonical QA itself
    for path in sorted(HARD_DIR.glob("t1_*.json")):
        passage_id = path.stem
        for record in json.loads(path.read_text(encoding="utf-8")):
            if record.get("q_type") != "mcq":
                continue
            options = record.get("A") or {}
            if not isinstance(options, dict):
                continue
            correct = str(record.get("correct") or "").strip()[:1]
            if correct not in options:
                continue
            window = window_text(zh_verses.get(passage_id, {}), record.get("window_verses"))
            if not window:
                continue
            others = [ratio(v, window) for k, v in options.items()
                      if k in LETTERS and k != correct]
            hard.append({"item": str(record.get("passage_id") or ""),
                         "key_text": options[correct],
                         "key_ratio": ratio(options[correct], window),
                         "max_distractor_ratio": max(others) if others else 0.0})

    summarise("gold72 (served Chinese)", gold)
    summarise("hard66 (canonical Chinese)", hard)
    drift = [r for r in gold if r.get("en_key_ratio") is not None
             and r["key_ratio"] - r["en_key_ratio"] >= 0.3]
    print(f"\n=== translation-induced: key overlap >=30pp higher in Chinese than English"
          f"  ({len(drift)} items)")
    for r in sorted(drift, key=lambda r: -(r["key_ratio"] - r["en_key_ratio"]))[:12]:
        print(f"  {r['item']:22s} EN {r['en_key_ratio']:.2f} -> ZH {r['key_ratio']:.2f}   {r['key_text']}")
    if args.json:
        args.json.write_text(json.dumps({"gold72": gold, "hard66": hard},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
