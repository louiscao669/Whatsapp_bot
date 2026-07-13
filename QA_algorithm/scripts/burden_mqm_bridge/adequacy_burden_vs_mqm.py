#!/usr/bin/env python3
"""Step 1 of the MQM defect-vector program (see EXPERIMENT_H3 §15 planning):

Expand each translation's scalar MQM score into its per-category defect vector,
weight it by the CALIBRATED family sensitivities lambda_g (from the synthetic
defect-variant dose grids), and compare the resulting adequacy-weighted burden
B_T with MQM's own severity-weighted scalar.

    B_T = sum_g  lambda_g * rate_{T,g}

Severity brackets (the calibration was done at generator-grade severity, MQM
grades minor/major/critical — unresolved a priori, so bracket it):
  B_count   — rate = raw error count per 1000 source words   (severity-blind)
  B_penalty — rate = MQM severity-weighted penalty per 1000  (imports MQM 1/5/10)

Category -> calibrated-family mapping (documented assumption):
  accuracy_omission        -> omission
  accuracy_mistranslation  -> mistranslation
  accuracy_addition        -> mean(addition:bad, addition:neutral)  [natural, not adversarial]
  fluency_grammar          -> grammar
  terminology              -> inconsistency:name  (~0)
  untranslated_non_translation -> omission (meaning lost; family never QA-scored)
                                  ... plus a sensitivity variant mapped to 0
  other                    -> 0

Inputs:
  evaluation/outputs/reports/mqm_translation_scores_1.7b_MERGED_luke1_8.csv
  QA_algorithm/outputs/reports/item_sensitivity/s_item_by_defect.csv (q_var_ok)

Outputs (QA_algorithm/outputs/reports/adequacy_burden/):
  step1_burden_vs_mqm.csv     per (chapter x method) burden components + scalars
  step1_summary.txt           correlations + method-rank comparison
  step1_burden_vs_mqm.png     scatter + per-method rank shift
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

QA_ROOT = Path(__file__).resolve().parents[2]
REPO = QA_ROOT.parent
MQM_CSV = REPO / "evaluation" / "outputs" / "reports" / \
    "mqm_translation_scores_1.7b_MERGED_luke1_8.csv"
S_CSV = QA_ROOT / "outputs" / "reports" / "item_sensitivity" / "s_item_by_defect.csv"
OUT_DIR = QA_ROOT / "outputs" / "reports" / "adequacy_burden"

# MQM category -> (calibrated families to average for lambda)
CATEGORY_MAP = {
    "accuracy_omission": ["omission"],
    "accuracy_mistranslation": ["mistranslation"],
    "accuracy_addition": ["addition:bad", "addition:neutral"],
    "fluency_grammar": ["grammar"],
    "terminology": ["inconsistency:name"],
    "untranslated_non_translation": ["omission"],  # sensitivity variant: 0
    "other": [],  # lambda = 0
}


def family_lambdas():
    with open(S_CSV) as f:
        rows = [r for r in csv.DictReader(f)
                if r["q_var_ok"].strip().lower() in ("1", "true")]
    fams = {}
    for r in rows:
        fams.setdefault(r["defect"], []).append(float(r["s_i"]))
    return {f: float(np.mean(v)) for f, v in fams.items()}


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    lam = family_lambdas()
    cat_lam = {}
    for cat, fams in CATEGORY_MAP.items():
        cat_lam[cat] = float(np.mean([lam[f] for f in fams])) if fams else 0.0
    print("[lambda per MQM category]")
    for c, v in cat_lam.items():
        print(f"  {c:<30} lambda={v:+.3f}   (from {CATEGORY_MAP[c] or ['-']})")

    with open(MQM_CSV) as f:
        rows = list(csv.DictReader(f))

    out = []
    for r in rows:
        words = float(r["source_words"])
        rec = {"chapter": int(r["chapter"]), "method": r["method"],
               "source_words": words,
               "mqm_penalty_per_1000": float(r["penalty_per_1000_words"]),
               "mqm_quality_0_1": float(r["mqm_quality_0_1"])}
        b_cnt = b_pen = 0.0
        b_cnt_u0 = b_pen_u0 = 0.0  # sensitivity: untranslated -> lambda 0
        for cat, lg in cat_lam.items():
            cnt = float(r[f"{cat}_count"]) / words * 1000
            pen = float(r[f"{cat}_penalty"]) / words * 1000
            rec[f"{cat}_count_rate"] = round(cnt, 4)
            rec[f"{cat}_penalty_rate"] = round(pen, 4)
            b_cnt += lg * cnt
            b_pen += lg * pen
            lg_u = 0.0 if cat == "untranslated_non_translation" else lg
            b_cnt_u0 += lg_u * cnt
            b_pen_u0 += lg_u * pen
        rec.update(B_count=round(b_cnt, 4), B_penalty=round(b_pen, 4),
                   B_count_untr0=round(b_cnt_u0, 4),
                   B_penalty_untr0=round(b_pen_u0, 4))
        out.append(rec)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "step1_burden_vs_mqm.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    # ---- summary: correlations (against MQM scalar penalty; higher = worse)
    mqm = np.array([r["mqm_penalty_per_1000"] for r in out])
    lines = ["Step 1: adequacy-weighted burden vs scalar MQM  "
             f"({len(out)} chapter x method cells)", ""]
    for col in ("B_count", "B_penalty", "B_count_untr0", "B_penalty_untr0"):
        b = np.array([r[col] for r in out])
        lines.append(f"{col:<16} Spearman={spearman(b, mqm):+.3f}  "
                     f"Pearson={float(np.corrcoef(b, mqm)[0, 1]):+.3f}")

    # ---- per-method mean ranks (within chapter), B vs MQM
    methods = sorted({r["method"] for r in out})
    chaps = sorted({r["chapter"] for r in out})
    rank_b, rank_m = {m: [] for m in methods}, {m: [] for m in methods}
    for ch in chaps:
        sub = [r for r in out if r["chapter"] == ch]
        for key, store in (("B_count", rank_b), ("mqm_penalty_per_1000", rank_m)):
            order = sorted(sub, key=lambda r: r[key])  # low burden = rank 1 (best)
            for i, r in enumerate(order):
                store[r["method"]].append(i + 1)
    lines += ["", f"{'method':<22} {'meanrank_B':>10} {'meanrank_MQM':>12} "
              f"{'shift':>6}   adequacy_share_of_penalty"]
    for m in methods:
        sub = [r for r in out if r["method"] == m]
        adeq = np.mean([(r["accuracy_omission_penalty_rate"]
                         + r["accuracy_mistranslation_penalty_rate"]
                         + r["accuracy_addition_penalty_rate"]
                         + r["untranslated_non_translation_penalty_rate"])
                        / max(1e-9, r["mqm_penalty_per_1000"]) for r in sub])
        rb, rm = np.mean(rank_b[m]), np.mean(rank_m[m])
        lines.append(f"{m:<22} {rb:>10.2f} {rm:>12.2f} {rb - rm:>+6.2f}   {adeq:.2f}")
    lines += ["", "shift < 0: method looks BETTER under adequacy weighting than "
              "under MQM (fluency-dominated errors); shift > 0: worse (adequacy-"
              "dominated)."]

    summary = "\n".join(lines)
    (OUT_DIR / "step1_summary.txt").write_text(summary)
    print("\n" + summary)

    # ---- figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    cmap = plt.get_cmap("tab10")
    for i, m in enumerate(methods):
        sub = [r for r in out if r["method"] == m]
        ax.scatter([r["mqm_penalty_per_1000"] for r in sub],
                   [r["B_count"] for r in sub],
                   color=cmap(i % 10), label=m, s=28)
    ax.set_xlabel("MQM severity-weighted penalty / 1000 words (higher = worse)")
    ax.set_ylabel("adequacy-weighted burden B_count (higher = worse)")
    ax.set_title("Per-cell: B vs scalar MQM")
    ax.legend(fontsize=7.5)
    xs = np.arange(len(methods))
    order = np.argsort([np.mean(rank_m[m]) for m in methods])
    ax2.plot([np.mean(rank_m[methods[i]]) for i in order], xs, "o-",
             label="MQM rank", color="crimson")
    ax2.plot([np.mean(rank_b[methods[i]]) for i in order], xs, "s--",
             label="B_count rank", color="steelblue")
    ax2.set_yticks(xs)
    ax2.set_yticklabels([methods[i] for i in order], fontsize=8.5)
    ax2.set_xlabel("mean within-chapter rank (1 = best)")
    ax2.set_title("Method ranking: MQM vs adequacy burden")
    ax2.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "step1_burden_vs_mqm.png", dpi=140)
    print(f"\n[out] {OUT_DIR}/step1_burden_vs_mqm.{{csv,png}} + step1_summary.txt")


if __name__ == "__main__":
    main()
