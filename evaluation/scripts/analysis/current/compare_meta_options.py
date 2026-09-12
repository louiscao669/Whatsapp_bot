#!/usr/bin/env python3
"""Accuracy, abstention (E) and none-of-the-above (F) as separate outcomes.

Works with 5-option (E only) or 6-option (E and F) runs, and with one arm or two.

Meta-options are detected from the ANSWER TEXT as well as from selected_choice.
The mapper returns None when it cannot map a reply to a permitted letter, and in
the 2026-09-11 run every one of the 18 Nones was the model quoting option E's text
verbatim while the prompt still said "A, B, C, or D". Reading only selected_choice
reported a 0% abstention rate for a run that actually abstained 18 times.

Chance: 0.250 at 4 options, 0.200 at 5, 0.167 at 6 -- but measured EFFECTIVE options
on gold72 are 2.81 (40% of content distractors are never selected), so the real
floor is higher. Do not compare across option counts.
"""
import json, math, os, sys
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
ARMS = {"blinded": os.environ.get("ARM_BLINDED", "tier1_bsb_6opt"),
        "unblinded": os.environ.get("ARM_UNBLINDED", "tier1_bsb_unblinded_6opt")}
MODELS = ["llama321b", "qwen2515b", "qwen317b"]
DOSES = ["0%", "30%"]
TEXT = {"E": ("无法", "不知道", "没有说", "未提", "不确定", "不能确定"),
        "F": ("以上都不是", "以上都不", "以上均不")}

def classify(it):
    """-> ('E'|'F'|'content'|'unparsed', correct: 0/1)"""
    sc = str(it.get("selected_choice") or "").strip().upper()[:1]
    ans = str(it.get("generated_answer") or "")
    if sc in ("E", "F"): meta = sc
    elif sc in ("A", "B", "C", "D"): meta = "content"
    else:
        meta = next((L for L, ms in TEXT.items() if any(m in ans for m in ms)), "unparsed")
    return meta, (1.0 if it.get("direct_correct") else 0.0)

def load(tree, dose):
    out = {}
    base = os.path.join(R, tree)
    if not os.path.isdir(base): return out
    for p in sorted(os.listdir(base)):
        if not p.startswith("t1_"): continue
        for m in MODELS:
            f = os.path.join(base, p, m, "omission", dose, "scores_target_llama.json")
            if not os.path.exists(f): continue
            for it in json.load(open(f)).get("items", []):
                if it.get("q_type") != "mcq": continue
                iid = str(it["id"]).split(":")[-1].rsplit("-", 1)[0]
                out[(p, iid, m)] = classify(it)
    return out

D = {(a, d): load(t, d) for a, t in ARMS.items() for d in DOSES}
present = [a for a in ARMS if all(D[(a, d)] for d in DOSES)]
for a in ARMS:
    if a not in present: print(f"  (no data for the {a} arm at {ARMS[a]} -- skipping)")
if not present: raise SystemExit("no arm has data yet")
keys = None
for a in present:
    for d in DOSES:
        keys = set(D[(a, d)]) if keys is None else keys & set(D[(a, d)])
keys = keys or set()
print(f"paired MCQ observations: {len(keys)}   items: {len({(k[0],k[1]) for k in keys})}")
print(f"arms: {', '.join(present)}\n")
if not keys: raise SystemExit("nothing paired yet")

def mean(x): return sum(x)/len(x) if x else float("nan")
def dz(v):
    n=len(v)
    if n<2: return float("nan")
    mu=mean(v); s=math.sqrt(sum((x-mu)**2 for x in v)/(n-1))
    return mu/s if s>0 else 0.0

has_f = any(D[(a,d)][k][0]=="F" for a in present for d in DOSES for k in keys) or True
print("="*86)
print("VALIDITY GATE — meta-option selection on CLEAN text (both should be near zero)")
print("="*86)
print(f"{'arm':10} {'model':11} {'E abstain':>10} {'F none-above':>13} {'unparsed':>10}")
for a in present:
    for m in MODELS:
        ks=[k for k in keys if k[2]==m]
        c=defaultdict(int)
        for k in ks: c[D[(a,"0%")][k][0]]+=1
        n=len(ks)
        flag="  <-- SUSPECT" if max(c['E'],c['F'])/n>0.25 else ""
        print(f"{a:10} {m:11} {c['E']/n:10.3f} {c['F']/n:13.3f} {c['unparsed']/n:10.3f}{flag}")
    print()

print("="*86)
print("OUTCOMES BY DOSE")
print("="*86)
print(f"{'arm':10} {'model':11} {'dose':>5} {'accuracy':>9} {'E abstain':>10} {'F none-above':>13} {'content':>8}")
for a in present:
    for m in MODELS:
        ks=[k for k in keys if k[2]==m]
        for d in DOSES:
            c=defaultdict(int); acc=[]
            for k in ks:
                meta,cor=D[(a,d)][k]; c[meta]+=1; acc.append(cor)
            n=len(ks)
            print(f"{a:10} {m:11} {d:>5} {mean(acc):9.3f} {c['E']/n:10.3f} {c['F']/n:13.3f} {c['content']/n:8.3f}")
        print()

print("="*86)
print("WHICH OUTCOME SEPARATES DOSE BEST?  paired dz, 0% -> 30%")
print("="*86)
print(f"{'arm':10} {'model':11} {'accuracy':>10} {'E rise':>9} {'F rise':>9}")
for a in present:
    for m in MODELS:
        ks=[k for k in keys if k[2]==m]
        da=dz([D[(a,"0%")][k][1]-D[(a,"30%")][k][1] for k in ks])
        de=dz([(1 if D[(a,"30%")][k][0]=="E" else 0)-(1 if D[(a,"0%")][k][0]=="E" else 0) for k in ks])
        df=dz([(1 if D[(a,"30%")][k][0]=="F" else 0)-(1 if D[(a,"0%")][k][0]=="F" else 0) for k in ks])
        print(f"{a:10} {m:11} {da:10.3f} {de:9.3f} {df:9.3f}")
    print()
print("Reminder: E and F are only worth separating if each fires often enough to measure.")
print("At 6.6% combined (the 2026-09-11 single-option rate) each cell holds ~7 events.")
