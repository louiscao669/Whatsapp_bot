"""Apply the original choice-mapping prompt to unresolved primary-reader responses."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import time

from dotenv import load_dotenv

import run_sol_slide_experiment as run


def map_choices(study):
    db = run.db_open()
    db.execute("""CREATE TABLE IF NOT EXISTS mapped_choices
        (signature TEXT PRIMARY KEY, choice TEXT NOT NULL, model TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS mapped_observations
        (study TEXT,reader TEXT,condition TEXT,item TEXT,signature TEXT,
        PRIMARY KEY(study,reader,condition,item))""")
    items = {r['id']:r for r in run.source()[0] if r['source'] == run.STUDIES[study]}
    models = [run.model_name(*m) for m in run.MODELS[:4]]
    client = run.scoring.get_openai_client()
    while True:
        pending = db.execute("""
            SELECT o.model,o.condition,o.item,a.answer FROM observations o
            JOIN answers a ON o.request_hash=a.hash
            WHERE o.study=? AND o.form='mcq' AND o.model IN (?,?,?,?)
              AND o.outcome='invalid' AND length(trim(a.answer))>0
            ORDER BY o.rowid LIMIT 256""", (study,*models)).fetchall()
        if not pending:
            n = db.execute("""SELECT count(*) FROM observations
                WHERE study=? AND form='mcq' AND model IN (?,?,?,?)""", (study,*models)).fetchone()[0]
            if n == len(items)*len(models)*(len(run.FULL)+1):
                return
            time.sleep(12)
            continue
        records = defaultdict(list)
        payloads = {}
        for model, condition, item, answer in pending:
            choices = dict(zip("ABCDE", items[item]["choices"], strict=True))
            key = run.digest([run.JUDGE, choices, answer])
            records[key].append((model,condition,item))
            payloads[key] = (choices,answer)
        def select(key):
            choices,answer = payloads[key]
            choice = run.gen.openai_closest_mcq_choice(client, run.JUDGE, raw_answer=answer, choices=choices, retries=2)
            if choice not in tuple("ABCDE"):
                raise ValueError("Choice mapper returned an invalid label.")
            return key,choice
        known = dict(db.execute("SELECT signature,choice FROM mapped_choices"))
        def write(key,choice):
            with db:
                if key not in known:
                    db.execute("INSERT INTO mapped_choices VALUES(?,?,?)",(key,choice,run.JUDGE))
                for model,condition,item in records[key]:
                    outcome = "abstain" if choice=="E" else "correct" if choice==items[item]["correct"] else "incorrect"
                    db.execute("""UPDATE observations SET choice=?,outcome=?
                            WHERE study=? AND model=? AND condition=? AND item=? AND form='mcq' AND outcome='invalid'""",
                            (choice,outcome,study,model,condition,item))
                    db.execute("INSERT INTO mapped_observations VALUES(?,?,?,?,?)",(study,model,condition,item,key))
        for key in records.keys() & known.keys():
            write(key,known[key])
        with ThreadPoolExecutor(max_workers=6) as pool:
            for key,choice in pool.map(select,records.keys()-known.keys()):
                write(key,choice)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", choices=run.STUDIES)
    args=parser.parse_args()
    load_dotenv(run.REPO/".env")
    map_choices(args.study)
