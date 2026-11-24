from copy import deepcopy
from types import SimpleNamespace

import pytest

from evaluation.scripts.pipeline import build_all_low_dose_defects as campaign


def fixture():
    clean={'1:1':'甲乙丙丁戊'}
    w=dict(id='test',clean=clean,question='问题')
    qa=dict(question='问题',choices=['甲','乙'],correct='A')
    candidate=dict(id='edit1',edits=[dict(verse='1:1',start=0,before='甲',after='')],chars=1,kinds=['word'])
    cell=dict(status='pass',selected_ids=['edit1'],checks={'information_omitted':'yes'})
    base=dict(clean=clean,pool=[candidate],history=[],cells={'30':cell},baseline={})
    old=dict(clean=clean,qa=qa,pool=[candidate],history=[{'5':cell}],cells={'5':cell})
    checked=[]
    driver=SimpleNamespace(check_cell=lambda w,p,d,c:checked.append(d))
    return w,qa,base,old,driver,checked


def test_reuse_deduplicates_and_verifies_without_mutating_original():
    w,qa,base,old,driver,checked=fixture();before=deepcopy(base)
    fixed,merged=campaign.merge_reuse(w,qa,base,[old,deepcopy(old)],driver)
    assert set(fixed['cells'])=={'5','30'}
    assert len(merged['pool'])==1
    assert checked.count(5)>=2 and 30 in checked
    assert base==before


@pytest.mark.parametrize('change',['qa','candidate','forbidden','text'])
def test_reuse_rejects_changed_inputs_and_constraints(change):
    w,qa,base,old,driver,checked=fixture()
    old=deepcopy(old)
    if change=='qa':old['qa']['question']='新问题'
    if change=='candidate':old['pool'][0]['requires']=['missing-companion']
    if change=='forbidden':base['baseline']['forbidden_candidate_sets']=[['edit1']]
    if change=='text':old['clean']['1:1']='不同'
    with pytest.raises(ValueError):campaign.merge_reuse(w,qa,base,[old],driver)
