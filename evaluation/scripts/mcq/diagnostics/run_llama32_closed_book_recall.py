#!/usr/bin/env python3
"""Extend the frozen Hard66 question-only recall experiment with Llama 3.2 3B."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import html
import json
from pathlib import Path
import shutil
import sys
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import run_hard66_closed_book_recall as base

ROOT = REPO / 'evaluation/runs/hard66_closed_book_recall_llama323b_2026-10-28'
OUT = REPO / 'evaluation/reports/hard66_closed_book_recall_llama323b_2026-10-28'
CONFIG = ['llama323b', 'llama3.2:3b', None]
LABELS = {**base.previous.LABELS, 'llama323b': 'Meta Llama 3.2 3B'}


def prepare():
    parent_path = base.DEFAULT_ROOT / 'manifest.json'
    parent = base.replay.read(parent_path)
    assert base.replay.read(base.DEFAULT_ROOT / 'state.json')['status'] == 'complete'
    assert base.replay.file_hash(Path(base.__file__)) == parent['code_hash']
    manifest = copy.deepcopy(parent)
    manifest.update(configs=[CONFIG], created_at=time.time(), parent_manifest=str(parent_path),
                    extension='Meta Llama 3.2 3B; previous Qwen results reused without regeneration.')
    dependencies = [parent_path, base.DEFAULT_REPORT / 'results.json', base.DEFAULT_REPORT / 'summary.json',
                    Path(__file__), Path(base.__file__), Path(base.replay.gen.__file__), Path(base.replay.scoring.__file__)]
    for path in dependencies:
        manifest['source_hashes'][str(path)] = base.replay.file_hash(path)
    saved_path = ROOT / 'manifest.json'
    if saved_path.exists():
        saved = base.replay.read(saved_path)
        manifest['created_at'] = saved['created_at']
        assert manifest == saved, 'Frozen experiment inputs changed.'
    else:
        base.replay.write(saved_path, manifest)
    base.replay.write(ROOT / 'prompts/llama323b.json', [
        {'id': item['id'], 'model': CONFIG[1], 'messages': base.messages_for(item['question'], None)}
        for item in manifest['items']])
    snapshot = ROOT / 'code_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in dependencies[3:]:
        shutil.copy2(path, snapshot / path.name)
    print(json.dumps({'questions': len(manifest['items']), 'model': CONFIG[1], 'responses': 65}), flush=True)
    return manifest


def verify_sources(manifest):
    assert manifest['configs'] == [CONFIG]
    assert manifest['system'] == base.SYSTEM and manifest['judge_system'] == base.JUDGE_SYSTEM
    for path, sha in manifest['source_hashes'].items():
        assert base.replay.file_hash(path) == sha, path


def report(manifest):
    verify_sources(manifest)
    assert base.replay.read(ROOT / 'state.json')['status'] == 'complete'
    overrides_path = ROOT / 'review_overrides.json'
    overrides = base.replay.read(overrides_path) if overrides_path.exists() else []
    overrides = {(x['config'], x['id']): x['grade'] for x in overrides}
    rows = base.replay.read(base.DEFAULT_REPORT / 'results.json')
    assert len(rows) == 195
    new_rows = []
    token_limited = []
    for item in manifest['items']:
        cache = base.replay.digest({'config': CONFIG, 'messages': base.messages_for(item['question'], None),
                                    'settings': manifest['settings']})
        answer = base.replay.read(ROOT / 'answers/llama323b' / f'{cache}.json')
        grade = base.replay.read(ROOT / 'grades/llama323b' / f'{cache}.json')
        request = answer['request']
        assert request['messages'] == base.messages_for(item['question'], None)
        assert request['model'] == CONFIG[1] and 'think' not in request
        assert request['options'] == {k: manifest['settings'][k] for k in ('temperature', 'num_ctx', 'num_predict')}
        assert answer['id'] == item['id'] and not answer['answer_effort'].get('thinking_chars', 0)
        if answer['raw_response'].get('done_reason') == 'length':
            token_limited.append(item['id'])
        new_rows.append(dict(id=item['id'], config=CONFIG[0], question=item['question'], expected=item['expected'],
                             reference=item['reference'], answer=answer['answer'], generation_error=answer['generation_error'],
                             answer_effort={k: v for k, v in answer['answer_effort'].items() if k != 'thinking_text'},
                             automated_grade=grade, grade=overrides.get((CONFIG[0], item['id']), grade)))
    assert len(new_rows) == 65 and len({r['id'] for r in new_rows}) == 65
    rows += new_rows
    configs = ['qwen2515b', 'qwen317b_nothink', 'qwen317b_think', 'llama323b']
    summaries = []
    for config in configs:
        subset = [r for r in rows if r['config'] == config]
        assert len(subset) == 65
        counts = Counter(r['grade']['label'] for r in subset)
        summaries.append(dict(config=config, n=65, **{k: counts[k] for k in ('correct', 'partial', 'incorrect', 'unknown', 'failure')},
                              strict_accuracy=counts['correct']/65, mean_score=sum(r['grade']['score'] for r in subset)/65))
    OUT.mkdir(parents=True, exist_ok=True)
    base.replay.write(OUT / 'results.json', rows)
    base.replay.write(OUT / 'summary.json', dict(configurations=summaries, design=manifest['design'],
                                               judge_model=manifest['settings']['judge_model'], llama_review_overrides=len(overrides)))
    audit = dict(status='verified', new_responses=65, comparison_responses=260, question_only_requests_checked=65,
                 sources_unchanged=True, qwen_results_reused_unchanged=True, model=CONFIG[1],
                 generation_settings=manifest['settings'], token_limited_ids=token_limited,
                 manual_overrides=len(overrides))
    base.replay.write(ROOT / 'verification.json', audit)
    base.replay.write(OUT / 'verification.json', audit)
    e = lambda x: html.escape(str(x))
    parts = ['<h1>Hard66 · closed-book Bible recall</h1><p>28 October 2026 · 65 active questions · Qwen and Meta Llama comparison</p>',
             '<div class="card"><b>No passages, answer choices, or chapter references were supplied.</b> Each question began a fresh conversation. General Bible knowledge was explicitly allowed. Llama used the same instructions, questions, answer keys, temperature (0), context limit (8,192), and output limit (2,500 tokens) as the earlier test. Previously reviewed Qwen responses are reused unchanged.</div>',
             '<table><tr><th>Model</th><th>Fully correct</th><th>Partial</th><th>Incorrect</th><th>Does not know</th><th>Failed output</th></tr>']
    for s in summaries:
        parts.append(f'<tr><td>{e(LABELS[s["config"]])}</td><td>{s["correct"]}/65 ({100*s["strict_accuracy"]:.1f}%)</td><td>{s["partial"]}</td><td>{s["incorrect"]}</td><td>{s["unknown"]}</td><td>{s["failure"]}</td></tr>')
    parts.append('</table><p>Answers were graded against the Chinese key and private clean passage: exact matches and explicit abstentions use rules; other responses use gpt-4.1-mini. Full correctness scores 1; partial correctness scores 0.5. English equivalents of biblical names are accepted. Original and reviewed grades are retained in the data.</p>')
    parts.append(f'<p>Llama review corrections: {len(overrides)}. Token-limited Llama responses: {len(token_limited)}. Empty outputs are failures, not abstentions.</p>')
    parts.append('<div class="card">Interpretation: these are question-only free-response results. Some stems depend on missing context, and answer choices may cue knowledge that cannot be freely recalled. Success may also reflect cues in the question. This test does not isolate why a model selected an option in an earlier multiple-choice test.</div><h2>Question-by-question answers</h2>')
    lookup = {(r['config'], r['id']): r for r in rows}
    for item in manifest['items']:
        parts.append('<details class="card"><summary>'+e(item['question'])+'</summary><p><b>Key:</b> '+e(item['expected'])+'<br><small>'+e(item['reference'])+' · '+e(item['id'])+'</small></p><table><tr><th>Model</th><th>Answer</th><th>Grade</th><th>Reason</th></tr>')
        for config in configs:
            r = lookup[config, item['id']]
            parts.append('<tr><td>'+e(LABELS[config])+'</td><td>'+e(r['answer'] or '[empty]')+'</td><td>'+e(r['grade']['label'])+'</td><td>'+e(r['grade']['rationale'])+'</td></tr>')
        parts.append('</table><details><summary>Private reference used for grading only</summary><p style="white-space:pre-wrap">'+e(item['private_clean_passage'])+'</p></details></details>')
    parts.append('<p><a href="summary.json">Summary</a> · <a href="results.json">All answers and grades</a> · <a href="verification.json">Verification</a></p>')
    style = 'body{font:16px/1.6 system-ui;background:#f4f6f8;color:#172b3b}main{max-width:1200px;margin:auto;padding:28px}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dce3e9}th{background:#e9eff4}.card{background:white;border:1px solid #dce3e9;border-radius:10px;padding:18px;margin:16px 0}summary{cursor:pointer;font-weight:650;color:#145b81}small{color:#637584}a{color:#145b81}'
    (OUT / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hard66 closed-book recall comparison</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')
    print(json.dumps({'summary': summaries, 'report': str(OUT / 'index.html')}, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['prepare', 'run', 'report', 'all'], default='all')
    args = parser.parse_args()
    manifest = prepare() if args.phase in ('prepare', 'all') else base.replay.read(ROOT / 'manifest.json')
    verify_sources(manifest)
    if args.phase in ('run', 'all'):
        # Reuse the frozen generator, judge, cache, and retry logic for only this new model.
        base.CONFIGS = [CONFIG]
        base.run(ROOT, manifest)
    if args.phase in ('report', 'all'):
        report(manifest)


if __name__ == '__main__':
    main()
