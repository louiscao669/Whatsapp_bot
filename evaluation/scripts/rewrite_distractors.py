#!/usr/bin/env python3
"""Rewrite MCQ distractors on the DELIVERED Chinese pilot items, then validate.

Problem it fixes: the pilot MCQs are answerable without the passage (register-obvious
options / weak distractors) -> defects can't move accuracy. This regenerates each item's
options to be register-congruent, parallel, and passage-dependent, keyed to the source
verse, WITHOUT knowing anything about the injected translation defects.

Quality bar (encoded in the generation prompt + enforced by two gates):
  * Correct answer: entailed by the passage, UNIQUELY correct, and a PLAIN-LANGUAGE
    paraphrase (no verbatim overlap with the passage; but never a synonym that needs Bible
    knowledge to map -- e.g. 圣灵 stays 圣灵, shared across a near-miss instead).
  * Distractors: register-congruent, parallel in form/length, each NOT entailed by the
    passage, no stem-echo, >=1 near-miss.
  * Gate 1 (faithfulness/uniqueness): LLM entailment -- answer entailed, every distractor
    not entailed by the chapter passage.
  * Gate 2 (guessability): closed-book accuracy (question+options only, religious-text
    system prompt, K samples) must fall to <= --max-prior, while the clean open-book answer
    stays correct.

Few-shot: seeded by the LOCKED Luke 3 gold set (embedded below).
Operates on delivered Chinese only: reads/writes evaluation/outputs/luke{ch}/<model-dir>/
omission/0%/qa_target_pseudonymized.json. Writes a *proposal* file by default (never
overwrites in place unless --in-place); flags any item that fails a gate for human review.

Usage:
  set -a; source .env; set +a               # or --provider ollama
  python evaluation/scripts/rewrite_distractors.py --chapters 1 2 4 5 6 7 8 \
      --provider openai --model gpt-4.1-mini --k 5 --max-prior 0.4
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

LETTER_RE = re.compile(r"[A-Da-d]")

# --- LOCKED Luke 3 gold few-shot (see Bible Translation/LUKE3_MCQ_GOLD_2026-07-24.md) ---
FEWSHOT = """\
### Example 1 (deity paraphrase — toward the PLAINER word, not a harder synonym)
Verse (3:4): 预备主的道路，修直他的路。
Question: 米珥为谁预备道路？
Correct meaning to keep: 主 (the Lord / God)
Rewritten options:
A. 为将要登基的君王预备道路
B. 为上帝来临预备道路   [correct]
C. 为应许的先知预备道路
D. 为归回的百姓预备道路
Why: 主→上帝 (上帝 is the plainer word AND the only God-word not verbatim in the passage);
all four share "预备道路" so the stem word is neutralized; king/prophet/people are register-
plausible but not stated; A/C are near-misses.

### Example 2 (fixed term with no plain synonym — DO NOT paraphrase it; share it instead)
Verse (3:16): 他要用圣灵和火给你们施洗。
Question: 米珥说那位更大的会用什么施洗？
Correct meaning to keep: 圣灵与火
Rewritten options:
A. 圣灵与活水
B. 圣灵与烈火   [correct]
C. 烈火与灰烬
D. 清水与香膏
Why: 圣灵 is kept (paraphrasing it to 神的灵 would need Bible knowledge to map). 圣灵 appears
in A+B and 火 in B+C, so no single word-match solves it — the reader must grasp it is
specifically Spirit AND fire. A is a near-miss (water).

### Example 3 (near-miss from a real motif)
Verse (3:9): 凡不结果子的树就要砍下来，丢进火里。
Question: 不结好果子的树会遭遇什么？
Correct meaning to keep: 砍倒并扔进火里
Rewritten options:
A. 被移栽到别处
B. 被留待来年再结果
C. 被伐倒焚烧   [correct]
D. 被修剪后重新栽种
Why: answer paraphrased to plain 伐倒焚烧; B is a near-miss (the "one more year" mercy);
all are plausible fates of a tree, only C is stated.
"""

GEN_SYSTEM = """You rewrite the four options of a Chinese biblical reading-comprehension MCQ.
Goal: make the item answerable ONLY by reading the given passage — not by register, priors,
or string-matching — while keeping the SAME correct fact.

Rules:
1. Keep the correct fact's meaning. Rewrite the correct option as a PLAIN-LANGUAGE paraphrase
   so it does not copy a distinctive string from the passage. BUT never replace a fixed term
   (e.g. 圣灵, 施洗, 鸽子) with a synonym that needs Bible knowledge to recognize as equal —
   for such terms keep the term and instead repeat it in a distractor so discrimination falls
   on a plain in-passage detail. Paraphrase only toward SIMPLER wording a reader with no Bible
   background would understand.
2. Write 3 distractors that are: register-congruent (all four equally plausible in a biblical
   frame — no absurd war/trade/art options), parallel in grammar/length/specificity (the
   answer must not stand out), each FALSE for this passage (not stated by it), and include at
   least one near-miss drawn from a real biblical motif.
3. No stem-echo: do not let the correct option uniquely repeat a word from the question. If a
   cue word is unavoidable, put it in every option.
4. Output STRICT JSON only: {"A":"...","B":"...","C":"...","D":"...","correct":"<letter>"}.
   Randomize which letter is correct."""


def build_client(provider):
    from openai import OpenAI
    if provider == "ollama":
        return OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                      api_key="ollama")
    return OpenAI()


def chat(client, model, messages, temperature=0.0, max_tokens=400):
    r = client.chat.completions.create(model=model, temperature=temperature,
                                       max_tokens=max_tokens, messages=messages)
    return (r.choices[0].message.content or "").strip()


def options_block(o):
    return "\n".join(f"{k}. {o[k]}" for k in ("A", "B", "C", "D") if o.get(k))


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def pick(d, *names):
    for n in names:
        if (d / n).exists():
            return d / n
    return None


# ---------------------------------------------------------------- generation + gates
def generate(client, model, question, correct_fact, passage, ref):
    user = (f"{FEWSHOT}\n\n### Now rewrite this item\n"
            f"Passage (whole chapter, pseudonymized):\n{passage}\n\n"
            f"This item's fact is from verse {ref}.\n"
            f"Question: {question}\n"
            f"Correct fact to keep (paraphrase to plain language): {correct_fact}\n"
            f"Return STRICT JSON only.")
    out = chat(client, model, [{"role": "system", "content": GEN_SYSTEM},
                               {"role": "user", "content": user}], temperature=0.7)
    return parse_json(out)


def entails(client, model, passage, hypothesis):
    """True iff the passage entails the hypothesis (semantic, not string)."""
    msg = [{"role": "system", "content":
            "Decide if the PASSAGE entails the STATEMENT (is it true and supported by the "
            "passage?). Judge meaning, not wording. Answer strictly 'yes' or 'no'."},
           {"role": "user", "content": f"PASSAGE:\n{passage}\n\nSTATEMENT: {hypothesis}\n\nyes or no?"}]
    return chat(client, model, msg, 0.0, 4).strip().lower().startswith("y")


def ask_letter(client, model, question, opts, passage, temperature, system):
    header = f"文章：\n{passage}\n\n" if passage else ""
    instr = "请只根据下面的文章作答。" if passage else "没有提供文章。请凭已有知识猜最可能的答案。"
    prompt = (f"{header}这是一道单项选择题。{instr}\n\n问题：{question}\n选项：\n"
              f"{options_block(opts)}\n\n只输出一个字母：A、B、C 或 D。")
    m = [{"role": "system", "content": system}] if system else []
    m.append({"role": "user", "content": prompt})
    t = chat(client, model, m, temperature, 8)
    mt = LETTER_RE.search(t)
    return mt.group(0).upper() if mt else "?"


def validate(client, model, gclient, gmodel, item, question, passage, k, max_prior, system):
    opts = {L: item[L] for L in "ABCD"}
    correct = item["correct"]
    # Gate 1: faithfulness / uniqueness (strong judge model)
    ans_ok = entails(client, model, passage, opts[correct])
    distractor_entailed = [L for L in "ABCD" if L != correct and entails(client, model, passage, opts[L])]
    gate1 = ans_ok and not distractor_entailed
    # Gate 2: guessability (WEAK proxy model = the human-like guesser)
    guesses = [ask_letter(gclient, gmodel, question, opts, "", 1.0, system) for _ in range(k)]
    prior = sum(g == correct for g in guesses) / max(1, k)
    open_ok = ask_letter(gclient, gmodel, question, opts, passage, 0.0, system) == correct
    gate2 = prior <= max_prior and open_ok
    return {"answer_entailed": ans_ok, "distractors_entailed": distractor_entailed,
            "gate1_faithful": gate1, "prior_answerability": prior,
            "open_book_correct": open_ok, "gate2_passgame": gate2,
            "passed": gate1 and gate2}


# ------------------------------------------------------------------------------ main
def run(args):
    client = build_client(args.provider)                       # generation + entailment (strong)
    gclient = build_client(args.guess_provider or args.provider)  # guessability (weak proxy)
    gmodel = args.guess_model or args.model
    system = None if args.no_domain_hint else args.domain_hint
    root = Path(args.root)
    report = []
    for ch in args.chapters:
        d = root / f"luke{ch}" / args.model_dir / "omission" / "0%"
        qf = pick(d, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
        pf = pick(d, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt")
        if not qf or not pf:
            print(f"[warn] missing files for luke{ch}", file=sys.stderr); continue
        passage = pf.read_text(encoding="utf-8")
        data = json.loads(qf.read_text(encoding="utf-8"))
        for rec in data:
            if rec.get("q_type") != "mcq":
                continue
            iid, ref = rec.get("passage_id"), rec.get("passage_reference")
            correct_fact = (rec.get("A") or {}).get(rec.get("correct"), "")
            best, result = None, None
            for attempt in range(1, args.max_tries + 1):
                try:
                    cand = generate(client, args.model, rec["Q"], correct_fact, passage, ref)
                    res = validate(client, args.model, gclient, gmodel, cand, rec["Q"], passage,
                                   args.k, args.max_prior, system)
                except Exception as exc:
                    print(f"  [luke{ch} {iid}] attempt {attempt} error: {exc}", file=sys.stderr)
                    continue
                best, result = cand, res
                if res["passed"]:
                    break
            if result and result["passed"]:
                rec["A"] = {L: best[L] for L in "ABCD"}
                rec["correct"] = best["correct"]
                rec["_rewritten"] = True
            report.append({"chapter": ch, "id": iid, "ref": ref,
                           "passed": bool(result and result["passed"]),
                           **(result or {}), "options": best})
            tag = "OK " if (result and result["passed"]) else "FLAG"
            r = result or {}
            print(f"[{tag}] luke{ch} {iid} prior={round(r.get('prior_answerability', 0), 2)} "
                  f"ans_entailed={r.get('answer_entailed')} "
                  f"distractors_entailed={r.get('distractors_entailed')} "
                  f"open_ok={r.get('open_book_correct')}")
        # write proposal (or in-place)
        out_qf = qf if args.in_place else qf.with_suffix(".rewritten.json")
        out_qf.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  wrote {out_qf}")

    outdir = Path(args.out_dir); outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "rewrite_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    n = len(report); ok = sum(r["passed"] for r in report)
    print(f"\n=== {ok}/{n} items passed both gates; {n-ok} flagged for review ===")
    print(f"report: {outdir/'rewrite_report.json'}")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--chapters", type=int, nargs="+", default=[1, 2, 4, 5, 6, 7, 8])
    ap.add_argument("--model-dir", default="1.7b")
    ap.add_argument("--provider", default="openai", choices=["openai", "ollama"],
                    help="generation + entailment backend (use a STRONG model)")
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--guess-provider", choices=["openai", "ollama"],
                    help="guessability-gate backend; use the WEAK respondent proxy "
                         "(e.g. --guess-provider ollama --guess-model qwen2.5:1.5b). "
                         "Defaults to --provider/--model, which is usually too strong to measure guessing.")
    ap.add_argument("--guess-model")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--max-prior", type=float, default=0.4,
                    help="max closed-book accuracy to accept (<=0.4 ~ near chance)")
    ap.add_argument("--max-tries", type=int, default=4)
    ap.add_argument("--domain-hint", default="你正在回答关于一段宗教经文（圣经）的阅读理解选择题。")
    ap.add_argument("--no-domain-hint", action="store_true")
    ap.add_argument("--in-place", action="store_true",
                    help="overwrite qa_target_pseudonymized.json (default: write .rewritten.json)")
    ap.add_argument("--out-dir", default="evaluation/outputs/reports/rewrite_distractors")
    return ap.parse_args()


if __name__ == "__main__":
    run(parse_args())
