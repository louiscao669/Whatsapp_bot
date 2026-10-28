#!/usr/bin/env python3
"""Replay accepted QA rewrites, preserving the original experiment and its results.

Only selected forms are sent to answer models. Exact repeated model inputs reuse
one response; this is recorded explicitly. Unchanged results are copied verbatim
when publishing revised run copies. New coverage stays separate from old totals.
"""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
os.environ.update(QA_FORMATS='open,mcq', MCQ_CHOICE_LABELS='ABCDE', MCQ_ABSTAIN_LABEL='E', MCQ_KEEP_THINKING='1')
from evaluation.agents import generate_chinese_answers as gen
from evaluation.scripts.scoring.current import score_generated_answers as scoring

RUNS = REPO / 'evaluation/runs'
DEFAULT_OUTPUT = RUNS / 'qa_rewrite_rerun_2026-10-27'
REWRITES = REPO / 'evaluation/reports/qa_early_simplify_flagged_v3_1_2026-10-27/rewritten_cases.json'
CONFIGS = [('llama321b', 'llama3.2:1b', False), ('qwen2515b', 'qwen2.5:1.5b', False),
           ('qwen317b_think', 'qwen3:1.7b', True), ('qwen317b_nothink', 'qwen3:1.7b', False)]
METHODS = ['omission/0%'] + [f'{f}/{r}%' for f in ('omission', 'mistranslation', 'grammar') for r in (5,10,15,20,25,30)] + ['google_word_by_word', 'grammar/max_approved']
GOLD_TRANSLATIONS = {
    'gold:t1_1kgs13:o8ae:open': '耶罗波安家族的罪是什么？',
    'gold:t1_1kgs13:o8ae:mcq': '耶罗波安家族的罪是什么？',
    'gold:t1_2kgs11:otua:open': '安息日下值的那些队伍被吩咐做什么？',
    'gold:t1_2kgs11:otua:mcq': '安息日下值的那两队人被安排做什么？',
    'gold:t1_acts20:jxkk#2:open': '保罗扑在那个年轻人身上以后，年轻人怎么样了？',
}
RESULT_FILES = ['generated_answers_target_llama.json', 'generated_answers_target_llama_backtranslated.json', 'scores_target_llama.json']


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def form_key(row):
    return row['id'], row['q_type']


def merge_rows(original, replacements):
    """Replace exactly matching forms without changing order or other rows."""
    keys = [form_key(r) for r in original]
    patch = {form_key(r): r for r in replacements}
    if len(keys) != len(set(keys)) or len(patch) != len(replacements) or set(patch) - set(keys):
        raise ValueError('Missing or duplicate result identifiers')
    result = []
    for row in original:
        if form_key(row) not in patch:
            result.append(copy.deepcopy(row))
            continue
        new = copy.deepcopy(patch[form_key(row)])
        for k in ('item_index', 'id', 'q_type', 'passage_id', 'passage_reference'):
            if k in row:
                new[k] = row[k]
        result.append(new)
    return result


def source_for(dataset, config, method):
    name, model, thinking = config
    stem = model.replace(':', '').replace('.', '')
    if dataset == 'gold':
        slug = stem + ('_think' if thinking else '_nothink')
        parent = 'gold72_max_sentence_grammar_four_configs_2026-10-27' if method == 'grammar/max_approved' else 'gold72_four_configs_2026-10-27'
        return RUNS / parent / slug, slug, not thinking
    no_think = name == 'qwen317b_nothink'
    slug = stem + ('_nothink' if no_think else '_think')
    if method == 'grammar/max_approved':
        root = RUNS / 'hard66_grammar_sentence_all_mcq_qwen317b_nothink_2026-10-25' if no_think else RUNS / 'hard66_grammar_sentence_all_mcq_models_2026-10-25' / stem
    elif no_think:
        family = 'google_word_by_word' if method == 'google_word_by_word' else method.split('/')[0]
        root = RUNS / f'hard66_{family}_mcq_qwen317b_nothink_2026-10-26'
    elif method.startswith('grammar/'):
        root = RUNS / 'hard66_grammar_full_2026-10-24'
    else:
        root = RUNS / 'hard66_full_ladder_2026-10-23'
    return root, slug, no_think


def canonical_id(case):
    _, rest = case['id'].split(':', 1)
    content_id, form = rest.rsplit(':', 1)
    return f'uw-{content_id}-{form}'


def freeze(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f'Frozen input changed: {path}')
    else:
        write(path, value)


def prepare(output):
    from dotenv import dotenv_values
    env = dotenv_values(REPO / '.env')
    settings = {k: os.environ.get(k) or env.get(k) or 'gpt-4.1-mini' for k in ('OPENAI_TRANSLATION_MODEL', 'OPENAI_JUDGE_MODEL', 'OPENAI_MCQ_CHOICE_MODEL')}
    settings.update(num_ctx=8192, num_predict=2500, timeout_seconds=150, temperature=0, retries=2)
    cases = [c for c in read(REWRITES) if c['id'].startswith(('gold:', 'hard:'))]
    assert len(cases) == 16
    assert sum(c['id'].startswith('gold:') for c in cases) == 5
    hashes, jobs, cells, questions = {}, [], {}, {}

    def tracked(path, as_json=True):
        path = Path(path).resolve()
        hashes[str(path)] = file_hash(path)
        return read(path) if as_json else path.read_text()

    tracked(REWRITES)
    roots = {source_for(dataset, config, method)[0] for dataset in ('gold', 'hard') for config in CONFIGS for method in METHODS}
    # Include the duplicate clean baselines stored by the no-thinking family runs.
    for root in sorted(roots):
        dataset = 'gold' if root.parts[-2].startswith('gold72_') else 'hard'
        state = tracked(root / 'campaign_state.json')
        if state['status'] != 'complete':
            raise ValueError(f'Source campaign is not complete: {root}')
        tracked(root / 'release.json')
        for path in sorted(root.glob('t1_*/*/**/scores_target_llama.json')):
            rel = path.parent.relative_to(root)
            if len(rel.parts) < 3 or not rel.parts[1].endswith(('_think', '_nothink')):
                continue
            pid, slug, *parts = rel.parts
            method = '/'.join(parts)
            model = next(m for _, m, _ in CONFIGS if slug.startswith(m.replace(':', '').replace('.', '')))
            config_name = model.replace(':', '').replace('.', '')
            if model == 'qwen3:1.7b':
                config_name += '_nothink' if slug.endswith('_nothink') else '_think'
            key = str(path.parent.relative_to(RUNS))
            files = {name: str(path.parent / name) for name in RESULT_FILES}
            data = {name: tracked(p) for name, p in files.items()}
            tracked(path.parent / 'qa_target_decanonicalized.json')
            rows = data[RESULT_FILES[2]]['items']
            if {form_key(r) for r in rows} != {form_key(r) for r in data[RESULT_FILES[0]]}:
                raise ValueError(f'Source result mismatch: {path}')
            cells[key] = dict(dataset=dataset, config=config_name, model=model, method=method, pid=pid,
                              source_root=str(root), source_directory=str(path.parent), files=files,
                              before_summary=scoring.summarize(rows))

    for dataset in ('gold', 'hard'):
        for config in CONFIGS:
            for method in METHODS:
                root, slug, no_think = source_for(dataset, config, method)
                for case in [c for c in cases if c['id'].startswith(dataset + ':')]:
                    pid = case['id'].split(':')[1]
                    cid = canonical_id(case)
                    directory = root / pid / slug / method
                    qa_path = directory / 'qa_target_decanonicalized.json'
                    native = tracked(qa_path)
                    baseline = tracked(directory / RESULT_FILES[2])['items']
                    matches = [r for r in native if (r.get('id') or r.get('passage_id')) == cid]
                    existing = next((r for r in baseline if r['id'] == cid and r['q_type'] == case['form']), None)
                    if not matches:
                        proto_root = RUNS / ('full_ladder_2026-10-23' if dataset == 'gold' else 'hard66_full_ladder_2026-10-23')
                        native = tracked(proto_root / pid / '_base/_shared' / f'{pid}_base_qa_zh_decanonicalized.json')
                        matches = [r for r in native if (r.get('id') or r.get('passage_id')) == cid]
                    if len(matches) != 1:
                        raise ValueError(f'Cannot bind exact form {case["id"]}')
                    standard = copy.deepcopy(matches[0])
                    old_q = standard['Q']
                    standard['id'] = cid
                    standard['Q'] = GOLD_TRANSLATIONS[case['id']] if dataset == 'gold' else case['question']
                    if case['form'] == 'open':
                        standard['A'] = case['expected_answer']
                    else:
                        assert standard['correct'] == case['correct_option']
                        if dataset == 'hard':
                            assert standard['A'] == case['options']
                        if existing:
                            # Gold's historical MCQ score files also carry the
                            # source open-answer text. Preserve that metadata;
                            # MCQ correctness still uses the unchanged letter key.
                            standard['expected_answer'] = existing['standard_answer']
                    public = gen.public_question(standard, existing['item_index'] if existing else next(i for i, r in enumerate(native, 1) if (r.get('id') or r.get('passage_id')) == cid))
                    assert not ({'A', 'correct', 'expected_answer', 'required_keywords'} & set(public))
                    passage_path = directory / 'passage_target_decanonicalized.txt'
                    passage = tracked(passage_path, False)
                    windows_path = root / '_inputs/windows.json'
                    tracked(windows_path)
                    windows = gen.load_verse_windows(windows_path)
                    keys = gen.curated_window_for_item(windows, public)
                    if not keys:
                        raise ValueError(f'No curated window for {cid}')
                    index, order = gen.index_passage_verses(passage, gen.chapters_from_reference(public['passage_reference']))
                    local = gen.local_passage_for_question(passage, index, public, 2, order, windows)
                    if not local.strip():
                        raise ValueError(f'Empty passage: {case["id"]}, {method}')
                    if existing:
                        expected = scoring.build_standard_index([standard], placeholder_mapping=scoring.default_standard_placeholder_mapping())[cid]
                        if expected['standard_answer'] != existing['standard_answer'] or (case['form'] == 'mcq' and expected['correct_choice'] != existing['correct_choice']):
                            raise ValueError(f'Scoring standard changed: {case["id"]}')
                    input_data = dict(model=config[1], no_think=no_think, passage=local, question=gen.prompt_question(public),
                                      num_ctx=8192, num_predict=2500, temperature=0, mapper=settings['OPENAI_MCQ_CHOICE_MODEL'])
                    generation_key = digest(input_data)
                    scoring_key = digest(dict(generation_key=generation_key, standard=standard, settings=settings))
                    job = dict(id=f'{dataset}/{config[0]}/{method}/{cid}', dataset=dataset, config=config[0], method=method,
                               case_id=case['id'], model=config[1], no_think=no_think, public_question=public, standard=standard,
                               passage=local, window=[list(k) for k in keys], generation_key=generation_key, scoring_key=scoring_key,
                               baseline_directory=str(directory), has_baseline=bool(existing))
                    jobs.append(job)
                    questions[case['id']] = dict(accepted_case=case, displayed_question=standard['Q'], earlier_displayed_question=old_q,
                                               translation='Chinese translation of accepted English rewrite' if dataset == 'gold' else 'Accepted Chinese rewrite')
    assert len(jobs) == 1344 and len({j['id'] for j in jobs}) == len(jobs)
    sources = [Path(__file__), Path(gen.__file__), Path(scoring.__file__)]
    manifest = dict(version='changed_qa_replay_v1', settings=settings, jobs=jobs, cells=cells, questions=questions,
                    source_hashes=hashes, code_hashes={str(p): file_hash(p) for p in sources},
                    counts=dict(changed_forms=16, distinct_question_ids=9, evaluation_rows=len(jobs),
                                unique_generation_inputs=len({j['generation_key'] for j in jobs}),
                                existing_comparisons=sum(j['has_baseline'] for j in jobs), baseline_cells=len(cells)),
                    policy='Only changed forms are generated. Preserve original runs. Publish merged result copies with unchanged rows verbatim. New form/configuration coverage is separate. Exact repeated deterministic model inputs reuse a cached response, not an independent observation.')
    freeze(output / 'manifest.json', manifest)
    write(output / 'question_changes.json', questions)
    print(json.dumps(manifest['counts']), flush=True)
    return manifest


def restore_metadata(value, public):
    result = copy.deepcopy(value)
    for key in ('item_index', 'id', 'passage_id', 'passage_reference', 'q_type', 'question'):
        result[key] = public[key]
    return result


def run(output, manifest):
    from dotenv import load_dotenv
    load_dotenv(REPO / '.env')
    settings = manifest['settings']
    os.environ.update(OLLAMA_NUM_CTX='8192', OLLAMA_NUM_PREDICT='2500', OLLAMA_TIMEOUT='150')
    for p, sha in manifest['code_hashes'].items():
        if file_hash(p) != sha:
            raise ValueError(f'Execution code changed: {p}')
    jobs = sorted(manifest['jobs'], key=lambda j: (next(i for i,c in enumerate(CONFIGS) if c[0] == j['config']), j['dataset'], METHODS.index(j['method']), j['case_id']))
    state = dict(status='running', pid=os.getpid(), total=len(jobs), completed=0, generation_inputs=manifest['counts']['unique_generation_inputs'], started_at=time.time())
    write(output / 'state.json', state)
    futures = {}

    def score(job, answer):
        path = output / 'score_cache' / (job['scoring_key'] + '.json')
        if path.exists():
            return read(path)
        back = scoring.backtranslate_generated_answers([answer], [job['standard']], translation_model=settings['OPENAI_TRANSLATION_MODEL'], retries=2, temperature=0, reverse_glossary={})
        rows = scoring.score_items(back, [job['standard']], judge_model=settings['OPENAI_JUDGE_MODEL'], translation_model=settings['OPENAI_TRANSLATION_MODEL'], retries=2, skip_llm=False, placeholder_standard_answers=True, temperature=0)
        value = dict(backtranslated=back[0], score=rows[0])
        write(path, value)
        return value

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i, job in enumerate(jobs):
                answer_path = output / 'answer_cache' / (job['generation_key'] + '.json')
                state.update(current=job['id'], processed=i, generated_inputs=len(list((output/'answer_cache').glob('*.json'))) if (output/'answer_cache').exists() else 0)
                write(output / 'state.json', state)
                if answer_path.exists():
                    answer = restore_metadata(read(answer_path), job['public_question'])
                else:
                    print(f'ANSWER {i+1}/{len(jobs)} {job["id"]}', flush=True)
                    answers = gen.generate_answers(job['passage'], [job['public_question']], provider='ollama', model=job['model'],
                        ollama_base_url=os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'), batch_size=1, verse_window=None,
                        retries=2, dry_run=False, allow_partial_answers=False, ollama_no_think=job['no_think'],
                        expanded_answer_format=False, mcq_choice_mapper='openai', mcq_choice_model=settings['OPENAI_MCQ_CHOICE_MODEL'])
                    answer = answers[0]
                    if answer.get('generation_error'):
                        # The established answerer records empty model replies as
                        # failed responses. Keep that outcome, never reroll it.
                        write(output/'generation_failures'/(job['generation_key']+'.json'), answer)
                    if job['no_think'] and answer.get('answer_effort',{}).get('thinking_chars',0):
                        raise ValueError('Unexpected thinking output in no-thinking configuration')
                    write(answer_path, answer)
                if job['scoring_key'] not in futures:
                    futures[job['scoring_key']] = pool.submit(score, job, answer)
                # Surface scoring errors promptly while generation continues.
                for future in futures.values():
                    if future.done():
                        future.result()
            state.update(status='scoring', processed=len(jobs))
            write(output / 'state.json', state)
            for future in as_completed(list(futures.values())):
                future.result()
        state.update(status='complete', completed=len(jobs), finished_at=time.time(),
                     generated_inputs=len(list((output/'answer_cache').glob('*.json'))))
        write(output / 'state.json', state)
    except Exception as exc:
        state.update(status='failed', error=str(exc), finished_at=time.time())
        write(output / 'state.json', state)
        raise


def publish(output, manifest):
    if read(output/'state.json')['status'] != 'complete':
        raise ValueError('Cannot publish an incomplete replay')
    for path, sha in manifest['source_hashes'].items():
        if file_hash(path) != sha:
            raise ValueError(f'Baseline changed during replay: {path}')
    rows, patches = [], {}
    for job in manifest['jobs']:
        answer = restore_metadata(read(output/'answer_cache'/(job['generation_key']+'.json')), job['public_question'])
        cached = read(output/'score_cache'/(job['scoring_key']+'.json'))
        back = restore_metadata(cached['backtranslated'], job['public_question'])
        score = restore_metadata(cached['score'], job['public_question'])
        record = dict(id=job['id'], case_id=job['case_id'], dataset=job['dataset'], config=job['config'], method=job['method'],
                      has_baseline=job['has_baseline'], answer=answer, backtranslated=back, score=score)
        rows.append(record)
        patches[(job['dataset'],job['config'],job['method'],form_key(score))] = record
    summaries, replaced, untouched = [], 0, 0
    for key, cell in manifest['cells'].items():
        source = {name: read(path) for name,path in cell['files'].items()}
        before = source[RESULT_FILES[2]]['items']
        selected = [patches[(cell['dataset'],cell['config'],cell['method'],form_key(r))] for r in before
                    if (cell['dataset'],cell['config'],cell['method'],form_key(r)) in patches]
        for record in selected:
            old = next(r for r in before if form_key(r) == form_key(record['score']))
            assert old['standard_answer'] == record['score']['standard_answer']
            if old['q_type'] == 'mcq':
                assert old['correct_choice'] == record['score']['correct_choice']
        new_answers = merge_rows(source[RESULT_FILES[0]], [r['answer'] for r in selected])
        new_back = merge_rows(source[RESULT_FILES[1]], [r['backtranslated'] for r in selected])
        after = merge_rows(before, [r['score'] for r in selected])
        selected_keys = {form_key(r['score']) for r in selected}
        assert all(a == b for a,b in zip(before,after) if form_key(a) not in selected_keys)
        directory = output / 'updated_runs' / key
        write(directory/RESULT_FILES[0], new_answers)
        write(directory/RESULT_FILES[1], new_back)
        write(directory/RESULT_FILES[2], dict(summary=scoring.summarize(after), items=after))
        revised_qa = read(Path(cell['source_directory'])/'qa_target_decanonicalized.json')
        for q in revised_qa:
            qid = q.get('id') or q.get('passage_id')
            match = next((r for r in selected if r['score']['id'] == qid and r['score']['q_type'] == q['q_type']),None)
            if match:
                q['Q'] = match['score']['question']
        write(directory/'qa_target_decanonicalized.json', revised_qa)
        summaries.append(dict(source_cell=key, dataset=cell['dataset'], config=cell['config'], method=cell['method'], pid=cell['pid'],
                              changed_rows=len(selected), before=scoring.summarize(before), after=scoring.summarize(after)))
        replaced += len(selected)
        untouched += len(before)-len(selected)
    write(output/'changed_results.json', rows)
    write(output/'cell_summaries.json', summaries)
    write(output/'verification.json', dict(status='complete', evaluation_rows=len(rows), model_inputs=manifest['counts']['unique_generation_inputs'],
          updated_baseline_rows=replaced, unchanged_baseline_rows=untouched, baseline_cells=len(summaries),
          source_hashes_verified=len(manifest['source_hashes']), original_runs_unchanged=True,
          answer_keys_preserved=True, untouched_rows_identical=True, new_coverage_separate=True))
    print(json.dumps(read(output/'verification.json')),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=DEFAULT_OUTPUT)
    p.add_argument('--phase',choices=['prepare','run','publish','all'],default='all')
    args=p.parse_args();output=args.output_dir.resolve()
    if args.phase in ('prepare','all'):
        manifest=prepare(output)
    else:
        manifest=read(output/'manifest.json')
    if args.phase in ('run','all'):
        run(output,manifest)
    if args.phase in ('publish','all'):
        publish(output,manifest)


if __name__=='__main__':
    main()
