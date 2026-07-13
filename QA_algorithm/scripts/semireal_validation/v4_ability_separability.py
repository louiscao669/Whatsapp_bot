#!/usr/bin/env python3
"""V4 of the semi-real validation — the flagship SEPARABILITY claim
(EXPERIMENT_SEMIREAL_LAMBDA_VALIDATION_2026-07-09.md §4-V4):

The deployed estimate q̂ (here: damage Δ) should be a property of the
TRANSLATION, not of WHO answered. Three answer models of very different
ability answered the same 8 method-translations × 8 chapters. Fit Δ per
(model × method) with each model's OWN anchor θ (per q_type), then test:

  (1) RANK AGREEMENT: cross-model Spearman of method-level Δ.
      Pre-registered pass: rho >= ~0.7 for all 3 model pairs.
  (2) SCALE AGREEMENT (λ ability-independence): WLS slope of
      Δ_modelA vs Δ_modelB across methods. Slope ~ 1 => the quality scale
      is ability-independent; slope != 1 => weaker/stronger respondents
      compress or expand the scale (ability-dependent sensitivity — the
      dynamic-range finding predicts weaker models may show LARGER spread).
  (3) LEVEL AGREEMENT: per-method |Δ_A − Δ_B| vs joint SEs
      (z = diff/sqrt(seA²+seB²)); mean offset per pair = residual θ
      miscalibration (a per-deployment re-zeroing analogue).

Δ per (model, method) is fitted on responses POOLED over all 8 chapters
(~200-350 answers) — the aggregation level Step 2b showed is reliable.
Per-cell (chapter-level) cross-model correlations reported as secondary.

Models: anchor ladder only ('llama 1b', '1.5b', '1.7b'; 'llama 3b' has
responses but no anchor θ — excluded, noted).

Outputs (QA_algorithm/outputs/reports/adequacy_burden/):
  v4_ability_separability.csv   per (model, method[, chapter]) Δ, SE, n
  v4_summary.txt                three verdicts
  v4_ability_separability.png   pairwise scatter + rank plot

Usage: python3 QA_algorithm/scripts/semireal_validation/v4_ability_separability.py
       [--q-types both|mcq|open]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

QA_ROOT = Path(__file__).resolve().parents[2]
REPO = QA_ROOT.parent
EVAL_OUT = REPO / "evaluation" / "outputs"
ANCHOR = {qt: QA_ROOT / "outputs" / f"anchor_irt_estimates_{qt}.json"
          for qt in ("mcq", "open")}
OUT_DIR = QA_ROOT / "outputs" / "reports" / "adequacy_burden"

MODELS = ["llama 1b", "1.5b", "1.7b"]      # tier dir == anchor ladder key
METHODS = ["google_word_by_word", "helsinki", "llm_prompt_high",
           "llm_prompt_low", "llm_prompt_medium", "mBART-50",
           "nllb-200-1.3B", "nllb-200-distilled-600M"]
PRIOR_SD = 3.0
PASS_RHO = 0.7


def fit_delta(y, base_logit, prior_sd=PRIOR_SD):
    y = np.asarray(y, float)
    d = 0.0
    for _ in range(100):
        p = 1.0 / (1.0 + np.exp(-(base_logit - d)))
        g = float(np.sum(p - y)) - d / prior_sd**2
        h = -float(np.sum(p * (1 - p))) - 1.0 / prior_sd**2
        step = g / h
        d -= step
        if abs(step) < 1e-10:
            break
    p = 1.0 / (1.0 + np.exp(-(base_logit - d)))
    se = 1.0 / np.sqrt(np.sum(p * (1 - p)) + 1.0 / prior_sd**2)
    return float(d), float(se)


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q-types", choices=("both", "mcq", "open"),
                    default="both")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    qtypes = ("mcq", "open") if args.q_types == "both" else (args.q_types,)

    theta, bmap = {}, {}
    for qt, path in ANCHOR.items():
        d = json.load(open(path))
        theta[qt] = {m: float(v["theta"])
                     for m, v in d["model_abilities"].items()}
        bmap[qt] = {k: float(v["b_posterior"])
                    for k, v in d["item_difficulties"].items()}

    rows_cell, rows_mm = [], []
    for model in MODELS:
        for method in METHODS:
            y_all, base_all = [], []
            for ch in range(1, 9):
                sf = (EVAL_OUT / f"luke{ch}" / model / method /
                      "scores_target_llama.json")
                if not sf.exists():
                    continue
                y, base = [], []
                for it in json.load(open(sf))["items"]:
                    qt = it["q_type"]
                    if qt not in qtypes:
                        continue
                    b = bmap[qt].get(f"luke{ch}:item{it['item_index']}:{qt}")
                    if b is None:
                        continue
                    if qt == "mcq":
                        yy = 1.0 if it["direct_correct"] else 0.0
                    else:
                        if it["llm_score"] is None:
                            continue
                        yy = float(it["llm_score"])
                    y.append(yy)
                    base.append(theta[qt][model] - b)
                if len(y) >= 6:
                    d, se = fit_delta(y, np.array(base))
                    rows_cell.append(dict(model=model, method=method,
                                          chapter=ch, delta=d, se=se,
                                          n=len(y), acc=float(np.mean(y))))
                y_all += y
                base_all += base
            if len(y_all) >= 30:
                d, se = fit_delta(y_all, np.array(base_all))
                rows_mm.append(dict(model=model, method=method, delta=d,
                                    se=se, n=len(y_all),
                                    acc=float(np.mean(y_all))))

    lines = [f"V4 ability separability ({args.q_types}; models={MODELS}; "
             f"'llama 3b' excluded — not in anchor ladder)", ""]
    # method-level Δ matrix
    D = {m: {r["method"]: r for r in rows_mm if r["model"] == m}
         for m in MODELS}
    common = [mm for mm in METHODS
              if all(mm in D[m] for m in MODELS)]
    lines.append(f"methods with all 3 models: {len(common)}/8")
    lines.append("")
    lines.append(f"{'method':<26}" + "".join(f"{m:>14}" for m in MODELS))
    for mm in common:
        lines.append(f"{mm:<26}" + "".join(
            f"{D[m][mm]['delta']:>+9.2f}±{D[m][mm]['se']:.2f}"
            for m in MODELS))

    # (1) rank agreement
    lines += ["", "== (1) RANK AGREEMENT (method-level Delta, "
              f"n={len(common)}) =="]
    pairs = [(a, b) for i, a in enumerate(MODELS) for b in MODELS[i + 1:]]
    all_pass = True
    for a, b in pairs:
        da = [D[a][mm]["delta"] for mm in common]
        db = [D[b][mm]["delta"] for mm in common]
        rho = spearman(da, db)
        ok = rho >= PASS_RHO
        all_pass &= ok
        lines.append(f"  {a:<9} vs {b:<9} Spearman = {rho:+.2f}   "
                     f"[{'PASS' if ok else 'FAIL'} @ >= +{PASS_RHO}]")

    # (2) scale agreement: WLS slope through the pair means
    lines += ["", "== (2) SCALE AGREEMENT (slope of Delta_B on Delta_A; "
              "1 = ability-independent lambda) =="]
    for a, b in pairs:
        da = np.array([D[a][mm]["delta"] for mm in common])
        db = np.array([D[b][mm]["delta"] for mm in common])
        w = 1.0 / np.array([D[b][mm]["se"]**2 + D[a][mm]["se"]**2
                            for mm in common])
        xm = np.average(da, weights=w)
        ym = np.average(db, weights=w)
        slope = float(np.sum(w * (da - xm) * (db - ym))
                      / np.sum(w * (da - xm)**2))
        # rough SE via residual bootstrap over methods
        rngb = np.random.default_rng(3)
        boots = []
        idx = np.arange(len(common))
        for _ in range(500):
            ii = rngb.choice(idx, size=len(idx), replace=True)
            if np.var(da[ii]) < 1e-9:
                continue
            xm2 = np.average(da[ii], weights=w[ii])
            ym2 = np.average(db[ii], weights=w[ii])
            boots.append(float(np.sum(w[ii] * (da[ii] - xm2) * (db[ii] - ym2))
                               / np.sum(w[ii] * (da[ii] - xm2)**2)))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        lines.append(f"  {b:<9} on {a:<9} slope = {slope:+.2f} "
                     f"[95% {lo:+.2f}, {hi:+.2f}]   "
                     f"({'consistent with 1' if lo <= 1 <= hi else 'SCALE DIFFERS'})")

    # (3) level agreement
    lines += ["", "== (3) LEVEL AGREEMENT (per-method z = diff/joint SE) =="]
    for a, b in pairs:
        zs = np.array([(D[b][mm]["delta"] - D[a][mm]["delta"])
                       / np.sqrt(D[a][mm]["se"]**2 + D[b][mm]["se"]**2)
                       for mm in common])
        lines.append(f"  {a:<9} vs {b:<9} mean offset = "
                     f"{float(np.mean([D[b][mm]['delta'] - D[a][mm]['delta'] for mm in common])):+.2f} logits; "
                     f"mean|z| = {float(np.mean(np.abs(zs))):.2f}; "
                     f"max|z| = {float(np.max(np.abs(zs))):.2f}")
    lines.append("  (offset = residual theta miscalibration; absorbed by "
                 "per-deployment re-zeroing. Rank+scale are the "
                 "separability-critical tests.)")

    # secondary: per-cell cross-model spearman
    lines += ["", "== secondary: per-cell (method x chapter) rank agreement =="]
    Dc = {m: {(r["method"], r["chapter"]): r["delta"]
              for r in rows_cell if r["model"] == m} for m in MODELS}
    for a, b in pairs:
        keys = sorted(set(Dc[a]) & set(Dc[b]))
        rho = spearman([Dc[a][k] for k in keys], [Dc[b][k] for k in keys])
        lines.append(f"  {a:<9} vs {b:<9} rho = {rho:+.2f}  (n={len(keys)} "
                     "cells; noisy level — context, not a gate)")

    lines += ["", f"== VERDICT: separability "
              f"{'PASS' if all_pass else 'FAIL'} at method level =="]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.q_types == "both" else f"_{args.q_types}"
    with open(out_dir / f"v4_ability_separability{suffix}.csv", "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_cell[0].keys()))
        w.writeheader()
        w.writerows(rows_cell)
        # method-level rows appended with chapter=''
        for r in rows_mm:
            w.writerow({**r, "chapter": ""})
    (out_dir / f"v4_summary{suffix}.txt").write_text("\n".join(lines))
    print("\n".join(lines))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2))
    for ax, (a, b) in zip(axes, pairs):
        da = [D[a][mm]["delta"] for mm in common]
        db = [D[b][mm]["delta"] for mm in common]
        ax.errorbar(da, db, xerr=[2 * D[a][mm]["se"] for mm in common],
                    yerr=[2 * D[b][mm]["se"] for mm in common],
                    fmt="o", ms=5, capsize=2, lw=0, elinewidth=0.8)
        for mm, x, yv in zip(common, da, db):
            ax.annotate(mm.replace("llm_prompt_", "llm_")
                        .replace("google_word_by_word", "wbw")[:12],
                        (x, yv), fontsize=7, xytext=(3, 3),
                        textcoords="offset points")
        lim = [min(min(da), min(db)) - 0.3, max(max(da), max(db)) + 0.3]
        ax.plot(lim, lim, "k--", lw=0.8)
        ax.set_xlabel(f"Delta ({a})")
        ax.set_ylabel(f"Delta ({b})")
        ax.set_title(f"{a} vs {b}  rho={spearman(da, db):+.2f}")
    plt.tight_layout()
    plt.savefig(out_dir / f"v4_ability_separability{suffix}.png", dpi=140)
    print(f"\n[out] {out_dir}/v4_ability_separability{suffix}.{{csv,png}} "
          f"+ v4_summary{suffix}.txt")


if __name__ == "__main__":
    main()
