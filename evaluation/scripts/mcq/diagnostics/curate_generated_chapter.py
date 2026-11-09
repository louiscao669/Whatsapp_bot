"""Apply the Hard85 eligibility and duplicate checks to fresh scored-generator output."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

from openai import OpenAI

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import check_hard85_rules as rules
from evaluation.scripts.mcq.diagnostics import experiment_hard66_selectors as io


def signature(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def load_generation(directory, verse_loader, *, partial=False):
    plan=io.read(directory/"run_config.json")
    source=Path(plan["source_file"])
    if sha256(source.read_bytes()).hexdigest()!=plan["source_sha256"]:
        raise ValueError("Source passage changed after generation")
    verses,_,_=verse_loader(source,"auto")
    windows={r["id"]:r["verses"] for r in plan["windows"]}
    if partial:
        records=[]
        plan_hash=sha256((directory/"run_config.json").read_bytes()).hexdigest()
        for label in windows:
            file=directory/"window_checkpoints"/(label+".json")
            if file.exists():
                checkpoint=io.read(file)
                if checkpoint["config_digest"]!=plan_hash:raise ValueError(f"Stale checkpoint: {label}")
                records.append(checkpoint["data"])
        reports=[r["report"] for r in records]
        rows=[item for r in records for item in r["kept"]]
    else:
        reports=io.read(directory/"windows.json")
        rows=io.read(directory/"generated.json")
    seen={r["window_id"]:r["verses"] for r in reports}
    if (not partial and seen!=windows) or len(reports)!=len(seen) or any(windows.get(k)!=v for k,v in seen.items()):
        raise ValueError(f"Missing or duplicate generator jobs: expected {list(windows)}, received {list(seen)}")
    if [v for w in windows.values() for v in w]!=sorted(verses):
        raise ValueError("Planned windows do not cover the chapter exactly once")
    for r in rows:
        label=r["content_id"].rsplit(":",1)[0]
        if r["window_text"]!={str(k):verses[k] for k in windows[label]} or not r["audit"]["passed"]:
            raise ValueError(f"Invalid generator survivor: {r['content_id']}")
    if len({r["content_id"] for r in rows})!=len(rows):
        raise ValueError("Duplicate generated ID")
    return plan,reports,rows


def run(args):
    sys.path.insert(0,str(args.generator_root.resolve()))
    os.environ.setdefault("HARD_QA_TIMEOUT_SECONDS","180")
    from qa_generation.scripts.generate_hard import load_windowed_verses
    from qa_generation.services.answerability import AnswerabilityCheck
    from qa_generation.prompts.hard_qa import format_window
    directory=args.run_dir
    plan,reports,generated=load_generation(directory,load_windowed_verses,partial=args.precheck)
    client=None if args.verify else OpenAI(timeout=420,max_retries=2)
    checker=AnswerabilityCheck("enforce",plan["generation_judge"])
    edits=io.read(directory/"edits.json") if (directory/"edits.json").exists() else {}
    if set(edits)-{r["content_id"] for r in generated}:
        raise ValueError("Editorial changes refer to unknown items")
    (directory/"responses").mkdir(exist_ok=True)
    records={}; inputs={}; checks={}
    for r in generated:
        k=r["content_id"];edit=edits.get(k,{})
        q=edit.get("question",r["question"]);answer=edit.get("answer",r["answer"])
        text=format_window({int(v):s for v,s in r["window_text"].items()})
        old=r["audit"].get("answerability",{})
        if old.get("status")!="passed" or old.get("question")!=r["question"] or not old.get("readings"):
            raise ValueError(f"{k} lacks a passed blind check for the original stem")
        checks[k]={"blind":old}
        if (q,answer)!=(r["question"],r["answer"]):
            path=directory/"responses"/f"blind_{signature([text,q,answer,checker.model])}.json"
            if path.exists() and io.read(path)["status"]!="unchecked":
                finding=io.read(path)
            else:
                if args.verify:raise ValueError(f"Missing blind check: {k}")
                finding=checker.assess(text,q,answer);io.save(path,finding)
            if finding["status"]=="unchecked":raise ValueError(f"Unchecked wording: {k}")
            checks[k]["blind"]=finding
        inputs[k]=dict(id=k,window=text,question=q,key=answer,competitor=edit.get("competitor",r["wrong_answer"]))
        records[k]=dict(id=k,reference=f"{plan['chapter']}:{min(r['window_verses'])}–{max(r['window_verses'])}",
                        question=q,answer=answer,competitor=inputs[k]["competitor"],window_text=r["window_text"],
                        original_question=r["question"],original_answer=r["answer"],edit=edit)
    def call(name,prompt,batch,schema):
        token=signature([rules.MODEL,prompt,batch])
        return rules.ask(client,f"{name}_{token}",prompt,batch,schema,output_dir=directory)
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs={}
        for k,item in inputs.items():
            for perspective,suffix in rules.PERSPECTIVES.items():
                future=pool.submit(call,perspective,rules.ITEM_PROMPT+"\n"+suffix,[item],rules.Gates)
                jobs[future]=(k,perspective)
        for job in as_completed(jobs):
            k,p=jobs[job];checks[k][p]=job.result()["items"][0]
    if args.precheck:
        print(f"Saved item checks for {len(inputs)} candidates from {len(reports)} completed windows.")
        return
    for k,r in records.items():
        c=checks[k]; ratings=[rules.verdict(c[p]) for p in rules.PERSPECTIVES]
        action=ratings[0] if len(set(ratings))==1 else "review"
        if action=="keep" and c["blind"]["status"]!="passed":action="review"
        r.update(checks=c,item_decision=action,final_decision=action)
    eligible=sorted(k for k,r in records.items() if r["item_decision"]=="keep")
    pairs=[]
    if len(eligible)>=2:
        with ThreadPoolExecutor(2) as pool:
            jobs=[pool.submit(call,"duplicates",rules.DUP_PROMPT,[inputs[k] for k in order],rules.Pairs)
                  for order in (eligible,list(reversed(eligible)))]
            pairs=[job.result()["pairs"] for job in jobs]
        for k,(action,why) in rules.duplicate_decisions(pairs).items():
            records[k].update(final_decision=action,duplicate_reason=why)
    ordered=sorted(records.values(),key=lambda r:min(map(int,r["window_text"])))
    bank=[{f:r[f] for f in ("id","reference","question","answer","competitor","window_text")}
          for r in ordered if r["final_decision"]=="keep"]
    counts=Counter(r["final_decision"] for r in ordered)
    io.save(directory/"editorial_audit.json",dict(counts=dict(counts),items=ordered,duplicate_judgments=pairs))
    io.save(directory/"final_bank.json",bank)
    lines=[f"# {plan['chapter']} · Fresh hard-QA run","",
           f"**{len(bank)} English open-response questions passed.** The generator processed {len(reports)} windows, "
           f"drafted {sum(r['generated'] for r in reports)} candidates across all attempts, and retained "
           f"{len(generated)} for the final chapter review.","",
           "GPT-5 generated and scored from the chapter text and checked answerability with the key hidden from the reader. "
           "The generator could retain one representative per window and retry empty windows once. "
           "Two GPT-5.6 Sol assessments judged clean-window support, wording and comprehension. Eligible items then received duplicate checks in two orders. "
           "The chapter had no target question count.","","| Verse window | Final question | Answer key |","|---|---|---|"]
    for r in bank:
        lines.append("| "+" | ".join(r[f].replace("|","\\|") for f in ("reference","question","answer"))+" |")
    lines+=["","## Window coverage","","| Verses | Candidates drafted | Generator survivors | Final questions |","|---|---:|---:|---:|"]
    for r in sorted(reports,key=lambda x:min(x["verses"])):
        span=r["window_id"]
        lines.append(f"| {min(r['verses'])}–{max(r['verses'])} | {r['generated']} | {r['kept']} | "
                     f"{sum(b['id'].rsplit(':',1)[0]==span for b in bank)} |")
    edited_or_cut=[r for r in ordered if r["edit"] or r["final_decision"]!="keep"]
    if edited_or_cut:
        lines+=["","## Editorial decisions","","| Window | Original draft | Decision | Reason |",
                "|---|---|---|---|"]
        for r in edited_or_cut:
            checks=r["checks"]
            reasons=[r["edit"]["reason"]] if r["edit"].get("reason") else []
            if checks["blind"]["status"]!="passed":
                reasons.append(checks["blind"]["reason"])
            reasons.extend(checks[p]["reason"] for p in rules.PERSPECTIVES if rules.verdict(checks[p])!="keep")
            if r.get("duplicate_reason"):reasons.append(r["duplicate_reason"])
            decision="Keep after edit" if r["edit"] and r["final_decision"]=="keep" else r["final_decision"].title()
            lines.append("| "+" | ".join(t.replace("|","\\|").replace("\n"," ") for t in
                         (r["reference"],r["original_question"],decision," ".join(dict.fromkeys(reasons))))+" |")
    lines+=["","[Final bank with keys and windows](final_bank.json) · [Editorial and duplicate findings](editorial_audit.json) · "
            "[Generation settings](run_config.json) · [Rejected candidates](generation_rejections.json)",""]
    io.atomic_write(directory/"review.md","\n".join(lines))
    print("Final decisions:",dict(counts))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir",required=True,type=Path)
    parser.add_argument("--generator-root",required=True,type=Path)
    parser.add_argument("--verify",action="store_true")
    parser.add_argument("--precheck",action="store_true",help="Check completed window candidates early; do not select or export a bank.")
    run(parser.parse_args())
