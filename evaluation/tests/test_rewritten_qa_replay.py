import copy

import pytest

from evaluation.scripts.campaigns.current import rerun_rewritten_qa as replay


def test_merge_updates_exact_form_and_preserves_other_rows_and_indices():
    rows = [dict(id='x', q_type='open', item_index=4, question='old', value=0),
            dict(id='x', q_type='mcq', item_index=5, question='unchanged', value=1)]
    snapshot = copy.deepcopy(rows)
    patch = dict(id='x', q_type='open', item_index=1, question='new', value=2)
    actual = replay.merge_rows(rows, [patch])
    assert rows == snapshot
    assert actual[0] == dict(patch, item_index=4)
    assert actual[1] == rows[1]


def test_merge_rejects_unmatched_or_duplicate_replacements():
    rows = [dict(id='x', q_type='open')]
    with pytest.raises(ValueError):
        replay.merge_rows(rows, [dict(id='x', q_type='mcq')])
    with pytest.raises(ValueError):
        replay.merge_rows(rows, [rows[0], rows[0]])


def test_input_publication_hides_answers_and_keeps_all_five_choices():
    standard = dict(id='uw-x-mcq', passage_id='uw-x-mcq', passage_reference='Acts 19:11-20',
                    q_type='mcq', Q='谁？', A={k:k for k in 'ABCDE'}, correct='D', expected_answer='secret')
    q = replay.gen.public_question(standard, 3)
    sent = replay.gen.prompt_question(q)
    assert set(sent) == {'q_type', 'question', 'choices'}
    assert list(sent['choices']) == list('ABCDE')
    assert 'secret' not in str(sent)
    assert 'correct' not in sent


def test_routes_keep_dataset_specific_no_think_prompt_settings():
    gold, _, gold_no_think = replay.source_for('gold', replay.CONFIGS[0], 'grammar/5%')
    hard, _, hard_no_think = replay.source_for('hard', replay.CONFIGS[0], 'grammar/5%')
    assert gold_no_think is True
    assert hard_no_think is False
    assert 'gold72_four_configs' in str(gold)
    assert hard.name == 'hard66_grammar_full_2026-10-24'


def test_restore_cache_identity_does_not_overwrite_answer():
    result = dict(id='old', item_index=1, question='q', q_type='open', generated_answer='answer')
    public = dict(id='new', item_index=9, question='q', q_type='open', passage_id='new', passage_reference='ref')
    actual = replay.restore_metadata(result, public)
    assert actual['id'] == 'new' and actual['item_index'] == 9
    assert actual['generated_answer'] == 'answer'
    assert result['id'] == 'old'
