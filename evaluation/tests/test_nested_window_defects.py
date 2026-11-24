from copy import deepcopy
from types import SimpleNamespace

import pytest

from evaluation.scripts.pipeline import build_nested_window_defects as n


def fixture(family='omission'):
    clean={'1:1':'甲'*50,'1:2':'乙'*50}
    w=dict(id='w',clean=clean,clean_content_chars=100)
    pool=[]
    for verse,body in clean.items():
        for start in range(0,40,5):
            pool.append(n.make_candidate([dict(verse=verse,start=start,before=body[start:start+5],
                after='' if family=='omission' else '丙'*5)],['clause'] if family=='omission' else []))
    return w,pool


@pytest.mark.parametrize('family',['omission','mistranslation'])
def test_four_levels_are_nested_and_in_band(family):
    w,pool=fixture(family)
    solution=n.plan([w],{'w':pool},family,strict=True)
    cells={str(d):n.materialize(w,pool,solution['selected'][('w',d)],family,d) for d in n.DOSES}
    for d,c in cells.items():
        assert abs(c['actual_percent']-int(d))<=2
        c['status']='pass'
    n.validate_chain(w,cells,family)
    assert not n.all_pass({k:v for k,v in cells.items() if k!='40'})
    cells['40']['status']='rejected'
    assert not n.all_pass(cells)


def test_fixed_baseline_and_rejected_combination_are_respected():
    w,pool=fixture();first=n.plan([w],{'w':pool},'omission',strict=True)
    fixed={('w',30):first['selected'][('w',30)]}
    ban=[('w',60,first['selected'][('w',60)])]
    second=n.plan([w],{'w':pool},'omission',fixed=fixed,banned=ban,strict=True)
    assert second['selected'][('w',30)]==fixed[('w',30)]
    assert set(second['selected'][('w',60)])!=set(ban[0][2])


@pytest.mark.parametrize('weights,expected', [
    (None, {'word': 2, 'phrase': 4, 'clause': 4}),
    ({'word': 20, 'phrase': 50, 'clause': 30}, {'word': 2, 'phrase': 5, 'clause': 3}),
])
def test_configurable_omission_mix_uses_occurrences_and_preserves_dose(weights, expected):
    w=dict(id='mix',clean={'1:1':'甲'*100},clean_content_chars=100)
    kinds=['word']*5+['phrase']*10+['clause']*10
    pool=[n.make_candidate([dict(verse='1:1',start=i*3,before='甲'*3,after='')],[kind])
          for i,kind in enumerate(kinds)]
    solution=n.plan([w],{'mix':pool},'omission',strict=True,doses=(30,),omission_mix=weights)
    cell=n.materialize(w,pool,solution['selected'][('mix',30)],'omission',30)
    assert cell['unit_counts']==expected and cell['actual_percent']==30
    assert solution['objectives']['mixture_event_count_deviation']==0


@pytest.mark.parametrize('weights', [
    {'word':0,'phrase':0,'clause':0}, {'word':-1,'phrase':2,'clause':3},
    {'word':0.2,'phrase':0.5,'clause':0.3}, {'word':20,'phrase':50},
])
def test_invalid_omission_mix_is_rejected(weights):
    with pytest.raises(ValueError,match='Omission mix'):
        n.omission_mix_weights(weights)


def test_preference_retains_passing_levels_without_freezing_the_ladder():
    w,pool=fixture();first=n.plan([w],{'w':pool},'omission',strict=True)
    preferred={('w',d):first['selected'][('w',d)] for d in (30,40,50)}
    next_plan=n.plan([w],{'w':pool},'omission',preferred=preferred,
        banned=[('w',60,first['selected'][('w',60)])],strict=True,seed=42)
    assert all(set(next_plan['selected'][k])==set(v) for k,v in preferred.items())
    assert set(next_plan['selected'][('w',60)])!=set(first['selected'][('w',60)])


def test_optional_tie_timeout_retains_verified_feasible_selection(monkeypatch):
    model=n.NestedModel();x=model.var();model.constrain({x:1},1,1)
    assert list(model.solve({}))==[1]
    monkeypatch.setattr(n.m,'milp',lambda *a,**kw:SimpleNamespace(status=1,success=False,x=None,message='time limit'))
    model.allow_feasible=True
    assert list(model.solve({x:1}))==[1] and model.used_fallback
    model.constrain({x:1},0,0)
    with pytest.raises(RuntimeError,match='verified feasible'):model.solve({})


def test_optional_false_infeasibility_preserves_only_a_valid_integer_witness(monkeypatch):
    model=n.NestedModel();x=model.var();model.constrain({x:1},1,1)
    assert list(model.solve({}))==[1]
    monkeypatch.setattr(n.m,'milp',lambda *a,**kw:SimpleNamespace(status=2,success=False,x=None,message='infeasible'))
    model.allow_feasible=True;model.stage='mixture_preference'
    assert list(model.solve({x:1}))==[1]
    assert model.fallback_stages==['mixture_preference_verified_witness']
    model.constrain({x:1},0,0)
    assert model.solve({}) is None


def test_atomic_bundle_cannot_be_partially_applied_and_overlap_is_forbidden():
    w,pool=fixture()
    bundle=n.make_candidate(pool[0]['edits']+pool[1]['edits'],['clause','clause'])
    pool.append(bundle)
    solution=n.plan([w],{'w':pool},'omission',fixed={('w',30):[bundle['id'],pool[2]['id'],pool[3]['id'],pool[4]['id'],pool[5]['id']]},strict=True)
    assert solution
    for ids in solution['selected'].values():
        if bundle['id'] in ids:assert pool[0]['id'] not in ids and pool[1]['id'] not in ids
    with pytest.raises(ValueError,match='Overlapping'):
        n.materialize(w,pool,[bundle['id'],pool[0]['id']],'omission',30)


def test_inherited_failed_candidate_interaction_is_excluded_at_every_dose():
    w,pool=fixture('mistranslation');bad=[pool[0]['id'],pool[1]['id']]
    solution=n.plan([w],{'w':pool},'mistranslation',forbidden=[('w',bad)],strict=True)
    assert solution
    assert all(not set(bad)<=set(ids) for ids in solution['selected'].values())


def test_review_does_not_receive_target_question_key_or_writer_rationale(monkeypatch,tmp_path):
    w,pool=fixture();w.update(question='SECRET',answer_evidence='SECRET')
    cell=n.materialize(w,pool,[pool[0]['id']],'omission',30)
    def fake(client,folder,stage,model,prompt,payload,schema,validate):
        assert 'SECRET' not in str(payload)
        assert 'target_percent' not in str(payload)
        d=n.m.CombinedDecision(number=1,checks=dict.fromkeys(n.m.review.ClauseChecks.model_fields,'yes'),flags=[],reason='All checks passed.')
        result=n.m.CombinedDecisions(decisions=[d]);validate(result);return result
    monkeypatch.setattr(n.m.review,'ask',fake)
    n.review_cells(None,w,{1:cell},SimpleNamespace(english={'1:1':'English','1:2':'English'}),tmp_path,'omission')
    assert cell['status']=='pass'


def test_minimal_mistranslation_spans_and_wrong_occurrences():
    w=dict(clean={'1:1':'他站在祭坛旁。'},clean_content_chars=6)
    p=dict(edits=[dict(verse='1:1',before='站在祭坛旁',after='跪在祭坛旁',occurrence=1)])
    c=n.normalize(w,p,'mistranslation')
    assert c['chars']==1 and c['edits'][0]['before']=='站'
    p['edits'][0]['occurrence']=2
    with pytest.raises(ValueError):n.normalize(w,p,'mistranslation')


def test_empty_verse_and_standalone_marker_are_rejected():
    w=dict(clean={'1:1':'他回家。','1:2':'忽然，他走了。'},clean_content_chars=8)
    for before,verse in [('他回家。','1:1'),('忽然，','1:2')]:
        with pytest.raises(ValueError):n.normalize(w,dict(edits=[dict(verse=verse,before=before,after='',occurrence=1)]),'omission')


def test_rejection_memory_requires_identical_complete_context():
    bad=dict(status='rejected',checks={'fluent':'no'},review={'reason':'“请为我祷告。”后面的“和从前一样”缺少所指。'},
             edits=[dict(verse='1:1',start=0,before='神人说',after='')],verses={'1:1':'请为我祷告。和从前一样。'})
    assert n.remembered_review([{'60':bad}],deepcopy(bad)) is bad
    good=deepcopy(bad);good['verses']={'1:1':'请为我祷告。王的手恢复了，和从前一样。'}
    assert n.remembered_review([{'60':bad}],good) is None
    conflicting=deepcopy(bad);conflicting['status']='pass'
    assert n.remembered_review([{'60':bad},{'50':conflicting}],conflicting)['status']=='rejected'
    assert n.has_quality_failure([{'60':bad}])
    assert not n.has_quality_failure([{'60':dict(status='held_dose')}])


def test_review_reuse_never_promotes_wrong_dose_but_keeps_language_approval():
    w=dict(clean_content_chars=100)
    passed=dict(status='pass',checks={'fluent':'yes'},flags=[],review={'reason':'Fluent.'},affected_chars=50)
    higher=deepcopy(passed)
    n.apply_remembered_review(w,60,higher,passed)
    assert higher['status']=='held_dose' and higher['quality_review_status']=='pass'
    assert higher['checks']==passed['checks']
    lower=deepcopy(higher)
    n.apply_remembered_review(w,50,lower,higher)
    assert lower['status']=='pass'
    no_old=deepcopy(passed)
    n.apply_remembered_review(w,60,no_old,None)
    assert no_old['status']=='held_dose'


def test_joint_timeout_falls_back_without_relaxing_window_constraints(monkeypatch):
    w,pool=fixture();other=deepcopy(w);other['id']='other'
    original=n._plan_joint
    def timeout_multiple(windows,*args,**kwargs):
        if len(windows)>1:raise RuntimeError('Nested optimization did not finish: time limit')
        return original(windows,*args,**kwargs)
    monkeypatch.setattr(n,'_plan_joint',timeout_multiple)
    result=n.plan([w,other],{'w':pool,'other':pool},'omission',strict=True)
    assert 'joint_time_limit_per_window_fit' in result['optimization_fallback_stages']
    assert 'sum_of_window_mixture_deviations' in result['objectives']
    for window in [w,other]:
        cells={str(d):n.materialize(window,pool,result['selected'][(window['id'],d)],'omission',d) for d in n.DOSES}
        assert all(abs(c['actual_percent']-int(d))<=2 for d,c in cells.items())
        n.validate_chain(window,cells,'omission')


def test_explicit_preview_doses_do_not_change_default_four_dose_run():
    w,pool=fixture()
    result=n.plan([w],{'w':pool},'omission',strict=True,doses=(15,30))
    cells={str(d):n.materialize(w,pool,result['selected'][('w',d)],'omission',d) for d in (15,30)}
    assert set(result['selected'])=={('w',15),('w',30)}
    assert all(abs(c['actual_percent']-int(d))<=2 for d,c in cells.items())
    n.validate_chain(w,cells,'omission',doses=(15,30))
    assert n.DOSES==(30,40,50,60)
    with pytest.raises(ValueError,match='Doses'):
        n.plan([w],{'w':pool},'omission',doses=(30,15))


def test_candidate_refill_uses_explicit_preview_targets_without_qa(monkeypatch,tmp_path):
    w,pool=fixture();w['question']='SECRET'
    state=dict(pool=pool,batches=0,proposed_count=0,proposals=[],cells={},baseline={'verses':w['clean']})
    def fake(client,folder,stage,model,prompt,payload,schema,validate):
        assert payload['targets']==[5,10] and prompt=='Preview policy'
        assert 'SECRET' not in str(payload)
        result=n.Proposals(candidates=[],no_candidates_reason='No further candidates.')
        validate(result);return result
    monkeypatch.setattr(n.m.review,'ask',fake)
    n.generate_candidates(None,w,SimpleNamespace(english={'1:1':'English','1:2':'English'}),
        'omission',state,tmp_path,8,doses=(5,10),writer_prompt='Preview policy')
    assert state['batches']==1 and state['proposed_count']==0 and n.DOSES==(30,40,50,60)
