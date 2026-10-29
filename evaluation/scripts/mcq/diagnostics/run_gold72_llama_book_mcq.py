#!/usr/bin/env python3
"""Gold72 closed/open-book MCQs using the frozen Hard66 Llama protocol."""
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
from evaluation.scripts.mcq.diagnostics import run_hard66_book_mcq as mcq

data = mcq.base.replay
gen = data.gen
ROOT = REPO / 'evaluation/runs/gold72_llama_book_mcq_2026-10-28'
OUT = REPO / 'evaluation/reports/gold72_llama_book_mcq_2026-10-28'
ARMS = [dict(config='llama323b', model='llama3.2:3b', thinking=None, condition=c)
        for c in ('closed_book', 'open_book')]


def prepare():
    sources = {}
    def tracked(path, as_json=True):
        path = Path(path).resolve()
        sources[str(path)] = data.file_hash(path)
        return data.read(path) if as_json else path.read_text()

    replay_root = mcq.base.previous.ROOT
    previous = tracked(replay_root / 'manifest.json')
    hard = tracked(mcq.ROOT / 'manifest.json')
    tracked(mcq.OUT / 'summary.json')
    tracked(mcq.ROOT / 'model_inventory.json')
    items = []
    for key, cell in previous['cells'].items():
        if cell.get('dataset') != 'gold' or cell['config'] != 'qwen2515b' or cell['method'] != 'omission/0%':
            continue
        qa_path = replay_root / 'updated_runs' / key / 'qa_target_decanonicalized.json'
        qa = tracked(qa_path)
        passage_path = Path(cell['source_directory']) / 'passage_target_decanonicalized.txt'
        passage = tracked(passage_path, False)
        window_path = Path(cell['source_root']) / '_inputs/windows.json'
        tracked(window_path)
        windows = gen.load_verse_windows(window_path)
        for index, q in enumerate(qa, 1):
            if q['q_type'] != 'mcq':
                continue
            public = gen.public_question(q, index)
            curated = gen.curated_window_for_item(windows, public)
            assert curated, f'Missing curated passage window: {public["id"]}'
            verse_index, order = gen.index_passage_verses(passage, gen.chapters_from_reference(public['passage_reference']))
            assert all(k in verse_index for k in curated), f'Missing clean verses: {public["id"]}'
            local = gen.local_passage_for_question(passage, verse_index, public, 2, order, windows)
            assert local == '\n'.join(verse_index[k] for k in curated).strip()
            assert q['correct'] in 'ABCD' and set(q['A']) == set('ABCDE')
            items.append(dict(id=public['id'], pid=cell['pid'], question=q['Q'], choices=copy.deepcopy(q['A']),
                              correct=q['correct'], expected=q['A'][q['correct']], reference=public['passage_reference'],
                              private_clean_passage=local, curated_window=[f'{ch}:{v}' for ch, v in curated],
                              qa_source=str(qa_path), passage_source=str(passage_path)))
    assert len(items) == len({i['id'] for i in items}) == 71
    code_paths = [Path(__file__), Path(mcq.__file__), Path(mcq.base.__file__), Path(gen.__file__),
                  Path(data.__file__), Path(mcq.base.previous.__file__)]
    for path in code_paths:
        tracked(path, False)
    manifest = dict(version=1, dataset='Gold72', active_mcqs=71, items=items, arms=ARMS,
                    systems=mcq.SYSTEMS, closed_e=mcq.CLOSED_E, settings=hard['settings'],
                    model_digests={'llama3.2:3b': hard['model_digests']['llama3.2:3b']},
                    source_hashes=sources, created_at=time.time(),
                    design='MCQ only: 71 active Gold72 questions with accepted rewrites, tested with Meta Llama 3.2 3B in closed-book and clean-passage open-book conditions (142 responses). The prompts, A-E parsing, settings and model weights match the Hard66 MCQ experiment. Original A-D choices and order are unchanged. Closed-book E means unable to answer from existing knowledge; open-book E retains the original passage-insufficiency meaning. Every question has its curated clean passage window, provided only in open book. No key, reference header, previous turns or examples are sent. Scoring is direct letter comparison, with E, wrong A-D answers, invalid outputs and failures separate. No LLM grader or random fallback is used.')
    if (ROOT / 'manifest.json').exists():
        saved = data.read(ROOT / 'manifest.json')
        manifest['created_at'] = saved['created_at']
        assert manifest == saved, 'Frozen Gold72 inputs changed.'
    else:
        data.write(ROOT / 'manifest.json', manifest)
    for arm in ARMS:
        data.write(ROOT / 'prompts' / f'{mcq.arm_id(arm)}.json',
                   [{'id': i['id'], 'request': mcq.payload_for(i, arm, manifest['settings'])} for i in items])
    snapshot = ROOT / 'code_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in code_paths:
        shutil.copy2(path, snapshot / path.name)
    print(json.dumps({'dataset': 'Gold72', 'active_mcqs': 71, 'conditions': 2, 'responses': 142,
                      'all_curated_windows_verified': True}), flush=True)
    return manifest


def verify_sources(manifest):
    assert manifest['arms'] == ARMS and manifest['systems'] == mcq.SYSTEMS and manifest['closed_e'] == mcq.CLOSED_E
    for path, sha in manifest['source_hashes'].items():
        assert data.file_hash(path) == sha, path


def run(manifest):
    from dotenv import load_dotenv
    verify_sources(manifest)
    load_dotenv(REPO / '.env')
    url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
    models = mcq.base.request_json(url + '/api/tags', timeout=20)['models']
    model = next(m for m in models if m['name'] == 'llama3.2:3b')
    assert model['digest'] == manifest['model_digests'][model['name']], 'Model weights changed.'
    data.write(ROOT / 'model_inventory.json', [model])
    total = len(ARMS) * len(manifest['items'])
    state = dict(status='running', total=total, completed=0, started_at=time.time())
    data.write(ROOT / 'state.json', state)
    try:
        for arm in ARMS:
            for item in manifest['items']:
                state.update(current_arm=mcq.arm_id(arm), current_question=item['id'])
                data.write(ROOT / 'state.json', state)
                cache = mcq.cache_key(item, arm, manifest['settings'])
                path = ROOT / 'answers' / mcq.arm_id(arm) / f'{cache}.json'
                if path.exists():
                    answer = data.read(path)
                else:
                    print(f'GOLD MCQ {state["completed"]+1}/{total} {arm["condition"]} {item["id"]}', flush=True)
                    answer = mcq.generate(item, arm, manifest['settings'], url)
                    data.write(path, answer)
                data.write(ROOT / 'scores' / mcq.arm_id(arm) / f'{cache}.json', mcq.score(answer, item, arm))
                state['completed'] += 1
                data.write(ROOT / 'state.json', state)
        state.update(status='complete', finished_at=time.time())
    except Exception as exc:
        state.update(status='failed', error=str(exc), finished_at=time.time())
        raise
    finally:
        data.write(ROOT / 'state.json', state)


def report(manifest):
    verify_sources(manifest)
    assert data.read(ROOT / 'state.json')['status'] == 'complete'
    model = data.read(ROOT / 'model_inventory.json')[0]
    assert model['digest'] == manifest['model_digests'][model['name']]
    n = len(manifest['items'])
    rows = []; summaries = []; limits = []
    for arm in ARMS:
        subset = []
        for item in manifest['items']:
            cache = mcq.cache_key(item, arm, manifest['settings'])
            answer = data.read(ROOT / 'answers' / mcq.arm_id(arm) / f'{cache}.json')
            grade = data.read(ROOT / 'scores' / mcq.arm_id(arm) / f'{cache}.json')
            assert answer['request'] == mcq.payload_for(item, arm, manifest['settings'])
            assert grade == mcq.score(answer, item, arm) and answer['id'] == item['id']
            assert not answer['answer_effort'].get('thinking_chars', 0)
            if answer['raw_response'].get('done_reason') == 'length':
                limits.append(dict(condition=arm['condition'], id=item['id']))
            row = dict(id=item['id'], dataset='Gold72', arm=mcq.arm_id(arm), **arm,
                       question=item['question'], choices=mcq.displayed_choices(item, arm['condition']),
                       correct_choice=item['correct'], expected=item['expected'], answer=answer['answer'],
                       generation_error=answer['generation_error'], grade=grade,
                       answer_effort={k: v for k, v in answer['answer_effort'].items() if k != 'thinking_text'})
            subset.append(row); rows.append(row)
        counts = Counter(r['grade']['label'] for r in subset)
        summaries.append(dict(dataset='Gold72', arm=mcq.arm_id(arm), **arm, n=n,
                              **{k: counts[k] for k in ('correct', 'incorrect_ad', 'abstain_e', 'invalid', 'failure')},
                              accuracy=counts['correct']/n))
    assert len(rows) == len({(r['condition'], r['id']) for r in rows}) == 142
    lookup = {(r['condition'], r['id']): r for r in rows}
    pairs = Counter((lookup['closed_book', i['id']]['grade']['label'], lookup['open_book', i['id']]['grade']['label']) for i in manifest['items'])
    hard = [dict(dataset='Hard66', **s) for s in data.read(mcq.OUT / 'summary.json')['configurations'] if s['config'] == 'llama323b']
    summary = dict(model='llama3.2:3b', configurations=summaries, hard66_comparison=hard,
                   transitions=[dict(closed=a, open=b, count=v) for (a, b), v in sorted(pairs.items())],
                   design=manifest['design'], strict_accuracy_change_pp=100*(summaries[1]['accuracy']-summaries[0]['accuracy']))
    OUT.mkdir(parents=True, exist_ok=True)
    data.write(OUT / 'results.json', rows); data.write(OUT / 'summary.json', summary)
    audit = dict(status='verified', active_mcqs=n, actual_requests_checked=len(rows), deterministic_scores_checked=len(rows),
                 source_files_unchanged=True, same_weights_and_protocol_as_hard66=True, all_curated_windows_verified=True,
                 original_ad_options_preserved=True, closed_e_adapted=True, keys_and_reference_headers_not_sent=True,
                 invalid_outputs=sum(s['invalid'] for s in summaries), failed_outputs=sum(s['failure'] for s in summaries),
                 token_limited_outputs=limits)
    data.write(ROOT / 'verification.json', audit); data.write(OUT / 'verification.json', audit)
    e = lambda x: html.escape(str(x))
    parts = ['<h1>Gold72 · Llama 3.2 3B MCQ</h1><p>28 October 2026 · 71 active MCQs · 142 responses</p>',
             '<div class="card"><b>MCQ only, in both conditions.</b> Closed book supplies the question and choices. Open book adds the question’s curated clean passage window. Original A–D choices are unchanged. Closed-book E means “'+e(mcq.CLOSED_E)+'”; open-book E retains “cannot determine from this passage.” The prompts, model weights and generation settings match the Hard66 MCQ experiment.</div>',
             '<table><tr><th>Condition</th><th>Correct</th><th>Wrong A–D</th><th>E</th><th>Invalid</th><th>Failed output</th></tr>']
    for s in summaries:
        parts.append(f'<tr><td>{e(s["condition"].replace("_"," "))}</td><td>{s["correct"]}/{n} ({100*s["accuracy"]:.1f}%)</td><td>{s["incorrect_ad"]}</td><td>{s["abstain_e"]}</td><td>{s["invalid"]}</td><td>{s["failure"]}</td></tr>')
    parts.append(f'</table><p>Open-minus-closed accuracy: {summary["strict_accuracy_change_pp"]:+.1f} percentage points. Every response is scored directly against the saved letter key. E is reported separately. No LLM judge, random fallback or imputed E is used.</p><h2>Comparison with Hard66</h2><table><tr><th>Dataset</th><th>Condition</th><th>Correct</th><th>E</th></tr>')
    for s in hard + summaries:
        parts.append(f'<tr><td>{e(s["dataset"])}</td><td>{e(s["condition"].replace("_"," "))}</td><td>{s["correct"]}/{s["n"]} ({100*s["accuracy"]:.1f}%)</td><td>{s["abstain_e"]}</td></tr>')
    parts.append('</table><p>These datasets contain different questions. Closed-book success may reflect knowledge, recognition, wording cues, elimination or guessing. E has a different abstention meaning in each condition. The original dataset name is Gold72; the current accepted export contains 71 active MCQs.</p><h2>Questions, choices and paired answers</h2>')
    for item in manifest['items']:
        parts.append('<details class="card"><summary>'+e(item['question'])+'</summary><p><b>Key:</b> '+e(item['correct'])+' · '+e(item['expected'])+'<br><small>'+e(item['id'])+' · '+e(item['reference'])+'</small></p><ul>'+''.join('<li><b>'+k+':</b> '+e(item['choices'][k])+'</li>' for k in 'ABCD')+'</ul><table><tr><th>Condition</th><th>Raw final answer</th><th>Selected choice</th><th>Outcome</th></tr>')
        for arm in ARMS:
            r = lookup[arm['condition'], item['id']]
            parts.append('<tr><td>'+e(arm['condition'].replace('_',' '))+'</td><td>'+e(r['answer'] or '[empty]')+'</td><td>'+e(r['grade']['selected_choice'] or '—')+'</td><td>'+e(r['grade']['label'])+'</td></tr>')
        parts.append('</table><details><summary>Clean passage, supplied only in open book</summary><p class="passage">'+e(item['private_clean_passage'])+'</p></details></details>')
    parts.append('<p><a href="summary.json">Summary data</a> · <a href="results.json">All MCQ results</a> · <a href="verification.json">Verification</a></p>')
    style = 'body{font:16px/1.6 system-ui;background:#f4f6f8;color:#172b3b}main{max-width:1200px;margin:auto;padding:28px}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dce3e9}th{background:#e9eff4}.card{background:white;border:1px solid #dce3e9;border-radius:10px;padding:18px;margin:16px 0}.passage{white-space:pre-wrap;background:#f6f8fa;padding:16px}summary{cursor:pointer;font-weight:650;color:#145b81}a{color:#145b81}'
    (OUT / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gold72 Llama MCQ comparison</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')
    print(json.dumps({'summary': summary, 'report': str(OUT / 'index.html')}, ensure_ascii=False, indent=2), flush=True)


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
