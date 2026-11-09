"""Replay historical blind selection with frozen prompts and a passage-level holdout."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import time

from openai import OpenAI

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics.audit_hard66_answerability import atomic_write, read
from evaluation.scripts.mcq.diagnostics.audit_hard66_selection import passage_reference

SOURCE = REPO / "evaluation/reports/hard66_selection_answerability_2026-11-07/answerability.json"
OUTPUT = REPO / "evaluation/reports/hard66_selector_experiment_2026-11-07"
HISTORICAL_CHAT = "01a01108-19fa-7382-b032-96e2e0403cc6"
ARTIFACT = "https://claude.ai/epitaxy/artifact/KE19Ma4JwD58oVfqs8mcst"
REQUEST = "can you get the strong QAs from all the passages"
CONTEXT = (
    "Pipeline generates and scores candidates. Give me the kept output plus passage windows. "
    "Return only genuinely strong candidates, checking naturalness, self-containment, answer "
    "completeness, and discriminating value. Exclude items that are vague, unnatural, incidental, "
    "duplicate another survivor, or are unlikely to distinguish answerers. Judge each concept "
    "as written. An otherwise good QA can survive a metadata correction."
)
PROMPTS = {
    "original_request": REQUEST,
    "historical_context": REQUEST + "\n\nEarlier selection criteria:\n" + CONTEXT,
    "luke_examples": REQUEST + "\n\n" + CONTEXT + """
Examples from a different passage used in the earlier discussion: identifying whom Simeon
asks God to dismiss and distinguishing the host from the angel as speaker were strong.
Naming a bird, redirecting a crowd's reaction from an act to a person, or relying on an
unnamed speaker were weak. Use these principles even when an answer happens to be a name.
Notice when vague synonyms introduced just to avoid giving clues make a simple event obscure.""",
    "claude_artifact_rubric": """Select questions that demand a relational inference about the passage.
Assess four dimensions: structure dependence, uniqueness of the statement, answer certainty
and centrality. Would an error in participant, agent, cause, sequence, scope or reference
change the answer? How plausible is the competing answer under a misreading? Choose the
best probes across these four dimensions, giving greatest weight to structural dependence.""",
    "ordinary_reader": """Edit an open-response comprehension test for ordinary readers who have
never encountered these stories. Try answering from each exact excerpt. Check whether an
unprompted reader understands the question on first reading, can give one complete answer
in everyday words and can see exactly why it is right. Give full credit to paraphrases and
co-referring labels. Penalize reverse-engineered wording, author-only referents, vague answer
keys and artificial difficulty. Prefer a real comprehension task over trivial retrieval.""",
    "damaged_translation": """Curate items for detecting meaning lost in translation. Compare a
careful reading to one in which a key relation is damaged while the passage words and names
survive. Is there a specific plausible incorrect answer under the damaged reading? Could a
reader shortcut the question using a single token, general knowledge or common sense?
Keep only natural, unambiguous, substantial questions that a clean reader can answer and
that make those two readers diverge. Reject strained contrasts and incidental details.""",
    "editorial_panel": """Examine each item from three perspectives: a participant trying to parse
the stem naturally, a grader deciding which open responses count, and an editor choosing what
is worth testing. Resolve disagreements using the exact window. Reward a clear, important
distinction about this event. Cut opaque generic stand-ins, empty or circular keys, duplicate
concepts, arbitrary sequence boundaries, easy word spotting and forced Bible-quiz wording.
Meaningful direct questions can be strong. For each item name the decisive strength or flaw.""",
}
MODELS = {"original_low": ("gpt-5.6-sol", "low"), "original_high": ("gpt-5.6-sol", "high"),
          "sol_high": ("gpt-6.1-sol", "high"), "astra_high": ("gpt-6-astra", "high")}
SPLITS = ("development", "holdout")
COMMON = """These are candidates for a Bible-translation comprehension study. Use only the supplied materials.
The competing answer is a proposed misreading. Rate each question's suitability as written on
a common 0–1000 scale, higher means stronger. Spread scores enough to rank closely matched
questions. Give each item one short concrete reason. Do not change the items or drop rows.
Return JSON only: {"items":[{"id":"opaque ID","score":integer,"why":"short reason"}]}."""
SCHEMA = {"type":"object","properties":{"items":{"type":"array","items":{"type":"object",
          "properties":{"id":{"type":"string"},"score":{"type":"integer"},"why":{"type":"string"}},
          "required":["id","score","why"],"additionalProperties":False}}},
          "required":["items"],"additionalProperties":False}

def save(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def load_data():
    audit = read(SOURCE)
    root = Path(audit["source"]) / "tier1_hard_v3"
    items, history = {}, {}
    for r in audit["items"]:
        k = "Q" + digest(r["id"])[:5].upper()
        src = next(x for x in read(root / (r["passage"] + ".json")) if x["content_id"] == r["source_id"])
        assert (src["question"], src["answer"], src["window_text"]) == (r["question"], r["answer"], r["window"])
        assert k not in history
        history[k] = dict(r, split="holdout" if r["passage"].startswith("judg_") else "development")
        items[k] = {"id": k, "window": " ".join(v for _,v in sorted(r["window"].items(), key=lambda p:int(p[0]))),
                    "question":r["question"], "key":r["answer"], "competitor":src["wrong_answer"]}
    return items, history

def validate(data, ids):
    rows = data["items"]
    if len(rows) != len(ids) or {r["id"] for r in rows} != set(ids):
        raise ValueError("IDs missing, duplicated or unexpected")
    if any(type(r["score"]) is not int or not 0 <= r["score"] <= 1000
           or not isinstance(r["why"],str) or not r["why"].strip() for r in rows):
        raise ValueError("Invalid score or empty reason")
    return rows

def prepare():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    items, history = load_data()
    plan = {"prompts":PROMPTS, "common_instructions":COMMON, "models":MODELS,
            "claude_panel":["historical_context","editorial_panel"],
            "development":"All source passages except Judges", "holdout":"All three source passages from Judges",
            "metric":"Removal F1, then balanced accuracy; lexicographic model/prompt as final tie-break.",
            "quota":"Reject round(19/85 * split size) per split. For the full-bank reconstruction reject the 19 lowest absolute scores. Ties use opaque ID.",
            "source_chat":HISTORICAL_CHAT,"claude_artifact":ARTIFACT,"batches":{}}
    batches={}
    for split in SPLITS:
        ordered = sorted(k for k,r in history.items() if r["split"] == split)
        random.Random(20261107).shuffle(ordered)
        payload = [items[k] for k in ordered]
        plan["batches"][split] = digest(json.dumps(payload, ensure_ascii=False))
        batches[split]=payload
    p = OUTPUT / "design.json"
    if p.exists() and read(p) != json.loads(json.dumps(plan)):
        raise ValueError("Experiment design has changed. Use a fresh output directory.")
    for split,payload in batches.items():
        path=OUTPUT/(split+"_blinded.json")
        if path.exists() and read(path)!=payload:
            raise ValueError(f"Saved input changed: {path}")
        if not path.exists():save(path,payload)
    if not p.exists():save(p,plan)
    (OUTPUT / "responses").mkdir(exist_ok=True)

def run_case(client, label, name, split, repeat_seed=None, *, prompt_text=None, output_root=None):
    model, effort = MODELS[label]
    target = (output_root or OUTPUT) / ("responses" if repeat_seed is None else f"repeats/order_{repeat_seed}")
    target.mkdir(parents=True,exist_ok=True)
    path = target / f"{label}__{name}__{split}.json"
    inputs = read(OUTPUT / (split + "_blinded.json"))
    if repeat_seed is not None:
        random.Random(repeat_seed).shuffle(inputs)
    ids = [r["id"] for r in inputs]
    if path.exists():
        validate(read(path),ids)
        return
    for attempt in range(3):
        try:
            res = client.responses.create(model=model,reasoning={"effort":effort},store=False,
                instructions=(PROMPTS[name] if prompt_text is None else prompt_text)+"\n\n"+COMMON,
                input=json.dumps(inputs,ensure_ascii=False),
                text={"format":{"type":"json_schema","name":"curation","strict":True,"schema":SCHEMA}},
                max_output_tokens=20000)
            if res.status != "completed":
                raise ValueError(f"incomplete response: {res.status}")
            rows = validate(json.loads(res.output_text),ids)
            save(path,dict(items=rows,model=res.model,effort=effort,response_id=res.id,
                           usage=res.usage.model_dump() if res.usage else {},prompt=name,split=split,
                           repeat_seed=repeat_seed))
            print(label,name,split,"complete",flush=True)
            return
        except Exception as exc:
            print(label,name,split,type(exc).__name__,str(exc)[:220],flush=True)
            if attempt==2:raise
            time.sleep(2**attempt)

def score(ids, pred, history):
    removed={k for k in ids if history[k]["historical"]=="removed"}
    tp=len(removed & pred); fp=len(pred-removed); fn=len(removed-pred); tn=len(ids)-tp-fn-fp
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,agreement=tp+tn,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
                balanced=(tp/len(removed)+tn/(len(ids)-len(removed)))/2)

def predicted(rows):
    ordered=sorted(rows,key=lambda r:(r["score"],r["id"]))
    return {r["id"] for r in ordered[:round(len(ordered)*19/85)]}

def table(path, rows):
    buf=io.StringIO()
    writer=csv.DictWriter(buf,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows);atomic_write(path,buf.getvalue())


def replicate(workers):
    _, history = load_data()
    controls = read(OUTPUT/"replication_plan.json")
    configs = []
    for model in MODELS:
        for name in PROMPTS:
            path = OUTPUT/"responses"/f"{model}__{name}__development.json"
            rows = read(path)["items"]
            ids = {k for k in history if history[k]["split"]=="development"}
            validate({"items":rows}, ids)
            metrics = score(ids,predicted(rows),history)
            configs.append((-metrics["f1"],-metrics["balanced"],model,name))
    finalists = [(m,n) for _,_,m,n in sorted(configs)[:2]]
    save(OUTPUT/"replication_finalists.json",finalists)
    client=OpenAI(timeout=600,max_retries=2)
    with ThreadPoolExecutor(workers) as ex:
        jobs=[ex.submit(run_case,client,m,n,s,seed) for m,n in finalists
              for seed in controls["seeds"] for s in SPLITS]
        for job in as_completed(jobs): job.result()
    records=[]
    for m,n in finalists:
        original=full_predictions(OUTPUT/"responses",m,n)
        for seed in controls["seeds"]:
            flags=full_predictions(OUTPUT/"repeats"/f"order_{seed}",m,n)
            records.append(dict(model=m,prompt=n,order_seed=seed,
                                same_decision_as_first=len(history)-len(flags ^ original),
                                **score(set(history),flags,history)))
    table(OUTPUT/"repeat_stability.csv",records)


def full_predictions(directory,model,name):
    rows=[r for split in SPLITS for r in read(directory/f"{model}__{name}__{split}.json")["items"]]
    return predicted(rows)


def repeated_selections(history):
    final_path=OUTPUT/"replication_finalists.json"
    if not (OUTPUT/"repeat_stability.csv").exists() or not final_path.exists():
        return []
    seeds=read(OUTPUT/"replication_plan.json")["seeds"]
    directories=[OUTPUT/"responses"]+[OUTPUT/"repeats"/f"order_{s}" for s in seeds]
    summary=[];details=[]
    for model,name in read(final_path):
        ranks={k:[] for k in history}
        runs=[]
        for directory in directories:
            items=[r for split in SPLITS for r in read(directory/f"{model}__{name}__{split}.json")["items"]]
            ordered=sorted(items,key=lambda r:(r["score"],r["id"]))
            for j,r in enumerate(ordered,1):ranks[r["id"]].append(j)
            runs.append(score(set(history),{r["id"] for r in ordered[:19]},history)["agreement"])
        # Three draws. Median position is primary, with mean position and opaque ID for ties.
        cut=set(sorted(history,key=lambda k:(sorted(ranks[k])[1],sum(ranks[k]),k))[:19])
        row=dict(model=model,prompt=name,first=runs[0],repeat_1=runs[1],repeat_2=runs[2],
                 mean_matches=round(sum(runs)/len(runs),2),median_rank_matches=score(set(history),cut,history)["agreement"])
        summary.append(row)
        for k,h in history.items():
            pred="removed" if k in cut else "retained"
            details.append(dict(model=model,prompt=name,reference=passage_reference(h),question=h["question"],
                                historical=h["historical"],median_rank_decision=pred,
                                agrees=(pred==h["historical"]),removal_votes=sum(i<=19 for i in ranks[k]),
                                source_id=h["id"]))
    table(OUTPUT/"repeat_summary.csv",summary)
    table(OUTPUT/"repeat_decisions.csv",details)
    return summary


def comparison_html(history,settings,full_rows,winner,best_all):
    """Portable, offline drilldown from any configuration to its exact disagreements."""
    def key(pair):
        return "/".join(pair)
    data={}
    for pair,(rows,flags) in full_rows.items():
        label,name=pair
        data[key(pair)]=dict(model=" ".join(MODELS[label]),prompt=name,text=PROMPTS[name],metrics=settings[pair],
            items=[dict(ref=passage_reference(history[r["id"]]),q=history[r["id"]]["question"],
                        a=history[r["id"]]["answer"],source=history[r["id"]]["historical"],
                        model="removed" if r["id"] in flags else "retained",score=r["score"],
                        why=r["why"],split=history[r["id"]]["split"],
                        window=" ".join(history[r["id"]]["window"].values())) for r in rows])
    doc="""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hard66 selection experiment</title><style>
*{box-sizing:border-box}body{margin:0;color:#172d37;background:#f8f8f3;font:16px/1.5 system-ui,sans-serif}
main{max-width:1080px;margin:auto;padding:36px 22px 60px}h1{font:600 clamp(2rem,5vw,3.5rem)/1.1 Georgia,serif;margin:0 0 12px}
h2{font:600 1.15rem/1.4 Georgia,serif;margin:.6rem 0}a{color:#125b70}header{border-bottom:2px solid #254c57;padding-bottom:20px}
label{display:flex;flex-direction:column;gap:5px;font-weight:600}select{max-width:100%;background:white;padding:8px;font:inherit;border:1px solid #68838a;border-radius:4px}
section.controls{display:flex;flex-wrap:wrap;gap:16px;align-items:end;margin:24px 0 12px}article{background:white;border:1px solid #d0dad7;border-radius:6px;padding:14px 19px;margin:10px 0}p{margin:.35rem 0}.meta,summary{font-size:.9rem;color:#375c63}summary{cursor:pointer}pre{white-space:pre-wrap;font:inherit}strong{font-weight:650}
</style><main><header><h1>Reproducing Hard66</h1><p id="intro"></p>
<a href="review.md">Full leaderboard</a> · <a href="provenance.md">Historical prompt</a> · <a href="all_item_decisions.csv">Decision matrix</a></header>
<section class="controls"><label>Prompt and model<select id="case"></select></label>
<label>Questions<select id="filter"><option value="different">All disagreements</option><option value="removed">Model removed, originally retained</option><option value="retained">Model retained, originally removed</option><option value="all">All 85</option></select></label></section>
<p id="stats"></p><details><summary>Read the selection prompt</summary><pre id="prompt"></pre></details>
<h2 id="count"></h2><div id="questions"></div></main>
<script id="results" type="application/json">__DATA__</script><script>
const db=JSON.parse(document.getElementById("results").textContent), field=id=>document.getElementById(id);
const label=k=>db.cases[k].model+" · "+db.cases[k].prompt;
field("intro").textContent="Development winner: "+label(db.winner)+". Highest agreement on the full bank: "+label(db.best)+".";
for(const k of Object.keys(db.cases).sort()){field("case").add(new Option(label(k),k));}field("case").value=db.winner;
function elem(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;}
function draw(){const v=db.cases[field("case").value],f=field("filter").value,m=v.metrics;
field("stats").textContent="Full bank: "+m.full.agreement+"/85 matched · "+m.full.tp+"/19 historical removals found · Held-out Judges: "+m.holdout.agreement+"/31 matched.";
field("prompt").textContent=v.text;
const xs=v.items.filter(r=>f==="all"||(r.source!==r.model&&(f==="different"||f===r.model))).sort((a,b)=>a.score-b.score);
field("count").textContent=xs.length+" questions";const target=field("questions");target.replaceChildren();
for(const r of xs){const card=document.createElement("article");card.append(elem("p",r.ref+" · "+r.split+" · Historical: "+r.source+" · Model: "+r.model+" ("+r.score+"/1000)","meta"),elem("h2",r.q),elem("p","Key: "+r.a),elem("p",r.why));const d=document.createElement("details");d.append(elem("summary","Read the original window"),elem("p",r.window));card.append(d);target.append(card);}}
field("case").onchange=draw;field("filter").onchange=draw;draw();</script></html>"""
    blob=json.dumps(dict(cases=data,winner=key(winner),best=key(best_all)),ensure_ascii=False).replace("<","\\u003c")
    atomic_write(OUTPUT/"compare.html",doc.replace("__DATA__",blob))

def report():
    _,history=load_data()
    grid={}
    for path in sorted((OUTPUT/"responses").glob("*.json")):
        model,name,split=path.stem.split("__")
        ids=[k for k in history if history[k]["split"]==split]
        data=read(path);rows=validate(data,ids)
        grid.setdefault((model,name),{})[split]=rows
    # Eligibility is the frozen, fully crossed panel of OpenAI configurations.
    # Preserve separately collected baselines, including incomplete ones.
    complete={k:v for k,v in grid.items() if k[0] in MODELS and set(v)==set(SPLITS)}
    if not complete:raise ValueError("No completed configurations")
    settings={}; full_rows={}; all_cases=[]
    for (model,name),splits in complete.items():
        for split, rows in dict(splits,full=splits["development"]+splits["holdout"]).items():
            flags=predicted(rows);ids={r["id"] for r in rows}
            counts=score(ids,flags,history)
            settings.setdefault((model,name),{})[split]=counts
            if split=="full":full_rows[model,name]=rows,flags
            cut=min(r["score"] for r in rows if r["id"] not in flags)
            boundary=[r for r in rows if r["score"]==cut]
            tie_decisions=sum(r["id"] in flags for r in boundary)
            all_cases.append(dict(model=model,model_id=MODELS[model][0],effort=MODELS[model][1],
                                  prompt=name,split=split,ties_removed_by_id=tie_decisions,**counts))
    def ordered_by(split):
        return sorted(settings,key=lambda k:(-settings[k][split]["f1"],-settings[k][split]["balanced"],k))
    winner=ordered_by("development")[0]
    table(OUTPUT/"leaderboard.csv",all_cases)
    def detail(key):
        rows,flags=full_rows[key]
        return [dict(reference=passage_reference(history[r["id"]]), historical=history[r["id"]]["historical"],
                     model_decision="remove" if r["id"] in flags else "retain",
                     question=history[r["id"]]["question"],answer=history[r["id"]]["answer"],
                     score=r["score"],reason=r["why"],source_id=history[r["id"]]["id"],id=r["id"])
                for r in sorted(rows,key=lambda r:(r["score"],r["id"]))]
    def mismatches(rows):
        return [r for r in rows if (r["model_decision"]=="remove")!=(r["historical"]=="removed")]
    best_all=ordered_by("full")[0]
    comparison_html(history,settings,full_rows,winner,best_all)
    for suffix,key in [("development_winner",winner),("full_bank_best",best_all)]:
        rows=detail(key);table(OUTPUT/(suffix+"_all.csv"),rows)
        diffs=mismatches(rows)
        if diffs:table(OUTPUT/(suffix+"_disagreements.csv"),diffs)
    summary={"cases":len(complete),"development_winner":list(winner),"development_ties":
             [list(k) for k in ordered_by("development") if settings[k]["development"]==settings[winner]["development"]],
             "winner_metrics":settings[winner],"best_full":list(best_all),"best_full_metrics":settings[best_all],
             "best_full_ties":[list(k) for k in ordered_by("full") if settings[k]["full"]==settings[best_all]["full"]]}
    supplement=[]
    for (model,name),splits in grid.items():
        if model in MODELS:continue
        for split,rows in splits.items():
            ids={r["id"] for r in rows}
            supplement.append(dict(model=model,prompt=name,split=split,n=len(ids),
                                   **score(ids,predicted(rows),history)))
    if supplement:
        table(OUTPUT/"supplemental_runs.csv",supplement)
    save(OUTPUT/"summary.json",summary)
    decisions=[]
    for k,h in history.items():
        votes={f"{m}/{p}":("remove" if k in full_rows[m,p][1] else "retain")
               for m,p in sorted(full_rows)}
        count=sum(v=="remove" for v in votes.values())
        decisions.append(dict(reference=passage_reference(h),question=h["question"],key=h["answer"],
                              historical=h["historical"],remove_votes=count,total=len(votes),
                              source_id=h["id"],**votes))
    table(OUTPUT/"all_item_decisions.csv",sorted(decisions,key=lambda v:(-v["remove_votes"],v["source_id"])))
    lines=["# Reproducing the original 85-to-66 selection","",
           f"Tested {len(complete)} complete prompt and model configurations. Each scored all 85 original English questions against its original passage, key and proposed competitor. Opaque IDs and randomized order hid the original decision and rank. Whole books were separated before choosing a winner.",
           "",f"The development winner was **{MODELS[winner[0]][0]} ({MODELS[winner[0]][1]} effort) / {winner[1]}**. "
           f"It matched {settings[winner]['holdout']['agreement']}/31 held-out decisions and "
           f"{settings[winner]['full']['agreement']}/85 in the full reconstruction. "
           f"Ranking retrospectively on all 85 gives **{best_all[0]} / {best_all[1]}** "
           f"with {settings[best_all]['full']['agreement']}/85 matches.",
           "", "## Prompt and model comparisons","",
           "| Model setting | Prompt | Dev removal F1 | Held-out removal F1 | Held-out matches /31 | Full matches /85 | Full removals found /19 |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for k in ordered_by("development"):
        d,h,f=(settings[k][s] for s in (*SPLITS,"full"))
        lines.append(f"| {k[0]} | {k[1]} | {d['f1']:.3f} | {h['f1']:.3f} | {h['agreement']} | {f['agreement']} | {f['tp']} |")
    lines+=["","## Most frequent disagreements across configurations","",
            "Each configuration makes its own 19-item cut. Counts below use the first run of each complete OpenAI configuration.",
            "","| Historical decision | Configurations disagreeing | Passage | Question |","|---|---:|---|---|"]
    for group in ("removed","retained"):
        def disagreement_count(row):
            return row["total"]-row["remove_votes"] if group=="removed" else row["remove_votes"]
        subset=sorted((r for r in decisions if r["historical"]==group),key=lambda r:(-disagreement_count(r),r["source_id"]))
        for r in subset[:3]:
            lines.append(f"| {group} | {disagreement_count(r)}/{r['total']} | {r['reference']} | {r['question']} |")
    lines+=["","## Questions where the development winner disagrees","","| Passage | Historical | Model | Original question | Model’s reason |","|---|---|---|---|---|"]
    for r in mismatches(detail(winner)):
        lines.append("| "+" | ".join(str(r[k]).replace("|","\\|") for k in ["reference","historical","model_decision","question","reason"])+" |")
    if best_all!=winner:
        lines+=["","## Questions where the retrospective full-bank winner disagrees","",
                "| Passage | Historical | Model | Original question | Model’s reason |","|---|---|---|---|---|"]
        for r in mismatches(detail(best_all)):
            lines.append("| "+" | ".join(str(r[k]).replace("|","\\|") for k in ["reference","historical","model_decision","question","reason"])+" |")
    lines+=["","## How to read the comparison","",
            "Development used 54 questions outside Judges. The held-out set used all 31 Judges questions. At the known 19/85 removal rate each configuration removed 12 on development and seven on holdout. The independent full reconstruction ranks the combined scores and removes 19. Its cutoff can move questions across the two split cutoffs.",
            "","Removal F1 weights precision and recall for the rarer removal decision. The development winner uses removal F1, balanced accuracy, then a fixed name tie-break. An all-keep baseline agrees with 66/85 and finds zero removals. An uninformed random cut of 19 has an expected 4.25 historical removals in common. Aggregate scores describe this finite collection. The model prompts were blind. The analyst had previously inspected this corpus, so the held-out book is an internal check rather than a new independent corpus.",
            "","The original model was GPT-5.6 Sol at low effort. In the table, original_low and original_high are GPT-5.6 Sol, sol_high is GPT-6.1 Sol, and astra_high is GPT-6 Astra. Each model saw all candidates in one split together. [Source of the original instruction](provenance.md) · [Exact prompts](design.json) · [Every configuration’s decision on every question](all_item_decisions.csv).",""]
    if supplement:
        lines+=["## Supplemental runs","","The Claude Sonnet 5.5 development batch had already been submitted before authorization was restricted to OpenAI. Claude received no held-out batch. The local Qwen fallback ran while authorization was pending. These runs were outside the OpenAI model comparison. [Supplemental results](supplemental_runs.csv)",""]
    stability=OUTPUT/"repeat_stability.csv"
    if stability.exists():
        lines+=["## Repeat runs","","Two more runs for each development finalist shuffled question order within the same splits. Model sampling can also vary between calls.","",
                "| Model setting | Prompt | Shuffle seed | Full matches /85 | Removals found /19 | Decisions identical to first run /85 |",
                "|---|---|---:|---:|---:|---:|"]
        for r in csv.DictReader(io.StringIO(stability.read_text())):
            lines.append(f"| {r['model']} | {r['prompt']} | {r['order_seed']} | {r['agreement']} | {r['tp']} | {r['same_decision_as_first']} |")
        repeated=repeated_selections(history)
        if repeated:
            lines+=["","The three-draw summary averages the historical matches. The median-rank selection uses the median of each question's three positions, with average position and opaque ID as tie-breaks, then removes the bottom 19. This is a descriptive follow-up on the same bank.","",
                    "| Finalist | Matches by draw /85 | Average matches /85 | Median-rank matches /85 |",
                    "|---|---|---:|---:|"]
            for r in repeated:
                lines.append(f"| {r['model']} / {r['prompt']} | {r['first']}, {r['repeat_1']}, {r['repeat_2']} | {r['mean_matches']} | {r['median_rank_matches']} |")
    atomic_write(OUTPUT/"review.md","\n".join(lines))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["prepare","run","repeat","report"])
    p.add_argument("--workers",type=int,default=8)
    a=p.parse_args();prepare()
    if a.action=="repeat":
        replicate(a.workers)
    if a.action=="run":
        client=OpenAI(timeout=600,max_retries=2)
        with ThreadPoolExecutor(a.workers) as ex:
            jobs=[ex.submit(run_case,client,m,n,s) for s in SPLITS for n in PROMPTS for m in MODELS]
            errors=[]
            for job in as_completed(jobs):
                try:job.result()
                except Exception as exc:errors.append(type(exc).__name__)
            if errors:raise RuntimeError(f"{len(errors)} cases failed; rerun to resume")
    if a.action!="prepare":report()

if __name__=="__main__":main()
