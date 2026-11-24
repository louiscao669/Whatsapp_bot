"""Record Qwen's thinking and final answers for the corrected from-scratch WBW MCQs."""
from collections import Counter
import fcntl
from html import escape
import json
import sqlite3

import requests

import rerun_sol_wbw_names as exp

run = exp.run
MODEL = 'qwen3:1.7b'
READER = run.model_name(MODEL, True)
FOLDER = exp.FOLDER.with_name('sol_wbw_scratch66_qwen3_thinking_traces')
REPORT = exp.REPORT.with_name(FOLDER.name)


def paired_requests():
    rows, design, _, release, _ = exp.protocol()
    roster = [row for row in rows if row['source'] == run.STUDIES['scratch']]
    db_path = exp.FOLDER / 'observations.sqlite'
    with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
        prior = {item: (signature, choice, outcome) for item, signature, choice, outcome in db.execute(
            """SELECT item, request_hash, choice, outcome FROM observations
               WHERE study='scratch' AND condition='wbw' AND form='mcq' AND model=?""", (READER,))}
    if len(roster) != 66 or set(prior) != {row['id'] for row in roster}:
        raise ValueError('The bank and the previous corrected experiment must contain the same 66 items.')
    model_digest = design['models'][MODEL]
    jobs = []
    for row in roster:
        verses = release[row['passage_id']]['verses']
        passage = ' '.join(verses[v] for v in row['verses'])
        body, public = run.request_for(row, passage, MODEL, True, 'mcq', False)
        signature, choice, outcome = prior[row['id']]
        if signature != run.digest(['scratch', model_digest, body]):
            raise ValueError(f"Previous prompt differs for {row['id']}")
        jobs.append((row, passage, body, public, signature, choice, outcome))
    return jobs, model_digest


def record():
    jobs, model_digest = paired_requests()
    records = []
    with requests.Session() as session:
        response = session.get(run.LOCAL + '/api/tags', timeout=20)
        response.raise_for_status()
        if not any(m['name'] == MODEL and m['digest'] == model_digest for m in response.json()['models']):
            raise ValueError('The local Qwen model differs from the previous experiment.')
        for n, (row, passage, body, public, signature, old_choice, old_outcome) in enumerate(jobs, 1):
            path = FOLDER / 'items' / (signature + '.json')
            if path.exists():
                result = run.read(path)
            else:
                raw = run.infer_response(session, body)
                message = raw['message']
                trace = message.get('thinking')
                if not isinstance(trace, str) or not trace.strip():
                    raise ValueError(f"Missing thinking trace for {row['id']}")
                answer = run.gen.clean_raw_answer(message['content'])
                choice = run.gen.selected_choice_from_raw_answer(public, answer) if answer else None
                outcome = ('correct' if choice == row['correct'] else 'abstain' if choice == 'E'
                           else 'incorrect' if choice in ('A','B','C','D') else 'invalid')
                result = dict(id=row['id'], reference=row['reference'], question=row['question'],
                              passage=passage, choices=public['choices'], key=row['correct'],
                              model=READER, model_digest=model_digest, inference=body['options'],
                              request_hash=signature, thinking=trace, final_output=message['content'],
                              choice=choice, outcome=outcome, previous_choice=old_choice,
                              previous_outcome=old_outcome, prompt_tokens=raw.get('prompt_eval_count'),
                              generated_tokens=raw.get('eval_count'), done_reason=raw['done_reason'])
                run.save(path, result)
            if (result['request_hash'] != signature or result['id'] != row['id']
                    or not result['thinking'].strip() or result['previous_choice'] != old_choice):
                raise ValueError(f"Checkpoint mismatch for {row['id']}")
            records.append(result)
            print(f"{n}/{len(jobs)}  {row['reference']}  {result['outcome']}", flush=True)
    return records


def export(records):
    REPORT.mkdir(parents=True, exist_ok=True)
    export_path = REPORT / 'qwen3-thinking-traces.jsonl'
    tmp = export_path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    tmp.replace(export_path)
    counts = Counter(r['outcome'] for r in records)
    previous = Counter(r['previous_outcome'] for r in records)
    switches = sum(r['previous_choice'] != r['choice'] for r in records)
    lines = ['# Qwen 3 1.7B with thinking on corrected Google word-by-word passages', '',
             f"All {len(records)} from-scratch multiple-choice questions have a saved trace. "
             f"{switches} selections changed from the previous corrected experiment.", '',
             '| Result | Previous | Trace run |', '|---|---:|---:|']
    for outcome in ('correct','incorrect','abstain','invalid'):
        lines.append(f'| {outcome.title()} | {previous[outcome]} | {counts[outcome]} |')
    lines += ['', 'A dash indicates no selected answer. E is the cannot-tell option. '
              'Generated tokens include thinking and final output.', '',
              '| Passage | Question | Key | Previous | Trace run | Generated tokens |',
              '|---|---|---|---|---|---:|']
    for r in records:
        lines.append(f"| {r['reference']} | {r['question']} | {r['key']} | "
                     f"{r['previous_choice'] or '—'} | {r['choice'] or '—'} | {r['generated_tokens']} |")
    (REPORT / 'results.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    write_trace_view(records, counts)
    print(dict(counts), 'changed choices:', switches, flush=True)


def write_trace_view(records, counts):
    html = ['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qwen 3 · From-scratch multiple-choice traces</title>
<style>
body{max-width:960px;margin:2rem auto;padding:0 1rem 3rem;color:#193637;font:16px/1.55 system-ui,sans-serif}
h1{line-height:1.18}details{border-top:1px solid #cadcd9;padding:.75rem 0}
summary{cursor:pointer}summary strong,small{color:#446365}h2{font-size:1.1rem}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f6f5;padding:1rem;font:inherit}
</style><main><h1>Qwen 3 1.7B with thinking</h1>''',
            f'<p>Corrected Google word-by-word passages · {len(records)} from-scratch multiple-choice questions · '
            f'{counts["correct"]} correct</p>']
    for r in records:
        choice = r['choice'] or '—'
        old = r['previous_choice'] or '—'
        html.append(f'<details><summary><strong>{escape(r["reference"])}</strong> · '
                    f'{escape(r["question"])} <small>· {choice} · {r["outcome"]}</small></summary>'
                    f'<p lang="zh-Hans">{escape(r["passage"])}</p><ol type="A" lang="zh-Hans">')
        html.extend(f'<li>{escape(c)}</li>' for c in r['choices'].values())
        html.append(f'</ol><p>Key <b>{r["key"]}</b> · Previous choice <b>{old}</b> · '
                    f'Current choice <b>{choice}</b> · {r["generated_tokens"]} generated tokens · '
                    f'Stop reason <b>{escape(r["done_reason"])}</b></p>'
                    f'<h2>Recorded thinking</h2><pre>{escape(r["thinking"])}</pre>'
                    f'<h2>Final output</h2><pre>{escape(r["final_output"]) or "(empty)"}</pre></details>')
    html.append('</main></html>')
    (REPORT / 'trace-review.html').write_text('\n'.join(html), encoding='utf-8')


if __name__ == '__main__':
    FOLDER.mkdir(parents=True, exist_ok=True)
    with (FOLDER / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        export(record())
