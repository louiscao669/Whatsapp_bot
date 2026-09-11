#!/usr/bin/env python3
"""Paired blinded vs unblinded diagnostic on the gold72 items.

Arm A  evaluation/outputs/tier1_bsb            pseudonymized passage + QA
Arm B  evaluation/outputs/tier1_bsb_unblinded  canonical      passage + QA

Held identical: same 71 items, same BSB passages, same llm_prompt_high base at
temperature 0, same 3-verse windows, same 3 answer models, same judge.
The only difference is whether names are blinded.

Two questions:
  1. does clean accuracy rise?            -> size of the prior-knowledge channel
  2. does the 0%->30% drop shrink?        -> does unblinding flatten lambda
"""
import json, math, os
from collections import defaultdict

def _outputs_root():
    """Resolve evaluation/outputs portably.

    Prefer EVAL_OUTPUTS_ROOT, then evaluation/outputs relative to the repo root
    (it is a symlink into eten-research-outputs), then the cwd. Never hardcode a
    machine-specific absolute path -- that silently yields an empty result set
    and reads as 'the run has not finished'.
    """
    import os as _os
    env = _os.environ.get("EVAL_OUTPUTS_ROOT")
    if env and _os.path.isdir(env):
        return env
    here = _os.path.dirname(_os.path.abspath(__file__))
    for _ in range(6):
        cand = _os.path.join(here, "evaluation", "outputs")
        if _os.path.isdir(cand):
            return cand
        here = _os.path.dirname(here)
    for cand in ("evaluation/outputs", "outputs", "."):
        if _os.path.isdir(cand):
            return cand
    raise SystemExit("cannot locate evaluation/outputs; set EVAL_OUTPUTS_ROOT")


R = _outputs_root()
ARMS = {"blinded": "tier1_bsb", "unblinded": "tier1_bsb_unblinded"}
MODELS = ["llama321b", "qwen2515b", "qwen317b"]

def load(tree, dose):
    out = {}
    base = os.path.join(R, tree)
    for p in sorted(os.listdir(base)):
        if not p.startswith("t1_"): continue
        for m in MODELS:
            f = os.path.join(base, p, m, "omission", dose, "scores_target_llama.json")
            if not os.path.exists(f): continue
            for it in json.load(open(f)).get("items", []):
                qt = it.get("q_type")
                v = it.get("direct_correct") if qt == "mcq" else it.get("llm_score")
                if v is None: continue
                iid = it["id"].split(":")[1].rsplit("-", 1)[0]
                out[(p, iid, qt, m)] = float(v)
    return out

D = {(a, d): load(t, d) for a, t in ARMS.items() for d in ("0%", "30%")}
def mean(x): return sum(x)/len(x) if x else float("nan")
def sd(x):
    n=len(x)
    if n<2: return float("nan")
    mu=mean(x); return math.sqrt(sum((v-mu)**2 for v in x)/(n-1))

# items present in every one of the four cells -> fully paired
keys = set(D[("blinded","0%")])
for k in D: keys &= set(D[k])
print(f"fully paired observations (item x model x format): {len(keys)}")
print(f"distinct items: {len({(k[0],k[1]) for k in keys})}\n")

print("="*78)
print("1. CLEAN (0%) ACCURACY — how much do canonical names give the model for free?")
print("="*78)
print(f"{'form':5} {'model':11} {'blinded':>9} {'unblinded':>10} {'delta':>8} {'paired t':>9}")
for qt in ("mcq","open"):
    for m in MODELS:
        ks=[k for k in keys if k[2]==qt and k[3]==m]
        b=[D[("blinded","0%")][k] for k in ks]; u=[D[("unblinded","0%")][k] for k in ks]
        d=[x-y for x,y in zip(u,b)]; s=sd(d)
        t=mean(d)/(s/math.sqrt(len(d))) if s>0 else float("nan")
        print(f"{qt:5} {m:11} {mean(b):9.3f} {mean(u):10.3f} {mean(d):+8.3f} {t:9.2f}")
    ks=[k for k in keys if k[2]==qt]
    b=[D[("blinded","0%")][k] for k in ks]; u=[D[("unblinded","0%")][k] for k in ks]
    d=[x-y for x,y in zip(u,b)]; s=sd(d)
    t=mean(d)/(s/math.sqrt(len(d))) if s>0 else float("nan")
    print(f"{qt:5} {'ALL':11} {mean(b):9.3f} {mean(u):10.3f} {mean(d):+8.3f} {t:9.2f}   n={len(ks)}\n")

print("="*78)
print("2. DOSE RESPONSE — does unblinding flatten the omission signal?")
print("="*78)
print(f"{'form':5} {'model':11} {'arm':10} {'acc0':>6} {'acc30':>6} {'drop':>7} {'dz':>7}")
DZ={}
for qt in ("mcq","open"):
    for m in MODELS:
        ks=[k for k in keys if k[2]==qt and k[3]==m]
        for a in ("blinded","unblinded"):
            a0=[D[(a,"0%")][k] for k in ks]; a30=[D[(a,"30%")][k] for k in ks]
            diffs=[x-y for x,y in zip(a0,a30)]; s=sd(diffs)
            dz=mean(diffs)/s if s>0 else 0.0
            DZ[(qt,m,a)]=dz
            print(f"{qt:5} {m:11} {a:10} {mean(a0):6.3f} {mean(a30):6.3f} {mean(diffs):+7.3f} {dz:7.3f}")
        print()

print("="*78)
print("3. THE HEADLINE — paired dz, blinded vs unblinded")
print("="*78)
print(f"{'form':5} {'model':11} {'blinded dz':>11} {'unblinded dz':>13} {'change':>9}")
tot_b=[];tot_u=[]
for qt in ("mcq","open"):
    for m in MODELS:
        b,u=DZ[(qt,m,"blinded")],DZ[(qt,m,"unblinded")]
        tot_b.append(b);tot_u.append(u)
        print(f"{qt:5} {m:11} {b:11.3f} {u:13.3f} {u-b:+9.3f}")
print(f"\nmean dz over the 6 cells:  blinded {mean(tot_b):.3f}   unblinded {mean(tot_u):.3f}   "
      f"change {mean(tot_u)-mean(tot_b):+.3f}  ({100*(mean(tot_u)-mean(tot_b))/mean(tot_b):+.0f}%)")
print(f"cells where unblinding REDUCED sensitivity: {sum(1 for b,u in zip(tot_b,tot_u) if u<b)}/6")
