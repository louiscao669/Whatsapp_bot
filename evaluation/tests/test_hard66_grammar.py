import json

import pytest

from evaluation.scripts.campaigns.current import run_hard66_grammar as campaign
from evaluation.agents import generate_chinese_answers as answers


def fixture_campaign(tmp_path, monkeypatch):
    root, old = tmp_path / 'new', tmp_path / 'old'
    pid, model, method = 't1_test', 'llama3.2:1b', 'grammar/5%'
    slug = 'llama321b_think'
    key = f'grammar/{model}/{pid}/{method}'
    row = {'id': 'question', 'q_type': 'mcq'}
    monkeypatch.setenv('OLLAMA_NUM_PREDICT', '2500')
    monkeypatch.setenv('OLLAMA_TIMEOUT', '150')
    monkeypatch.setattr(answers, 'load_qa_items', lambda p: [row])
    monkeypatch.setattr(answers, 'public_questions', lambda rows: rows)
    for base in [root, old]:
        (base / '_inputs').mkdir(parents=True)
        (base / '_inputs/windows.json').write_text('{}')
        shared = base / pid / '_base/_shared'
        shared.mkdir(parents=True)
        (shared / f'{pid}_base_qa_zh_decanonicalized.json').write_text('[]')
    source, saved = root / pid / method, old / pid / slug / method
    for directory in [source, saved]:
        directory.mkdir(parents=True)
        for name in [*campaign.ladder.TEXTS, 'passage_source_decanonicalized.txt', 'qa_target.json', 'qa_target_decanonicalized.json']:
            (directory / name).write_text('same content')
    for name in campaign.ladder.RESULTS:
        (saved / name).write_text(json.dumps({'items': [row]} if name.startswith('scores') else [row]))
    verified = campaign.ladder.verify_cell(saved, {('question', 'mcq')})
    (old / 'job.json').write_text(json.dumps({'num_predict': 2500, 'timeout_seconds': 150}))
    (old / 'campaign_state.json').write_text(json.dumps({'cells': {key: {'status': 'complete', **verified}}}))
    manifest = {'cells': [('grammar', model, pid, method)], 'total_cells': 1}
    return root, old, source, saved, key, manifest


def test_reuses_exact_results_but_not_changed_passages(tmp_path, monkeypatch):
    root, old, source, saved, key, manifest = fixture_campaign(tmp_path, monkeypatch)
    (source / 'passage_target.txt').write_text('changed passage')
    report = campaign.reuse_completed(root, old, manifest)
    assert report['changed_inputs'] == [key] and not report['reused']
    (source / 'passage_target.txt').write_text('same content')
    report = campaign.reuse_completed(root, old, manifest)
    assert report['reused'] == [key]
    state = json.loads((root / 'campaign_state.json').read_text())
    assert state['completed_cells'] == 1
    assert state['cells'][key]['result_hashes'] == campaign.ladder.verify_cell(saved, {('question', 'mcq')})['result_hashes']


def test_refuses_result_hash_changes(tmp_path, monkeypatch):
    root, old, _, saved, _, manifest = fixture_campaign(tmp_path, monkeypatch)
    (saved / campaign.ladder.RESULTS[0]).write_text(json.dumps([{'id': 'question', 'q_type': 'mcq', 'generated_answer': 'tampered'}]))
    with pytest.raises(ValueError, match='Completed source results changed'):
        campaign.reuse_completed(root, old, manifest)


def test_refuses_different_inference_limits(tmp_path, monkeypatch):
    root, old, _, _, _, manifest = fixture_campaign(tmp_path, monkeypatch)
    monkeypatch.setenv('OLLAMA_NUM_PREDICT', '5000')
    with pytest.raises(ValueError, match='different inference limits'):
        campaign.reuse_completed(root, old, manifest)
