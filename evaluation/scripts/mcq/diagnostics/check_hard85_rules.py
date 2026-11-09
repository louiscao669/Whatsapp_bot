"""Apply explicit, quota-free item and duplicate gates to the archived English QA pool."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import random
import sys
import time
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import experiment_hard66_selectors as prior

OUT = REPO / "evaluation/reports/hard85_rule_check_2026-11-07"
MODEL = "gpt-5.6-sol"
ITEM_PROMPT = """Independently audit each open-response question for a Bible translation comprehension study.
Any number may qualify. Use only that item's exact clean window. Judge each gate separately.
KEY: unique means the key answers the question completely and only one meaning fits. Treat paraphrases, a person and their co-referring title, or equivalents as one meaning. Repairable means a bounded stem/key edit would recover the same intended relation. Unsupported means the window cannot establish the target relation even with clearer wording. Use uncertain for unresolved cases.
WORDING: clear means an ordinary reader understands what is asked without guessing the author's reference. Mark rewrite for avoidable generic stand-ins, technical labels, or a materially vague or misleading stem. A slightly smoother alternative alone is insufficient.
COMPREHENSION: meaningful means there is a concrete distinction the reader must resolve (e.g. actor versus recipient, reference, condition versus outcome, cause, scope, or an indirect utterance). State the specific contrast and why the distinction follows from this window. A simple question can qualify. An explicit answer can qualify when the relation matters. Mark lookup when a key word, incidental fact or generic retrieval is sufficient and there is no credible misreading of the relationship. Assess the underlying comprehension target separately from any wording fault. Consider whether a later line simply gives the answer away. The supplied competitor is only a proposal; it can be replaced by a better, passage-grounded misreading. Mark uncertain if there is insufficient evidence to judge.
For a unique key give one brief contiguous verbatim quote from the window; use an empty quote only when there is no evidence. Explain the decisive evidence or failure in plain English. Do not rank, compare different candidates, infer prior selection, or choose a bank size."""
PERSPECTIVES = {
    "reader": "First consider what an attentive reader would understand and then compare that with the key.",
    "editor": "First test the plausibility of an alternative reading, then check whether the wording and key resolve it.",
}
DUP_PROMPT = """Audit only redundancy among these individually eligible questions from the same passage.
Return a pair only when the items ask for essentially the same fact, or repeat the same inference in parallel scenes with only the entities changed. Sharing grammar, characters, or question type alone is insufficient. Zero pairs is normal. For each duplicate, prefer the item that tests more distinct passage meaning, then clearer wording and more complete key. Pick the earlier textual event for an otherwise exact tie. Explain what is repeated and why the selected representative is preferable. For three or more equivalent items, compare the preferred representative directly with each redundant item. Return no self-pairs or repeated pairs."""


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Gate(StrictRecord):
    id: str
    key: Literal["unique", "repairable", "unsupported", "uncertain"]
    wording: Literal["clear", "rewrite", "uncertain"]
    comprehension: Literal["meaningful", "lookup", "uncertain"]
    quote: str
    contrast: str
    reason: str


class Gates(StrictRecord):
    items: list[Gate]


class Pair(StrictRecord):
    preferred: str
    redundant: str
    reason: str


class Pairs(StrictRecord):
    pairs: list[Pair]


def freeze(path, obj):
    if path.exists() and prior.read(path)!=obj:
        raise ValueError(f"Frozen inputs or policy changed: {path}")
    if not path.exists():
        prior.save(path,obj)


def verdict(g):
    if g["key"]=="unsupported" or g["comprehension"]=="lookup":
        return "drop"
    if "uncertain" in (g["key"],g["wording"],g["comprehension"]):
        return "review"
    if g["key"]=="repairable" or g["wording"]=="rewrite":
        return "revise"
    return "keep"


def validate(result, records, schema):
    parsed=schema.model_validate(result).model_dump()
    by_id={r["id"]:r for r in records}
    if schema is Gates:
        gates=parsed["items"]
        if len(gates)!=len(by_id) or {g["id"] for g in gates}!=set(by_id):
            raise ValueError("Item IDs differ from request")
        for g in gates:
            span=" ".join(g["quote"].split())
            window=" ".join(by_id[g["id"]]["window"].split())
            if (g["key"]=="unique" and not span) or (span and span not in window):
                raise ValueError(f"Unverified support for {g['id']}")
            if not g["reason"].strip() or (g["comprehension"]=="meaningful" and not g["contrast"].strip()):
                raise ValueError("Missing gate explanation")
    else:
        seen=set()
        for pair in parsed["pairs"]:
            key=frozenset((pair["preferred"],pair["redundant"]))
            if len(key)!=2 or not key.issubset(by_id) or key in seen or not pair["reason"].strip():
                raise ValueError("Invalid duplicate pair")
            seen.add(key)
    return parsed


def ask(client, name, prompt, records, schema, *, output_dir=OUT):
    path=output_dir/"responses"/f"{name}.json"
    body=json.dumps(records,ensure_ascii=False)
    fingerprint=prior.digest(prompt+"\n"+body+schema.__name__+MODEL)
    if path.exists():
        saved=prior.read(path)
        if saved["fingerprint"]!=fingerprint:raise ValueError(f"Stale response: {path}")
        return validate(saved["result"],records,schema)
    if client is None:raise ValueError(f"Missing response: {path}")
    for attempt in range(3):
        try:
            response=client.responses.create(model=MODEL,reasoning={"effort":"high"},store=False,
                instructions=prompt,input=body,max_output_tokens=10000,
                text={"format":{"type":"json_schema","name":schema.__name__,"strict":True,
                                "schema":schema.model_json_schema()}})
            if response.status!="completed":raise ValueError(response.status)
            result=validate(json.loads(response.output_text),records,schema)
            prior.save(path,dict(fingerprint=fingerprint,model=response.model,response_id=response.id,result=result))
            return result
        except Exception as exc:
            if attempt==2:raise
            print(f"Retry {name}: {type(exc).__name__}",flush=True)
            time.sleep(2**attempt)


def duplicate_decisions(orders):
    # Resolve an entire cluster only when both presentations retain the same
    # representative in a direct comparison with every other cluster member.
    edge_sets=[{(p["preferred"],p["redundant"]) for p in pairs} for pairs in orders]
    union=set.union(*edge_sets)
    links=defaultdict(set)
    for a,b in union:
        links[a].add(b);links[b].add(a)
    decisions={};remaining=set(links)
    while remaining:
        group=set();todo=[min(remaining)]
        while todo:
            k=todo.pop()
            if k in group:continue
            group.add(k);todo.extend(links[k]-group)
        remaining-=group
        edges={e for e in union if e[0] in group}
        roots=group-{b for _,b in edges}
        representative=next(iter(roots)) if len(roots)==1 else None
        if (representative and all(edges.issubset(es) for es in edge_sets)
                and all((representative,k) in edges for k in group-{representative})):
            for k in group-{representative}:decisions[k]=("drop",f"Confirmed duplicate of {representative}")
        else:
            for k in group:decisions[k]=("review","Unresolved duplicate group: "+", ".join(sorted(group)))
    return decisions


def write_report(rows):
    counts=Counter(r["final_decision"] for r in rows.values())
    before=Counter(r["item_decision"] for r in rows.values())
    agreed=sum(verdict(r["gates"]["reader"])==verdict(r["gates"]["editor"]) for r in rows.values())
    duplicate_drops=[r for r in rows.values() if r["reason"].startswith("Confirmed duplicate")]
    lines=["# Which Hard85 questions qualify as written?","",
        f"Applied a fixed decision rule to the original {len(rows)} English questions and their clean windows. "
        f"**{counts['keep']} are ready as written.** The historical selection and prior editorial calls were hidden. "
        "The rule has no target bank size and uses no score cutoff.","",
        "| Action | After item checks | After duplicate check |","|---|---:|---:|"]
    for label in ("keep","revise","review","drop"):
        lines.append(f"| {label.title()} | {before[label]} | {counts[label]} |")
    lines+=["","## Decision rule","",
        "1. Check whether a reader can recover one complete, supported answer from the clean window. Accept equivalent labels and paraphrases. Check whether the question is clear on first reading.",
        "2. Require a specific distinction a translation could change, such as agency, sequence, reference or scope. The evaluator must quote evidence for a supported key and explain the distinction. A simple stem can pass. A weak supplied competitor can be replaced by another grounded misreading.",
        "3. Two GPT-5.6 Sol high-effort assessments evaluate each item from different perspectives in shuffled batches. Code maps their findings to actions. Unsupported targets and pure lookup are dropped from the hard set. A fixable key or stem goes to revision and must be rechecked after editing. Uncertainty or disagreement goes to review. A proposed keep also needs a pass from the earlier key-blind GPT-5 check.",
        "4. Compare ready items within each archived source passage in two presentation orders. Drop a redundant item only when both comparisons identify the same preferred representative. Route disputed duplicate clusters to review. Recheck a passage's duplicates whenever an edited or reviewed item is admitted.","",
        f"The two assessments from the same model agreed on the initial action for {agreed}/{len(rows)}. Duplicate removals: {len(duplicate_drops)}. "
        "The rules are deterministic given the findings. The semantic findings are model judgments. This is a source-English screening result. Discrimination on actual damaged translations and with human readers requires separate measurements.",
        "","## Six previously discussed questions","",
        "| Window | Question | No-quota action | Basis |","|---|---|---|---|"]
    examples=prior.read(REPO/"evaluation/reports/hard66_refined_selection_2026-11-07/editorial_review.json")
    for prior_item in examples["items"]:
        r=rows[prior_item["id"]]; reason=r["reason"]
        if reason.startswith("Confirmed duplicate of "):
            other=rows[reason.split()[-1]]
            reason=f"Duplicates {other['question']}"
        elif r["final_decision"]!="review":
            reason=r["gates"]["reader"]["reason"]
        else:
            reason+=" "+r["gates"]["reader"]["reason"]+" "+r["gates"]["editor"]["reason"]
        cells=(r["reference"],r["question"],r["final_decision"],reason)
        lines.append("| "+" | ".join(c.replace("|","\\|").replace("\n"," ") for c in cells)+" |")
    lines+=["","These six are examples previously used in developing the rubric. They are not an independent test of selection quality.",
            "","[Every decision and both gate assessments](decisions.csv) · [Exact rubric and policy](design.json) · [Original windows and duplicate judgments](audit.json)",""]
    parallel=prior.read(REPO/"evaluation/reports/hard66_refined_selection_2026-11-07/bank_review_update.json")
    olive=next(r for r in rows.values() if r["source_id"]==parallel["comparator_source_id"])
    fig=rows[parallel["id"]]
    if olive["item_decision"]!="keep" and fig["final_decision"]=="keep":
        lines+=["## A pending duplicate check","",
                f"The fig-tree question qualified. The olive-tree question went to {olive['item_decision']}, "
                "so those two were never compared by the duplicate judge. If the olive item is approved, "
                "reassess the pair before publishing an updated bank.",""]
    prior.atomic_write(OUT/"review.md","\n".join(lines))


def execute(run):
    items,history=prior.load_data()
    (OUT/"responses").mkdir(parents=True,exist_ok=True)
    freeze(OUT/"design.json",dict(model=MODEL,effort="high",item_prompt=ITEM_PROMPT,
        perspectives=PERSPECTIVES,duplicate_prompt=DUP_PROMPT,
        policy="Both item dispositions must agree. Unsupported target or plain lookup: drop. Any unresolved gate: review. Fixable key or wording: revise. Otherwise keep if earlier independent blind reader/key check also passed, or request review. Compare eligible items within each original source passage twice for duplicates; disputed groups require review. No target size or numerical score.",
        source_hash=prior.digest(json.dumps(items,sort_keys=True,ensure_ascii=False)),
        blind_results_hash=prior.digest(json.dumps({k:h["finding"] for k,h in history.items()},sort_keys=True,ensure_ascii=False))))
    client=OpenAI(timeout=420,max_retries=2) if run else None
    evaluations=defaultdict(dict)
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs={}
        for seed,(perspective,suffix) in enumerate(PERSPECTIVES.items(),1):
            ids=sorted(items);random.Random(20261107+seed).shuffle(ids)
            for start in range(0,len(ids),5):
                group=[items[k] for k in ids[start:start+5]]
                job=pool.submit(ask,client,f"{perspective}_{start:02}",ITEM_PROMPT+"\n"+suffix,group,Gates)
                jobs[job]=perspective
        for job in as_completed(jobs):
            for g in job.result()["items"]:evaluations[g["id"]][jobs[job]]=g
    rows={};eligible=defaultdict(list)
    for k,h in history.items():
        both=evaluations[k]
        if set(both)!=set(PERSPECTIVES):raise ValueError("Missing gate evidence")
        a,b=[verdict(both[p]) for p in PERSPECTIVES]
        blind=h["finding"]["status"]
        action=a if a==b else "review"
        reason=f"Reader {a}; editor {b}."
        if action=="keep" and blind!="passed":
            action="review";reason+=f" Earlier blind check: {h['finding']['verdict']}."
        if action=="keep":eligible[h["passage"]].append(k)
        rows[k]=dict(id=k,source_id=h["id"],reference=prior.passage_reference(h),question=h["question"],
            key=h["answer"],window=h["window"],gates=both,blind_status=blind,blind_verdict=h["finding"]["verdict"],
            item_decision=action,final_decision=action,reason=reason)
    pairs=defaultdict(dict)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs={}
        for passage,ids in eligible.items():
            if len(ids)<2:continue
            for orientation,order in enumerate([sorted(ids),sorted(ids,reverse=True)]):
                job=pool.submit(ask,client,f"duplicates_{passage}_{orientation}",DUP_PROMPT,
                                [items[k] for k in order],Pairs)
                jobs[job]=(passage,orientation)
        for job in as_completed(jobs):
            passage,order=jobs[job];pairs[passage][order]=job.result()["pairs"]
    for passage,results in pairs.items():
        for k,(action,why) in duplicate_decisions([results[0],results[1]]).items():
            rows[k].update(final_decision=action,reason=why)
    final=Counter(r["final_decision"] for r in rows.values())
    prior.save(OUT/"audit.json",dict(counts=dict(final),items=list(rows.values()),duplicate_judgments=pairs))
    flat=[]
    for row in rows.values():
        out={k:v for k,v in row.items() if k not in ("gates","window")}
        for p,g in row["gates"].items():
            out.update({f"{p}_{field}":v for field,v in g.items() if field!="id"})
        flat.append(out)
    prior.table(OUT/"decisions.csv",flat)
    write_report(rows)
    print(dict(final),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["run","verify"])
    execute(parser.parse_args().action=="run")
