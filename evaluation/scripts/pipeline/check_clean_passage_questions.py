"""Check the original Chinese pilot MCQs on the new clean passages with the same local blind reader."""
import json
from collections import Counter
from hashlib import sha256

import requests

from evaluation.scripts.pipeline.compare_clean_passages import RUN, ROOT, read, save, freeze
from evaluation.scripts.pipeline.verify_reviewed122_zh import MODEL, PROMPT, SCHEMA, run_check

BANK = ROOT / "evaluation/datasets/qa/reviewed122"
PREVIOUS = ROOT / "evaluation/runs/english_mcq_hard77_prepared60_2026-11-08/chinese_translation/blind_audit.json"


def main():
    directory = RUN / "pilot_mcq_check"
    published = read(BANK / "zh.json")
    final = {p.parent.name: read(p)["verses"] for p in RUN.glob("t1_*/clean_release.json")}
    eligibility = {r["id"]: r["status"] for r in read(BANK/"pilot_review.json")}
    old = {r["id"]:r for r in read(PREVIOUS)}
    previous_windows = read(BANK/"clean_zh_verses.json")
    rows = []
    for n, row in enumerate(published,1):
        before = {v:previous_windows[row["passage_id"]][v] for v in row["verses"]}
        if before != row["verses"] or old[row["id"]]["correct"] != row["correct"]:
            raise ValueError(f"Baseline mismatch for {row['id']}")
        window = {v:final[row["passage_id"]][v] for v in row["verses"]}
        rows.append((n,dict(row,verses=window)))
    if len(rows)!=len(eligibility) or len(rows)!=len(old) or len(rows)!=122:
        raise ValueError("Incomplete QA bank")
    candidate = [r for _,r in rows]
    freeze(directory/"questions_with_candidate_windows.json",candidate)
    with requests.Session() as session:
        session.trust_env=False
        url="http://127.0.0.1:11434"
        version=session.get(url+"/api/version",timeout=10,allow_redirects=False)
        version.raise_for_status()
        models=session.get(url+"/api/tags",timeout=10,allow_redirects=False)
        models.raise_for_status()
        model=next(m for m in models.json()["models"] if m["name"]==MODEL)
        recipe=dict(check="blind",model=MODEL,model_digest=model["digest"],ollama_version=version.json()["version"],
                    options={"temperature":0,"num_ctx":8192,"num_predict":1150},think=False,prompt=PROMPT,schema=SCHEMA,
                    bank_sha256=sha256((directory/"questions_with_candidate_windows.json").read_bytes()).hexdigest(),
                    baseline_audit_sha256=sha256(PREVIOUS.read_bytes()).hexdigest())
        checks=run_check(session,directory,rows,recipe,{})
    result=[dict(id=c["id"],prior_eligibility=eligibility[c["id"]],key=c["correct"],
                 old_match=old[c["id"]]["matched"],new_match=c["matched"],
                 proposed_choices=c["review"]["supported"],reason=c["review"]["reason"]) for c in checks]
    counts=Counter((r["prior_eligibility"],r["old_match"],r["new_match"]) for r in result)
    save(directory/"comparison.json",{"counts":[dict(prior_status=s,old_match=o,new_match=n,count=v)
        for (s,o,n),v in counts.items()],"items":result})
    print("old / new matches",sum(r["old_match"] for r in result),sum(r["new_match"] for r in result),flush=True)


if __name__=="__main__":
    main()
