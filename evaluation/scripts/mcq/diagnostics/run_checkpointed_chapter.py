"""Run the scored chapter generator with resumable per-window draft and verdict files."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics.audit_hard66_answerability import atomic_write, read


def save(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2)+"\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir",type=Path,required=True)
    parser.add_argument("--generator-root",type=Path,required=True)
    args=parser.parse_args()
    directory=args.run_dir
    plan=read(directory/"run_config.json")
    config_digest=sha256((directory/"run_config.json").read_bytes()).hexdigest()
    sys.path.insert(0,str(args.generator_root.resolve()))
    os.environ["HARD_QA_TIMEOUT_SECONDS"]="180"
    from qa_generation.scripts.generate_hard import load_windowed_verses
    from qa_generation.services.scored_generation import ScoredGenerator
    from qa_generation.services.answerability import AnswerabilityCheck
    from qa_generation.prompts.scored_qa import Candidate
    from qa_generation.prompts.hard_qa import _build_llm
    assert _build_llm(plan["writer"]).root_client.timeout==180
    source=Path(plan["source_file"])
    if sha256(source.read_bytes()).hexdigest()!=plan["source_sha256"]:
        raise ValueError("Source changed")
    verses,_,_=load_windowed_verses(source,"auto")
    if [v for win in plan["windows"] for v in win["verses"]]!=sorted(verses):
        raise ValueError("Planned windows do not cover the chapter")
    generator=ScoredGenerator(
        candidates_per_window=plan["candidates_per_window"],survivors_per_window=plan["per_window"],
        window_retries=plan["window_retries"],model=plan["writer"],judge_model=plan["generation_judge"],
        max_concurrency=12,answerability=AnswerabilityCheck(plan["answerability"],plan["generation_judge"]))
    checkpoint=directory/"window_checkpoints"
    checkpoint.mkdir(exist_ok=True)
    def cached(path):
        obj=read(path)
        if obj["config_digest"]!=config_digest:raise ValueError(f"Stale checkpoint {path.name}")
        return obj["data"]
    def process(win):
        label=win["id"]
        finished=checkpoint/f"{label}.json"
        if finished.exists():return cached(finished)
        passage={k:verses[k] for k in win["verses"]}
        drafts=checkpoint/f"{label}_drafts.json"
        if drafts.exists():
            candidates=[Candidate.model_validate(row) for row in cached(drafts)]
        else:
            candidates=generator.generate_candidates(passage)
            save(drafts,dict(config_digest=config_digest,data=[c.model_dump() for c in candidates]))
            print(f"{label}: {len(candidates)} initial drafts saved",flush=True)
        kept,rejected,report=generator._finish_generated_window(label,passage,candidates)
        result=dict(kept=kept,rejected=rejected,report=report)
        save(finished,dict(config_digest=config_digest,data=result))
        print(f"{label}: {report['generated']} candidates, {len(kept)} retained",flush=True)
        return result
    results={}
    with ThreadPoolExecutor(max_workers=12) as pool:
        jobs={pool.submit(process,win):win["id"] for win in plan["windows"]}
        failed=[]
        for job in as_completed(jobs):
            try:results[jobs[job]]=job.result()
            except Exception as exc:
                failed.append(jobs[job]);print(jobs[job],type(exc).__name__,str(exc)[:160],flush=True)
        if failed:raise RuntimeError(f"Unfinished windows: {failed}. Rerun to resume.")
    kept=[];rejected=[];reports=[]
    for win in plan["windows"]:
        out=results[win["id"]];kept+=out["kept"];rejected+=out["rejected"];reports.append(out["report"])
    kept,cut=generator.rank(kept,plan["chapter_target"],per_window=plan["per_window"])
    save(directory/"generated.json",kept)
    save(directory/"generation_rejections.json",rejected+cut)
    save(directory/"windows.json",reports)
    print(f"{len(reports)} completed windows, {sum(r['generated'] for r in reports)} candidates, "
          f"{len(kept)} finalists",flush=True)


if __name__=="__main__":main()
