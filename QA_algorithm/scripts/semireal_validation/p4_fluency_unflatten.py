#!/usr/bin/env python3
"""P4 - Do the 'flat' fluency defects (grammar, awkward) un-flatten at lower ability?

Two competing mechanisms make a defect read 'flat' on 1.7b:
  * priors-compensation : a strong model repairs the damaged translation from its
                          priors, hiding a real dose-response -> a WEAKER model should
                          REVEAL a gradient (lambda rises as theta falls).
  * floor compression   : the weak model is bunched near the guessing floor, so a real
                          gradient is squashed to ~0 (false-flat).

The discriminator is HEADROOM: if the weakest model's baseline (0% dose) accuracy sits
well ABOVE its qtype floor, it HAS room to drop, so a ~0 slope is genuine fluency-
blindness, not compression. We test, per fluency family x model x qtype:
  * lambda (per-SD logit dose slope), Wald z/p, and an ITEM-CLUSTERED bootstrap 95% CI
    (responses within an item are correlated; the cluster bootstrap is the honest CI),
  * a floor-aware (3-param guessing) refit,
  * headroom = baseline_acc@0% - floor,
and cross-check against:
  * a POSITIVE CONTROL: adequacy families (omission, mistranslation) at 1b must show a
    clearly non-zero slope, proving the test has power at the weakest respondent,
  * the cross-ability slope kappa = d lambda / d theta for the fluency families: a
    NEGATIVE kappa would be un-flattening; ~0/positive is not.
"""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "evaluation" / "outputs"
ANCHOR = REPO / "QA_algorithm" / "outputs"
OUTDIR = REPO / "QA_algorithm" / "outputs" / "reports" / "item_sensitivity"

MODELS = ["llama 1b", "1.5b", "1.7b"]
FLUENCY = ["grammar", "awkward"]
ADEQUACY = ["omission", "mistranslation"]          # positive control
CHAPTERS = range(1, 9)
DOSES = ["0%", "5%", "10%", "15%", "20%", "30%"]
GUESS = {"mcq": 0.25, "open": 0.05}
NBOOT = 1000
RNG = np.random.default_rng(20260721)


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


def gather(families):
    """(family, model, qtype) -> list of (item_key, q_raw=-dose, y)."""
    data = defaultdict(list)
    for ch in CHAPTERS:
        for m in MODELS:
            for fam in families:
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
                        key = f"luke{ch}:item{it.get('item_index')}:{qt}"
                        data[(fam, m, qt)].append((key, q, y))
    return data


def fit_slope(qraw, y, guess=0.0, ridge=1e-3, return_base=False):
    q = np.asarray(qraw, float); y = np.asarray(y, float)
    sd = q.std()
    if sd < 1e-9:
        return None
    qz = (q - q.mean()) / sd
    X = np.column_stack([np.ones(len(qz)), qz])
    b = np.zeros(2); g = guess
    H = None
    for _ in range(200):
        eta = X @ b
        s = 1.0 / (1.0 + np.exp(-eta))
        p = np.clip(g + (1 - g) * s, 1e-6, 1 - 1e-6)
        dp = (1 - g) * s * (1 - s)
        grad = X.T @ ((y - p) * dp / (p * (1 - p))) - ridge * b
        W = (dp ** 2) / (p * (1 - p))
        H = -(X.T * W) @ X - ridge * np.eye(2)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        b = b - step
        if np.max(np.abs(step)) < 1e-9:
            break
    try:
        se = float(np.sqrt(max(np.linalg.inv(-H)[1, 1], 0.0)))
    except Exception:
        se = float("nan")
    if not return_base:
        return float(b[1]), se
    qz0 = (0.0 - q.mean()) / sd
    p0 = g + (1 - g) / (1.0 + math.exp(-(b[0] + b[1] * qz0)))
    return float(b[1]), se, float(p0)


def cluster_bootstrap(obs, guess=0.0):
    """Item-clustered bootstrap of the per-SD slope. obs = list of (item_key,q,y)."""
    by_item = defaultdict(list)
    for k, q, y in obs:
        by_item[k].append((q, y))
    keys = list(by_item.keys())
    ests = []
    for _ in range(NBOOT):
        pick = RNG.choice(len(keys), size=len(keys), replace=True)
        qs, ys = [], []
        for idx in pick:
            for q, y in by_item[keys[idx]]:
                qs.append(q); ys.append(y)
        r = fit_slope(qs, ys, guess=guess)
        if r is not None:
            ests.append(r[0])
    if not ests:
        return None
    lo, hi = np.percentile(ests, [2.5, 97.5])
    return float(lo), float(hi), float(np.std(ests))


def main():
    th = load_theta()
    data = gather(FLUENCY + ADEQUACY)
    rows = []
    for (fam, m, qt), obs in sorted(data.items()):
        qs = [o[1] for o in obs]; ys = [o[2] for o in obs]
        plain = fit_slope(qs, ys, guess=0.0, return_base=True)
        floored = fit_slope(qs, ys, guess=GUESS[qt], return_base=True)
        if plain is None or floored is None:
            continue
        lam, se, base0 = plain
        lam_f, se_f, _ = floored
        boot = cluster_bootstrap(obs, guess=0.0)
        lo, hi, bse = boot if boot else (float("nan"),) * 3
        z = lam / bse if bse and bse == bse and bse > 0 else float("nan")
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))) if z == z else float("nan")
        rows.append({
            "family": fam, "kind": "fluency" if fam in FLUENCY else "adequacy",
            "model": m, "qtype": qt, "theta": round(th[qt][m], 3),
            "n": len(obs), "base_acc0": round(base0, 3),
            "floor": GUESS[qt], "headroom": round(base0 - GUESS[qt], 3),
            "lambda": round(lam, 4), "wald_se": round(se, 4),
            "lambda_floored": round(lam_f, 4),
            "boot_lo": round(lo, 4), "boot_hi": round(hi, 4), "boot_se": round(bse, 4),
            "z": round(z, 2) if z == z else "", "p": round(p, 4) if p == p else "",
            "sig05": int(z == z and abs(z) > 1.96),
        })

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / "p4_fluency_unflatten.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"wrote {out}\n")

    def kappa(fam, qt):
        pts = sorted((r["theta"], r["lambda"]) for r in rows if r["family"] == fam and r["qtype"] == qt)
        x = np.array([p[0] for p in pts]); y = np.array([p[1] for p in pts])
        return float(np.polyfit(x, y, 1)[0])

    for qt in ("open", "mcq"):
        print(f"===== {qt.upper()}  (floor g={GUESS[qt]}) =====")
        print(f"{'family':15}{'kind':9}{'model':9}{'theta':>7}{'base@0':>8}{'headroom':>9}"
              f"{'lambda':>9}{'boot95CI':>18}{'p':>8}{'sig':>4}")
        for fam in ADEQUACY + FLUENCY:
            for m in MODELS:
                r = next((x for x in rows if x["family"] == fam and x["model"] == m and x["qtype"] == qt), None)
                if not r:
                    continue
                ci = f"[{r['boot_lo']:+.3f},{r['boot_hi']:+.3f}]"
                print(f"{fam:15}{r['kind']:9}{m:9}{r['theta']:>7.2f}{r['base_acc0']:>8.2f}"
                      f"{r['headroom']:>9.2f}{r['lambda']:>+9.3f}{ci:>18}{str(r['p']):>8}{r['sig05']:>4}")
        print(f"  kappa d(lambda)/d(theta):  grammar={kappa('grammar',qt):+.3f}  "
              f"awkward={kappa('awkward',qt):+.3f}   (negative = UN-FLATTEN at low ability)\n")

    # verdict
    flu = [r for r in rows if r["kind"] == "fluency"]
    flu_1b = [r for r in flu if r["model"] == "llama 1b"]
    any_1b_sig = any(r["sig05"] and r["lambda"] > 0 for r in flu_1b)
    headroom_ok = all(r["headroom"] > 0.15 for r in flu_1b)
    adq_1b = [r for r in rows if r["kind"] == "adequacy" and r["model"] == "llama 1b"]
    ctrl_ok = all(r["sig05"] and r["lambda"] > 0 for r in adq_1b)
    print("VERDICT")
    print(f"  positive control (adequacy sig>0 at 1b, all cells): {ctrl_ok}")
    print(f"  1b fluency has headroom above floor (>0.15, all cells): {headroom_ok}")
    print(f"  any 1b fluency slope significantly >0 (un-flatten): {any_1b_sig}")
    if ctrl_ok and headroom_ok and not any_1b_sig:
        print("  => NO un-flattening. Flatness is informative (headroom present, test powered).")
        print("     'adequacy-not-fluency' STRENGTHENS: fluency-blindness holds at the weakest respondent.")
    else:
        print("  => see cells above; claim may need scoping.")


if __name__ == "__main__":
    main()
