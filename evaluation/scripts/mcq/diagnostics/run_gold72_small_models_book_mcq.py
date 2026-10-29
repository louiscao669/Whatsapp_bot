#!/usr/bin/env python3
"""Compare three additional small models on the frozen Gold72 book MCQs."""
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
from evaluation.scripts.mcq.diagnostics import run_gold72_llama_book_mcq as gold

mcq = gold.mcq
data = gold.data
ROOT = REPO / 'evaluation/runs/gold72_small_models_book_mcq_2026-10-28'
OUT = REPO / 'evaluation/reports/gold72_small_models_book_mcq_2026-10-28'
MODELS = [('gemma34b', 'gemma3:4b'), ('phi4mini38b', 'phi4-mini:3.8b'), ('qwen253b', 'qwen2.5:3b')]
LABELS = {'gemma34b': 'Gemma 3 4B', 'phi4mini38b': 'Phi-4-mini 3.8B',
          'qwen253b': 'Qwen2.5 3B', 'llama323b': 'Llama 3.2 3B'}
ARMS = [dict(config=config, model=model, thinking=None, condition=condition)
        for config, model in MODELS for condition in ('closed_book', 'open_book')]
OUTCOMES = ('correct', 'incorrect_ad', 'abstain_e', 'invalid', 'failure')


def prepare():
    parent = data.read(gold.ROOT / 'manifest.json')
    gold.verify_sources(parent)
    sources = copy.deepcopy(parent['source_hashes'])
    paths = [gold.ROOT / 'manifest.json', gold.OUT / 'results.json', gold.OUT / 'summary.json',
             gold.OUT / 'verification.json', Path(__file__)]
    for path in paths:
        sources[str(path)] = data.file_hash(path)
    manifest = dict(version=1, dataset='Gold72', active_mcqs=71,
                    items=copy.deepcopy(parent['items']), arms=ARMS,
                    settings=copy.deepcopy(parent['settings']), systems=mcq.SYSTEMS,
                    closed_e=mcq.CLOSED_E, source_hashes=sources, created_at=time.time(),
                    design='71 active accepted Gold72 MCQs, three new models, closed book and clean open book: 426 new responses. Questions, A-D choices, order, clean passage windows, system/user messages, generation settings and direct A-E scoring match the previous Llama 3.2 3B experiment. Only the model changes. Closed-book E means unable to determine from existing knowledge; open-book E means insufficient passage information. The earlier 142 Llama responses are reused only for comparison. No answer key, reference header, examples or previous turns are sent. No LLM judge, random fallback or imputed E. Each condition has one response per question.')
    assert len(manifest['items']) == len({i['id'] for i in manifest['items']}) == 71
    for arm in ARMS:
        old_arm = next(a for a in parent['arms'] if a['condition'] == arm['condition'])
        for item in manifest['items']:
            new = mcq.payload_for(item, arm, manifest['settings'])
            previous = mcq.payload_for(item, old_arm, parent['settings'])
            new['model'] = previous['model']
            assert new == previous, 'Protocol must match the completed Llama run.'
    if (ROOT / 'manifest.json').exists():
        saved = data.read(ROOT / 'manifest.json')
        manifest['created_at'] = saved['created_at']
        assert saved == manifest, 'Frozen experiment changed.'
    else:
        data.write(ROOT / 'manifest.json', manifest)
    for arm in ARMS:
        data.write(ROOT / 'prompts' / f'{mcq.arm_id(arm)}.json',
                   [{'id': i['id'], 'request': mcq.payload_for(i, arm, manifest['settings'])} for i in manifest['items']])
    snapshot = ROOT / 'code_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in [Path(__file__), Path(gold.__file__), Path(mcq.__file__), Path(mcq.base.__file__),
                 Path(data.__file__), Path(gold.gen.__file__)]:
        shutil.copy2(path, snapshot / path.name)
    print(json.dumps({'prepared': True, 'questions': 71, 'new_responses': 426,
                      'all_requests_match_llama_protocol_except_model': True}), flush=True)
    return manifest


def verify_sources(manifest):
    assert manifest['arms'] == ARMS and manifest['systems'] == mcq.SYSTEMS and manifest['closed_e'] == mcq.CLOSED_E
    for path, sha in manifest['source_hashes'].items():
        assert data.file_hash(path) == sha, f'Source changed: {path}'


def run(manifest):
    from dotenv import load_dotenv
    verify_sources(manifest)
    load_dotenv(REPO / '.env')
    url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
    available = mcq.base.request_json(url + '/api/tags', timeout=20)['models']
    names = {model for _, model in MODELS}
    selected = [m for m in available if m['name'] in names]
    assert {m['name'] for m in selected} == names, 'Download all three models before running.'
    inventory_path = ROOT / 'model_inventory.json'
    if inventory_path.exists():
        frozen = data.read(inventory_path)
        assert {m['name']: m['digest'] for m in frozen} == {m['name']: m['digest'] for m in selected}, 'Model weights changed.'
    else:
        data.write(inventory_path, selected)
    for name in sorted(names):
        path = ROOT / 'model_metadata' / (name.replace(':', '_') + '.json')
        if not path.exists():
            data.write(path, mcq.base.request_json(url + '/api/show', {'model': name}, timeout=30))
    total = len(ARMS) * len(manifest['items'])
    state = dict(status='running', total=total, completed=0, started_at=time.time())
    data.write(ROOT / 'state.json', state)
    try:
        for arm in ARMS:
            counts = Counter()
            for item in manifest['items']:
                state.update(current_arm=mcq.arm_id(arm), current_question=item['id'])
                data.write(ROOT / 'state.json', state)
                cache = mcq.cache_key(item, arm, manifest['settings'])
                path = ROOT / 'answers' / mcq.arm_id(arm) / f'{cache}.json'
                if path.exists():
                    answer = data.read(path)
                else:
                    print(f'MCQ {state["completed"] + 1}/{total} {mcq.arm_id(arm)} {item["id"]}', flush=True)
                    answer = mcq.generate(item, arm, manifest['settings'], url)
                    data.write(path, answer)
                assert answer['request'] == mcq.payload_for(item, arm, manifest['settings'])
                grade = mcq.score(answer, item, arm)
                data.write(ROOT / 'scores' / mcq.arm_id(arm) / f'{cache}.json', grade)
                counts[grade['label']] += 1
                state['completed'] += 1
                state['current_arm_outcomes'] = dict(counts)
                data.write(ROOT / 'state.json', state)
            print(json.dumps({'arm_complete': mcq.arm_id(arm), 'counts': counts}), flush=True)
        state.update(status='complete', finished_at=time.time())
    except Exception as exc:
        state.update(status='failed', error=str(exc), finished_at=time.time())
        raise
    finally:
        data.write(ROOT / 'state.json', state)


def report(manifest):
    verify_sources(manifest)
    assert data.read(ROOT / 'state.json')['status'] == 'complete'
    rows = []
    limits = []
    for arm in ARMS:
        for item in manifest['items']:
            cache = mcq.cache_key(item, arm, manifest['settings'])
            answer = data.read(ROOT / 'answers' / mcq.arm_id(arm) / f'{cache}.json')
            grade = data.read(ROOT / 'scores' / mcq.arm_id(arm) / f'{cache}.json')
            assert answer['id'] == item['id'] and answer['request'] == mcq.payload_for(item, arm, manifest['settings'])
            assert grade == mcq.score(answer, item, arm)
            assert answer['raw_response']['model'] == arm['model']
            if answer['raw_response'].get('done_reason') == 'length':
                limits.append(dict(arm=mcq.arm_id(arm), id=item['id']))
            rows.append(dict(id=item['id'], dataset='Gold72', arm=mcq.arm_id(arm), **arm,
                             question=item['question'], choices=mcq.displayed_choices(item, arm['condition']),
                             correct_choice=item['correct'], expected=item['expected'], answer=answer['answer'],
                             generation_error=answer['generation_error'], grade=grade,
                             answer_effort={k: v for k, v in answer['answer_effort'].items() if k != 'thinking_text'},
                             result_origin='new_run'))
    assert len(rows) == len({(r['arm'], r['id']) for r in rows}) == 426
    baseline = data.read(gold.OUT / 'results.json')
    assert len(baseline) == len({(r['arm'], r['id']) for r in baseline}) == 142
    item_map = {i['id']: i for i in manifest['items']}
    for row in baseline:
        item = item_map[row['id']]
        assert row['question'] == item['question'] and row['correct_choice'] == item['correct']
        assert row['choices'] == mcq.displayed_choices(item, row['condition'])
        assert row['grade'] == mcq.score(row, item, row)
    all_rows = [dict(r, result_origin='previous_llama_run') for r in baseline] + rows
    all_arms = gold.ARMS + ARMS
    summaries = []
    for arm in all_arms:
        subset = [r for r in all_rows if r['arm'] == mcq.arm_id(arm)]
        assert len(subset) == 71
        counts = Counter(r['grade']['label'] for r in subset)
        summaries.append(dict(arm=mcq.arm_id(arm), **arm, n=71, **{k: counts[k] for k in OUTCOMES},
                              accuracy=counts['correct']/71, result_origin=subset[0]['result_origin']))
    lookup = {(r['config'], r['condition'], r['id']): r for r in all_rows}
    transitions = []
    for config in LABELS:
        pairs = Counter((lookup[config, 'closed_book', i['id']]['grade']['label'],
                         lookup[config, 'open_book', i['id']]['grade']['label']) for i in manifest['items'])
        rates = {s['condition']: s['accuracy'] for s in summaries if s['config'] == config}
        transitions.append(dict(config=config, accuracy_change_pp=100*(rates['open_book']-rates['closed_book']),
                                pairs=[dict(closed=a, open=b, count=n) for (a, b), n in sorted(pairs.items())]))
    summary = dict(configurations=summaries, transitions=transitions, design=manifest['design'])
    audit = dict(status='verified', active_mcqs=71, new_requests_checked=426, baseline_responses_reused=142,
                 sources_unchanged=True, all_new_requests_match_llama_protocol_except_model=True,
                 original_ad_options_and_order_preserved=True, clean_windows_match_llama=True,
                 no_answer_keys_or_reference_headers_sent=True, direct_scores_verified=568,
                 invalid_outputs=sum(s['invalid'] for s in summaries), failed_outputs=sum(s['failure'] for s in summaries),
                 token_limited_outputs=limits)
    OUT.mkdir(parents=True, exist_ok=True)
    data.write(OUT / 'results.json', all_rows)
    data.write(OUT / 'summary.json', summary)
    data.write(OUT / 'verification.json', audit)
    data.write(ROOT / 'verification.json', audit)
    render(manifest, all_rows, summaries, transitions)
    print(json.dumps({'configurations': summaries, 'report': str(OUT / 'index.html')}, indent=2), flush=True)


def render(manifest, rows, summaries, transitions):
    e = lambda value: html.escape(str(value))
    parts = ['<h1>Gold72 · small-model MCQ comparison</h1><p>71 active questions · closed book and clean open book · 28 October 2026</p>',
             '<div class="card">426 new responses from Gemma 3 4B, Phi-4-mini 3.8B and Qwen2.5 3B, compared with 142 saved Llama 3.2 3B responses. Every model receives the same questions, A–D options, passage windows and instructions. E is shown separately.</div>',
             '<table><tr><th>Model</th><th>Condition</th><th>Correct</th><th>Wrong A–D</th><th>E</th><th>Invalid</th><th>Failed</th></tr>']
    for s in summaries:
        parts.append(f'<tr><td>{e(LABELS[s["config"]])}</td><td>{e(s["condition"].replace("_", " "))}</td><td><b>{s["correct"]}/71 ({100*s["accuracy"]:.1f}%)</b></td><td>{s["incorrect_ad"]}</td><td>{s["abstain_e"]}</td><td>{s["invalid"]}</td><td>{s["failure"]}</td></tr>')
    parts.append('</table><p>Closed book supplies only the question and choices; E means “'+e(mcq.CLOSED_E)+'”. Open book adds the curated clean passage; E retains its original meaning, “cannot determine from this passage”. These E rates represent different decisions. No missing-information passage condition is tested in this run.</p><h2>What changes when the passage is supplied?</h2><table><tr><th>Model</th><th>Accuracy change</th><th>Correct in both</th><th>Becomes correct</th><th>Loses correct answer</th></tr>')
    for t in transitions:
        both = sum(p['count'] for p in t['pairs'] if p['closed'] == p['open'] == 'correct')
        gain = sum(p['count'] for p in t['pairs'] if p['closed'] != 'correct' and p['open'] == 'correct')
        loss = sum(p['count'] for p in t['pairs'] if p['closed'] == 'correct' and p['open'] != 'correct')
        parts.append(f'<tr><td>{e(LABELS[t["config"]])}</td><td>{t["accuracy_change_pp"]:+.1f} percentage points</td><td>{both}</td><td>{gain}</td><td>{loss}</td></tr>')
    parts.append('</table><p>Closed-book success can reflect prior knowledge, recognition, answer-choice cues, elimination or guessing. It does not establish Bible memorization. A low closed-book score may also reflect abstention. Compare these results with clean-passage comprehension and future information-removal controls.</p><details class="card"><summary>Protocol and reproducibility</summary><p>One fresh conversation per question and condition. Temperature 0; context 8,192; output limit 2,500 tokens. No answer keys, reference headers, examples or previous turns are supplied. Scoring uses the frozen A–E parser, with no model judge or random fallback. Model digests, metadata, complete requests and raw responses are saved. Gold72 is the dataset name; the accepted current export contains 71 active MCQs.</p></details><h2>Question-level comparison</h2>')
    lookup = {(r['config'], r['condition'], r['id']): r for r in rows}
    for item in manifest['items']:
        parts.append('<details class="card"><summary>'+e(item['question'])+'</summary><p><b>Key:</b> '+e(item['correct'])+' · '+e(item['expected'])+'<br><small>'+e(item['id'])+' · '+e(item['reference'])+'</small></p><ul>'+''.join('<li><b>'+k+':</b> '+e(item['choices'][k])+'</li>' for k in 'ABCD')+'</ul><table><tr><th>Model</th><th>Condition</th><th>Raw final answer</th><th>Selected</th><th>Outcome</th></tr>')
        for config in ['llama323b'] + [c for c, _ in MODELS]:
            for condition in ('closed_book', 'open_book'):
                r = lookup[config, condition, item['id']]
                parts.append('<tr><td>'+e(LABELS[config])+'</td><td>'+e(condition.replace('_', ' '))+'</td><td>'+e(r['answer'] or '[empty]')+'</td><td>'+e(r['grade']['selected_choice'] or '—')+'</td><td>'+e(r['grade']['label'])+'</td></tr>')
        parts.append('</table><details><summary>Clean passage, supplied only in open book</summary><p class="passage">'+e(item['private_clean_passage'])+'</p></details></details>')
    parts.append('<p><a href="summary.json">Summary data</a> · <a href="results.json">All results</a> · <a href="verification.json">Verification</a></p>')
    style = 'body{font:16px/1.6 system-ui;background:#f4f6f8;color:#172b3b}main{max-width:1200px;margin:auto;padding:28px}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dce3e9}td{overflow-wrap:anywhere}th{background:#e9eff4}.card{background:white;border:1px solid #dce3e9;border-radius:10px;padding:18px;margin:16px 0}.passage{white-space:pre-wrap;background:#f6f8fa;padding:16px}summary{cursor:pointer;font-weight:650;color:#145b81}a{color:#145b81}'
    (OUT / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gold72 small-model MCQ comparison</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'run', 'report', 'all'], default='all')
    args = parser.parse_args()
    manifest = prepare() if args.phase in ('prepare', 'all') else data.read(ROOT / 'manifest.json')
    verify_sources(manifest)
    if args.phase in ('run', 'all'):
        run(manifest)
    if args.phase in ('report', 'all'):
        report(manifest)


if __name__ == '__main__':
    main()
