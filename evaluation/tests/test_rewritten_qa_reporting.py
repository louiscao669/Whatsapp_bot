from evaluation.scripts.analysis.report_rewritten_qa_models import metrics, recover_selected_choice


def row(key, choice, correct=False):
    return {'id':key, 'q_type':'mcq', 'selected_choice':choice, 'direct_correct':correct}


def test_recovers_e_from_answer_log_without_changing_correctness():
    original=row('q1',None)
    recovered=recover_selected_choice(original,row('q1','E'))
    assert recovered['selected_choice']=='E'
    assert recovered['direct_correct'] is False
    assert original['selected_choice'] is None


def test_outcomes_partition_denominator_and_do_not_treat_failures_as_e():
    result=metrics([row('q1','B',True),row('q2','A'),row('q3','E'),row('q4',None)])
    assert result['mcq_n']==4
    assert result['mcq_correct']==result['mcq_incorrect_ad_count']==result['mcq_e_count']==result['mcq_unresolved_count']==1
    assert result['mcq_accuracy']==result['mcq_e_rate']==.25
    assert result['mcq_accuracy_excluding_e']==1/3
    assert result['mcq_accuracy_among_ad']==.5


def test_missing_response_stays_unresolved():
    recovered=recover_selected_choice(row('q1',None),row('q1',None))
    assert recovered['selected_choice'] is None
