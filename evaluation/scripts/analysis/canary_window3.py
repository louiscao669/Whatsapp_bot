#!/usr/bin/env python3
"""wbw fluency-canary check on the NEW 3-verse-window data (H-T6, matched regime).

The canary: fluency damage (word-by-word) destroys syntax while leaving content words intact,
so MCQ (recognition) stays high while OPEN (production) collapses. Signature = a large
(MCQ − open) gap at wbw, ABOVE what adequacy defects of similar severity produce. Old
whole-passage result: wbw fired at z ≈ +3.8/+4.0 (above-floor models); grammar/awkward 30%
did NOT fire (good specificity).

New-regime twist under test: open is now the MORE sensitive format EVERYWHERE and MCQ is
ceiling-compressed, so the (MCQ − open) gap may widen at every degraded condition — which
would wash out wbw's specificity and make the canary non-diagnostic. This computes, per model:

  gap(c)      = mcq_acc(c) − open_mean(c)            (pooled over 8 chapters)
  excess(c)   = gap(c) − gap(anchor=omission/0%)     (widening vs clean)
  z(c)        = paired per-chapter (gap(c)−gap(anchor)) mean / SE over 8 chapters

Canary is DIAGNOSTIC only if wbw's excess/z stands out from the adequacy conditions
(omission/30%, mistranslation/20%) and stays above the fluency control (grammar/30%).

  python evaluation/scripts/analysis/canary_window3.py
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "evaluation" / "outputs"
SCORE = "scores_target_window3_v2.json"
MODELS = ["llama 1b", "1.5b", "1.7b"]
ANCHOR = "omission/0%"
CONDS = ["omission/10%", "omission/20%", "omission/30%",
         "mistranslation/20%", "grammar/30%", "google_word_by_word"]
OLD_Z = "old whole-passage: wbw z≈+3.8/+4.0; grammar 30% did NOT fire"


def chapter_cell(model, cond, ch):
    """(mcq_acc, open_mean) for one chapter cell, or (nan,nan)."""
    fp = EVAL / f"luke{ch}" / model / cond / SCORE
    if not fp.exists():
        return float("nan"), float("nan")
    mcq, opn = [], []
    for it in json.loads(fp.read_text()).get("items", []):
        if it.get("q_type") == "mcq":
            dc = it.get("direct_correct")
            if dc is not None:
                mcq.append(1.0 if dc else 0.0)
        else:
            v = it.get("llm_score")
            if v is not None:
                opn.append(float(min(1.0, max(0.0, v))))
    m = lambda x: (sum(x) / len(x)) if x else float("nan")
    return m(mcq), m(opn)


def main():
    print("=" * 82)
    print("wbw FLUENCY CANARY — new 3-verse window   (gap = MCQ_acc − open_mean)")
    print("=" * 82)
    print(f"({OLD_Z})\n")

    for model in MODELS:
        # per-chapter gaps
        gaps = {c: [] for c in [ANCHOR] + CONDS}
        for ch in range(1, 9):
            for c in [ANCHOR] + CONDS:
                mcq, opn = chapter_cell(model, c, ch)
                gaps[c].append(mcq - opn if not (math.isnan(mcq) or math.isnan(opn)) else float("nan"))
        anchor_by_ch = np.array(gaps[ANCHOR], float)
        anchor_gap = float(np.nanmean(anchor_by_ch))

        # pooled level to report open floor (is this model above the open floor?)
        open_levels = []
        for ch in range(1, 9):
            _, opn = chapter_cell(model, ANCHOR, ch)
            if not math.isnan(opn):
                open_levels.append(opn)
        open_floor = float(np.mean(open_levels)) if open_levels else float("nan")

        print(f"── {model:8}   anchor gap={anchor_gap:+.3f}   clean open={open_floor:.3f}"
              f"{'  (near floor: canary unreliable)' if open_floor < 0.45 else ''}")
        print(f"   {'condition':22}{'gap':>8}{'excess':>9}{'z (vs anchor)':>15}")
        rows = []
        for c in CONDS:
            g_by_ch = np.array(gaps[c], float)
            gap = float(np.nanmean(g_by_ch))
            excess = gap - anchor_gap
            d = g_by_ch - anchor_by_ch
            d = d[~np.isnan(d)]
            if len(d) > 1 and d.std(ddof=1) > 1e-9:
                z = float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d))))
            else:
                z = float("nan")
            rows.append((c, gap, excess, z))
            tag = "  ← wbw" if c == "google_word_by_word" else ""
            print(f"   {c:22}{gap:>8.3f}{excess:>+9.3f}{z:>15.2f}{tag}")

        # specificity read
        wbw = next(r for r in rows if r[0] == "google_word_by_word")
        adeq = [r for r in rows if r[0] in ("omission/30%", "mistranslation/20%")]
        gram = next(r for r in rows if r[0] == "grammar/30%")
        max_adeq_excess = max(r[2] for r in adeq)
        print(f"   → wbw excess {wbw[2]:+.3f} vs max adequacy excess {max_adeq_excess:+.3f}"
              f" vs grammar excess {gram[2]:+.3f}")
        if open_floor < 0.45:
            print("   → verdict: model near open floor — exclude from canary (as old design required)\n")
        elif wbw[2] > max_adeq_excess + 0.03 and wbw[3] == wbw[3] and wbw[3] > 2:
            print("   → verdict: CANARY DIAGNOSTIC (wbw open-collapse exceeds adequacy conditions)\n")
        else:
            print("   → verdict: NOT diagnostic — wbw gap not distinct from adequacy conditions"
                  " (open>MCQ everywhere washes it out)\n")

    print("Read: if wbw 'excess' is NOT clearly larger than omission/mistranslation excess,")
    print("the canary no longer isolates fluency damage in the new regime — open's general")
    print("sensitivity has absorbed the wbw-specific signal.")


if __name__ == "__main__":
    main()
