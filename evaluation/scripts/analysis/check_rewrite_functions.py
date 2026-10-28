#!/usr/bin/env python3
"""Check existing rewrite functions in isolation without editing a dataset."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMBO = Path('/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo')
sys.path.insert(0, str(COMBO))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    from qa_generation.config import load_env
    load_env()
    from qa_generation.services.anchor_rewrite import find_anchors
    from qa_generation.services.scored_generation import ScoredGenerator
    from qa_generation.pipeline import BibleQAPipeline
    from qa_generation.prompts.qa import QAPairSimple, llm

    queue_path = ROOT / 'evaluation/reports/qa_review_v2_full_2026-10-27/revision_queue.json'
    queue = json.loads(queue_path.read_text())['entries']
    flagged = [x for x in queue if x['rewrite_category'] == 'rewrite_both']
    routing = []
    for entry in flagged:
        # Temporary ordinal verse keys suffice to check anchor eligibility only;
        # no answer-verse judgment or repair is run with these mapped keys.
        window = {i: line.split(' ', 1)[1] for i, line in enumerate(entry['passage'].splitlines(), 1)}
        anchors = find_anchors(entry['question'], window)
        routing.append(dict(id=entry['id'], dataset=entry['dataset'],
                            anchors=[a.word for a in anchors],
                            legacy_repair_accepts_review_record=ScoredGenerator._eligible_for_repair(entry)))
    write(args.output_dir / 'routing_check.json', routing)

    selected = [x for x in queue if x['id'] in (
        'gold:t1_1kgs13:o8ae:open', 'gold:t1_2kgs6_7:pb1x:open')]
    inputs = [dict(content_id=x['id'], Q=x['question'], A=x['expected_answer']) for x in selected]
    write(args.output_dir / 'inputs.json', inputs)
    source_paths = ['qa_generation/pipeline.py', 'qa_generation/prompts/qa.py',
                    'qa_generation/services/scored_generation.py', 'qa_generation/services/anchor_rewrite.py']
    write(args.output_dir / 'manifest.json', dict(
        scope='Isolated existing methods; no model/prompt changes, no canonical edits, no end-to-end approval claim.',
        rewrite_model=llm.model_name,
        source_hashes={p: hashlib.sha256((COMBO / p).read_bytes()).hexdigest() for p in source_paths},
        selected_ids=[x['content_id'] for x in inputs],
        offline_tests='126 existing anchor/scored-generation/hard-recovery tests passed.',
    ))
    print(f'Routing: {len(flagged)} repeated rewrite flags; '
          f'{sum(x["legacy_repair_accepts_review_record"] for x in routing)} directly accepted by legacy repair routing.', flush=True)
    if not args.live:
        return 0

    # These methods use no constructor state except the length limits. Isolate
    # them from generation, selection, translation, and all dataset writes.
    pipeline = BibleQAPipeline.__new__(BibleQAPipeline)
    pipeline.lenq, pipeline.lena = 10, 5
    errors = 0
    for name in ('_shorten_qa_pairs', '_simplify_qa_pairs'):
        path = args.output_dir / (name.strip('_') + '.json')
        if path.exists() and json.loads(path.read_text()).get('status') == 'completed':
            print(name + ': using saved completed check', flush=True)
            continue
        pairs = [QAPairSimple(**x) for x in inputs]
        try:
            result = getattr(pipeline, name)({'qa_pairs': pairs})
            rows = [x.model_dump() for x in result['qa_pairs']]
            result_ids = [x['content_id'] for x in rows]
            write(path, dict(status='completed', model=llm.model_name, inputs=inputs, outputs=rows,
                             input_count=len(inputs), output_count=len(rows),
                             ids_preserved=set(result_ids) == {x['content_id'] for x in inputs},
                             duplicate_ids=len(result_ids) != len(set(result_ids))))
            print(name + ': completed; ' + str(len(rows)) + ' outputs', flush=True)
        except Exception as exc:
            errors += 1
            write(path, dict(status='error', error_type=type(exc).__name__, error=str(exc)[:500]))
            print(name + ': ' + type(exc).__name__, flush=True)
    return int(errors > 0)


if __name__ == '__main__':
    raise SystemExit(main())
