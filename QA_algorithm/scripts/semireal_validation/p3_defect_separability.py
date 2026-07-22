#!/usr/bin/env python3
"""P3 - Defect-axis separability across ability.

Does each answer-model rank the defect FAMILIES in the same order of dose-sensitivity
(adequacy steep, fluency flat)? If the ordering is preserved across abilities, the
adequacy-not-fluency structure is a property of the translation defect, not an artifact
of the 1.7b respondent. This is the V4 separability logic (which ran on the METHOD axis
and partially failed - 1.5b disagreed) applied to the DEFECT axis.

Estimand: pairwise cross-ability Spearman rho of the per-family lambda vectors over the
8 families common to all three models. Uncertainty via an ITEM-CLUSTERED bootstrap: one
resample of the shared item set per replicate (applied to every model+family), refit the
group slope lambda_g,m, recompute rho -> 95% CI. Because the same items are resampled for
all models, cross-model rank agreement is measured on matched data.

Point-estimate lambdas are read from the canonical fitter output (lambda_by_defect_model.csv);
the bootstrap re-derives them from raw responses assembled by fit_item_sensitivity.
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
from fit_item_sensitivity import assemble_rows_defect, fit_penalized_logistic  # noqa: E402

OUTDIR = REPO / "QA_algorithm" / "outputs" / "reports" / "item_sensitivity"
LAMBDA_CSV = OUTDIR / "lambda_by_defect_model.csv"
MODELS = ["llama 1b", "1.5b", "1.7b"]
FAMILIES = ["omission", "mistranslation", "addition:adversarial", "addition:bad",
            "addition:neutral", "grammar", "awkward", "local_inconsistency:style"]
KIND = {"omission": "adeq", "mistranslation": "adeq", "addition:adversarial": "adeq",
        "addition:bad": "adeq", "addition:neutral": "adeq", "grammar": "flu",
        "awkward": "flu", "local_inconsistency:style": "flu"}
NBOOT = 1000
RNG = np.random.default_rng(20260721)


def spearman(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    ra = ra - ra.mean(); rb = rb - rb.mean()
    denom = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / denom) if denom else float("nan")


def group_slope(drs):
    """beta_z: per-SD logit dose slope over rows in one (family, model) cell."""
    q = np.array([r["q_raw"] for r in drs], float)
    sd = q.std()
    if sd < 1e-9:
        return None
    qz = (q - q.mean()) / sd
    y = np.array([r["y"] for r in drs], float)
    X = np.column_stack([np.ones(len(qz)), qz])
    coef, _, _ = fit_penalized_logistic(X, np.zeros(len(qz)), y,
                                        np.zeros(2), np.array([1e-3, 1e-3]))
    return float(coef[1])


def main():
    # ---- point estimate from canonical fitter output ----
    lam = defaultdict(dict)
    for r in csv.DictReader(open(LAMBDA_CSV)):
        lam[r["defect"]][r["model"]] = float(r["beta_z"])
    vec = {m: [lam[f][m] for f in FAMILIES] for m in MODELS}

    pairs = [("llama 1b", "1.5b"), ("llama 1b", "1.7b"), ("1.5b", "1.7b")]
    rho_pt = {p: spearman(vec[p[0]], vec[p[1]]) for p in pairs}

    # ---- assemble raw rows once, grouped by (family, model) with item keys ----
    args = SimpleNamespace(
        eval_root=str(REPO / "evaluation" / "outputs"),
        models=MODELS, defects=["omission", "mistranslation", "grammar", "awkward",
                                "addition", "local_inconsistency"],
        chapters=list(range(1, 9)), qtypes=["open", "mcq"])
    rows, _ = assemble_rows_defect(args, None)
    cells = defaultdict(lambda: defaultdict(list))   # (defect,model) -> item_key -> [rows]
    all_keys = set()
    for r in rows:
        if r["defect"] in FAMILIES:
            cells[(r["defect"], r["model"])][r["key"]].append(r)
            all_keys.add(r["key"])
    all_keys = sorted(all_keys)

    # ---- item-clustered bootstrap ----
    boot = {p: [] for p in pairs}
    for _ in range(NBOOT):
        pick = RNG.choice(len(all_keys), size=len(all_keys), replace=True)
        keyset = [all_keys[i] for i in pick]
        bvec = {}
        ok = True
        for m in MODELS:
            v = []
            for f in FAMILIES:
                pool = cells[(f, m)]
                drs = []
                for k in keyset:
                    drs.extend(pool.get(k, ()))
                s = group_slope(drs) if drs else None
                if s is None:
                    ok = False
                    break
                v.append(s)
            if not ok:
                break
            bvec[m] = v
        if not ok:
            continue
        for p in pairs:
            boot[p].append(spearman(bvec[p[0]], bvec[p[1]]))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "p3_defect_separability.csv"
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["pair", "rho", "boot_lo95", "boot_hi95", "boot_median", "n_boot"])
        for p in pairs:
            arr = np.array(boot[p])
            lo, hi, med = (np.percentile(arr, [2.5, 97.5]).tolist() + [float(np.median(arr))]) \
                if len(arr) else (float("nan"), float("nan"), float("nan"))
            w.writerow([f"{p[0]} vs {p[1]}", round(rho_pt[p], 3),
                        round(lo, 3), round(hi, 3), round(med, 3), len(arr)])

    # ---- report ----
    print("Per-family lambda (beta_z) and within-model RANK (1=steepest):\n")
    hdr = f"{'family':26}{'kind':6}" + "".join(f"{m:>20}" for m in MODELS)
    print(hdr)
    ranks = {m: {f: r for r, f in enumerate(sorted(FAMILIES, key=lambda x: -lam[x][m]), 1)}
             for m in MODELS}
    for f in sorted(FAMILIES, key=lambda x: -lam[x]["1.7b"]):
        cellstr = "".join(f"{lam[f][m]:>+11.3f} (r{ranks[m][f]})" for m in MODELS)
        print(f"{f:26}{KIND[f]:6}{cellstr}")

    print("\nCross-ability Spearman rho of the lambda-ranking (8 families):")
    for p in pairs:
        arr = np.array(boot[p])
        lo, hi = np.percentile(arr, [2.5, 97.5]) if len(arr) else (float("nan"),) * 2
        print(f"  {p[0]:9} vs {p[1]:5}:  rho={rho_pt[p]:+.3f}   "
              f"boot95=[{lo:+.3f},{hi:+.3f}]")

    # adequacy-vs-fluency block separation per model (min adeq lambda vs max flu lambda)
    print("\nAdequacy-block vs fluency-block separation (does every adequacy family "
          "outrank every fluency family?):")
    for m in MODELS:
        adeq = [lam[f][m] for f in FAMILIES if KIND[f] == "adeq"]
        flu = [lam[f][m] for f in FAMILIES if KIND[f] == "flu"]
        clean = min(adeq) > max(flu)
        print(f"  {m:9}: min(adeq)={min(adeq):+.3f}  max(flu)={max(flu):+.3f}  "
              f"clean_block_separation={clean}")

    # CORE-family view: drop the empirically near-zero / ambiguous families whose ranks
    # are unstable (neutral & bad additions weakly damage meaning per A3; local_inconsistency
    # style ~0). These carry no adequacy-not-fluency signal, only rank noise.
    CORE = ["omission", "mistranslation", "addition:adversarial", "grammar", "awkward"]
    print("\nCORE families only (omission, mistranslation, adversarial-add | grammar, awkward):")
    cvec = {m: [lam[f][m] for f in CORE] for m in MODELS}
    for p in pairs:
        print(f"  spearman {p[0]:9} vs {p[1]:5}: rho={spearman(cvec[p[0]], cvec[p[1]]):+.3f}")
    for m in MODELS:
        a = min(lam[f][m] for f in CORE if KIND[f] == "adeq")
        fl = max(lam[f][m] for f in CORE if KIND[f] == "flu")
        print(f"  {m:9}: min(adeq)={a:+.3f} > max(flu)={fl:+.3f}  clean={a > fl}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
