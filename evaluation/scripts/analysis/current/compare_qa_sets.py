#!/usr/bin/env python3
"""Compare QA sets (gold72 / strong66 / hard95) on difficulty and defect sensitivity.

Method follows EXPERIMENT_QA_SET_COMPARISON_2026-08-30.md and is verified to
reproduce its published numbers exactly:
  - accuracy per item: mcq -> direct_correct (0/1), open -> judge llm_score (0-1)
  - items paired against themselves across dose levels (removes item difficulty)
  - open and mcq reported separately (two forms of one question are not
    independent observations -- pooling inflates n)
  - effect size = paired Cohen's dz, because the sets have different n
  - do NOT macro-average over passages: 5 of the 10 have <=7 items

Reads evaluation/outputs/{tier1_bsb,tier1_strong,tier1_hard_v3}. Run from anywhere:
    python3 evaluation/scripts/analysis/current/compare_qa_sets.py
Companion: compare_qa_sets_ladder.py (full 6-dose ladders, floor headroom,
llm_prompt_high vs google_word_by_word method contrast).
"""
import json, math, os, sys
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



ROOT = _outputs_root()
SETS = {"strong66": "tier1_strong", "gold72": "tier1_bsb", "hard95": "tier1_hard_v3"}
MODELS = ["llama321b", "qwen2515b", "qwen317b"]
FAMILIES = ["omission", "mistranslation", "grammar"]
DOSES = ["0%", "5%", "10%", "15%", "20%", "30%"]

scores = defaultdict(dict)
missing = []
for sname, tree in SETS.items():
    base = os.path.join(ROOT, tree)
    for passage in sorted(os.listdir(base)):
        pdir = os.path.join(base, passage)
        if not os.path.isdir(pdir) or not passage.startswith("t1_"):
            continue
        for model in MODELS:
            for fam in FAMILIES:
                for dose in DOSES:
                    fp = os.path.join(pdir, model, fam, dose, "scores_target_llama.json")
                    if not os.path.exists(fp):
                        missing.append(fp); continue
                    d = json.load(open(fp))
                    for it in d.get("items", []):
                        qt = it.get("q_type")
                        v = it.get("direct_correct") if qt == "mcq" else it.get("llm_score")
                        if v is None: continue
                        scores[(sname, model, fam, dose)][(passage, it.get("id"), qt)] = float(v)
sys.stderr.write("missing cells: %d\n" % len(missing))

def mean(xs): return sum(xs)/len(xs) if xs else float("nan")
def stdev(xs):
    n=len(xs)
    if n<2: return float("nan")
    m=mean(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(n-1))
def betacf(a,b,x):
    MAXIT,EPS,FPMIN=200,3e-16,1e-300
    qab,qap,qam=a+b,a+1.0,a-1.0
    c,d=1.0,1.0-qab*x/qap
    if abs(d)<FPMIN: d=FPMIN
    d=1.0/d; h=d
    for m in range(1,MAXIT+1):
        m2=2*m
        aa=m*(b-m)*x/((qam+m2)*(a+m2))
        d=1.0+aa*d
        if abs(d)<FPMIN: d=FPMIN
        c=1.0+aa/c
        if abs(c)<FPMIN: c=FPMIN
        d=1.0/d; h*=d*c
        aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2))
        d=1.0+aa*d
        if abs(d)<FPMIN: d=FPMIN
        c=1.0+aa/c
        if abs(c)<FPMIN: c=FPMIN
        d=1.0/d; de=d*c; h*=de
        if abs(de-1.0)<EPS: break
    return h
def betai(a,b,x):
    if x<=0: return 0.0
    if x>=1: return 1.0
    lbeta=math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)
    bt=math.exp(lbeta+a*math.log(x)+b*math.log(1.0-x))
    if x < (a+1.0)/(a+b+2.0): return bt*betacf(a,b,x)/a
    return 1.0-bt*betacf(b,a,1.0-x)/b
def t_pvalue(t,df):
    if df<=0 or not math.isfinite(t): return float("nan")
    return betai(df/2.0,0.5,df/(df+t*t))

print("="*78)
print("1. DIFFICULTY -- accuracy on the CLEAN (0% dose) text")
print("="*78)
print("   per item, averaged over the 3 independent clean draws (om/mis/gram 0%)")
print()
clean_rows=[]; clean_items={}
for sname in SETS:
    for model in MODELS:
        for qt in ["mcq","open"]:
            per_item=defaultdict(list)
            for fam in FAMILIES:
                for k,v in scores[(sname,model,fam,"0%")].items():
                    if k[2]==qt: per_item[k].append(v)
            vals=[mean(v) for v in per_item.values()]
            clean_items[(sname,model,qt)]=per_item
            if vals: clean_rows.append((sname,model,qt,len(vals),mean(vals),stdev(vals)))
print(f"{'set':10} {'model':11} {'form':5} {'n_items':>7} {'accuracy':>9} {'sd':>7}")
for qt in ["mcq","open"]:
    for model in MODELS:
        for sname in ["gold72","strong66","hard95"]:
            for r in clean_rows:
                if r[:3]==(sname,model,qt):
                    print(f"{r[0]:10} {r[1]:11} {r[2]:5} {r[3]:7d} {r[4]:9.3f} {r[5]:7.3f}")
        print()
print("pooled over the three answer models (item x model observations):")
print(f"{'set':10} {'form':5} {'n_obs':>7} {'accuracy':>9}")
pooled_clean={}
for qt in ["mcq","open"]:
    for sname in ["gold72","strong66","hard95"]:
        vals=[]
        for model in MODELS:
            vals+=[mean(v) for v in clean_items[(sname,model,qt)].values()]
        pooled_clean[(sname,qt)]=mean(vals)
        print(f"{sname:10} {qt:5} {len(vals):7d} {mean(vals):9.3f}")
    print()

print("="*78)
print("2. DISTINGUISHING POWER -- paired 0% -> 30%, item-level")
print("="*78)
print("   dz = mean(clean - dosed) / sd(clean - dosed) over paired items")
print()
sens={}
print(f"{'set':10} {'model':11} {'family':15} {'form':5} {'n':>4} {'acc0':>6} {'acc30':>6} {'drop':>6} {'dz':>7} {'t':>7} {'p':>9}")
for model in MODELS:
    for fam in FAMILIES:
        for qt in ["mcq","open"]:
            for sname in ["gold72","strong66","hard95"]:
                a=scores[(sname,model,fam,"0%")]; b=scores[(sname,model,fam,"30%")]
                keys=[k for k in a if k in b and k[2]==qt]
                if len(keys)<3: continue
                diffs=[a[k]-b[k] for k in keys]
                m,s=mean(diffs),stdev(diffs)
                dz=m/s if s>0 else float("nan")
                n=len(diffs)
                t=dz*math.sqrt(n) if math.isfinite(dz) else float("nan")
                p=t_pvalue(t,n-1)
                sens[(sname,model,fam,qt)]=(n,mean([a[k] for k in keys]),mean([b[k] for k in keys]),m,dz,t,p)
                print(f"{sname:10} {model:11} {fam:15} {qt:5} {n:4d} {mean([a[k] for k in keys]):6.3f} {mean([b[k] for k in keys]):6.3f} {m:6.3f} {dz:7.3f} {t:7.2f} {p:9.4f}")
            print()

print("="*78)
print("3. HEAD TO HEAD: strong66 vs gold72 (dz)")
print("="*78)
print(f"{'model':11} {'family':15} {'form':5} {'gold72':>8} {'strong66':>9} {'hard95':>8}  winner")
wins=defaultdict(int)
for model in MODELS:
    for fam in FAMILIES:
        for qt in ["mcq","open"]:
            g=sens.get(("gold72",model,fam,qt)); s=sens.get(("strong66",model,fam,qt)); h=sens.get(("hard95",model,fam,qt))
            if not (g and s): continue
            gz,sz=g[4],s[4]; hz=h[4] if h else float("nan")
            w="tie" if abs(gz-sz)<0.02 else ("strong66" if sz>gz else "gold72")
            wins[w]+=1
            print(f"{model:11} {fam:15} {qt:5} {gz:8.3f} {sz:9.3f} {hz:8.3f}  {w}")
print()
print("cell wins:",dict(wins))
print()
for label,fams in [("adequacy (omission+mistranslation)",["omission","mistranslation"]),("fluency (grammar)",["grammar"])]:
    for sname in ["gold72","strong66","hard95"]:
        vals=[v[4] for k,v in sens.items() if k[0]==sname and k[2] in fams]
        print(f"mean dz  {label:36} {sname:10} {mean(vals):6.3f}  (n={len(vals)} cells)")
    print()
json.dump({"clean":{"|".join(k):v for k,v in pooled_clean.items()},
           "clean_by_model":[list(r) for r in clean_rows],
           "sens":{"|".join(k):list(v) for k,v in sens.items()}},
          open(os.path.expanduser("~/qa_set_compare_results.json"),"w"),indent=1)
print("wrote ~/qa_set_compare_results.json")
