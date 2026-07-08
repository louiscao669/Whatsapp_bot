#!/usr/bin/env python3
"""Fit per-item translation-sensitivity slopes s_i (+ item intercept c_i).

Model, for a response r given by answer-model m on item i, to a passage produced by
translation (chapter, method) whose quality is q_r:

    2-var (free intercept, DEFAULT):
        logit P(y_r = 1) = theta_r + c_i + s_i * q_r          (offset = theta_r)

    1-var (fixed anchor difficulty, fallback):
        logit P(y_r = 1) = (theta_r - b_i) + s_i * q_r         (offset = theta_r - b_i)

where
    theta_r : answer-model ability  (anchor IRT, per q_type; model_abilities)
    b_i     : item difficulty       (anchor IRT, per q_type; item_difficulties)   [1-var only]
    q_r     : STANDARDIZED translation quality of the (chapter, method) the response
              was given on  ->  z-scored MQM `mqm_quality_0_1` (higher = better)
    y_r     : BINARY correctness in {0,1}  (mcq: direct_correct; open: llm_label
              correct/incorrect -- the LLM judgment, NOT the continuous llm_score)

Both slopes and free intercepts are PARTIALLY POOLED:
    s_i ~ N(beta,  sigma_s^2)       c_i ~ N(c0, sigma_c^2)
with (c0, beta) taken from a global single-slope fit over all responses. This shrinks
thin / noisy items toward the population, which is what makes ~24 responses/item usable.

Per item the estimator AUTO-SELECTS the form (--difficulty auto):
  * enough events + quality spread  -> 2-var free-intercept fit
  * otherwise                       -> 1-var fit, using the anchor b_i if available,
                                       else the global intercept c0.
The chosen form is recorded per item in the `mode` column. `--difficulty free|anchor`
forces one form for every item (for clean comparisons).

The Fisher information used by the adaptive selector, s_i^2 * p (1-p), is exactly the
per-response term in this fit's Hessian for the slope, so a well-determined s_i (small SE)
is by construction an item that carries information about translation quality.

Outputs
  <out>.csv                 per-item: s_i, se, intercept, mode, diagnostics
  <out>.meta.json           standardization constants + run config
  <scatter>.png (optional)  s_i vs per-item Spearman rho from item_discrimination_spearman.py

Run
  python3 scripts/fit_item_sensitivity.py                      # real fit, defaults
  python3 scripts/fit_item_sensitivity.py --self-test          # synthetic recovery check
  python3 scripts/fit_item_sensitivity.py --difficulty anchor  # force 1-var everywhere
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SCORE_FILE = "scores_target_llama.json"  # filename inside each <chapter>/<model>/<method>/ dir

DEFAULT_MODELS = ["llama 1b", "1.5b", "1.7b"]  # must match anchor model_abilities keys
DEFAULT_METHODS = [
    "google_word_by_word", "mBART-50", "helsinki", "nllb-200-distilled-600M",
    "llm_prompt_low", "llm_prompt_medium", "nllb-200-1.3B", "llm_prompt_high",
]

# --- defect (translation-variant) axis ---------------------------------------
# Level dirs are named like "10%", or with a sub-family prefix: "name_10%",
# "style_10%" (inconsistency), "adversarial_10%"/"bad_10%"/"neutral_10%"
# (addition). The dose fraction d is parsed out; q = -d. The shared "0%" baseline
# is attached to every sub-family of its defect.
DEFECT_PREFIXES = ("name_", "style_", "adversarial_", "bad_", "neutral_")
DEFAULT_DEFECTS = [
    "omission", "mistranslation", "grammar", "awkward",
    "addition", "inconsistency", "local_inconsistency", "untranslated",
]


# --------------------------------------------------------------------------- utils
def sigmoid(z: np.ndarray) -> np.ndarray:
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)), np.exp(z) / (1.0 + np.exp(z)))


def fit_penalized_logistic(
    X: np.ndarray, offset: np.ndarray, y: np.ndarray,
    prior_mean: np.ndarray, prior_prec: np.ndarray,
    max_iter: int = 200, tol: float = 1e-9,
):
    """Newton-Raphson MAP for logit p = offset + X @ b, with diagonal Gaussian prior
    b ~ N(prior_mean, diag(1/prior_prec)).  Works for continuous y in [0, 1]
    (fractional Bernoulli).  Returns (coef, se, converged).  The prior guarantees a
    finite, invertible solution even under (quasi-)separation."""
    n, k = X.shape
    b = prior_mean.astype(float).copy()
    converged = False
    for _ in range(max_iter):
        eta = offset + X @ b
        p = sigmoid(eta)
        w = np.clip(p * (1.0 - p), 1e-9, None)
        grad = -X.T @ (y - p) + prior_prec * (b - prior_mean)
        H = (X.T * w) @ X + np.diag(prior_prec)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, grad, rcond=None)[0]
        b = b - step
        if np.max(np.abs(step)) < tol:
            converged = True
            break
    cov = np.linalg.inv(H)
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    return b, se, converged


# ----------------------------------------------------------------------- loading
def load_anchor(path: Path):
    d = json.loads(Path(path).read_text())
    theta = {m: v["theta"] for m, v in d.get("model_abilities", {}).items()}
    diff = {k: v.get("b_posterior", v.get("b_prior_mean", 0.0))
            for k, v in d.get("item_difficulties", {}).items()}
    return theta, diff


def load_mqm_quality(path: Path):
    """Return {(chapter:int, method:str): mqm_quality_0_1:float} (higher = better)."""
    q = {}
    with Path(path).open(newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                q[(int(row["chapter"]), row["method"])] = float(row["mqm_quality_0_1"])
            except (KeyError, ValueError):
                continue
    return q


def item_key(chapter: int, item_index, q_type: str) -> str:
    return f"luke{chapter}:item{item_index}:{q_type}"


def response_value(item: dict, q_type: str):
    """Binary correctness in {0, 1}. mcq -> direct_correct; open -> the LLM's
    correct/incorrect judgment (llm_label), NOT the continuous llm_score."""
    if q_type == "mcq":
        dc = item.get("direct_correct")
        return None if dc is None else (1.0 if dc else 0.0)
    lab = item.get("llm_label")
    if lab is None:
        return None
    lab = str(lab).strip().lower()
    if lab == "correct":
        return 1.0
    if lab == "incorrect":
        return 0.0
    return None


def assemble_rows(args, theta_by_qtype, q_by_cell):
    """Walk <eval_root>/luke<ch>/<model>/<method>/scores_target_llama.json and build a
    flat list of response rows.  Returns rows and a coverage summary."""
    rows = []
    missing_q = skipped_null = 0
    eval_root = Path(args.eval_root)
    for ch in args.chapters:
        for model in args.models:
            theta_open = theta_by_qtype["open"].get(model)
            theta_mcq = theta_by_qtype["mcq"].get(model)
            for method in args.methods:
                fp = eval_root / f"luke{ch}" / model / method / SCORE_FILE
                if not fp.exists():
                    continue
                q_raw = q_by_cell.get((ch, method))
                if q_raw is None:
                    missing_q += 1
                    continue
                data = json.loads(fp.read_text())
                for it in data.get("items", []):
                    q_type = it.get("q_type")
                    if q_type not in args.qtypes:
                        continue
                    theta = theta_open if q_type == "open" else theta_mcq
                    if theta is None:
                        continue
                    y = response_value(it, q_type)
                    if y is None:
                        skipped_null += 1
                        continue
                    rows.append({
                        "key": item_key(ch, it.get("item_index"), q_type),
                        "id": it.get("id"),
                        "chapter": ch, "q_type": q_type, "model": model, "method": method,
                        "theta": float(theta), "q_raw": float(q_raw), "y": float(y),
                    })
    return rows, {"missing_q_cells": missing_q, "skipped_null_y": skipped_null}


# -------------------------------------------------------------------------- fit
def choose_mode(diff_flag, n_obs, minority, q_spread, y_var, has_b, args):
    if diff_flag == "free":
        return "free"
    if diff_flag == "anchor":
        return "anchor" if has_b else "pooled1"
    # auto
    eligible2 = (
        n_obs >= args.min_obs and q_spread >= args.min_qspread and y_var > 1e-6
        and (minority is None or minority >= args.epv_min)
    )
    if eligible2:
        return "free"
    return "anchor" if has_b else "pooled1"


def fit_items(rows, diff_by_key, args):
    # standardize q over the DISTINCT (chapter, method) cells actually used
    cells = {(r["chapter"], r["method"]): r["q_raw"] for r in rows}
    cell_vals = np.array(list(cells.values()), dtype=float)
    q_mean, q_sd = float(cell_vals.mean()), float(cell_vals.std())
    if q_sd < 1e-12:
        raise SystemExit("Translation-quality (MQM) has ~zero spread across cells; cannot fit s_i.")
    for r in rows:
        r["q"] = (r["q_raw"] - q_mean) / q_sd

    # ---- global single-slope fit -> pooling centers (c0, beta) ----
    theta = np.array([r["theta"] for r in rows])
    qv = np.array([r["q"] for r in rows])
    yv = np.array([r["y"] for r in rows])
    Xg = np.column_stack([np.ones(len(rows)), qv])
    weak = np.array([1e-3, 1e-3])
    gcoef, _, _ = fit_penalized_logistic(Xg, theta, yv, np.zeros(2), weak)
    c0, beta = float(gcoef[0]), float(gcoef[1])

    prec_s = 1.0 / args.sigma_s ** 2
    prec_c = 1.0 / args.sigma_c ** 2

    # ---- per-item fits ----
    by_key = {}
    for r in rows:
        by_key.setdefault(r["key"], []).append(r)

    results = []
    for key, rs in sorted(by_key.items()):
        q_type = rs[0]["q_type"]
        th = np.array([r["theta"] for r in rs])
        q = np.array([r["q"] for r in rs])
        y = np.array([r["y"] for r in rs])
        n_obs = len(rs)
        q_spread = float(q.max() - q.min())
        y_var = float(y.var())
        binary = bool(np.all(np.isin(y, (0.0, 1.0))))  # both mcq and open are binary now
        minority = int(min((y > 0.5).sum(), (y <= 0.5).sum())) if binary else None
        b_i = diff_by_key.get(key)
        mode = choose_mode(args.difficulty, n_obs, minority, q_spread, y_var, b_i is not None, args)

        if mode == "free":
            X = np.column_stack([np.ones(n_obs), q])
            coef, se, conv = fit_penalized_logistic(
                X, th, y, np.array([c0, beta]), np.array([prec_c, prec_s]))
            c_i, s_i, se_s = float(coef[0]), float(coef[1]), float(se[1])
        else:
            X = q.reshape(-1, 1)
            if mode == "anchor":
                off, c_i = th - b_i, float(-b_i)
            else:  # pooled1
                off, c_i = th + c0, c0
            coef, se, conv = fit_penalized_logistic(
                X, off, y, np.array([beta]), np.array([prec_s]))
            s_i, se_s = float(coef[0]), float(se[0])

        results.append({
            "item_key": key, "id": rs[0]["id"], "q_type": q_type,
            "chapter": rs[0]["chapter"], "n_obs": n_obs,
            "n_events_minority": "" if minority is None else minority,
            "q_spread": round(q_spread, 4), "y_var": round(y_var, 5),
            "mode": mode, "s_i": round(s_i, 5), "se_s_i": round(se_s, 5),
            "c_i": round(c_i, 5), "b_anchor": "" if b_i is None else round(b_i, 5),
            "converged": int(conv),
        })
    meta = {
        "q_mean_raw": q_mean, "q_sd_raw": q_sd, "global_c0": c0, "global_beta": beta,
        "n_rows": len(rows), "n_items": len(results),
        "sigma_s": args.sigma_s, "sigma_c": args.sigma_c,
        "difficulty": args.difficulty, "min_obs": args.min_obs,
        "epv_min": args.epv_min, "min_qspread": args.min_qspread,
    }
    return results, meta


# -------------------------------------------------------------------- validation
def validation_scatter(results, spearman_csv: Path, out_png: Path):
    """Merge fitted s_i against per-item Spearman rho and scatter + report correlation."""
    if not spearman_csv.exists():
        print(f"[validate] {spearman_csv} not found; skipping scatter. "
              f"Generate it with: python3 evaluation/scripts/item_discrimination_spearman.py")
        return
    with spearman_csv.open(newline="") as fh:
        rd = csv.DictReader(fh)
        cols = rd.fieldnames or []
        id_col = next((c for c in cols if c.lower() in ("id", "item", "item_id")), None)
        rho_col = next((c for c in cols if "rho" in c.lower() or "spearman" in c.lower()), None)
        if not id_col or not rho_col:
            print(f"[validate] could not find id/rho columns in {spearman_csv} ({cols}); skipping.")
            return
        rho_by_id = {}
        for row in rd:
            try:
                rho_by_id[row[id_col]] = float(row[rho_col])
            except (ValueError, TypeError):
                continue
    xs, ys = [], []
    for r in results:
        rho = rho_by_id.get(r["id"])
        if rho is not None and r["se_s_i"] != "":
            xs.append(r["s_i"]); ys.append(rho)
    if len(xs) < 4:
        print(f"[validate] only {len(xs)} items matched the Spearman report; skipping scatter.")
        return
    xs, ys = np.array(xs), np.array(ys)
    rx = np.argsort(np.argsort(xs)); ry = np.argsort(np.argsort(ys))
    rho = float(np.corrcoef(rx, ry)[0, 1])
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(5.5, 5))
        ax.scatter(xs, ys, s=18, alpha=0.7)
        ax.axhline(0, lw=0.6, color="gray"); ax.axvline(0, lw=0.6, color="gray")
        ax.set_xlabel("fitted s_i  (logit per SD of translation quality)")
        ax.set_ylabel("per-item Spearman rho  (item_discrimination_spearman.py)")
        ax.set_title(f"s_i vs rho   (Spearman = {rho:.3f}, n = {len(xs)})")
        fig.tight_layout(); out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_png, dpi=130); plt.close(fig)
        print(f"[validate] Spearman(s_i, rho) = {rho:.3f} over n={len(xs)} items -> {out_png}")
    except Exception as exc:  # noqa: BLE001
        print(f"[validate] Spearman(s_i, rho) = {rho:.3f} (n={len(xs)}); plot skipped ({exc})")


# ------------------------------------------------------- defect (variant) axis
def parse_dose(level_name: str):
    """'name_10%' -> ('name', 0.10); '0%' -> ('', 0.0); non-dose dir -> None."""
    s = level_name
    fam = ""
    for pre in DEFECT_PREFIXES:
        if s.startswith(pre):
            fam, s = pre.rstrip("_"), s[len(pre):]
            break
    if not s.endswith("%"):
        return None
    try:
        return fam, float(s[:-1]) / 100.0
    except ValueError:
        return None


def response_value_continuous(item: dict, q_type: str):
    """Continuous correctness in [0,1] (fractional Bernoulli): mcq -> direct_correct
    (0/1); open -> llm_score (the graded score, richer than the binary label for a
    6-point dose ladder)."""
    if q_type == "mcq":
        dc = item.get("direct_correct")
        return None if dc is None else (1.0 if dc else 0.0)
    v = item.get("llm_score")
    return None if v is None else float(min(1.0, max(0.0, v)))


def assemble_rows_defect(args):
    """Walk <eval_root>/luke<ch>/<defect>/<level>/scores_target_llama.json. Returns
    response rows tagged with a defect sub-type; the shared 0% baseline is replicated
    into each sub-family so every ladder has its clean anchor."""
    rows = []
    skipped_null = no_scores = 0
    eval_root = Path(args.eval_root)
    for ch in args.chapters:
        for defect in args.defects:
            ddir = eval_root / f"luke{ch}" / defect
            if not ddir.is_dir():
                continue
            levels = {}
            for p in ddir.iterdir():
                if not p.is_dir():
                    continue
                parsed = parse_dose(p.name)
                if parsed is not None:
                    levels[p.name] = parsed
            fams = sorted({fam for fam, _ in levels.values() if fam})
            for lvl, (fam, d) in levels.items():
                fp = ddir / lvl / SCORE_FILE
                if not fp.exists():
                    no_scores += 1
                    continue
                data = json.loads(fp.read_text())
                # sub-types this level's rows belong to
                if fam:
                    subtypes = [f"{defect}:{fam}"]
                elif fams:                       # 0% baseline -> every family
                    subtypes = [f"{defect}:{f}" for f in fams]
                else:                            # defect has no sub-families
                    subtypes = [defect]
                for it in data.get("items", []):
                    qt = it.get("q_type")
                    if qt not in args.qtypes:
                        continue
                    y = response_value_continuous(it, qt)
                    if y is None:
                        skipped_null += 1
                        continue
                    for sub in subtypes:
                        rows.append({
                            "defect": sub, "base_defect": defect,
                            "family": fam if fam else "",
                            "key": item_key(ch, it.get("item_index"), qt),
                            "id": it.get("id"), "chapter": ch, "q_type": qt,
                            "d": d, "q_raw": -d, "y": float(y),
                        })
    return rows, {"levels_without_scores": no_scores, "skipped_null_y": skipped_null}


def fit_defect_axis(rows, args):
    """Per (item, defect sub-type): partially-pooled free-intercept logistic slope on
    standardized dose q_z (q = -d, z-scored WITHIN each defect sub-type). Reports the
    per-SD slope s_i (primary) and the interpretable per-unit-dose slope."""
    from collections import defaultdict
    prec_s, prec_c = 1.0 / args.sigma_s ** 2, 1.0 / args.sigma_c ** 2
    by_defect = defaultdict(list)
    for r in rows:
        by_defect[r["defect"]].append(r)

    results, defect_meta = [], {}
    for defect, drs in sorted(by_defect.items()):
        q = np.array([r["q_raw"] for r in drs], dtype=float)
        q_sd = float(q.std())
        if q_sd < 1e-9:
            defect_meta[defect] = {"skipped": "no dose spread", "n_rows": len(drs)}
            continue
        q_mean = float(q.mean())
        for r in drs:
            r["qz"] = (r["q_raw"] - q_mean) / q_sd

        yv = np.array([r["y"] for r in drs])
        qz = np.array([r["qz"] for r in drs])
        Xg = np.column_stack([np.ones(len(drs)), qz])
        gcoef, _, _ = fit_penalized_logistic(
            Xg, np.zeros(len(drs)), yv, np.zeros(2), np.array([1e-3, 1e-3]))
        c0, beta = float(gcoef[0]), float(gcoef[1])
        defect_meta[defect] = {
            "beta_z": round(beta, 4), "beta_per_dose": round(beta / q_sd, 4),
            "q_sd_raw": round(q_sd, 5), "n_rows": len(drs),
            "n_items": len({r["key"] for r in drs}),
        }

        by_item = defaultdict(list)
        for r in drs:
            by_item[r["key"]].append(r)
        for key, rs in sorted(by_item.items()):
            qz_i = np.array([r["qz"] for r in rs])
            y_i = np.array([r["y"] for r in rs])
            n = len(rs)
            spread_raw = float(max(r["d"] for r in rs) - min(r["d"] for r in rs))
            y_var = float(y_i.var())
            X = np.column_stack([np.ones(n), qz_i])
            coef, se, conv = fit_penalized_logistic(
                X, np.zeros(n), y_i, np.array([c0, beta]), np.array([prec_c, prec_s]))
            c_i, s_z, se_z = float(coef[0]), float(coef[1]), float(se[1])
            results.append({
                "item_key": key, "id": rs[0]["id"], "defect": defect,
                "base_defect": rs[0]["base_defect"], "family": rs[0]["family"],
                "q_type": rs[0]["q_type"], "chapter": rs[0]["chapter"],
                "n_obs": n, "n_levels": len({r["d"] for r in rs}),
                "dose_spread": round(spread_raw, 3), "y_var": round(y_var, 5),
                "s_i": round(s_z, 5), "se_s_i": round(se_z, 5),
                "s_per_dose": round(s_z / q_sd, 5),
                "c_i": round(c_i, 5), "converged": int(conv),
                "q_var_ok": int(spread_raw >= 0.1 and y_var > 1e-6),
            })
    meta = {
        "axis": "defect", "y": "continuous (mcq direct_correct / open llm_score)",
        "q": "q = -dose, z-scored within each defect sub-type",
        "sigma_s": args.sigma_s, "sigma_c": args.sigma_c,
        "n_rows": len(rows), "n_item_defect_cells": len(results),
        "per_defect": defect_meta,
    }
    return results, meta


def run_defect_axis(args):
    args.chapters = ([int(c) for c in args.chapters.split(",") if c.strip()]
                     if args.chapters.strip() else list(range(1, 9)))
    print(f"[fit:defect] chapters={args.chapters} defects={args.defects} qtypes={args.qtypes}")
    rows, cov = assemble_rows_defect(args)
    if not rows:
        raise SystemExit("No variant responses assembled -- check eval-root / defect names.")
    print(f"[fit:defect] assembled {len(rows)} responses "
          f"(levels_without_scores={cov['levels_without_scores']}, "
          f"skipped_null_y={cov['skipped_null_y']})")
    results, meta = fit_defect_axis(rows, args)

    out = Path(args.out_defect)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["item_key", "id", "defect", "base_defect", "family", "q_type", "chapter",
              "n_obs", "n_levels", "dose_spread", "y_var", "s_i", "se_s_i",
              "s_per_dose", "c_i", "converged", "q_var_ok"]
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in sorted(results, key=lambda d: (d["base_defect"], -d["s_i"])):
            w.writerow(r)
    out.with_name(out.stem + ".meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[fit:defect] wrote {len(results)} item-defect cells -> {out}")
    print("[fit:defect] per-defect global slope (beta_z, higher = more dose-sensitive):")
    for d, m in sorted(meta["per_defect"].items(),
                       key=lambda kv: -kv[1].get("beta_z", -9)):
        if "beta_z" in m:
            print(f"    {d:28} beta_z={m['beta_z']:+.3f}  "
                  f"n_items={m['n_items']}  n_rows={m['n_rows']}")
        else:
            print(f"    {d:28} SKIPPED ({m.get('skipped')})")
    return 0


# --------------------------------------------------------------------- self test
def self_test():
    rng = np.random.default_rng(0)
    n_items, thetas = 60, np.array([-0.97, 0.44, 0.60])
    q_levels = np.linspace(-1.5, 1.5, 8)  # 8 methods, standardized
    true_c = rng.normal(0.5, 0.8, n_items)
    true_s = rng.normal(0.8, 0.6, n_items)
    rows, diff = [], {}
    for i in range(n_items):
        key = f"luke1:item{i}:open"
        diff[key] = -true_c[i]
        for th in thetas:
            for j, q in enumerate(q_levels):
                p = 1.0 / (1.0 + math.exp(-(th + true_c[i] + true_s[i] * q)))
                # continuous score with modest noise, mirroring open-item llm_score in [0,1]
                y = float(np.clip(p + rng.normal(0.0, 0.1), 0.01, 0.99))
                rows.append({"key": key, "id": key, "chapter": 1, "q_type": "open",
                             "model": "m", "method": f"m{j}", "theta": th,
                             "q_raw": q, "y": y})
    args = argparse.Namespace(difficulty="free", min_obs=10, epv_min=6, min_qspread=0.75,
                              sigma_s=2.0, sigma_c=3.0)
    res, meta = fit_items(rows, diff, args)
    idx = np.array([int(r["item_key"].split("item")[1].split(":")[0]) for r in res])
    est = np.array([r["s_i"] for r in res]); tru = true_s[idx]
    r = float(np.corrcoef(est, tru)[0, 1]); rmse = float(np.sqrt(np.mean((est - tru) ** 2)))
    print(f"[self-test] n_items={len(res)}  corr(true_s, est_s)={r:.3f}  RMSE={rmse:.3f}")
    ok = r > 0.8
    print("[self-test] PASS" if ok else "[self-test] FAIL (corr <= 0.8)")
    return 0 if ok else 1


# --------------------------------------------------------------------------- cli
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eval-root", default=str(REPO_ROOT / "evaluation" / "outputs"))
    p.add_argument("--mqm-csv", default=str(REPO_ROOT / "evaluation" / "outputs" / "reports"
                                            / "mqm_translation_scores_1.7b_luke1_8.csv"))
    p.add_argument("--anchor-open", default=str(REPO_ROOT / "QA_algorithm" / "outputs"
                                                / "anchor_irt_estimates_open.json"))
    p.add_argument("--anchor-mcq", default=str(REPO_ROOT / "QA_algorithm" / "outputs"
                                               / "anchor_irt_estimates_mcq.json"))
    p.add_argument("--axis", choices=["method", "defect"], default="method",
                   help="method = MQM quality across the 8 methods; "
                        "defect = translation-variant dose ladders (q = -dose)")
    p.add_argument("--defects", default=",".join(DEFAULT_DEFECTS),
                   help="defect types to fit on the defect axis")
    p.add_argument("--out-defect", default=str(REPO_ROOT / "QA_algorithm" / "outputs" / "reports"
                                               / "item_sensitivity" / "s_item_by_defect.csv"))
    p.add_argument("--models", default=",".join(DEFAULT_MODELS))
    p.add_argument("--methods", default=",".join(DEFAULT_METHODS))
    p.add_argument("--chapters", default="", help="comma list; default = chapters present in MQM csv")
    p.add_argument("--qtypes", default="open,mcq")
    p.add_argument("--difficulty", choices=["auto", "free", "anchor"], default="auto")
    p.add_argument("--min-obs", type=int, default=12, help="min responses for a 2-var fit")
    p.add_argument("--epv-min", type=int, default=6, help="min minority-class events (mcq) for 2-var")
    p.add_argument("--min-qspread", type=float, default=0.75, help="min z-scored q range for 2-var")
    p.add_argument("--sigma-s", type=float, default=1.0, help="pooling SD for slope s_i")
    p.add_argument("--sigma-c", type=float, default=2.0, help="pooling SD for intercept c_i")
    p.add_argument("--out", default=str(REPO_ROOT / "QA_algorithm" / "outputs" / "reports"
                                        / "item_sensitivity" / "s_item.csv"))
    p.add_argument("--spearman-csv", default=str(REPO_ROOT / "QA_algorithm" / "outputs" / "reports"
                                                 / "item_level_grid_analysis"
                                                 / "item_discrimination_spearman.csv"))
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)

    if args.self_test:
        return self_test()

    args.models = [m.strip() for m in args.models.split(",") if m.strip()]
    args.methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    args.defects = [m.strip() for m in args.defects.split(",") if m.strip()]
    args.qtypes = [m.strip() for m in args.qtypes.split(",") if m.strip()]

    if args.axis == "defect":
        return run_defect_axis(args)

    theta_open, diff_open = load_anchor(Path(args.anchor_open))
    theta_mcq, diff_mcq = load_anchor(Path(args.anchor_mcq))
    theta_by_qtype = {"open": theta_open, "mcq": theta_mcq}
    diff_by_key = {**diff_open, **diff_mcq}
    q_by_cell = load_mqm_quality(Path(args.mqm_csv))

    if args.chapters.strip():
        args.chapters = [int(c) for c in args.chapters.split(",") if c.strip()]
    else:
        args.chapters = sorted({ch for (ch, _m) in q_by_cell})
    print(f"[fit] chapters={args.chapters} models={args.models} qtypes={args.qtypes} "
          f"difficulty={args.difficulty}")

    rows, cov = assemble_rows(args, theta_by_qtype, q_by_cell)
    if not rows:
        raise SystemExit("No responses assembled -- check paths / model dir names.")
    print(f"[fit] assembled {len(rows)} responses "
          f"(missing_q_cells={cov['missing_q_cells']}, skipped_null_y={cov['skipped_null_y']})")

    results, meta = fit_items(rows, diff_by_key, args)

    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["item_key", "id", "q_type", "chapter", "n_obs", "n_events_minority",
              "q_spread", "y_var", "mode", "s_i", "se_s_i", "c_i", "b_anchor", "converged"]
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader()
        for r in sorted(results, key=lambda d: -d["s_i"]):
            w.writerow(r)
    out.with_name(out.stem + ".meta.json").write_text(json.dumps(meta, indent=2))

    modes = {}
    for r in results:
        modes[r["mode"]] = modes.get(r["mode"], 0) + 1
    print(f"[fit] wrote {len(results)} items -> {out}")
    print(f"[fit] modes: {modes}")
    print(f"[fit] global c0={meta['global_c0']:.3f} beta={meta['global_beta']:.3f} "
          f"(q_mean={meta['q_mean_raw']:.5f}, q_sd={meta['q_sd_raw']:.5f})")

    if not args.no_validate:
        scatter = out.with_name(out.stem + "_vs_spearman.png")
        validation_scatter(results, Path(args.spearman_csv), scatter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
