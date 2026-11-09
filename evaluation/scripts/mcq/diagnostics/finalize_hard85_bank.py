"""Recheck editorial repairs, adjudicate Hard85 referrals and export the passing bank."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sys

from openai import OpenAI

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import check_hard85_rules as rules

prior = rules.prior
OUT = REPO / "evaluation/reports/hard85_revised_bank_2026-11-07"


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare():
    data, history = prior.load_data()
    base = {r["id"]:r for r in prior.read(rules.OUT/"audit.json")["items"]}
    changes = prior.read(OUT/"editorial_changes.json")
    changes_by_id = {r["id"]:r for r in changes}
    target = {k for k,r in base.items() if r["final_decision"] in ("revise","review")}
    if (len(changes)!=22 or set(changes_by_id)!=target or len(base)!=85
            or Counter(base[k]["final_decision"] for k in target)!={"revise":9,"review":13}):
        raise ValueError("Editorial change set does not match the 22 outstanding items")
    for k,row in base.items():
        if (row["question"],row["key"],row["window"])!=(data[k]["question"],data[k]["key"],history[k]["window"]):
            raise ValueError(f"Archived item differs from the previously checked version: {k}")
    updates = OUT/"followup_changes.json"
    if updates.exists():
        for update in prior.read(updates):
            k = update["id"]
            if k not in target or update["supersedes"]!=fingerprint(changes_by_id[k]):
                raise ValueError("Follow-up edit must be bound to the previous version")
            changes_by_id[k] = {**changes_by_id[k],**update}
    items = {k:dict(r) for k,r in data.items()}
    for k,edit in changes_by_id.items():
        if edit["action"] not in ("edit","exclude"):
            raise ValueError(f"Unexpected editorial action: {k}")
        if edit["action"]=="edit" and not edit.get("question","").strip():
            raise ValueError(f"Missing revised question: {k}")
        for field in ("question","key","competitor"):
            if field in edit:
                if not edit[field].strip():raise ValueError(f"Empty {field}: {k}")
                items[k][field]=edit[field]
    return items,history,base,changes_by_id


def blind_check(judge, module, window, item, run):
    inputs=[window,item["question"],item["key"],judge.model,inspect.getsource(module),
            str(module.enumerate_readings_prompt),str(module.decision_prompt)]
    signature=fingerprint(inputs)
    path=OUT/"responses"/f"blind_{item['id']}_{signature[:16]}.json"
    if path.exists():
        cached=prior.read(path)
        if cached["fingerprint"]!=signature:raise ValueError(f"Stale blind cache: {path}")
        if cached["result"]["status"]!="unchecked":
            return cached["result"]
    if not run:raise ValueError(f"Missing blind check: {path}")
    finding=judge.assess(window,item["question"],item["key"])
    prior.save(path,{"fingerprint":signature,"result":finding})
    if finding["status"]=="unchecked":raise ValueError(f"Unchecked blind result for {item['id']}: {finding['reason']}")
    return finding


def check_items(items, history, changes, run, generator_root):
    sys.path.insert(0,str(generator_root.resolve()))
    from qa_generation.config import load_env
    load_env()
    from qa_generation.prompts.hard_qa import format_window
    from qa_generation.services import answerability
    client=OpenAI(timeout=420,max_retries=2) if run else None
    judge=answerability.AnswerabilityCheck("report-only","gpt-5")
    checked=defaultdict(dict)
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs={}
        for k in sorted(changes):
            item=items[k]
            for perspective,prompt in rules.PERSPECTIVES.items():
                req=rules.ITEM_PROMPT+"\n"+prompt
                token=fingerprint([req,item])[:16]
                job=pool.submit(rules.ask,client,f"{perspective}_{k}_{token}",req,[item],
                                rules.Gates,output_dir=OUT)
                jobs[job]=(k,perspective)
            window=format_window({int(v):s for v,s in history[k]["window"].items()})
            job=pool.submit(blind_check,judge,answerability,window,item,run)
            jobs[job]=(k,"blind")
        for job in as_completed(jobs):
            k,type_=jobs[job]
            result=job.result()
            checked[k][type_]=result if type_=="blind" else result["items"][0]
    return checked,client


def apply_checks(items, history, base, changes, checked, client):
    rows={};eligible=defaultdict(list)
    for k,item in items.items():
        h=history[k];original=base[k];edit=changes.get(k);check=checked.get(k)
        if edit:
            actions=[rules.verdict(check[p]) for p in rules.PERSPECTIVES]
            action=actions[0] if len(set(actions))==1 else "review"
            reason=f"Reader: {actions[0]}. Editor: {actions[1]}. Blind: {check['blind']['verdict']}."
            if action=="keep" and check["blind"]["status"]!="passed":
                action="review"
            if edit["action"]=="exclude":
                action="drop";reason+=" Editorial exclusion: "+edit["reason"]
        else:
            action=original["final_decision"]
            reason="Previous checks on identical question, key, competitor and window. "+original["reason"]
        if action=="keep":eligible[h["passage"]].append(k)
        rows[k]=dict(id=k,source_id=h["id"],published_id=h["published_id"],reference=original["reference"],
            window_text=h["window"],question=item["question"],answer=item["key"],competitor=item["competitor"],
            original_question=original["question"],original_answer=original["key"],
            starting_decision=original["final_decision"],editorial=edit,item_decision=action,
            final_decision=action,reason=reason,checks=check)
    pairs=defaultdict(dict)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs={}
        for passage,ids in eligible.items():
            if len(ids)<2:continue
            for order,ks in enumerate([sorted(ids),sorted(ids,reverse=True)]):
                payload=[items[k] for k in ks]
                token=fingerprint([payload,rules.DUP_PROMPT])[:16]
                job=pool.submit(rules.ask,client,f"duplicate_{passage}_{order}_{token}",rules.DUP_PROMPT,
                                payload,rules.Pairs,output_dir=OUT)
                jobs[job]=passage,order
        for job in as_completed(jobs):
            passage,order=jobs[job];pairs[passage][order]=job.result()["pairs"]
    for pair in pairs.values():
        for k,(action,why) in rules.duplicate_decisions([pair[0],pair[1]]).items():
            rows[k].update(final_decision=action,reason=why)
    return rows,pairs


def export(rows,pairs,history,changes):
    counts=Counter(r["final_decision"] for r in rows.values())
    keep=[{f:r[f] for f in ("id","source_id","published_id","reference","question","answer","competitor","window_text")}
          for r in rows.values() if r["final_decision"]=="keep"]
    if len(rows)!=85 or len(set(r["source_id"] for r in keep))!=counts["keep"]:
        raise ValueError("Bank identity check failed")
    prior.save(OUT/"final_bank.json",keep)
    prior.save(OUT/"audit.json",dict(counts=dict(counts),items=list(rows.values()),duplicate_judgments=pairs))
    flat=[]
    for r in rows.values():
        if r["id"] not in changes:continue
        c=r["checks"]
        flat.append(dict(reference=r["reference"],source_id=r["source_id"],origin=r["starting_decision"],
            original_question=r["original_question"],final_question=r["question"],
            original_key=r["original_answer"],final_key=r["answer"],editorial_action=r["editorial"]["action"],
            editorial_reason=r["editorial"]["reason"],reader=rules.verdict(c["reader"]),reader_reason=c["reader"]["reason"],
            editor=rules.verdict(c["editor"]),editor_reason=c["editor"]["reason"],
            blind=c["blind"]["verdict"],blind_reason=c["blind"]["reason"],
            final_decision=r["final_decision"],final_reason=r["reason"]))
    prior.table(OUT/"revision_log.csv",flat)
    lines=["# Hard85 final English question bank","",
           f"**{len(keep)} of 85 questions are included.** Each included item is available with its current key, original window, competitor and stable source identifier in [the usable bank](final_bank.json).",
           "","| Starting group | Questions | Kept in final bank | Outside final bank |",
           "|---|---:|---:|---:|"]
    for origin in ("keep","revise","review","drop"):
        subset=[r for r in rows.values() if r["starting_decision"]==origin]
        n=sum(r["final_decision"]=="keep" for r in subset)
        lines.append(f"| {origin.title()} | {len(subset)} | {n} | {len(subset)-n} |")
    lines+=["","## What was checked","",
            "I reviewed all 22 referrals against their original clean verse windows. Each received two fresh GPT-5.6 Sol editorial assessments and an isolated GPT-5 answerability check. The blind reader saw the exact question and window, and a separate call compared its answers with the key. The previously resolved 63 items used their existing item-level evidence. Every passage with at least two eligible candidates received duplicate checks in both presentation orders across the combined set.",
            "","No target size was imposed. Only the keep decisions enter the bank. Any discrepancy that remained after editing is recorded as a withheld item below.",
            "","## Items outside the bank","",
            "| Window | Question | Final disposition and reason |","|---|---|---|"]
    for k,r in rows.items():
        if r["final_decision"]=="keep":continue
        why=r["reason"]
        if why.startswith("Confirmed duplicate of "):
            winner=why.split()[-1]
            why="Duplicates “"+rows[winner]["question"]+"”"
        elif r["editorial"] and r["editorial"]["action"]=="exclude":
            why=r["editorial"]["reason"]
        elif r["checks"]:
            c=r["checks"]
            why=" ".join(dict.fromkeys([c[p]["reason"] for p in rules.PERSPECTIVES
                if rules.verdict(c[p])!="keep"]+([c["blind"]["reason"]] if c["blind"]["status"]!="passed" else []))) or why
        elif not r["editorial"]:
            why="Previously excluded. "+r["reason"].removeprefix("Previous checks on identical question, key, competitor and window. ")
        fields=[r["reference"],r["question"],r["final_decision"].title()+" — "+why]
        lines.append("| "+" | ".join(v.replace("|","\\|").replace("\n"," ") for v in fields)+" |")
    lines+=["","## All 22 editorial decisions","",
            "| Source group | Window | Question after review | Answer key | Outcome |",
            "|---|---|---|---|---|"]
    for r in flat:
        fields=[r["origin"],r["reference"],r["final_question"],r["final_key"],r["final_decision"]]
        lines.append("| "+" | ".join(v.replace("|","\\|").replace("\n"," ") for v in fields)+" |")
    lines+=["","[Before and after wording, keys, and check reasons](revision_log.csv) · [All 85 dispositions and duplicate evidence](audit.json)",""]
    prior.atomic_write(OUT/"review.md","\n".join(lines))
    print("Final decisions:",dict(counts))
    print("Prior to final:",dict(Counter((r["starting_decision"],r["final_decision"]) for r in rows.values())))
    for k,r in rows.items():
        if r["starting_decision"]=='keep' and r['final_decision']!='keep':
            print("Displaced:",k,r["question"],r["reason"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["prepare","run","verify"])
    p.add_argument("--generator-root",required=True,type=Path)
    args=p.parse_args()
    items,history,base,changes=prepare()
    (OUT/"responses").mkdir(parents=True,exist_ok=True)
    if args.action=="prepare":return
    checks,client=check_items(items,history,changes,args.action=="run",args.generator_root)
    rows,pairs=apply_checks(items,history,base,changes,checks,client)
    export(rows,pairs,history,changes)


if __name__=="__main__":main()
