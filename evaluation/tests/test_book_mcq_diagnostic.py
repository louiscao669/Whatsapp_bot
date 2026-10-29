from evaluation.scripts.mcq.diagnostics.run_hard66_book_mcq import (
    ARMS, CLOSED_E, messages_for, parse_choice, score,
)


ITEM = dict(question='谁做了这件事？', private_clean_passage='私有测试经文。',
            reference='Do not send this reference', correct='B',
            choices={'A':'人物甲', 'B':'人物乙', 'C':'人物丙', 'D':'人物丁', 'E':'根据这段文字无法判断'})


def test_closed_book_omits_passage_and_key_and_keeps_content_options():
    for arm in (a for a in ARMS if a['condition'] == 'closed_book'):
        messages = messages_for(ITEM, arm)
        text = messages[1]['content']
        assert ITEM['private_clean_passage'] not in text and ITEM['reference'] not in text
        assert 'correct' not in text and '答案：B' not in text
        assert all(f'{k}. {ITEM["choices"][k]}' in text for k in 'ABCD')
        assert f'E. {CLOSED_E}' in text
        assert text.startswith('/no_think') == (arm['thinking'] is False)


def test_open_book_includes_only_supplied_passage_question_choices():
    arm = next(a for a in ARMS if a['condition'] == 'open_book')
    text = messages_for(ITEM, arm)[1]['content']
    assert text.startswith('经文：\n'+ITEM['private_clean_passage'])
    assert 'E. 根据这段文字无法判断' in text
    assert ITEM['reference'] not in text


def test_e_is_recovered_and_ambiguous_answers_are_not_guessed():
    assert parse_choice('Ｅ。', ITEM['choices'])[0] == 'E'
    assert parse_choice('答案：B', ITEM['choices'])[0] == 'B'
    assert parse_choice('Answer: E.', ITEM['choices'])[0] == 'E'
    assert parse_choice('A or B', ITEM['choices'])[0] is None
    assert parse_choice('I cannot decide.', ITEM['choices'])[0] is None
    assert parse_choice('人物丙', ITEM['choices'])[0] == 'C'


def test_failure_invalid_abstention_and_wrong_answer_are_distinct():
    arm = ARMS[0]
    def label(answer, error=None):
        return score({'answer':answer, 'generation_error':error}, ITEM, arm)['label']
    assert label('', 'empty_response') == 'failure'
    assert label('A or B') == 'invalid'
    assert label('E') == 'abstain_e'
    assert label('A') == 'incorrect_ad'
    assert label('B') == 'correct'
