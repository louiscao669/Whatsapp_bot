#!/usr/bin/env python3
"""MCQ versions of the five completed Hard66 closed/open-book free-response arms."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import unicodedata

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import run_hard66_closed_book_recall as base
from evaluation.scripts.mcq.diagnostics import run_llama32_closed_book_recall as llama_closed
from evaluation.scripts.mcq.diagnostics import run_llama32_open_book as llama_open

ROOT = REPO / 'evaluation/runs/hard66_book_mcq_2026-10-28'
OUT = REPO / 'evaluation/reports/hard66_book_mcq_2026-10-28'
CLOSED_E = '我不知道／无法根据已有知识确定'
SYSTEMS = {
    'closed_book': 'You are taking a closed-book Bible multiple-choice test. No passage is provided. Answer using your existing knowledge of the Bible and the question and choices. Choose the correct answer from A, B, C, or D. Choose E if you do not know, cannot remember, or cannot identify the event or person referred to. E means that you cannot determine the answer from your existing knowledge; do not choose E merely because no passage is provided. Do not guess. Return only one uppercase letter: A, B, C, D, or E. Do not explain your answer or output your reasoning.',
    'open_book': 'You are taking an open-book Bible multiple-choice comprehension test. Answer using only the supplied passage. Choose the correct answer from A, B, C, or D. If the passage does not give enough information to answer, choose E. E means that the answer cannot be determined from the supplied passage. Do not guess. Return only one uppercase letter: A, B, C, D, or E. Do not explain your answer or output your reasoning.',
}
ARMS = [
    dict(config='qwen2515b', model='qwen2.5:1.5b', thinking=None, condition='closed_book'),
    dict(config='qwen317b_nothink', model='qwen3:1.7b', thinking=False, condition='closed_book'),
    dict(config='llama323b', model='llama3.2:3b', thinking=None, condition='closed_book'),
    dict(config='llama323b', model='llama3.2:3b', thinking=None, condition='open_book'),
    dict(config='qwen317b_think', model='qwen3:1.7b', thinking=True, condition='closed_book'),
]
LABELS = {**base.previous.LABELS, 'llama323b': 'Meta Llama 3.2 3B'}


def arm_id(arm):
    return arm['config'] + '_' + arm['condition']


def displayed_choices(item, condition):
    choices = dict(item['choices'])
    if condition == 'closed_book':
        choices['E'] = CLOSED_E
    return choices


def messages_for(item, arm):
    choices = displayed_choices(item, arm['condition'])
    text = '/no_think\n\n' if arm['thinking'] is False else ''
    if arm['condition'] == 'open_book':
        text += '经文：\n' + item['private_clean_passage'] + '\n\n'
    text += '问题：' + item['question'] + '\n\n选项：\n' + '\n'.join(f'{k}. {choices[k]}' for k in 'ABCDE')
    return [{'role': 'system', 'content': SYSTEMS[arm['condition']]}, {'role': 'user', 'content': text}]


def parse_choice(answer, choices):
    """Accept explicit single labels or exact option text; never choose a fallback."""
    text = unicodedata.normalize('NFKC', answer).strip().replace('**', '').strip('`').strip()
    direct = re.fullmatch(r'[\[(]?\s*([A-Ea-e])\s*[\])]?[.。!！]?', text)
    if direct:
        return direct[1].upper(), 'single_letter'
    tokens = {s.upper() for s in re.findall(r'(?<![A-Za-z])([A-Ea-e])(?![A-Za-z])', text)}
    labeled = re.match(r'^(?:(?:答案|正确答案|选项|选择|Answer|Option|Selected_choice)\s*(?:是|为)?\s*[:：]?\s*)?([A-Ea-e])(?:[.。:：、)\s]|$)', text, re.I)
    if labeled and tokens == {labeled[1].upper()}:
        return labeled[1].upper(), 'explicit_label'
    matches = [k for k, value in choices.items() if base.normalize(text) == base.normalize(value)]
    if len(matches) == 1:
        return matches[0], 'exact_option_text'
    return None, 'unresolved'


def score(answer, item, arm):
    if answer['generation_error']:
        return dict(label='failure', selected_choice=None, score=0, parser='generation_failure')
    choice, method = parse_choice(answer['answer'], displayed_choices(item, arm['condition']))
    label = 'invalid' if choice is None else 'abstain_e' if choice == 'E' else 'correct' if choice == item['correct'] else 'incorrect_ad'
    return dict(label=label, selected_choice=choice, score=int(label == 'correct'), parser=method)


def payload_for(item, arm, settings):
    request = dict(model=arm['model'], stream=False, messages=messages_for(item, arm),
                   options={k: settings[k] for k in ('temperature', 'num_ctx', 'num_predict')})
    if arm['thinking'] is not None:
        request['think'] = arm['thinking']
    return request


def cache_key(item, arm, settings):
    return base.replay.digest(payload_for(item, arm, settings))


def prepare():
    parent_path = base.DEFAULT_ROOT / 'manifest.json'
    parent = base.replay.read(parent_path)
    sources = copy.deepcopy(parent['source_hashes'])
    qa = {}
    for path in sources:
        if not path.endswith('qa_target_decanonicalized.json'):
            continue
        for q in base.replay.read(path):
            if q.get('q_type') != 'mcq':
                continue
            key = q.get('id') or q['passage_id']
            assert key not in qa
            qa[key] = q
    items = copy.deepcopy(parent['items'])
    for item in items:
        q = qa[item['id']]
        assert q['Q'] == item['question'] and q['A'][q['correct']] == item['expected']
        assert set(q['A']) == set('ABCDE') and q['correct'] in 'ABCD'
        item.update(choices=copy.deepcopy(q['A']), correct=q['correct'])
    assert len(items) == len({i['id'] for i in items}) == 65
    dependencies = [parent_path, llama_closed.ROOT / 'model_inventory.json', base.DEFAULT_ROOT / 'model_inventory.json',
                    llama_closed.OUT / 'results.json', llama_open.OUT / 'results.json',
                    Path(__file__), Path(base.__file__), Path(base.replay.gen.__file__)]
    for path in dependencies:
        sources[str(path)] = base.replay.file_hash(path)
    inventories = base.replay.read(dependencies[1]) + base.replay.read(dependencies[2])
    digests = {m['name']: m['digest'] for m in inventories}
    settings = {k: parent['settings'][k] for k in ('temperature', 'num_ctx', 'num_predict', 'timeout_seconds')}
    manifest = dict(version=1, dataset='Hard66', items=items, arms=ARMS, systems=SYSTEMS, closed_e=CLOSED_E,
                    settings=settings, model_digests=digests, source_hashes=sources, created_at=time.time(),
                    design='65 active rewritten Hard66 MCQs. Four closed-book configurations (Qwen 1.5B, Qwen3 1.7B with and without thinking, Llama 3.2 3B), plus clean-passage open-book Llama 3.2 3B: 325 responses. Original A-D options and order are unchanged. Closed-book E explicitly means unable to answer from prior knowledge; open-book E retains the original passage-insufficiency meaning. No answer key or reference header is sent. Each request is a fresh conversation. Same model weights, generation settings and local passage windows as the free-response tests. Direct deterministic letter scoring; no judge, random fallback, or imputed E. Closed-book MCQ success can reflect knowledge, recognition, elimination, wording cues or guessing; it does not prove Bible memorization. E rates have condition-specific meanings.')
    if (ROOT / 'manifest.json').exists():
        saved = base.replay.read(ROOT / 'manifest.json')
        manifest['created_at'] = saved['created_at']
        assert saved == manifest, 'Frozen experiment changed.'
    else:
        base.replay.write(ROOT / 'manifest.json', manifest)
    for arm in ARMS:
        base.replay.write(ROOT / 'prompts' / f'{arm_id(arm)}.json', [{'id': i['id'], 'request': payload_for(i, arm, settings)} for i in items])
    snapshot = ROOT / 'code_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in dependencies[5:]:
        shutil.copy2(path, snapshot / path.name)
    print(json.dumps({'questions': 65, 'arms': 5, 'responses': 325}), flush=True)
    return manifest


def verify_sources(manifest):
    assert manifest['arms'] == ARMS and manifest['systems'] == SYSTEMS and manifest['closed_e'] == CLOSED_E
    for path, sha in manifest['source_hashes'].items():
        assert base.replay.file_hash(path) == sha, path


def generate(item, arm, settings, url):
    payload = payload_for(item, arm, settings)
    for attempt in range(3):
        try:
            raw = base.request_json(url + '/api/chat', payload, settings['timeout_seconds'])
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    content = str((raw.get('message') or {}).get('content') or '').strip()
    answer = re.sub(r'<think>.*?</think>', '', content, flags=re.S).strip()
    effort = base.replay.gen.ollama_effort(raw, content)
    if arm['thinking'] is False:
        assert not effort.get('thinking_chars', 0), 'Unexpected reasoning in no-thinking mode.'
    return dict(id=item['id'], arm=arm_id(arm), model=arm['model'], condition=arm['condition'],
                answer=answer, generation_error=None if answer else 'empty_response',
                answer_effort=effort, request=payload, raw_response=raw, completed_at=time.time())


def run(manifest):
    from dotenv import load_dotenv
    verify_sources(manifest)
    load_dotenv(REPO / '.env')
    url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
    models = base.request_json(url + '/api/tags', timeout=20)['models']
    selected = [m for m in models if m['name'] in {a['model'] for a in ARMS}]
    assert {m['name'] for m in selected} == {a['model'] for a in ARMS}
    assert all(m['digest'] == manifest['model_digests'][m['name']] for m in selected), 'Model weights changed.'
    base.replay.write(ROOT / 'model_inventory.json', selected)
    state = dict(status='running', total=325, completed=0, started_at=time.time())
    base.replay.write(ROOT / 'state.json', state)
    try:
        for arm in ARMS:
            for item in manifest['items']:
                state.update(current_arm=arm_id(arm), current_question=item['id'])
                base.replay.write(ROOT / 'state.json', state)
                cache = cache_key(item, arm, manifest['settings'])
                ap = ROOT / 'answers' / arm_id(arm) / f'{cache}.json'
                if ap.exists():
                    answer = base.replay.read(ap)
                else:
                    print(f'MCQ {state["completed"]+1}/325 {arm_id(arm)} {item["id"]}', flush=True)
                    answer = generate(item, arm, manifest['settings'], url)
                    base.replay.write(ap, answer)
                base.replay.write(ROOT / 'scores' / arm_id(arm) / f'{cache}.json', score(answer, item, arm))
                state['completed'] += 1
                base.replay.write(ROOT / 'state.json', state)
        state.update(status='complete', finished_at=time.time())
    except Exception as exc:
        state.update(status='failed', error=str(exc), finished_at=time.time())
        raise
    finally:
        base.replay.write(ROOT / 'state.json', state)


def report(manifest):
    verify_sources(manifest)
    assert base.replay.read(ROOT / 'state.json')['status'] == 'complete'
    inventory = base.replay.read(ROOT / 'model_inventory.json')
    assert all(m['digest'] == manifest['model_digests'][m['name']] for m in inventory)
    free_closed = {(r['config'], r['id']): r for r in base.replay.read(llama_closed.OUT / 'results.json')}
    free_open = {r['id']: r['open_book'] for r in base.replay.read(llama_open.OUT / 'results.json')}
    rows = []; summaries = []; limits = []
    for arm in ARMS:
        subset = []
        for item in manifest['items']:
            cache = cache_key(item, arm, manifest['settings'])
            answer = base.replay.read(ROOT / 'answers' / arm_id(arm) / f'{cache}.json')
            grade = base.replay.read(ROOT / 'scores' / arm_id(arm) / f'{cache}.json')
            assert answer['request'] == payload_for(item, arm, manifest['settings'])
            assert answer['id'] == item['id'] and grade == score(answer, item, arm)
            if arm['thinking'] is False:
                assert not answer['answer_effort'].get('thinking_chars', 0)
            if answer['raw_response'].get('done_reason') == 'length':
                limits.append(dict(arm=arm_id(arm), id=item['id']))
            free = free_open[item['id']] if arm['condition'] == 'open_book' else free_closed[arm['config'], item['id']]
            row = dict(id=item['id'], arm=arm_id(arm), **arm, question=item['question'], choices=displayed_choices(item, arm['condition']),
                       correct_choice=item['correct'], expected=item['expected'], answer=answer['answer'],
                       generation_error=answer['generation_error'], grade=grade,
                       answer_effort={k: v for k, v in answer['answer_effort'].items() if k != 'thinking_text'},
                       free_response_answer=free['answer'], free_response_grade=free['grade'])
            subset.append(row); rows.append(row)
        counts = Counter(r['grade']['label'] for r in subset)
        summaries.append(dict(arm=arm_id(arm), **arm, n=65,
                              **{k: counts[k] for k in ('correct', 'incorrect_ad', 'abstain_e', 'invalid', 'failure')},
                              accuracy=counts['correct']/65,
                              free_response_correct=sum(r['free_response_grade']['label'] == 'correct' for r in subset)))
    assert len(rows) == 325 and len({(r['arm'], r['id']) for r in rows}) == 325
    OUT.mkdir(parents=True, exist_ok=True)
    base.replay.write(OUT / 'results.json', rows)
    base.replay.write(OUT / 'summary.json', dict(configurations=summaries, design=manifest['design']))
    audit = dict(status='verified', actual_requests_checked=325, deterministic_scores_checked=325,
                 sources_unchanged=True, model_weights_unchanged=True, no_answer_keys_or_reference_headers_sent=True,
                 original_ad_options_and_order_preserved=True, e_meaning_adapted_for_closed_book=True,
                 invalid_answers=sum(s['invalid'] for s in summaries), failed_outputs=sum(s['failure'] for s in summaries),
                 token_limited_outputs=limits)
    base.replay.write(ROOT / 'verification.json', audit); base.replay.write(OUT / 'verification.json', audit)
    e = lambda x: html.escape(str(x))
    parts = ['<h1>Hard66 · closed-book and open-book MCQ</h1><p>28 October 2026 · 65 questions · 325 new responses · direct A–E scoring</p>',
             '<div class="card"><b>These tests include answer choices.</b> A–D are unchanged from the accepted Hard66 set. In closed book, E reads “'+e(CLOSED_E)+'” and means unable to answer from prior knowledge. In open book, E retains “cannot determine from this passage.” Closed book gives only the question and choices; open book adds the same clean local passage window used in the earlier free-response test. These two E rates represent different abstention decisions.</div>',
             '<table><tr><th>Model</th><th>Condition</th><th>Correct</th><th>Wrong A–D</th><th>E</th><th>Invalid / failed</th><th>Earlier free-response correct</th></tr>']
    for s in summaries:
        parts.append(f'<tr><td>{e(LABELS[s["config"]])}</td><td>{e(s["condition"].replace("_"," "))}</td><td>{s["correct"]}/65 ({100*s["accuracy"]:.1f}%)</td><td>{s["incorrect_ad"]}</td><td>{s["abstain_e"]}</td><td>{s["invalid"]} / {s["failure"]}</td><td>{s["free_response_correct"]}/65</td></tr>')
    parts.append('</table><p>One response per question and condition; temperature 0, context limit 8,192, output limit 2,500 tokens. Model weights match the earlier runs. Selected letters are compared directly with the saved answer key, with E reported separately. Empty or unparseable outputs are not replaced by a random option or E. No model grader is used.</p><p>Closed-book MCQ accuracy can reflect prior knowledge, recognition, elimination, wording cues, or guessing. Higher accuracy than free response does not by itself establish memorized Bible knowledge. Some questions depend on absent passage context.</p><h2>Question-level comparison</h2>')
    lookup = {(r['arm'], r['id']): r for r in rows}
    for item in manifest['items']:
        parts.append('<details class="card"><summary>'+e(item['question'])+'</summary><p><b>Key:</b> '+e(item['correct'])+' · '+e(item['expected'])+'</p><ul>'+''.join('<li><b>'+k+':</b> '+e(item['choices'][k])+'</li>' for k in 'ABCD')+'</ul><table><tr><th>Model / condition</th><th>MCQ output</th><th>Outcome</th><th>Earlier free response</th></tr>')
        for arm in ARMS:
            r = lookup[arm_id(arm), item['id']]
            parts.append('<tr><td>'+e(LABELS[arm['config']])+' · '+e(arm['condition'].replace('_',' '))+'</td><td>'+e(r['answer'] or '[empty]')+'</td><td>'+e(r['grade']['label'])+'</td><td>'+e(r['free_response_answer'] or '[empty]')+'</td></tr>')
        parts.append('</table><details><summary>Clean passage (sent only in the open-book condition)</summary><p class="passage">'+e(item['private_clean_passage'])+'</p></details></details>')
    parts.append('<p><a href="summary.json">Summary data</a> · <a href="results.json">All results</a> · <a href="verification.json">Verification</a></p>')
    style = 'body{font:16px/1.6 system-ui;background:#f4f6f8;color:#172b3b}main{max-width:1280px;margin:auto;padding:28px}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dce3e9}th{background:#e9eff4}.card{background:white;border:1px solid #dce3e9;border-radius:10px;padding:18px;margin:16px 0}.passage{white-space:pre-wrap;background:#f6f8fa;padding:16px}summary{cursor:pointer;font-weight:650;color:#145b81}a{color:#145b81}'
    (OUT / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hard66 book MCQ comparison</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')
    print(json.dumps({'summary': summaries, 'report': str(OUT / 'index.html')}, ensure_ascii=False, indent=2), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase', choices=['prepare', 'run', 'report', 'all'], default='all')
    args = p.parse_args()
    manifest = prepare() if args.phase in ('prepare', 'all') else base.replay.read(ROOT / 'manifest.json')
    verify_sources(manifest)
    if args.phase in ('run', 'all'):
        run(manifest)
    if args.phase in ('report', 'all'):
        report(manifest)


if __name__ == '__main__':
    main()
