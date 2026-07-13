#!/usr/bin/env python3
"""Revised H3 — 1PL adaptive question selection simulations.

Spec: EXPERIMENT_H3_1PL_ADAPTIVE_SELECTION_2026-07-08.md (project folder).

Phase C0 (this script, --phase c0): coverage calibration of the 1PL SE(q).
  Generate responses from a HETEROGENEOUS truth
      y_i ~ Bernoulli( sigma(theta_u - b_i + s_i * q*) ),   q* ~ N(0,1)
  with b_i from the anchor Rasch calibration and s_i resampled from the
  empirical q_var_ok distribution in s_item_by_defect.csv. Fit the SIMPLE
  1PL model (slope == 1) by 1-D MAP, record whether the nominal 95% CI
  covers q*. Outputs per cell (theta x n_items x pool):
    coverage, kappa = sd(qhat - q*) / mean(SE), bias, attenuation slope, rmse.

Phase C1 (--phase c1): adaptive vs random item selection — NOT YET IMPLEMENTED;
  run after the C0 decision gate (spec section 5).

Inputs (all existing):
  QA_algorithm/outputs/anchor_irt_estimates_open.json / _mcq.json
      -> b_posterior per item (102 each), theta ladder.
  QA_algorithm/outputs/reports/item_sensitivity/s_item_by_defect.csv
      -> empirical s_i distribution (q_var_ok rows only), defect family
         + q_type used for FILTERED-pool draws.

Pool conditions:
  FULL     — all 204 calibrated anchor items (open + mcq); s_i drawn from all
             q_var_ok rows.
  FILTERED — adequacy-probing pool: MCQ anchor items only (spec section 4,
             "prefer MCQ"); s_i drawn from q_var_ok rows whose defect class is
             adequacy-sensitive: base defect in {mistranslation, omission} or
             defect == addition:adversarial. Restricted further to q_type==mcq
             rows when at least --min-s-rows are available (group membership
             only — an item's own fitted s_i is never used for filtering).

Usage:
  python QA_algorithm/scripts/simulate_1pl_adaptive.py --phase c0
  python QA_algorithm/scripts/simulate_1pl_adaptive.py --phase c0 \
      --pool filtered --n-items 5 10 20 40 --theta -1 0 0.5 \
      --draws 1000 --seed 2026
Robustness re-runs (spec section 10):
  --s-obs-noise      add N(0, se_s_i^2) to each drawn s_i
  --b-noise-sd 0.5   generation uses b_i + N(0, sd^2); fit keeps calibrated b_i
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]  # QA_algorithm/
ANCHOR_OPEN = ROOT / "outputs" / "anchor_irt_estimates_open.json"
ANCHOR_MCQ = ROOT / "outputs" / "anchor_irt_estimates_mcq.json"
S_ITEM_CSV = ROOT / "outputs" / "reports" / "item_sensitivity" / "s_item_by_defect.csv"
OUT_DIR = ROOT / "outputs" / "adaptive_sim_1pl"

ADEQUACY_BASE = {"mistranslation", "omission"}
ADEQUACY_DEFECT = {"addition:adversarial"}


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


# ---------------------------------------------------------------- inputs


def load_anchor_items():
    """Return list of dicts: {key, b, q_type} from both anchor files."""
    items = []
    for path, q_type in ((ANCHOR_OPEN, "open"), (ANCHOR_MCQ, "mcq")):
        data = json.loads(path.read_text())
        for key, rec in data["item_difficulties"].items():
            items.append({"key": key, "b": float(rec["b_posterior"]), "q_type": q_type})
    return items


def load_s_rows():
    """Return q_var_ok rows of s_item_by_defect.csv."""
    with open(S_ITEM_CSV) as f:
        rows = list(csv.DictReader(f))
    ok = [r for r in rows if r["q_var_ok"].strip().lower() in ("1", "true")]
    for r in ok:
        r["s_i"] = float(r["s_i"])
        r["se_s_i"] = float(r["se_s_i"])
    return ok


def is_adequacy(row) -> bool:
    return row["base_defect"] in ADEQUACY_BASE or row["defect"] in ADEQUACY_DEFECT


def shrink_s_rows(s_rows):
    """Empirical-Bayes shrinkage of each s_i toward its defect-family mean.

    The fitted s_i are noisy estimates; their empirical spread overstates TRUE
    slope heterogeneity by the measurement-noise variance. Per defect class:
        tau^2 = max(0, var(s_i) - mean(se_s_i^2))   (method-of-moments)
        w_r   = tau^2 / (tau^2 + se_r^2)
        s_r  <- family_mean + w_r * (s_r - family_mean)
    Resampling from the shrunken values gives the OPTIMISTIC bracket for C0
    (true heterogeneity only); --s-obs-noise gives the pessimistic one.
    Mutates and returns s_rows; prints per-family shrink diagnostics.
    """
    by_defect = {}
    for r in s_rows:
        by_defect.setdefault(r["defect"], []).append(r)
    print("[shrink] empirical-Bayes toward defect-family means:")
    for defect, rows in sorted(by_defect.items()):
        s = np.array([r["s_i"] for r in rows])
        se = np.array([r["se_s_i"] for r in rows])
        mean = s.mean()
        tau2 = max(0.0, s.var(ddof=1) - np.mean(se**2))
        for r, se_r in zip(rows, se):
            w = tau2 / (tau2 + se_r**2) if tau2 > 0 else 0.0
            r["s_i"] = mean + w * (r["s_i"] - mean)
        s_new = np.array([r["s_i"] for r in rows])
        print(f"  {defect:<28} n={len(rows):>3}  mean={mean:+.3f}  "
              f"sd {s.std(ddof=1):.3f} -> {s_new.std(ddof=1):.3f}  "
              f"(tau={np.sqrt(tau2):.3f})")
    return s_rows


def build_pool(pool: str, items, s_rows, min_s_rows: int):
    """Return (b array, s_i array, se_s_i array, lam array, note).

    lam[j] = the CALIBRATED slope for s-row j's defect family = mean fitted s_i
    of that family within the selected s-row subset. This is what a deployed
    family-slope (lambda_g) model would use for an item probing that family —
    group membership only, never the row's own s_i.
    """
    if pool == "full":
        b = np.array([it["b"] for it in items])
        sr = s_rows
        note = f"FULL: {len(b)} items, {len(sr)} s-rows"
    else:
        mcq_items = [it for it in items if it["q_type"] == "mcq"]
        b = np.array([it["b"] for it in mcq_items])
        adeq = [r for r in s_rows if is_adequacy(r)]
        adeq_mcq = [r for r in adeq if r["q_type"] == "mcq"]
        if len(adeq_mcq) >= min_s_rows:
            sr = adeq_mcq
            note = f"FILTERED: {len(b)} mcq items, {len(sr)} adequacy+mcq s-rows"
        else:
            sr = adeq
            note = (f"FILTERED: {len(b)} mcq items, {len(sr)} adequacy s-rows "
                    f"(mcq-only had {len(adeq_mcq)} < {min_s_rows}, using all q_types)")
    s = np.array([r["s_i"] for r in sr])
    se = np.array([r["se_s_i"] for r in sr])
    fams = [r["defect"] for r in sr]
    fam_mean = {f: s[[i for i, g in enumerate(fams) if g == f]].mean()
                for f in set(fams)}
    lam = np.array([fam_mean[f] for f in fams])
    return b, s, se, lam, note


# ---------------------------------------------------------------- 1PL MAP


def fit_q_map(y, theta, b, lam=None, sigma_q=1.0, iters=60):
    """Vectorized 1-D Newton MAP for q under P = sigma(theta - b + lam*q).

    y: (R, n) responses in {0,1}; b: (R, n) difficulties; theta: scalar;
    lam: (R, n) fitted slopes (None -> slope==1 plain 1PL).
    Returns qhat (R,), se (R,).
    Log-posterior is strictly concave in q -> Newton from 0 converges.
    """
    if lam is None:
        lam = 1.0
    q = np.zeros(y.shape[0])
    for _ in range(iters):
        p = sigmoid(theta - b + lam * q[:, None])
        grad = (lam * (y - p)).sum(axis=1) - q / sigma_q**2
        hess = -(lam**2 * p * (1 - p)).sum(axis=1) - 1.0 / sigma_q**2
        step = grad / hess
        q -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    p = sigmoid(theta - b + lam * q[:, None])
    se = 1.0 / np.sqrt((lam**2 * p * (1 - p)).sum(axis=1) + 1.0 / sigma_q**2)
    return q, se


# ---------------------------------------------------------------- Phase C0


def run_c0_cell(rng, theta, n_items, pool_b, pool_s, pool_se, pool_lam, draws,
                sigma_q, s_obs_noise, b_noise_sd, fit_slope):
    R = draws
    q_star = rng.standard_normal(R)

    # items without replacement per replicate
    idx = np.argsort(rng.random((R, pool_b.size)), axis=1)[:, :n_items]
    b = pool_b[idx]  # (R, n)

    # s_i resampled with replacement from the empirical distribution
    s_idx = rng.integers(0, pool_s.size, size=(R, n_items))
    s = pool_s[s_idx]
    if s_obs_noise:
        s = s + rng.standard_normal((R, n_items)) * pool_se[s_idx]

    # heterogeneous truth (optional b perturbation in generation only)
    b_true = b + (rng.standard_normal((R, n_items)) * b_noise_sd if b_noise_sd else 0.0)
    p_true = sigmoid(theta - b_true + s * q_star[:, None])
    y = (rng.random((R, n_items)) < p_true).astype(float)

    # fit: slope==1 (unit) or calibrated family-mean slopes (group)
    lam = pool_lam[s_idx] if fit_slope == "group" else None
    q_hat, se = fit_q_map(y, theta, b, lam=lam, sigma_q=sigma_q)

    err = q_hat - q_star
    hit = np.abs(err) <= 1.96 * se
    atten = np.cov(q_hat, q_star)[0, 1] / np.var(q_star)
    return {
        "coverage": float(hit.mean()),
        "kappa": float(err.std(ddof=1) / se.mean()),
        "bias": float(err.mean()),
        "attenuation_slope": float(atten),
        "rmse": float(np.sqrt((err**2).mean())),
        "mean_se": float(se.mean()),
    }


def run_c0(args):
    items = load_anchor_items()
    s_rows = load_s_rows()
    if args.exclude_defects:
        s_rows = [r for r in s_rows if r["defect"] not in args.exclude_defects]
        print(f"[exclude] {args.exclude_defects} -> {len(s_rows)} s-rows remain")
    if args.s_shrink:
        if args.s_obs_noise:
            raise SystemExit("--s-shrink and --s-obs-noise are opposite brackets; pick one.")
        s_rows = shrink_s_rows(s_rows)
    pools = ["full", "filtered"] if args.pool == "both" else [args.pool]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / args.out_name
    results = []
    for pool in pools:
        pool_b, pool_s, pool_se, pool_lam, note = build_pool(
            pool, items, s_rows, args.min_s_rows)
        print(f"[pool] {note}  | s_i median={np.median(pool_s):.3f} "
              f"mean={pool_s.mean():.3f} sd={pool_s.std(ddof=1):.3f}"
              f"  | fit_slope={args.fit_slope}")
        for theta in args.theta:
            for n_items in args.n_items:
                rng = np.random.default_rng(
                    [args.seed, pools.index(pool), int(theta * 100) + 1000, n_items])
                cell = run_c0_cell(rng, theta, n_items, pool_b, pool_s, pool_se,
                                   pool_lam, args.draws, args.sigma_q,
                                   args.s_obs_noise, args.b_noise_sd, args.fit_slope)
                cell.update(pool=pool, theta=theta, n_items=n_items,
                            draws=args.draws, s_obs_noise=int(args.s_obs_noise),
                            s_shrink=int(args.s_shrink), fit_slope=args.fit_slope,
                            b_noise_sd=args.b_noise_sd, seed=args.seed)
                results.append(cell)
                print(f"  theta={theta:+.1f} n={n_items:>3}  "
                      f"coverage={cell['coverage']:.3f}  kappa={cell['kappa']:.3f}  "
                      f"bias={cell['bias']:+.3f}  atten={cell['attenuation_slope']:.3f}  "
                      f"rmse={cell['rmse']:.3f}")

    cols = ["pool", "theta", "n_items", "draws", "coverage", "kappa", "bias",
            "attenuation_slope", "rmse", "mean_se", "s_obs_noise", "s_shrink",
            "fit_slope", "b_noise_sd", "seed"]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(results)
    print(f"\n[out] {out_path}")

    # ---- decision gate (spec section 5)
    filt = [r for r in results if r["pool"] == "filtered"]
    if filt:
        cov = np.array([r["coverage"] for r in filt])
        kap = np.array([r["kappa"] for r in filt])
        att = np.array([r["attenuation_slope"] for r in filt])
        print("\n[decision gate — FILTERED pool]")
        print(f"  coverage: min={cov.min():.3f} mean={cov.mean():.3f}   "
              f"kappa: max={kap.max():.3f} mean={kap.mean():.3f}   "
              f"attenuation: min={att.min():.3f}")
        if cov.min() >= 0.85 and kap.max() <= 1.6:
            print("  -> PASS: proceed with 1PL + kappa (use per-n_items kappa in C1).")
        elif cov.min() < 0.70:
            print("  -> FAIL: coverage collapses; fall back to two-group slope model.")
        else:
            print("  -> MARGINAL: inspect per-cell table; consider two-group slope model "
                  "if attenuation << 1.")
    return results


# ---------------------------------------------------------------- Phase C1


def load_kappa_fn(args, pool):
    """kappa(n) for the stopping rule: scalar --kappa, or interpolated per-n
    from a C0 output CSV (rows matching this pool; mean over theta)."""
    if args.kappa is not None:
        return lambda n: args.kappa
    path = OUT_DIR / args.kappa_csv
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if r["pool"] == pool]
    if not rows:
        raise SystemExit(f"no rows for pool={pool} in {path}; run C0 first or pass --kappa")
    by_n = {}
    for r in rows:
        by_n.setdefault(int(r["n_items"]), []).append(float(r["kappa"]))
    ns = np.array(sorted(by_n))
    ks = np.array([np.mean(by_n[n]) for n in ns])
    return lambda n: float(np.interp(n, ns, ks))


def run_c1_cell(rng, theta, arm, pool_b, pool_s, pool_se, pool_lam, args, kappa_fn):
    """One C1 cell: R sequential runs, one selector, to the corrected stop rule.

    Selection (ADAPTIVE) = max expected Fisher info lam_i^2 * p(1-p) among unused
    items (reduces to argmin |b_i - (theta+qhat)| when lam is constant, per spec §6).
    """
    R, P = args.draws, pool_b.size
    group = args.fit_slope == "group"
    max_steps = min(args.max_items, P)
    q_star = rng.standard_normal(R)
    s_idx = rng.integers(0, pool_s.size, size=(R, P))
    s_true = pool_s[s_idx]
    if args.s_obs_noise:
        s_true = s_true + rng.standard_normal((R, P)) * pool_se[s_idx]
    lam_it = pool_lam[s_idx] if group else np.ones((R, P))

    used = np.zeros((R, P), bool)
    qhat = np.zeros(R)
    se = np.full(R, args.sigma_q)
    Y = np.zeros((R, max_steps)); B = np.zeros((R, max_steps)); L = np.ones((R, max_steps))
    stop_step = np.zeros(R, int)
    active = np.ones(R, bool)
    exposure = np.zeros(P, int)
    se_curve = []
    rows = np.arange(R)

    for k in range(max_steps):
        if arm == "adaptive":
            p_exp = sigmoid(theta - pool_b[None, :] + lam_it * qhat[:, None])
            score = lam_it**2 * p_exp * (1 - p_exp)
        else:
            score = rng.random((R, P))
        score[used] = -np.inf
        choice = score.argmax(axis=1)
        used[rows, choice] = True
        np.add.at(exposure, choice[active], 1)

        bi = pool_b[choice]
        si = s_true[rows, choice]
        y = (rng.random(R) < sigmoid(theta - bi + si * q_star)).astype(float)
        Y[:, k], B[:, k], L[:, k] = y, bi, lam_it[rows, choice]

        qh, se_k = fit_q_map(Y[:, :k + 1], theta, B[:, :k + 1],
                             lam=L[:, :k + 1] if group else None, sigma_q=args.sigma_q)
        qhat = np.where(active, qh, qhat)
        se = np.where(active, se_k, se)
        se_curve.append((k + 1, float(se_k[active].mean()), int(active.sum())))

        newly = active & (kappa_fn(k + 1) * se < args.tau)
        stop_step[newly] = k + 1
        active &= ~newly
        if not active.any():
            break

    censored = active
    stop_step[censored] = max_steps
    kap_at_stop = np.array([kappa_fn(n) for n in stop_step])
    err = qhat - q_star
    hit = np.abs(err) <= 1.96 * kap_at_stop * se
    return {
        "median_items": float(np.median(stop_step)),
        "iqr_lo": float(np.percentile(stop_step, 25)),
        "iqr_hi": float(np.percentile(stop_step, 75)),
        "mean_items": float(stop_step.mean()),
        "censor_rate": float(censored.mean()),
        "mean_abs_err": float(np.abs(err).mean()),
        "coverage_at_stop": float(hit.mean()),
        "max_exposure_share": float(exposure.max() / max(1, exposure.sum())),
    }, se_curve, exposure


def run_c1(args):
    items = load_anchor_items()
    s_rows = load_s_rows()
    if args.exclude_defects:
        s_rows = [r for r in s_rows if r["defect"] not in args.exclude_defects]
        print(f"[exclude] {args.exclude_defects} -> {len(s_rows)} s-rows remain")
    if args.s_shrink:
        s_rows = shrink_s_rows(s_rows)
    pools = ["full", "filtered"] if args.pool == "both" else [args.pool]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results, curves, expo_rows = [], [], []
    for pool in pools:
        pool_b, pool_s, pool_se, pool_lam, note = build_pool(
            pool, items, s_rows, args.min_s_rows)
        kappa_fn = load_kappa_fn(args, pool)
        print(f"[pool] {note} | fit_slope={args.fit_slope} | "
              f"kappa(5..40)={kappa_fn(5):.3f}..{kappa_fn(40):.3f} | tau={args.tau}")
        for size in args.pool_sizes:
            if size and size < pool_b.size:
                sub_rng = np.random.default_rng([args.seed, 77, size])
                sub = np.sort(sub_rng.choice(pool_b.size, size, replace=False))
                b_use = pool_b[sub]
            else:
                size, b_use = pool_b.size, pool_b
            for theta in args.theta:
                for arm in ("adaptive", "random"):
                    rng = np.random.default_rng(
                        [args.seed, pools.index(pool), size,
                         int(theta * 100) + 1000, arm == "adaptive"])
                    cell, curve, expo = run_c1_cell(
                        rng, theta, arm, b_use, pool_s, pool_se, pool_lam,
                        args, kappa_fn)
                    meta = dict(pool=pool, pool_size=size, theta=theta, arm=arm,
                                draws=args.draws, tau=args.tau,
                                fit_slope=args.fit_slope, seed=args.seed)
                    results.append({**meta, **cell})
                    curves += [{**meta, "step": s, "mean_se": m, "n_active": a}
                               for s, m, a in curve]
                    expo_rows += [{**meta, "item_idx": i, "count": int(c)}
                                  for i, c in enumerate(expo) if c]
                    print(f"  size={size:>3} theta={theta:+.1f} {arm:<8} "
                          f"items-to-stop median={cell['median_items']:.0f} "
                          f"[{cell['iqr_lo']:.0f},{cell['iqr_hi']:.0f}] "
                          f"censor={cell['censor_rate']:.2f} "
                          f"|err|={cell['mean_abs_err']:.3f} "
                          f"cov@stop={cell['coverage_at_stop']:.3f} "
                          f"maxexp={cell['max_exposure_share']:.2f}")

    def dump(name, rows):
        with open(OUT_DIR / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"[out] {OUT_DIR / name}")

    pre = args.out_prefix
    dump(f"{pre}c1_items_to_confidence.csv", results)
    dump(f"{pre}c1_se_curves.csv", curves)
    dump(f"{pre}c1_exposure.csv", expo_rows)
    return results


# ---------------------------------------------------------------- CLI


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["c0", "c1"], required=True)
    ap.add_argument("--pool", choices=["full", "filtered", "both"], default="both")
    ap.add_argument("--n-items", type=int, nargs="+", default=[5, 10, 20, 40])
    ap.add_argument("--theta", type=float, nargs="+", default=[-1.0, 0.0, 0.5])
    ap.add_argument("--tau", type=float, default=0.3, help="C1 stop threshold (unused in C0)")
    ap.add_argument("--kappa", type=float, default=None,
                    help="C1 inflation factor (scalar override; default = interpolate "
                         "per-n from --kappa-csv)")
    ap.add_argument("--kappa-csv", default="c0_coverage_lambda.csv",
                    help="C0 output CSV (in outputs/adaptive_sim_1pl/) to read kappa from")
    ap.add_argument("--max-items", type=int, default=40, help="C1 cap per run (censored)")
    ap.add_argument("--pool-sizes", type=int, nargs="+", default=[0, 40, 20],
                    help="C1 scarcity sweep; 0 = full pool")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--sigma-q", type=float, default=1.0)
    ap.add_argument("--min-s-rows", type=int, default=30,
                    help="min mcq-only adequacy s-rows before falling back to all q_types")
    ap.add_argument("--s-obs-noise", action="store_true",
                    help="add N(0, se_s_i^2) noise to drawn s_i (PESSIMISTIC bracket)")
    ap.add_argument("--s-shrink", action="store_true",
                    help="EB-shrink s_i toward defect-family means before resampling "
                         "(OPTIMISTIC bracket: true heterogeneity only)")
    ap.add_argument("--exclude-defects", nargs="+", default=[],
                    help="defect families to drop from the s distribution (e.g. the "
                         "degenerate local_inconsistency:name local_inconsistency:style)")
    ap.add_argument("--fit-slope", choices=["unit", "group"], default="unit",
                    help="fitted slope: 'unit' = plain 1PL (slope 1); 'group' = "
                         "calibrated family-mean slopes lambda_g (fallback model)")
    ap.add_argument("--b-noise-sd", type=float, default=0.0,
                    help="perturb b in GENERATION only, N(0, sd^2) (robustness, spec sec.10)")
    ap.add_argument("--out-name", default="c0_coverage.csv")
    ap.add_argument("--out-prefix", default="", help="prefix for C1 output CSVs")
    args = ap.parse_args()

    if args.phase == "c0":
        run_c0(args)
    else:
        run_c1(args)


if __name__ == "__main__":
    main()
