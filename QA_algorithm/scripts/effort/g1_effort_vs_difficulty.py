#!/usr/bin/env python3
"""GATE G1 (EXPERIMENT_EFFORT_FLUENCY_GUARDRAIL_2026-08-20.md §4): does the
answer model's token spend track INDEPENDENTLY estimated item difficulty?

On CLEAN cells only -- no defects, no doses. If the model does not spend more
tokens on items it is independently more likely to fail, token spend is not
measuring effort and every dose analysis downstream is uninterpretable. This
is the cheapest gate in the program and it runs before anything else.

  PASS = Spearman(log output_tokens, b_hat_i) >= +0.30 with p < 0.05
  FAIL = stop; the effort program does not have a measurement to stand on
  UNDERPOWERED = n too small to resolve rho=0.30; run more clean cells

Standalone value of a PASS: token spend becomes a judge-free, gold-key-free,
language-blind item-difficulty estimator -- the cheap prescreen left open on
2026-08-17b, reached from a direction that does not depend on the gpt-5
structural rubric generalising.

THREE THINGS THIS SCRIPT CHECKS THAT A BARE CORRELATION WOULD MISS:

  (a) TRUNCATION (Gate G2). done_reason == 'length' censors the DV exactly
      where spend is highest. Reported first because it invalidates the rest.
  (b) PROMPT-LENGTH CONFOUND. Longer windows cost more tokens for mechanical
      reasons. A rank-partial correlation controlling log(prompt_tokens) is
      reported alongside the raw one; if they diverge, believe the partial.
  (c) SHARED-SOURCE DEPENDENCE. b_hat_i is estimated from anchor responses
      that INCLUDE the 1.7b's own correctness. Correlating the 1.7b's token
      spend against a difficulty estimate partly built from the 1.7b's own
      outcomes is a weaker claim than "tokens track difficulty" -- it drifts
      toward "tokens track what this model got wrong". The script detects this
      from model_abilities and prints the leave-one-out recipe. G1 is only
      fully clean against a b_hat estimated WITHOUT the answer model.

Data: evaluation/outputs/luke{ch}/<tier>/<cell>/scores_target_llama.json
      default tier '1.7b_think', default cell 'llm_prompt_high' -- the
      reference translation the anchor IRT was calibrated on.
      Requires answer_effort in the rows (committed 2026-08-18, 104b4c03).
b_hat: QA_algorithm/outputs/anchor_irt_estimates_{mcq,open}.json
       schema {"item_difficulties": {"luke8:item3:open": {"b_posterior": ...}}}

Outputs (QA_algorithm/outputs/reports/effort/):
  g1_items.csv     per item: b_hat, tokens, prompt tokens, thinking chars
  g1_summary.txt   the verdict plus (a)-(c)

Usage:
  python3 QA_algorithm/scripts/effort/g1_effort_vs_difficulty.py
  python3 QA_algorithm/scripts/effort/g1_effort_vs_difficulty.py \
      --anchor-estimates QA_algorithm/outputs/anchor_irt_estimates_loo_mcq.json \
                         QA_algorithm/outputs/anchor_irt_estimates_loo_open.json
  python3 QA_algorithm/scripts/effort/g1_effort_vs_difficulty.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

QA_ROOT = Path(__file__).resolve().parents[2]
REPO = QA_ROOT.parent
EVAL_OUT = REPO / "evaluation" / "outputs"
OUT_DIR = QA_ROOT / "outputs" / "reports" / "effort"
ANCHOR_DEFAULT = {qt: QA_ROOT / "outputs" / f"anchor_irt_estimates_{qt}.json"
                  for qt in ("mcq", "open")}

DEFAULT_CELL_TEMPLATE = "{passage}/1.7b_think/llm_prompt_high"
DEFAULT_PASSAGES = [f"luke{c}" for c in range(1, 9)]
ANSWER_MODEL_KEY = "1.7b"          # the tier whose tokens we are correlating
SCORE_FILE = "scores_target_llama.json"

# Gate G0. Thinking OFF collapses the DV: an MCQ answer is the single token
# "B". Measured on the tier1_bsb gold72 clean cell (2026-08-20): median
# output_tokens 2 (mcq) / 8 (open), thinking_chars 0 everywhere. A correlation
# against that is arithmetic on noise, so G0 stops before G1 is reported.
G0_MIN_DISTINCT = 10
G0_MIN_MEDIAN_TOKENS = 20

G1_MIN_RHO = 0.30
G1_ALPHA = 0.05
TRUNC_WARN = 0.02
TRUNC_STOP = 0.15


# ---------------------------------------------------------------- statistics

def rankdata(values: list[float]) -> list[float]:
    """Average ranks, ties shared."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        shared = (i + j + 1) / 2.0
        for k in order[i:j]:
            ranks[k] = shared
        i = j
    return ranks


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    dx = [a - mx for a in x]
    dy = [b - my for b in y]
    den = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    return (sum(a * b for a, b in zip(dx, dy)) / den) if den > 0 else None


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return pearson(rankdata(x), rankdata(y))


def partial_spearman(x: list[float], y: list[float],
                     z: list[float]) -> float | None:
    """Rank-partial correlation of x,y controlling z (the prompt-length knob).

    Residualise the ranks of x and y on the ranks of z, then correlate. This is
    the (b) check: a raw rho that survives here is not a window-length artifact.
    """
    if len(set(z)) < 2:
        return spearman(x, y)   # z constant: nothing to control for
    rx, ry, rz = rankdata(x), rankdata(y), rankdata(z)

    def residualise(r: list[float]) -> list[float] | None:
        beta = pearson(rz, r)
        if beta is None:
            return None
        n = len(rz)
        mz, mr = sum(rz) / n, sum(r) / n
        szz = sum((a - mz) ** 2 for a in rz)
        if szz <= 0:
            return None
        slope = sum((a - mz) * (b - mr) for a, b in zip(rz, r)) / szz
        return [b - (mr + slope * (a - mz)) for a, b in zip(rz, r)]

    ex, ey = residualise(rx), residualise(ry)
    if ex is None or ey is None:
        return None
    return pearson(ex, ey)


def fisher_p(rho: float | None, n: int) -> float:
    """Two-sided p for a correlation via Fisher z. Adequate at these n and
    keeps the script dependency-free."""
    if rho is None or n < 4 or abs(rho) >= 1.0:
        return float("nan")
    z = math.atanh(rho) * math.sqrt(n - 3)
    return math.erfc(abs(z) / math.sqrt(2))


def min_detectable_rho(n: int, alpha: float = G1_ALPHA) -> float | None:
    """Smallest |rho| significant at alpha with this n (two-sided, z=1.96)."""
    return math.tanh(1.959963985 / math.sqrt(n - 3)) if n > 3 else None


def n_for_rho(rho: float, alpha: float = G1_ALPHA) -> int:
    """n at which an OBSERVED rho would clear alpha.

    NOT a power calculation -- at this n you have roughly a coin's chance of
    observing rho if rho is the true value. Use n_for_power() for planning.
    """
    return int(math.ceil((1.959963985 / math.atanh(rho)) ** 2 + 3))


def n_for_power(rho: float, power: float = 0.80) -> int:
    """n needed to detect a TRUE rho at `power`. This is the planning number.

    Conflating this with n_for_rho is the classic way to under-size a study by
    ~2x: rho=0.30 is 'significant if observed' at n=44, but you need n~85 to
    have an 80% chance of observing it.
    """
    z_beta = {0.80: 0.8416212336, 0.90: 1.2815515655,
              0.95: 1.6448536270}.get(power, 0.8416212336)
    return int(math.ceil(((1.959963985 + z_beta) / math.atanh(rho)) ** 2 + 3))


# --------------------------------------------------------------- data access

def load_difficulty(paths: dict[str, Path]) -> tuple[dict[str, float], set[str]]:
    """b_hat keyed 'luke{ch}:item{idx}:{q_type}', plus the model ids the
    estimate was fitted on (used for the (c) shared-source check)."""
    out: dict[str, float] = {}
    models: set[str] = set()
    for q_type, path in paths.items():
        if not path.exists():
            print(f"[warn] no anchor-IRT estimates for q_type={q_type} at "
                  f"{path} -- that q_type is dropped from G1.")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        models |= set((payload.get("model_abilities") or {}).keys())
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
            print(f"[warn] {path} parsed but yielded no b_hat -- "
                  f"unrecognised schema.")
    return out, models


def item_correct(item: dict) -> float | None:
    if item.get("q_type") == "mcq":
        value = item.get("direct_correct")
        return None if value is None else float(bool(value))
    value = item.get("llm_score")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_cell(path: Path, passage: str) -> list[dict]:
    """One score file -> raw rows. Effort may be absent (pre-104b4c03 cells)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[skip] unreadable {path}: {exc}")
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append({
                "passage": passage,
                "key": f"{passage}:item{item.get('item_index')}:{item.get('q_type')}",
                "q_type": item.get("q_type"),
                "item_index": item.get("item_index"),
                "effort": item.get("answer_effort"),
                "correct": item_correct(item)})
    return out


def difficulty_from_peers(root: Path, templates: list[str],
                          passages: list[str]) -> tuple[dict[str, float], set[str]]:
    """Item difficulty as -(mean correct) over PEER answerers' clean cells.

    Why this is a legitimate stand-in where no anchor IRT exists (tier-1 has
    none -- the anchor inputs are Luke-only): in a Rasch/1PL model the item's
    total-correct count is a sufficient statistic for b_i, so b_hat is a
    monotone function of mean correctness. G1 is a RANK correlation, and rank
    correlations are invariant under monotone transforms -- so peer accuracy
    and a fitted b_hat give the same rho, up to prior shrinkage and ties.

    It also solves the shared-source problem by construction: the answer model
    whose tokens we correlate is not among the peers, so (c) is satisfied
    without a leave-one-out refit.

    The cost is TIES. Two peers x a binary outcome gives at most 3 distinct
    levels for mcq, which attenuates rho badly. The distinct-level count is
    reported so this is visible rather than assumed away.
    """
    totals: dict[str, list[float]] = {}
    models: set[str] = set()
    for template in templates:
        models.add(template)
        for passage in passages:
            path = root / template.format(passage=passage) / SCORE_FILE
            if not path.exists():
                continue
            for row in read_cell(path, passage):
                if row["correct"] is not None:
                    totals.setdefault(row["key"], []).append(row["correct"])
    return ({k: -(sum(v) / len(v)) for k, v in totals.items() if v}, models)


def collect(root: Path, cell_template: str, passages: list[str],
            difficulty: dict[str, float]) -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    tally = {"cells": 0, "items": 0, "no_effort": 0, "no_bhat": 0}
    for passage in passages:
        path = root / cell_template.format(passage=passage) / SCORE_FILE
        if not path.exists():
            continue
        tally["cells"] += 1
        for raw in read_cell(path, passage):
            tally["items"] += 1
            effort = raw["effort"]
            if not isinstance(effort, dict) or not effort.get("output_tokens"):
                tally["no_effort"] += 1
                continue
            b = difficulty.get(raw["key"])
            if b is None:
                tally["no_bhat"] += 1
                continue
            rows.append({
                "key": raw["key"], "passage": passage,
                "q_type": raw["q_type"], "item_index": raw["item_index"],
                "b_hat": b,
                "output_tokens": float(effort["output_tokens"]),
                "prompt_tokens": float(effort.get("prompt_tokens") or 0.0),
                "thinking_chars": float(effort.get("thinking_chars") or 0.0),
                "answer_chars": float(effort.get("answer_chars") or 0.0),
                "thinking_source": effort.get("thinking_source"),
                "done_reason": effort.get("done_reason"),
                "correct": raw["correct"]})
    return rows, tally


def gate_zero(rows: list[dict]) -> dict[str, Any]:
    """G0: is there any effort variance to correlate?"""
    tokens = sorted(r["output_tokens"] for r in rows)
    n = len(tokens)
    median = tokens[n // 2] if n else 0.0
    distinct = len(set(tokens))
    thinking = [r["thinking_chars"] for r in rows]
    sources = {r.get("thinking_source") for r in rows}
    degenerate = distinct < G0_MIN_DISTINCT or median < G0_MIN_MEDIAN_TOKENS
    thinking_off = all(t == 0 for t in thinking) and sources <= {None}
    return {"n": n, "median": median, "distinct": distinct,
            "iqr": (tokens[int(n * .75)] - tokens[int(n * .25)]) if n > 3 else 0.0,
            "median_thinking_chars": (sorted(thinking)[n // 2] if n else 0.0),
            "thinking_sources": sources, "thinking_off": thinking_off,
            "degenerate": degenerate}


# ------------------------------------------------------------------ analysis

def correlate(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    if n < 4:
        return {"n": n, "rho": None, "p": float("nan"), "partial": None}
    tokens = [math.log(r["output_tokens"]) for r in rows]
    b_hat = [r["b_hat"] for r in rows]
    prompt = [math.log(r["prompt_tokens"]) if r["prompt_tokens"] > 0 else 0.0
              for r in rows]
    rho = spearman(b_hat, tokens)
    partial = partial_spearman(b_hat, tokens, prompt)
    observed = [r["correct"] for r in rows if r["correct"] is not None]
    obs_tokens = [math.log(r["output_tokens"]) for r in rows
                  if r["correct"] is not None]
    return {"n": n, "rho": rho, "p": fisher_p(rho, n),
            "partial": partial, "partial_p": fisher_p(partial, n),
            "rho_prompt": spearman(prompt, tokens),
            "rho_correct": spearman(observed, obs_tokens) if observed else None,
            "min_detectable": min_detectable_rho(n),
            "tie_ceiling": tie_ceiling(b_hat, tokens)}


def rho_ci(rho: float, n: int, alpha: float = G1_ALPHA) -> tuple[float, float]:
    """Fisher-z confidence interval for a correlation."""
    z, se = math.atanh(rho), 1.0 / math.sqrt(n - 3)
    half = 1.959963985 * se
    return math.tanh(z - half), math.tanh(z + half)


def tie_ceiling(b_hat: list[float], y: list[float]) -> float | None:
    """Largest rho achievable given the tie structure of b_hat.

    A coarse difficulty proxy (peer accuracy over 2 binary respondents gives ~5
    levels) cannot reach rho=1 however good the effort measure is. Sorting y
    into b_hat's tie groups in perfect order gives that upper bound, so the
    observed rho can be read against what was reachable rather than against 1.0.
    Measured on gold72 (2026-08-20): ceiling 0.951 -- ties cost only ~5%, so a
    weak rho there is NOT a tie artifact. Note this bounds the TIE effect only;
    noise in the difficulty estimate attenuates separately and is not covered.
    """
    if len(b_hat) < 4:
        return None
    order = sorted(range(len(b_hat)), key=lambda i: b_hat[i])
    ideal = [0.0] * len(b_hat)
    for position, index in enumerate(order):
        ideal[index] = sorted(y)[position]
    return spearman(b_hat, ideal)


def verdict(res: dict[str, Any]) -> str:
    """Threshold test on the INTERVAL, not the point estimate.

    Comparing a point estimate to a threshold silently claims a precision the
    data may not have: on gold72, rho=0.253 with CI [0.093, 0.401] sits below
    0.30 yet cannot be distinguished from it. Reporting that as FAIL would
    retire the programme on a difference the study could not resolve.
    """
    rho, n = res.get("rho"), res["n"]
    if rho is None:
        return "NO DATA"
    if n <= 3:
        return "NO DATA -- n too small for an interval"
    lo, hi = rho_ci(rho, n)
    res["ci"] = (lo, hi)
    if res["p"] >= G1_ALPHA:
        floor = res.get("min_detectable")
        if floor is not None and floor > G1_MIN_RHO:
            return (f"UNDERPOWERED -- n={n} resolves only |rho|>={floor:.2f}, "
                    f"and G1 asks about {G1_MIN_RHO:.2f}. "
                    f"n>={n_for_rho(G1_MIN_RHO)} to detect it if observed; "
                    f"n>={n_for_power(G1_MIN_RHO)} for 80% power.")
        return (f"FAIL -- rho={rho:+.3f} is not distinguishable from zero "
                f"(p={res['p']:.3f}). No effort signal. STOP.")
    if lo >= G1_MIN_RHO:
        return f"PASS -- CI [{lo:.3f}, {hi:.3f}] lies above {G1_MIN_RHO}."
    if hi < G1_MIN_RHO:
        return (f"FAIL -- signal is real (p={res['p']:.4f}) but CI "
                f"[{lo:.3f}, {hi:.3f}] lies entirely below {G1_MIN_RHO}. "
                f"Too weak to carry the dose analyses.")
    return (f"INCONCLUSIVE -- rho={rho:+.3f} significant (p={res['p']:.4f}) but "
            f"CI [{lo:.3f}, {hi:.3f}] straddles {G1_MIN_RHO}; the data cannot "
            f"resolve the threshold. Reduce difficulty-proxy noise or add n "
            f"(n>={n_for_power(G1_MIN_RHO)} for 80% power).")


def truncation(rows: list[dict]) -> tuple[float, dict[str, int]]:
    tally: dict[str, int] = {}
    for row in rows:
        tally[str(row.get("done_reason"))] = tally.get(str(row.get("done_reason")), 0) + 1
    return tally.get("length", 0) / max(len(rows), 1), tally


def build_summary(args, rows, tally, res, by_type, trunc_rate, reasons,
                  fitted_models, g0) -> str:
    def f(value, digits=3):
        if value is None:
            return "n/a"
        return "nan" if isinstance(value, float) and math.isnan(value) \
            else f"{value:.{digits}f}"

    lines = ["GATE G1 -- DOES TOKEN SPEND TRACK ITEM DIFFICULTY?",
             f"cells={args.cell_template}  passages={len(args.passages)}  "
             f"difficulty={args.difficulty_source}",
             f"cells found={tally['cells']}  items seen={tally['items']}  "
             f"joined={len(rows)}  (dropped: no_effort={tally['no_effort']}, "
             f"no_bhat={tally['no_bhat']})", ""]

    lines += ["(0) IS THERE ANY EFFORT VARIANCE? [Gate G0]",
              f"  median output_tokens = {g0['median']:.0f}   "
              f"distinct values = {g0['distinct']}   IQR = {g0['iqr']:.0f}",
              f"  median thinking_chars = {g0['median_thinking_chars']:.0f}   "
              f"thinking_source = {g0['thinking_sources']}"]
    if g0["degenerate"]:
        lines += ["  ⛔ DEGENERATE -- the DV has essentially no variance.",
                  "     G1 below is arithmetic on noise. DO NOT INTERPRET IT."]
        if g0["thinking_off"]:
            lines += ["     Cause: thinking was OFF for this run (zero reasoning",
                      "     chars, no thinking_source). With --ollama-no-think an",
                      "     MCQ answer is the single token \"B\"; there is nothing",
                      "     to correlate. Re-run the cell WITHOUT that flag.",
                      "     (/no_think as a prompt token is ignored by qwen3:1.7b;",
                      "      the structured think:false is what takes effect, so",
                      "      omitting the flag is what enables reasoning.)"]
    else:
        lines.append("  OK -- the DV varies enough to carry a correlation.")
    lines.append("")

    lines += ["(a) TRUNCATION [Gate G2]",
              f"  done_reason=='length': {trunc_rate:.1%}   {reasons}"]
    if trunc_rate > TRUNC_STOP:
        lines.append("  STOP -- the DV is censored. Raise OLLAMA_NUM_PREDICT / "
                     "OLLAMA_NUM_CTX and re-run before reading anything below.")
    elif trunc_rate > TRUNC_WARN:
        lines.append("  WARN -- some censoring; treat rho as a lower bound.")
    else:
        lines.append("  OK")
    lines.append("")

    lines += ["(1) G1 CORRELATION  Spearman(b_hat, log output_tokens)",
              f"  n            = {res['n']}",
              f"  rho          = {f(res.get('rho'))}   p = {f(res.get('p'), 4)}",
              f"  rho partial  = {f(res.get('partial'))}   p = "
              f"{f(res.get('partial_p'), 4)}   (controls log prompt_tokens)",
              f"  min |rho| detectable at n={res['n']}: "
              f"{f(res.get('min_detectable'), 2)}",
              f"  tie ceiling  = {f(res.get('tie_ceiling'))}   "
              f"(max reachable given the difficulty proxy's ties; "
              f"disattenuated rho = "
              f"{f((res['rho'] / res['tie_ceiling']) if res.get('rho') is not None and res.get('tie_ceiling') else None)})",
              f"  for reference: rho={G1_MIN_RHO} is significant-if-observed at "
              f"n>={n_for_rho(G1_MIN_RHO)}, and needs n>="
              f"{n_for_power(G1_MIN_RHO)} for 80% power",
              f"  VERDICT: {verdict(res)}", ""]

    if by_type:
        lines.append("  by question form:")
        for q_type, sub in by_type.items():
            lines.append(f"    {q_type:<5} n={sub['n']:<4} rho={f(sub.get('rho'))} "
                         f"partial={f(sub.get('partial'))} "
                         f"p={f(sub.get('p'), 4)}")
        lines.append("    (mcq is judge-free; open labels carry the "
                     "4.5-18.2% judge flip rate)")
        lines.append("")

    lines += ["(b) PROMPT-LENGTH CONFOUND",
              f"  Spearman(log prompt_tokens, log output_tokens) = "
              f"{f(res.get('rho_prompt'))}",
              "  If this is large AND the partial rho above collapses toward 0,",
              "  the raw G1 correlation is a window-length artifact, not effort.",
              ""]

    lines += ["(c) SHARED-SOURCE DEPENDENCE"]
    if ANSWER_MODEL_KEY in fitted_models:
        lines += [f"  ⚠ b_hat was fitted on responses INCLUDING '{ANSWER_MODEL_KEY}' "
                  f"(models: {sorted(fitted_models)}).",
                  "  So this correlation partly asks 'does the model spend more",
                  "  tokens on items IT got wrong', which is weaker than G1's",
                  "  claim. For the clean version, re-estimate b_hat without it:",
                  "",
                  "    python3 QA_algorithm/scripts/effort/make_loo_anchor_input.py \\",
                  f"        --exclude '{ANSWER_MODEL_KEY}'",
                  "    for QT in mcq open; do",
                  "      python3 QA_algorithm/scripts/anchor_irt/estimate_anchor_irt.py \\",
                  "        --input-json  QA_algorithm/inputs/anchor_irt_input_loo_$QT.json \\",
                  "        --output-json QA_algorithm/outputs/anchor_irt_estimates_loo_$QT.json",
                  "    done",
                  "    python3 QA_algorithm/scripts/effort/g1_effort_vs_difficulty.py \\",
                  "        --anchor-estimates "
                  "QA_algorithm/outputs/anchor_irt_estimates_loo_mcq.json \\",
                  "                           "
                  "QA_algorithm/outputs/anchor_irt_estimates_loo_open.json"]
    else:
        lines.append(f"  OK -- b_hat fitted without '{ANSWER_MODEL_KEY}' "
                     f"(models: {sorted(fitted_models) or 'unknown'}).")
    lines += ["",
              f"  descriptive: Spearman(correct, log tokens) = "
              f"{f(res.get('rho_correct'))}",
              "  (strongly negative = the model spends more on what it fails;",
              "   that is the mechanism G1 assumes, not an independent check)",
              ""]

    lines += ["CAVEATS",
              "  - Clean cells only. This gate says nothing about dose response.",
              "  - Temperature 0: no replicate variance. n here is items.",
              "  - Thinking must be ON. With --ollama-no-think an MCQ answer is",
              "    1-3 tokens and there is almost no variance to correlate.",
              "  - b_hat came from temp-1.0, thinking-OFF anchor runs; the token",
              "    spend is temp-0, thinking-ON. Different conditions -- which",
              "    weakens the join but also blunts (c)."]
    return "\n".join(lines)


# ------------------------------------------------------------------ self-test

def self_test() -> int:
    import random
    rng = random.Random(20260820)
    failures = []

    # tokens generated as a monotone function of b_hat plus noise
    rows = []
    for chapter in range(1, 9):
        for i in range(12):
            for q_type in ("mcq", "open"):
                b = rng.gauss(0, 1)
                tokens = math.exp(4.8 + 0.45 * b + rng.gauss(0, 0.25))
                rows.append({"key": f"luke{chapter}:item{i}:{q_type}",
                             "passage": f"luke{chapter}", "q_type": q_type,
                             "item_index": i, "b_hat": b,
                             "output_tokens": tokens, "prompt_tokens": 300.0,
                             "thinking_chars": 600.0, "answer_chars": 10.0,
                             "done_reason": "stop", "correct": 1.0})
    res = correlate(rows)
    if res["rho"] is None or res["rho"] < 0.6:
        failures.append(f"planted signal not recovered: rho={res['rho']}")
    else:
        print(f"  [ok] planted signal recovered: rho={res['rho']:.3f} "
              f"p={res['p']:.2g}  verdict={verdict(res).split(' --')[0]}")

    # pure noise must NOT pass
    noise = [dict(r, output_tokens=math.exp(rng.gauss(4.8, 0.25))) for r in rows]
    res_noise = correlate(noise)
    if verdict(res_noise) == "PASS":
        failures.append(f"noise passed G1: rho={res_noise['rho']}")
    else:
        print(f"  [ok] noise rejected: rho={res_noise['rho']:+.3f} "
              f"verdict={verdict(res_noise).split(' --')[0]}")

    # A pure prompt-length artifact must survive the raw rho but die in the
    # partial: harder items happen to sit in longer windows, and tokens track
    # ONLY window length. Raw G1 would call this a pass; the partial must not.
    art = []
    for r in rows:
        prompt = math.exp(5.5 + 0.5 * r["b_hat"] + rng.gauss(0, 0.35))
        art.append(dict(r, prompt_tokens=prompt,
                        output_tokens=prompt * math.exp(rng.gauss(0, 0.02))))
    res_art = correlate(art)
    raw, part = res_art["rho"], res_art["partial"]
    if raw is None or part is None or raw < 0.5 or abs(part) > 0.3:
        failures.append(f"prompt-artifact check wrong: raw={raw} partial={part}")
    else:
        print(f"  [ok] prompt-length artifact caught: raw rho="
              f"{raw:.3f} -> partial {part:+.3f}")

    # Degenerate case: control perfectly collinear with b_hat. The partial is
    # mathematically undefined -- it must come back None, not a fake number.
    exact = [dict(r, prompt_tokens=math.exp(5.5 + 0.5 * r["b_hat"]))
             for r in rows]
    if correlate(exact)["partial"] is not None:
        failures.append("collinear control did not yield an undefined partial")
    else:
        print("  [ok] collinear control -> partial undefined (not fabricated)")

    # Underpowered = small n AND no significance. A small n with a huge effect
    # is NOT underpowered (the old test wrongly said it was, by reading
    # min_detectable without looking at whether significance was reached).
    small_noise = correlate(noise[:8])
    if not verdict(small_noise).startswith("UNDERPOWERED"):
        failures.append(f"small-n null not flagged underpowered: "
                        f"{verdict(small_noise)}")
    else:
        print("  [ok] n=8 with no signal -> UNDERPOWERED, not FAIL")
    strong_small = correlate(rows[:8])
    if not verdict(strong_small).startswith("PASS"):
        failures.append(f"small-n strong effect misjudged: "
                        f"{verdict(strong_small)}")
    else:
        print("  [ok] n=8 with a huge effect -> PASS (interval clears the bar)")

    # The band gold72 actually landed in: significant, but CI straddles 0.30.
    # Must be INCONCLUSIVE -- calling it FAIL would retire the programme on a
    # difference the study cannot resolve.
    band = {"n": 143, "rho": 0.253, "p": 0.0022,
            "min_detectable": min_detectable_rho(143)}
    if not verdict(band).startswith("INCONCLUSIVE"):
        failures.append(f"threshold-straddling case misjudged: {verdict(band)}")
    else:
        lo, hi = rho_ci(0.253, 143)
        print(f"  [ok] rho=0.253 n=143 -> INCONCLUSIVE "
              f"(CI [{lo:.3f}, {hi:.3f}] straddles {G1_MIN_RHO})")

    # A real but genuinely too-weak effect must still FAIL.
    weak = {"n": 2000, "rho": 0.09, "p": 1e-5,
            "min_detectable": min_detectable_rho(2000)}
    if not verdict(weak).startswith("FAIL"):
        failures.append(f"weak-but-significant case misjudged: {verdict(weak)}")
    else:
        print("  [ok] rho=0.09 n=2000 -> FAIL (significant but CI below the bar)")

    # tie ceiling: a 5-level proxy still permits a high rho
    ceiling = tie_ceiling([0, 0, 1, 1, 2, 2, 3, 3, 4, 4],
                          [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    if ceiling is None or ceiling < 0.9:
        failures.append(f"tie ceiling implausible: {ceiling}")
    else:
        print(f"  [ok] tie ceiling on a 5-level proxy = {ceiling:.3f}")

    # known values
    if abs((spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) or 0) - 0.8) > 1e-9:
        failures.append("spearman wrong on a known case")
    else:
        print("  [ok] spearman matches the known value 0.800")
    if n_for_rho(0.30) != 44 or n_for_power(0.30) != 85:
        failures.append(f"power wrong: n_for_rho={n_for_rho(0.30)} (want 44), "
                        f"n_for_power={n_for_power(0.30)} (want 85)")
    else:
        print("  [ok] power: rho=0.30 significant-if-observed at n=44, "
              "80% power at n=85")

    if failures:
        print("\nSELF-TEST FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nSELF-TEST PASSED")
    return 0


# ----------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cell-template", default=DEFAULT_CELL_TEMPLATE,
                        help="Path to the clean cell under --root, with "
                             "{passage}. Luke default: "
                             "'{passage}/1.7b_think/llm_prompt_high'. Tier-1 "
                             "layout differs: "
                             "'tier1_bsb/{passage}/qwen317b_think/grammar/0%%'.")
    parser.add_argument("--passages", nargs="+", default=DEFAULT_PASSAGES,
                        help="Passage ids. Default luke1..luke8.")
    parser.add_argument("--difficulty-source", choices=("anchor", "peers"),
                        default="anchor",
                        help="'anchor' = fitted b_hat (Luke only). 'peers' = "
                             "-(mean correct) over other answerers' clean "
                             "cells; rank-equivalent under a 1PL and clean of "
                             "shared-source bias, but heavily tied.")
    parser.add_argument("--peer-templates", nargs="+", default=[],
                        help="Clean-cell templates for the PEER answerers, "
                             "used with --difficulty-source peers. Must not "
                             "include the model being correlated.")
    parser.add_argument("--anchor-estimates", nargs=2, metavar=("MCQ", "OPEN"),
                        type=Path,
                        help="Explicit anchor-IRT estimate JSONs. Use this to "
                             "point at a leave-one-out re-estimate.")
    parser.add_argument("--root", type=Path, default=EVAL_OUT)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.difficulty_source == "peers":
        if not args.peer_templates:
            print("[fatal] --difficulty-source peers needs --peer-templates")
            return 2
        difficulty, fitted_models = difficulty_from_peers(
            args.root, args.peer_templates, args.passages)
        levels = len(set(difficulty.values()))
        print(f"[info] peer difficulty: {len(difficulty)} items, "
              f"{levels} distinct level(s) from {len(args.peer_templates)} peer "
              f"model(s). Few levels => heavy ties => attenuated rho.")
    else:
        anchor = ({"mcq": args.anchor_estimates[0],
                   "open": args.anchor_estimates[1]}
                  if args.anchor_estimates else ANCHOR_DEFAULT)
        difficulty, fitted_models = load_difficulty(anchor)
    if not difficulty:
        print("[fatal] no difficulty estimates loaded. Either generate the "
              "anchor estimates:\n"
              "  python3 QA_algorithm/scripts/anchor_irt/estimate_anchor_irt.py \\\n"
              "      --input-json  QA_algorithm/inputs/anchor_irt_input_open.json \\\n"
              "      --output-json QA_algorithm/outputs/anchor_irt_estimates_open.json\n"
              "or use --difficulty-source peers (tier-1 has no anchor IRT).")
        return 2

    rows, tally = collect(args.root, args.cell_template, args.passages,
                          difficulty)
    if not rows:
        print(f"[fatal] no clean cells with answer_effort at "
              f"{args.root}/{args.cell_template}/{SCORE_FILE}\n"
              f"        cells found={tally['cells']} items={tally['items']} "
              f"no_effort={tally['no_effort']} no_bhat={tally['no_bhat']}\n"
              f"        Run the clean pass first: "
              f"bash evaluation/scripts/campaigns/run_g1_clean_pass.sh")
        return 2

    res = correlate(rows)
    by_type = {}
    for q_type in ("mcq", "open"):
        subset = [r for r in rows if r["q_type"] == q_type]
        if len(subset) >= 4:
            by_type[q_type] = correlate(subset)
    trunc_rate, reasons = truncation(rows)
    g0 = gate_zero(rows)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["key", "passage", "q_type", "item_index", "b_hat",
              "output_tokens", "prompt_tokens", "thinking_chars",
              "answer_chars", "thinking_chars", "thinking_source",
              "done_reason", "correct"]
    with (args.out_dir / "g1_items.csv").open("w", newline="",
                                              encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})

    summary = build_summary(args, rows, tally, res, by_type, trunc_rate,
                            reasons, fitted_models, g0)
    (args.out_dir / "g1_summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"\nwrote -> {args.out_dir}")
    if g0["degenerate"]:
        return 3
    final = verdict(res)
    return 0 if final.startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
