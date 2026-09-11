#!/usr/bin/env python3
"""Dose ladders, floor headroom and the wbw method contrast. See compare_qa_sets.py."""
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


ROOT=_outputs_root()
SETS={"strong66":"tier1_strong","gold72":"tier1_bsb","hard95":"tier1_hard_v3"}
MODELS=["llama321b","qwen2515b","qwen317b"]
FAMILIES=["omission","mistranslation","grammar"]
DOSES=["0%","5%","10%","15%","20%","30%"]
def load(fp):
    out={}
    if not os.path.exists(fp): return None
    d=json.load(open(fp))
    for it in d.get("items",[]):
        qt=it.get("q_type"); v=it.get("direct_correct") if qt=="mcq" else it.get("llm_score")
        if v is None: continue
        out[(it.get("id"),qt)]=float(v)
    return out
def mean(xs): return sum(xs)/len(xs) if xs else float("nan")
def stdev(xs):
    n=len(xs)
    if n<2: return float("nan")
    m=mean(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(n-1))

cells=defaultdict(dict)   # (set,model,fam,dose,qt) -> {(passage,id):v}
wbw=defaultdict(dict)
for s,tree in SETS.items():
    base=os.path.join(ROOT,tree)
    for p in sorted(os.listdir(base)):
        if not p.startswith("t1_"): continue
        for m in MODELS:
            for fam in FAMILIES:
                for dose in DOSES:
                    r=load(os.path.join(base,p,m,fam,dose,"scores_target_llama.json"))
                    if r:
                        for (i,qt),v in r.items(): cells[(s,m,fam,dose,qt)][(p,i)]=v
            r=load(os.path.join(base,p,m,"google_word_by_word","scores_target_llama.json"))
            if r:
                for (i,qt),v in r.items(): wbw[(s,m,qt)][(p,i)]=v

print("="*80); print("A. FULL DOSE LADDER -- mean accuracy at each dose (pooled over 3 models)"); print("="*80)
for qt in ["mcq","open"]:
    for fam in FAMILIES:
        print(f"\n{fam} / {qt}")
        print(f"{'set':10} " + " ".join(f"{d:>7}" for d in DOSES) + "   spearman(dose,acc)")
        for s in ["gold72","strong66","hard95"]:
            row=[]
            for d in DOSES:
                vals=[]
                for m in MODELS: vals += list(cells[(s,m,fam,d,qt)].values())
                row.append(mean(vals))
            # spearman of dose rank vs acc rank (6 points)
            xr=list(range(6))
            yr=[sorted(row).index(v) for v in row]
            n=6; dsum=sum((a-b)**2 for a,b in zip(xr,yr))
            rho=1-6*dsum/(n*(n*n-1))
            print(f"{s:10} " + " ".join(f"{v:7.3f}" for v in row) + f"   {rho:+.2f}")

print()
print("="*80); print("B. FLOOR HEADROOM -- how much room is there to fall?"); print("="*80)
print("mcq chance floor = 0.25 (4 options); open floor ~ 0.0")
print(f"{'set':10} {'model':11} {'form':5} {'acc0':>6} {'floor':>6} {'headroom':>9} {'drop30':>7} {'drop/headroom':>14}")
for qt in ["mcq","open"]:
    floor=0.25 if qt=="mcq" else 0.0
    for m in MODELS:
        for s in ["gold72","strong66","hard95"]:
            a0=[];a30=[]
            for fam in ["omission","mistranslation"]:
                a=cells[(s,m,fam,"0%",qt)]; b=cells[(s,m,fam,"30%",qt)]
                ks=[k for k in a if k in b]
                a0+=[a[k] for k in ks]; a30+=[b[k] for k in ks]
            h=mean(a0)-floor; drop=mean(a0)-mean(a30)
            print(f"{s:10} {m:11} {qt:5} {mean(a0):6.3f} {floor:6.2f} {h:9.3f} {drop:7.3f} {drop/h if h>0 else float('nan'):14.3f}")
        print()

print("="*80); print("C. METHOD CONTRAST -- clean llm_prompt_high vs google_word_by_word"); print("="*80)
print("(a much larger quality gap than a 30% defect dose; same items, paired)")
print(f"{'set':10} {'model':11} {'form':5} {'n':>4} {'clean':>6} {'wbw':>6} {'drop':>6} {'dz':>7}")
for qt in ["mcq","open"]:
    for m in MODELS:
        for s in ["gold72","strong66","hard95"]:
            clean=defaultdict(list)
            for fam in FAMILIES:
                for k,v in cells[(s,m,fam,"0%",qt)].items(): clean[k].append(v)
            w=wbw[(s,m,qt)]
            ks=[k for k in clean if k in w]
            if len(ks)<3: continue
            diffs=[mean(clean[k])-w[k] for k in ks]
            sd=stdev(diffs); dz=mean(diffs)/sd if sd>0 else float("nan")
            print(f"{s:10} {m:11} {qt:5} {len(ks):4d} {mean([mean(clean[k]) for k in ks]):6.3f} {mean([w[k] for k in ks]):6.3f} {mean(diffs):6.3f} {dz:7.3f}")
        print()
