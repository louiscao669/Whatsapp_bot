#!/usr/bin/env python3
"""Fix the pseudonym gap in OPEN scoring: the expected answers use canonical English names
(John, Mary, ...) while everything the respondent reads/writes uses the pseudonyms (米珥, 芮茉).
For NAME-answer items the judge can't map an arbitrary pseudonym to the canonical name, so it
under-scores (e.g. 174339 capped at 0.5).

This walks every open item, rewrites the expected answer's canonical names to the pseudonyms
(EN2PS, derived from the datasets/pseudonym_remap files), and RE-JUDGES only the items whose
expected actually changed -- with the same window context and the same gpt-4o-mini judge.
MCQ and the unaffected (fact-answer) opens are left untouched. Updates llm_score +
open_llm_score_mean in scores_target_window3_v2.json in place.

  set -a; source .env; set +a
  python evaluation/scripts/pseudonymize_expected_rejudge.py --judge-provider openai --judge-model gpt-4o-mini
"""
from __future__ import annotations
import argparse, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from regen_mcq_tier01 import (build_client, judge_open, randomized_three_verse_window,
                              item_stem, pick, CONDITIONS, EXCLUDED_OPEN_STEMS)

# canonical English name -> pseudonym (consistent across chapters; from the remap files)
EN2PS = {"Theophilus": "珈恒", "Zechariah": "珂温", "Elizabeth": "哈丽", "John": "米珥",
         "Mary": "芮茉", "Joseph": "米恒", "Jesus": "玛伦", "Gabriel": "维萨", "Israel": "泰隆",
         "Abraham": "珈昂", "Jacob": "维罗", "David": "芮谷", "Jairus": "黛恩",
         "Simon": "亚磐", "Peter": "亚磐", "Levi": "芮斯"}
_PAT = re.compile(r"\b(" + "|".join(sorted(EN2PS, key=len, reverse=True)) + r")\b")


def pseudonymize(expected: str) -> str:
    return _PAT.sub(lambda m: EN2PS[m.group(1)], expected or "")


def run(args):
    root = Path(args.root)
    active_stems = {item_stem(i) for i in
                    json.loads((root.parent / "mcq_rewrites.json").read_text(encoding="utf-8"))}
    judge = build_client(args.judge_provider)

    def do_cell(model_dir, ch, cond):
        src = root / f"luke{ch}" / args.qa_model_dir / cond
        qf = pick(src, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
        pf = pick(src, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt")
        sp = root / f"luke{ch}" / model_dir / cond / "scores_target_window3_v2.json"
        if not (qf and pf and sp.exists()):
            return 0
        passage = pf.read_text(encoding="utf-8")
        recs = {r["passage_id"]: r for r in json.loads(qf.read_text(encoding="utf-8"))}
        data = json.loads(sp.read_text(encoding="utf-8"))
        changed = 0
        for it in data.get("items", []):
            if it.get("q_type") == "mcq" or item_stem(it["id"]) in EXCLUDED_OPEN_STEMS:
                continue
            rec = recs.get(it["id"])
            if not rec:
                continue
            expected = str(rec.get("A") or "")
            ps = pseudonymize(expected)
            if ps == expected:          # no canonical name -> untouched
                continue
            ctx = randomized_three_verse_window(passage, rec)
            it["llm_score"] = judge_open(judge, args.judge_model, rec["Q"], ps,
                                         it.get("generated_answer", ""), ctx)
            changed += 1
        if changed:
            opens = [i for i in data["items"] if i.get("q_type") != "mcq"]
            data.setdefault("summary", {})["open_llm_score_mean"] = (
                sum(i["llm_score"] for i in opens) / len(opens) if opens else 0.0)
            sp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return changed

    models = args.models.split(",") if args.models else ["1.7b", "1.5b", "llama 1b"]
    total = 0
    jobs = [(m, ch, c) for m in models for ch in args.chapters for c in CONDITIONS]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(do_cell, m, ch, c): (m, ch, c) for m, ch, c in jobs}
        for f in as_completed(futs):
            total += f.result()
    print(f"re-judged {total} open items (only those whose expected answer contained a "
          f"pseudonymizable name). MCQ and fact-answer opens untouched.")
    print("Next: re-run adapt_scores_to_llama.py to propagate, then --report-only.")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--qa-model-dir", default="1.7b")
    ap.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    ap.add_argument("--models", help="comma dir list; default all 3 tiers")
    ap.add_argument("--judge-provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--judge-model", default="gpt-4o-mini")
    ap.add_argument("--workers", type=int, default=8)
    return ap.parse_args()


if __name__ == "__main__":
    run(parse_args())
