#!/usr/bin/env python3
"""Paired comparison of the three Luke naming conditions.

  decanon    人物丙 / 角色02      historical eval condition
  pseudonym  珂温 / 哈丽 / 米珥    pilot delivery form
  canonical  撒迦利亚 / 以利沙伯   UNBLINDED

Same variant passages, doses, items, models, window and judge; the arms differ
only in names. Two questions, same as the tier-1 diagnostic:
  1. does clean accuracy rise as names get more canonical?  -> prior-knowledge channel
  2. does the 0%->30% omission drop shrink?                 -> does it flatten lambda
"""
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts._common import outputs_root

R = outputs_root(__file__)
ARMS = ["decanon", "pseudonym", "canonical"]
TIERS = ["llama 1b", "1.5b", "1.7b"]
DOSES = ["0%", "30%"]

def load(arm, dose):
    out = {}
    for ch in range(1, 9):
        for tier in TIERS:
            f = os.path.join(R, f"naming_{arm}", f"luke{ch}", tier, "omission", dose,
                             "scores_target_llama.json")
            if not os.path.exists(f): continue
            for it in json.load(open(f)).get("items", []):
                qt = it.get("q_type")
                v = it.get("direct_correct") if qt == "mcq" else it.get("llm_score")
                if v is None: continue
                out[(ch, str(it.get("id")), qt, tier)] = float(v)
    return out

D = {(a, d): load(a, d) for a in ARMS for d in DOSES}
for k, v in D.items():
    if not v: print(f"  !! no data for {k} -- has the run finished?")
keys = None
for k, v in D.items():
    keys = set(v) if keys is None else keys & set(v)
keys = keys or set()
print(f"fully paired observations: {len(keys)}   distinct items: {len({(k[0],k[1]) for k in keys})}\n")
if not keys: raise SystemExit("nothing paired yet")

def mean(x): return sum(x)/len(x) if x else float("nan")
def sd(x):
    n=len(x)
    if n<2: return float("nan")
    mu=mean(x); return math.sqrt(sum((v-mu)**2 for v in x)/(n-1))

print("="*80)
print("1. CLEAN (0%) ACCURACY BY NAMING CONDITION")
print("="*80)
print(f"{'form':5} {'model':10} " + "".join(f"{a:>12}" for a in ARMS) + f"{'canon-decanon':>15}")
for qt in ("mcq","open"):
    for tier in TIERS:
        ks=[k for k in keys if k[2]==qt and k[3]==tier]
        vals=[mean([D[(a,"0%")][k] for k in ks]) for a in ARMS]
        d=[D[("canonical","0%")][k]-D[("decanon","0%")][k] for k in ks]
        print(f"{qt:5} {tier:10} " + "".join(f"{v:12.3f}" for v in vals) + f"{mean(d):+15.3f}")
    ks=[k for k in keys if k[2]==qt]
    vals=[mean([D[(a,"0%")][k] for k in ks]) for a in ARMS]
    d=[D[("canonical","0%")][k]-D[("decanon","0%")][k] for k in ks]
    s=sd(d); t=mean(d)/(s/math.sqrt(len(d))) if s>0 else float("nan")
    print(f"{qt:5} {'ALL':10} " + "".join(f"{v:12.3f}" for v in vals) + f"{mean(d):+15.3f}   t={t:.2f} n={len(ks)}\n")

print("="*80)
print("2. DOSE RESPONSE (0% -> 30% omission), paired Cohen's dz")
print("="*80)
print(f"{'form':5} {'model':10} " + "".join(f"{a:>12}" for a in ARMS))
agg=defaultdict(list)
for qt in ("mcq","open"):
    for tier in TIERS:
        ks=[k for k in keys if k[2]==qt and k[3]==tier]
        row=[]
        for a in ARMS:
            diffs=[D[(a,"0%")][k]-D[(a,"30%")][k] for k in ks]
            s=sd(diffs); dz=mean(diffs)/s if s>0 else 0.0
            row.append(dz); agg[a].append(dz)
        print(f"{qt:5} {tier:10} " + "".join(f"{v:12.3f}" for v in row))
    print()
print("mean dz over the 6 model x form cells:")
for a in ARMS: print(f"  {a:10} {mean(agg[a]):.3f}")
print(f"\ncanonical - decanon: {mean(agg['canonical'])-mean(agg['decanon']):+.3f}"
      f"   ({100*(mean(agg['canonical'])-mean(agg['decanon']))/mean(agg['decanon']):+.0f}%)")
print(f"cells where UNBLINDING reduced sensitivity: "
      f"{sum(1 for c,d in zip(agg['canonical'],agg['decanon']) if c<d)}/6")
