#!/usr/bin/env python3
"""Run rebalance_mcq_options on a handful of known items and print what happened.

A quick effectiveness check before a full run: each sample is an item whose problem we
already know (from the 2026-09-30 manual review), so the output can be judged against
an expectation. Uses the PRE-redraft options (the .bak_overlap_2026-09-30 backups) where
they exist, so the stage faces the same problem the manual redraft did, and prints the
manual redraft alongside for comparison. Dry run: no QA file is written.

    python -m evaluation.scripts.pipeline.rebalance_smoke_test \\
        --tier1-root ~/whatsapp-bot/eten-research-outputs/evaluation/outputs/tier1_bsb_unblinded_5opt_think
    # no Astra access?   --judge-model gpt-6.1-sol
    # offline plumbing check (fake model):   --stub

Writes the full transcript (prompts, raw model replies, verdicts) to
rebalance_cmp/smoke_<timestamp>.json.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.agents.generate_chinese_answers import load_verse_windows  # noqa: E402
from evaluation.scripts.pipeline import rebalance_mcq_options as rb  # noqa: E402

HARD_DIR = REPO_ROOT / "evaluation/datasets/qa/tier1_hard66_canonical"
WINDOWS = REPO_ROOT / "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"
BACKUP = ".bak_overlap_2026-09-30"

# (set, passage, item passage_id, what a good outcome looks like)
SAMPLES = [
    ("gold72", "t1_2kgs6_7", "uw-t1_2kgs6_7:kenl-mcq",
     "key 关门挡住他 verbatim vs distractors at 0.00 -> rebalanced with in-window actions"),
    ("gold72", "t1_acts20", "uw-t1_acts20:jxkk#2-mcq",
     "gap +0.66, missed by the manual audit -> rebalanced"),
    ("gold72", "t1_1kgs13", "uw-t1_1kgs13:sy7m-mcq",
     "window has only one 'word' -> partial or needs_review, no near-synonym of 耶和华的话"),
    ("gold72", "t1_judg17_18", "uw-t1_judg17_18:h3z1-mcq",
     "old C 来自伯利恒的利未人 IS Jonathan -> must not survive; must not be re-proposed"),
    ("hard66", "t1_2kgs6_7", "uw-t1_2kgs6_7:5bba-mcq",
     "only full in-window alternative 以色列王 is near-correct -> partial / needs_review"),
    ("hard66", "t1_2chr26", "uw-t1_2chr26:9860-mcq",
     "timing item; 约坦管理王宫 (regency) vs 接续他作王 -> validator decides"),
    ("hard66", "t1_2chr26", "uw-t1_2chr26:723e-mcq",
     "A 哈拿尼雅 reads as commander (在…指挥下) -> judged non-incorrect and replaced"),
    ("hard66", "t1_acts23", "uw-t1_acts23:5613-mcq",
     "B 保罗被带到公会 is also awaited by the ambush -> judged non-incorrect and replaced"),
]


def load_item(tier1_root: Path, set_name: str, pid: str, item_id: str):
    if set_name == "hard66":
        current = HARD_DIR / f"{pid}.json"
    else:
        current = tier1_root / pid / "omission/0%" / "qa_target_decanonicalized.json"
    source = current.with_name(current.name + BACKUP)
    source = source if source.exists() else current
    pick = lambda path: next((r for r in json.loads(path.read_text(encoding="utf-8"))
                              if r.get("passage_id") == item_id and r.get("q_type") == "mcq"), None)
    return pick(source), pick(current), source.name


def stub_llm():
    state = {}

    def call(role, system, user):
        p = json.loads(user)
        if role == "generate":
            clauses = [c for c in re.split(r"[，。：；“”‘’！？\s\d]+", p["excerpt"]) if 2 <= len(c) <= 12]
            state["key_text"] = p["correct_answer"]
            return {"answer_type": "", "candidates": [{"text": c, "source": "stub", "why_wrong": "stub",
                                                       "why_tempting": "stub"} for c in clauses[:8]]}
        if role == "keygen":
            return {"rewordings": [{"text": "stub改写" + p["correct_answer"][:2], "why_same": "stub"}]}
        if role == "keycheck":
            return {"rewordings": [{"id": rid, "verdict": "same", "natural": True} for rid in p["rewordings"]]}
        if role == "screen":
            return {"candidates": [{"id": cid, "label": "correct" if t == state.get("key_text") else "incorrect",
                                    "natural": True, "plausibility": 4} for cid, t in p["candidates"].items()]}
        if role == "factcheck":
            state["key_text"] = p["correct_answer"]
            return {"options": [{"letter": l, "verdict": "ok"} for l in p["wrong_options"]]}
        return {"options": [{"letter": l, "label": "correct" if t == state.get("key_text") else "incorrect",
                             "natural": True, "plausibility": 4} for l, t in p["options"].items()]}
    call.state = state
    return call


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier1-root", type=Path, required=True)
    ap.add_argument("--generator-model", default=rb.DEFAULT_GENERATOR_MODEL)
    ap.add_argument("--judge-model", default=rb.DEFAULT_JUDGE_MODEL)
    ap.add_argument("--effort", default=rb.DEFAULT_EFFORT)
    ap.add_argument("--only", nargs="+", help="substring filter on item ids")
    ap.add_argument("--stub", action="store_true", help="fake model, no API calls")
    ap.add_argument("--out-dir", type=Path, default=Path("rebalance_cmp"))
    args = ap.parse_args()

    root = args.tier1_root.expanduser()
    windows = load_verse_windows(WINDOWS)
    base = stub_llm() if args.stub else rb.openai_llm(args.generator_model, args.judge_model,
                                                       args.effort or None)
    transcript = []

    def logged(role, system, user):
        t0 = time.time()
        reply = base(role, system, user)
        transcript[-1]["calls"].append({"role": role, "seconds": round(time.time() - t0, 1),
                                        "user": json.loads(user), "reply": reply})
        return reply

    counts = {}
    for set_name, pid, item_id, expect in SAMPLES:
        if args.only and not any(s in item_id for s in args.only):
            continue
        record, current, source_name = load_item(root, set_name, pid, item_id)
        if record is None:
            print(f"\n## {item_id}: not found")
            continue
        passage_dir = root / pid / "omission/0%"
        passage = next(passage_dir / n for n in ("passage_target_decanonicalized.txt", "passage_target.txt")
                       if (passage_dir / n).exists())
        ctx = rb.PassageContext(passage.read_text(encoding="utf-8"), record.get("passage_reference", ""),
                                windows)
        if args.stub:
            base.state["key_text"] = rb.content_options(record).get(rb.key_letter(record))
        transcript.append({"item": item_id, "set": set_name, "source": source_name,
                           "expect": expect, "calls": []})
        result = rb.process_item(record, ctx, logged)
        counts[result.status] = counts.get(result.status, 0) + 1
        transcript[-1].update(status=result.status, reason=result.reason, judge=result.judge,
                              natural=result.natural, facts=result.facts,
                              plausibility=result.plausibility, proposal=result.proposal,
                              old=result.old_options, new=result.new_options,
                              before=result.before, after=result.after, notes=result.notes)

        key = rb.key_letter(record)
        print(f"\n## {set_name} {item_id}   [{result.status}: {result.reason}]")
        print(f"   expect: {expect}")
        print(f"   Q: {record.get('Q')}")
        print(f"   window: {ctx.display_window_for(record)[:220]}")
        for l in rb.CONTENT_LETTERS:
            if l not in result.old_options:
                continue
            old = f"{result.old_options[l]} ({result.before['ratios'][l]:.2f})" if result.before else result.old_options[l]
            new = ""
            if result.new_options and result.after:
                new = f"{result.new_options[l]} ({result.after['ratios'][l]:.2f})"
                new = "(same)" if result.new_options[l] == result.old_options[l] else new
            mark = "*" if l == key else " "
            flags = [result.judge.get(l, "")]
            if result.natural and not result.natural.get(l, True):
                flags.append("UNNATURAL")
            if l != key and l in result.plausibility:
                flags.append(f"plaus={result.plausibility[l]}")
            if result.facts.get(l, "ok") != "ok":
                flags.append(result.facts[l].upper())
            print(f"   {l}{mark} {old:<34} -> {new:<34} {' '.join(f for f in flags if f)}")
        if result.before:
            gap_after = f"{result.after['gap']:+.2f}" if result.after else "-"
            lead2_after = f"{result.after['weakest_gap']:+.2f}" if result.after else "-"
            print(f"   gap {result.before['gap']:+.2f} -> {gap_after}   "
                  f"weakest-distractor gap {result.before['weakest_gap']:+.2f} -> {lead2_after}")
        if current and current.get("A") != record.get("A"):
            print("   manual redraft: " + " | ".join(f"{l}:{current['A'][l]}" for l in rb.CONTENT_LETTERS if l in current["A"]))
        gens = [c for c in transcript[-1]["calls"] if c["role"] == "generate"]
        if gens:
            cands = [c.get("text") for g in gens for c in (g["reply"].get("candidates") or [])]
            kinds = [c.get("kind", "?") for g in gens for c in (g["reply"].get("candidates") or [])]
            verdicts = {}
            for c in transcript[-1]["calls"]:
                if c["role"] == "screen":
                    texts = c["user"]["candidates"]
                    for e in c["reply"].get("candidates", []):
                        t = texts.get(e.get("id"))
                        if t:
                            ok = "" if e.get("natural", True) else ",unnatural"
                            verdicts[t] = f"{e.get('label', '?')[:3]},p{e.get('plausibility', '?')}{ok}"
            print(f"   candidates ({len(cands)}), screened as label,plausibility:")
            for t, k in zip(cands, kinds):
                print(f"      {t} [{k}] {verdicts.get(t, 'dropped before screening')}")
            first = gens[0]["reply"]
            if first.get("answer_type") or first.get("question_assumes"):
                print(f"   answer type: {first.get('answer_type')} | question assumes: {first.get('question_assumes')}")
        for c in transcript[-1]["calls"]:
            if c["role"] == "factcheck":
                bad = [(o.get("letter"), o.get("verdict"), o.get("reason")) for o in c["reply"].get("options", [])
                       if o.get("verdict") not in (None, "ok")]
                if bad:
                    print(f"   fact check: {bad}")
        for n in result.notes.items():
            print(f"   note {n[0]}: {n[1]}")
        if result.proposal:
            pr = result.proposal
            print(f"   KEY REWORDING PROPOSAL (report only) [{pr.get('status')}]: "
                  f"{pr.get('original_key', '')} -> {pr.get('key', '')}"
                  + (f" ({pr['key_overlap']:.2f})" if pr.get("key_overlap") is not None else "")
                  + (f" fluency {pr['key_fluency']}" if pr.get("key_fluency") is not None else ""))
            if pr.get("candidates"):
                print(f"      rewordings: {' / '.join(pr['candidates'])}   valid: {' / '.join(pr.get('valid', []))}")
            if pr.get("options"):
                print("      options: " + " | ".join(f"{l}:{v}" for l, v in sorted(pr["options"].items()))
                      + f"   gap {pr.get('gap')}, weakest {pr.get('weakest_gap')}")
            if pr.get("note"):
                print(f"      note: {pr['note']}")

    print("\nsummary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"smoke_{_dt.datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"generator": args.generator_model, "judge": args.judge_model,
                               "effort": args.effort, "stub": args.stub, "items": transcript},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"transcript: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
