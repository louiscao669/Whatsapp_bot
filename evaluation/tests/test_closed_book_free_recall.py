from evaluation.scripts.mcq.diagnostics.run_hard66_closed_book_recall import messages_for,automatic_grade


def test_model_messages_contain_only_instructions_and_question():
    q='谁受伤逃出了那房子？'
    for thinking in (None,False,True):
        messages=messages_for(q,thinking)
        assert len(messages)==2
        assert messages[1]['content']==('/no_think\n\n' if thinking is False else '')+'问题：'+q
        assert 'existing knowledge' in messages[0]['content']
        assert 'No passage or answer choices' in messages[0]['content']
        assert '士基瓦' not in str(messages)


def test_failed_generation_is_not_an_abstention():
    assert automatic_grade({'answer':'','generation_error':'empty_response'},'乌西雅')['label']=='failure'


def test_exact_unknown_and_paraphrase_routes():
    assert automatic_grade({'answer':'乌西雅。'},'乌西雅')['score']==1
    assert automatic_grade({'answer':'我不知道。'},'乌西雅')['label']=='unknown'
    assert automatic_grade({'answer':'士基瓦的儿子们'},'士基瓦的七个儿子') is None
