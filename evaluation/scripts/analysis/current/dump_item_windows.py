import json,os,re

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


P=os.path.join(os.path.dirname(_outputs_root()), "datasets/pseudonymized/passages/tier1_bsb")
DS=os.path.join(os.path.dirname(_outputs_root()), "datasets/pseudonymized/qa/tier1_strong")
MAP={"t1_1kgs13":"1kgs_13_1-34","t1_2chr26":"2chr_26_1-23","t1_2kgs11":"2kgs_11_1-21",
     "t1_2kgs6_7":"2kgs_6_24-7_20","t1_2sam21":"2sam_21_15-22","t1_acts19":"acts_19_11-20",
     "t1_acts20":"acts_20_7-12","t1_acts23":"acts_23_12-35","t1_judg17_18":"judg_17_1-18_31",
     "t1_judg9":"judg_9_1-57"}
def parse(fn):
    stem=fn
    m=re.match(r"^[0-9]?[a-z]+_(\d+)_(\d+)-(?:(\d+)_)?(\d+)$",stem)
    c0,v0=int(m.group(1)),int(m.group(2))
    txt=open(os.path.join(P,stem+".txt")).read()
    blocks=[b.strip() for b in txt.split("\n\n") if b.strip()]
    idx={}; ch=c0; prev=None
    for b in blocks:
        mm=re.match(r"^(\d+)\s+(.*)$",b,re.S)
        n=int(mm.group(1)); body=mm.group(2).strip()
        if prev is None: v=v0
        elif n==prev+1: v=n
        else: ch=n; v=1
        idx[(ch,v)]=body; prev=v
    return idx
IDX={k:parse(v) for k,v in MAP.items()}
for k,v in IDX.items(): print("#",k,"verses parsed:",len(v),"range:",min(v),max(v))
out=[];n=0
for fn in sorted(os.listdir(DS)):
    for it in json.load(open(os.path.join(DS,fn))):
        n+=1
        pid=it["passage_id"]; ch=int(str(it.get("reference","0:0")).split(":")[0])
        wv=it.get("window_verses") or []
        txt=[]
        for v in wv:
            body=IDX[pid].get((ch,v))
            txt.append(f"  v{v}: {body}" if body else f"  v{v}: <MISSING>")
        out.append(f"### [{n}] {pid}/{it['id']}  ref {it.get('reference')}\nQ: {it['question']}\nA: {it['answer']}\nWINDOW ({ch}:{wv}):\n"+"\n".join(txt))
open(os.path.expanduser("~/win66.txt"),"w").write("\n\n".join(out))
print("wrote", n, "items")
