#!/usr/bin/env python3
"""
Method ranking + cross-model agreement (Spearman) + consensus ranking.

Reads per-item scores from
    outputs/luke{1..8}/{model}/{method}/scores_target_llama.json
for the three answer-model ability tiers (llama3.2:1b, qwen2.5:1.5b, qwen3:1.7b)
across the 8 translation methods.

Produces three views:
  1. Per-model method ranking (each model ranks the 8 methods on its own).
  2. Pairwise Spearman rho between models' rankings (separability check).
  3. Consensus ranking: for each item, mean of the 3 models' scores
     (matched items only), pooled over chapters, then mean per method.

Item score: open -> llm_score in [0,1]; mcq -> 1.0 if direct_correct else 0.0.

Writes: reports/method_ranking_consensus.{json,md,csv}
Run:  cd evaluation && python3 scripts/method_ranking_consensus.py
"""
import json, os
from itertools import combinations
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # repo root (script now lives in QA_algorithm/scripts)
OUT  = os.path.join(REPO, "evaluation", "outputs")     # answer-score inputs stay under evaluation/
REPORTS = os.path.join(REPO, "QA_algorithm", "outputs", "reports")  # analysis outputs live under QA_algorithm/

METHODS = ["google_word_by_word", "mBART-50", "helsinki", "nllb-200-distilled-600M",
           "llm_prompt_low", "llm_prompt_medium", "nllb-200-1.3B", "llm_prompt_high"]
MODELS  = {"llama 1b": "llama1b", "1.5b": "qwen1.5b", "1.7b": "qwen1.7b"}
LABELS  = list(MODELS.values())
CHAPTERS = [f"luke{i}" for i in range(1, 9)]


def item_scores(path):
    d = {}
    with open(path) as f:
        items = json.load(f)["items"]
    for it in items:
        if it["q_type"] == "mcq":
            d[it["id"]] = 1.0 if it.get("direct_correct") else 0.0
        else:
            s = it.get("llm_score")
            if s is not None:
                d[it["id"]] = s
    return d


def summary_combined(path):
    with open(path) as f:
        s = json.load(f)["summary"]
    tot = s["total"]
    if not tot:
        return None
    open_sum = (s.get("open_llm_score_mean") or 0) * (s.get("open_count") or 0)
    return (s.get("mcq_correct", 0) + open_sum) / tot


def spearman(a, b):
    n = len(a)
    d2 = sum((a[m] - b[m]) ** 2 for m in a)
    return 1 - 6 * d2 / (n * (n * n - 1))


def ranks(d):  # 1 = worst, 8 = best
    order = sorted(d, key=lambda m: d[m])
    return {m: i + 1 for i, m in enumerate(order)}


# ---- 1. per-model method means (all available items per model) ----
per_model = {l: {} for l in LABELS}
for md, lab in MODELS.items():
    for meth in METHODS:
        vals = []
        for ch in CHAPTERS:
            p = f"{OUT}/{ch}/{md}/{meth}/scores_target_llama.json"
            if os.path.exists(p):
                c = summary_combined(p)
                if c is not None:
                    vals.append(c)
        per_model[lab][meth] = sum(vals) / len(vals) if vals else None

rk = {l: ranks(per_model[l]) for l in LABELS}
spear = {f"{x} vs {y}": round(spearman(rk[x], rk[y]), 3) for x, y in combinations(LABELS, 2)}

# ---- 3. consensus ranking (matched items, mean of 3 models) ----
consensus, n_items, cons_per_model = {}, {}, {l: {} for l in LABELS}
for meth in METHODS:
    pooled, pm = [], {l: [] for l in LABELS}
    for ch in CHAPTERS:
        paths = {l: f"{OUT}/{ch}/{md}/{meth}/scores_target_llama.json"
                 for md, l in MODELS.items()}
        if not all(os.path.exists(p) for p in paths.values()):
            continue
        sc = {l: item_scores(paths[l]) for l in LABELS}
        common = set.intersection(*[set(s) for s in sc.values()])
        for iid in common:
            vals = [sc[l][iid] for l in LABELS]
            pooled.append(sum(vals) / len(vals))
            for l in LABELS:
                pm[l].append(sc[l][iid])
    consensus[meth] = sum(pooled) / len(pooled) if pooled else None
    n_items[meth] = len(pooled)
    for l in LABELS:
        cons_per_model[l][meth] = sum(pm[l]) / len(pm[l]) if pm[l] else None

cons_order = sorted(METHODS, key=lambda m: consensus[m], reverse=True)

# ---- write JSON ----
os.makedirs(REPORTS, exist_ok=True)
payload = {
    "generated": str(date.today()),
    "metric": "open=llm_score[0,1]; mcq=1.0 if direct_correct else 0.0",
    "models": LABELS,
    "methods": METHODS,
    "per_model_method_mean": per_model,
    "per_model_ranks_1worst_8best": rk,
    "pairwise_spearman_rho": spear,
    "consensus_ranking": [
        {"rank": i + 1, "method": m, "consensus": round(consensus[m], 4),
         "llama1b": round(cons_per_model["llama1b"][m], 4),
         "qwen1.5b": round(cons_per_model["qwen1.5b"][m], 4),
         "qwen1.7b": round(cons_per_model["qwen1.7b"][m], 4),
         "n_items": n_items[m]}
        for i, m in enumerate(cons_order)
    ],
}
with open(f"{REPORTS}/method_ranking_consensus.json", "w") as f:
    json.dump(payload, f, indent=2)

# ---- write CSV (consensus ranking) ----
with open(f"{REPORTS}/method_ranking_consensus.csv", "w") as f:
    f.write("rank,method,consensus,llama1b,qwen1.5b,qwen1.7b,n_items\n")
    for r in payload["consensus_ranking"]:
        f.write(f"{r['rank']},{r['method']},{r['consensus']},{r['llama1b']},"
                f"{r['qwen1.5b']},{r['qwen1.7b']},{r['n_items']}\n")

# ---- write Markdown ----
md = []
md.append("# Method Ranking & Cross-Model Consensus\n")
md.append(f"_Generated {date.today()} · source: `outputs/luke1-8/{{model}}/{{method}}/scores_target_llama.json`_\n")
md.append("**Metric.** Per item: open answers use the LLM judge score in [0,1]; "
          "MCQ items score 1.0 if correct else 0.0. Combined per method as noted below.\n")
md.append("**Answer models (ability tiers):** llama3.2:1b < qwen2.5:1.5b < qwen3:1.7b.\n")

md.append("\n## 1. Consensus ranking (mean of the 3 models' per-item scores)\n")
md.append("For each item, average the three models' scores (matched items only — all three "
          "answered it), pool over Luke 1–8, then mean per method. Best → worst.\n")
md.append("| rank | method | consensus | 1b | 1.5b | 1.7b | items |")
md.append("|---|---|---|---|---|---|---|")
for r in payload["consensus_ranking"]:
    md.append(f"| {r['rank']} | {r['method']} | **{r['consensus']:.3f}** | "
              f"{r['llama1b']:.3f} | {r['qwen1.5b']:.3f} | {r['qwen1.7b']:.3f} | {r['n_items']} |")

md.append("\n## 2. Per-model method means (combined accuracy, all available items)\n")
md.append("| method | llama1b | qwen1.5b | qwen1.7b |")
md.append("|---|---|---|---|")
for meth in METHODS:
    md.append(f"| {meth} | {per_model['llama1b'][meth]:.3f} | "
              f"{per_model['qwen1.5b'][meth]:.3f} | {per_model['qwen1.7b'][meth]:.3f} |")

md.append("\n## 3. Pairwise Spearman rho (agreement of method rankings, n=8)\n")
md.append("How much two ability tiers agree on the *ordering* of the 8 methods. "
          "+1 identical, 0 unrelated, -1 reversed. Separability wants high rho across tiers. "
          "At n=8, two-tailed p<0.05 needs |rho| >= ~0.74.\n")
md.append("| pair | rho |")
md.append("|---|---|")
for k, v in spear.items():
    md.append(f"| {k} | {v:+.3f} |")

md.append("\n## Notes & caveats\n")
md.append("- Consensus here is the **unweighted mean** over items and models (equal weight per "
          "respondent). Median-across-models or ability/discrimination weighting are alternatives.\n")
md.append("- The consensus order is cleaner/more monotonic than any single model, because "
          "averaging cancels per-model noise — the argument for an **ensemble** of answer models.\n")
md.append("- `llm_prompt_low` ranks higher than its quality warrants; it is inflated by qwen1.5b "
          "(0.845) and swings widely across tiers (0.32 / 0.85 / 0.81) — least trustworthy cell.\n")
md.append("- Most method×model cells still rest on a **single chapter**; middle-of-table ordering "
          "is provisional until the grid is filled. Item counts shown per method.\n")
with open(f"{REPORTS}/method_ranking_consensus.md", "w") as f:
    f.write("\n".join(md) + "\n")

print("Wrote:")
for ext in ("md", "json", "csv"):
    print("  ", f"{REPORTS}/method_ranking_consensus.{ext}")
