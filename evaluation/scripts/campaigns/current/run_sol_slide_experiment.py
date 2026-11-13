"""Run the corrected Sol questions under the reader configurations shown in slides 35–43."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import fcntl
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

import requests

REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO), str(REPO / "human_pilot")]
os.environ.update(MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E", MCQ_NOTA_LABEL="")
from evaluation.agents import generate_chinese_answers as gen
from evaluation.scripts.mcq.diagnostics import run_hard66_book_mcq as small
from evaluation.scripts.scoring.current import score_generated_answers as scoring
from evaluation.scripts.variants.current import create_grammar_variants as grammar
from human_pilot import pilot_import_reviewed122 as pilot
from human_pilot.pilot_import import load_tier1_metadata, parse_tier1_verses

RUN = REPO / "evaluation/runs/sol_slides35_43_2026-11-13"
REPORT = REPO / "evaluation/reports/sol_slides35_43_2026-11-13"
RAW = REPO / "evaluation/runs/clean_passage_sol_astra_2026-11-09/release"
LOCAL = "http://127.0.0.1:11434"
STUDIES = {"scratch":"Hard77","prepared":"Prepared60"}
MODELS = [
    ("llama3.2:1b", None), ("qwen2.5:1.5b", None), ("qwen3:1.7b", True), ("qwen3:1.7b", False),
    ("gemma3:4b", None), ("phi4-mini:3.8b", None), ("qwen2.5:3b", None),
]
SHORT = ["clean","omission15","omission30","mistranslation15","mistranslation30","grammar30","wbw"]
FULL = ["clean"]+[f"{family}{rate}" for family in ("omission","mistranslation","grammar") for rate in range(5,31,5)]+["wbw"]
CONFIG = {"temperature":0,"num_ctx":8192,"num_predict":2500}
SYSTEM = ("Answer from the translated passage only. Do not include verse numbers, guess, or use outside knowledge. "
          "Do not repeat or echo the passage text in the answer. Do not echo the question. Do not output markdown or explanations. "
          "Return only the raw answer text.")
JUDGE = "gpt-4.1-mini"


def read(p):
    return json.loads(p.read_text())


def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(f"{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
    tmp.replace(p)


def digest(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def model_name(model,thinking):
    return model if thinking is None else f"{model} ({'thinking' if thinking else 'no thinking'})"


@lru_cache(maxsize=1)
def source():
    path=RUN/'sol_questions.json'
    rows=read(path) if path.is_file() else pilot.load_bank(pilot.SOL_SET)
    plan=RUN/'design.json'
    if plan.is_file() and digest(rows)!=read(plan)['bank_sha']:
        raise ValueError('Sol question snapshot differs from the experiment manifest.')
    assert Counter(r["source"] for r in rows)=={"Hard77":66,"Prepared60":48}
    manifest=read(pilot.SOL_RELEASE/"manifest.json")
    packs={p.stem:pilot.checked_json(p,manifest["files"][p.name]) for p in pilot.SOL_RELEASE.glob("t1_*.json")}
    if not path.exists():
        save(path,rows)
    return rows,packs


def db_open():
    RUN.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(RUN/"observations.sqlite",timeout=60)
    db.execute("pragma journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS answers(hash TEXT PRIMARY KEY, answer TEXT NOT NULL, tokens INTEGER, done_reason TEXT);
        CREATE TABLE IF NOT EXISTS observations(study TEXT,model TEXT,condition TEXT,form TEXT,item TEXT,request_hash TEXT,choice TEXT,outcome TEXT,
            PRIMARY KEY(study,model,condition,form,item));
        CREATE TABLE IF NOT EXISTS grades(study TEXT,model TEXT,condition TEXT,item TEXT,english TEXT,score REAL,rationale TEXT,
            PRIMARY KEY(study,model,condition,item));
    """)
    return db


def frozen(db, inventory):
    rows,packs=source()
    required={k for k,_ in MODELS}
    weights={m["name"]:m["digest"] for m in inventory["models"] if m["name"] in required}
    assert weights.keys()==required
    for f in ("hard66_small_models_variants_2026-10-28","hard66_book_mcq_2026-10-28"):
        for name,sha in read(REPO/"evaluation/runs"/f/"manifest.json")["model_digests"].items():
            if name in required: assert sha==weights[name],name
    assert weights["llama3.2:1b"].startswith("baf6a787fdff")
    audit={"models":weights,"inference":CONFIG,"bank_sha":digest(rows),"passages":{k:digest(v) for k,v in packs.items()},
           "bank_questions":{s:[r['id'] for r in rows if r['source']==src] for s,src in STUDIES.items()},
           "open_conditions":SHORT,"primary_mcq_conditions":[*FULL,"grammarMax"],"additional_mcq_conditions":SHORT,
           "open_scoring_model":JUDGE,"window":"exact reviewed Sol verse labels; use only surviving verses after omission",
           "reuse":"same complete prompt, model digest, thinking setting and inference options within a set",
           "source_files":{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [Path(gen.__file__),Path(small.__file__),Path(scoring.__file__)]}}
    path=RUN/"design.json"
    if path.exists() and read(path)!=audit:raise ValueError("Frozen protocol or inputs changed.")
    save(path,audit)
    return weights


@lru_cache(maxsize=1)
def max_verses():
    rows,packs=source()
    metadata={m['id']:m for m in load_tier1_metadata(REPO/'evaluation')}
    coverage,verses={},{}
    for pid,pack in packs.items():
        directory=RUN/'grammar_max_final'/pid/'grammar'
        audit=read(directory/'sentence_review.json')['files']['passage_target.txt']
        bank=read(directory/'_grammar_bank'/f"bank_{audit['bank_id']}.json")
        clean=(RAW/pid/'_base/llm_prompt_high/passage_target.txt').read_text()
        assert clean.strip()==pack['conditions']['clean']['text'].strip()
        checked,_=grammar.apply_grammar_bank(clean,rate=1.0,seed=bank['spec']['seed'],bank=bank)
        assert bank['spec']['unit_mode']=='sentence' and audit['source_sha256']==grammar.json_digest(clean)
        assert 0<len(bank['entries'])==audit['approved_sentence_units'] and checked==(directory/'draft_passage_target.txt').read_text()
        total=sum(unit['affectable'] for unit in grammar.passage_units(clean,unit_mode='sentence'))
        assert total==audit['total_sentence_units'] and audit['sentence_coverage']==len(bank['entries'])/total
        verses[pid]=dict(parse_tier1_verses(checked,metadata[pid]))
        assert list(verses[pid])==list(pack['conditions']['clean']['verses'])
        coverage[pid]={k:audit[k] for k in ('bank_id','approved_sentence_units','total_sentence_units','sentence_coverage')}
    save(RUN/'grammar_max_coverage.json',coverage)
    return verses


def request_for(row,passage,model,thinking,form,additional):
    choices=dict(zip("ABCDE",row['choices'],strict=True))
    public={'question':row['question'],'choices':choices,'q_type':form,'item_index':1}
    if additional:
        msgs=small.messages_for({'question':row['question'],'choices':choices,'private_clean_passage':passage},
                                {'condition':'open_book','thinking':None})
    else:
        prompt=gen.build_raw_answer_prompt(passage,public,expanded_answer_format=False)
        if thinking is False:prompt=gen.apply_no_think(prompt)
        msgs=[{'role':'system','content':SYSTEM},{'role':'user','content':prompt}]
    body={'model':model,'messages':msgs,'stream':False,'options':CONFIG}
    if thinking is not None:body['think']=thinking
    return body, public


def infer(session,body):
    for attempt in range(3):
        try:
            response=session.post(LOCAL+'/api/chat',json=body,timeout=(10,150))
            if body.get('think') is False and response.status_code in (400,404,422):
                response=session.post(LOCAL+'/api/chat',json={k:v for k,v in body.items() if k!='think'},timeout=(10,150))
            response.raise_for_status()
            raw=response.json()
            if not raw.get('done') or 'message' not in raw:raise ValueError('Incomplete Ollama reply')
            return gen.clean_raw_answer(raw['message']['content']),raw.get('eval_count'),raw.get('done_reason')
        except (requests.RequestException,ValueError):
            if attempt==2:raise
            time.sleep(2**attempt)


def run_readers(study,max_only,*,item_id=None):
    rows,packs=source()
    selected=[r for r in rows if r['source']==STUDIES[study]]
    if item_id is not None:
        selected=[r for r in selected if r['id']==item_id]
        if len(selected)!=1:
            raise ValueError(f"Expected one {study} question with ID {item_id!r}")
    session=requests.Session()
    tags=session.get(LOCAL+'/api/tags',timeout=15); tags.raise_for_status()
    db=db_open()
    weights=frozen(db,tags.json())
    for ix,(model,thinking) in enumerate(MODELS):
        if max_only and ix>=4:continue
        name=model_name(model,thinking)
        conditions=['grammarMax'] if max_only else FULL if ix<4 else SHORT
        for condition in conditions:
            for form in (['mcq','open'] if ix<3 and condition in SHORT else ['mcq']):
                completed={i for (i,) in db.execute("select item from observations where study=? and model=? and condition=? and form=?",(study,name,condition,form))}
                for r in selected:
                    if r['id'] in completed:continue
                    pid=r['passage_id']
                    verses=max_verses()[pid] if max_only else packs[pid]['conditions'][condition]['verses']
                    excerpt=' '.join(verses[v] for v in r['verses'] if v in verses)
                    if not excerpt:raise ValueError(f"Empty passage for {r['id']} {condition}")
                    # The historical Gold configurations used the no-thinking prompt
                    # for both small readers. Hard used their default prompt.
                    mode=False if study=='prepared' and ix<2 else thinking
                    body,public=request_for(r,excerpt,model,mode,form,ix>=4)
                    key=digest([study,weights[model],body])
                    cached=db.execute("select answer from answers where hash=?",(key,)).fetchone()
                    with db:
                        if cached:answer=cached[0]
                        else:
                            answer,tokens,reason=infer(session,body)
                            db.execute("insert into answers values(?,?,?,?)",(key,answer,tokens,reason))
                        choice,outcome=None,None
                        if form=='mcq':
                            if ix>=4:choice,_=small.parse_choice(answer,public['choices'])
                            else:choice=gen.selected_choice_from_raw_answer(public,answer) if answer else None
                            outcome='correct' if choice==r['correct'] else 'abstain' if choice=='E' else 'incorrect' if choice else 'invalid'
                        db.execute("insert into observations values(?,?,?,?,?,?,?,?)",(study,name,condition,form,r['id'],key,choice,outcome))
                print(study,name,condition,form,len(selected),flush=True)
    db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study',choices=STUDIES)
    parser.add_argument('--max-only',action='store_true')
    parser.add_argument('--item',help='Run only this item in the selected study.')
    args=parser.parse_args()
    RUN.mkdir(parents=True,exist_ok=True)
    with (RUN/'reader.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run_readers(args.study,args.max_only,item_id=args.item)
