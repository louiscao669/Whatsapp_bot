"""Back-translate and grade the open responses against the current Sol answer keys."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time
import fcntl

from dotenv import load_dotenv

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_sol_slide_experiment as run


def translate(client,rows):
    run.scoring.translate_open_answers_to_english(client,run.JUDGE,rows,retries=2,batch_size=12,temperature=0,reverse_glossary={})


def references(client,study,items):
    path=run.RUN/f"{study}_english_grading_keys.json"
    signature=run.digest([(r['id'],r['question'],r['choices']['ABCD'.index(r['correct'])]) for r in items])
    existing=run.read(path) if path.exists() else {'signature':signature,'keys':{}}
    if existing['signature']!=signature:raise ValueError('Reference wording changed')
    keys=existing['keys']
    pending=[r for r in items if r['id'] not in keys]
    for offset in range(0,len(pending),12):
        batch=pending[offset:offset+12]
        data=[{'item_index':i,'question':r['question'],'generated_answer':r['choices']['ABCD'.index(r['correct'])]} for i,r in enumerate(batch,1)]
        translate(client,data)
        for r,out in zip(batch,data,strict=True):
            if not out['generated_answer_english'].strip():raise ValueError('Empty reference translation')
            keys[r['id']]=out['generated_answer_english']
        run.save(path,existing)
    return keys


def grade_batch(client, batch, items, keys):
    data = []
    for index, (item, answer) in enumerate(batch, 1):
        question = items[item]['question']
        if run.gen.looks_like_passage_excerpt(answer):
            answer = run.gen.compact_passage_excerpt(answer, question)
        data.append({'item_index': index, 'question': question, 'generated_answer': answer,
                     'standard_answer': keys[item]})
    valid = [row for row in data if row['generated_answer'].strip()]
    translate(client, valid)
    args = dict(answer_field='generated_answer_english', mode='english', temperature=0)
    try:
        judgments = run.scoring.llm_judge_batch(client, run.JUDGE, valid, 2, **args)
    except run.scoring.ScoreError:
        judgments = {row['item_index']: run.scoring.llm_judge_one(client, run.JUDGE, row, 2, **args) for row in valid}
    output = {}
    for pair, row in zip(batch, data, strict=True):
        result = judgments[row['item_index']] if row['generated_answer'].strip() else {'score':0,'rationale':'Empty response.'}
        assert result['score'] in (0, 0.5, 1)
        output[pair] = (row.get('generated_answer_english',''), result['score'], result['rationale'])
    return output


def grade(study):
    db=run.db_open()
    client=run.scoring.get_openai_client()
    rows=[r for r in run.source()[0] if r['source']==run.STUDIES[study]]
    items={r['id']:r for r in rows}
    keys=references(client,study,rows)
    total=len(items)*3*len(run.SHORT)
    known = {}
    for item, answer, english, score, rationale in db.execute("""
            SELECT o.item,a.answer,g.english,g.score,g.rationale FROM observations o
            JOIN answers a ON o.request_hash=a.hash JOIN grades g USING(study,model,condition,item)
            WHERE o.study=? AND o.form='open' ORDER BY g.rowid""", (study,)):
        known.setdefault((item,answer),(english,score,rationale))
    while True:
        pending=db.execute("""SELECT o.model,o.condition,o.item,a.answer FROM observations o JOIN answers a ON o.request_hash=a.hash
                           LEFT JOIN grades g USING(study,model,condition,item) WHERE o.study=? AND o.form='open' AND g.item IS NULL
                           ORDER BY o.rowid LIMIT 128""",(study,)).fetchall()
        if not pending:
            n=db.execute("SELECT count(*) FROM grades WHERE study=?",(study,)).fetchone()[0]
            if n==total:return
            time.sleep(10)
            continue
        groups = defaultdict(list)
        for model, cond, item, answer in pending:
            groups[item, answer].append((study, model, cond, item))
        def record(scores):
            with db:
                for pair, score in scores.items():
                    db.executemany("insert into grades values(?,?,?,?,?,?,?)", [(*key,*score) for key in groups[pair]])
                    known[pair] = score
        record({pair:known[pair] for pair in groups if pair in known})
        new = [pair for pair in groups if pair not in known]
        with ThreadPoolExecutor(max_workers=4) as pool:
            batches = [new[i:i+12] for i in range(0,len(new),12)]
            for scores in pool.map(lambda batch: grade_batch(client,batch,items,keys), batches):
                record(scores)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study',choices=run.STUDIES)
    parser.add_argument('--wait-for-reader',action='store_true')
    args=parser.parse_args()
    load_dotenv(run.REPO/'.env')
    with (run.RUN/f'{args.study}_grader.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.wait_for_reader:
            with run.db_open() as db:
                while not db.execute("SELECT 1 FROM observations WHERE study=? AND form='open' LIMIT 1",(args.study,)).fetchone():
                    time.sleep(12)
        grade(args.study)
