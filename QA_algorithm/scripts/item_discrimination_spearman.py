#!/usr/bin/env python3
"""
Per-item Spearman: does each question detect translation quality?

For every item, correlate (across the 8 translation methods):
  x = method's GLOBAL quality rank (from consensus ranking, 1=worst..8=best)
  y = method's score ON THIS ITEM, averaged over the 3 answer models
      (open=llm_score, mcq=1/0; mean of 3 -> {0,1/3,2/3,1}, reduces ties)
rho close to +1  -> item tracks translation quality well  (good QC probe)
rho near 0       -> item insensitive to translation quality (noise/too easy/too hard)
rho negative     -> perverse: worse translations score higher on this item

Only items with >=5 methods present AND non-degenerate y (some variance) get a rho.
Writes reports/item_discrimination_spearman.{csv,md}
"""
import json, os, csv, statistics
from datetime import date

HERE=os.path.dirname(os.path.abspath(__file__)); REPO=os.path.dirname(os.path.dirname(HERE))
OUT=os.path.join(REPO,"evaluation","outputs")  # answer-score inputs stay under evaluation/
ROOT=os.path.join(REPO,"QA_algorithm","outputs","reports"); REPORTS=os.path.join(ROOT,"item_level_grid_analysis")
METHODS=["google_word_by_word","mBART-50","helsinki","nllb-200-distilled-600M",
         "llm_prompt_low","llm_prompt_medium","nllb-200-1.3B","llm_prompt_high"]
MODELS={"llama 1b":"llama1b","1.5b":"qwen1.5b","1.7b":"qwen1.7b"}
LABELS=list(MODELS.values()); CHAPTERS=[f"luke{i}" for i in range(1,9)]

# global quality rank (1=worst..8=best) from consensus json if present, else recompute order
GLOBAL_ORDER=["google_word_by_word","mBART-50","helsinki","nllb-200-distilled-600M",
              "llm_prompt_low","llm_prompt_medium","nllb-200-1.3B","llm_prompt_high"]
cj=os.path.join(ROOT,"method_ranking_consensus.json")
if os.path.exists(cj):
    d=json.load(open(cj))
    GLOBAL_ORDER=[r["method"] for r in sorted(d["consensus_ranking"],key=lambda r:r["consensus"])]
QRANK={m:i+1 for i,m in enumerate(GLOBAL_ORDER)}

def item_scores(path):
    d={}
    for it in json.load(open(path))["items"]:
        if it["q_type"]=="mcq": d[it["id"]]=(it["q_type"],it.get("question",""),
            it.get("passage_reference",""),1.0 if it.get("direct_correct") else 0.0)
        else:
            s=it.get("llm_score")
            if s is not None: d[it["id"]]=(it["q_type"],it.get("question",""),
                it.get("passage_reference",""),s)
    return d

def spearman(xs,ys):
    # average-rank Spearman with tie handling
    def rank(v):
        order=sorted(range(len(v)),key=lambda i:v[i])
        r=[0]*len(v); i=0
        while i<len(v):
            j=i
            while j+1<len(v) and v[order[j+1]]==v[order[i]]: j+=1
            avg=(i+j)/2+1
            for k in range(i,j+1): r[order[k]]=avg
            i=j+1
        return r
    rx,ry=rank(xs),rank(ys); n=len(xs)
    mx=sum(rx)/n; my=sum(ry)/n
    num=sum((rx[i]-mx)*(ry[i]-my) for i in range(n))
    den=(sum((rx[i]-mx)**2 for i in range(n))*sum((ry[i]-my)**2 for i in range(n)))**.5
    return num/den if den else None

# collect per-item method-mean scores
items={}  # (chapter,id) -> {meta, method-> mean score}
meta={}
for ch in CHAPTERS:
    per={}
    for md,lab in MODELS.items():
        for meth in METHODS:
            p=f"{OUT}/{ch}/{md}/{meth}/scores_target_llama.json"
            if not os.path.exists(p): continue
            for iid,(qt,q,ref,s) in item_scores(p).items():
                per.setdefault(iid,{}).setdefault(meth,[]).append(s)
                meta[(ch,iid)]=(qt,ref,q)
    for iid,mm in per.items():
        items[(ch,iid)]={me:statistics.mean(v) for me,v in mm.items()}

rows=[]
for (ch,iid),mm in items.items():
    present=[me for me in METHODS if me in mm]
    if len(present)<5: continue
    ys=[mm[me] for me in present]
    if len(set(ys))<2: 
        rho=None; note="degenerate (all methods tie)"
    else:
        xs=[QRANK[me] for me in present]
        rho=spearman(xs,ys); note=""
    qt,ref,q=meta[(ch,iid)]
    rows.append({"chapter":ch,"item_id":iid,"reference":ref,"q_type":qt,
                 "n_methods":len(present),"mean_score":round(statistics.mean(ys),3),
                 "rho":"" if rho is None else round(rho,3),"note":note,"question":q})

# sort by rho desc (blanks last)
rows.sort(key=lambda r:(r["rho"]=="", -(r["rho"] if r["rho"]!="" else 0)))
os.makedirs(REPORTS,exist_ok=True)
with open(f"{REPORTS}/item_discrimination_spearman.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["chapter","item_id","reference","q_type",
        "n_methods","mean_score","rho","note","question"]); w.writeheader(); w.writerows(rows)

valid=[r["rho"] for r in rows if r["rho"]!=""]
pos=[r for r in valid if r>0.5]; neg=[r for r in valid if r<-0.3]; flat=[r for r in valid if -0.3<=r<=0.3]
md=[f"# Per-item discrimination (Spearman of item-score vs translation-quality rank)\n",
    f"_Generated {date.today()}_\n",
    "For each item, rho correlates the 8 methods' **global quality rank** with the item's "
    "**score under each method** (mean of 3 answer models). High +rho = the question detects "
    "translation quality; ~0 = insensitive; negative = perverse.\n",
    f"**Items scored:** {len(rows)}  |  with a computable rho: {len(valid)}  |  "
    f"degenerate (all-tie): {len(rows)-len(valid)}\n",
    f"**Distribution:** strong probes (rho>0.5): {len(pos)}  |  "
    f"flat (-0.3..0.3): {len(flat)}  |  perverse (rho<-0.3): {len(neg)}\n",
    f"**Mean rho (computable items):** {round(sum(valid)/len(valid),3) if valid else 'NA'}  |  "
    f"**median:** {round(statistics.median(valid),3) if valid else 'NA'}\n",
    "\n## Top 15 discriminating items\n",
    "| chapter | item | ref | type | rho | mean | question |","|---|---|---|---|---|---|---|"]
for r in rows[:15]:
    md.append(f"| {r['chapter']} | {r['item_id']} | {r['reference']} | {r['q_type']} | "
              f"{r['rho']} | {r['mean_score']} | {r['question'][:40]} |")
md+=["\n## Most perverse (negative rho) — worse translations scored higher\n",
     "| chapter | item | ref | rho | mean | question |","|---|---|---|---|---|---|"]
for r in [x for x in rows if x['rho']!='' and x['rho']<0][:10]:
    md.append(f"| {r['chapter']} | {r['item_id']} | {r['reference']} | {r['rho']} | "
              f"{r['mean_score']} | {r['question'][:40]} |")
md+=["\n## Caveats\n",
 "- Item score per method is the mean of 3 models -> values in {0,1/3,2/3,1}; still tie-prone, "
 "so single-item rho is noisy. Read the **distribution**, not any one item.\n",
 "- Many items are near ceiling (mean_score high) -> no variance across methods -> degenerate, "
 "no rho. Those items are poor QC probes by construction.\n",
 "- Quality rank is the global consensus ranking; if that ordering is noisy, item rho inherits it.\n"]
open(f"{REPORTS}/item_discrimination_spearman.md","w").write("\n".join(md)+"\n")
print(f"items:{len(rows)} computable_rho:{len(valid)} mean_rho:"
      f"{round(sum(valid)/len(valid),3) if valid else 'NA'} "
      f"pos>0.5:{len(pos)} flat:{len(flat)} neg<-0.3:{len(neg)}")
