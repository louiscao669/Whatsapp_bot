#!/usr/bin/env python3
"""Step 2 of the MQM defect-vector program (EXPERIMENT_BURDEN_MQM_BRIDGE.md §2):
parameter-free prediction of observed QA outcomes from the adequacy burden.

FORWARD MODEL (zero free quality parameters):
    predicted logit shift  Delta_pred(cell) = k * B(cell)
    B(cell) = sum_g lambda_g * rate_{cell,g}      [Step-1 burden]
  - lambda_g : FROZEN family sensitivities from the synthetic-variant dose
    grids (s_item_by_defect.csv, q_var_ok family means). Not fitted here.
  - rate_g   : MQM per-category defect rates (errors or penalty /1000 words)
    from the corrected MERGED MQM grid. Measured, not fitted.
  - k        : the ONE fitted number — a global unit-scale factor reconciling
    synthetic-dose z-units with MQM-rate units. Fitted through the origin,
    weighted by 1/SE^2, across all cells.

OBSERVED OUTCOME per cell (chapter x method):
    Delta_obs = common logit shift fitted by 1PL MLE on the cell's real
    responses:  y_i ~ Bernoulli( sigma( theta_qtype - b_i - Delta ) )
  - theta from anchor Rasch (per q_type ladder), b_i from anchor difficulties
    (same 1PL misspecification as the anchor fit, incl. MCQ guessing absorbed
    into b — consistent by construction).
  - Weak ridge prior Delta ~ N(0, 3^2) for cells near 0%/100%.
  - SE from Fisher information (+ prior).

WHAT IT TESTS
  1. ADDITIVITY / calibration transfer: lambdas were calibrated one defect
     family at a time; natural translations stack families. Pass if
     Delta_obs tracks k*B across cells (pre-registered: Spearman >= +0.6),
     intercept ~ 0 in the diagnostic with-intercept fit (zero-point /
     anchor-b transfer), and no non-wbw method with large systematic
     residual.
  2. THE PRE-REGISTERED THREE-WAY DIVERGENCE (google_word_by_word):
     B says mid-pack, MQM near-worst, observed QA worst. Adjudicated by the
     residual analysis (grammar excluded from B so its full effect appears
     in the residual):
       - nonlinear DENSITY COLLAPSE  -> residuals track grammar COUNT rate
         (superlinear: quadratic term > 0 on the burden scale);
       - SEVERITY RESPONSE / category leakage -> residuals track grammar
         mean severity (penalty/count) at fixed count.
     Plus the fitted severity exponent gamma in B(gamma) =
     sum_g lambda_g * count_rate_g * sev_g^gamma  (gamma=0 -> counts,
     gamma=1 -> penalties); chapter-cluster bootstrap CI.

Inputs (defaults; override by flag):
  evaluation/outputs/reports/mqm_translation_scores_1.7b_MERGED_luke1_8.csv
  QA_algorithm/outputs/reports/item_sensitivity/s_item_by_defect.csv
  QA_algorithm/outputs/anchor_irt_estimates_{mcq,open}.json
  evaluation/outputs/luke{ch}/<model>/<method>/scores_target_llama.json
  (located via the MQM csv's translation_file column)

Outputs (QA_algorithm/outputs/reports/adequacy_burden/):
  step2_prediction.csv   per-cell burden components, Delta_obs (+SE, n),
                         predictions, residuals
  step2_summary.txt      fits, pass/fail verdicts, adjudication
  step2_prediction.png   observed-vs-predicted + residual diagnostics

Usage:
  PYTHONPATH=. python3 QA_algorithm/scripts/step2_parameter_free_prediction.py
  ... --q-types both|mcq|open   (default both; mcq = robustness, cleaner)
  ... --exclude-methods google_word_by_word   (refit without the outlier)
  ... --n-boot 500
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np

QA_ROOT = Path(__file__).resolve().parents[2]
REPO = QA_ROOT.parent
MQM_CSV = REPO / "evaluation" / "outputs" / "reports" / \
    "mqm_translation_scores_1.7b_MERGED_luke1_8.csv"
S_CSV = QA_ROOT / "outputs" / "reports" / "item_sensitivity" / "s_item_by_defect.csv"
ANCHOR = {qt: QA_ROOT / "outputs" / f"anchor_irt_estimates_{qt}.json"
          for qt in ("mcq", "open")}
OUT_DIR = QA_ROOT / "outputs" / "reports" / "adequacy_burden"

# Same category -> family mapping as Step 1 (documented assumptions).
CATEGORY_MAP = {
    "accuracy_omission": ["omission"],
    "accuracy_mistranslation": ["mistranslation"],
    "accuracy_addition": ["addition:bad", "addition:neutral"],
    "fluency_grammar": ["grammar"],
    "terminology": ["inconsistency:name"],
    "untranslated_non_translation": ["omission"],
    "other": [],
}
ADEQUACY_CATS = ("accuracy_omission", "accuracy_mistranslation",
                 "accuracy_addition", "untranslated_non_translation")
# Anchor-ladder key for the answer model whose responses populate the grid.
ANCHOR_MODEL_KEY = "1.7b"
PRIOR_SD = 3.0          # ridge prior on Delta (logits)
SPEARMAN_PASS = 0.6     # pre-registered additivity threshold (matches V3)


# ---------------------------------------------------------------- utilities
def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def family_lambdas():
    with open(S_CSV) as f:
        rows = [r for r in csv.DictReader(f)
                if r["q_var_ok"].strip().lower() in ("1", "true")]
    fams = {}
    for r in rows:
        fams.setdefault(r["defect"], []).append(float(r["s_i"]))
    lam = {f: float(np.mean(v)) for f, v in fams.items()}
    cat_lam = {}
    for cat, fs in CATEGORY_MAP.items():
        cat_lam[cat] = float(np.mean([lam[f] for f in fs])) if fs else 0.0
    return cat_lam


def load_anchor():
    theta, bmap = {}, {}
    for qt, path in ANCHOR.items():
        d = json.load(open(path))
        theta[qt] = float(d["model_abilities"][ANCHOR_MODEL_KEY]["theta"])
        bmap[qt] = {k: float(v["b_posterior"])
                    for k, v in d["item_difficulties"].items()}
    return theta, bmap


def fit_delta(y, base_logit, prior_sd=PRIOR_SD):
    """MLE of common shift Delta in y ~ Bern(sigma(base_logit - Delta)),
    ridge prior N(0, prior_sd^2). Returns (delta, se)."""
    y = np.asarray(y, float)
    d = 0.0
    for _ in range(100):
        p = 1.0 / (1.0 + np.exp(-(base_logit - d)))
        g = float(np.sum(p - y)) - d / prior_sd**2          # dlogpost/dDelta
        h = -float(np.sum(p * (1 - p))) - 1.0 / prior_sd**2  # d2/dDelta2
        step = g / h
        d -= step
        if abs(step) < 1e-10:
            break
    p = 1.0 / (1.0 + np.exp(-(base_logit - d)))
    se = 1.0 / np.sqrt(np.sum(p * (1 - p)) + 1.0 / prior_sd**2)
    return float(d), float(se)


def wls_through_origin(x, y, w):
    """y ~ k*x, weights w. Returns k, se_k, weighted R^2 (through origin)."""
    x, y, w = map(lambda a: np.asarray(a, float), (x, y, w))
    k = float(np.sum(w * x * y) / np.sum(w * x * x))
    resid = y - k * x
    se_k = float(np.sqrt(1.0 / np.sum(w * x * x))
                 * np.sqrt(np.sum(w * resid**2) / max(1, len(x) - 1)))
    r2 = 1.0 - float(np.sum(w * resid**2) / np.sum(w * y**2))
    return k, se_k, r2


def wls_line(x, y, w):
    """y ~ a + k*x, weights w. Returns (a, k, se_a, se_k)."""
    x, y, w = map(lambda a: np.asarray(a, float), (x, y, w))
    X = np.column_stack([np.ones_like(x), x])
    W = np.diag(w)
    XtW = X.T @ W
    beta = np.linalg.solve(XtW @ X, XtW @ y)
    resid = y - X @ beta
    s2 = float(np.sum(w * resid**2) / max(1, len(x) - 2))
    cov = np.linalg.inv(XtW @ X) * s2
    return (float(beta[0]), float(beta[1]),
            float(np.sqrt(cov[0, 0])), float(np.sqrt(cov[1, 1])))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mqm-csv", default=str(MQM_CSV))
    ap.add_argument("--q-types", choices=("both", "mcq", "open"),
                    default="both")
    ap.add_argument("--exclude-methods", default="",
                    help="comma-separated methods to drop from ALL fits")
    ap.add_argument("--n-boot", type=int, default=500)
    ap.add_argument("--gamma-grid", default="0:2:41",
                    help="min:max:npoints for the severity exponent search")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    rng = np.random.default_rng(7)
    excl = {m.strip() for m in args.exclude_methods.split(",") if m.strip()}
    qtypes = ("mcq", "open") if args.q_types == "both" else (args.q_types,)

    cat_lam = family_lambdas()
    theta, bmap = load_anchor()
    print("[lambda per MQM category]",
          {c: round(v, 3) for c, v in cat_lam.items()})
    print("[theta]", {qt: round(theta[qt], 3) for qt in qtypes})

    # ---- per-cell: burden components + observed Delta ---------------------
    cells = []
    n_join_tot = n_join_hit = 0
    with open(args.mqm_csv) as f:
        mqm_rows = [r for r in csv.DictReader(f) if r["method"] not in excl]
    for r in mqm_rows:
        ch, method = int(r["chapter"]), r["method"]
        words = float(r["source_words"])
        rec = {"chapter": ch, "method": method,
               "mqm_penalty_per_1000": float(r["penalty_per_1000_words"])}
        # burden components
        B_cnt = B_pen = B_cnt_nogr = 0.0
        for cat, lg in cat_lam.items():
            cnt = float(r[f"{cat}_count"]) / words * 1000
            pen = float(r[f"{cat}_penalty"]) / words * 1000
            rec[f"{cat}_count_rate"] = cnt
            rec[f"{cat}_penalty_rate"] = pen
            B_cnt += lg * cnt
            B_pen += lg * pen
            if cat != "fluency_grammar":
                B_cnt_nogr += lg * cnt
        gcnt = rec["fluency_grammar_count_rate"]
        rec.update(B_count=B_cnt, B_penalty=B_pen, B_count_nogrammar=B_cnt_nogr,
                   grammar_count_rate=gcnt,
                   grammar_mean_severity=(rec["fluency_grammar_penalty_rate"]
                                          / gcnt if gcnt > 0 else 0.0))
        # observed Delta from real responses
        score_file = os.path.join(os.path.dirname(r["translation_file"]),
                                  "scores_target_llama.json")
        score_path = (REPO / score_file) if not os.path.isabs(score_file) \
            else Path(score_file)
        if not score_path.exists():
            print(f"[skip] no scores: {score_path}")
            continue
        items = json.load(open(score_path))["items"]
        y, base = [], []
        per_type = {qt: [[], []] for qt in qtypes}
        for it in items:
            qt = it["q_type"]
            if qt not in qtypes:
                continue
            key = f"luke{ch}:item{it['item_index']}:{qt}"
            n_join_tot += 1
            b = bmap[qt].get(key)
            if b is None:
                continue
            n_join_hit += 1
            if qt == "mcq":
                yy = 1.0 if it["direct_correct"] else 0.0
            else:
                if it["llm_score"] is None:
                    continue
                yy = float(it["llm_score"])
            y.append(yy)
            base.append(theta[qt] - b)
            per_type[qt][0].append(yy)
            per_type[qt][1].append(theta[qt] - b)
        if len(y) < 6:
            print(f"[skip] {method} luke{ch}: only {len(y)} joined items")
            continue
        d, se = fit_delta(y, np.array(base))
        rec.update(delta_obs=d, delta_se=se, n_items=len(y),
                   acc=float(np.mean(y)))
        for qt in qtypes:
            yy, bb = per_type[qt]
            if len(yy) >= 4:
                dq, sq = fit_delta(yy, np.array(bb))
                rec[f"delta_{qt}"] = dq
                rec[f"delta_{qt}_se"] = sq
        cells.append(rec)

    print(f"[join] anchor-b coverage: {n_join_hit}/{n_join_tot}"
          f" ({n_join_hit / max(1, n_join_tot):.2f});"
          f" cells: {len(cells)}")

    B = np.array([c["B_count"] for c in cells])
    Bp = np.array([c["B_penalty"] for c in cells])
    Bng = np.array([c["B_count_nogrammar"] for c in cells])
    D = np.array([c["delta_obs"] for c in cells])
    W = np.array([1.0 / c["delta_se"]**2 for c in cells])
    methods = sorted({c["method"] for c in cells})
    chapters = sorted({c["chapter"] for c in cells})
    is_wbw = np.array([c["method"] == "google_word_by_word" for c in cells])

    lines = [f"Step 2: parameter-free prediction of observed QA shift from "
             f"burden ({len(cells)} cells; q_types={args.q_types}; "
             f"excluded={sorted(excl) or '-'})", ""]

    # ---- (1) main fit: Delta_obs ~ k * B_count ----------------------------
    k, se_k, r2 = wls_through_origin(B, D, W)
    a_i, k_i, se_a_i, se_k_i = wls_line(B, D, W)
    rho = spearman(B, D)
    pear = float(np.corrcoef(B, D)[0, 1])
    lines += ["== (1) ADDITIVITY / calibration transfer ==",
              f"through-origin  k = {k:+.4f} +/- {se_k:.4f}   "
              f"(logits per burden unit)   weighted R^2 = {r2:.3f}",
              f"with intercept  a = {a_i:+.3f} +/- {se_a_i:.3f}, "
              f"k = {k_i:+.4f} +/- {se_k_i:.4f}   "
              f"[|a| < 2se -> zero-point OK: "
              f"{'PASS' if abs(a_i) < 2 * se_a_i else 'FAIL'}]",
              f"Spearman(Delta_obs, B_count) = {rho:+.3f}   "
              f"Pearson = {pear:+.3f}   "
              f"[>= +{SPEARMAN_PASS} -> {'PASS' if rho >= SPEARMAN_PASS else 'FAIL'}]"]
    # penalty-bracket comparison (same # free params)
    kp, _, r2p = wls_through_origin(Bp, D, W)
    lines.append(f"bracket check: B_penalty  Spearman={spearman(Bp, D):+.3f} "
                 f"R^2={r2p:.3f}  vs  B_count R^2={r2:.3f}")

    # secondary (pre-specified nuisance control): chapter fixed effects —
    # demean B and Delta within chapter; absorbs chapter-specific content /
    # anchor-b-transfer offsets that are uncorrelated with burden.
    Bfe = B.copy().astype(float)
    Dfe = D.copy().astype(float)
    for ch in chapters:
        mk = np.array([c["chapter"] == ch for c in cells])
        Bfe[mk] -= Bfe[mk].mean()
        Dfe[mk] -= Dfe[mk].mean()
    k_fe, se_k_fe, r2_fe = wls_through_origin(Bfe, Dfe, W)
    lines.append(f"chapter-FE fit  k = {k_fe:+.4f} +/- {se_k_fe:.4f}  "
                 f"R^2 = {r2_fe:.3f}  "
                 f"within-chapter Spearman = {spearman(Bfe, Dfe):+.3f}  "
                 "(secondary; not parameter-free — 8 chapter offsets)")
    # method-level aggregation (mean over chapters; averages out cell noise)
    mB = {m: float(np.mean(B[np.array([c['method'] == m for c in cells])]))
          for m in methods}
    mD = {m: float(np.mean(D[np.array([c['method'] == m for c in cells])]))
          for m in methods}
    lines.append(f"method-level (chapter-averaged) Spearman(B, Delta) = "
                 f"{spearman([mB[m] for m in methods], [mD[m] for m in methods]):+.3f}"
                 f"   (n={len(methods)} methods)")

    # leave-one-method-out stability of k
    loo = []
    for m in methods:
        mask = np.array([c["method"] != m for c in cells])
        km, _, _ = wls_through_origin(B[mask], D[mask], W[mask])
        loo.append((m, km))
    lines += ["", "leave-one-method-out k: " +
              ", ".join(f"{m}={km:+.3f}" for m, km in loo)]

    # per-method mean residual (from through-origin fit)
    resid = D - k * B
    lines += ["", f"{'method':<24}{'mean_resid':>11}{'mean|SE|':>10}"
              f"{'n':>4}   (resid>0: worse than burden predicts)"]
    for m in methods:
        mask = np.array([c["method"] == m for c in cells])
        se_m = float(np.mean([c["delta_se"] for c, f in zip(cells, mask) if f]))
        flag = " <-- PRE-REGISTERED OUTLIER" if m == "google_word_by_word" else ""
        lines.append(f"{m:<24}{float(np.mean(resid[mask])):>+11.3f}"
                     f"{se_m:>10.3f}{int(mask.sum()):>4}{flag}")

    # ---- (2) adjudication: residuals from the NO-GRAMMAR burden -----------
    kng, _, _ = wls_through_origin(Bng, D, W)
    rng_resid = D - kng * Bng   # all grammar effect lives here
    g_cnt = np.array([c["grammar_count_rate"] for c in cells])
    g_sev = np.array([c["grammar_mean_severity"] for c in cells])
    # joint WLS: resid ~ a + b1*count + b2*severity + b3*count^2
    X = np.column_stack([np.ones_like(g_cnt), g_cnt, g_sev, g_cnt**2])
    Wm = np.diag(W)
    beta = np.linalg.solve(X.T @ Wm @ X, X.T @ Wm @ rng_resid)
    res2 = rng_resid - X @ beta
    s2 = float(np.sum(W * res2**2) / max(1, len(cells) - 4))
    cov = np.linalg.inv(X.T @ Wm @ X) * s2
    ses = np.sqrt(np.diag(cov))
    lines += ["", "== (2) MECHANISM ADJUDICATION (grammar left out of burden;"
              " residual = its full effect) ==",
              f"Spearman(resid, grammar count rate)    = "
              f"{spearman(g_cnt, rng_resid):+.3f}",
              f"Spearman(resid, grammar mean severity) = "
              f"{spearman(g_sev, rng_resid):+.3f}",
              "joint WLS resid ~ a + b1*count + b2*severity + b3*count^2:",
              f"  b1(count)    = {beta[1]:+.4f} +/- {ses[1]:.4f}",
              f"  b2(severity) = {beta[2]:+.4f} +/- {ses[2]:.4f}",
              f"  b3(count^2)  = {beta[3]:+.5f} +/- {ses[3]:.5f}   "
              "[b3>2se -> superlinear DENSITY COLLAPSE; "
              "b2>2se & b3~0 -> SEVERITY RESPONSE]"]

    # ---- (3) severity exponent gamma --------------------------------------
    lo, hi, npts = args.gamma_grid.split(":")
    gammas = np.linspace(float(lo), float(hi), int(npts))
    cnt_rates = {cat: np.array([c[f"{cat}_count_rate"] for c in cells])
                 for cat in CATEGORY_MAP}
    sev = {}
    for cat in CATEGORY_MAP:
        pen = np.array([c[f"{cat}_penalty_rate"] for c in cells])
        cnt = cnt_rates[cat]
        sev[cat] = np.where(cnt > 0, pen / np.maximum(cnt, 1e-12), 0.0)

    def burden_gamma(g, idx=None):
        ii = slice(None) if idx is None else idx
        tot = np.zeros(len(cells))
        for cat, lg in cat_lam.items():
            tot += lg * cnt_rates[cat] * np.where(
                cnt_rates[cat] > 0, sev[cat]**g, 0.0)
        return tot[ii]

    def fit_gamma(idx=None):
        ii = np.arange(len(cells)) if idx is None else idx
        best = (None, -np.inf)
        for g in gammas:
            bg = burden_gamma(g)[ii]
            kk, _, rr = wls_through_origin(bg, D[ii], W[ii])
            # maximize weighted R^2
            if rr > best[1]:
                best = (g, rr, kk)
        return best

    g_hat, r2_g, k_g = fit_gamma()
    # chapter-cluster bootstrap
    ch_idx = {ch: np.array([i for i, c in enumerate(cells)
                            if c["chapter"] == ch]) for ch in chapters}
    boots = []
    for _ in range(args.n_boot):
        pick = rng.choice(chapters, size=len(chapters), replace=True)
        idx = np.concatenate([ch_idx[ch] for ch in pick])
        boots.append(fit_gamma(idx)[0])
    g_lo, g_hi = np.percentile(boots, [2.5, 97.5])
    lines += ["", "== (3) severity exponent gamma "
              "(B = sum lambda*count*sev^gamma; 0=counts, 1=penalties) ==",
              f"gamma_hat = {g_hat:.2f}  (R^2 {r2_g:.3f}; k={k_g:+.4f})   "
              f"bootstrap 95% CI [{g_lo:.2f}, {g_hi:.2f}]  "
              f"(chapter-cluster, n={args.n_boot})",
              "adopt gamma>0 only if robust across methods/chapters — not to "
              "patch google_word_by_word (doc §4.4)."]

    # ---- verdicts ----------------------------------------------------------
    lines += ["", "== VERDICT SUMMARY ==",
              f"additivity: Spearman {rho:+.3f} "
              f"({'PASS' if rho >= SPEARMAN_PASS else 'FAIL'}); "
              f"zero-point {'PASS' if abs(a_i) < 2 * se_a_i else 'FAIL'}"]
    if is_wbw.any():
        wbw_res = float(np.mean(resid[is_wbw]))
        n_wbw = int(is_wbw.sum())
        # SE of the MEAN residual over wbw cells (cell SEs / sqrt(n))
        wbw_sem = float(np.sqrt(np.mean(
            [c["delta_se"]**2 for c, f in zip(cells, is_wbw) if f])
            / n_wbw))
        wbw_verdict = ("B UNDERPREDICTS damage - three-way divergence "
                       "CONFIRMED" if wbw_res > 2 * wbw_sem
                       else "within noise - divergence NOT confirmed")
        lines.append(f"wbw mean residual {wbw_res:+.3f} logits over "
                     f"{n_wbw} cells (SE of mean {wbw_sem:.3f}): "
                     f"{wbw_verdict}")
    else:
        lines.append("wbw excluded from this run")

    # ---- write outputs ------------------------------------------------------
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for c, rs, rg in zip(cells, resid, rng_resid):
        c["delta_pred"] = k * c["B_count"]
        c["resid"] = float(rs)
        c["resid_nogrammar_model"] = float(rg)
    suffix = "" if args.q_types == "both" else f"_{args.q_types}"
    csv_path = out_dir / f"step2_prediction{suffix}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cells[0].keys()))
        w.writeheader()
        w.writerows(cells)
    summary = "\n".join(lines)
    (out_dir / f"step2_summary{suffix}.txt").write_text(summary)
    print("\n" + summary)

    # ---- figure -------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    cmap = plt.get_cmap("tab10")
    ax = axes[0]
    for i, m in enumerate(methods):
        mk = np.array([c["method"] == m for c in cells])
        ax.errorbar(B[mk], D[mk], yerr=[c["delta_se"] for c, f
                                        in zip(cells, mk) if f],
                    fmt="o" if m != "google_word_by_word" else "*",
                    ms=6 if m != "google_word_by_word" else 13,
                    color=cmap(i % 10), label=m, lw=0, elinewidth=0.8,
                    capsize=2)
    xs = np.linspace(0, B.max() * 1.05, 50)
    ax.plot(xs, k * xs, "k-", lw=1.2, label=f"k*B (k={k:+.3f})")
    ax.set_xlabel("adequacy burden B_count")
    ax.set_ylabel("observed logit shift Delta_obs")
    ax.set_title(f"Step 2: observed vs predicted "
                 f"(Spearman {rho:+.2f}, R2 {r2:.2f})")
    ax.legend(fontsize=7)
    for j, (xv, ttl) in enumerate(
            [(g_cnt, "grammar COUNT rate (density collapse?)"),
             (g_sev, "grammar MEAN SEVERITY (severity response?)")]):
        ax2 = axes[j + 1]
        for i, m in enumerate(methods):
            mk = np.array([c["method"] == m for c in cells])
            ax2.scatter(xv[mk], rng_resid[mk], color=cmap(i % 10), s=30,
                        marker="o" if m != "google_word_by_word" else "*")
        ax2.axhline(0, color="grey", lw=0.7)
        ax2.set_xlabel(ttl)
        ax2.set_ylabel("residual (no-grammar burden model)")
        ax2.set_title(f"resid vs {ttl.split()[1].lower()}  Spearman "
                      f"{spearman(xv, rng_resid):+.2f}")
    plt.tight_layout()
    fig_path = out_dir / f"step2_prediction{suffix}.png"
    plt.savefig(fig_path, dpi=140)
    print(f"\n[out] {csv_path}\n[out] {out_dir}/step2_summary{suffix}.txt"
          f"\n[out] {fig_path}")


if __name__ == "__main__":
    main()
