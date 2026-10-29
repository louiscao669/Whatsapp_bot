#!/usr/bin/env python3
"""Run three small models on six saved Gold72 passage variants."""
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
from evaluation.scripts.mcq.diagnostics import run_gold72_small_models_book_mcq as baseline
from evaluation.scripts.variants.current import create_omission_variants as omission

mcq = baseline.mcq
data = baseline.data
gen = baseline.gold.gen
ROOT = REPO / 'evaluation/runs/gold72_small_models_variants_2026-10-28'
OUT = REPO / 'evaluation/reports/gold72_small_models_variants_2026-10-28'
METHODS = ['omission/15%', 'omission/30%', 'mistranslation/15%', 'mistranslation/30%', 'grammar/30%', 'google_word_by_word']
METHOD_LABELS = {'clean': 'Clean passage', 'omission/15%': 'Omission 15%', 'omission/30%': 'Omission 30%',
                 'mistranslation/15%': 'Mistranslation 15%', 'mistranslation/30%': 'Mistranslation 30%',
                 'grammar/30%': 'Grammar 30%', 'google_word_by_word': 'Google word-by-word'}
ARMS = [dict(config=config, model=model, thinking=None, condition='open_book', variant=method)
        for config, model in baseline.MODELS for method in METHODS]


def arm_id(arm):
    return arm['config'] + '_' + arm['variant'].replace('/', '_').replace('%', 'pct')


def omission_verse_index(clean, variant, metadata, chapters):
    """Locate surviving characters by their original verse, without restoring any."""
    units = omission.passage_units(clean)
    assert ''.join(u['text'] for u in units) == clean
    removed = {u['unit_index']: u for u in metadata['omitted_units']}
    assert len(removed) == len(metadata['omitted_units'])
    assert all(type(i) is int and 0 <= i < len(units) for i in removed)
    keep = bytearray([1]) * len(clean)
    cursor = 0
    for index, unit in enumerate(units):
        end = cursor + len(unit['text'])
        if index in removed:
            assert unit['text'].strip() == removed[index]['text'], 'Omission record mismatch.'
            keep[cursor:end] = bytes(end - cursor)
        cursor = end
    reconstructed = ''.join(char for index, char in enumerate(clean) if keep[index])
    assert reconstructed.strip() == variant.strip(), 'Saved omission variant does not match its deletion records.'
    clean_index, order = gen.index_passage_verses(clean, chapters)
    result = {}
    cursor = 0
    for key in order:
        text = clean_index[key]
        start = clean.find(text, cursor)
        assert start >= cursor
        end = start + len(text)
        result[key] = ''.join(clean[i] for i in range(start, end) if keep[i]).strip()
        cursor = end
    return result


def inference_item(item):
    # The frozen helper uses this field name for whichever passage is supplied.
    return dict(item, private_clean_passage=item['variant_passage'])


def prepare():
    parent = data.read(baseline.ROOT / 'manifest.json')
    baseline.verify_sources(parent)
    sources = copy.deepcopy(parent['source_hashes'])
    def tracked(path, as_json=True):
        path = Path(path).resolve()
        sources[str(path)] = data.file_hash(path)
        return data.read(path) if as_json else path.read_text()
    for path in [baseline.ROOT / 'manifest.json', baseline.ROOT / 'model_inventory.json',
                 baseline.OUT / 'results.json', baseline.OUT / 'summary.json', baseline.OUT / 'verification.json',
                 Path(__file__), Path(omission.__file__), REPO / 'evaluation/scripts/variants/_common.py']:
        tracked(path, path.suffix == '.json')
    replay_root = mcq.base.previous.ROOT
    replay = tracked(replay_root / 'manifest.json')
    cells = {(c['pid'], c['method']): (key, c) for key, c in replay['cells'].items()
             if c['dataset'] == 'gold' and c['config'] == 'qwen2515b' and c['method'] in METHODS}
    variants = {method: [] for method in METHODS}
    extraction = {method: Counter() for method in METHODS}
    for method in METHODS:
        loaded = {}
        for clean_item in parent['items']:
            pid = clean_item['pid']
            if pid not in loaded:
                key, cell = cells[pid, method]
                folder = Path(cell['source_directory'])
                passage_path = folder / 'passage_target_decanonicalized.txt'
                passage = tracked(passage_path, False)
                qa_path = replay_root / 'updated_runs' / key / 'qa_target_decanonicalized.json'
                qa = tracked(qa_path)
                questions = {gen.public_question(q, idx)['id']: (q, gen.public_question(q, idx))
                             for idx, q in enumerate(qa, 1) if q['q_type'] == 'mcq'}
                chapters = gen.chapters_from_reference(clean_item['reference'])
                parsed, order = gen.index_passage_verses(passage, chapters)
                assert parsed
                window_path = Path(cell['source_root']) / '_inputs/windows.json'
                tracked(window_path)
                windows = gen.load_verse_windows(window_path)
                indexed = parsed
                metadata_path = None
                if method.startswith('omission/'):
                    metadata_path = folder / 'omission_metadata.json'
                    metadata = tracked(metadata_path)['files']['passage_target_decanonicalized']
                    clean_full = tracked(clean_item['passage_source'], False)
                    indexed = omission_verse_index(clean_full, passage, metadata, chapters)
                loaded[pid] = (questions, passage, parsed, order, windows, indexed, passage_path, qa_path, metadata_path)
            questions, passage, parsed, order, windows, indexed, passage_path, qa_path, metadata_path = loaded[pid]
            q, public = questions[clean_item['id']]
            assert (q['Q'], q['A'], q['correct']) == (clean_item['question'], clean_item['choices'], clean_item['correct'])
            curated = gen.curated_window_for_item(windows, public)
            assert [f'{ch}:{verse}' for ch, verse in curated] == clean_item['curated_window']
            assert all(key in indexed for key in curated)
            local = '\n'.join(indexed[key] for key in curated if indexed[key]).strip()
            old_local = gen.local_passage_for_question(passage, parsed, public, 2, order, windows)
            missing_markers = [f'{ch}:{verse}' for ch, verse in curated if (ch, verse) not in parsed]
            if not method.startswith('omission/'):
                assert local == old_local and not missing_markers
            item = dict(clean_item, variant=method, variant_passage=local,
                        variant_passage_source=str(passage_path), variant_qa_source=str(qa_path),
                        omission_metadata_source=str(metadata_path) if metadata_path else None,
                        extraction=dict(original_window_preserved=True, missing_verse_markers=missing_markers,
                                        differs_from_legacy_extractor=local != old_local,
                                        empty_window=not bool(local), unchanged_from_clean=local == clean_item['private_clean_passage']))
            variants[method].append(item)
            stats = extraction[method]
            stats['questions'] += 1
            stats['missing_verse_markers'] += bool(missing_markers)
            stats['differs_from_legacy_extractor'] += local != old_local
            stats['empty_windows'] += not bool(local)
            stats['unchanged_from_clean'] += local == clean_item['private_clean_passage']
        assert len(variants[method]) == len({i['id'] for i in variants[method]}) == 71
    inventory = data.read(baseline.ROOT / 'model_inventory.json')
    manifest = dict(version=1, dataset='Gold72', items=parent['items'], variants=variants, arms=ARMS,
                    settings=parent['settings'], system=mcq.SYSTEMS['open_book'], source_hashes=sources,
                    model_digests={m['name']: m['digest'] for m in inventory}, extraction=dict(extraction),
                    new_responses=1278, clean_responses_reused=213, created_at=time.time(),
                    design='71 accepted Gold72 MCQs × six saved passage conditions × three models = 1,278 new responses. Same model weights, questions, A-E choices, original answer keys, open-book prompts and generation settings as the clean comparison. Only supplied passage content changes. Omission windows are anchored to original chapter/verse boundaries using recorded deletions, verified to reproduce saved variants exactly; deleted text and verse markers are never restored. No full-passage fallback. Prior clean results are reused for comparison. Original-key agreement, other A-D choices, E, invalid outputs and failures are separate. No per-variant answerability labels are assumed: key disagreement can include faithful answers to mistranslated text; E is not automatically classified as right or wrong.')
    if (ROOT / 'manifest.json').exists():
        saved = data.read(ROOT / 'manifest.json')
        manifest['created_at'] = saved['created_at']
        assert manifest == saved, 'Frozen experiment changed.'
    else:
        data.write(ROOT / 'manifest.json', manifest)
    data.write(ROOT / 'model_inventory.json', inventory)
    for arm in ARMS:
        prompts = [{'id': i['id'], 'request': mcq.payload_for(inference_item(i), arm, manifest['settings'])}
                   for i in variants[arm['variant']]]
        data.write(ROOT / 'prompts' / (arm_id(arm) + '.json'), prompts)
    snapshot = ROOT / 'code_snapshot'
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in [Path(__file__), Path(baseline.__file__), Path(mcq.__file__), Path(gen.__file__), Path(omission.__file__)]:
        shutil.copy2(path, snapshot / path.name)
    print(json.dumps({'prepared': True, 'new_responses': 1278, 'extraction': extraction}), flush=True)
    return manifest


def verify_sources(manifest):
    assert manifest['arms'] == ARMS and manifest['system'] == mcq.SYSTEMS['open_book']
    for path, digest in manifest['source_hashes'].items():
        assert data.file_hash(path) == digest, f'Changed source: {path}'


def run(manifest):
    from dotenv import load_dotenv
    verify_sources(manifest)
    load_dotenv(REPO / '.env')
    url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
    inventory = mcq.base.request_json(url + '/api/tags', timeout=20)['models']
    actual = {m['name']: m['digest'] for m in inventory}
    assert all(actual.get(name) == digest for name, digest in manifest['model_digests'].items()), 'Model weights differ from clean run.'
    state = dict(status='running', total=1278, completed=0, started_at=time.time())
    data.write(ROOT / 'state.json', state)
    try:
        for arm in ARMS:
            counts = Counter()
            aid = arm_id(arm)
            for original in manifest['variants'][arm['variant']]:
                item = inference_item(original)
                state.update(current_arm=aid, current_question=item['id'])
                data.write(ROOT / 'state.json', state)
                cache = mcq.cache_key(item, arm, manifest['settings'])
                path = ROOT / 'answers' / aid / (cache + '.json')
                if path.exists():
                    answer = data.read(path)
                else:
                    if state['completed'] % 10 == 0:
                        print(f'MCQ {state["completed"] + 1}/1278 {aid} {item["id"]}', flush=True)
                    answer = mcq.generate(item, arm, manifest['settings'], url)
                    answer.update(arm=aid, variant=arm['variant'])
                    data.write(path, answer)
                assert answer['request'] == mcq.payload_for(item, arm, manifest['settings'])
                grade = mcq.score(answer, item, arm)
                data.write(ROOT / 'scores' / aid / (cache + '.json'), grade)
                counts[grade['label']] += 1
                state['completed'] += 1
                state['current_arm_outcomes'] = dict(counts)
                data.write(ROOT / 'state.json', state)
            print(json.dumps({'arm_complete': aid, 'outcomes': counts}), flush=True)
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
        for original in manifest['variants'][arm['variant']]:
            item = inference_item(original)
            aid = arm_id(arm)
            cache = mcq.cache_key(item, arm, manifest['settings'])
            answer = data.read(ROOT / 'answers' / aid / (cache + '.json'))
            grade = data.read(ROOT / 'scores' / aid / (cache + '.json'))
            assert answer['id'] == item['id'] and answer['request'] == mcq.payload_for(item, arm, manifest['settings'])
            assert grade == mcq.score(answer, item, arm)
            assert answer['raw_response']['model'] == arm['model']
            if answer['raw_response'].get('done_reason') == 'length':
                limits.append(dict(arm=aid, id=item['id']))
            rows.append(dict(id=item['id'], dataset='Gold72', arm=aid, **arm, question=item['question'],
                             choices=item['choices'], correct_choice=item['correct'], expected=item['expected'],
                             answer=answer['answer'], generation_error=answer['generation_error'], grade=grade,
                             answer_effort={k: v for k, v in answer['answer_effort'].items() if k != 'thinking_text'},
                             extraction=original['extraction'], result_origin='new_run'))
    assert len(rows) == len({(r['arm'], r['id']) for r in rows}) == 1278
    configs = {config for config, _ in baseline.MODELS}
    clean = [dict(r, variant='clean', result_origin='previous_clean_run')
             for r in data.read(baseline.OUT / 'results.json') if r['config'] in configs and r['condition'] == 'open_book']
    assert len(clean) == 213
    all_rows = clean + rows
    summaries = []
    lookup = {(r['config'], r['variant'], r['id']): r for r in all_rows}
    for config, model in baseline.MODELS:
        for method in ['clean'] + METHODS:
            subset = [r for r in all_rows if r['config'] == config and r['variant'] == method]
            assert len(subset) == 71
            counts = Counter(r['grade']['label'] for r in subset)
            baseline_correct = sum(lookup[config, 'clean', r['id']]['grade']['label'] == 'correct' for r in subset)
            lost = sum(lookup[config, 'clean', r['id']]['grade']['label'] == 'correct' and r['grade']['label'] != 'correct' for r in subset)
            gained = sum(lookup[config, 'clean', r['id']]['grade']['label'] != 'correct' and r['grade']['label'] == 'correct' for r in subset)
            summaries.append(dict(config=config, model=model, variant=method, n=71,
                                  **{k: counts[k] for k in baseline.OUTCOMES}, accuracy=counts['correct']/71,
                                  change_from_clean_pp=100*(counts['correct']-baseline_correct)/71,
                                  lost_clean_correct=lost, gained_key_matches=gained))
    summary = dict(configurations=summaries, design=manifest['design'], extraction=manifest['extraction'])
    audit = dict(status='verified', new_requests_checked=1278, direct_scores_checked=1278,
                 clean_results_reused=213, sources_unchanged=True, same_model_weights_as_clean=True,
                 original_questions_choices_and_keys_unchanged=True, original_windows_preserved=True,
                 omission_variants_reconstructed_exactly=True, no_clean_text_restored=True,
                 no_full_passage_fallback=True, invalid_outputs=sum(s['invalid'] for s in summaries),
                 failed_outputs=sum(s['failure'] for s in summaries), token_limited_outputs=limits)
    OUT.mkdir(parents=True, exist_ok=True)
    data.write(OUT / 'results.json', all_rows)
    data.write(OUT / 'summary.json', summary)
    data.write(OUT / 'verification.json', audit)
    data.write(ROOT / 'verification.json', audit)
    render(manifest, all_rows, summaries)
    print(json.dumps({'configurations': summaries, 'report': str(OUT / 'index.html')}, indent=2), flush=True)


def render(manifest, rows, summaries):
    e = lambda value: html.escape(str(value))
    lookup = {(s['config'], s['variant']): s for s in summaries}
    parts = ['<h1>Gold72 · passage-variant comparison</h1><p>71 active MCQs · three models · six altered-passage conditions · 28 October 2026</p>',
             '<div class="card">1,278 new responses, with 213 saved clean-passage responses for comparison. The same questions, answer choices, model weights, prompts and generation settings are used in every condition. E is reported separately.</div>',
             '<h2>Agreement with the original answer key</h2><table><tr><th>Passage condition</th>'+''.join('<th>'+e(baseline.LABELS[c])+'</th>' for c, _ in baseline.MODELS)+'</tr>']
    for method in ['clean'] + METHODS:
        parts.append('<tr><td>'+e(METHOD_LABELS[method])+'</td>')
        for config, _ in baseline.MODELS:
            s = lookup[config, method]
            parts.append(f'<td><b>{s["correct"]}/71 ({100*s["accuracy"]:.1f}%)</b><br><small>E: {s["abstain_e"]} · other A–D: {s["incorrect_ad"]}'+(f' · change: {s["change_from_clean_pp"]:+.1f} pp' if method != 'clean' else '')+'</small></td>')
        parts.append('</tr>')
    parts.append('</table><p><b>How to read these scores:</b> “Original-key match” measures recovery of the original passage meaning. A different A–D answer can be faithful to a mistranslated passage. E means the supplied passage does not provide enough information; it is counted separately, without assuming that every omitted passage requires E. No per-question answerability judgments or revised keys are introduced.</p><h2>All outcomes</h2><table><tr><th>Model</th><th>Condition</th><th>Original-key match</th><th>Other A–D</th><th>E</th><th>Invalid</th><th>Failed</th></tr>')
    for s in summaries:
        parts.append('<tr><td>'+e(baseline.LABELS[s['config']])+'</td><td>'+e(METHOD_LABELS[s['variant']])+'</td>'+''.join('<td>'+str(s[key])+'</td>' for key in baseline.OUTCOMES)+'</tr>')
    parts.append('</table><details class="card"><summary>Passage extraction and reproducibility</summary><p>Every question uses its original curated chapter/verse window. Some saved omissions delete verse-number markers along with clauses. For those passages, the exact recorded deleted units are mapped to their original verses; the reconstructed full variant must match the saved variant. Deleted text and verse markers are never restored. This avoids merging adjacent verses or falling back to a larger passage. These omission windows can therefore differ from older variant runs that relied only on surviving verse numbers. Other variants use the existing verse extraction unchanged.</p><p>Temperature 0; context 8,192; output limit 2,500 tokens. One fresh conversation per question and condition. Original A–E choices and answer keys unchanged. Exact model digests match the clean run. Direct deterministic scoring, no LLM grader and no random fallback. Rates describe the saved full-passage conditions, not a guaranteed percentage within each local window.</p><pre>'+e(json.dumps(manifest['extraction'], indent=2))+'</pre></details><h2>Question-level answers and supplied passages</h2>')
    answers = {(r['config'], r['variant'], r['id']): r for r in rows}
    variants = {(method, i['id']): i for method, items in manifest['variants'].items() for i in items}
    for item in manifest['items']:
        parts.append('<details class="card"><summary>'+e(item['question'])+'</summary><p><b>Original key:</b> '+e(item['correct'])+' · '+e(item['expected'])+'<br><small>'+e(item['id'])+' · '+e(item['reference'])+'</small></p><ul>'+''.join('<li><b>'+key+':</b> '+e(item['choices'][key])+'</li>' for key in 'ABCDE')+'</ul>')
        for method in ['clean'] + METHODS:
            text = item['private_clean_passage'] if method == 'clean' else variants[method, item['id']]['variant_passage']
            parts.append('<details><summary>'+e(METHOD_LABELS[method])+'</summary><p class="passage">'+e(text or '[The entire curated window is absent.]')+'</p><table><tr><th>Model</th><th>Raw final answer</th><th>Choice</th><th>Outcome</th></tr>')
            for config, _ in baseline.MODELS:
                r = answers[config, method, item['id']]
                label = {'correct': 'original-key match', 'incorrect_ad': 'other A–D', 'abstain_e': 'E'}.get(r['grade']['label'], r['grade']['label'])
                parts.append('<tr><td>'+e(baseline.LABELS[config])+'</td><td>'+e(r['answer'] or '[empty]')+'</td><td>'+e(r['grade']['selected_choice'] or '—')+'</td><td>'+e(label)+'</td></tr>')
            parts.append('</table></details>')
        parts.append('</details>')
    parts.append('<p><a href="summary.json">Summary data</a> · <a href="results.json">All results</a> · <a href="verification.json">Verification</a></p>')
    style = 'body{font:16px/1.6 system-ui;background:#f4f6f8;color:#172b3b}main{max-width:1200px;margin:auto;padding:28px}table{width:100%;border-collapse:collapse;background:white;margin:20px 0}td,th{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dce3e9}td{overflow-wrap:anywhere}th{background:#e9eff4}.card{background:white;border:1px solid #dce3e9;border-radius:10px;padding:18px;margin:16px 0}.passage{white-space:pre-wrap;background:#f6f8fa;padding:16px}summary{cursor:pointer;font-weight:650;color:#145b81}a{color:#145b81}details details{margin:12px 0}pre{white-space:pre-wrap}'
    (OUT / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gold72 passage-variant comparison</title><style>'+style+'</style><main>'+''.join(parts)+'</main></html>')


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
