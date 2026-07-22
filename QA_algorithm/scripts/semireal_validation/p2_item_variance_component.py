#!/usr/bin/env python3
"""P2 - Does tripling obs/item lift per-item sensitivity variation above the noise floor?

Prior single-model result (C0, 2026-07-09): within each defect family the spread of
fitted per-item slopes s_i was FULLY explained by the fits' own SEs (tau = 0), at ~6
obs/item with se ~ 0.7. That "per-item s_i is dead" verdict rested on thin data.

Pooling the three answer-models (item IDs are identical across models) gives ~18 obs/item.
For each family we fit per-item slopes on the pooled data with theta as a fixed offset
(so ability level is controlled; the group ability->slope trend of P1 is common to all
items and does not inflate between-item variance). Then decompose:

    Var(s_i)  =  tau^2 (true per-item variance)  +  mean(se_i^2) (sampling noise)
    tau^2_hat =  Var(s_i) - mean(se_i^2)

Item-clustered bootstrap gives a CI on tau^2. If tau^2 CI excludes 0 -> per-item signal
emerges from under the noise (revive per-item s_i). If tau^2 <= 0 / CI includes 0 -> tau=0
CONFIRMED on 3x stronger data (group-level slopes only, as deployed).
"""
from __future__ import annotations
import csv, sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
from fit_item_sensitivity import assemble_rows_defect, fit_penalized_logistic  # noqa: E402

OUTDIR = REPO / "QA_algorithm" / "outputs" / "reports" / "item_sensitivity"
FAMILIES = ["omission", "mistranslation", "grammar", "awkward", "addition:adversarial"]
BASE_DEFECTS = ["omission", "mistranslation", "grammar", "awkward", "addition"]
PRIOR_PREC_C, PRIOR_PREC_S = 0.11, 0.04   # weak (sigma_c~3, sigma_s~5): near-MLE s_i
NBOOT = 600
RNG = np.random.default_rng(20260721)


def load_theta():
    import json
    th = {}
    for qt in ("open", "mcq"):
        d = json.loads((REPO / "QA_algorithm" / "outputs" /
                        f"anchor_irt_estimates_{qt}.json").read_text())
        th[qt] = {m: v["theta"] for m, v in d["model_abilities"].items()}
    return th


def zscore_family(rows):
    q = np.array([r["q_raw"] for r in rows], float)
    sd = q.std()
    if sd < 1e-9:
        return None
    mean = q.mean()
    for r in rows:
        r["qz"] = (r["q_raw"] - mean) / sd
    return sd


def fit_item(item_rows):
    qz = np.array([r["qz"] for r in item_rows], float)
    y = np.array([r["y"] for r in item_rows], float)
    off = np.array([(r["theta"] if r["theta"] is not None else 0.0) for r in item_rows], float)
    spread = max(r["d"] for r in item_rows) - min(r["d"] for r in item_rows)
    if qz.std() < 1e-9 or y.var() < 1e-6 or spread < 0.1:
        return None
    X = np.column_stack([np.ones(len(qz)), qz])
    coef, se, conv = fit_penalized_logistic(
        X, off, y, np.zeros(2), np.array([PRIOR_PREC_C, PRIOR_PREC_S]))
    if not conv:
        return None
    return float(coef[1]), float(se[1])


def decompose(items):
    """items: list of (s_i, se_i). Returns Var(s), mean(se^2), tau2."""
    s = np.array([x[0] for x in items]); se = np.array([x[1] for x in items])
    var_s = float(s.var(ddof=1)) if len(s) > 1 else float("nan")
    mean_se2 = float((se ** 2).mean())
    return var_s, mean_se2, var_s - mean_se2


def main():
    theta = load_theta()
    # pooled 3-model rows
    args = SimpleNamespace(eval_root=str(REPO / "evaluation" / "outputs"),
                           models=["llama 1b", "1.5b", "1.7b"], defects=BASE_DEFECTS,
                           chapters=list(range(1, 9)), qtypes=["open", "mcq"])
    rows_all, _ = assemble_rows_defect(args, theta)
    # single-model (1.7b) rows for the SE-shrinkage comparison
    args17 = SimpleNamespace(**{**args.__dict__, "models": ["1.7b"]})
    rows_17, _ = assemble_rows_defect(args17, theta)

    def per_family(rows):
        by_fam = defaultdict(list)
        for r in rows:
            if r["defect"] in FAMILIES:
                by_fam[r["defect"]].append(r)
        return by_fam

    fam_pool = per_family(rows_all)
    fam_17 = per_family(rows_17)

    results = []
    for fam in FAMILIES:
        # POOLED (3 models)
        rws = fam_pool[fam]
        zscore_family(rws)
        by_item = defaultdict(list)
        for r in rws:
            by_item[r["key"]].append(r)
        fitted = {}
        for k, irs in by_item.items():
            f = fit_item(irs)
            if f is not None:
                fitted[k] = (f, len(irs))
        items = [v[0] for v in fitted.values()]
        obs = np.mean([v[1] for v in fitted.values()]) if fitted else 0
        var_s, mean_se2, tau2 = decompose(items)

        # SINGLE model 1.7b for SE comparison
        r17 = fam_17[fam]
        zscore_family(r17)
        bi17 = defaultdict(list)
        for r in r17:
            bi17[r["key"]].append(r)
        items17 = [f for k, irs in bi17.items() if (f := fit_item(irs)) is not None]
        mean_se_17 = float(np.mean([x[1] for x in items17])) if items17 else float("nan")

        # item-clustered bootstrap on tau2 (pooled)
        keys = list(fitted.keys())
        taus = []
        for _ in range(NBOOT):
            pick = RNG.choice(len(keys), size=len(keys), replace=True)
            samp = [fitted[keys[i]][0] for i in pick]
            _, _, t2 = decompose(samp)
            taus.append(t2)
        lo, hi = np.percentile(taus, [2.5, 97.5])

        results.append({
            "family": fam, "n_items": len(items), "mean_obs_per_item": round(obs, 1),
            "mean_se_pooled": round(float(np.mean([x[1] for x in items])), 3),
            "mean_se_1.7b_only": round(mean_se_17, 3),
            "sd_s_i": round(var_s ** 0.5, 4), "rms_se": round(mean_se2 ** 0.5, 4),
            "tau2": round(tau2, 4), "tau2_lo95": round(float(lo), 4),
            "tau2_hi95": round(float(hi), 4),
            "tau": round(max(tau2, 0.0) ** 0.5, 4),
            "signal": "REVIVED" if lo > 0 else "tau=0 (confirmed)",
        })

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "p2_item_variance_component.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        w.writeheader(); w.writerows(results)

    print("P2 - per-item slope variance component (pooled 3 models, theta-controlled)\n")
    print(f"{'family':22}{'n_it':>5}{'obs/it':>7}{'se(1.7b)':>9}{'se(pool)':>9}"
          f"{'SD(s_i)':>9}{'rms_se':>8}{'tau^2 [95% CI]':>22}{'verdict':>20}")
    for r in results:
        ci = f"{r['tau2']:+.3f}[{r['tau2_lo95']:+.2f},{r['tau2_hi95']:+.2f}]"
        print(f"{r['family']:22}{r['n_items']:>5}{r['mean_obs_per_item']:>7}"
              f"{r['mean_se_1.7b_only']:>9}{r['mean_se_pooled']:>9}"
              f"{r['sd_s_i']:>9}{r['rms_se']:>8}{ci:>22}{r['signal']:>20}")
    print(f"\nwrote {out}")
    print("\nRead: SD(s_i) = spread of per-item slopes; rms_se = sqrt(mean sampling var).")
    print("tau^2 = SD^2 - rms_se^2. CI>0 => per-item signal real; CI includes 0 => tau=0.")


if __name__ == "__main__":
    main()
