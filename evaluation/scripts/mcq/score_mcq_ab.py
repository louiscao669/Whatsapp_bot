#!/usr/bin/env python3
"""A/B-score an answer model on OLD vs NEW MCQ options from mcq_ab_testset.json.

For every item it answers both the original options and the rewritten options, in two modes:
  * closed-book (question + options only, religious-text system prompt, K sampled guesses)
      -> the DE-GUESSING check. Good rewrite => new prior < old prior (toward 0.25 chance).
  * open-book (clean passage + question + options, temp 0)
      -> the FAIRNESS check. Good rewrite => new open-acc stays ~ old open-acc (a reader
         who has the passage can still answer; the rewrite didn't make it unfair/ambiguous).

The ideal signature is: closed-book accuracy DROPS, open-book accuracy HOLDS.

Usage:
  python evaluation/scripts/mcq/score_mcq_ab.py --provider ollama --model qwen2.5:1.5b --k 5
  python evaluation/scripts/mcq/score_mcq_ab.py --provider ollama --model qwen3:1.7b       # ladder
"""
from __future__ import annotations
import argparse, csv, json, os, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LETTER = re.compile(r"[A-Da-d]")


def build_client(provider):
    from openai import OpenAI
    if provider == "ollama":
        return OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                      api_key="ollama")
    return OpenAI()


def opts_block(o):
    return "\n".join(f"{L}. {o[L]}" for L in "ABCD" if o.get(L))


def ask(client, model, question, opts, passage, temperature, system):
    header = f"文章：\n{passage}\n\n" if passage else ""
    instr = "请只根据下面的文章作答。" if passage else "没有提供文章。请凭已有知识猜最可能的答案。"
    prompt = (f"{header}这是一道单项选择题。{instr}\n\n问题：{question}\n选项：\n"
              f"{opts_block(opts)}\n\n只输出一个字母：A、B、C 或 D。")
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    r = client.chat.completions.create(model=model, temperature=temperature, max_tokens=8, messages=msgs)
    m = LETTER.search((r.choices[0].message.content or "").strip())
    return m.group(0).upper() if m else "?"


def load_passages(root, model_dir):
    cache = {}
    for ch in range(1, 9):
        p = Path(root) / f"luke{ch}" / model_dir / "omission" / "0%" / "passage_target_pseudonymized.txt"
        cache[ch] = p.read_text(encoding="utf-8") if p.exists() else ""
    return cache


def score_variant(client, model, q, variant, passage, k, system):
    correct = variant["correct"]
    guesses = [ask(client, model, q, variant, "", 1.0, system) for _ in range(k)]
    prior = sum(g == correct for g in guesses) / max(1, k)
    open_correct = int(ask(client, model, q, variant, passage, 0.0, system) == correct)
    return prior, open_correct


def run(args):
    client = build_client(args.provider)
    system = None if args.no_domain_hint else args.domain_hint
    items = json.loads(Path(args.testset).read_text(encoding="utf-8"))
    passages = load_passages(args.root, args.model_dir)

    def process(it):
        p = passages.get(it["chapter"], "")
        op, oo = score_variant(client, args.model, it["question"], it["old"], p, args.k, system)
        npr, no = score_variant(client, args.model, it["question"], it["new"], p, args.k, system)
        return {**{k: it[k] for k in ("id", "chapter", "ref", "question")},
                "old_closed_prior": op, "old_open_correct": oo,
                "new_closed_prior": npr, "new_open_correct": no}

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process, it) for it in items]
        for i, f in enumerate(as_completed(futs), 1):
            rows.append(f.result())
            if i % 20 == 0:
                print(f"  ...{i}/{len(items)}")

    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    cols = ["id", "chapter", "ref", "old_closed_prior", "new_closed_prior",
            "old_open_correct", "new_open_correct", "question"]
    with (out / "mcq_ab_items.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(cols)
        for r in rows:
            w.writerow([r["id"], r["chapter"], r["ref"], f'{r["old_closed_prior"]:.2f}',
                        f'{r["new_closed_prior"]:.2f}', r["old_open_correct"],
                        r["new_open_correct"], r["question"]])

    n = len(rows)
    mean = lambda key: round(sum(r[key] for r in rows) / n, 3) if n else None
    summary = {
        "model": args.model, "provider": args.provider, "k": args.k, "n_items": n, "chance": 0.25,
        "closed_book": {"old_mean_prior": mean("old_closed_prior"),
                        "new_mean_prior": mean("new_closed_prior"),
                        "drop": round((mean("old_closed_prior") or 0) - (mean("new_closed_prior") or 0), 3)},
        "open_book": {"old_accuracy": mean("old_open_correct"),
                      "new_accuracy": mean("new_open_correct")},
        "new_open_book_failures": [r["id"] for r in rows if r["new_open_correct"] == 0],
        "still_guessable_new(prior>=0.5)": [r["id"] for r in rows if r["new_closed_prior"] >= 0.5],
    }
    (out / "mcq_ab_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== A/B SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nwrote {out/'mcq_ab_items.csv'}")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testset", default="evaluation/datasets/mcq/mcq_ab_testset.json")
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--model-dir", default="1.7b")
    ap.add_argument("--provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--domain-hint", default="你正在回答关于一段宗教经文（圣经）的阅读理解选择题。")
    ap.add_argument("--no-domain-hint", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out-dir", default="evaluation/outputs/reports/mcq_ab")
    return ap.parse_args()


if __name__ == "__main__":
    run(parse_args())
