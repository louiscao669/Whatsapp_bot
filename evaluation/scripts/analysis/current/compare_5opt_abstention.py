#!/usr/bin/env python3
"""Blinded vs unblinded tier-1 gold72 at 5 options, with abstention as its own DV.

Accuracy and abstention are reported separately. Abstention is the direct readout
of "information destroyed": it should sit near zero on clean text and rise with
dose, and unlike accuracy it has no floor -- which is the problem that has dogged
llama3.2:1b throughout.

VALIDITY GATE: if E-selection at 0% dose is high, the option is being used as a
general escape hatch and that model's cells are uninterpretable.

Chance is 0.20 here, not 0.25. Do not compare these numbers to 4-option runs.
"""
import json, math, os
from collections import defaultdict

def _outputs_root():
    env = os.environ.get("EVAL_OUTPUTS_ROOT")
    if env and os.path.isdir(env): return env
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        c = os.path.join(here, "evaluation", "outputs")
        if os.path.isdir(c): return c
        here = os.path.dirname(here)
    for c in ("evaluation/outputs", "outputs", "."):
        if os.path.isdir(c): return c
    raise SystemExit("cannot locate evaluation/outputs; set EVAL_OUTPUTS_ROOT")

R = _outputs_root()
ARMS = {"blinded": "tier1_bsb_5opt", "unblinded": "tier1_bsb_unblinded_5opt"}
MODELS = ["llama321b", "qwen2515b", "qwen317b"]
DOSES = ["0%", "30%"]

def load(tree, dose):
    acc, abst = {}, {}
    base = os.path.join(R, tree)
    if not os.path.isdir(base): return acc, abst
    for p in sorted(os.listdir(base)):
        if not p.startswith("t1_"): continue
        for m in MODELS:
            f = os.path.join(base, p, m, "omission", dose, "scores_target_llama.json")
            if not os.path.exists(f): continue
            for it in json.load(open(f)).get("items", []):
                if it.get("q_type") != "mcq": continue
                iid = it["id"].split(":")[1].rsplit("-", 1)[0]
                k = (p, iid, m)
                acc[k] = 1.0 if it.get("direct_correct") else 0.0
                ch = str(it.get("direct_choice") or it.get("mcq_choice") or
                         it.get("selected_choice") or "").strip().upper()[:1]
                abst[k] = 1.0 if ch == "E" else 0.0
    return acc, abst

A = {(a, d): load(t, d) for a, t in ARMS.items() for d in DOSES}

# Run whichever arms are present. A single-arm run is a legitimate design: the
# within-arm dose response and the abstention readout stand on their own. Only
# the between-arm blinding contrast needs both.
present = [a for a in ARMS if all(A[(a, d)][0] for d in DOSES)]
for a in ARMS:
    if a not in present:
        print(f"  (no data for the {a} arm -- skipping it)")
if not present:
    raise SystemExit("no arm has data yet")
ARMS_RUN = present

keys = None
for a in ARMS_RUN:
    for d in DOSES:
        keys = set(A[(a, d)][0]) if keys is None else keys & set(A[(a, d)][0])
keys = keys or set()
print(f"paired MCQ observations: {len(keys)}   items: {len({(k[0],k[1]) for k in keys})}")
print(f"arms with data: {', '.join(ARMS_RUN)}\n")
if not keys: raise SystemExit("nothing paired yet")
if len(ARMS_RUN) == 1:
    print("NOTE: one arm only. The dose response and abstention readout below are valid.")
    print("      The blinding contrast is not available, and these 5-option numbers are")
    print("      NOT comparable to the existing 4-option runs (chance 0.20 vs 0.25).\n")

def mean(x): return sum(x)/len(x) if x else float("nan")

print("="*74)
print("VALIDITY GATE — E-selection on CLEAN text (must be near zero)")
print("="*74)
bad = False
for arm in ARMS_RUN:
    for m in MODELS:
        ks = [k for k in keys if k[2] == m]
        r = mean([A[(arm, "0%")][1][k] for k in ks])
        flag = "  <-- SUSPECT" if r > 0.25 else ""
        if r > 0.25: bad = True
        print(f"  {arm:10} {m:11} {r:6.3f}{flag}")
print("  !! a high clean-text abstention rate means E is an escape hatch, not a signal\n" if bad else "")

print("="*74)
print("ACCURACY and ABSTENTION by arm and dose   (chance = 0.20)")
print("="*74)
print(f"{'arm':10} {'model':11} {'acc 0%':>8} {'acc 30%':>8} {'drop':>7} | {'abst 0%':>8} {'abst 30%':>9} {'rise':>7}")
for arm in ARMS_RUN:
    for m in MODELS:
        ks = [k for k in keys if k[2] == m]
        a0, a30 = mean([A[(arm,"0%")][0][k] for k in ks]), mean([A[(arm,"30%")][0][k] for k in ks])
        b0, b30 = mean([A[(arm,"0%")][1][k] for k in ks]), mean([A[(arm,"30%")][1][k] for k in ks])
        print(f"{arm:10} {m:11} {a0:8.3f} {a30:8.3f} {a0-a30:+7.3f} | {b0:8.3f} {b30:9.3f} {b30-b0:+7.3f}")
    print()

print("="*74)
print("WHICH DV SEPARATES DOSE BETTER? paired dz, 0% -> 30%")
print("="*74)
def dz(vals):
    n = len(vals)
    if n < 2: return float("nan")
    mu = mean(vals); s = math.sqrt(sum((v-mu)**2 for v in vals)/(n-1))
    return mu/s if s > 0 else 0.0
print(f"{'arm':10} {'model':11} {'accuracy dz':>12} {'abstention dz':>14}")
for arm in ARMS_RUN:
    for m in MODELS:
        ks = [k for k in keys if k[2] == m]
        da = dz([A[(arm,"0%")][0][k]-A[(arm,"30%")][0][k] for k in ks])
        db = dz([A[(arm,"30%")][1][k]-A[(arm,"0%")][1][k] for k in ks])
        print(f"{arm:10} {m:11} {da:12.3f} {db:14.3f}")
    print()
