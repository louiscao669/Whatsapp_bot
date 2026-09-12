#!/usr/bin/env python3
"""Rewrite gold72 distractors on the ENGLISH SOURCE, before translation.

Why English source rather than the Chinese cells: the fix then survives
re-translation, propagates to every model and both naming arms through the normal
translate step, and carries into the human pilot. Rewriting the Chinese in output
cells would have to be redone per arm and (before SHARE_QA) per model.

Measured problem this addresses (gold72, ~159 observations/item):
    distractors never selected by ANY model in ANY cell : 86/216 (40%)
    mean EFFECTIVE options per item                     : 2.81 (design assumes 4)
    omission dz, items with 0 dead distractors          : 0.492
    omission dz, items with 2-3 dead distractors        : 0.233
Dead distractors cost 2.1x the dose sensitivity the experiment exists to measure.

Reuses the prompt design, relevance framing, length matching and deterministic
shuffle from rewrite_distractors.py (16/16 self-tests) and supplies English inputs:
  - QA        evaluation/datasets/qa/tier1_gold72_canonical_5opt
  - windows   QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json
  - passages  evaluation/datasets/passages/tier1_bsb

Option E (the abstention) is held out of the rewrite AND out of the shuffle, then
re-appended last, so it never becomes the keyed answer and never moves position.

Usage:
  set -a; source .env; set +a
  python3 evaluation/scripts/mcq/preparation/rewrite_distractors_gold72_en.py --self-test
  python3 evaluation/scripts/mcq/preparation/rewrite_distractors_gold72_en.py \
      --model gpt-5.6-terra --relevance-model gpt-5.6-sol \
      --answer-provider ollama --answer-model qwen2.5:1.5b
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))
import evaluation.scripts.mcq.preparation.rewrite_distractors as rd   # noqa: E402

LETTERS = "ABCD"
ABSTAIN_EN = "I can't tell from this passage"
PASSAGE_FILE = {
    "t1_1kgs13":"1kgs_13_1-34","t1_2chr26":"2chr_26_1-23","t1_2kgs11":"2kgs_11_1-21",
    "t1_2kgs6_7":"2kgs_6_24-7_20","t1_2sam21":"2sam_21_15-22","t1_acts19":"acts_19_11-20",
    "t1_acts20":"acts_20_7-12","t1_acts23":"acts_23_12-35","t1_judg17_18":"judg_17_1-18_31",
    "t1_judg9":"judg_9_1-57",
}

# ---- English mode: swap the two Chinese-specific pieces of the shared module ----
def en_len(s): return len(str(s or "").split())          # words, not CJK characters
def install_english_mode():
    rd.cjk_len = en_len
    rd.REWRITE_SYSTEM_TEMPLATE = rd.REWRITE_SYSTEM_TEMPLATE.replace(
        "Chinese reading-comprehension MCQ", "English reading-comprehension MCQ")

def norm_q(q): return re.sub(r"\s+", " ", (q or "").strip().lower())
def item_question(it):
    return str((it.get("open") or {}).get("original_question") or it.get("question") or "").strip()
def win_key(pid, q, occ=0):
    return f"{pid}:{hashlib.sha1(norm_q(q).encode()).hexdigest()[:10]}#{occ}"

def parse_passage(stem, pdir):
    m = re.match(r"^[0-9]?[a-z]+_(\d+)_(\d+)-(?:(\d+)_)?(\d+)$", stem)
    c0, v0 = int(m.group(1)), int(m.group(2))
    idx, ch, prev = {}, int(m.group(1)), None
    for b in [x.strip() for x in (Path(pdir)/f"{stem}.txt").read_text(encoding="utf-8").split("\n\n") if x.strip()]:
        mm = re.match(r"^(\d+)\s+(.*)$", b, re.S); n = int(mm.group(1))
        if prev is None: v = v0
        elif n == prev + 1: v = n
        else: ch = n; v = 1
        idx[(ch, v)] = mm.group(2).strip(); prev = v
    return idx

def ask_letter_en(client, model, question, opts, context, temperature, effort=None):
    head = f"Passage:\n{context}\n\n" if context else ""
    instr = ("Answer using ONLY the passage above." if context
             else "No passage is provided. Guess the most likely answer from prior knowledge.")
    body = "\n".join(f"{L}. {opts[L]}" for L in LETTERS)
    prompt = (f"{head}This is a multiple-choice question. {instr}\n\n"
              f"Question: {question}\nOptions:\n{body}\n\nReply with one letter only: A, B, C, or D.")
    out = rd.chat(client, model, [{"role":"user","content":prompt}], temperature, 8, effort)
    m = re.search(r"[A-Da-d]", out or "")
    return m.group(0).upper() if m else "?"

def self_test():
    ok = []
    install_english_mode()
    ok.append(("English length is word-based", en_len("the man of God") == 4))
    ok.append(("prompt says English not Chinese",
               "English reading-comprehension MCQ" in rd.REWRITE_SYSTEM_TEMPLATE
               and "Chinese reading-comprehension MCQ" not in rd.REWRITE_SYSTEM_TEMPLATE))
    it = {"A":"w","B":"x","C":"y","D":"z","correct":"C"}
    sh = rd.randomize_choices(dict(it), "seed-1")
    ok.append(("shuffle preserves the keyed text", sh[sh["correct"]] == "y"))
    ok.append(("shuffle is deterministic", rd.randomize_choices(dict(it), "seed-1") == sh))
    ok.append(("shuffle touches only 4 options", set(sh) == set("ABCD") | {"correct"}))
    idx = {("9",1):"x"}
    ok.append(("window key is content-addressed",
               win_key("p","Who ran?") == win_key("p"," who  RAN? ")))
    ok.append(("abstention never enters the shuffle", ABSTAIN_EN not in sh.values()))
    ok.append(("all 10 passages mapped", len(PASSAGE_FILE) == 10))
    for name, cond in ok: print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    n = sum(1 for _, c in ok if c)
    print(f"\n{n}/{len(ok)} self-tests passed")
    return 0 if n == len(ok) else 1

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qa-dir", default="evaluation/datasets/qa/tier1_gold72_canonical_5opt")
    ap.add_argument("--out-dir", default="evaluation/datasets/qa/tier1_gold72_canonical_5opt_rw")
    ap.add_argument("--passage-dir", default="evaluation/datasets/passages/tier1_bsb")
    ap.add_argument("--windows", default="QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json")
    ap.add_argument("--provider", default="openai"); ap.add_argument("--model", default="gpt-5.6-terra")
    ap.add_argument("--rewrite-temperature", type=float, default=0.4)
    ap.add_argument("--rewrite-effort", default="medium")
    ap.add_argument("--relevance-model", default="gpt-5.6-sol")
    ap.add_argument("--relevance-effort", default="medium")
    ap.add_argument("--relevance-retries", type=int, default=1)
    ap.add_argument("--length-tolerance", type=int, default=3)
    ap.add_argument("--shuffle-seed", default="mcq-key")
    ap.add_argument("--verify", dest="verify", action="store_true", default=True)
    ap.add_argument("--no-verify", dest="verify", action="store_false")
    ap.add_argument("--answer-provider", default="ollama")
    ap.add_argument("--answer-model", default="qwen2.5:1.5b")
    ap.add_argument("--report", default="evaluation/outputs/reports/rewrite_gold72_en.json")
    ap.add_argument("--limit", type=int, default=0, help="only N items, for a cheap smoke test")
    ap.add_argument("--verify-only", action="store_true",
                    help="measure closed/open book on the INPUT QA without rewriting, to get a "
                         "before-baseline. Applies the SAME deterministic shuffle as the rewrite "
                         "path, so the comparison isolates distractor quality rather than the "
                         "key's position (a mis-aligned key can explain a closed-book number "
                         "on its own).")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return self_test()

    install_english_mode()
    # Index by content_id, matching generate_chinese_answers.load_verse_windows.
    # The "key"/"span_key" fields are build-time annotation artifacts and are NOT
    # what the pipeline looks windows up by; content_id is shared across the
    # canonical and pseudonymized arms, so one windows file serves both.
    W = json.load(open(a.windows))
    wins = {str(w.get("content_id") or "").strip(): w for w in W["windows"] if w.get("content_id")}
    client = None if a.verify_only else rd.build_client(a.provider)
    ans_client = rd.build_client(a.answer_provider) if a.verify else None
    if not a.verify_only: os.makedirs(a.out_dir, exist_ok=True)
    report, done = [], 0

    for fn in sorted(os.listdir(a.qa_dir)):
        if not fn.endswith(".json"): continue
        items = json.load(open(os.path.join(a.qa_dir, fn)))
        pid = next((x.get("passage_id") or str(x.get("content_id","")).split(":")[0])
                   for x in items if isinstance(x, dict)
                   and (x.get("passage_id") or x.get("content_id")))
        idx = parse_passage(PASSAGE_FILE[pid], a.passage_dir)
        occ = {}
        for it in items:
            mcq = it.get("mcq")
            if not mcq: continue
            cid0 = str(it.get("content_id") or "")
            if not it.get("id") and ":" in cid0: it["id"] = cid0.split(":",1)[1].split("#")[0]
            if not it.get("passage_id") and ":" in cid0: it["passage_id"] = cid0.split(":",1)[0]
            if not it.get("id") or not it.get("passage_id"):
                print(f"[skip] malformed record (no id/content_id): {sorted(it)[:6]}", file=sys.stderr)
                continue
            opts = list(mcq.get("mcq_options") or [])
            if len(opts) != 5:
                print(f"[skip] {pid}/{it['id']}: expected 5 options, got {len(opts)}", file=sys.stderr); continue
            if a.limit and done >= a.limit: break
            keyed = re.search(r"<answer>([A-E])<answer>", mcq.get("content", ""))
            if not keyed: print(f"[skip] {pid}/{it['id']}: no key", file=sys.stderr); continue
            ki = "ABCDE".index(keyed.group(1))
            q = item_question(it)
            cid = str(it.get("content_id") or f"{pid}:{it['id']}").strip()
            w = wins.get(cid) or wins.get(cid.split("#")[0])
            if not w: print(f"[skip] {pid}/{it['id']}: no window", file=sys.stderr); continue
            ch = int(str(it.get("reference", "0:0")).split(":")[0])
            window = "\n".join(f"{v} {idx.get((ch, int(str(v).split(':')[-1])), '')}"
                               for v in [int(str(x).split(':')[-1]) for x in w["window"]])
            base = {LETTERS[i]: opts[i] for i in range(4)}
            base["correct"] = LETTERS[ki] if ki < 4 else "A"
            if a.verify_only:
                new = dict(base)
            else:
                try:
                    new = rd.rewrite_distractors(client, a.model, base, q, window,
                                                 temperature=a.rewrite_temperature, effort=a.rewrite_effort)
                except Exception as exc:
                    print(f"[err ] {pid}/{it['id']}: {exc}", file=sys.stderr); new = base
            new["correct"] = base["correct"]
            sh = rd.randomize_choices(new, f"{a.shuffle_seed}:{it['id']}")
            final = [sh[L] for L in LETTERS] + [ABSTAIN_EN]
            mcq["mcq_options"] = final
            stem = mcq.get("mcq_stem") or q
            mcq["content"] = ("<question>" + stem + "\n\n"
                              + "\n".join(f"{L}. {final[i]}" for i, L in enumerate("ABCDE"))
                              + f"\n<question><answer>{sh['correct']}<answer>")
            mcq["abstention_option"] = "E"
            mcq["distractors_rewritten"] = True
            row = {"pid": pid, "id": it["id"], "key": sh["correct"],
                   "before": opts[:4], "after": [sh[L] for L in LETTERS]}
            if a.verify and ans_client:
                try:
                    cb = ask_letter_en(ans_client, a.answer_model, q, sh, "", 0.0)
                    ob = ask_letter_en(ans_client, a.answer_model, q, sh, window, 0.0)
                    row["closed_book_correct"] = int(cb == sh["correct"])
                    row["open_book_correct"] = int(ob == sh["correct"])
                except Exception as exc:
                    print(f"[warn] verify failed {pid}/{it['id']}: {exc}", file=sys.stderr)
            report.append(row); done += 1
            print(f"[ok  ] {pid}/{it['id']} key={sh['correct']}"
                  + (f" closed={row.get('closed_book_correct')} open={row.get('open_book_correct')}"
                     if a.verify else ""))
        if not a.verify_only:
            json.dump(items, open(os.path.join(a.out_dir, fn), "w"), ensure_ascii=False, indent=2)

    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    json.dump(report, open(a.report, "w"), ensure_ascii=False, indent=2)
    cb = [r["closed_book_correct"] for r in report if "closed_book_correct" in r]
    ob = [r["open_book_correct"] for r in report if "open_book_correct" in r]
    print(f"\n{'measured' if a.verify_only else 'rewrote'} {done} items"
          + ("" if a.verify_only else f" -> {a.out_dir}"))
    if cb:
        print(f"  closed-book accuracy : {sum(cb)/len(cb):.3f}   (want near 0.25 -- distractors work)")
        print(f"  open-book accuracy   : {sum(ob)/len(ob):.3f}   (want high -- item still answerable)")
        print(f"  discrimination       : {sum(ob)/len(ob) - sum(cb)/len(cb):+.3f}")
    print(f"  report: {a.report}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
