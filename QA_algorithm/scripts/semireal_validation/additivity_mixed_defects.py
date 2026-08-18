#!/usr/bin/env python3
"""Additivity analysis for the MIXED-DEFECT campaign
(EXPERIMENT_BURDEN_MQM_BRIDGE.md §7.2; variants generated + answered by
evaluation/scripts/campaigns/run_mixed_defect_campaign.sh).

MODEL UNDER TEST: defects add in the logit —
    Delta(A@dA + B@dB) = Delta(A@dA) + Delta(B@dB)      (all relative to 0%)

For every mixed cell luke{ch}/<tier>/mixed/<A><dA>_<B>/<level>:
    I = (D_AB - D_0) - (D_A - D_0) - (D_B - D_0)
      = D_AB + D_0 - D_A - D_B
  with D_* = 1PL common logit shift fitted on that condition's responses
  (anchor theta/b, same estimator as V2/Step 2), and D_0 = precision-weighted
  mean of the two defects' 0% baselines for that chapter.
  SE(I) via quadrature. I > 0: superadditive (worse than predicted);
  I < 0: subadditive (damage overlaps/saturates).

AGGREGATION: precision-weighted mean interaction per (pair x dose combo)
across chapters, plus pooled per pair and overall. Verdicts:
  ADDITIVE       — |pooled I| < 2 SE and |pooled I| < MARGIN (0.3 logits)
  SUPER/SUBADDITIVE — pooled |I| > 2 SE
  UNDERPOWERED   — SE too large to bound within MARGIN

Usage:
  python3 QA_algorithm/scripts/semireal_validation/additivity_mixed_defects.py
      [--tier 1.7b] [--q-types both|mcq|open] [--margin 0.3]
Outputs (QA_algorithm/outputs/reports/adequacy_burden/):
  additivity_mixed.csv / additivity_mixed.txt / additivity_mixed.png
"""

from __future__ import annotations

import argparse
import csv
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

PRIOR_SD = 3.0
MIX_RE = re.compile(r"^([a-z_]+?)(\d+)_([a-z_]+)$")   # <A><dA>_<B>
LEV_RE = re.compile(r"^(?:([a-z]+)_)?(\d+(?:\.\d+)?)%$")  # [cat_]<dB>%


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


def load_and_fit(score_path, ch, qtypes, theta, bmap):
    if not score_path.exists():
        return None
    y, base = [], []
    for it in json.load(open(score_path))["items"]:
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
    if len(y) < 6:
        return None
    d, se = fit_delta(y, np.array(base))
    return d, se, len(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="1.7b",
                    help="answer-model tier dir ('1.7b', 'llama 1b', '1.5b')")
    ap.add_argument("--q-types", choices=("both", "mcq", "open"),
                    default="both")
    ap.add_argument("--margin", type=float, default=0.3,
                    help="equivalence margin (logits) for the ADDITIVE verdict")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    qtypes = ("mcq", "open") if args.q_types == "both" else (args.q_types,)

    theta, bmap = {}, {}
    for qt, path in ANCHOR.items():
        d = json.load(open(path))
        theta[qt] = float(d["model_abilities"][args.tier]["theta"]) \
            if args.tier in d["model_abilities"] else None
        if theta[qt] is None:
            raise SystemExit(f"tier '{args.tier}' not in anchor ladder")
        bmap[qt] = {k: float(v["b_posterior"])
                    for k, v in d["item_difficulties"].items()}

    def single_path(ch, defect, level):
        return EVAL_OUT / f"luke{ch}" / args.tier / defect / level / \
            "scores_target_llama.json"

    rows = []
    for ch in range(1, 9):
        mixroot = EVAL_OUT / f"luke{ch}" / args.tier / "mixed"
        if not mixroot.is_dir():
            continue
        for mixdir in sorted(p for p in mixroot.iterdir() if p.is_dir()):
            m = MIX_RE.match(mixdir.name)
            if not m:
                continue
            A, dA, B = m.group(1), m.group(2), m.group(3)
            for levdir in sorted(p for p in mixdir.iterdir() if p.is_dir()):
                lv = LEV_RE.match(levdir.name)
                if not lv:
                    continue
                cat, dB = lv.group(1), lv.group(2)
                # singles: A@dA, B@dB (addition levels are '<cat>_<dB>%')
                a_lev = f"{dA}%"
                b_lev = f"{cat}_{dB}%" if cat else f"{dB}%"
                fits = {}
                fits["AB"] = load_and_fit(
                    levdir / "scores_target_llama.json", ch, qtypes,
                    theta, bmap)
                fits["A"] = load_and_fit(single_path(ch, A, a_lev), ch,
                                         qtypes, theta, bmap)
                fits["B"] = load_and_fit(single_path(ch, B, b_lev), ch,
                                         qtypes, theta, bmap)
                # baseline: precision-weighted mean of the two defects' 0%
                zeros = [load_and_fit(single_path(ch, dd, "0%"), ch, qtypes,
                                      theta, bmap) for dd in (A, B)]
                zeros = [z for z in zeros if z]
                if not all(fits.values()) or not zeros:
                    continue
                w0 = np.array([1.0 / z[1]**2 for z in zeros])
                d0 = float(np.sum(w0 * [z[0] for z in zeros]) / np.sum(w0))
                se0 = float(1.0 / np.sqrt(np.sum(w0)))
                (dAB, seAB, nAB) = fits["AB"]
                (dA_, seA, _) = fits["A"]
                (dB_, seB, _) = fits["B"]
                inter = dAB + d0 - dA_ - dB_
                se_i = float(np.sqrt(seAB**2 + se0**2 + seA**2 + seB**2))
                rows.append(dict(
                    chapter=ch, pair=f"{A}+{B}", dA=f"{dA}%",
                    dB=(f"{cat}_{dB}%" if cat else f"{dB}%"),
                    delta_AB=dAB, delta_A=dA_, delta_B=dB_, delta_0=d0,
                    interaction=inter, se=se_i, n_items=nAB))

    if not rows:
        raise SystemExit(
            "No mixed cells with scores found — run the campaign first:\n"
            "  bash evaluation/scripts/campaigns/run_mixed_defect_campaign.sh generate\n"
            "  bash evaluation/scripts/campaigns/run_mixed_defect_campaign.sh answer")

    lines = [f"Mixed-defect additivity (tier={args.tier}, "
             f"q_types={args.q_types}, {len(rows)} cells, "
             f"margin={args.margin})", ""]

    def agg(sub):
        w = np.array([1.0 / r["se"]**2 for r in sub])
        i = np.array([r["interaction"] for r in sub])
        mean = float(np.sum(w * i) / np.sum(w))
        se = float(1.0 / np.sqrt(np.sum(w)))
        return mean, se

    def verdict(mean, se):
        if abs(mean) > 2 * se:
            return "SUPERADDITIVE" if mean > 0 else "SUBADDITIVE"
        if abs(mean) + 2 * se < args.margin:
            return "ADDITIVE (within margin)"
        return "underpowered"

    lines.append(f"{'pair':<28}{'doses':<18}{'I (logits)':>12}{'SE':>7}"
                 f"{'n_ch':>6}   verdict")
    pairs = sorted({r["pair"] for r in rows})
    for pair in pairs:
        combos = sorted({(r["dA"], r["dB"]) for r in rows
                         if r["pair"] == pair})
        for dA, dB in combos:
            sub = [r for r in rows if r["pair"] == pair
                   and r["dA"] == dA and r["dB"] == dB]
            mean, se = agg(sub)
            lines.append(f"{pair:<28}{dA + ' x ' + dB:<18}{mean:>+12.3f}"
                         f"{se:>7.3f}{len(sub):>6}   {verdict(mean, se)}")
        mean, se = agg([r for r in rows if r["pair"] == pair])
        lines.append(f"{pair:<28}{'POOLED':<18}{mean:>+12.3f}{se:>7.3f}"
                     f"{'':>6}   {verdict(mean, se)}")
        lines.append("")
    mean, se = agg(rows)
    lines += [f"{'ALL PAIRS':<28}{'POOLED':<18}{mean:>+12.3f}{se:>7.3f}"
              f"{'':>6}   {verdict(mean, se)}",
              "",
              "I > 0: superadditive (stacked damage worse than sum) — "
              "threshold transfer from singles UNDERSTATES damage.",
              "I < 0: subadditive (overlap/saturation) — thresholds "
              "OVERSTATE damage; consider a saturating combination rule.",
              "ADDITIVE pooled verdict => absolute-threshold claims "
              "(burden doc §3) are re-licensed at these doses."]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.q_types == "both" else f"_{args.q_types}"
    tier_tag = args.tier.replace(" ", "")
    with open(out_dir / f"additivity_mixed_{tier_tag}{suffix}.csv", "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (out_dir / f"additivity_mixed_{tier_tag}{suffix}.txt").write_text(
        "\n".join(lines))
    print("\n".join(lines))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 5.5))
    xt, labels = 0, []
    for pair in pairs:
        combos = sorted({(r["dA"], r["dB"]) for r in rows
                         if r["pair"] == pair})
        for dA, dB in combos:
            sub = [r for r in rows if r["pair"] == pair
                   and r["dA"] == dA and r["dB"] == dB]
            mean, se = agg(sub)
            ax.errorbar([xt], [mean], yerr=[2 * se], fmt="o", capsize=3)
            ax.scatter([xt] * len(sub), [r["interaction"] for r in sub],
                       s=10, alpha=0.4, color="grey")
            labels.append(f"{pair}\n{dA}x{dB}")
            xt += 1
    ax.axhline(0, color="k", lw=0.8)
    ax.axhspan(-args.margin, args.margin, color="green", alpha=0.08,
               label=f"additive margin ±{args.margin}")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=6.5, rotation=45, ha="right")
    ax.set_ylabel("interaction I (logits) ± 2SE")
    ax.set_title(f"Mixed-defect additivity — tier {args.tier}")
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(out_dir / f"additivity_mixed_{tier_tag}{suffix}.png", dpi=140)
    print(f"\n[out] {out_dir}/additivity_mixed_{tier_tag}{suffix}.*")


if __name__ == "__main__":
    main()
