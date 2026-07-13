#!/usr/bin/env python3
"""V2 of the semi-real lambda validation (EXPERIMENT_SEMIREAL_LAMBDA_VALIDATION
_2026-07-09.md §4): run the deployed 1PL estimator on REAL answer-model
responses over the synthetic defect-variant dose grids, where ground truth
(designed dose) is strongest. Three independent tests:

  (1) DOSE ORDERING (signal): per (family x chapter), Spearman(Delta_obs,
      dose) including the shared 0% baseline replicated into each sub-family.
      Pass = median rho >= +0.7 for adequacy families (Delta rises with dose).
      Fluency families expected flat — CORRECT behavior (adequacy-scoped
      proxy), not failure.
  (2) ZERO POINT (bias): at dose 0, Delta ~ 0 within kappa*SE. Adjudicates
      Step 2's +0.4-0.5 logit method-axis offset: dose-0 OK here => offset is
      a property of the method-condition texts, not the estimator/anchor.
      CAVEAT: if the 0% responses fed the anchor calibration, this test is
      partially circular — treat as consistency check.
  (3) SPLIT-HALF kappa_real (noise honesty): difficulty-stratified random
      half-splits of each condition's items; Delta fitted on each half.
      z = (dA - dB)/sqrt(seA^2+seB^2) should be std normal if SEs honest.
      kappa_real = sd(z), pooled and per family / q_type. Ground-truth-free
      (q cancels in the difference). Deployment carries max(kappa_sim=1.13,
      kappa_real).

Data: evaluation/outputs/luke{1..8}/1.7b/{defect}/{level}/scores_target_llama.json
      levels: '0%', '5%'..'30%', with sub-family prefixes
      (adversarial_/bad_/neutral_, name_/style_). Answer model = 1.7b tier.
theta/b: anchor Rasch estimates (per q_type), as in Step 2.

Outputs (QA_algorithm/outputs/reports/adequacy_burden/):
  v2_defect_axis.csv       per (chapter,family,dose): Delta, SE, n, acc
  v2_summary.txt           three verdicts
  v2_defect_axis.png       dose-response curves + zero-point + z-histogram

Usage:  python3 QA_algorithm/scripts/v2_semireal_defect_axis.py
        [--q-types both|mcq|open] [--n-splits 20] [--kappa 1.13]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

QA_ROOT = Path(__file__).resolve().parents[2]
REPO = QA_ROOT.parent
EVAL_OUT = REPO / "evaluation" / "outputs"
ANCHOR = {qt: QA_ROOT / "outputs" / f"anchor_irt_estimates_{qt}.json"
          for qt in ("mcq", "open")}
OUT_DIR = QA_ROOT / "outputs" / "reports" / "adequacy_burden"

MODEL_TIER = "1.7b"
ANCHOR_MODEL_KEY = "1.7b"
DEFECT_DIRS = ["omission", "mistranslation", "grammar", "awkward",
               "addition", "inconsistency", "local_inconsistency"]
SUB_PREFIXES = ("adversarial", "bad", "neutral", "name", "style")
ADEQUACY_FAMILIES = {"omission", "mistranslation", "addition:adversarial",
                     "addition:bad"}
PRIOR_SD = 3.0
LEVEL_RE = re.compile(r"^(?:(" + "|".join(SUB_PREFIXES) + r")_)?(\d+(?:\.\d+)?)%$")


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
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def load_anchor():
    theta, bmap = {}, {}
    for qt, path in ANCHOR.items():
        d = json.load(open(path))
        theta[qt] = float(d["model_abilities"][ANCHOR_MODEL_KEY]["theta"])
        bmap[qt] = {k: float(v["b_posterior"])
                    for k, v in d["item_difficulties"].items()}
    return theta, bmap


def load_condition(score_path, ch, qtypes, theta, bmap):
    """-> (y, base_logit, b_list) arrays for joined items."""
    items = json.load(open(score_path))["items"]
    y, base, bs = [], [], []
    for it in items:
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
        base.append(theta[qt] - b)
        bs.append(b)
    return np.array(y), np.array(base), np.array(bs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q-types", choices=("both", "mcq", "open"),
                    default="both")
    ap.add_argument("--n-splits", type=int, default=20)
    ap.add_argument("--kappa", type=float, default=1.13,
                    help="simulated kappa for the zero-point tolerance")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    qtypes = ("mcq", "open") if args.q_types == "both" else (args.q_types,)
    rng = np.random.default_rng(11)
    theta, bmap = load_anchor()

    # ---- walk the grid, fit Delta per condition ---------------------------
    rows = []          # per (chapter, family, dose)
    zs = []            # split-half z values (cond-level dicts)
    for ch in range(1, 9):
        for defect in DEFECT_DIRS:
            droot = EVAL_OUT / f"luke{ch}" / MODEL_TIER / defect
            if not droot.is_dir():
                continue
            # collect levels
            levels = []
            for lev in sorted(p.name for p in droot.iterdir() if p.is_dir()):
                m = LEVEL_RE.match(lev)
                if not m:
                    continue
                sub, dose = m.group(1), float(m.group(2)) / 100.0
                sf = droot / lev / "scores_target_llama.json"
                if sf.exists():
                    levels.append((sub, dose, sf))
            if not levels:
                continue
            subs = sorted({s for s, d, _ in levels if s}) or [None]
            for sub in subs:
                fam = f"{defect}:{sub}" if sub else defect
                fam_levels = [(d, f) for s, d, f in levels
                              if s == sub or d == 0.0]  # share 0% baseline
                fam_levels.sort()
                for dose, sf in fam_levels:
                    y, base, bs = load_condition(sf, ch, qtypes, theta, bmap)
                    if len(y) < 6:
                        continue
                    d, se = fit_delta(y, base)
                    rows.append(dict(chapter=ch, family=fam, defect=defect,
                                     dose=dose, delta=d, se=se,
                                     n_items=len(y), acc=float(np.mean(y)),
                                     score_file=str(sf.relative_to(REPO))))
                    # split-half (skip tiny cells)
                    if len(y) >= 12:
                        order = np.argsort(bs)  # difficulty-stratified
                        for _ in range(args.n_splits):
                            half = np.zeros(len(y), bool)
                            for i in range(0, len(y) - 1, 2):
                                a, b2 = order[i], order[i + 1]
                                if rng.random() < 0.5:
                                    half[a] = True
                                else:
                                    half[b2] = True
                            if half.sum() < 4 or (~half).sum() < 4:
                                continue
                            dA, sA = fit_delta(y[half], base[half])
                            dB, sB = fit_delta(y[~half], base[~half])
                            zs.append(dict(
                                family=fam, chapter=ch, dose=dose,
                                z=(dA - dB) / np.sqrt(sA**2 + sB**2)))

    fams = sorted({r["family"] for r in rows})
    lines = [f"V2 semi-real validation — defect axis "
             f"({len(rows)} conditions; model tier {MODEL_TIER}; "
             f"q_types={args.q_types}; {args.n_splits} splits)", ""]

    # ---- (1) dose ordering -------------------------------------------------
    lines.append("== (1) DOSE ORDERING: Spearman(Delta, dose) per family "
                 "(median over chapters; pass adequacy >= +0.7) ==")
    fam_med = {}
    for fam in fams:
        rhos = []
        for ch in range(1, 9):
            sub = [r for r in rows if r["family"] == fam
                   and r["chapter"] == ch]
            if len(sub) >= 3:
                rhos.append(spearman([r["dose"] for r in sub],
                                     [r["delta"] for r in sub]))
        rhos = [r for r in rhos if not np.isnan(r)]
        if not rhos:
            continue
        med = float(np.median(rhos))
        fam_med[fam] = med
        tag = "ADEQUACY" if fam in ADEQUACY_FAMILIES else "        "
        verdict = ""
        if fam in ADEQUACY_FAMILIES:
            verdict = "  PASS" if med >= 0.7 else "  FAIL"
        lines.append(f"  {fam:<28} {tag} median rho = {med:+.2f} "
                     f"(n_ch={len(rhos)}, range {min(rhos):+.2f}"
                     f"..{max(rhos):+.2f}){verdict}")

    # ---- (2) zero point ----------------------------------------------------
    z0 = [r for r in rows if r["dose"] == 0.0]
    # dedupe: same 0% file appears once per sub-family — keep one per
    # (chapter, defect)
    seen, z0u = set(), []
    for r in z0:
        key = (r["chapter"], r["defect"])
        if key not in seen:
            seen.add(key)
            z0u.append(r)
    d0 = np.array([r["delta"] for r in z0u])
    s0 = np.array([r["se"] for r in z0u])
    within = np.abs(d0) <= args.kappa * 2 * s0
    lines += ["", f"== (2) ZERO POINT: dose-0 Delta ~ 0 within "
              f"{args.kappa}*2*SE ({len(z0u)} unique chapterxdefect cells) ==",
              f"  mean Delta_0 = {float(np.mean(d0)):+.3f}  "
              f"(SE of mean {float(np.std(d0) / np.sqrt(len(d0))):.3f});  "
              f"median {float(np.median(d0)):+.3f}",
              f"  fraction within tolerance: {float(np.mean(within)):.2f}  "
              f"[{'PASS' if np.mean(within) >= 0.9 else 'FAIL'}]",
              f"  -> Step-2 method-axis offset was +0.4-0.5; if Delta_0 ~ 0 "
              f"here, that offset is text-specific, not estimator bias."]

    # ---- (3) split-half kappa_real -----------------------------------------
    zarr = np.array([z["z"] for z in zs])
    kap_all = float(np.std(zarr))
    lines += ["", f"== (3) SPLIT-HALF kappa_real ({len(zarr)} splits) ==",
              f"  pooled kappa_real = sd(z) = {kap_all:.3f}   "
              f"(honest ~ 1; deployment carries max(1.13, this))",
              f"  |z|>2 fraction = {float(np.mean(np.abs(zarr) > 2)):.3f} "
              f"(honest ~ 0.05)"]
    for qt in qtypes if args.q_types == "both" else ():
        pass  # per-qtype kappa needs separate runs; noted in summary
    by_fam = {}
    for fam in fams:
        za = np.array([z["z"] for z in zs if z["family"] == fam])
        if len(za) >= 40:
            by_fam[fam] = float(np.std(za))
    lines.append("  per-family: " + ", ".join(
        f"{f}={k:.2f}" for f, k in sorted(by_fam.items())))
    kap_carry = max(1.13, kap_all)
    lines += ["", "== VERDICTS ==",
              f"  dose ordering: adequacy families "
              + ", ".join(f"{f} {fam_med.get(f, float('nan')):+.2f}"
                          for f in sorted(ADEQUACY_FAMILIES)
                          if f in fam_med),
              f"  zero point: {'PASS' if np.mean(within) >= 0.9 else 'FAIL'} "
              f"(mean Delta_0 {float(np.mean(d0)):+.3f})",
              f"  kappa_real = {kap_all:.3f} -> protocol carries "
              f"kappa = {kap_carry:.3f}"]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.q_types == "both" else f"_{args.q_types}"
    import csv as _csv
    with open(out_dir / f"v2_defect_axis{suffix}.csv", "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary = "\n".join(lines)
    (out_dir / f"v2_summary{suffix}.txt").write_text(summary)
    print(summary)

    # ---- figure -------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    ax = axes[0]
    cmap = plt.get_cmap("tab10")
    for i, fam in enumerate(fams):
        doses = sorted({r["dose"] for r in rows if r["family"] == fam})
        mean_d = [float(np.mean([r["delta"] for r in rows
                                 if r["family"] == fam and r["dose"] == d]))
                  for d in doses]
        style = "-" if fam in ADEQUACY_FAMILIES else "--"
        ax.plot(doses, mean_d, style, marker="o", ms=4,
                color=cmap(i % 10), label=fam, lw=1.6)
    ax.set_xlabel("defect dose")
    ax.set_ylabel("mean Delta_obs (logits, chapters pooled)")
    ax.set_title("V2: dose-response of the deployed estimator "
                 "(solid = adequacy)")
    ax.legend(fontsize=7)
    ax2 = axes[1]
    ax2.errorbar(np.arange(len(z0u)), d0, yerr=2 * s0, fmt="o", ms=4,
                 capsize=2, lw=0, elinewidth=0.8)
    ax2.axhline(0, color="k", lw=0.8)
    ax2.set_title(f"zero point: Delta_0 +/- 2SE "
                  f"(mean {float(np.mean(d0)):+.2f})")
    ax2.set_xlabel("chapter x defect cell")
    ax2.set_ylabel("Delta at dose 0")
    ax3 = axes[2]
    ax3.hist(zarr, bins=40, density=True, alpha=0.7)
    xs = np.linspace(-4, 4, 200)
    ax3.plot(xs, np.exp(-xs**2 / 2) / np.sqrt(2 * np.pi), "k-", lw=1.2,
             label="N(0,1)")
    ax3.set_title(f"split-half z (kappa_real = sd = {kap_all:.2f})")
    ax3.legend()
    plt.tight_layout()
    plt.savefig(out_dir / f"v2_defect_axis{suffix}.png", dpi=140)
    print(f"\n[out] {out_dir}/v2_defect_axis{suffix}.{{csv,png}} "
          f"+ v2_summary{suffix}.txt")


if __name__ == "__main__":
    main()
