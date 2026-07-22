#!/usr/bin/env python3
"""P5 - Multi-respondent aggregation, per-pool re-zeroing, cross-respondent consistency.

The deployment protocol answers a passage with MULTIPLE respondents of differing ability
and needs one quality estimate that factors out ability. This script demonstrates the
three pieces the protocol requires, on the filled 3-model defect grid:

1. PER-POOL RE-ZEROING. Absolute accuracy is not comparable across respondents (a 1b
   baseline sits far below a 1.7b baseline). Each respondent's dose effect is measured
   as a logit shift from ITS OWN 0% anchor:  Delta_m(f,d) = logit(acc_m(f,d)) - logit(acc_m(f,0)).
   (V2/Step-2 found a +0.4-0.5 logit anchor-transfer offset -> per-deployment re-zeroing
   is the fix; this operationalizes it.)

2. AGGREGATION. Pool re-zeroed Delta across respondents -> an aggregate dose-response with
   error bars (chapter bootstrap), replacing n=1 point estimates. Aggregate SE should beat
   any single respondent's.

3. CROSS-RESPONDENT SPLIT-CONSISTENCY. Do respondents agree on the re-zeroed dose effects?
   Pairwise + a {1b} vs {1.5b,1.7b} split correlation of Delta vectors over (family,dose)
   cells. High agreement => aggregation is valid; ability has been factored out.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "evaluation" / "outputs"
OUTDIR = REPO / "QA_algorithm" / "outputs" / "reports" / "item_sensitivity"
MODELS = ["llama 1b", "1.5b", "1.7b"]
FAMILIES = ["omission", "mistranslation", "grammar", "awkward"]
KIND = {"omission": "adeq", "mistranslation": "adeq", "grammar": "flu", "awkward": "flu"}
DOSES = ["0%", "5%", "10%", "15%", "20%", "30%"]
CHAPTERS = list(range(1, 9))
NBOOT = 2000
RNG = np.random.default_rng(20260721)


def cell_num_den(fam, model, ch, dose):
    """(mcq_correct + open_llm_sum, total) for one score file, or None."""
    f = EVAL / f"luke{ch}" / model / fam / dose / "scores_target_llama.json"
    if not f.exists():
        return None
    s = json.loads(f.read_text()).get("summary", {})
    total = s.get("total") or 0
    if not total:
        return None
    mcq_c = s.get("mcq_correct") or 0
    open_sum = (s.get("open_llm_score_mean") or 0.0) * (s.get("open_count") or 0)
    return mcq_c + open_sum, total


def acc(fam, model, doses_chs):
    """combined accuracy pooled over the given (dose fixed) chapter set."""
    num = den = 0.0
    for ch in doses_chs:
        r = doses_chs[ch]
        if r:
            num += r[0]; den += r[1]
    return num / den if den else None


def logit(p, eps=0.02):
    p = min(1 - eps, max(eps, p))
    return math.log(p / (1 - p))


def gather():
    """data[(fam,model,dose)][ch] = (num,den)."""
    data = defaultdict(dict)
    for fam in FAMILIES:
        for m in MODELS:
            for d in DOSES:
                for ch in CHAPTERS:
                    nd = cell_num_den(fam, m, ch, d)
                    if nd:
                        data[(fam, m, d)][ch] = nd
    return data


def acc_pooled(data, fam, m, d, chs):
    num = den = 0.0
    for ch in chs:
        nd = data[(fam, m, d)].get(ch)
        if nd:
            num += nd[0]; den += nd[1]
    return (num / den) if den else None


def delta_vector(data, models, chs):
    """re-zeroed logit dose-shift per (fam,dose>0), averaged over the given models."""
    out = {}
    for fam in FAMILIES:
        base_by_m = {m: acc_pooled(data, fam, m, "0%", chs) for m in models}
        for d in DOSES[1:]:
            vals = []
            for m in models:
                a = acc_pooled(data, fam, m, d, chs); b = base_by_m[m]
                if a is not None and b is not None:
                    vals.append(logit(a) - logit(b))
            if vals:
                out[(fam, d)] = float(np.mean(vals))
    return out


def per_model_delta(data, m, chs):
    out = {}
    for fam in FAMILIES:
        b = acc_pooled(data, fam, m, "0%", chs)
        for d in DOSES[1:]:
            a = acc_pooled(data, fam, m, d, chs)
            if a is not None and b is not None:
                out[(fam, d)] = logit(a) - logit(b)
    return out


def pearson(dref, dtest):
    keys = sorted(set(dref) & set(dtest))
    x = np.array([dref[k] for k in keys]); y = np.array([dtest[k] for k in keys])
    if len(x) < 3 or x.std() < 1e-9 or y.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def main():
    data = gather()

    # ---- 1. re-zeroing motivation: baselines differ wildly across respondents ----
    print("1) PER-POOL RE-ZEROING - 0% baseline combined-accuracy by respondent "
          "(why absolute acc is not comparable):")
    print(f"   {'family':16}" + "".join(f"{m:>12}" for m in MODELS))
    for fam in FAMILIES:
        cells = [acc_pooled(data, fam, m, "0%", CHAPTERS) for m in MODELS]
        print(f"   {fam:16}" + "".join(f"{c:>12.3f}" for c in cells))

    # ---- 2. aggregated re-zeroed dose-response with chapter-bootstrap CI ----
    agg_pt = delta_vector(data, MODELS, CHAPTERS)
    permodel_pt = {m: per_model_delta(data, m, CHAPTERS) for m in MODELS}
    boot_agg = defaultdict(list); boot_m = {m: defaultdict(list) for m in MODELS}
    for _ in range(NBOOT):
        chs = list(RNG.choice(CHAPTERS, size=len(CHAPTERS), replace=True))
        for k, v in delta_vector(data, MODELS, chs).items():
            boot_agg[k].append(v)
        for m in MODELS:
            for k, v in per_model_delta(data, m, chs).items():
                boot_m[m][k].append(v)

    rows = []
    for fam in FAMILIES:
        for d in DOSES[1:]:
            k = (fam, d)
            if k not in agg_pt:
                continue
            arr = np.array(boot_agg[k])
            lo, hi = np.percentile(arr, [2.5, 97.5])
            se_agg = float(arr.std())
            se_single = float(np.mean([np.std(boot_m[m][k]) for m in MODELS
                                       if k in boot_m[m]]))
            rows.append({"family": fam, "kind": KIND[fam], "dose": d,
                         "agg_delta": round(agg_pt[k], 3),
                         "ci_lo": round(float(lo), 3), "ci_hi": round(float(hi), 3),
                         "se_aggregate": round(se_agg, 3),
                         "se_single_mean": round(se_single, 3),
                         "d1b": round(permodel_pt["llama 1b"].get(k, float('nan')), 3),
                         "d1p5b": round(permodel_pt["1.5b"].get(k, float('nan')), 3),
                         "d1p7b": round(permodel_pt["1.7b"].get(k, float('nan')), 3)})
    out = OUTDIR / "p5_multirespondent_aggregation.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    print("\n2) AGGREGATED re-zeroed dose-response (logit shift from 0%; negative = damage), "
          "chapter-bootstrap 95% CI:")
    print(f"   {'family':15}{'dose':>5}{'aggDelta':>10}{'95% CI':>18}"
          f"{'se_agg':>8}{'se_1model':>11}  monotone?")
    for fam in FAMILIES:
        seq = [r for r in rows if r["family"] == fam]
        deltas = [r["agg_delta"] for r in seq]
        mono = all(deltas[i] >= deltas[i + 1] - 1e-9 for i in range(len(deltas) - 1))
        for r in seq:
            ci = f"[{r['ci_lo']:+.2f},{r['ci_hi']:+.2f}]"
            print(f"   {r['family']:15}{r['dose']:>5}{r['agg_delta']:>+10.3f}{ci:>18}"
                  f"{r['se_aggregate']:>8}{r['se_single_mean']:>11}"
                  f"{'   yes' if r is seq[-1] and mono else ''}")

    # ---- 3. cross-respondent split-consistency ----
    print("\n3) CROSS-RESPONDENT SPLIT-CONSISTENCY - Pearson r of re-zeroed Delta vectors "
          "(over family x dose cells):")
    pm = permodel_pt
    print(f"   1b   vs 1.5b : r={pearson(pm['llama 1b'], pm['1.5b']):+.3f}")
    print(f"   1b   vs 1.7b : r={pearson(pm['llama 1b'], pm['1.7b']):+.3f}")
    print(f"   1.5b vs 1.7b : r={pearson(pm['1.5b'], pm['1.7b']):+.3f}")
    split_a = per_model_delta(data, "llama 1b", CHAPTERS)  # weak pool
    split_b = delta_vector(data, ["1.5b", "1.7b"], CHAPTERS)  # strong pool
    print(f"   split {{1b}} vs {{1.5b,1.7b}} : r={pearson(split_a, split_b):+.3f}  "
          "(deployment-style disjoint respondent pools)")
    # adequacy-only (the cells that carry signal)
    adq = lambda dd: {k: v for k, v in dd.items() if KIND[k[0]] == "adeq"}
    print(f"   [adequacy cells only] 1b vs 1.7b : r={pearson(adq(pm['llama 1b']), adq(pm['1.7b'])):+.3f}"
          f" ;  {{1b}} vs {{1.5b,1.7b}} : r={pearson(adq(split_a), adq(split_b)):+.3f}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
