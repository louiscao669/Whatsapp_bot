from copy import deepcopy
from types import SimpleNamespace

import pytest

from evaluation.scripts.pipeline import build_nested_window_defects as n
from evaluation.scripts.pipeline import repair_nested_agreement as r


def ladder():
    w=dict(id='w',clean={'1:1':'他'+'甲'*99},clean_content_chars=100)
    pool=[n.make_candidate([dict(verse='1:1',start=i,before='甲'*5,after='乙'*5)]) for i in range(1,81,5)]
    companion=n.make_candidate([dict(verse='1:1',start=0,before='他',after='她')]);pool.append(companion)
    cells={str(d):n.materialize(w,pool,[c['id'] for c in pool[:d//5]]+
        ([companion['id']] if d>=50 else []),'mistranslation',d) for d in n.DOSES}
    patches=r.Repairs(levels=[r.Patch(dose=d,remove_edit_numbers=[],reason='Model proposes earlier agreement.',
        add=[n.ProposedEdit(verse='1:1',before='他',after='她',occurrence=1)] if d<50 else []) for d in n.DOSES])
    return w,cells,patches


def test_companion_enters_earlier_doses_is_counted_and_nested():
    w,cells,patches=ladder();pool,fixed=r.compile_patches(w,cells,patches)
    assert [c['actual_percent'] for c in fixed.values()]==[31,41,51,61]
    assert all(c['verses']['1:1'].startswith('她') for c in fixed.values())
    n.validate_chain(w,fixed,'mistranslation')
    with pytest.raises(ValueError,match='prerequisite'):
        n.materialize(w,pool,[pool[1]['id']],'mistranslation',40)
    solution=n.plan([w],{'w':pool},'mistranslation',strict=True)
    assert solution
    for ids in solution['selected'].values():
        assert all(set(c['requires'])<=set(ids) for c in pool if c['id'] in ids)


def test_nonpronoun_changes_and_lost_nesting_are_rejected():
    w,cells,patches=ladder()
    invalid=deepcopy(patches);invalid.levels[0].remove_edit_numbers=[1]
    with pytest.raises(ValueError,match='source pronouns'):r.compile_patches(w,cells,invalid)
    invalid=deepcopy(patches);invalid.levels[1].add=[]
    with pytest.raises(ValueError,match='lower-dose'):r.compile_patches(w,cells,invalid)


def test_gender_conflict_is_rejected_despite_other_five_checks(monkeypatch,tmp_path):
    w,cells,_=ladder();cell=cells['30']
    def fake(client,folder,stage,model,prompt,payload,schema,validate):
        checks=dict.fromkeys(n.mr.Checks.model_fields,'yes');checks['gender_agreement']='no'
        answer=n.mr.Decisions(decisions=[n.mr.Decision(number=1,checks=checks,flags=[],reason='女儿…他 mismatch')])
        validate(answer);return answer
    monkeypatch.setattr(n.m.review,'ask',fake)
    n.review_cells(None,w,{1:cell},SimpleNamespace(english={'1:1':'Source'}),tmp_path,'mistranslation')
    assert cell['status']=='rejected'
    old=deepcopy(cell);old['checks'].pop('gender_agreement');old['status']='pass'
    assert n.remembered_review([{'30':old}],cell) is None
    assert n.remembered_review([{'30':cell}],cell)['status']=='rejected'
