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
TXT={k:open(os.path.join(P,v+".txt")).read() for k,v in MAP.items()}
COMMON=set("The A An In On At He She It They We You I And But For So Then Now When While Because Since After Before Who Whom What Where Why How This That These Those Sovereign LORD Lord God Gate Valley Corner Sabbath Testimony Treason Oh Bring Seize Intercede Come Saddle Leave Only Under Each Even Surely Indeed His Her Their Its Suddenly Long Return Went Stay Go Whose Which Being".split())
print("=== A. proper nouns in Q/A that never appear in the passage ===")
bad=0
for fn in sorted(os.listdir(DS)):
    for it in json.load(open(os.path.join(DS,fn))):
        pid=it["passage_id"]; txt=TXT[pid]
        blob=it["question"]+" "+it["answer"]
        mcq=it.get("mcq",{}).get("mcq_options") or []
        if isinstance(mcq,list): blob+=" "+" ".join(str(x) for x in mcq)
        names={w for w in re.findall(r"\b[A-Z][a-z]{2,}\b",blob)} - COMMON
        miss=sorted(n for n in names if not re.search(r"\b"+re.escape(n),txt,re.I))
        if miss:
            bad+=1
            print(f"  {pid}/{it['id']}: {miss}   | Q: {it['question'][:60]}")
print(f"  -> {bad}/66 items reference a name absent from their passage\n")

print("=== B. pseudonymization damage in the CLEAN passage text ===")
PAT=[(r"\bthe Sovereign his the Sovereign\b","doubled substitution"),
     (r"\b(the|a|an)\s+(the|a|an)\b","doubled article"),
     (r"(?<![.!?\"'“‘]\s)(?<!^)\b(?:timil|ledas|meses|besur|tadul|terin|kireth|visas|tiva|sadon|derur|tilir)\b","lowercase name mid-text"),
     (r"\bthe Sovereign\s+the Sovereign\b","repeat"),
     (r"\bhe sought the Sovereign gave him\b","dropped subject")]
tot=0
for pid,txt in TXT.items():
    for pat,label in PAT:
        for m in re.finditer(pat,txt,re.M):
            s=max(0,m.start()-55); print(f"  {pid} [{label}] ...{txt[s:m.end()+45].strip()}..."); tot+=1
print(f"  -> {tot} damaged spans in the clean (0% dose) base text")
