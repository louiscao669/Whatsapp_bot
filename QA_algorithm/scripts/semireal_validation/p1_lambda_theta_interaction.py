#!/usr/bin/env python3
"""P1 - Is dose-sensitivity lambda ability-dependent?

For each defect family g and answer-model m, estimate the dose slope lambda_g,m two
ways and test whether it depends on model ability theta_m:

  (1) PLAIN   : 2-param logistic  P = sigma(a + b * qz)         (matches fit_item_sensitivity)
  (2) FLOORED : 3-param guessing  P = g + (1-g)*sigma(a + b*qz) (g = qtype floor)

The FLOORED slope is the floor-attenuation control: a weak model bunched near the
guessing floor has an artificially small PLAIN slope; if its FLOORED slope jumps up to
match the stronger models, the "rises with ability" pattern is a floor artifact. If the
FLOORED slope still rises with theta, ability-dependence of lambda is real.

Reads raw score files directly (self-contained). Writes a tidy CSV + prints a summary.
"""
from __future__ import annotations
import csv, json, math, os
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "evaluation" / "outputs"
ANCHOR = REPO / "QA_algorithm" / "outputs"
OUTDIR = REPO / "QA_algorithm" / "outputs" / "reports" / "item_sensitivity"

MODELS = ["llama 1b", "1.5b", "1.7b"]
FAMILIES = ["omission", "mistranslation", "grammar", "awkward"]  # simple 6-dose ladders
CHAPTERS = range(1, 9)
DOSES = ["0%", "5%", "10%", "15%", "20%", "30%"]
GUESS = {"mcq": 0.25, "open": 0.05}   # lower asymptote per qtype (4-option MCQ; open ~0)


def load_theta():
    th = {}
    for qt in ("open", "mcq"):
        d = json.loads((ANCHOR / f"anchor_irt_estimates_{qt}.json").read_text())
        th[qt] = {m: v["theta"] for m, v in d["model_abilities"].items()}
    return th


def yval(it, qt):
    if qt == "mcq":
        dc = it.get("direct_correct")
        return None if dc is None else (1.0 if dc else 0.0)
    v = it.get("llm_score")
    return None if v is None else float(min(1.0, max(0.0, v)))


def gather():
    """rows keyed by (family, model, qtype) -> list of (q_raw=-dose, y)."""
    data = defaultdict(list)
    for ch in CHAPTERS:
        for m in MODELS:
            for fam in FAMILIES:
                for dose in DOSES:
                    f = EVAL / f"luke{ch}" / m / fam / dose / "scores_target_llama.json"
                    if not f.exists():
                        continue
                    d = json.loads(f.read_text())
                    q = -float(dose.rstrip("%")) / 100.0
                    for it in d.get("items", []):
                        qt = it.get("q_type")
                        if qt not in GUESS:
                            continue
                        y = yval(it, qt)
                        if y is None:
                            continue
                        data[(fam, m, qt)].append((q, y))
    return data


def fit_slope(qraw, y, guess=None, ridge=1e-3):
    """MLE slope b in continuous-Bernoulli logistic on z-scored q. If guess given, fit
    P = g + (1-g)sigma(a+b*qz). Returns (b_z, se_b, base_acc_at_0)."""
    q = np.asarray(qraw, float)
    y = np.asarray(y, float)
    sd = q.std()
    if sd < 1e-9:
        return None
    qz = (q - q.mean()) / sd
    X = np.column_stack([np.ones(len(qz)), qz])
    b = np.zeros(2)
    g = 0.0 if guess is None else guess
    for _ in range(200):
        eta = X @ b
        s = 1.0 / (1.0 + np.exp(-eta))
        p = g + (1 - g) * s
        p = np.clip(p, 1e-6, 1 - 1e-6)
        # d p / d eta = (1-g) s (1-s);  grad of loglik wrt b
        dp = (1 - g) * s * (1 - s)
        grad = X.T @ ((y - p) * dp / (p * (1 - p))) - ridge * b
        # Fisher-ish weight
        W = (dp ** 2) / (p * (1 - p))
        H = -(X.T * W) @ X - ridge * np.eye(2)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        b = b - step
        if np.max(np.abs(step)) < 1e-8:
            break
    try:
        cov = np.linalg.inv(-H)
        se = float(np.sqrt(max(cov[1, 1], 0.0)))
    except np.linalg.LinAlgError:
        se = float("nan")
    # baseline accuracy at dose 0 (q=0 -> qz0)
    qz0 = (0.0 - q.mean()) / sd
    p0 = g + (1 - g) / (1.0 + math.exp(-(b[0] + b[1] * qz0)))
    return float(b[1]), se, float(p0)


def main():
    th = load_theta()
    data = gather()
    rows = []
    for (fam, m, qt), obs in sorted(data.items()):
        qraw = [o[0] for o in obs]
        yv = [o[1] for o in obs]
        plain = fit_slope(qraw, yv, guess=None)
        floored = fit_slope(qraw, yv, guess=GUESS[qt])
        if plain is None or floored is None:
            continue
        rows.append({
            "family": fam, "model": m, "qtype": qt, "theta": round(th[qt][m], 3),
            "n": len(obs), "base_acc0": round(plain[2], 3),
            "lambda_plain": round(plain[0], 4), "se_plain": round(plain[1], 4),
            "lambda_floored": round(floored[0], 4), "se_floored": round(floored[1], 4),
        })

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "p1_lambda_theta.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # kappa_g: OLS slope of lambda on theta (3 points) per (family, qtype, estimator)
    def kappa(fam, qt, col):
        pts = [(r["theta"], r[col]) for r in rows if r["family"] == fam and r["qtype"] == qt]
        pts.sort()
        if len(pts) < 2:
            return None
        x = np.array([p[0] for p in pts]); y = np.array([p[1] for p in pts])
        k = float(np.polyfit(x, y, 1)[0])
        return k, y  # y ordered by theta

    print(f"\nwrote {out}\n")
    print("lambda_g,m by family/qtype (theta order: 1b < 1.5b < 1.7b); "
          "kappa = d lambda / d theta; positive = MORE sensitive at HIGHER ability\n")
    for qt in ("open", "mcq"):
        print(f"===== {qt.upper()}  (guessing floor g={GUESS[qt]}) =====")
        hdr = f"{'family':15}{'estimator':10}{'1b':>9}{'1.5b':>9}{'1.7b':>9}{'kappa':>9}{'base_acc0 (1b/1.5b/1.7b)':>28}"
        print(hdr)
        for fam in FAMILIES:
            base = [r["base_acc0"] for m in MODELS for r in rows
                    if r["family"] == fam and r["qtype"] == qt and r["model"] == m]
            bstr = "/".join(f"{b:.2f}" for b in base) if len(base) == 3 else "-"
            for est, col in (("plain", "lambda_plain"), ("floored", "lambda_floored")):
                res = kappa(fam, qt, col)
                if res is None:
                    continue
                k, yv = res
                print(f"{fam:15}{est:10}{yv[0]:>+9.3f}{yv[1]:>+9.3f}{yv[2]:>+9.3f}"
                      f"{k:>+9.3f}{bstr:>28}")
        print()


if __name__ == "__main__":
    main()
