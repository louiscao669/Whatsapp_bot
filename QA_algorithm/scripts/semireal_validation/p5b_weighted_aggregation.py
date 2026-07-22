#!/usr/bin/env python3
"""P5b - Reliability-WEIGHTED multi-respondent quality inference (deployment estimator).

The plain P5 averaged re-zeroed Delta at KNOWN doses. Deployment is the inverse problem:
given respondents' answers on a passage of UNKNOWN quality, estimate the quality, factoring
out ability. Each respondent converts their re-zeroed answer shift into a common-scale
quality (damage) estimate using their OWN calibrated sensitivity:

    Delta_m = logit(acc_m(d)) - logit(acc_m(0))         # re-zeroed shift (per respondent)
    qhat_m  = -Delta_m / lambda_m                        # common-scale damage estimate

Dividing by lambda un-does ability-dependent sensitivity (puts everyone on one quality
scale). But a weak respondent (small lambda) blows up the noise in qhat_m, so combining
qhat_m EQUALLY lets the noisiest respondent dominate. Fisher-optimal weighting fixes it:

    Var(qhat_m) ~ 1 / (lambda_m^2 * N * p_m(1-p_m))   ->   w_m  prop  lambda_m^2 * p_m(1-p_m)

lambda_m is the PRIOR adequacy sensitivity from the synthetic-defect grid (passage-
independent, non-circular). We compare aggregation schemes on their ability to recover the
(secretly known) dose on the grid: EQUAL vs PRIOR-WEIGHTED vs SHRUNK(0.5) vs EMPIRICAL-
OPTIMAL (inverse observed variance = unattainable upper bound). Metric: variance of the
pooled damage estimate and dose-recovery fidelity -> effective respondent savings.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "evaluation" / "outputs"
OUTDIR = REPO / "QA_algorithm" / "outputs" / "reports" / "item_sensitivity"
LAMBDA_CSV = OUTDIR / "lambda_by_defect_model.csv"
MODELS = ["llama 1b", "1.5b", "1.7b"]
ADQ = ["omission", "mistranslation"]                 # clean full-ladder adequacy families
ADQ_LAMBDA = ["omission", "mistranslation", "addition:adversarial"]  # for the prior weight
DOSES = ["0%", "5%", "10%", "15%", "20%", "30%"]
CHAPTERS = list(range(1, 9))
SHRINK = 0.5


def combined_acc(fam, m, ch, dose):
    f = EVAL / f"luke{ch}" / m / fam / dose / "scores_target_llama.json"
    if not f.exists():
        return None
    s = json.loads(f.read_text()).get("summary", {})
    tot = s.get("total") or 0
    if not tot:
        return None
    mcq_c = s.get("mcq_correct") or 0
    open_sum = (s.get("open_llm_score_mean") or 0.0) * (s.get("open_count") or 0)
    return (mcq_c + open_sum) / tot


def logit(p, eps=0.02):
    p = min(1 - eps, max(eps, p))
    return math.log(p / (1 - p))


def main():
    # ---- prior adequacy lambda per model (grid) ----
    lam_rows = list(csv.DictReader(open(LAMBDA_CSV)))
    lam_tab = {(r["defect"], r["model"]): float(r["beta_z"]) for r in lam_rows}
    lam = {m: float(np.mean([lam_tab[(f, m)] for f in ADQ_LAMBDA])) for m in MODELS}

    # ---- per-model 0% baseline accuracy (operating point p_m) ----
    base_global = {}
    for m in MODELS:
        vals = [combined_acc(f, m, ch, "0%") for f in ADQ for ch in CHAPTERS]
        base_global[m] = float(np.mean([v for v in vals if v is not None]))
    p = base_global

    # ---- weights ----
    def norm(d):
        s = sum(d.values()); return {k: v / s for k, v in d.items()}
    w_equal = {m: 1 / len(MODELS) for m in MODELS}
    w_prior = norm({m: max(lam[m], 0) ** 2 * p[m] * (1 - p[m]) for m in MODELS})
    w_shrunk = {m: (1 - SHRINK) * w_prior[m] + SHRINK * w_equal[m] for m in MODELS}

    # ---- build qhat_m for every (family, dose>0, chapter) instance ----
    inst = []  # (family, dose_frac, chapter, {m: qhat_m})
    for fam in ADQ:
        for dose in DOSES[1:]:
            dfrac = float(dose.rstrip("%")) / 100.0
            for ch in CHAPTERS:
                base = {m: combined_acc(fam, m, ch, "0%") for m in MODELS}
                cur = {m: combined_acc(fam, m, ch, dose) for m in MODELS}
                qh = {}
                for m in MODELS:
                    if base[m] is None or cur[m] is None or lam[m] <= 0:
                        continue
                    delta = logit(cur[m]) - logit(base[m])
                    qh[m] = -delta / lam[m]              # damage estimate (>0 = worse)
                if len(qh) == len(MODELS):
                    inst.append((fam, dfrac, ch, qh))

    # empirical-optimal weights: inverse observed variance of qhat_m across instances
    permodel = {m: np.array([x[3][m] for x in inst]) for m in MODELS}
    emp_var = {m: float(permodel[m].var(ddof=1)) for m in MODELS}
    w_emp = norm({m: 1.0 / emp_var[m] for m in MODELS})

    schemes = {"equal": w_equal, "prior_lambda2": w_prior,
               "shrunk0.5": w_shrunk, "empirical_opt": w_emp}

    def agg(qh, w):
        return sum(w[m] * qh[m] for m in MODELS)

    # ---- fidelity: correlation of pooled qhat with true dose; and per-dose precision ----
    true = np.array([x[1] for x in inst])
    results = {}
    for name, w in schemes.items():
        qagg = np.array([agg(x[3], w) for x in inst])
        # standardize qagg to dose scale via least-squares slope (removes arbitrary 1/lambda units)
        b = np.polyfit(qagg, true, 1)
        pred = np.polyval(b, qagg)
        rmse = float(np.sqrt(np.mean((pred - true) ** 2)))
        r = float(np.corrcoef(qagg, true)[0, 1])
        # residual variance at fixed dose (noise not explained by dose) -> precision
        resid = []
        for fam in ADQ:
            for dfrac in sorted({x[1] for x in inst}):
                sub = [agg(x[3], w) for x in inst if x[0] == fam and x[1] == dfrac]
                if len(sub) > 1:
                    resid.append(np.var(sub, ddof=1))
        results[name] = {"corr_true": r, "rmse_dose": rmse,
                         "within_dose_var": float(np.mean(resid))}

    # ---- effective respondent savings from the variance ratio (weighted vs equal) ----
    v_eq = results["equal"]["within_dose_var"]
    def savings(name):
        vr = v_eq / results[name]["within_dose_var"]          # effective data multiplier
        pct_fewer = (1 - 1 / vr) * 100
        return vr, pct_fewer

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "p5b_weighted_aggregation.csv"
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["scheme", "w_1b", "w_1.5b", "w_1.7b", "corr_true_dose",
                    "rmse_dose", "within_dose_var", "eff_data_mult_vs_equal", "pct_fewer_respondents"])
        for name in schemes:
            vr, pf = savings(name)
            wr = schemes[name]
            w.writerow([name, round(wr["llama 1b"], 3), round(wr["1.5b"], 3), round(wr["1.7b"], 3),
                        round(results[name]["corr_true"], 3), round(results[name]["rmse_dose"], 4),
                        round(results[name]["within_dose_var"], 4), round(vr, 2), round(pf, 1)])

    # ---- report ----
    print("PRIOR adequacy lambda (grid) and operating point p (0% baseline):")
    for m in MODELS:
        print(f"   {m:9} lambda={lam[m]:+.3f}  p={p[m]:.3f}  p(1-p)={p[m]*(1-p[m]):.3f}")
    print("\nWEIGHTS by scheme:")
    print(f"   {'scheme':16}{'1b':>8}{'1.5b':>8}{'1.7b':>8}")
    for name in schemes:
        wr = schemes[name]
        print(f"   {name:16}{wr['llama 1b']:>8.2f}{wr['1.5b']:>8.2f}{wr['1.7b']:>8.2f}")
    print("\nqhat_m per-model variance across instances (why equal-weight is bad):")
    for m in MODELS:
        print(f"   {m:9} Var(qhat)={emp_var[m]:.3f}   (small lambda -> noisy qhat)")
    print("\nAGGREGATION QUALITY (recovering the known dose):")
    print(f"   {'scheme':16}{'corr(true)':>11}{'RMSE(dose)':>12}{'withinVar':>11}"
          f"{'effData x':>10}{'% fewer resp':>13}")
    for name in schemes:
        vr, pf = savings(name)
        rr = results[name]
        print(f"   {name:16}{rr['corr_true']:>11.3f}{rr['rmse_dose']:>12.4f}"
              f"{rr['within_dose_var']:>11.4f}{vr:>10.2f}{pf:>13.1f}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
