#!/usr/bin/env python3
"""First-cut calibration of the OPEN-QUESTION CANARY threshold for the
fluency-saturation guardrail (EXPERIMENT_BURDEN_MQM_BRIDGE.md §5, §8.5).

Signature to detect: MCQ accuracy fine while OPEN accuracy collapses —
the google_word_by_word (wbw) pattern (content words survive word-by-word
translation, syntax doesn't; MCQ = recognition, open = production).

Divergence statistic per (model x method x chapter) cell, computed directly
from score files (deployment-friendly — no IRT needed):

    gap = acc_mcq − acc_open        (per-model z-scored variant reported too,
                                     since the baseline gap differs by model)

Positives = wbw cells; negatives = the other 7 methods. Threshold = per-model
95th percentile of the negative distribution; report wbw detection rate and
false-alarm rate at that threshold, plus a pooled-z variant. ALSO checks the
30% grammar/awkward defect-variant cells (1.7b): modest-dose fluency damage
should NOT trigger the canary (specificity against sub-saturation fluency).

Outputs (QA_algorithm/outputs/reports/adequacy_burden/):
  canary_firstcut.csv / canary_firstcut.txt / canary_firstcut.png
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

QA_ROOT = Path(__file__).resolve().parents[2]
REPO = QA_ROOT.parent
EVAL_OUT = REPO / "evaluation" / "outputs"
OUT_DIR = QA_ROOT / "outputs" / "reports" / "adequacy_burden"

MODELS = ["llama 1b", "1.5b", "1.7b"]
METHODS = ["google_word_by_word", "helsinki", "llm_prompt_high",
           "llm_prompt_low", "llm_prompt_medium", "mBART-50",
           "nllb-200-1.3B", "nllb-200-distilled-600M"]
POSITIVE = "google_word_by_word"
FLUENCY_VARIANTS = [("grammar", "30%"), ("awkward", "30%")]  # 1.7b tier


def cell_gap(score_file):
    d = json.load(open(score_file))
    mcq, opn = [], []
    for it in d["items"]:
        if it["q_type"] == "mcq":
            mcq.append(1.0 if it["direct_correct"] else 0.0)
        elif it["q_type"] == "open" and it["llm_score"] is not None:
            opn.append(float(it["llm_score"]))
    if len(mcq) < 4 or len(opn) < 4:
        return None
    return dict(acc_mcq=float(np.mean(mcq)), acc_open=float(np.mean(opn)),
                gap=float(np.mean(mcq) - np.mean(opn)),
                n_mcq=len(mcq), n_open=len(opn))


def main():
    rows = []
    for model in MODELS:
        for method in METHODS:
            for ch in range(1, 9):
                sf = (EVAL_OUT / f"luke{ch}" / model / method /
                      "scores_target_llama.json")
                if not sf.exists():
                    continue
                g = cell_gap(sf)
                if g:
                    rows.append(dict(model=model, kind="method",
                                     method=method, chapter=ch, **g))
    # modest-dose fluency variants (should NOT trigger)
    for fam, lev in FLUENCY_VARIANTS:
        for ch in range(1, 9):
            sf = EVAL_OUT / f"luke{ch}" / "1.7b" / fam / lev / \
                "scores_target_llama.json"
            if sf.exists():
                g = cell_gap(sf)
                if g:
                    rows.append(dict(model="1.7b", kind="variant",
                                     method=f"{fam}_{lev}", chapter=ch, **g))

    lines = ["Open-canary threshold — first cut from existing wbw cells", ""]
    lines.append(f"{'model':<10}{'neg mean gap':>13}{'neg sd':>8}"
                 f"{'thr(95%)':>10}{'wbw hit':>9}{'FA rate':>9}")
    thr_by_model = {}
    for model in MODELS:
        neg = [r["gap"] for r in rows if r["model"] == model
               and r["kind"] == "method" and r["method"] != POSITIVE]
        pos = [r["gap"] for r in rows if r["model"] == model
               and r["method"] == POSITIVE]
        thr = float(np.percentile(neg, 95))
        thr_by_model[model] = thr
        hit = float(np.mean([g > thr for g in pos]))
        fa = float(np.mean([g > thr for g in neg]))
        lines.append(f"{model:<10}{float(np.mean(neg)):>+13.3f}"
                     f"{float(np.std(neg)):>8.3f}{thr:>10.3f}"
                     f"{hit:>9.2f}{fa:>9.2f}   (n_neg={len(neg)}, "
                     f"n_pos={len(pos)})")

    # pooled z-scored variant
    z_rows = []
    for model in MODELS:
        neg = np.array([r["gap"] for r in rows if r["model"] == model
                        and r["kind"] == "method"
                        and r["method"] != POSITIVE])
        mu, sd = float(np.mean(neg)), float(np.std(neg))
        for r in rows:
            if r["model"] == model:
                r["gap_z"] = (r["gap"] - mu) / sd
                z_rows.append(r)
    posz = [r["gap_z"] for r in z_rows if r["method"] == POSITIVE]
    negz = [r["gap_z"] for r in z_rows if r["kind"] == "method"
            and r["method"] != POSITIVE]
    for zthr in (1.5, 2.0, 2.5):
        hit = float(np.mean([z > zthr for z in posz]))
        fa = float(np.mean([z > zthr for z in negz]))
        lines.append(f"pooled z > {zthr}: wbw detection {hit:.2f}, "
                     f"false alarm {fa:.3f}")

    # AUC (pooled z)
    allz = sorted(set(posz + negz))
    auc = float(np.mean([[pz > nz for nz in negz].count(True) +
                         0.5 * [pz == nz for nz in negz].count(True)
                         for pz in posz]) / len(negz))
    lines.append(f"AUC (wbw vs rest, pooled z) = {auc:.3f}")

    # specificity check: modest-dose fluency variants
    varz = [r for r in z_rows if r["kind"] == "variant"]
    if varz:
        lines += ["", "specificity — 30% grammar/awkward variants "
                  "(modest dose, should NOT trigger):"]
        for fam in sorted({r["method"] for r in varz}):
            zz = [r["gap_z"] for r in varz if r["method"] == fam]
            lines.append(f"  {fam:<14} mean z = {float(np.mean(zz)):+.2f}; "
                         f"frac > 2.0 = {float(np.mean([z > 2 for z in zz])):.2f} "
                         f"(n={len(zz)})")

    # translation-level (chapters pooled) — the reliable aggregation level
    lines += ["", "translation level (chapters pooled per model x method):"]
    from collections import defaultdict
    agg = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for r in rows:
        if r["kind"] != "method":
            continue
        a = agg[(r["model"], r["method"])]
        a[0] += r["acc_mcq"] * r["n_mcq"]
        a[1] += r["n_mcq"]
        a[2] += r["acc_open"] * r["n_open"]
        a[3] += r["n_open"]
    for model in MODELS:
        gaps = {me: a[0] / a[1] - a[2] / a[3]
                for (mo, me), a in agg.items() if mo == model}
        neg = [v for k, v in gaps.items() if k != POSITIVE]
        mu, sd = float(np.mean(neg)), float(np.std(neg))
        zw = (gaps[POSITIVE] - mu) / sd
        lines.append(f"  {model:<10} wbw gap {gaps[POSITIVE]:+.3f}  "
                     f"z = {zw:+.1f}  "
                     f"({'DETECTED' if zw > 2 else 'not detected'})")
    lines += ["", "PROVISIONAL RULE: canary operates at TRANSLATION level "
              "(pool >=~8 passages / ~150+ open answers): flag when "
              "z of (acc_mcq − acc_open) vs reference conditions > 2-3. "
              "Per-chapter gaps are too noisy (AUC ~0.66). REQUIREMENT: "
              "respondents must be above the open-question floor (llama-1b "
              "shows no signal — open acc at floor everywhere). Calibrate "
              "final threshold with the high-dose open-scored fluency "
              "ladder (burden doc §7.1)."]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "canary_firstcut.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(z_rows[0].keys()))
        w.writeheader()
        w.writerows(z_rows)
    (OUT_DIR / "canary_firstcut.txt").write_text("\n".join(lines))
    print("\n".join(lines))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(negz, bins=30, alpha=0.6, density=True,
            label="other 7 methods (negatives)")
    ax.hist(posz, bins=15, alpha=0.6, density=True,
            label="google_word_by_word (positives)")
    if varz:
        ax.hist([r["gap_z"] for r in varz], bins=10, alpha=0.5, density=True,
                label="30% grammar/awkward variants")
    ax.axvline(2.0, color="k", ls="--", lw=1, label="z = 2 provisional")
    ax.set_xlabel("per-model z of (acc_mcq − acc_open)")
    ax.set_ylabel("density")
    ax.set_title(f"Open-canary divergence, AUC={auc:.2f}")
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "canary_firstcut.png", dpi=140)
    print(f"\n[out] {OUT_DIR}/canary_firstcut.{{csv,png,txt}}")


if __name__ == "__main__":
    main()
