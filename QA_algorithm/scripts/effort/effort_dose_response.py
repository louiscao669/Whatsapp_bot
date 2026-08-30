#!/usr/bin/env python3
"""Thinking-token effort vs defect dose (EXPERIMENT_EFFORT_FLUENCY_GUARDRAIL
_2026-08-20.md §6): does the answer model's generation effort respond to
FLUENCY defects, over the range where accuracy is known flat?

Primary hypothesis H-E4: effort is the fluency guardrail the proxy lacks
(adequacy-only accuracy + failed CometKiwi). Secondary: H-E1/E2/E3/E5.

Six outputs, in the order the design gates them:

  (G2) TRUNCATION: share of items with done_reason == 'length'. With thinking
       ON and num_ctx 8192 the DV can silently censor exactly where the effect
       is largest. >15% => do not analyse; 2-15% => read the Tobit column too.
  (G1) DIFFICULTY VALIDATION: on CLEAN cells only, Spearman(log output_tokens,
       b_hat_i) against anchor-IRT difficulty. If token spend does not track
       independently estimated difficulty, it is not measuring effort and
       nothing below is interpretable. Pass = rho >= +0.3, p < 0.05.
       Luke-only: tier-1 has no b_hat_i.
  (1)  PRIMARY FE MODEL: log(output_tokens) ~ alpha_{item x family}
       + beta_f * dose + gamma * log(prompt_tokens), SEs clustered by passage.
       The item x family fixed effect is where "use the clean run as the
       baseline" belongs -- at temperature 0 the clean cell carries zero
       measurement error, so the within-item contrast is exact. Indexing the FE
       by family also absorbs the addition/0% vs omission/0% baseline mismatch
       logged on 2026-08-17.
  (2)  PER-ITEM SLOPES, in the 2026-08-17 table shape, against the within-item
       dose-label permutation null. NOTE THE SIGN: accuracy runs negative,
       effort is expected POSITIVE, so the thresholds are flipped.
  (3)  DISSOCIATION (H-E3): accuracy-responds x effort-responds 2x2. The
       headline cell is accuracy-flat + effort-rising = compensation. Both
       margins are estimated SEPARATELY -- correctness is a collider on the
       dose->effort path and must never be conditioned on.
  (4)  METHOD-AXIS CANARY (H-E4-eco, --methods): does effort flag
       google_word_by_word, the known fluency-saturated method, at |z| >= 2 on
       MCQ items -- where the existing acc_mcq-acc_open canary is weakest?

Data: evaluation/outputs/luke{ch}/<tier>/<family>/<level>/scores_target_llama.json
      tier defaults to '1.7b_think' -- the SLUG_SUFFIX cell written by
      run_tier1_defect_models.sh with NO_THINK=0. The plain '1.7b' cells were
      answered with thinking OFF (both multimodel runners hardcode
      --ollama-no-think) and contain NO thinking tokens.
      Levels: '0%','5%'..'30%', optionally sub-family-prefixed
      (adversarial_/bad_/neutral_/name_/style_).
      Requires answer_effort in the score rows (added in 104b4c03).

b_hat: QA_algorithm/outputs/anchor_irt_estimates_{mcq,open}.json, as in Step 2.

Outputs (QA_algorithm/outputs/reports/effort/):
  effort_cells.csv        per (passage,family,dose,item,q_type) effort + score
  effort_item_slopes.csv  per-item rho, permutation p, quadratic vertex, z
  effort_summary.txt      G1/G2 verdicts + the four tables

Usage:
  python3 QA_algorithm/scripts/effort/effort_dose_response.py
  python3 QA_algorithm/scripts/effort/effort_dose_response.py \
      --tier 1.7b_think --families grammar mistranslation --q-types both
  python3 QA_algorithm/scripts/effort/effort_dose_response.py --methods
  python3 QA_algorithm/scripts/effort/effort_dose_response.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

QA_ROOT = Path(__file__).resolve().parents[2]
REPO = QA_ROOT.parent
EVAL_OUT = REPO / "evaluation" / "outputs"
ANCHOR = {qt: QA_ROOT / "outputs" / f"anchor_irt_estimates_{qt}.json"
          for qt in ("mcq", "open")}
OUT_DIR = QA_ROOT / "outputs" / "reports" / "effort"

DEFAULT_TIER = "1.7b_think"
FLUENCY_FAMILIES = ("grammar", "awkward")
ADEQUACY_FAMILIES = ("mistranslation", "omission", "addition")
DEFAULT_FAMILIES = ("grammar", "awkward", "mistranslation")
METHODS = ("helsinki", "mbart-50", "nllb-distilled-600M", "nllb-200-1.3B",
           "llm_prompt_low", "llm_prompt_medium", "llm_prompt_high",
           "google_word_by_word")
CANARY_METHOD = "google_word_by_word"
SUB_PREFIXES = ("adversarial", "bad", "neutral", "name", "style")
LEVEL_RE = re.compile(r"^(?:(" + "|".join(SUB_PREFIXES) + r")_)?(\d+(?:\.\d+)?)%$")
SCORE_FILE = "scores_target_llama.json"

# Effort is expected to rise with dose; accuracy to fall. Every threshold below
# is written for the effort sign and flipped where accuracy is scored.
STRONG_RHO = 0.7
G1_MIN_RHO = 0.3
TRUNC_WARN = 0.02
TRUNC_STOP = 0.15


# ---------------------------------------------------------------- statistics

def rankdata(values: np.ndarray) -> np.ndarray:
    """Average ranks, ties shared (matches scipy.stats.rankdata 'average')."""
    values = np.asarray(values, float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), float)
    sorted_values = values[order]
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and sorted_values[j] == sorted_values[i]:
            j += 1
        ranks[order[i:j]] = (i + j + 1) / 2.0
        i = j
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    """Spearman rho. None when either side is constant (rho undefined)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return None
    rx, ry = rankdata(x), rankdata(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    denom = math.sqrt(float(np.dot(rx, rx) * np.dot(ry, ry)))
    return float(np.dot(rx, ry) / denom) if denom > 0 else None


def ols_cluster(X: np.ndarray, y: np.ndarray,
                clusters: list[Any]) -> tuple[np.ndarray, np.ndarray]:
    """OLS with CR1 cluster-robust SEs.

    Items inside a chapter share a verse window and one defect draw, so the
    chapter is the independence unit, not the item.
    """
    X, y = np.asarray(X, float), np.asarray(y, float)
    n, k = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    resid = y - X @ beta
    groups = defaultdict(list)
    for idx, cluster in enumerate(clusters):
        groups[cluster].append(idx)
    meat = np.zeros((k, k))
    for idx in groups.values():
        xg, ug = X[idx], resid[idx]
        s = xg.T @ ug
        meat += np.outer(s, s)
    g = len(groups)
    # CR1 small-sample correction. g <= 1 leaves the SEs undefined; return nan
    # rather than a number that looks like an answer.
    if g <= 1 or n <= k:
        return beta, np.full(k, np.nan)
    scale = (g / (g - 1.0)) * ((n - 1.0) / (n - k))
    cov = scale * (xtx_inv @ meat @ xtx_inv)
    return beta, np.sqrt(np.maximum(np.diag(cov), 0.0))


def within_transform(y: np.ndarray, X: np.ndarray,
                     groups: list[Any]) -> tuple[np.ndarray, np.ndarray, int]:
    """Demean y and X inside each fixed-effect group. Returns absorbed count."""
    y, X = np.asarray(y, float).copy(), np.asarray(X, float).copy()
    index = defaultdict(list)
    for i, g in enumerate(groups):
        index[g].append(i)
    for idx in index.values():
        y[idx] -= y[idx].mean()
        X[idx] -= X[idx].mean(axis=0)
    return y, X, len(index)


def quadratic_vertex(dose: np.ndarray, y: np.ndarray) -> float | None:
    """Vertex of a per-item quadratic in dose (H-E5 inverted-U check).

    Returned only for a genuine interior maximum: c < 0 and the vertex inside
    the observed dose range. Those are the items where a monotone Spearman
    understates the effect.
    """
    dose, y = np.asarray(dose, float), np.asarray(y, float)
    if len(dose) < 4 or len(set(dose.tolist())) < 3:
        return None
    design = np.column_stack([np.ones_like(dose), dose, dose ** 2])
    try:
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    _, b, c = coef
    if c >= -1e-12:
        return None
    vertex = -b / (2 * c)
    return float(vertex) if dose.min() < vertex < dose.max() else None


def permutation_null(items: list[tuple[np.ndarray, np.ndarray]],
                     n_perm: int, rng: np.random.Generator) -> np.ndarray:
    """Within-item dose-label shuffle, preserving each item's outcome values.

    Same null the 2026-08-17 accuracy analysis used (mean rho ~ 0.000, ~48%
    negative, 4-6% strong), so the two results stay comparable. It tests dose
    label exchangeability ONLY -- it says nothing about how much a different
    draw of the same-severity defect moves the outcome. That is the separate
    defect-draw null in design doc §7.2, which has to be generated with
    --seed and does not exist yet.
    """
    null = []
    for dose, y in items:
        for _ in range(n_perm):
            rho = spearman(rng.permutation(dose), y)
            if rho is not None:
                null.append(rho)
    return np.asarray(null, float)


# --------------------------------------------------------------- data access

def parse_level(name: str) -> tuple[str | None, float] | None:
    match = LEVEL_RE.match(name)
    if not match:
        return None
    return match.group(1), float(match.group(2)) / 100.0


def item_correct(item: dict) -> float | None:
    """Binary outcome. MCQ is judge-free; open carries the 4.5-18.2% judge
    label flip rate measured on 2026-08-03."""
    if item.get("q_type") == "mcq":
        value = item.get("direct_correct")
        return None if value is None else float(bool(value))
    value = item.get("llm_score")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_cell(path: Path, passage: str, family: str, dose: float,
              sub: str | None) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[skip] unreadable {path}: {exc}")
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        effort = item.get("answer_effort")
        if not isinstance(effort, dict):
            continue  # pre-104b4c03 cell, or a non-Ollama provider
        out_tokens = effort.get("output_tokens")
        if not out_tokens or out_tokens <= 0:
            continue
        rows.append({
            "passage": passage,
            "family": family if not sub else f"{family}:{sub}",
            "dose": dose,
            "item_index": item.get("item_index"),
            "item_id": item.get("id"),
            "q_type": item.get("q_type"),
            "output_tokens": float(out_tokens),
            "prompt_tokens": float(effort.get("prompt_tokens") or 0.0),
            "thinking_chars": float(effort.get("thinking_chars") or 0.0),
            "answer_chars": float(effort.get("answer_chars") or 0.0),
            "thinking_source": effort.get("thinking_source"),
            "done_reason": effort.get("done_reason"),
            "total_ms": effort.get("total_ms"),
            "correct": item_correct(item),
        })
    return rows


def discover(tier: str, families: tuple[str, ...], chapters: list[int],
             root: Path) -> list[dict]:
    rows: list[dict] = []
    for chapter in chapters:
        passage = f"luke{chapter}"
        for family in families:
            family_dir = root / passage / tier / family
            if not family_dir.is_dir():
                continue
            for level_dir in sorted(family_dir.iterdir()):
                if not level_dir.is_dir():
                    continue
                parsed = parse_level(level_dir.name)
                if parsed is None:
                    continue
                sub, dose = parsed
                score_path = level_dir / SCORE_FILE
                if score_path.exists():
                    rows.extend(read_cell(score_path, passage, family, dose, sub))
    return rows


def discover_methods(tier: str, chapters: list[int], root: Path) -> list[dict]:
    rows: list[dict] = []
    for chapter in chapters:
        passage = f"luke{chapter}"
        for method in METHODS:
            score_path = root / passage / tier / method / SCORE_FILE
            if score_path.exists():
                rows.extend(read_cell(score_path, passage, method, 0.0, None))
    return rows


def load_difficulty(paths: dict[str, Path] | None = None) -> dict[str, float]:
    """b_hat_i keyed 'luke{ch}:item{idx}:{q_type}', as in Step 2.

    estimate_anchor_irt.py takes an explicit --output-json and has NO default
    path, so ANCHOR below is a convention guess, not a guarantee. Missing files
    are reported by name rather than skipped silently -- a silent fallback here
    would turn "G1 was never run" into "G1 was skipped", which reads like a
    decision instead of an accident.
    """
    out: dict[str, float] = {}
    for q_type, path in (paths or ANCHOR).items():
        if not path.exists():
            print(f"[warn] no anchor-IRT estimates for q_type={q_type} at "
                  f"{path} -- G1 will run on the remaining q_types only. "
                  f"Generate with estimate_anchor_irt.py --output-json, or "
                  f"point --anchor-estimates at the real file.")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        # Real shape (verified against the committed estimates):
        #   {"model_abilities": {...},
        #    "item_difficulties": {"luke1:item10:mcq": {"b_posterior": -1.09,
        #                                               "b_prior_mean": -1.0,
        #                                               "label": "easy", ...}},
        #    "convergence": {...}}
        # The 'items'/'questions' list forms are accepted too so a future
        # estimator rewrite does not silently produce an empty join.
        entries = (payload.get("item_difficulties") or payload.get("items")
                   or payload.get("questions") or [])
        if isinstance(entries, dict):
            entries = [dict(v, question_id=k) if isinstance(v, dict)
                       else {"question_id": k, "b_posterior": v}
                       for k, v in entries.items()]
        before = len(out)
        for entry in entries:
            key = entry.get("question_id") or entry.get("id")
            b = next((entry[f] for f in ("b_posterior", "b", "difficulty")
                      if entry.get(f) is not None), None)
            if key and b is not None:
                out[str(key)] = float(b)
        if len(out) == before:
            print(f"[warn] {path} parsed but yielded no b_hat for "
                  f"q_type={q_type} -- unrecognised schema, G1 will be empty.")
    return out


# ------------------------------------------------------------------ analyses

def gate_truncation(rows: list[dict]) -> tuple[float, dict[str, int]]:
    reasons = defaultdict(int)
    for row in rows:
        reasons[str(row.get("done_reason"))] += 1
    total = max(len(rows), 1)
    return reasons.get("length", 0) / total, dict(reasons)


def gate_difficulty(rows: list[dict],
                    difficulty: dict[str, float]) -> dict[str, Any]:
    """G1 on CLEAN cells only: does token spend track anchor-IRT difficulty?"""
    tokens, b_values = [], []
    for row in rows:
        if row["dose"] != 0.0 or row["item_index"] is None:
            continue
        key = f"{row['passage']}:item{row['item_index']}:{row['q_type']}"
        b = difficulty.get(key)
        if b is None:
            continue
        tokens.append(math.log(row["output_tokens"]))
        b_values.append(b)
    if len(tokens) < 10:
        return {"n": len(tokens), "rho": None,
                "verdict": "SKIPPED (no b_hat join -- tier-1 has none, and "
                           "anchor inputs are Luke-only)"}
    rho = spearman(np.asarray(b_values), np.asarray(tokens))
    n = len(tokens)
    # Fisher z, adequate at these n and free of a scipy dependency.
    if rho is None or abs(rho) >= 1.0:
        p = float("nan")
    else:
        z = math.atanh(rho) * math.sqrt(n - 3)
        p = math.erfc(abs(z) / math.sqrt(2))
    passed = rho is not None and rho >= G1_MIN_RHO and p < 0.05
    return {"n": n, "rho": rho, "p": p,
            "verdict": "PASS" if passed else "FAIL -- STOP, tokens do not "
                                             "track difficulty"}


def fit_primary(rows: list[dict], family: str) -> dict[str, Any] | None:
    """log(output_tokens) ~ item x family FE + dose + log(prompt_tokens)."""
    subset = [r for r in rows if r["family"].split(":")[0] == family]
    if len(subset) < 8:
        return None
    y = np.array([math.log(r["output_tokens"]) for r in subset])
    dose = np.array([r["dose"] for r in subset])
    # prompt_tokens is a CONTROL, not a signal: with fixed verse windows it
    # should be near constant inside a cell. Its within-cell CV is reported so
    # a context change cannot masquerade as an effort effect.
    prompt = np.array([math.log(r["prompt_tokens"]) if r["prompt_tokens"] > 0
                       else 0.0 for r in subset])
    groups = [(r["passage"], r["item_index"], r["q_type"], r["family"])
              for r in subset]
    X = np.column_stack([dose, prompt])
    y_w, X_w, n_groups = within_transform(y, X, groups)
    beta, se = ols_cluster(X_w, y_w, [r["passage"] for r in subset])
    return {"family": family, "n": len(subset), "n_items": n_groups,
            "beta_dose": float(beta[0]), "se_dose": float(se[0]),
            "beta_prompt": float(beta[1]),
            "pct_per_10pts": float(math.expm1(beta[0] * 0.10) * 100)}


def item_slopes(rows: list[dict], outcome: str,
                n_perm: int, rng: np.random.Generator) -> dict[str, Any]:
    """Per-item Spearman + permutation null, in the 2026-08-17 table shape."""
    by_item: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        by_item[(row["passage"], row["item_index"], row["q_type"],
                 row["family"])].append(row)
    observed, records, null_input = [], [], []
    for key, group in by_item.items():
        values = [r[outcome] for r in group]
        if any(v is None for v in values):
            continue
        dose = np.array([r["dose"] for r in group], float)
        y = np.array(values, float)
        if outcome == "output_tokens":
            y = np.log(y)
        if len(dose) < 4 or len(set(dose.tolist())) < 3:
            continue
        rho = spearman(dose, y)
        if rho is None:
            continue
        observed.append(rho)
        null_input.append((dose, y))
        records.append({"passage": key[0], "item_index": key[1],
                        "q_type": key[2], "family": key[3], "n_doses": len(dose),
                        "rho": rho, "vertex": quadratic_vertex(dose, y)})
    if not observed:
        return {"n": 0, "records": [], "null_strong": None}
    null = permutation_null(null_input, n_perm, rng)
    obs = np.asarray(observed)
    # Effort runs POSITIVE, accuracy NEGATIVE. Score each in its own direction
    # rather than copying the accuracy thresholds across.
    if outcome == "output_tokens":
        strong = float(np.mean(obs >= STRONG_RHO))
        null_strong = float(np.mean(null >= STRONG_RHO)) if len(null) else None
        signed = float(np.mean(obs > 0))
    else:
        strong = float(np.mean(obs <= -STRONG_RHO))
        null_strong = float(np.mean(null <= -STRONG_RHO)) if len(null) else None
        signed = float(np.mean(obs < 0))
    for record in records:
        rho = record["rho"]
        record["perm_p"] = (float(np.mean(null >= rho)) if outcome == "output_tokens"
                            else float(np.mean(null <= rho))) if len(null) else None
    return {"n": len(obs), "median_rho": float(np.median(obs)),
            "signed_share": signed, "strong": strong, "null_strong": null_strong,
            "excess": (strong - null_strong) if null_strong is not None else None,
            "vertex_share": float(np.mean([r["vertex"] is not None
                                           for r in records])),
            "records": records}


def dissociation(effort: dict, accuracy: dict, alpha: float) -> dict[str, int]:
    """H-E3 2x2. Both margins come from SEPARATELY estimated marginal effects --
    correctness is a collider on dose->effort and is never conditioned on."""
    def responded(records):
        return {(r["passage"], r["item_index"], r["q_type"], r["family"])
                for r in records
                if r.get("perm_p") is not None and r["perm_p"] < alpha}
    eff_keys = {(r["passage"], r["item_index"], r["q_type"], r["family"])
                for r in effort.get("records", [])}
    acc_keys = {(r["passage"], r["item_index"], r["q_type"], r["family"])
                for r in accuracy.get("records", [])}
    shared = eff_keys & acc_keys
    eff_hit, acc_hit = responded(effort.get("records", [])), \
        responded(accuracy.get("records", []))
    table = {"both": 0, "compensation": 0, "give_up": 0, "inert": 0,
             "n_shared": len(shared)}
    for key in shared:
        e, a = key in eff_hit, key in acc_hit
        table["both" if (e and a) else "compensation" if e else
              "give_up" if a else "inert"] += 1
    flat = table["compensation"] + table["inert"]
    table["compensation_share_of_flat"] = (table["compensation"] / flat
                                           if flat else None)
    return table


def method_canary(rows: list[dict], q_type: str) -> list[dict]:
    """H-E4-eco: does effort flag google_word_by_word as an outlier?

    Per method, mean within-item-standardised log effort, then a z against the
    across-method spread. MCQ is the decisive form -- it is where the existing
    acc_mcq-acc_open canary is weakest and where the budget analysis wants to
    live."""
    subset = [r for r in rows if r["q_type"] == q_type]
    by_item: dict[tuple, list[dict]] = defaultdict(list)
    for row in subset:
        by_item[(row["passage"], row["item_index"])].append(row)
    per_method: dict[str, list[float]] = defaultdict(list)
    for group in by_item.values():
        if len(group) < 3:
            continue
        values = np.array([math.log(r["output_tokens"]) for r in group])
        sd = values.std(ddof=1)
        if sd <= 0:
            continue
        centred = (values - values.mean()) / sd
        for row, value in zip(group, centred):
            per_method[row["family"]].append(float(value))
    means = {m: float(np.mean(v)) for m, v in per_method.items() if v}
    if len(means) < 3:
        return []
    values = np.array(list(means.values()))
    mu, sd = values.mean(), values.std(ddof=1)
    return sorted(
        ({"method": m, "mean_std_effort": v, "n": len(per_method[m]),
          "z": float((v - mu) / sd) if sd > 0 else float("nan")}
         for m, v in means.items()),
        key=lambda d: -d["mean_std_effort"])


# ------------------------------------------------------------------- reporting

def write_cells(rows: list[dict], path: Path) -> None:
    fields = ["passage", "family", "dose", "item_index", "item_id", "q_type",
              "output_tokens", "prompt_tokens", "thinking_chars", "answer_chars",
              "thinking_source", "done_reason", "total_ms", "correct"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def write_slopes(effort: dict, accuracy: dict, path: Path) -> None:
    acc_index = {(r["passage"], r["item_index"], r["q_type"], r["family"]): r
                 for r in accuracy.get("records", [])}
    fields = ["passage", "family", "item_index", "q_type", "n_doses",
              "rho_effort", "perm_p_effort", "vertex_effort",
              "rho_accuracy", "perm_p_accuracy"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in effort.get("records", []):
            key = (record["passage"], record["item_index"], record["q_type"],
                   record["family"])
            match = acc_index.get(key, {})
            writer.writerow({
                "passage": record["passage"], "family": record["family"],
                "item_index": record["item_index"], "q_type": record["q_type"],
                "n_doses": record["n_doses"], "rho_effort": record["rho"],
                "perm_p_effort": record.get("perm_p"),
                "vertex_effort": record.get("vertex"),
                "rho_accuracy": match.get("rho"),
                "perm_p_accuracy": match.get("perm_p")})


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return "nan" if math.isnan(value) else f"{value:.{digits}f}"
    return str(value)


def build_summary(args, rows, trunc_rate, reasons, g1, primaries,
                  effort, accuracy, table, canary) -> str:
    lines = ["THINKING-TOKEN EFFORT vs DEFECT DOSE",
             f"tier={args.tier}  families={','.join(args.families)}  "
             f"q_types={args.q_types}  rows={len(rows)}", ""]

    lines += ["(G2) TRUNCATION",
              f"  done_reason=='length': {trunc_rate:.1%}",
              f"  distribution: {reasons}"]
    if trunc_rate > TRUNC_STOP:
        lines.append("  VERDICT: STOP -- DV is censored; raise OLLAMA_NUM_PREDICT "
                     "/ OLLAMA_NUM_CTX and re-run.")
    elif trunc_rate > TRUNC_WARN:
        lines.append("  VERDICT: PROCEED WITH CENSORING -- fit Tobit alongside OLS.")
    else:
        lines.append("  VERDICT: PASS")
    lines.append("")

    lines += ["(G1) DOES TOKEN SPEND TRACK ANCHOR-IRT DIFFICULTY? (clean cells)",
              f"  n={g1['n']}  rho={fmt(g1.get('rho'))}  p={fmt(g1.get('p'), 4)}",
              f"  VERDICT: {g1['verdict']}",
              "  A pass also makes token spend a judge-free, gold-key-free,",
              "  language-blind difficulty estimator (cf. 2026-08-17b prescreen).",
              ""]

    lines += ["(1) PRIMARY FE MODEL  log(tokens) ~ item x family FE + dose "
              "+ log(prompt_tokens)",
              "    SEs clustered by passage.",
              f"  {'family':<18}{'n':>6}{'items':>7}{'beta':>9}{'SE':>8}"
              f"{'t':>7}{'%/10pts':>10}"]
    for fit in primaries:
        t = (fit["beta_dose"] / fit["se_dose"]
             if fit["se_dose"] and not math.isnan(fit["se_dose"]) else float("nan"))
        lines.append(f"  {fit['family']:<18}{fit['n']:>6}{fit['n_items']:>7}"
                     f"{fit['beta_dose']:>9.3f}{fit['se_dose']:>8.3f}"
                     f"{t:>7.2f}{fit['pct_per_10pts']:>9.1f}%")
    lines.append("")

    lines += ["(2) PER-ITEM SLOPES vs PERMUTATION NULL  (2026-08-17 table shape)",
              "    SIGN FLIPPED vs the accuracy table: effort is expected "
              "POSITIVE.",
              f"  {'outcome':<12}{'n':>6}{'median rho':>12}{'signed':>9}"
              f"{'strong':>9}{'null':>8}{'excess':>9}{'vertex':>9}"]
    for label, res in (("effort", effort), ("accuracy", accuracy)):
        if not res.get("n"):
            lines.append(f"  {label:<12}{'0':>6}  (no items with >=3 doses)")
            continue
        excess = res.get("excess")
        lines.append(
            f"  {label:<12}{res['n']:>6}{res['median_rho']:>12.3f}"
            f"{res['signed_share']:>8.0%}{res['strong']:>9.0%}"
            f"{(res['null_strong'] or 0):>8.0%}"
            f"{(f'{excess:+.0%}' if excess is not None else 'n/a'):>9}"
            f"{res['vertex_share']:>9.0%}")
    lines += ["  vertex = share of items with an interior quadratic maximum "
              "(H-E5);",
              "  a high share means the monotone rho UNDERSTATES the effect.", ""]

    lines += ["(3) DISSOCIATION (H-E3)  -- separately estimated margins",
              f"  shared items: {table['n_shared']}",
              f"  accuracy DOWN + effort UP   (detected)      : {table['both']}",
              f"  accuracy FLAT + effort UP   (COMPENSATION)  : "
              f"{table['compensation']}",
              f"  accuracy DOWN + effort FLAT (give-up)       : {table['give_up']}",
              f"  accuracy FLAT + effort FLAT (inert)         : {table['inert']}",
              f"  compensation share of accuracy-flat items   : "
              f"{fmt(table['compensation_share_of_flat'])}", ""]

    if canary:
        lines += ["(4) METHOD-AXIS CANARY (H-E4-eco)",
                  f"  {'method':<26}{'mean std effort':>17}{'z':>8}{'n':>7}"]
        for entry in canary:
            flag = "  <-- CANARY" if entry["method"] == CANARY_METHOD else ""
            lines.append(f"  {entry['method']:<26}{entry['mean_std_effort']:>17.3f}"
                         f"{entry['z']:>8.2f}{entry['n']:>7}{flag}")
        wbw = next((e for e in canary if e["method"] == CANARY_METHOD), None)
        if wbw:
            lines.append(f"  VERDICT: {'PASS' if abs(wbw['z']) >= 2 else 'FAIL'} "
                         f"(|z|={abs(wbw['z']):.2f}, threshold 2.0)")
        lines.append("")

    lines += ["CAVEATS CARRIED FROM THE DESIGN",
              "  - One answer model (qwen3:1.7b). llama3.2:1b and qwen2.5:1.5b do",
              "    not reason, so ability generalisation is UNTESTED (P1 open).",
              "  - Temperature 0: re-running a cell reproduces it exactly. These",
              "    SEs come from items and chapters, NOT replicates. The",
              "    defect-draw null (design §7.2, --seed) is not built yet.",
              "  - Open-item labels carry the 4.5-18.2% judge flip rate; MCQ is",
              "    judge-free, which is why H-E4b is the decisive test.",
              "  - Fluency slopes are small, not zero (V2: grammar +0.97 dose",
              "    ordering on mcq-only). Read effect sizes, not pass/fail."]
    return "\n".join(lines)


# ------------------------------------------------------------------ self-test

def self_test() -> int:
    """Synthetic cells with a known effort slope and a deliberately flat
    accuracy: the H-E4 shape. Confirms the estimators recover it and that the
    permutation null stays centred."""
    rng = np.random.default_rng(20260820)
    rows: list[dict] = []
    true_beta = 1.5  # log tokens per unit dose
    for chapter in range(1, 6):
        for item in range(12):
            base = rng.normal(5.0, 0.35)
            for dose in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30):
                tokens = math.exp(base + true_beta * dose + rng.normal(0, 0.05))
                rows.append({
                    "passage": f"luke{chapter}", "family": "grammar",
                    "dose": dose, "item_index": item, "item_id": f"i{item}",
                    "q_type": "mcq", "output_tokens": tokens,
                    "prompt_tokens": 900.0, "thinking_chars": 400.0,
                    "answer_chars": 12.0, "thinking_source": "api",
                    "done_reason": "stop", "total_ms": 1000.0,
                    "correct": float(rng.random() < 0.8)})  # flat by construction

    failures = []
    fit = fit_primary(rows, "grammar")
    if fit is None or abs(fit["beta_dose"] - true_beta) > 0.15:
        failures.append(f"FE slope {fmt(fit and fit['beta_dose'])} != {true_beta}")
    else:
        print(f"  [ok] FE dose slope {fit['beta_dose']:.3f} "
              f"(true {true_beta}), SE {fit['se_dose']:.3f}, "
              f"{fit['pct_per_10pts']:.1f}% per 10 dose points")

    effort = item_slopes(rows, "output_tokens", 40, rng)
    if effort["n"] != 60 or effort["median_rho"] < 0.9:
        failures.append(f"effort rho median {fmt(effort.get('median_rho'))}")
    else:
        print(f"  [ok] effort: n={effort['n']} median rho="
              f"{effort['median_rho']:.3f} strong={effort['strong']:.0%} "
              f"null={effort['null_strong']:.0%}")
    if effort["null_strong"] is not None and effort["null_strong"] > 0.15:
        failures.append(f"permutation null too hot: {effort['null_strong']:.2f}")

    accuracy = item_slopes(rows, "correct", 40, rng)
    if accuracy["n"] and abs(accuracy["median_rho"]) > 0.5:
        failures.append(f"flat accuracy leaked signal: {accuracy['median_rho']:.3f}")
    else:
        print(f"  [ok] accuracy flat as constructed: median rho="
              f"{fmt(accuracy.get('median_rho'))}")

    table = dissociation(effort, accuracy, 0.05)
    if table["compensation"] + table["both"] < 30:
        failures.append(f"dissociation found too few responders: {table}")
    else:
        print(f"  [ok] dissociation: compensation={table['compensation']} "
              f"both={table['both']} give_up={table['give_up']} "
              f"inert={table['inert']}")

    # rank helpers against a known answer
    # rho = 1 - 6*sum(d^2)/(n(n^2-1)) = 1 - 6*4/(5*24) = 0.8
    if abs((spearman(np.array([1, 2, 3, 4, 5]),
                     np.array([2, 1, 4, 3, 5])) or 0) - 0.8) > 1e-9:
        failures.append("spearman wrong on a known case")
    else:
        print("  [ok] spearman matches the known value 0.800")
    # ties must share an average rank
    if abs((spearman(np.array([1, 2, 3, 4]),
                     np.array([1, 2, 2, 3])) or 0) - 0.9486832980505138) > 1e-9:
        failures.append("spearman mishandles ties")
    else:
        print("  [ok] spearman handles tied ranks")

    # canary: one method inflated, must surface as the top |z|
    method_rows = []
    for chapter in range(1, 6):
        for item in range(12):
            base = rng.normal(5.0, 0.3)
            for method in METHODS:
                bump = 0.6 if method == CANARY_METHOD else 0.0
                method_rows.append({
                    "passage": f"luke{chapter}", "family": method, "dose": 0.0,
                    "item_index": item, "q_type": "mcq",
                    "output_tokens": math.exp(base + bump + rng.normal(0, 0.1)),
                    "prompt_tokens": 900.0, "done_reason": "stop",
                    "correct": 1.0})
    canary = method_canary(method_rows, "mcq")
    wbw = next((e for e in canary if e["method"] == CANARY_METHOD), None)
    if not wbw or wbw["z"] < 2.0:
        failures.append(f"canary missed wbw: {wbw}")
    else:
        print(f"  [ok] canary flags {CANARY_METHOD} at z={wbw['z']:.2f}")

    if failures:
        print("\nSELF-TEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nSELF-TEST PASSED")
    return 0


# ----------------------------------------------------------------------- main

def parse_chapters(spec: str) -> list[int]:
    chapters: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            chapters.extend(range(int(lo), int(hi) + 1))
        elif part:
            chapters.append(int(part))
    return chapters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", default=DEFAULT_TIER,
                        help="Answer-model output dir. Default '1.7b_think' "
                             "(NO_THINK=0 + SLUG_SUFFIX). Plain '1.7b' cells "
                             "were run with thinking OFF and have no reasoning.")
    parser.add_argument("--families", nargs="+", default=list(DEFAULT_FAMILIES))
    parser.add_argument("--chapters", default="1-8")
    parser.add_argument("--q-types", choices=("both", "mcq", "open"),
                        default="both")
    parser.add_argument("--methods", action="store_true",
                        help="Also run the Arm B method-axis canary.")
    parser.add_argument("--n-perm", type=int, default=200)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--root", type=Path, default=EVAL_OUT)
    parser.add_argument("--anchor-estimates", nargs=2, metavar=("MCQ", "OPEN"),
                        type=Path,
                        help="Explicit paths to the anchor-IRT estimate JSONs "
                             "for G1. estimate_anchor_irt.py has no default "
                             "output path, so the built-in guess "
                             "(QA_algorithm/outputs/anchor_irt_estimates_*.json) "
                             "may not match your run.")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    chapters = parse_chapters(args.chapters)
    rows = discover(args.tier, tuple(args.families), chapters, args.root)
    if args.q_types != "both":
        rows = [r for r in rows if r["q_type"] == args.q_types]
    if not rows:
        print(f"[fatal] no cells with answer_effort under {args.root} "
              f"tier={args.tier}.\n"
              f"        The thinking arm may not have been run yet: both "
              f"multimodel runners hardcode --ollama-no-think.\n"
              f"        Check with:  find -L {args.root} -type d -name "
              f"'*_think'   (-L is REQUIRED, outputs is a symlink)")
        return 2

    rng = np.random.default_rng(args.seed)
    trunc_rate, reasons = gate_truncation(rows)
    anchor_paths = ({"mcq": args.anchor_estimates[0],
                     "open": args.anchor_estimates[1]}
                    if args.anchor_estimates else None)
    g1 = gate_difficulty(rows, load_difficulty(anchor_paths))
    primaries = [f for f in (fit_primary(rows, fam) for fam in args.families)
                 if f]
    effort = item_slopes(rows, "output_tokens", args.n_perm, rng)
    accuracy = item_slopes(rows, "correct", args.n_perm, rng)
    table = dissociation(effort, accuracy, args.alpha)

    canary = []
    if args.methods:
        method_rows = discover_methods(args.tier, chapters, args.root)
        if method_rows:
            canary = method_canary(method_rows, "mcq")
        else:
            print("[warn] --methods requested but no method cells found")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_cells(rows, args.out_dir / "effort_cells.csv")
    write_slopes(effort, accuracy, args.out_dir / "effort_item_slopes.csv")
    summary = build_summary(args, rows, trunc_rate, reasons, g1, primaries,
                            effort, accuracy, table, canary)
    (args.out_dir / "effort_summary.txt").write_text(summary + "\n",
                                                     encoding="utf-8")
    print(summary)
    print(f"\nwrote -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
