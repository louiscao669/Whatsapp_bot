from copy import deepcopy

import pytest

from evaluation.scripts.campaigns.current import audit_window_dose_answerability as a


def case():
    return dict(case_id='test',content=dict(question='谁来了？',passage='有人来了。',
        choices=dict(A='甲',B='乙',C='丙',D='丁',E='无法判断')),
        clean_key='A',family='omission',dose=60,clean_verses={'1':'甲来了。'},responses=[{'choice':'E'}])


def judgment(finding='information_missing',options=None,quotes=None):
    return dict(case_id='test',finding=finding,supported_options=options or [],
                evidence_quotes=quotes or [],reason='The visitor is not identified.')


def test_review_payload_is_isolated_and_hides_key_original_and_reader_response():
    p=a.payload_for([case()])
    assert set(p['cases'][0])=={'case_id','question','choices','passage'}
    assert '甲来了。' not in str(p)
    with pytest.raises(ValueError,match='Isolate'):
        a.payload_for([case(),case()])


def test_two_independent_missing_information_findings_support_e():
    assert a.reconcile(judgment(),judgment())==dict(status='e_supported',e_correct=True,displayed_key='E')


def test_changed_a_d_answer_is_recorded_instead_of_e():
    j=judgment('unique_answer',['D'],['有人来了。'])
    assert a.reconcile(j,j)==dict(status='a_d_supported',e_correct=False,displayed_key='D')


@pytest.mark.parametrize('finding',['multiple_answers','contradiction','premise_mismatch','uncertain'])
def test_menu_or_premise_problems_never_automatically_become_e(finding):
    j=judgment(finding,['A','B'] if finding=='multiple_answers' else [])
    assert a.reconcile(j,j)==dict(status='held_for_review',e_correct=None,displayed_key=None)


@pytest.mark.parametrize('first,second',[
    ('answer_not_in_options','answer_not_in_options'),
    ('information_missing','answer_not_in_options'),
    ('answer_not_in_options','information_missing'),
])
def test_unlisted_answer_and_missing_information_both_support_e(first,second):
    assert a.reconcile(judgment(first),judgment(second))==dict(status='e_supported',e_correct=True,displayed_key='E')


def test_disagreement_is_held():
    assert a.reconcile(judgment(),judgment('unique_answer',['A']))['e_correct'] is None
    assert a.reconcile(judgment('unique_answer',['A']),judgment('unique_answer',['B']))['e_correct'] is None


def test_validation_rejects_cross_window_quotes_and_duplicate_ids():
    p=a.payload_for([case()])
    good=judgment(quotes=['有人来了。'])
    a.validate(a.Assessment(cases=[good]),p)
    bad=deepcopy(good);bad['evidence_quotes']=['甲来了。']
    with pytest.raises(ValueError,match='exact displayed'):
        a.validate(a.Assessment(cases=[bad]),p)
    with pytest.raises(ValueError,match='duplicate'):
        a.validate(a.Assessment(cases=[good,good]),p)


def test_original_experiment_has_one_record_per_displayed_case():
    cases,hashes=a.load_inventory(a.ANALYSIS)
    assert len(cases)==1252
    assert sum(len(c['responses']) for c in cases)==8764
    assert all(c['status']=='unreviewed' and c['e_correct'] is None for c in cases)
    assert sum(c['passage_id']=='t1_1kgs13' for c in cases)==152
    assert sum(r['choice']=='E' for c in cases for r in c['responses'])==828
    assert len(hashes)==20


def test_manual_flags_preserve_model_findings_and_only_quarantine():
    c=case();c.update(a.reconcile(judgment(),judgment()))
    m=dict(cases=[c]);flag=dict(case_id='test',reason='Only an incidental identifying detail is missing.',author='Codex')
    a.apply_review_flags(m,[flag])
    assert c['e_correct'] is None and c['status']=='held_for_review'
    assert c['automated_consensus']['e_correct'] is True
    a.apply_review_flags(m,[flag])
    assert c['automated_consensus']['e_correct'] is True


def test_policy_migration_preserves_evidence_unreviewed_cases_and_local_holds():
    c=case();c.update(status='held_for_review',e_correct=None,displayed_key=None,
        assessments={'primary_assessment':judgment('answer_not_in_options'),
                     'independent_review':judgment('answer_not_in_options')})
    pending=dict(case_id='pending',status='unreviewed',e_correct=None,displayed_key=None)
    m=dict(policy='displayed_window_answerability_v1',prompt_sha256='original-review-prompt',cases=[c,pending])
    original=deepcopy(c['assessments']);responses=deepcopy(c['responses'])
    a.apply_current_policy(m,[])
    assert c['e_correct'] is True and m['policy']==a.POLICY
    assert c['assessments']==original and c['responses']==responses
    assert m['prompt_sha256']=='original-review-prompt' and pending['status']=='unreviewed'
    assert len(m['policy_history'][0]['changes'])==1
    a.apply_current_policy(m,[])
    assert len(m['policy_history'])==1
    a.apply_current_policy(m,[dict(case_id='test',reason='An identifying detail still needs review.')])
    assert c['status']=='held_for_review' and c['automated_consensus']['e_correct'] is True
