#!/usr/bin/env python3
"""Step 2b — adjudicate the Step-2 cell-level additivity FAIL between three
suspects: (a) real non-additivity, (b) noise in Delta_obs, (c) noise/bias in
the MQM-derived burden B. Free checks on existing outputs only.

  (1) DISATTENUATION: reliability of Delta across cells,
      rel = 1 - mean(SE^2)/var_obs(Delta); the max correlation achievable
      against a NOISELESS, PERFECTLY-additive predictor is sqrt(rel).
      If rho_obs << ceiling -> failure not explained by Delta noise alone.
  (2) METHOD-FE REGRESSION: Delta ~ method offsets + k*B (WLS). The V2 zero
      point showed per-text register offsets; method FE absorbs them. k > 0
      within methods => additivity partially works, Step-2 global FAIL was
      register confounding. k ~ 0 => B carries no compositional signal.
      (Also chapter+method two-way FE variant.)
  (3) FILTERED-POOL RERUN: the mcq-only Step-2 outputs ARE the deployment
      (FILTERED = MCQ anchor items) version; repeat (1)-(2) on them.
  (4) CONSENSUS CROSS-CHECK: method-level Delta vs the 3-model consensus
      accuracy ranking (non-MQM ground truth) vs method-level B. If Delta
      tracks consensus better than B does/than Delta tracks B, the weak link
      is the MQM defect vector, not the response side.
  (5) SHAPE: Delta ~ k*B^alpha grid (alpha 0.25..3), with and without
      method FE — is the relationship there but nonlinear/saturating?

Inputs: QA_algorithm/outputs/reports/adequacy_burden/step2_prediction{,_mcq}.csv
        QA_algorithm/outputs/reports/consensus/method_ranking_consensus.csv
Output: .../adequacy_burden/step2b_noise_vs_real.txt (summary; printed)
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

QA_ROOT = Path(__file__).resolve().parents[2]
BURD = QA_ROOT / "outputs" / "reports" / "adequacy_burden"
CONS = QA_ROOT / "outputs" / "reports" / "consensus" / \
    "method_ranking_consensus.csv"


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def wls(X, y, w):
    Wm = np.diag(w)
    beta = np.linalg.solve(X.T @ Wm @ X, X.T @ Wm @ y)
    resid = y - X @ beta
    s2 = float(np.sum(w * resid**2) / max(1, len(y) - X.shape[1]))
    cov = np.linalg.inv(X.T @ Wm @ X) * s2
    return beta, np.sqrt(np.diag(cov)), resid


def load(path, delta_col="delta_obs", se_col="delta_se"):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return dict(
        rows=rows,
        B=np.array([float(r["B_count"]) for r in rows]),
        D=np.array([float(r[delta_col]) for r in rows]),
        SE=np.array([float(r[se_col]) for r in rows]),
        method=[r["method"] for r in rows],
        chapter=[r["chapter"] for r in rows],
    )


def analyze(tag, d, lines):
    B, D, SE = d["B"], d["D"], d["SE"]
    W = 1.0 / SE**2
    methods = sorted(set(d["method"]))
    chapters = sorted(set(d["chapter"]))
    lines.append(f"---- [{tag}]  n={len(B)} cells ----")

    # (1) disattenuation
    var_obs = float(np.var(D, ddof=1))
    noise = float(np.mean(SE**2))
    rel = max(0.0, 1.0 - noise / var_obs)
    ceiling = float(np.sqrt(rel))
    rho = spearman(B, D)
    pear = float(np.corrcoef(B, D)[0, 1])
    disatt = (f"{pear / ceiling:+.3f}" if ceiling >= 0.1 else "n/a (ceiling~0)")
    lines += [f"(1) var_obs(Delta)={var_obs:.3f}  mean SE^2={noise:.3f}  "
              f"reliability={rel:.2f}  CEILING rho={ceiling:.2f}",
              f"    observed rho={rho:+.3f} (pearson {pear:+.3f})  "
              f"disattenuated ~ {disatt}",
              f"    verdict: {'NOISE-LIMITED (ceiling low)' if ceiling < 0.45 else 'failure NOT explained by Delta noise' if abs(pear)/max(ceiling,1e-9) < 0.4 else 'partial signal'}"]

    # (2) method FE
    Xm = np.column_stack(
        [np.array([1.0 * (m == mm) for m in d["method"]]) for mm in methods]
        + [B])
    beta, se_b, resid = wls(Xm, D, W)
    k_fe, k_se = float(beta[-1]), float(se_b[-1])
    # within-method demeaned spearman
    Bw, Dw = B.astype(float).copy(), D.astype(float).copy()
    for mm in methods:
        mk = np.array([m == mm for m in d["method"]])
        Bw[mk] -= Bw[mk].mean()
        Dw[mk] -= Dw[mk].mean()
    lines += [f"(2) method-FE: k={k_fe:+.4f} +/- {k_se:.4f}  "
              f"({'SIGNAL' if k_fe > 2 * k_se else 'no within-method signal'})"
              f"   within-method rho={spearman(Bw, Dw):+.3f}"]
    # two-way FE
    X2 = np.column_stack(
        [np.array([1.0 * (m == mm) for m in d["method"]]) for mm in methods]
        + [np.array([1.0 * (c == cc) for c in d["chapter"]])
           for cc in chapters[1:]]
        + [B])
    beta2, se2, _ = wls(X2, D, W)
    lines.append(f"    two-way FE (method+chapter): k={float(beta2[-1]):+.4f} "
                 f"+/- {float(se2[-1]):.4f}  "
                 f"({'SIGNAL' if beta2[-1] > 2 * se2[-1] else 'ns'})")

    # (5) shape
    best = (1.0, -np.inf, 0.0)
    for al in np.linspace(0.25, 3.0, 34):
        Ba = B**al
        Xa = np.column_stack(
            [np.array([1.0 * (m == mm) for m in d["method"]])
             for mm in methods] + [Ba])
        bb, ss, rr = wls(Xa, D, W)
        r2 = 1.0 - float(np.sum(W * rr**2) /
                         np.sum(W * (D - np.average(D, weights=W))**2))
        if r2 > best[1]:
            best = (float(al), r2, float(bb[-1]))
    # alpha=1 comparison
    r2_1 = 1.0 - float(np.sum(W * resid**2) /
                       np.sum(W * (D - np.average(D, weights=W))**2))
    lines.append(f"(5) shape (with method FE): best alpha={best[0]:.2f} "
                 f"R^2={best[1]:.3f} vs alpha=1 R^2={r2_1:.3f}  "
                 f"({'nonlinearity helps' if best[1] - r2_1 > 0.02 else 'no material nonlinearity'})")
    return methods


def main():
    lines = ["Step 2b: noise vs real — adjudicating the Step-2 additivity "
             "FAIL", ""]
    d_both = load(BURD / "step2_prediction.csv")
    analyze("BOTH q_types", d_both, lines)
    lines.append("")
    mcq_path = BURD / "step2_prediction_mcq.csv"
    d_mcq = load(mcq_path)
    analyze("FILTERED (mcq-only = deployment pool)", d_mcq, lines)

    # (4) consensus cross-check (method level)
    with open(CONS) as f:
        cons = {r["method"]: float(r["consensus"])
                for r in csv.DictReader(f)}
    lines.append("")
    for tag, d in (("BOTH", d_both), ("MCQ", d_mcq)):
        methods = sorted(set(d["method"]))
        mD = [float(np.mean(d["D"][np.array([m == mm for m in d["method"]])]))
              for mm in methods]
        mB = [float(np.mean(d["B"][np.array([m == mm for m in d["method"]])]))
              for mm in methods]
        common = [m for m in methods if m in cons]
        mDc = [mD[methods.index(m)] for m in common]
        mBc = [mB[methods.index(m)] for m in common]
        mC = [cons[m] for m in common]
        lines += [f"(4) [{tag}] method level (n={len(common)}): "
                  f"rho(Delta, consensus_acc) = {spearman(mDc, mC):+.2f} "
                  f"(expect negative & strong if response side healthy)",
                  f"    rho(Delta, B) = {spearman(mDc, mBc):+.2f}   "
                  f"rho(B, consensus_acc) = {spearman(mBc, mC):+.2f}"]

    out = "\n".join(lines)
    (BURD / "step2b_noise_vs_real.txt").write_text(out)
    print(out)
    print(f"\n[out] {BURD}/step2b_noise_vs_real.txt")


if __name__ == "__main__":
    main()
