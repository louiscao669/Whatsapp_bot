#!/usr/bin/env python3
"""Run saved Gold72 defect inputs across four inference configurations."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.campaigns.current import run_overnight_ladder as ladder
from evaluation.scripts.campaigns.current.run_hard66_grammar import verify_hashes
from evaluation.agents.generate_chinese_answers import load_qa_items, public_questions

ROOT = REPO / 'evaluation/runs/gold72_four_configs_2026-10-27'
SOURCE = REPO / 'evaluation/runs/full_ladder_2026-10-23'
CONFIGS = [('llama3.2:1b', False), ('qwen2.5:1.5b', False), ('qwen3:1.7b', True), ('qwen3:1.7b', False)]
METHODS = [('clean', 'omission/0%')] + [(f, f'{f}/{r}%') for f in ['omission', 'mistranslation', 'grammar'] for r in [5,10,15,20,25,30]] + [('wbw', 'google_word_by_word')]


def prepare():
    release = ladder.read(SOURCE / 'release.json')
    verify_hashes(SOURCE, release['input_hashes'])
    stages = []
    for model, think in CONFIGS:
        slug = model.replace(':','').replace('.','') + ('_think' if think else '_nothink')
        root = ROOT / slug
        for path in (SOURCE / '_inputs').rglob('*'):
            if path.is_file():
                ladder.snapshot(path, root / path.relative_to(SOURCE))
        counts = {}
        for pid in ladder.PASSAGES:
            for suffix in ['qa_zh.json', 'qa_zh_decanonicalized.json']:
                name = f'{pid}_base_{suffix}'
                rows = [r for r in load_qa_items(SOURCE / pid / '_base/_shared' / name) if r['q_type'] == 'mcq']
                ladder.write_atomic(root / pid / '_base/_shared' / name, rows)
                counts[pid] = len(public_questions(rows))
            for _, method in METHODS:
                for name in ladder.ARTIFACTS:
                    if name.startswith('qa_target'):
                        suffix = 'qa_zh_decanonicalized.json' if 'decanonicalized' in name else 'qa_zh.json'
                        ladder.snapshot(root / pid / '_base/_shared' / f'{pid}_base_{suffix}', root / pid / method / name)
                    else:
                        ladder.snapshot(SOURCE / pid / method / name, root / pid / method / name)
                for path in (SOURCE / pid / method).glob('*_metadata.json'):
                    ladder.snapshot(path, root / pid / method / path.name)
        cells = [(stage, model, pid, method) for stage, method in METHODS for pid in ladder.PASSAGES]
        manifest = {'dataset': 'tier1_gold72_canonical_5opt', 'source': str(SOURCE), 'model': model, 'thinking': think,
                    'qa_formats': ['mcq'], 'question_counts': counts, 'questions_per_condition': sum(counts.values()),
                    'cells': cells, 'total_responses': sum(counts.values()) * len(METHODS),
                    'input_hashes': {str(p.relative_to(root)): ladder.fingerprint(p) for p in root.rglob('*') if p.is_file() and (p.name in ladder.ARTIFACTS or '_inputs' in p.parts or '_shared' in p.parts)}}
        ladder.write_atomic(root / 'release.json', manifest)
        stages.append({'root': str(root), 'model': model, 'thinking': think, 'responses': manifest['total_responses']})
    plan = {'stages': stages, 'source': str(SOURCE), 'conditions': METHODS, 'total_responses': sum(s['responses'] for s in stages)}
    ladder.write_atomic(ROOT / 'plan.json', plan)
    return plan


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    lock = (ROOT / 'run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = prepare()
    if '--prepare-only' in sys.argv:
        print(plan)
        return
    from dotenv import load_dotenv
    load_dotenv(REPO / '.env')
    os.environ.update(QA_FORMATS='mcq', MCQ_CHOICE_LABELS='ABCDE', MCQ_ABSTAIN_LABEL='E', MCQ_KEEP_THINKING='1',
                      OLLAMA_NUM_CTX='8192', OLLAMA_NUM_PREDICT='2500', OLLAMA_TIMEOUT='150')
    job = {'status': 'running', 'pid': os.getpid(), 'started_at': time.time()}
    caffeinate = subprocess.Popen(['/usr/bin/caffeinate','-is','-w',str(os.getpid())])
    try:
        for stage in plan['stages']:
            root = Path(stage['root'])
            job.update(current_configuration=root.name)
            ladder.write_atomic(ROOT / 'job.json', job)
            manifest = ladder.read(root / 'release.json')
            verify_hashes(root, manifest['input_hashes'])
            ladder.evaluate(root, selected_cells=[tuple(c) for c in manifest['cells']], no_think=not stage['thinking'])
            state = ladder.read(root / 'campaign_state.json')
            if state['status'] != 'complete':
                raise RuntimeError(f'Incomplete configuration: {root.name}')
            summaries = []
            slug = stage['model'].replace(':','').replace('.','') + ('_think' if stage['thinking'] else '_nothink')
            for family, method in METHODS:
                scores, answers = [], []
                for pid in ladder.PASSAGES:
                    dest = root / pid / slug / method
                    scores.extend(ladder.read(dest / 'scores_target_llama.json')['items'])
                    answers.extend(ladder.read(dest / 'generated_answers_target_llama.json'))
                summaries.append({'condition': method, 'correct': sum(bool(r['direct_correct']) for r in scores), 'n': len(scores),
                                  'generation_errors': sum(bool(r.get('generation_error')) for r in answers)})
            ladder.write_atomic(root / 'results_summary.json', {'model':stage['model'], 'thinking':stage['thinking'], 'conditions':summaries})
        job.update(status='complete', finished_at=time.time())
    except Exception as exc:
        job.update(status='failed', error=str(exc), finished_at=time.time())
        raise
    finally:
        ladder.write_atomic(ROOT / 'job.json', job)
        caffeinate.terminate()

if __name__ == '__main__':
    main()
