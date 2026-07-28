#!/usr/bin/env python3
"""New-regime (3-verse window) ability-θ recompute + dose-ordering separability — matched to H-T4.

At the window the ability structure COMPRESSED (clean-cell 1.5b≈1.7b), so the old 07-12 anchor θ
and the old V4 MT-method separability verdict are the wrong benchmark for the pilot's H-T4.
This recomputes, on scores_target_window3_v2.json (the 7 pilot conditions ONLY):

  (1) per-model ability θ̂ on the CLEAN cell (omission/0%) as logit(mean acc), MCQ & open;
  (2) condition-level quality per model + pairwise cross-model Spearman = separability
      (do the models agree on which conditions are worse, i.e. is quality separable from
      the respondent?); the old V4 pattern was ONE model deviant (ρ≈+0.07/+0.43 vs +0.88);
  (3) omission dose-monotonicity per model (0>10>20>30);
  (4) dynamic range per model (spread across conditions) — the low- vs high-ability check.

Low-powered BY DESIGN (3 models, 7 conditions / 4-pt omission ladder): a matched-regime,
suggestive read — NOT the high-powered 8-MT-method battery (which the new data can't
reproduce and the pilot never tests). If separability looks weaker here than old, that is a
finding that STRENGTHENS "aggregate over diverse respondents", not a bug.

  python evaluation/scripts/separability_window3.py
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "evaluation" / "outputs"
SCORE = "scores_target_window3_v2.json"
MODELS = ["llama 1b", "1.5b", "1.7b"]
CONDS = ["omission/0%", "omission/10%", "omission/20%", "omission/30%",
         "mistranslation/20%", "grammar/30%", "google_word_by_word"]
OMISSION = ["omission/0%", "omission/10%", "omission/20%", "omission/30%"]


def rankdata(a):
    a = np.asarray(a, float); n = len(a)
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(n); ranks[order] = np.arange(1, n + 1)
    sa = a[order]; i = 0
    while i < n:                                    # average tied ranks
        j = i
        while j + 1 < n and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return ranks


def spearman(x, y):
    rx, ry = rankdata(x), rankdata(y)
    rx = rx - rx.mean(); ry = ry - ry.mean()
    den = math.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / den) if den > 0 else float("nan")


def logit(p):
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def cell_scores(model, cond):
    """pooled over 8 chapters -> (mcq_acc, open_mean, combined_mean, n)."""
    mcq, opn = [], []
    for ch in range(1, 9):
        fp = EVAL / f"luke{ch}" / model / cond / SCORE
        if not fp.exists():
            continue
        for it in json.loads(fp.read_text()).get("items", []):
            if it.get("q_type") == "mcq":
                dc = it.get("direct_correct")
                if dc is not None:
                    mcq.append(1.0 if dc else 0.0)
            else:
                v = it.get("llm_score")
                if v is not None:
                    opn.append(float(min(1.0, max(0.0, v))))
    allv = mcq + opn
    m = lambda x: sum(x) / len(x) if x else float("nan")
    return m(mcq), m(opn), m(allv), len(allv)


def main():
    # table[model][cond] = (mcq, open, combined, n)
    table = {mo: {c: cell_scores(mo, c) for c in CONDS} for mo in MODELS}

    # ---- (1) ability θ̂ on the clean cell ----
    print("=" * 74)
    print("(1) NEW-regime ability θ̂  (clean cell = omission/0%, θ = logit(mean acc))")
    print("=" * 74)
    print(f"{'model':10}{'MCQ acc':>9}{'θ_mcq':>8}{'open':>8}{'θ_open':>9}")
    for mo in MODELS:
        mcq, opn, _, _ = table[mo]["omission/0%"]
        print(f"{mo:10}{mcq:>9.3f}{logit(mcq):>8.2f}{opn:>8.3f}{logit(opn):>9.2f}")
    print("  → compare to OLD ladder 1b<1.5b<1.7b; watch for 1.5b≈1.7b compression.")

    # ---- (2) separability: cross-model Spearman on condition-level quality ----
    print("\n" + "=" * 74)
    print("(2) Separability — do models agree on the condition quality ordering?")
    print("=" * 74)
    vecs = {mo: np.array([table[mo][c][2] for c in CONDS]) for mo in MODELS}
    print("  per-condition COMBINED score:")
    print(f"    {'condition':22}" + "".join(f"{mo:>11}" for mo in MODELS))
    for i, c in enumerate(CONDS):
        print(f"    {c:22}" + "".join(f"{vecs[mo][i]:>11.3f}" for mo in MODELS))
    print("\n  pairwise Spearman (rank agreement across the 7 conditions):")
    pairs = [("llama 1b", "1.5b"), ("llama 1b", "1.7b"), ("1.5b", "1.7b")]
    rhos = {}
    for a, b in pairs:
        r = spearman(vecs[a], vecs[b]); rhos[(a, b)] = r
        print(f"    ρ({a:8} , {b:6}) = {r:+.3f}")
    lo = min(rhos.values())
    verdict = ("SEPARABLE (all pairs agree)" if lo >= 0.7 else
               "PARTIAL FAIL (a model reorders conditions)" if lo >= 0.3 else
               "FAIL (models disagree on ordering)")
    print(f"  → min pairwise ρ = {lo:+.3f}  ⇒  {verdict}")
    print("    (old V4 whole-passage / 8-MT-methods: one model deviant, ρ +0.07/+0.43 vs +0.88)")

    # ---- (3) omission dose monotonicity per model ----
    print("\n" + "=" * 74)
    print("(3) Omission dose-monotonicity per model (0>10>20>30 on COMBINED)")
    print("=" * 74)
    for mo in MODELS:
        seq = [table[mo][c][2] for c in OMISSION]
        mono = all(seq[i] > seq[i + 1] for i in range(3))
        print(f"  {mo:10} {['%.3f' % s for s in seq]}  strictly-decreasing={mono}")

    # ---- (4) dynamic range per model (low- vs high-ability) ----
    print("\n" + "=" * 74)
    print("(4) Dynamic range across conditions (max−min COMBINED) by ability")
    print("=" * 74)
    for mo in MODELS:
        v = vecs[mo]
        print(f"  {mo:10} range={float(np.nanmax(v) - np.nanmin(v)):.3f}  "
              f"(θ_open={logit(table[mo]['omission/0%'][1]):+.2f})")
    print("  → old finding: weaker respondent carries MORE range; check if it still holds.")


if __name__ == "__main__":
    main()
