"""Compare four frozen banks of English open questions using a uniform on-device reader."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random
import sys
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
import time

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
OUT = Path(__file__).resolve().parent
READER = "qwen3:8b"
GRADER = "gemma3:4b"
SYSTEM = """You are answering one comprehension question. Use only the provided passage. Give a direct, concise English answer. If the passage does not establish the answer, say 'Cannot tell from this passage.' Do not supply information from memory or explain your reasoning."""
MARK = """Grade an English short answer to a Bible comprehension question against the supplied key. Judge the requested fact rather than wording. Full credit for paraphrases, ordinary spelling variants, synonyms, co-referring titles and any answer that adequately answers what the stem actually asks. Allow nonessential extra detail. If the answer states a correct part but omits an essential requested part, classify partial. If unsupported, contradictory, or an abstention, classify wrong. Return only the requested JSON."""
OPTIONS = {"temperature":0,"seed":20261108,"num_ctx":4096,"num_predict":160}
SCORE_SCHEMA = {"type":"object","properties":{"grade":{"type":"string","enum":["full","partial","wrong"]}},"required":["grade"]}


def load(p):
    return json.loads(Path(p).read_text())


def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    with NamedTemporaryFile("w",encoding="utf-8",dir=p.parent,delete=False) as f:
        json.dump(x,f,ensure_ascii=False,indent=2,sort_keys=True)
        f.write("\n")
    Path(f.name).replace(p)


def sig(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def banks():
    prep = REPORTS / "prepared110_review_2026-11-08"
    audit = load(prep/"audit.json")
    placement = load(prep/"selection.json")
    selected = placement["projected_assignment"]
    old_gold = load(ROOT/"datasets/tier1_gold_72.json")["items"]
    lookup = {r["content_id"]:r for r in audit["items"]}
    banks = defaultdict(list)
    def add(group, pid, cid, q, key, labels, verses, blind, editorial):
        assert len(labels)==len(verses)>=2 and all(x.strip() for x in verses)
        # Identical references lose the same verse, regardless of bank, wording or key.
        lost = int(sig([20261108,pid,labels])[:16],16) % len(labels)
        banks[group].append(dict(pid=pid,id=cid,q=q,key=key,labels=labels,verses=verses,
                                 omitted=lost, prior_blind=blind, prior_editorial=editorial))
    for group, rows in [("Gold72",[(r["content_id"],r["window_ordinals"],r) for r in old_gold]),
                        ("Prepared60",[(cid,ordinals,None) for cid,ordinals in selected.items()])]:
        for cid,ordinals,old in rows:
            item = lookup[cid]
            revised = old is None and cid in audit["accepted_revisions"]
            form = audit["accepted_revisions"][cid] if revised else item
            if old:
                assert (old["question"],old["answer"])==(form["question"],form["answer"])
            win = next(w for w in item["windows"] if w["start"]==ordinals[0])
            findings = (audit["rechecks"] if revised else audit["as_written"])[cid]
            finding = next(r for r in findings if r["start"]==ordinals[0])
            texts = [line.split("] ",1)[1] for line in win["text"].splitlines()]
            add(group,item["passage_id"],cid,form["question"],form["answer"],win["verses"],texts,
                finding["blind"]["status"]=="passed",finding["passed"])
    active = {i["id"].removeprefix("uw-").removesuffix("-mcq") for i in load(ROOT/"runs/hard66_book_mcq_2026-10-28/manifest.json")["items"]}
    pool = load(REPORTS/"hard66_selection_answerability_2026-11-07/answerability.json")["items"]
    original = {r["source_id"]:r for r in load(REPORTS/"hard85_rule_check_2026-11-07/audit.json")["items"]}
    final = load(REPORTS/"hard85_revised_bank_2026-11-07/audit.json")["items"]
    public = load(REPORTS/"hard85_revised_bank_2026-11-07/final_bank.json")
    kept = {r["source_id"]:r for r in public}
    meta = {r["id"]:r for r in pool}
    pids = {r["passage"]:r["published_id"].split(":")[0] for r in pool if r["published_id"]}
    for r in final:
        cid = r["source_id"]; orig = original[cid]; m = meta[cid]
        pid = pids[m["passage"]]
        chapter = m["passage"].split("_")[1]
        labels = [f"{chapter}:{v}" for v in r["window_text"]]
        assert r["window_text"]==orig["window"]==m["window"]
        if m["published_id"] in active:
            assert m["historical"]=="retained" and (orig["question"],orig["key"])==(m["question"],m["answer"])
            add("Hard65",pid,cid,m["question"],m["answer"],labels,list(m["window"].values()),
                m["finding"]["status"]=="passed",orig["item_decision"]=="keep")
        if cid in kept:
            k=kept[cid]
            assert (k["question"],k["answer"],k["window_text"])==(r["question"],r["answer"],r["window_text"])
            checks=r["checks"]
            if checks is None:
                assert (r["question"],r["answer"])==(m["question"],m["answer"])
            blind=(checks["blind"]["status"]=="passed") if checks else (m["finding"]["status"]=="passed")
            add("Hard77",pid,cid,k["question"],k["answer"],labels,list(k["window_text"].values()),blind,r["item_decision"]=="keep")
    for name,count in [("Gold72",72),("Prepared60",60),("Hard65",65),("Hard77",77)]:
        assert len({r["id"] for r in banks[name]})==len(banks[name])==count
    return dict(banks)


def tasks(rosters):
    jobs = {}
    for rows in rosters.values():
        for r in rows:
            for condition in ["clean","omission"]:
                text="\n".join(v for i,v in enumerate(r["verses"]) if condition=="clean" or i!=r["omitted"])
                prompt="Passage\n"+text+"\n\nQuestion\n"+r["q"]
                token=sig([READER,SYSTEM,OPTIONS,prompt])
                jobs[token]=prompt
                r[condition]=token
    return jobs


def local(endpoint,body=None):
    data = None if body is None else json.dumps(body,ensure_ascii=False).encode()
    request=Request("http://127.0.0.1:11434/api/"+endpoint,data=data,headers={"Content-Type":"application/json"})
    with urlopen(request,timeout=200) as response:
        return json.load(response)


def run_chat(model,system,prompt,schema=None):
    body=dict(model=model,messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
              stream=False,options=OPTIONS,keep_alive="10m")
    if model==READER: body["think"]=False
    if schema: body["format"]=schema
    for attempt in range(3):
        try:
            result=local("chat",body)
            reply=result["message"]["content"].strip()
            if not result["done"] or result.get("done_reason")=="length" or not reply:
                raise ValueError("Incomplete local response")
            if schema and json.loads(reply).get("grade") not in ["full","partial","wrong"]:
                raise ValueError("Bad grade")
            return reply
        except Exception:
            if attempt==2:raise
            time.sleep(1)


def collect():
    rosters=banks();jobs=tasks(rosters)
    inventory={m["name"]:m["digest"] for m in local("tags")["models"]}
    for m in (READER,GRADER): assert m in inventory
    plan=dict(banks=rosters,reader=READER,grader=GRADER,models={m:inventory[m] for m in (READER,GRADER)},
              reader_prompt=SYSTEM,grading_prompt=MARK,options=OPTIONS,distinct_reader_calls=len(jobs))
    manifest=OUT/"manifest.json"
    if manifest.exists():assert plan==load(manifest)
    else:save(manifest,plan)
    order=list(sorted(jobs));random.Random(20261108).shuffle(order)
    print("Distinct requests",len(order),flush=True)
    answers={}
    for n,k in enumerate(order,1):
        path=OUT/"answers"/(k+".json")
        if not path.exists(): save(path,{"answer":run_chat(READER,SYSTEM,jobs[k])})
        answers[k]=load(path)["answer"]
        if n%50==0:print("Read",n,"/",len(order),flush=True)
    grades={}
    for group,items in rosters.items():
        for r in items:
            for cond in ("clean","omission"):
                answer=answers[r[cond]]
                data={"question":r["q"],"key":r["key"],"reply":answer}
                k=sig([GRADER,MARK,OPTIONS,data])
                grades[k]=data
    order=list(sorted(grades));random.Random(20261109).shuffle(order)
    for n,k in enumerate(order,1):
        path=OUT/"grades"/(k+".json")
        if not path.exists():
            data=grades[k];a=data["reply"].strip().rstrip(".").lower()
            if a=="cannot tell from this passage":grade="wrong"
            elif a==data["key"].strip().rstrip(".").lower():grade="full"
            else:grade=json.loads(run_chat(GRADER,MARK,json.dumps(data,ensure_ascii=False),SCORE_SCHEMA))["grade"]
            save(path,dict(grade=grade,**data))
        if n%50==0:print("Graded",n,"/",len(order),flush=True)
    print("Completed",len(grades),"distinct grading records",flush=True)


if __name__=="__main__":collect()
