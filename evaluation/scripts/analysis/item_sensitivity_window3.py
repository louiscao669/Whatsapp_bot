#!/usr/bin/env python3
"""Per-item sensitivity s_i + tau^2 on the 3-verse-window data, ADEQUACY FAMILIES.

[UPDATED 2026-07-27] The pilot design moved from omission {0,10,20,30} + mistranslation {20}
to **omission AND mistranslation each at {15, 30}%** (see HUMAN_PILOT_DESIGN_2026-07-27), so:
  * the default omission ladder is now {0, 15, 30} (was {0, 10, 20, 30});
  * mistranslation now HAS a ladder ({0, 15, 30}) and is fitted too -- it used to be a single
    20% point carrying no per-item slope.

The 0% dose for BOTH families is the shared clean anchor `omission/0%` (the pilot delivers one
clean condition; there is no separate `mistranslation/0%` at window=3). The two families
therefore share their anchor cell, so their s_i are not statistically independent -- fine for
ranking/transfer use (H-T7), worth stating in any joint test.

Reads scores_target_window3_v2.json ONLY (never the old whole-passage blend) and reuses p2's
EXACT fit + variance decomposition, so tau^2 stays directly comparable to the 07-21 whole-
passage p2 numbers (printed side by side, read from p2_item_variance_component.csv).

  python evaluation/scripts/analysis/item_sensitivity_window3.py                    # both families, {0,15,30}
  python evaluation/scripts/analysis/item_sensitivity_window3.py --families omission --doses 0 10 20 30
  python evaluation/scripts/analysis/item_sensitivity_window3.py --no-per-item      # aggregate only
"""
from __future__ import annotations
import argparse, csv, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "QA_algorithm" / "scripts" / "semireal_validation"))
# reuse the identical math used by the old battery
from p2_item_variance_component import fit_item, decompose, zscore_family, load_theta  # noqa: E402

MODELS = ["llama 1b", "1.5b", "1.7b"]
DEFAULT_FAMILIES = ["omission", "mistranslation"]
DEFAULT_DOSES = [0, 15, 30]          # 2026-07-27 design; clean anchor supplies the 0
CLEAN_COND = "omission/0%"           # shared 0-dose cell for every family
EVAL = REPO / "evaluation" / "outputs"
SCORE = "scores_target_window3_v2.json"
OUT_DIR = REPO / "QA_algorithm" / "outputs" / "reports" / "item_sensitivity"
# 07-21 whole-passage p2 baselines for the side-by-side (falls back to these if the CSV is gone)
OLD_CSV = OUT_DIR / "p2_item_variance_component.csv"
OLD_FALLBACK = {
    "omission": {"n_items": 166, "obs": 17.7, "sd": 0.9896, "rms": 0.7388,
                 "tau2": 0.4336, "lo": 0.0777, "hi": 0.9397},
    "mistranslation": {"n_items": 167, "obs": 17.4, "sd": 1.3863, "rms": 0.9289,
                       "tau2": 1.0589, "lo": 0.4745, "hi": 1.643},
}


def load_old(family):
    if OLD_CSV.exists():
        for row in csv.DictReader(OLD_CSV.open(encoding="utf-8")):
            if row["family"] == family:
                return {"n_items": int(row["n_items"]), "obs": float(row["mean_obs_per_item"]),
                        "sd": float(row["sd_s_i"]), "rms": float(row["rms_se"]),
                        "tau2": float(row["tau2"]), "lo": float(row["tau2_lo95"]),
                        "hi": float(row["tau2_hi95"])}
    return OLD_FALLBACK.get(family)


def cell_dir(family, dose):
    """0% resolves to the shared clean anchor; every other dose to the family's own cell."""
    return CLEAN_COND if dose == 0 else f"{family}/{dose}%"


def yval(it):
    if it.get("q_type") == "mcq":
        dc = it.get("direct_correct")
        return None if dc is None else (1.0 if dc else 0.0)
    v = it.get("llm_score")
    return None if v is None else float(min(1.0, max(0.0, v)))


def assemble(family, doses, chapters, models):
    theta = load_theta()                       # {'open':{model:θ}, 'mcq':{model:θ}} (07-12 anchors)
    rows, missing = [], []
    for ch in chapters:
        for m in models:
            for dose in doses:
                cond = cell_dir(family, dose)
                fp = EVAL / f"luke{ch}" / m / cond / SCORE
                if not fp.exists():
                    missing.append(f"luke{ch}/{m}/{cond}")
                    continue
                for it in json.loads(fp.read_text()).get("items", []):
                    qt = it.get("q_type")
                    y = yval(it)
                    if y is None:
                        continue
                    th = theta.get(qt, {}).get(m)
                    d = dose / 100.0
                    rows.append({"key": (ch, it["id"], qt), "y": float(y),
                                 "theta": (float(th) if th is not None else None),
                                 "d": d, "q_raw": -d})
    return rows, missing


def fit_family(family, doses, chapters, models, nboot, rng):
    rows, missing = assemble(family, doses, chapters, models)
    if not rows:
        return None, missing
    # sets r["qz"]; z-scored WITHIN this family's ladder. Returns None when the surviving
    # cells carry no dose spread (e.g. only the clean anchor was found because this family's
    # dose cells have not been answered yet) -> no slope is identifiable, so bail out loudly
    # instead of dying on a missing "qz" downstream.
    if zscore_family(rows) is None:
        return None, missing
    by_item = defaultdict(list)
    for r in rows:
        by_item[r["key"]].append(r)

    fitted, ceiling_skips = {}, 0
    for k, irs in by_item.items():
        f = fit_item(irs)                      # (s_i, se_i) via p2's penalized logistic, θ offset
        if f is not None:
            fitted[k] = (f, len(irs))
        else:
            ceiling_skips += 1
    if not fitted:
        return None, missing

    items = [v[0] for v in fitted.values()]
    obs = float(np.mean([v[1] for v in fitted.values()]))
    var_s, mean_se2, tau2 = decompose(items)

    keys = list(fitted.keys())
    taus = []
    for _ in range(nboot):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        _, _, t2 = decompose([fitted[keys[i]][0] for i in pick])
        taus.append(t2)
    lo, hi = np.percentile(taus, [2.5, 97.5])
    return {"family": family, "fitted": fitted, "n_items": len(items), "obs": obs,
            "sd": var_s ** 0.5, "rms": mean_se2 ** 0.5, "tau2": tau2, "lo": lo, "hi": hi,
            "ceiling_skips": ceiling_skips}, missing


def write_per_item(res, doses, out_dir):
    """Per-item s_i table — this is the H-T7 benchmark (ranking transfer to human slopes)."""
    dose_tag = "_".join(str(d) for d in doses)
    path = out_dir / f"s_item_window3_{res['family']}_{dose_tag}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["family", "chapter", "item_id", "q_type", "s_i", "se_i", "n_obs"])
        rank = sorted(res["fitted"].items(), key=lambda kv: kv[1][0][0])
        for (ch, iid, qt), ((s, se), n) in rank:
            w.writerow([res["family"], ch, iid, qt, f"{s:.6f}", f"{se:.6f}", n])
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--families", nargs="+", default=DEFAULT_FAMILIES,
                    help=f"defect families to fit; default {DEFAULT_FAMILIES}")
    ap.add_argument("--doses", type=int, nargs="+", default=DEFAULT_DOSES,
                    help=f"dose ladder in percent; 0 = the shared clean anchor. "
                         f"Default {DEFAULT_DOSES} (2026-07-27 design).")
    ap.add_argument("--models", nargs="+", default=MODELS)
    ap.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    ap.add_argument("--nboot", type=int, default=600)
    ap.add_argument("--seed", type=int, default=20260727)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--no-per-item", action="store_true",
                    help="skip the per-item s_i CSVs (aggregate table only)")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ladder = "{" + ", ".join(f"{d}%" for d in args.doses) + "}"

    print("=" * 92)
    print(f"Per-item sensitivity — OLD (whole-passage, 07-21) vs NEW (3-verse window, {ladder})")
    print("=" * 92)
    print(f"{'family':16}{'':6}{'n_items':>9}{'obs/item':>10}{'SD(s_i)':>10}{'rms_se':>9}"
          f"{'tau^2':>9}{'95% CI':>18}")

    summary_rows = []
    for family in args.families:
        res, missing = fit_family(family, args.doses, args.chapters, args.models,
                                  args.nboot, rng)
        old = load_old(family)
        if old:
            old_ci = f"[{old['lo']:+.2f},{old['hi']:+.2f}]"
            print(f"{family:16}{'OLD':6}{old['n_items']:>9}{old['obs']:>10.1f}{old['sd']:>10.4f}"
                  f"{old['rms']:>9.4f}{old['tau2']:>+9.3f}{old_ci:>18}")
        if res is None:
            print(f"{family:16}{'NEW':6}{'— no scored cells found —':>56}")
            if missing:
                print(f"{'':22}missing: {len(missing)} cells, e.g. {missing[:3]}")
            continue
        new_ci = f"[{res['lo']:+.2f},{res['hi']:+.2f}]"
        print(f"{family:16}{'NEW':6}{res['n_items']:>9}{res['obs']:>10.1f}{res['sd']:>10.4f}"
              f"{res['rms']:>9.4f}{res['tau2']:>+9.3f}{new_ci:>18}")
        verdict = ("REVIVED (per-item signal real)" if res["lo"] > 0
                   else "tau=0 (per-item signal not resolved)")
        print(f"{'':22}verdict: {verdict}   dropped (ceiling/no-spread): {res['ceiling_skips']}"
              f"   missing cells: {len(missing)}")
        if missing:
            print(f"{'':22}missing e.g.: {missing[:3]}")
        if not args.no_per_item:
            print(f"{'':22}per-item s_i -> {write_per_item(res, args.doses, args.out_dir)}")
        summary_rows.append(res)
        print("-" * 92)

    if summary_rows:
        dose_tag = "_".join(str(d) for d in args.doses)
        path = args.out_dir / f"item_sensitivity_window3_{dose_tag}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["family", "doses", "n_items", "mean_obs_per_item", "sd_s_i", "rms_se",
                        "tau2", "tau2_lo95", "tau2_hi95", "signal"])
            for r in summary_rows:
                w.writerow([r["family"], "|".join(str(d) for d in args.doses), r["n_items"],
                            f"{r['obs']:.1f}", f"{r['sd']:.4f}", f"{r['rms']:.4f}",
                            f"{r['tau2']:.4f}", f"{r['lo']:.4f}", f"{r['hi']:.4f}",
                            "REVIVED" if r["lo"] > 0 else "tau=0"])
        print(f"wrote {path}")

    n_doses = len(args.doses)
    print("\nNotes:")
    print(f" - obs/item at full coverage = {n_doses} doses x {len(args.models)} models = "
          f"{n_doses * len(args.models)} (OLD was 6x3=18): fewer doses -> larger se_i -> smaller "
          f"tau^2, so compare the CI, not the point. If the obs/item COLUMN is below that, some "
          f"cells are missing (see the missing count) and the fit is on a partial ladder.")
    print(" - Both families share the clean anchor as their 0-dose cell, so their s_i are correlated.")
    print(" - θ offset uses the same 07-12 anchors as OLD, isolating the window/ladder change.")
    print(" - Higher window-3 accuracies push more MCQ items to ceiling (all-correct) -> dropped.")


if __name__ == "__main__":
    main()
