"""Compare the reviewed selector with the historical-context winner on matched orders."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
from pathlib import Path
import sys

from openai import OpenAI

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import experiment_hard66_selectors as prior


OUT = REPO / "evaluation/reports/hard66_refined_selection_2026-11-07"
MODEL = "original_high"
BASE = "historical_context"
NEW = "historical_context_refined"
ORDERS = (None, 67411, 81937)
BANK = "historical_context_bank_editor"


def prepare():
    data, history = prior.load_data()
    reviewed = {r["id"]: r for r in prior.read(OUT / "editorial_review.json")["items"]}
    with (prior.OUTPUT / "repeat_decisions.csv").open() as f:
        expected = {r["source_id"] for r in csv.DictReader(f) if r["model"] == MODEL and r["prompt"] == BASE
                    and (r["historical"], r["removal_votes"]) in {("retained", "3"), ("removed", "0")}}
    if len(reviewed) != 6 or {history[k]["id"] for k in reviewed} != expected:
        raise ValueError("Review must cover exactly the six persistent disagreements")
    prompt = prior.PROMPTS[BASE] + "\n\n" + (OUT / "prompt_addition.txt").read_text().strip()
    design = {"model":prior.MODELS[MODEL][0], "effort":prior.MODELS[MODEL][1],
              "selection_prompt":prompt, "common_instructions":prior.COMMON, "orders":list(ORDERS),
              "scope":"Only the selection prompt changes. Reuse original blinded batches, matched baseline calls, 19-removal quota and opaque-ID tie-break. No labels, review text or worked cases go to the model.",
              "review_hash":prior.digest((OUT / "editorial_review.json").read_text()),
              "evaluation":"Compare the six with the editor's judgments, the other 79 with historical decisions, and all 85 with historical decisions. The other 79 were used in earlier benchmarking, so this is an internal comparison.",
              "batches":prior.read(prior.OUTPUT / "design.json")["batches"]}
    for split in prior.SPLITS:
        batch=prior.read(prior.OUTPUT / f"{split}_blinded.json")
        if prior.digest(json.dumps(batch,ensure_ascii=False)) != design["batches"][split]:
            raise ValueError("Original blinded input fingerprint changed")
        if any(data[r["id"]]!=r for r in batch):
            raise ValueError("Blinded rows differ from source")
    path=OUT/"design.json"
    if path.exists() and prior.read(path)!=design:
        raise ValueError("Frozen comparison changed; use a new run directory")
    if not path.exists():prior.save(path,design)
    return data, history, reviewed, prompt


def read_draw(root, name, seed, history):
    path=root/("responses" if seed is None else f"repeats/order_{seed}")
    results={}
    for split in prior.SPLITS:
        record=prior.read(path/f"{MODEL}__{name}__{split}.json")
        if (record["model"],record["effort"])!=prior.MODELS[MODEL] or not record["response_id"]:
            raise ValueError("Unexpected model response")
        ids={k for k,v in history.items() if v["split"]==split}
        for r in prior.validate(record,ids):results[r["id"]]=r
    flags=prior.predicted(list(results.values()))
    if len(flags)!=19 or len(results)!=85:raise ValueError("Incomplete full-bank cut")
    return results,flags


def prepare_bank(history, reviewed):
    update=prior.read(OUT/"bank_review_update.json")
    bank={k:v["decision"] for k,v in reviewed.items()}
    bank[update["id"]]=update["bank_decision"]
    comparator=next(k for k,h in history.items() if h["id"]==update["comparator_source_id"])
    prompt=prior.PROMPTS[BASE]+"\n\n"+(OUT/"bank_prompt_addition.txt").read_text().strip()
    design=dict(prompt=prompt,common_instructions=prior.COMMON,model=prior.MODELS[MODEL][0],
                effort=prior.MODELS[MODEL][1],orders=list(ORDERS),editorial_calls=bank,
                comparison_item=comparator,review_update=update,
                base_design_hash=prior.digest((OUT/"design.json").read_text()))
    path=OUT/"bank_design.json"
    if path.exists() and prior.read(path)!=design:
        raise ValueError("Frozen second comparison changed")
    if not path.exists():prior.save(path,design)
    return bank, comparator, prompt


def bank_report(data, history, reviewed, bank, comparator):
    labels=[("Previous",prior.OUTPUT,BASE),("First revision",OUT,NEW),("Bank revision",OUT,BANK)]
    group=set(reviewed); others=set(history)-group
    outcomes={};counts=[];all_rows=[]
    for label,root,name in labels:
        for seed in ORDERS:
            results,flags=read_draw(root,name,seed,history)
            outcomes[label,seed]=flags
            cnt=dict(prompt=label,order=seed or "original",
                six_original=sum((k in flags)==(reviewed[k]["decision"]=="remove") for k in group),
                six_bank=sum((k in flags)==(bank[k]=="remove") for k in group),
                other79=sum((k in flags)==(history[k]["historical"]=="removed") for k in others),
                all85=sum((k in flags)==(h["historical"]=="removed") for k,h in history.items()),
                kept_olive_cut_fig=(comparator not in flags and "QEEBA6" in flags))
            counts.append(cnt)
            for k,r in results.items():
                all_rows.append(dict(prompt=label,order=cnt["order"],source_id=history[k]["id"],
                    question=data[k]["question"],key=data[k]["key"],reference=prior.passage_reference(history[k]),
                    historical=history[k]["historical"],bank_editor=bank.get(k,""),
                    decision="remove" if k in flags else "keep",score=r["score"],reason=r["why"]))
    prior.table(OUT/"bank_comparison.csv",counts)
    prior.table(OUT/"bank_decisions.csv",all_rows)
    update=prior.read(OUT/"bank_review_update.json")
    lines=["# Which of the six questions belong in Hard66?","",
        "I would keep the donkey rider and the ambushers’ pending condition. I would remove the other four as written from this bank. The fig tree remains a useful standalone question. Comparing its verse window with the adjacent olive-tree item changed my bank decision.",
        "","The initial six calls were frozen before the first revision ran. I recorded the fig-tree update before running the second revision. Neither revision contained the questions, names, verdicts or labels as examples. Each used GPT-5.6 Sol at high effort and the same 85 inputs in the same three orders as the previous winner. Each full-bank cut kept 66 questions.",
        "", "## Comparison across the three matched orders","",
        "| Prompt | Original six judgments /6 | Final bank judgments /6 | Historical decisions on other 79 /79 | Historical decisions on all 85 /85 | Kept olive and cut fig /3 runs |",
        "|---|---|---|---|---|---:|"]
    for label,_,_ in labels:
        draws=[r for r in counts if r["prompt"]==label]
        cells=[", ".join(str(r[key]) for r in draws) for key in ("six_original","six_bank","other79","all85")]
        lines.append("| "+" | ".join([label,*cells,str(sum(r["kept_olive_cut_fig"] for r in draws))])+" |")
    def mean(label,metric):
        draws=[r[metric] for r in counts if r["prompt"]==label]
        return sum(draws)/len(draws)
    lines+=["",f"The previous and bank-level prompts averaged {mean('Previous','all85'):.1f} and "
            f"{mean('Bank revision','all85'):.1f} historical matches out of 85. On the other 79, "
            f"their means were {mean('Previous','other79'):.1f} and {mean('Bank revision','other79'):.1f}. "
            "The evidence for this revision is concentrated in the reviewed cases. "
            "It consistently retained the olive-tree question and removed the fig-tree parallel, "
            "but kept the question about the claim in all three runs."]
    lines+=["","Numbers in each cell follow the original order, then shuffle seeds 67411 and 81937. Agreement on the six is a tuning-set result. The other 79 use historical decisions as their reference rather than new editorial ratings. All 85 had been seen in the earlier experiment.",
            "","## The six decisions","",
            "| Original question | Key | Final call | Previous kept /3 | First revision kept /3 | Bank revision kept /3 |",
            "|---|---|---|---:|---:|---:|"]
    for k in reviewed:
        c=[data[k]["question"],data[k]["key"],bank[k]]
        c.extend(str(sum(k not in outcomes[label,seed] for seed in ORDERS)) for label,_,_ in labels)
        lines.append("| "+" | ".join(c)+" |")
    for k,review in reviewed.items():
        h=history[k]
        reason=review["why"] if k!=update["id"] else review["why"]+" "+update["why"]
        lines+=["",f"### {prior.passage_reference(h)} · {h['question']}","",
                f"**{bank[k].title()} for this bank.** {reason}","",
                f"**Key** — {h['answer']}  ",f"**Competitor** — {data[k]['competitor']}","",
                *[f"> **{v}** {s}" for v,s in h["window"].items()]]
        if k==update["id"]:
            other=history[comparator]
            lines+=["",f"**Parallel item · {prior.passage_reference(other)}** — {other['question']}  ",
                    f"**Key** — {other['answer']}","",*[f"> **{v}** {s}" for v,s in other["window"].items()]]
    lines+=["","[First revised prompt](design.json) · [Bank-level revised prompt](bank_design.json) · [Matched results](bank_comparison.csv) · [All question scores, decisions and reasons](bank_decisions.csv)",""]
    prior.atomic_write(OUT/"bank_review.md","\n".join(lines))


def report(data,history,reviewed):
    comparisons=[];details=[];votes={}
    historic={k for k,v in history.items() if v["historical"]=="removed"}
    editorial={k for k,v in reviewed.items() if v["decision"]=="remove"}
    six=set(reviewed);others=set(history)-six
    for seed in ORDERS:
        for label,root,name in [("previous",prior.OUTPUT,BASE),("refined",OUT,NEW)]:
            results,flags=read_draw(root,name,seed,history)
            votes[label,seed]=flags
            comparisons.append(dict(order=seed or "original",prompt=label,
                six_editor_matches=len(six-((flags^editorial)&six)),
                other79_historical_matches=len(others-((flags^historic)&others)),
                full85_historical_matches=len(history)-len(flags^historic),
                historical_removals_found=len(flags&historic)))
            for k,r in results.items():
                details.append(dict(id=k,source_id=history[k]["id"],reference=prior.passage_reference(history[k]),
                    question=data[k]["question"],key=data[k]["key"],order=seed or "original",prompt=label,
                    decision="remove" if k in flags else "keep",score=r["score"],reason=r["why"],
                    historical=history[k]["historical"],editorial=reviewed.get(k,{}).get("decision","")))
    prior.table(OUT/"matched_results.csv",comparisons)
    prior.table(OUT/"all_item_decisions.csv",details)
    lines=["# Six hard-QA selection decisions","",
           "The editorial calls below were recorded before the revised prompt ran. Each model run used the archived English window, question, key and proposed competitor. We held the model (GPT-5.6 Sol), reasoning effort (high), inputs, three item orders and 66-place bank size fixed. Only the selection instructions changed.",
           "", "## Matched prompt comparison","",
           "| Order | Prompt | Matches my six /6 | Matches history on other 79 /79 | Matches history on all 85 /85 | Historical removals found /19 |",
           "|---|---|---:|---:|---:|---:|"]
    for r in comparisons:
        lines.append("| "+" | ".join(str(v) for v in r.values())+" |")
    for label in ("previous","refined"):
        runs=[r for r in comparisons if r["prompt"]==label]
        means=[sum(r[m] for r in runs)/len(runs) for m in list(runs[0])[2:]]
        lines.append(f"| Mean | {label} | "+" | ".join(f"{m:.1f}" for m in means)+" |")
    lines+=["","The six shaped the revision. The other 79 give an internal check on whether any gain carries over. For those 79 the reference is the historical selection, which can differ from editorial judgment.",
            "", "## What changed on the other 79?","",
            "| Order | Moved into agreement with history | Moved out of agreement with history |",
            "|---|---:|---:|"]
    for seed in ORDERS:
        old_wrong=(votes["previous",seed]^historic)&others
        new_wrong=(votes["refined",seed]^historic)&others
        lines.append(f"| {seed or 'original'} | {len(old_wrong-new_wrong)} | {len(new_wrong-old_wrong)} |")
    lines+=["","## The six decisions at a glance","",
            "| Window | Original question | Key | My call | Previous kept /3 | Refined kept /3 |",
            "|---|---|---|---|---:|---:|"]
    for k,r in reviewed.items():
        cells=[prior.passage_reference(history[k]),data[k]["question"],data[k]["key"],r["decision"]]
        cells.extend(str(sum(k not in votes[label,s] for s in ORDERS)) for label in ("previous","refined"))
        lines.append("| "+" | ".join(c.replace("|","\\|") for c in cells)+" |")
    lines+=["", "## Review against the original windows",""]
    for k,r in reviewed.items():
        h=history[k];lines+=[f"### {prior.passage_reference(h)} · {h['question']}","",
                f"**{r['decision'].title()} as written.** {r['why']}","",
                f"**Answer key** — {h['answer']}  ",
                f"**Proposed competitor** — {data[k]['competitor']}","",
                f"Historically {h['historical']}. Previous prompt kept it {sum(k not in votes['previous',s] for s in ORDERS)}/3 times. Revised prompt kept it {sum(k not in votes['refined',s] for s in ORDERS)}/3 times.","",
                *[f"> **{v}** {t}" for v,t in h["window"].items()],""]
    lines+=["## Revised prompt","","[Exact selection and output instructions](design.json) · [Added criteria](prompt_addition.txt) · [All model decisions, scores and reasons](all_item_decisions.csv)",""]
    prior.atomic_write(OUT/"review.md","\n".join(lines))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["prepare","run","report","prepare-bank","run-bank","report-bank"])
    args=parser.parse_args()
    data,history,reviewed,prompt=prepare()
    name=NEW
    if args.action.endswith("-bank"):
        bank, comparator, prompt=prepare_bank(history,reviewed)
        name=BANK
    if args.action in ("run","run-bank"):
        client=OpenAI(timeout=600,max_retries=2)
        with ThreadPoolExecutor(6) as pool:
            jobs=[pool.submit(prior.run_case,client,MODEL,name,split,seed,prompt_text=prompt,output_root=OUT)
                  for seed in ORDERS for split in prior.SPLITS]
            for job in as_completed(jobs):job.result()
    if args.action in ("run","report"):report(data,history,reviewed)
    if args.action in ("run-bank","report-bank"):bank_report(data,history,reviewed,bank,comparator)


if __name__=="__main__":main()
