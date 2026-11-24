from copy import deepcopy
from itertools import combinations
from types import SimpleNamespace

import pytest

from evaluation.scripts.analysis.current import audit_mistranslation_capacity as audit


def groups():
    def edit(start,n):return audit.d.Edit('1:1',start,'甲'*n,'乙'*n)
    return {0:[edit(0,3),edit(8,2)],1:[edit(2,4)],2:[edit(6,2)],3:[edit(9,1)]}


def test_maximum_matches_brute_force_with_systematic_groups_and_overlaps():
    pool=groups();possible=[]
    for n in range(len(pool)+1):
        for ids in combinations(pool,n):
            masks=[audit.d.positions(pool[i]) for i in ids]
            if any(a&b for a,b in combinations(masks,2)):continue
            possible.append(sum(len(audit.d.content_positions(pool[i])) for i in ids))
    selected,maximum=audit.maximize(pool)
    assert maximum==max(possible)==7
    rendered=[audit.d.positions(pool[i]) for i in selected]
    assert not any(a&b for a,b in combinations(rendered,2))


def test_published_selection_must_include_whole_systematic_group():
    pool=groups()
    cell={'edits':[audit.d.asdict(e) for e in pool[0]+pool[2]]}
    assert audit.recover_selection(pool,cell)==[0,2]
    cell['edits'].pop(0)
    with pytest.raises(ValueError,match='cannot be traced'):audit.recover_selection(pool,cell)


def test_identical_versions_share_review_and_do_not_send_question(monkeypatch,tmp_path):
    cell=dict(verses={'1:1':'乙'},edits=[dict(verse='1:1',start=0,before='甲',after='乙')])
    w=dict(id='w',clean={'1:1':'甲'},maximum=deepcopy(cell),current30=deepcopy(cell),question='SECRET')
    def fake(client,folder,stage,model,prompt,payload,schema,validate):
        assert 'SECRET' not in str(payload)
        assert len(payload['variants'])==1
        checks=dict.fromkeys(audit.Checks.model_fields,'yes');checks['fluent']='no'
        result=audit.Decisions(decisions=[audit.Decision(number=1,checks=checks,flags=[],reason='Broken construction.')])
        validate(result);return result
    monkeypatch.setattr(audit.m.review,'ask',fake)
    audit.review_window(None,w,SimpleNamespace(english={'1:1':'Source'}),tmp_path)
    assert w['maximum']['review_status']==w['current30']['review_status']=='rejected'
    assert w['current30']['shared_review_with_maximum']
