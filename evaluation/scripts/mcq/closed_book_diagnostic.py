#!/usr/bin/env python3
"""Closed-book prior-answerability / dynamic-range diagnostic for pilot MCQ items.

Question: can the MCQs be answered WITHOUT the passage (from register cues / priors /
weak distractors)? If yes, translation defects can't move accuracy -> the item is
"dead weight" and the dose-response signal is diluted.

For each MCQ item (pilot delivery form -- qa_target_pseudonymized.json, Chinese,
decanonicalized) this computes:

  * prior_answerability : closed-book accuracy = fraction of K sampled guesses that
    are correct when the model sees ONLY the question + 4 options (NO passage).
    Sampled at temperature 1.0 to model guessing. 0.25 == chance for 4 options.
  * open_book_correct   : does the SAME model answer correctly WITH the clean
    passage (temperature 0)? The within-model clean ceiling.
  * dynamic_range       : open_book_correct - prior_answerability. How much room the
    passage actually adds. ~0 (or negative) => the item carries no usable signal.
  * real_clean_correct  : the ACTUAL human-proxy model's clean-condition result for
    this item (joined from the existing scores_target_llama.json), as a second,
    model-matched reference.

Caveat: gpt-4.1-mini is stronger and more Bible-literate than the 1b/1.5b/1.7b human
proxies, so its closed-book accuracy is an UPPER BOUND on guessability. The RANKING of
which items are guessable (the register/distractor flaw) should transfer; use
--provider ollama --model qwen2.5:1.5b to reproduce with a proxy model.

Usage:
  set -a; source .env; set +a
  python evaluation/scripts/mcq/closed_book_diagnostic.py \
      --chapters 1 2 3 4 5 6 7 8 --k 5 --model gpt-4.1-mini
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LETTER_RE = re.compile(r"[A-Da-d]")


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pick(dir_: Path, *names: str) -> Path | None:
    for n in names:
        if (dir_ / n).exists():
            return dir_ / n
    return None


def build_client(provider: str):
    if provider == "openai":
        from openai import OpenAI
        return OpenAI()
    if provider == "ollama":
        from openai import OpenAI
        return OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                      api_key="ollama")
    raise SystemExit(f"unknown provider: {provider}")


def options_block(opts: dict) -> str:
    return "\n".join(f"{k}. {opts[k]}" for k in ("A", "B", "C", "D") if k in opts)


def ask(client, model, question, opts, passage, temperature, system=None):
    header = f"文章：\n{passage}\n\n" if passage else ""
    instr = ("请只根据下面的文章作答。" if passage
             else "没有提供文章。请仅凭你已有的知识猜一个最可能的答案。")
    prompt = (f"{header}这是一道单项选择题。{instr}\n\n"
              f"问题：{question}\n选项：\n{options_block(opts)}\n\n"
              f"只输出一个字母：A、B、C 或 D。")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    r = client.chat.completions.create(
        model=model, temperature=temperature, max_tokens=8, messages=messages,
    )
    text = (r.choices[0].message.content or "").strip()
    m = LETTER_RE.search(text)
    return m.group(0).upper() if m else "?"


def collect_items(root: Path, chapters, model_dir, clean_subdir):
    items = []
    for ch in chapters:
        d = root / f"luke{ch}" / model_dir / clean_subdir
        qf = pick(d, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
        if not qf:
            print(f"  [warn] no qa_target for luke{ch} at {d}", file=sys.stderr)
            continue
        pf = pick(d, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt")
        passage = pf.read_text(encoding="utf-8") if pf else ""
        # real proxy-model clean scores, join by id -> direct_correct
        scores = load_json(d / "scores_target_llama.json") or {}
        real = {it.get("id"): it.get("direct_correct")
                for it in (scores.get("items") or []) if it.get("q_type") == "mcq"}
        for r in load_json(qf) or []:
            if r.get("q_type") != "mcq":
                continue
            iid = r.get("passage_id")
            items.append({
                "chapter": ch, "id": iid, "reference": r.get("passage_reference"),
                "question": r.get("Q"), "options": r.get("A"), "correct": r.get("correct"),
                "passage": passage, "real_clean_correct": real.get(iid),
            })
    return items


def run(args):
    client = build_client(args.provider)
    items = collect_items(Path(args.root), args.chapters, args.model_dir, args.clean_subdir)
    print(f"loaded {len(items)} MCQ items across chapters {args.chapters}")

    system = None if args.no_domain_hint else args.domain_hint

    def process(it):
        # closed-book: K guesses at temp 1.0
        guesses = [ask(client, args.model, it["question"], it["options"], "", 1.0, system)
                   for _ in range(args.k)]
        correct = it["correct"]
        prior = sum(1 for g in guesses if g == correct) / max(1, args.k)
        # open-book: 1 answer at temp 0 on the clean passage
        ob = ask(client, args.model, it["question"], it["options"], it["passage"], 0.0, system) \
            if not args.no_open_book else "?"
        open_correct = int(ob == correct) if ob != "?" else None
        return {**it, "closed_guesses": guesses, "prior_answerability": prior,
                "open_book_choice": ob, "open_book_correct": open_correct}

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, it): it for it in items}
        for i, f in enumerate(as_completed(futs), 1):
            results.append(f.result())
            if i % 20 == 0:
                print(f"  ...{i}/{len(items)}")

    for r in results:
        oc = r["open_book_correct"]
        r["dynamic_range"] = (oc - r["prior_answerability"]) if oc is not None else None
        r["dead_weight"] = r["prior_answerability"] >= args.dead_threshold
    # rank: most prior-answerable (worst) first, then smallest dynamic range
    results.sort(key=lambda r: (-r["prior_answerability"],
                                (r["dynamic_range"] if r["dynamic_range"] is not None else 0)))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cols = ["chapter", "id", "reference", "correct", "prior_answerability",
            "open_book_choice", "open_book_correct", "dynamic_range",
            "real_clean_correct", "dead_weight", "question",
            "opt_A", "opt_B", "opt_C", "opt_D", "closed_guesses"]
    with (out / "closed_book_items.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in results:
            o = r["options"] or {}
            w.writerow([r["chapter"], r["id"], r["reference"], r["correct"],
                        f'{r["prior_answerability"]:.2f}', r["open_book_choice"],
                        r["open_book_correct"], r["dynamic_range"], r["real_clean_correct"],
                        r["dead_weight"], r["question"],
                        o.get("A"), o.get("B"), o.get("C"), o.get("D"),
                        "".join(r["closed_guesses"])])

    n = len(results)
    priors = [r["prior_answerability"] for r in results]
    obs = [r["open_book_correct"] for r in results if r["open_book_correct"] is not None]
    summary = {
        "model": args.model, "k": args.k, "n_items": n, "chance": 0.25,
        "domain_hint": None if args.no_domain_hint else args.domain_hint,
        "closed_book_mean_accuracy": round(sum(priors) / n, 4) if n else None,
        "open_book_mean_accuracy": round(sum(obs) / len(obs), 4) if obs else None,
        "pct_items_prior_over_50": round(sum(p > 0.5 for p in priors) / n, 4) if n else None,
        "pct_items_prior_over_chance_a_lot(>=0.6)": round(sum(p >= 0.6 for p in priors) / n, 4) if n else None,
        "n_dead_weight(prior>=%.2f)" % args.dead_threshold: sum(r["dead_weight"] for r in results),
        "n_dead_and_clean_correct": sum(1 for r in results if r["dead_weight"] and r["real_clean_correct"]),
    }
    (out / "closed_book_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nwrote {out/'closed_book_items.csv'}")
    return summary


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    ap.add_argument("--model-dir", default="1.7b")
    ap.add_argument("--clean-subdir", default="omission/0%")
    ap.add_argument("--provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--k", type=int, default=5, help="closed-book guess samples per item")
    ap.add_argument(
        "--domain-hint",
        default="你正在回答关于一段宗教经文（圣经）的阅读理解选择题。",
        help="System-prompt framing telling the model the text is religious/Bible — "
             "matches what a real participant knows and triggers register-guessing. "
             "Default ON (the realistic condition).",
    )
    ap.add_argument("--no-domain-hint", action="store_true",
                    help="Disable the religious-text framing (blind baseline).")
    ap.add_argument("--no-open-book", action="store_true")
    ap.add_argument("--dead-threshold", type=float, default=0.8)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out-dir", default="evaluation/outputs/reports/closed_book")
    return ap.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()) and 0)
