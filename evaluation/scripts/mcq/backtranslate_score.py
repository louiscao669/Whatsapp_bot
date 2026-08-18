#!/usr/bin/env python3
"""Back-translation scoring of the EXISTING open answers (deployment-realistic lower bound).

Regime 2 of the open-scoring decomposition:
    clean  = Chinese answer judged cross-lingually            (already in window3 file)
    BT     = Chinese answer --MT--> English --> judged in EN  (this script)

The ONLY change vs the clean score is the answer makes a Chinese->English MT round-trip
before judging (same question, same window context, same judge model). So the clean-vs-BT
gap = the cost of the back-translation step alone (the low-resource-deployment tax on open).

Does NOT re-answer and does NOT touch the clean scores. Writes per-cell
scores_target_window3_bt.json and a comparison report.

  set -a; source .env; set +a
  python evaluation/scripts/mcq/backtranslate_score.py --mt-model gpt-4o-mini --judge-model gpt-4o-mini
"""
from __future__ import annotations
import argparse, json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from regen_mcq_tier01 import (   # reuse the exact helpers so scoring is identical to clean
    build_client, judge_open, randomized_three_verse_window, item_stem, pick, CONDITIONS, CLEAN,
    EXCLUDED_OPEN_STEMS,
)

MODELS = ["1.7b", "1.5b", "llama 1b"]


def backtranslate(client, model, zh):
    if not zh or not zh.strip():
        return ""
    prompt = ("Translate this Chinese answer to English. Output only the English translation, "
              f"nothing else.\n\n{zh}")
    r = client.chat.completions.create(model=model, temperature=0.0, max_tokens=256,
        messages=[{"role": "user", "content": prompt}])
    return (r.choices[0].message.content or "").strip()


def run(args):
    root = Path(args.root)
    active_stems = {item_stem(i) for i in
                    json.loads((root.parent / "datasets" / "mcq" / "mcq_rewrites.json").read_text(encoding="utf-8"))}
    client = build_client(args.provider)             # openai for both MT and judge

    # open_scores[model][cond][id] = {"clean": x, "bt": y}
    open_scores = {m: {c: {} for c in CONDITIONS} for m in MODELS}

    def do_cell(model_dir, ch, cond):
        src = root / f"luke{ch}" / args.qa_model_dir / cond
        qf = pick(src, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
        pf = pick(src, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt")
        sp = root / f"luke{ch}" / model_dir / cond / "scores_target_window3_v2.json"
        if not (qf and pf and sp.exists()):
            return cond, {}
        passage = pf.read_text(encoding="utf-8")
        recs = {r["passage_id"]: r for r in json.loads(qf.read_text(encoding="utf-8"))
                if item_stem(r.get("passage_id")) in active_stems}
        data = json.loads(sp.read_text(encoding="utf-8"))
        out_items, cell = [], {}
        for it in data.get("items", []):
            if it.get("q_type") == "mcq" or item_stem(it["id"]) in EXCLUDED_OPEN_STEMS:
                continue
            rec = recs.get(it["id"])
            if not rec:
                continue
            zh = it.get("generated_answer", "")
            en = backtranslate(client, args.mt_model, zh)
            ctx = randomized_three_verse_window(passage, rec)
            bt = judge_open(client, args.judge_model, rec["Q"], str(rec.get("A") or ""), en, ctx)
            cell[it["id"]] = {"clean": it.get("llm_score"), "bt": bt}
            out_items.append({"id": it["id"], "generated_zh": zh, "generated_en": en,
                              "expected": str(rec.get("A") or ""),
                              "llm_score_clean": it.get("llm_score"), "llm_score_bt": bt})
        (root / f"luke{ch}" / model_dir / cond / "scores_target_window3_bt.json").write_text(
            json.dumps({"items": out_items}, ensure_ascii=False, indent=1), encoding="utf-8")
        return cond, cell

    for model_dir in MODELS:
        print(f"\n== back-translating + judging: {model_dir} ==")
        jobs = [(ch, c) for ch in args.chapters for c in CONDITIONS]
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(do_cell, model_dir, ch, c): (ch, c) for ch, c in jobs}
            for i, f in enumerate(as_completed(futs), 1):
                cond, cell = f.result()
                open_scores[model_dir][cond].update(cell)
                if i % 10 == 0:
                    print(f"   ...{i}/{len(jobs)} cells")

    # ---------------- comparison report ----------------
    out = root / "reports" / "mcq_regen_qc"; out.mkdir(parents=True, exist_ok=True)

    def mean(model, cond, key):
        vals = [v[key] for v in open_scores[model][cond].values() if v.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    rows = []
    print("\n=== OPEN: clean (cross-lingual judge) vs BT (MT->English judge) ===")
    for m in MODELS:
        for c in CONDITIONS:
            rows.append({"model": m, "condition": c,
                         "open_clean": mean(m, c, "clean"), "open_bt": mean(m, c, "bt")})
        clean = [mean(m, f"omission/{p}%", "clean") for p in (0, 10, 20, 30)]
        bt = [mean(m, f"omission/{p}%", "bt") for p in (0, 10, 20, 30)]
        cs = (clean[0] - clean[3]) if None not in clean else None
        bs = (bt[0] - bt[3]) if None not in bt else None
        print(f"  {m}: omission slope  clean={cs:+.3f}  bt={bs:+.3f}  "
              f"(attenuation {cs-bs:+.3f}, {100*(1-bs/cs):.0f}% of the slope lost)" if cs and bs else
              f"  {m}: (missing)")
    with (out / "backtranslation_compare.csv").open("w", encoding="utf-8") as fh:
        fh.write("model,condition,open_clean,open_bt\n")
        for r in rows:
            fh.write(f'{r["model"]},{r["condition"]},'
                     f'{"" if r["open_clean"] is None else round(r["open_clean"],3)},'
                     f'{"" if r["open_bt"] is None else round(r["open_bt"],3)}\n')
    print(f"\nwrote {out/'backtranslation_compare.csv'} and per-cell scores_target_window3_bt.json")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--qa-model-dir", default="1.7b")
    ap.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    ap.add_argument("--provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--mt-model", default="gpt-4o-mini", help="Chinese->English back-translator")
    ap.add_argument("--judge-model", default="gpt-4o-mini", help="scores the English answer vs English key")
    ap.add_argument("--workers", type=int, default=8)
    return ap.parse_args()


if __name__ == "__main__":
    run(parse_args())
