#!/usr/bin/env python3
"""Paired clean-passage free-response evaluation for Llama 3.2 3B."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import html
import json
import os
from pathlib import Path
import shutil
import sys
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import run_hard66_closed_book_recall as engine
from evaluation.scripts.mcq.diagnostics import run_llama32_closed_book_recall as closed

ROOT = REPO / 'evaluation/runs/hard66_open_book_llama323b_2026-10-28'
OUT = REPO / 'evaluation/reports/hard66_open_book_llama323b_2026-10-28'
CONFIG = ['llama323b', 'llama3.2:3b', None]
SYSTEM = '''You are taking an open-book Bible comprehension test. A passage is provided, but no answer choices. Answer using only the supplied passage. Give only the shortest direct answer in Simplified Chinese. If the passage does not give enough information to answer, or you cannot identify the event or person referred to by the question, answer only 我不知道. Do not guess, request a passage, explain your answer, or output your reasoning.'''
JUDGE_SYSTEM = engine.JUDGE_SYSTEM.replace(
    'Grade a closed-book answer against the supplied target answer and private clean reference passage. These reference materials were NOT shown to the answering model.',
    'Grade an open-book answer against the supplied target answer and clean reference passage. The answering model saw this passage and the question, but NOT the target answer.')


def messages_for(item):
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': '经文：\n' + item['private_clean_passage'] + '\n\n问题：' + item['question']}]


def cache_key(item, manifest):
    return engine.replay.digest({'config': CONFIG, 'messages': messages_for(item), 'settings': manifest['settings']})


def prepare():
    parent_path = closed.ROOT / 'manifest.json'
    parent = engine.replay.read(parent_path)
    assert engine.replay.read(closed.ROOT / 'state.json')['status'] == 'complete'
    manifest = copy.deepcopy(parent)
    manifest.update(created_at=time.time(), parent_manifest=str(parent_path), system=SYSTEM, judge_system=JUDGE_SYSTEM,
                    extension='Clean-passage free response paired with the completed Llama 3.2 3B closed-book test.',
                    design='Same 65 Hard66 questions, Chinese answer keys, free-response format, local model, generation settings, and substantive grading criteria as the closed-book test. Each question receives its clean local passage window from the existing evaluation. No answer choices, answer key, chapter reference header, examples, or previous turns are sent. The answer instruction is adapted from Bible recall to using only the supplied passage. The grading prompt changes only its description of whether the answer model saw the passage. This is a comparison of the two task conditions, not a passage-only prompt ablation.')
    paths = [parent_path, closed.OUT / 'results.json', closed.ROOT / 'model_inventory.json', Path(__file__)]
    for path in paths:
        manifest['source_hashes'][str(path)] = engine.replay.file_hash(path)
    assert len(manifest['items']) == 65
    assert len({i['question'] for i in manifest['items']}) == 65
    assert all(i['private_clean_passage'].strip() for i in manifest['items'])
    if (ROOT / 'manifest.json').exists():
        saved = engine.replay.read(ROOT / 'manifest.json')
        manifest['created_at'] = saved['created_at']
        assert saved == manifest, 'Frozen inputs changed.'
    else:
        engine.replay.write(ROOT / 'manifest.json', manifest)
    engine.replay.write(ROOT / 'prompts/llama323b.json', [{'id': i['id'], 'model': CONFIG[1], 'messages': messages_for(i)} for i in manifest['items']])
    snapshot = ROOT / 'code_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in (Path(__file__), Path(engine.__file__), Path(engine.replay.gen.__file__), Path(engine.replay.scoring.__file__)):
        shutil.copy2(path, snapshot / path.name)
    print(json.dumps({'questions': 65, 'model': CONFIG[1], 'condition': 'clean local passage + question; free response'}), flush=True)
    return manifest


def verify_sources(manifest):
    assert manifest['configs'] == [CONFIG]
    assert manifest['system'] == SYSTEM and manifest['judge_system'] == JUDGE_SYSTEM
    for path, sha in manifest['source_hashes'].items():
        assert engine.replay.file_hash(path) == sha, path
    parent = engine.replay.read(closed.ROOT / 'manifest.json')
    assert manifest['items'] == parent['items'] and manifest['settings'] == parent['settings']


def run(manifest):
    from dotenv import load_dotenv
    load_dotenv(REPO / '.env')
    url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
    models = engine.request_json(url + '/api/tags', timeout=20)['models']
    actual = next(m for m in models if m['name'] == CONFIG[1])
    prior = engine.replay.read(closed.ROOT / 'model_inventory.json')[0]
    assert actual['digest'] == prior['digest'], 'Model weights changed since the closed-book run.'
    by_question = {i['question']: i for i in manifest['items']}
    engine.CONFIGS = [CONFIG]
    engine.SYSTEM = SYSTEM
    engine.JUDGE_SYSTEM = JUDGE_SYSTEM
    # The original runner uses this hook for both request construction and cache identity.
    engine.messages_for = lambda question, thinking: messages_for(by_question[question])
    engine.run(ROOT, manifest)


def report(manifest):
    verify_sources(manifest)
    assert engine.replay.read(ROOT / 'state.json')['status'] == 'complete'
    overrides_path = ROOT / 'review_overrides.json'
    overrides = engine.replay.read(overrides_path) if overrides_path.exists() else []
    overrides = {(x['config'], x['id']): x['grade'] for x in overrides}
    prior = {r['id']: r for r in engine.replay.read(closed.OUT / 'results.json') if r['config'] == CONFIG[0]}
    rows = []
    limited = []
    for item in manifest['items']:
        cache = cache_key(item, manifest)
        a = engine.replay.read(ROOT / 'answers/llama323b' / f'{cache}.json')
        g = engine.replay.read(ROOT / 'grades/llama323b' / f'{cache}.json')
        assert a['request']['messages'] == messages_for(item)
        assert a['request']['model'] == CONFIG[1] and 'think' not in a['request']
        assert a['request']['options'] == {k: manifest['settings'][k] for k in ('temperature', 'num_ctx', 'num_predict')}
        assert not a['answer_effort'].get('thinking_chars', 0)
        assert a['id'] == item['id'] and prior[item['id']]['question'] == item['question']
        if a['raw_response'].get('done_reason') == 'length':
            limited.append(item['id'])
        opened = dict(answer=a['answer'], generation_error=a['generation_error'], automated_grade=g,
                      grade=overrides.get((CONFIG[0], item['id']), g),
                      answer_effort={k: v for k, v in a['answer_effort'].items() if k != 'thinking_text'})
        rows.append(dict(id=item['id'], question=item['question'], expected=item['expected'], reference=item['reference'],
                         passage=item['private_clean_passage'], closed_book=prior[item['id']], open_book=opened))
    assert len(rows) == len(prior) == 65
    summaries = []
    for condition in ('closed_book', 'open_book'):
        counts = Counter(r[condition]['grade']['label'] for r in rows)
        summaries.append(dict(condition=condition, n=65,
                              **{k: counts[k] for k in ('correct', 'partial', 'incorrect', 'unknown', 'failure')},
                              strict_accuracy=counts['correct']/65,
                              mean_score=sum(r[condition]['grade']['score'] for r in rows)/65))
    transitions = Counter((r['closed_book']['grade']['label'], r['open_book']['grade']['label']) for r in rows)
    summary = dict(model=CONFIG[1], configurations=summaries, design=manifest['design'],
                   strict_accuracy_change_pp=100*(summaries[1]['strict_accuracy']-summaries[0]['strict_accuracy']),
                   transitions=[dict(closed=a, open=b, count=n) for (a, b), n in sorted(transitions.items())],
                   review_overrides=len(overrides))
    OUT.mkdir(parents=True, exist_ok=True)
    engine.replay.write(OUT / 'results.json', rows)
    engine.replay.write(OUT / 'summary.json', summary)
    audit = dict(status='verified', responses=65, actual_passage_and_question_requests_checked=65,
                 no_choices_or_key_sent=True, same_model_weights=True, sources_unchanged=True,
                 closed_book_answers_reused_unchanged=True, token_limited_ids=limited, manual_overrides=len(overrides))
    engine.replay.write(ROOT / 'verification.json', audit)
    engine.replay.write(OUT / 'verification.json', audit)
    e = lambda x: html.escape(str(x))
    parts = ['<h1>Llama 3.2 3B · closed book vs. open book</h1><p>28 October 2026 · 65 active Hard66 questions · free response in both conditions</p>',
             '<div class="card"><b>Open book supplies each question’s clean local passage window.</b> No answer choices or answer key were supplied. Question wording, model weights, temperature, token limits, and substantive grading criteria match the closed-book run. The task instruction changes from recalling Bible knowledge to answering from the supplied passage. Each response starts a fresh conversation.</div>',
             '<table><tr><th>Condition</th><th>Fully correct</th><th>Partial</th><th>Incorrect</th><th>Does not know</th><th>Failed output</th></tr>']
    for s in summaries:
        parts.append(f'<tr><td>{e(s["condition"].replace("_", " "))}</td><td>{s["correct"]}/65 ({100*s["strict_accuracy"]:.1f}%)</td><td>{s["partial"]}</td><td>{s["incorrect"]}</td><td>{s["unknown"]}</td><td>{s["failure"]}</td></tr>')
    parts.append(f'</table><p>Full-correctness change: {summary["strict_accuracy_change_pp"]:+.1f} percentage points. Grading uses the Chinese key and clean passage, fixed rules for exact answers and abstentions, and gpt-4.1-mini for other responses. Partial answers score 0.5. Review corrections: {len(overrides)}. Original judgments are retained alongside reviewed grades.</p>')
    parts.append('<p>This compares two task conditions. Supplying the passage resolves context and supports answer retrieval; the result does not establish whether the model previously memorized these Bible facts.</p><h2>Paired answers and passages</h2>')
    for row in rows:
        parts.append('<details class="card"><summary>'+e(row['question'])+'</summary><p><b>Key:</b> '+e(row['expected'])+'<br><small>'+e(row['reference'])+' · '+e(row['id'])+'</small></p><p class="passage">'+e(row['passage'])+'</p><table><tr><th>Condition</th><th>Answer</th><th>Grade</th><th>Reason</th></tr>')
        for condition in ('closed_book', 'open_book'):
            a = row[condition]
            parts.append('<tr><td>'+e(condition.replace('_', ' '))+'</td><td>'+e(a['answer'] or '[empty]')+'</td><td>'+e(a['grade']['label'])+'</td><td>'+e(a['grade']['rationale'])+'</td></tr>')
        parts.append('</table></details>')
    parts.append('<p><a href="summary.json">Summary</a> · <a href="results.json">All paired answers</a> · <a href="verification.json">Verification</a></p>')
    style = 'body{font:16px/1.6 system-ui;background:#f4f6f8;color:#172b3b}main{max-width:1200px;margin:auto;padding:28px}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dce3e9}th{background:#e9eff4}.card{background:white;border:1px solid #dce3e9;border-radius:10px;padding:18px;margin:16px 0}.passage{white-space:pre-wrap;background:#f6f8fa;padding:16px}summary{cursor:pointer;font-weight:650;color:#145b81}small{color:#637584}a{color:#145b81}'
    (OUT / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Llama open-book comparison</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')
    print(json.dumps({'summary': summary, 'report': str(OUT / 'index.html')}, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'run', 'report', 'all'], default='all')
    args = parser.parse_args()
    manifest = prepare() if args.phase in ('prepare', 'all') else engine.replay.read(ROOT / 'manifest.json')
    verify_sources(manifest)
    if args.phase in ('run', 'all'):
        run(manifest)
    if args.phase in ('report', 'all'):
        report(manifest)


if __name__ == '__main__':
    main()
