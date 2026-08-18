#!/usr/bin/env python3
"""Report the per-defect-family dose split for tier-1 candidates, open form.

Answers three questions that decide whether the tile-granularity selection can
work at all:

  1. How much data does each family actually have per item?
  2. Do the families AGREE per item? If omission and mistranslation rank items
     the same way, splitting them buys nothing and the pooled figure was fine.
     If they disagree, pooling was hiding real structure.
  3. **Does any metric actually resolve the contested tiles?** 31 tiles have 2+
     candidates. A metric that leaves most of them tied hands the decision to
     `quality_score`, i.e. the empirical evidence stops deciding. This is the
     question that matters -- a metric that cannot separate candidates is not a
     selection criterion regardless of how principled it looks.

Reads the offline grid directly (evaluation/outputs, usually a symlink to
eten-research-outputs) so it must run on a machine where that resolves.

Usage (from repo root):
  python scripts/report_tier1_family_split.py \
      --eval-root evaluation \
      --candidates evaluation/datasets/tier1_tile_candidates.json
  python scripts/report_tier1_family_split.py --eval-root evaluation --csv out.csv
"""

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

MODELS = ("qwen317b", "qwen2515b", "llama321b")
CLEAN = "omission/0%"
FAMILIES = {
    "omission": "omission/30%",
    "mistranslation": "mistranslation/30%",
    "adversarial": "addition/adversarial_30%",
}
TIER1_ROOT = "tier1"

# Full dose ladders. The single-dose contrast above uses 3 observations per
# item; the ladder uses ~18, which is the only way to tell a real per-item dose
# response from a coin flip -- a genuine responder should decline roughly
# monotonically across doses, noise should not.
LADDERS = {
    "omission": [(0, "omission/0%"), (5, "omission/5%"), (10, "omission/10%"),
                 (15, "omission/15%"), (20, "omission/20%"), (30, "omission/30%")],
    "mistranslation": [(0, "omission/0%"), (5, "mistranslation/5%"),
                       (10, "mistranslation/10%"), (15, "mistranslation/15%"),
                       (20, "mistranslation/20%"), (30, "mistranslation/30%")],
    "adversarial": [(0, "addition/0%"), (5, "addition/adversarial_5%"),
                    (10, "addition/adversarial_10%"), (15, "addition/adversarial_15%"),
                    (20, "addition/adversarial_20%"), (30, "addition/adversarial_30%")],
}


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Rank correlation, ties averaged. None if either series is constant."""
    if len(xs) < 3:
        return None
    rx, ry = _ranks(list(xs)), _ranks(list(ys))
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def logit(p, n=3):
    """Logit with a Haldane-style continuity correction for 0 and 1.

    Accuracy is a mean of n graded scores, so it hits the bounds often; without
    a correction those points drop out and the slope is fitted on whichever
    doses happened to land strictly inside (0,1) -- which biases it toward
    flatness exactly for the strong responders that saturate at both ends.
    """
    adj = 0.5 / max(1, n)
    p = min(1.0 - adj, max(adj, float(p)))
    return math.log(p / (1.0 - p))


def ladder_slope(series, n_per_dose=3):
    """Least-squares slope of logit(accuracy) on dose. Logit per unit dose.

    This is a LOCAL, unpooled slope -- NOT the ``s_i`` from
    ``scripts/fit_item_sensitivity.py``, which is a partially-pooled IRT slope
    with a free item intercept and a per-respondent ability offset theta_r.
    Named separately on purpose: the two are not interchangeable, and the IRT
    fitter is hardcoded to the Luke layout (``eval_root/luke{ch}``) with
    positional item keys, so it does not currently run on tier-1.

    Sign convention matches s_i: NEGATIVE = accuracy falls as dose rises = a
    useful item.
    """
    if len(series) < 3:
        return None
    xs = [d for d, _ in series]
    ys = [logit(a, n_per_dose) for _, a in series]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def slope_permutation_p(series, n_per_dose=3, permutations=2000, seed=2026):
    """One-sided p: how often does shuffling dose labels give a slope this steep?

    Uses the item's own accuracy values, so it conditions on that item's
    difficulty and variability -- the null is "these same numbers, in a random
    dose order". A parametric p would need a variance assumption that 6 coarse
    points cannot support.
    """
    import random

    observed = ladder_slope(series, n_per_dose)
    if observed is None:
        return None, None
    rng = random.Random(f"{seed}:{len(series)}:{observed:.6f}")
    doses = [d for d, _ in series]
    accs = [a for _, a in series]
    if len(set(accs)) < 2:
        return observed, 1.0
    hits = 0
    for _ in range(permutations):
        shuffled = accs[:]
        rng.shuffle(shuffled)
        value = ladder_slope(list(zip(doses, shuffled)), n_per_dose)
        if value is not None and value <= observed:
            hits += 1
    return observed, (hits + 1) / (permutations + 1)


def _records(path: Path):
    """Record list from a QA file that may be a bare list or a keyed object."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for value in data.values():
        if isinstance(value, list):
            return value
    raise SystemExit(f"{path}: no record list found")


def normalize_id(raw: str) -> str:
    """Strip the grid's id decorations down to a bare content_id.

    The grid writes ids like ``uw-t1_judg9:w5fv-open``; the candidates file and
    the window map key on ``t1_judg9:w5fv``. Joining without normalising drops
    every row silently -- the same content_id-scheme divergence that made the
    duplicate filter no-op earlier (``rxf3#2`` vs ``rxf3b``), so normalise here
    rather than assuming the two sides agree.
    """
    out = str(raw or "").strip()
    out = out.removesuffix("-open").removesuffix("-mcq")
    for prefix in ("uw-", "UW-"):
        if out.startswith(prefix):
            out = out[len(prefix):]
    return out


def load_open_scores(eval_root: Path, passage_id: str):
    """item -> condition -> [open scores]. Open form only (llm_score, 0/0.5/1)."""
    observed = defaultdict(lambda: defaultdict(list))
    base = eval_root / "outputs" / TIER1_ROOT / passage_id
    for model in MODELS:
        for condition in (CLEAN, *FAMILIES.values()):
            path = base / model / condition / "scores_target_llama.json"
            if not path.exists():
                continue
            for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                item_id = str(item.get("id") or item.get("passage_id") or "")
                if not item_id.endswith("-open"):
                    continue
                value = item.get("llm_score")
                if value is not None:
                    observed[normalize_id(item_id)][condition].append(float(value))
    return observed


def load_ladder(eval_root: Path, passage_id: str, family: str):
    """item -> [(dose, mean open accuracy over the 3 answerers)] for one family."""
    per_dose = defaultdict(dict)
    base = eval_root / "outputs" / TIER1_ROOT / passage_id
    for dose, condition in LADDERS[family]:
        bucket = defaultdict(list)
        for model in MODELS:
            path = base / model / condition / "scores_target_llama.json"
            if not path.exists():
                continue
            for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                item_id = str(item.get("id") or item.get("passage_id") or "")
                if not item_id.endswith("-open"):
                    continue
                value = item.get("llm_score")
                if value is not None:
                    bucket[normalize_id(item_id)].append(float(value))
        for item_id, values in bucket.items():
            per_dose[item_id][dose] = sum(values) / len(values)
    return {i: sorted(d.items()) for i, d in per_dose.items()}


def load_ladder_observations(eval_root: Path, passage_id: str, family: str):
    """item -> individual (answerer, dose, score) rows for an IRT-style fit."""
    observed = defaultdict(list)
    base = eval_root / "outputs" / TIER1_ROOT / passage_id
    for dose, condition in LADDERS[family]:
        for model in MODELS:
            path = base / model / condition / "scores_target_llama.json"
            if not path.exists():
                continue
            for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                item_id = str(item.get("id") or item.get("passage_id") or "")
                if not item_id.endswith("-open"):
                    continue
                value = item.get("llm_score")
                if value is not None:
                    observed[normalize_id(item_id)].append({
                        "model": model,
                        "dose": float(dose),
                        "y": float(min(1.0, max(0.0, value))),
                    })
    return observed


def fit_tier1_s_i(observations):
    """Fit partially pooled item slopes with answer-model ability offsets.

    ``q`` is standardized translation quality (negative dose), so a useful
    item has positive ``s_i``. Ability offsets are estimated from this balanced
    Tier-1 grid; every answer model sees every available item/dose cell, which
    keeps model ability separate from dose. The free item intercept and weak
    Gaussian pooling match the established item-sensitivity fitter.
    """
    import numpy as np

    from fit_item_sensitivity import fit_penalized_logistic

    rows = [row for item_rows in observations.values() for row in item_rows]
    if not rows:
        return {}, {}
    doses = sorted({row["dose"] for row in rows})
    q_values = np.array([-dose for dose in doses], dtype=float)
    q_mean, q_sd = float(q_values.mean()), float(q_values.std())
    if q_sd < 1e-12:
        return {}, {}

    # Balanced-grid model ability offsets. Centering leaves the global
    # intercept identifiable while preserving relative answerer ability.
    by_model = defaultdict(list)
    for row in rows:
        by_model[row["model"]].append(row["y"])
    raw_theta = {
        model: logit(sum(values) / len(values), len(values))
        for model, values in by_model.items()
    }
    theta_mean = sum(raw_theta.values()) / len(raw_theta)
    theta = {model: value - theta_mean for model, value in raw_theta.items()}

    def arrays(item_rows):
        qz = np.array([(-row["dose"] - q_mean) / q_sd for row in item_rows])
        y = np.array([row["y"] for row in item_rows], dtype=float)
        offset = np.array([theta[row["model"]] for row in item_rows], dtype=float)
        return np.column_stack([np.ones(len(qz)), qz]), offset, y

    X, offset, y = arrays(rows)
    global_coef, _global_se, _ = fit_penalized_logistic(
        X, offset, y, np.zeros(2), np.array([1e-3, 1e-3])
    )
    # Same weak priors as the established pooled per-item fit (sigma_c~3,
    # sigma_s~5). They prevent separation without flattening real item spread.
    prior_prec = np.array([0.11, 0.04])
    fitted = {}
    for item_id, item_rows in observations.items():
        X_i, offset_i, y_i = arrays(item_rows)
        coef, se, converged = fit_penalized_logistic(
            X_i, offset_i, y_i, global_coef, prior_prec
        )
        fitted[item_id] = {
            "s_i": float(coef[1]),
            "se_s_i": float(se[1]),
            "c_i": float(coef[0]),
            "n_obs": len(item_rows),
            "n_levels": len({row["dose"] for row in item_rows}),
            "converged": bool(converged),
        }
    meta = {
        "q_definition": "negative dose, standardized within family",
        "q_mean": q_mean,
        "q_sd": q_sd,
        "global_intercept": float(global_coef[0]),
        "global_slope": float(global_coef[1]),
        "answer_model_ability_offsets": theta,
    }
    return fitted, meta


def ladder_report(eval_root: Path, passages, permutations: int = 2000, seed: int = 2026):
    """Per-item dose-response reality check, with a permutation null.

    A per-item Spearman looks impressive on its own, so it is meaningless
    without a null: with 6 dose points and coarse 0/0.5/1 scores, chance alone
    produces sizeable |rho|. The null shuffles each item's dose labels and
    recomputes, preserving that item's exact accuracy values -- so it answers
    "how negative would these rho's look if dose carried no information at all".
    """
    import random

    rng = random.Random(seed)
    print("\n" + "=" * 62)
    print("DOSE-LADDER REALITY CHECK (open form, mean over 3 answerers)")
    print("=" * 62)

    for family in LADDERS:
        per_item = {}
        for passage in passages:
            for item_id, series in load_ladder(eval_root, passage, family).items():
                if len(series) >= 4:
                    per_item[item_id] = series
        if not per_item:
            print(f"\n{family}: no ladder cells found")
            continue

        rhos, flat = [], 0
        for series in per_item.values():
            doses = [d for d, _ in series]
            accs = [a for _, a in series]
            rho = spearman(doses, accs)
            if rho is None:
                flat += 1
            else:
                rhos.append(rho)

        null = []
        for series in per_item.values():
            accs = [a for _, a in series]
            doses = [d for d, _ in series]
            if len(set(accs)) < 2:
                continue
            for _ in range(max(1, permutations // max(1, len(per_item)))):
                shuffled = accs[:]
                rng.shuffle(shuffled)
                value = spearman(doses, shuffled)
                if value is not None:
                    null.append(value)

        n_dose = len(next(iter(per_item.values())))
        print(f"\n{family}: {len(per_item)} items with >=4 dose points "
              f"({n_dose} doses x 3 answerers = ~{n_dose * 3} obs/item)")
        print(f"  flat across the whole ladder (no variation): {flat}")
        if not rhos:
            continue
        neg = sum(1 for r in rhos if r < 0)
        strong = sum(1 for r in rhos if r <= -0.7)
        print(f"  observed rho: mean {statistics.mean(rhos):+.3f}  "
              f"median {statistics.median(rhos):+.3f}")
        print(f"    negative (accuracy falls with dose): {neg}/{len(rhos)} "
              f"({100 * neg / len(rhos):.0f}%)")
        print(f"    strong (rho <= -0.7):                {strong}/{len(rhos)} "
              f"({100 * strong / len(rhos):.0f}%)")
        if null:
            null_neg = sum(1 for r in null if r < 0)
            null_strong = sum(1 for r in null if r <= -0.7)
            print(f"  permutation null (n={len(null)}): mean {statistics.mean(null):+.3f}"
                  f"   negative {100 * null_neg / len(null):.0f}%"
                  f"   strong {100 * null_strong / len(null):.0f}%")
            lift = (100 * strong / len(rhos)) - (100 * null_strong / len(null))
            print(f"  --> excess strong responders over chance: {lift:+.0f} pts")


def overlap_report(eval_root: Path, passages, cand, strong_cut=-0.7):
    """Are the strong dose responders the SAME items across families?

    This decides how the finding is used. If the sets largely coincide,
    "responds to dose" is a stable property of the item and can be selected on
    directly. If they are near-disjoint, response is family-specific -- there is
    no such thing as a generally sensitive item, and the "responds to both
    families" gate is selecting for something much rarer than it looks.

    Compared against the hypergeometric expectation, because two sets of ~19
    drawn from ~80 items overlap substantially by chance alone (~4-5 items), so
    a raw intersection count on its own says nothing.
    """
    rho = {family: {} for family in LADDERS}
    for family in LADDERS:
        for passage in passages:
            for item_id, series in load_ladder(eval_root, passage, family).items():
                if len(series) < 4:
                    continue
                value = spearman([d for d, _ in series], [a for _, a in series])
                if value is not None:
                    rho[family][item_id] = value

    print("\n" + "=" * 62)
    print(f"STRONG-RESPONDER OVERLAP (rho <= {strong_cut})")
    print("=" * 62)

    strong = {f: {i for i, v in r.items() if v <= strong_cut} for f, r in rho.items()}
    for family in LADDERS:
        print(f"  {family:16} {len(strong[family]):>3} strong "
              f"of {len(rho[family]):>3} scored")

    names = list(LADDERS)
    print("\npairwise overlap vs chance:")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            shared_pool = set(rho[a]) & set(rho[b])
            sa = strong[a] & shared_pool
            sb = strong[b] & shared_pool
            both = sa & sb
            expected = (len(sa) * len(sb) / len(shared_pool)) if shared_pool else 0
            jac = len(both) / len(sa | sb) if (sa | sb) else 0
            print(f"  {a[:12]:12} & {b[:12]:12} both {len(both):>2}   "
                  f"chance {expected:>4.1f}   jaccard {jac:.2f}")

    all_scored = set.intersection(*[set(rho[f]) for f in names]) if names else set()
    triple = set.intersection(*[strong[f] for f in names]) if names else set()
    union = set.union(*[strong[f] for f in names]) if names else set()
    print(f"\n  strong in ALL three: {len(triple)}")
    print(f"  strong in ANY family: {len(union)}   "
          f"(items scored in all three: {len(all_scored)})")
    counts = Counter(sum(1 for f in names if i in strong[f]) for i in all_scored)
    print(f"  families responded to, among the {len(all_scored)} fully-scored items: "
          f"{dict(sorted(counts.items()))}")

    print("\nladder-rho correlation across families (more reliable than the 3-obs contrast):")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            pairs = [(rho[a][k], rho[b][k]) for k in set(rho[a]) & set(rho[b])]
            if len(pairs) >= 3:
                xs, ys = zip(*pairs)
                r = spearman(xs, ys)
                print(f"  {a[:12]:12} & {b[:12]:12} n={len(pairs):>3}  "
                      f"spearman {r:+.3f}" if r is not None else "  (constant)")

    # The practical question for the pilot.
    print("\ntile coverage:")
    tiles = [t for t in cand["tiles"]]
    have = 0
    for tile in tiles:
        ids = {normalize_id(c["content_id"]) for c in tile["candidates"] if c["deliverable"]}
        if ids & union:
            have += 1
    print(f"  tiles with >=1 strong responder available: {have}/{len(tiles)}")
    print(f"  tiles with NO responder (selection is quality-only): {len(tiles) - have}")


def revisit_removals(eval_root: Path, passages, all_formats_path: Path):
    """Re-judge the 12 window-level removals against ladder rho.

    The original verdicts used `dose_drop` at a single 30% dose -- 3 open
    observations per item. Ladder rho uses ~18. If the two disagree, items were
    dropped from the pilot on evidence six times thinner than what is available,
    and the discarded candidate may be the better instrument.

    Reports per contest and in aggregate, per family, plus a comparison of the
    kept and removed pools overall.
    """
    records = _records(all_formats_path)
    by_cid = {r.get("content_id"): r for r in records}

    rho = {family: {} for family in LADDERS}
    for family in LADDERS:
        for passage in passages:
            for item_id, series in load_ladder(eval_root, passage, family).items():
                if len(series) < 4:
                    continue
                value = spearman([d for d, _ in series], [a for _, a in series])
                if value is not None:
                    rho[family][item_id] = value

    def best_rho(cid):
        """Most negative rho across families = strongest response anywhere."""
        values = [rho[f].get(normalize_id(cid)) for f in LADDERS]
        values = [v for v in values if v is not None]
        return min(values) if values else None

    removed = [r for r in records
               if (r.get("pilot_window_selection") or {}).get("removed_from_human_pilot")]

    print("\n" + "=" * 62)
    print("WERE THE 12 REMOVALS RIGHT? (3-obs dose_drop vs ~18-obs ladder rho)")
    print("=" * 62)
    print(f"{'passage':14}{'OUT':>10}{'rho':>8}   {'IN':>10}{'rho':>8}  verdict")
    print("-" * 62)

    reversals = ties = agree = unknown = 0
    for record in sorted(removed, key=lambda r: str(r.get("passage_id"))):
        selection = record["pilot_window_selection"]
        loser = record.get("content_id")
        winner = selection.get("selected_content_id")
        if selection.get("reason") in DUPLICATE_REASONS:
            continue
        lr, wr = best_rho(loser), best_rho(winner)
        if lr is None or wr is None:
            unknown += 1
            verdict = "no ladder data"
        elif lr < wr - 1e-9:
            reversals += 1
            verdict = "** REVERSAL: dropped item responds MORE"
        elif abs(lr - wr) < 1e-9:
            ties += 1
            verdict = "tie"
        else:
            agree += 1
            verdict = "agrees"
        print(f"{str(record.get('passage_id')):14}"
              f"{str(loser).split(':')[-1]:>10}{(f'{lr:+.2f}' if lr is not None else '  n/a'):>8}   "
              f"{str(winner).split(':')[-1]:>10}{(f'{wr:+.2f}' if wr is not None else '  n/a'):>8}"
              f"  {verdict}")

    total = reversals + ties + agree
    print(f"\n  ladder rho AGREES with the original verdict : {agree}/{total}")
    print(f"  ladder rho REVERSES it (dropped item better): {reversals}/{total}")
    print(f"  tie                                         : {ties}/{total}")
    if unknown:
        print(f"  no ladder data                              : {unknown}")

    # Pool-level comparison: are removed items systematically worse responders?
    removed_ids = {normalize_id(r["content_id"]) for r in removed}
    kept_ids = {normalize_id(r["content_id"]) for r in records} - removed_ids
    for label, ids in (("kept (78)", kept_ids), ("removed (12)", removed_ids)):
        values = [best_rho(i) for i in ids]
        values = [v for v in values if v is not None]
        if values:
            strong = sum(1 for v in values if v <= -0.7)
            print(f"\n  {label:14} n={len(values):>3}  median best-rho {statistics.median(values):+.3f}"
                  f"   strong {strong}/{len(values)} ({100*strong/len(values):.0f}%)")


DUPLICATE_REASONS = {"exact_duplicate_later_copy"}


def emit_sensitivity(eval_root: Path, passages, out_path: Path, p_gate=0.10):
    """Write per-item, per-family (p, s_i) for global and collision ranking.

    The selection primitives, and why these two:

      * **p (permutation)** is the GATE -- does this item respond at all? The
        3-observation ``dose_drop`` it replaces was shown to be noise: re-judging
        the 12 window-level removals against the ladder reversed 4 of 10
        (binomial p=0.75 vs a coin flip), and the kept/removed pools were
        indistinguishable (median best-rho -0.665 vs -0.655).
      * **s_i** is the SCORE -- how much information does it carry? Rank
        correlation cannot serve here: it is scale-free, so an item declining
        1.00->0.95 monotonically outranks one declining 1.00->0.20 with a single
        inversion. Fisher information is s^2 * p(1-p); the slope enters squared,
        rho does not appear.
    """
    out = {}
    summary = Counter()
    fit_meta = {}
    for family in LADDERS:
        observations = defaultdict(list)
        for passage in passages:
            for item_id, rows in load_ladder_observations(
                eval_root, passage, family
            ).items():
                observations[item_id].extend(rows)
        fitted, fit_meta[family] = fit_tier1_s_i(observations)
        for passage in passages:
            for item_id, series in load_ladder(eval_root, passage, family).items():
                if len(series) < 4:
                    continue
                slope, pval = slope_permutation_p(series)
                if slope is None:
                    continue
                entry = out.setdefault(item_id, {})
                item_fit = fitted.get(item_id) or {}
                s_i = item_fit.get("s_i")
                entry[family] = {
                    "s_i": round(s_i, 5) if s_i is not None else None,
                    "se_s_i": (round(item_fit["se_s_i"], 5)
                               if item_fit.get("se_s_i") is not None else None),
                    "slope": round(slope, 4),
                    "p": round(pval, 4),
                    "n_doses": len(series),
                    "n_obs": item_fit.get("n_obs"),
                    "converged": item_fit.get("converged"),
                    "passes_gate": bool(
                        pval <= p_gate and s_i is not None and s_i > 0
                    ),
                }
                summary[family] += 1
                if entry[family]["passes_gate"]:
                    summary[f"{family}_passes"] += 1

    print("\n" + "=" * 62)
    print(f"SELECTION PRIMITIVES: s_i (score) + permutation p (gate, p<={p_gate})")
    print("=" * 62)
    for family in LADDERS:
        n = summary[family]
        k = summary[f"{family}_passes"]
        slopes = [v[family]["s_i"] for v in out.values()
                  if family in v and v[family]["s_i"] is not None]
        gated = [v[family]["s_i"] for v in out.values()
                 if family in v and v[family]["passes_gate"]]
        print(f"\n{family}: {n} items fitted, {k} pass the gate ({100*k/n:.0f}%)"
              if n else f"\n{family}: no items")
        if slopes:
            print(f"  s_i (logit per SD quality)  median {statistics.median(slopes):+.3f}"
                  f"   min {min(slopes):+.3f}  max {max(slopes):+.3f}")
        if gated:
            print(f"  among gated items            median {statistics.median(gated):+.3f}"
                  f"   strongest {max(gated):+.3f}")

    any_gate = sum(1 for v in out.values()
                   if any(f.get("passes_gate") for f in v.values()))
    print(f"\nitems passing the gate in >=1 family: {any_gate}/{len(out)}")

    payload = {
        "schema_version": 2,
        "note": "Tier-1 partially pooled IRT-style s_i with a free item intercept "
                "and answer-model ability offset; permutation p is computed from "
                "the item's unpooled mean-accuracy ladder",
        "p_gate": p_gate,
        "families": list(LADDERS),
        "fit": fit_meta,
        "items": out,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"wrote {out_path}")


def list_responders(eval_root: Path, passages, shortened: Path, strong_cut=-0.7,
                    out_path=None):
    """List the strong dose responders with their full accuracy ladder.

    The aggregate says ~19 items per family respond; this shows WHICH, and what
    the response looks like dose by dose. That matters because the same rho can
    come from three very different mechanisms:

      * a genuine gradient (1.00 -> 0.83 -> 0.67 -> 0.50 ...) -- the item gets
        steadily harder as meaning degrades. This is the intended behaviour.
      * a CLIFF (1.00 -> 1.00 -> 0.00 -> 0.00) -- the answer clause survives
        until one dose deletes it, then the item is dead. Monotone, high |rho|,
        but it is measuring "was my verse hit", not sensitivity to quality.
      * a FLOOR SLIDE (0.33 -> 0.17 -> 0.00 ...) -- the item was barely
        answerable to begin with, so the decline is a few cells of noise near
        zero.

    Only the first is a good instrument. The printed ladder makes the three
    distinguishable by eye, which no summary statistic does.
    """
    # Question text is a convenience, not a requirement: the ladders are the
    # output. A wrong/absent path must not lose the analysis, and the default
    # cannot be guessed (qa_generation is not always a sibling of this repo).
    sh = {}
    if shortened and Path(shortened).is_file():
        sh = {r.get("content_id"): r for r in _records(shortened)}
    elif shortened:
        print(f"[warn] --shortened not found, listing without question text: {shortened}")
    rows = []
    for family in LADDERS:
        for passage in passages:
            for item_id, series in load_ladder(eval_root, passage, family).items():
                if len(series) < 4:
                    continue
                rho = spearman([d for d, _ in series], [a for _, a in series])
                if rho is None or rho > strong_cut:
                    continue
                slope, pval = slope_permutation_p(series)
                accs = [a for _, a in series]
                drops = [accs[i] - accs[i + 1] for i in range(len(accs) - 1)]
                # [2026-08-17] The cliff/gradient/floor-slide LABEL was removed.
                # With 6 dose points at 1/6 granularity a cliff and a steep
                # gradient differ by one intermediate point the instrument cannot
                # reliably place, so the label was drawing a mechanistic
                # distinction the data does not support -- and its thresholds
                # produced contradictory calls (a 0.67->0.50 single step read as
                # a "cliff" at ratio 1.0, while a genuine 0.67->0.17 crash read
                # as a "gradient" at 0.746 because floor noise widened its range).
                #
                # Reported instead: the quantities that decide whether an item is
                # USABLE, which are readable without inferring a mechanism.
                granularity = 1.0 / 6.0
                span = max(accs) - min(accs)
                biggest = max(drops) if drops else 0.0
                by_dose = dict(series)
                # First dose at which the item bottoms out. Past this point it
                # carries no information: every higher dose reads the same floor.
                floor_value = min(accs)
                floors_at = next((d for d, a in series if a <= floor_value + 1e-9), None)
                inversions = sum(1 for x in drops if x < -1e-9)
                # The pilot delivers 15% and 30%, so an item's value is decided by
                # what it does AT THOSE DOSES, not by its shape across the whole
                # research ladder.
                acc15, acc30 = by_dose.get(15), by_dose.get(30)
                # "Good" = discriminates at the doses actually used: not at
                # ceiling when clean, measurably lower at 30%, and still off the
                # floor there (an item that bottoms out early is uninformative
                # exactly where the pilot's strongest dose sits).
                usable = (
                    accs[0] >= 0.5
                    and acc30 is not None
                    and acc30 > 0.0
                    and (accs[0] - acc30) >= 2 * granularity
                )
                rows.append({
                    "content_id": item_id, "passage_id": passage, "family": family,
                    "rho": round(rho, 3),
                    "slope": round(slope, 4) if slope is not None else None,
                    "p": round(pval, 4) if pval is not None else None,
                    "clean": round(accs[0], 3),
                    "acc15": None if acc15 is None else round(acc15, 3),
                    "acc30": None if acc30 is None else round(acc30, 3),
                    "span": round(span, 3),
                    "biggest_step": round(biggest, 3),
                    "step_fraction": round(biggest / span, 3) if span > 0 else None,
                    "floors_at_dose": floors_at,
                    "inversions": inversions,
                    "usable_at_pilot_doses": usable,
                    "ladder": [[d, round(a, 3)] for d, a in series],
                    "question": (sh.get(item_id, {}) or {}).get("question")
                                or (sh.get(item_id, {}) or {}).get("original_question"),
                })

    print("\n" + "=" * 78)
    print(f"STRONG DOSE RESPONDERS (rho <= {strong_cut}) -- with the accuracy ladder")
    print("=" * 78)
    header = (f"{'use':>4} {'family':14}{'item':10}"
              f"{'clean':>6}{'@15':>6}{'@30':>6}{'span':>6}{'step':>6}{'frac':>6}"
              f"{'flr':>5}{'inv':>4}{'slope':>8}{'p':>7}{'rho':>7}")
    print(header)
    print("-" * len(header))
    # Usable first, then steepest slope: the ordering a selector would use.
    for row in sorted(rows, key=lambda r: (not r["usable_at_pilot_doses"],
                                           r["slope"] if r["slope"] is not None else 0)):
        fmt = lambda v, w=6, p=2: (f"{v:>{w}.{p}f}" if isinstance(v, float) else f"{'--':>{w}}")
        print(f"{'Y' if row['usable_at_pilot_doses'] else '.':>4} "
              f"{row['family']:14}{row['content_id'].split(':')[-1]:10}"
              f"{fmt(row['clean'])}{fmt(row['acc15'])}{fmt(row['acc30'])}"
              f"{fmt(row['span'])}{fmt(row['biggest_step'])}{fmt(row['step_fraction'])}"
              f"{str(row['floors_at_dose']):>5}{row['inversions']:>4}"
              f"{fmt(row['slope'], 8, 3)}{fmt(row['p'], 7, 3)}{fmt(row['rho'], 7)}")
    print("-" * len(header))

    usable = [r for r in rows if r["usable_at_pilot_doses"]]
    print(f"\nusable at the pilot's doses (clean>=0.5, acc30>0, drop>=0.33): "
          f"{len(usable)}/{len(rows)} (item x family rows)")
    print(f"distinct items with >=1 usable family: "
          f"{len({r['content_id'] for r in usable})}")
    print("\ncolumns: span=total decline, step=largest single drop, frac=step/span,")
    print("         flr=first dose at the item's floor, inv=accuracy rises (noise)")

    if usable:
        print("\nTHE GOOD ONES (usable, steepest first):")
        seen = set()
        for row in sorted(usable, key=lambda r: r["slope"] or 0):
            if row["content_id"] in seen:
                continue
            seen.add(row["content_id"])
            print(f"  {row['content_id']:22} {row['family']:15} "
                  f"{str(row['question'])[:50]}")

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(
            {"schema_version": 1, "strong_cut": strong_cut, "responders": rows},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-root", type=Path, default=Path("evaluation"))
    ap.add_argument("--candidates", type=Path,
                    default=Path("evaluation/datasets/tier1_tile_candidates.json"))
    ap.add_argument("--all-formats", type=Path,
                    default=Path("evaluation/datasets/qa/tier1_QAs_easy/tier1_all_formats.json"))
    ap.add_argument("--csv", type=Path, help="also write a per-item CSV")
    ap.add_argument("--list-responders", action="store_true",
                    help="list the strong dose responders with their per-dose "
                         "accuracy ladder, classified gradient / cliff / floor-slide")
    ap.add_argument("--shortened", type=Path,
                    help="optional: tier1_shortened.json, for question text in "
                         "--list-responders. Omit to list ladders only")
    ap.add_argument("--responders-out", type=Path)
    ap.add_argument("--emit-sensitivity", type=Path,
                    help="write per-item (slope, p) for the collision selector")
    ap.add_argument("--p-gate", type=float, default=0.10)
    ap.add_argument("--revisit", action="store_true",
                    help="re-judge the 12 window-level removals against ladder rho")
    ap.add_argument("--overlap", action="store_true",
                    help="are the strong dose responders the SAME items across "
                         "families? (implies --ladder data)")
    ap.add_argument("--ladder", action="store_true",
                    help="run the full dose-ladder monotonicity check with a "
                         "permutation null (answers whether per-item dose "
                         "response is real at all)")
    args = ap.parse_args()

    cand = json.loads(args.candidates.read_text(encoding="utf-8"))
    passages = sorted({t["passage_id"] for t in cand["tiles"]})

    rows = {}
    for passage in passages:
        for base_id, cells in load_open_scores(args.eval_root, passage).items():
            clean = cells.get(CLEAN) or []
            if not clean:
                continue
            clean_acc = sum(clean) / len(clean)
            row = {"passage": passage, "clean": clean_acc, "clean_n": len(clean)}
            for family, condition in FAMILIES.items():
                values = cells.get(condition) or []
                row[family] = (clean_acc - sum(values) / len(values)) if values else None
                row[f"{family}_n"] = len(values)
            rows[base_id] = row

    print(f"items with open clean data: {len(rows)}")
    print(f"clean_n distribution      : {dict(Counter(r['clean_n'] for r in rows.values()))}")
    for family in FAMILIES:
        have = [r[family] for r in rows.values() if r[family] is not None]
        ns = Counter(r[f"{family}_n"] for r in rows.values())
        print(f"\n{family}: {len(have)} items with data, n per item {dict(ns)}")
        if have:
            print(f"  mean {statistics.mean(have):+.3f}  median {statistics.median(have):+.3f}"
                  f"  min {min(have):+.3f}  max {max(have):+.3f}")
            print(f"  negative (wrong sign): {sum(1 for v in have if v < 0)}"
                  f"   zero: {sum(1 for v in have if v == 0)}"
                  f"   distinct values: {len(set(round(v, 4) for v in have))}")

    # --- do the families agree per item? -------------------------------------
    print("\npairwise agreement (items where both families have data):")
    names = list(FAMILIES)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            pairs = [(r[a], r[b]) for r in rows.values()
                     if r[a] is not None and r[b] is not None]
            if len(pairs) < 3:
                print(f"  {a} vs {b}: too few items ({len(pairs)})")
                continue
            xs, ys = zip(*pairs)
            try:
                corr = statistics.correlation(xs, ys)
                print(f"  {a} vs {b}: n={len(pairs)}  pearson r={corr:+.3f}")
            except Exception:
                print(f"  {a} vs {b}: n={len(pairs)}  (constant series)")
            agree = sum(1 for x, y in pairs if (x > 0) == (y > 0))
            print(f"      same sign: {agree}/{len(pairs)}")

    # --- THE question: does any metric resolve the contested tiles? ----------
    # Join diagnostic. A silent id mismatch here makes every metric look like it
    # has "insufficient data" while the grid is in fact fully populated.
    cand_ids = {normalize_id(c["content_id"])
                for t in cand["tiles"] for c in t["candidates"] if c["deliverable"]}
    matched = cand_ids & set(rows)
    print(f"\nid join: {len(matched)}/{len(cand_ids)} candidate ids found in the grid")
    if len(matched) < len(cand_ids):
        missing = sorted(cand_ids - set(rows))[:6]
        print(f"  unmatched examples: {missing}")
        print(f"  grid id examples  : {sorted(rows)[:3]}")

    contested = [t for t in cand["tiles"] if t["contested"]]
    print(f"\ncontested tiles: {len(contested)}")
    metrics = {
        "pooled (om+mis mean)": lambda r: _mean_of(r, ["omission", "mistranslation"]),
        "omission only": lambda r: r.get("omission"),
        "mistranslation only": lambda r: r.get("mistranslation"),
        "adversarial only": lambda r: r.get("adversarial"),
        "all three mean": lambda r: _mean_of(r, list(FAMILIES)),
    }
    for label, fn in metrics.items():
        resolved = tied = nodata = 0
        for tile in contested:
            ids = [normalize_id(c["content_id"])
                   for c in tile["candidates"] if c["deliverable"]]
            values = [fn(rows[i]) for i in ids if i in rows]
            values = [v for v in values if v is not None]
            if len(values) < 2:
                nodata += 1
            elif values.count(max(values)) == 1:
                resolved += 1
            else:
                tied += 1
        print(f"  {label:22} resolved {resolved:>2}   tied {tied:>2}   "
              f"insufficient data {nodata:>2}")

    if args.csv:
        import csv
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["content_id", "passage", "clean", "clean_n",
                        *[k for f in FAMILIES for k in (f, f"{f}_n")]])
            for cid, r in sorted(rows.items()):
                w.writerow([cid, r["passage"], round(r["clean"], 4), r["clean_n"],
                            *[(round(r[f], 4) if r[f] is not None else "")
                              if k == f else r[f"{f}_n"]
                              for f in FAMILIES for k in (f, f"{f}_n")]])
        print(f"\nwrote {args.csv}")

    if args.ladder:
        ladder_report(args.eval_root, passages)
    if args.overlap:
        overlap_report(args.eval_root, passages, cand)
    if args.revisit:
        revisit_removals(args.eval_root, passages, args.all_formats)
    if args.list_responders:
        list_responders(args.eval_root, passages, args.shortened,
                        out_path=args.responders_out)
    if args.emit_sensitivity:
        emit_sensitivity(args.eval_root, passages, args.emit_sensitivity, args.p_gate)
    return 0


def _mean_of(row, families):
    values = [row.get(f) for f in families if row.get(f) is not None]
    return sum(values) / len(values) if values else None


if __name__ == "__main__":
    sys.exit(main())
