import json,os,csv
from collections import defaultdict,Counter

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


DS=os.path.join(os.path.dirname(_outputs_root()), "datasets/pseudonymized/qa/tier1_strong")
R=os.path.expanduser("~/mnt/eten-research-outputs/evaluation/outputs/tier1_strong")
V={  # id -> (flag, note)   flag "" = clean
"0887":("WINDOW","'who will kill' also matches the lion in v24-26 once the whole chapter is in context"),
"ec63":("STEM","'Whose body is warned will not be buried with family?' is ungrammatical"),
"9a0c":("MCQ2","distractor 'the prophet' also denotes Ledas; pseudonym turned 'man of God' into a name"),
"e302":("STEM","open stem 'What does Vuvur not do?' is unbounded without the options"),
"723e":("AMBIG","v11 puts the army under Metun; v12-13 under the 2,600 leaders - both defensible"),
"1fc4":("STEM","'Whose love of soil explains the farm work?' is contorted"),
"1cab":("TEXT","answer says 'the Betuth in Verin'; the passage says 'Gur-baal' - answer not in text"),
"df0e":("AMBIG","v16 has Tiva put to the sword too; 'the woman being taken out' is defensible"),
"5bea":("VOCAB","answer/options say 'companies'; the passage says 'divisions' and 'a third of you'"),
"a99f":("STEM","circular: asks who hid with 'Kanoth's son's nurse' when the answer IS Kanoth's son"),
"fe00":("WEAKD","'yesterday'/'next week' are not live options; effectively a coin flip"),
"6138":("MCQ2","two options both describe v15; answer says 'messengers', text says 'scouts'"),
"c343":("WINDOW","'the doubt' has no referent once the window is dropped; models answered about the king"),
"3452":("VOCAB","answer 'royal palace' vs text 'king's household'; option B breaks tense parallelism"),
"5bba":("TEXT","answer 'the Hittite and Rusol'; passage says 'the Seson and Rusol' - and 'Hittite' is a canonical leak"),
"9b0c":("VOCAB","question/options say 'scrolls'; the passage says 'books'"),
"9b52":("MCQ2","'He eats bread' is also in v11, immediately before departure"),
"2b9c":("TEXT","pseudonymizer turned 'two of his centurions' into 'centurion' - the answer is not in the text"),
"058f":("AMBIG","option says 'cavalry', text says 'horsemen'; scope of 'they' in v32 is arguable"),
"c60a":("STEM","'the Meses' - article plus invented proper name, an artifact of pseudonymizing a common noun"),
"3162":("WINDOW","the 'five men' antecedent is v17, outside the item's own window; v20 has the priest take them"),
"616b":("MCQ2","v22 overtaking and v23 shouting are both in the text; options A and D are both defensible"),
"725d":("AMBIG","v5 says 'inquire of God', so the distractor 'God' is a live reading of the stem"),
"e935":("WINDOW","chapter contains an earlier ambush (v25); models answered from that one"),
"f36a":("STEM","'In response to Birel's first claim what are they said to be instead?' is barely parseable"),
"0bd2":("MCQ2","'To attack the tower' is verbatim in v52 alongside 'to set it on fire'"),
"79d0":("WINDOW","two different towers in the chapter (v46-49 fire, v50-53 millstone); stem does not say which"),
}
acc=defaultdict(list)
for p in sorted(os.listdir(R)):
    if not p.startswith("t1_"): continue
    for m in ["llama321b","qwen2515b","qwen317b"]:
        for fam in ["omission","mistranslation","grammar"]:
            f=os.path.join(R,p,m,fam,"0%","scores_target_llama.json")
            if not os.path.exists(f): continue
            for it in json.load(open(f)).get("items",[]):
                qt=it.get("q_type"); v=it.get("direct_correct") if qt=="mcq" else it.get("llm_score")
                if v is not None: acc[(it["id"],qt)].append(float(v))
def mean(x): return sum(x)/len(x) if x else None
rows=[];n=0
for fn in sorted(os.listdir(DS)):
    for it in json.load(open(os.path.join(DS,fn))):
        n+=1
        base=f"uw-{it['passage_id']}:{it['id']}"
        o=mean(acc.get((base+"-open","open"),[])); q=mean(acc.get((base+"-mcq","mcq"),[]))
        flag,note=V.get(it["id"],("",""))
        rows.append(dict(n=n,passage=it["passage_id"],id=it["id"],ref=it.get("reference"),
                         question=it["question"],answer=str(it["answer"]),
                         open_acc=round(o,3) if o is not None else "", mcq_acc=round(q,3) if q is not None else "",
                         flag=flag,note=note))
c=Counter(r["flag"] or "OK" for r in rows)
print("VERDICT COUNTS:",dict(c))
print(f"clean {c['OK']}/66 = {100*c['OK']/66:.0f}%   flagged {66-c['OK']}/66 = {100*(66-c['OK'])/66:.0f}%")
print()
for grp,label in [(lambda r: r["flag"]=="", "clean items"),(lambda r: r["flag"]!="", "flagged items")]:
    sel=[r for r in rows if grp(r)]
    oo=[r["open_acc"] for r in sel if r["open_acc"]!=""]; mm=[r["mcq_acc"] for r in sel if r["mcq_acc"]!=""]
    print(f"{label:15} n={len(sel):2d}   mean clean-text acc:  open {mean(oo):.3f}   mcq {mean(mm):.3f}")
print()
print("per-flag mean accuracy:")
for f in ["","WINDOW","STEM","AMBIG","MCQ2","TEXT","VOCAB","WEAKD"]:
    sel=[r for r in rows if r["flag"]==f]
    if not sel: continue
    oo=[r["open_acc"] for r in sel if r["open_acc"]!=""]; mm=[r["mcq_acc"] for r in sel if r["mcq_acc"]!=""]
    print(f"  {(f or 'OK'):8} n={len(sel):2d}  open {mean(oo):.3f}  mcq {mean(mm):.3f}")
out=os.path.expanduser("~/mnt/Bible Translation/STRONG66_ITEM_AUDIT_2026-09-10.csv")
with open(out,"w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("\nwrote",out)
