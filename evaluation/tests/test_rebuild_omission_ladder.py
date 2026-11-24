from copy import deepcopy
from types import SimpleNamespace

from evaluation.scripts.pipeline import rebuild_omission_ladder as ladder


def fixture():
    n=ladder.n
    w=dict(id='w',reference='Fixture 1:1',clean={'1:1':'甲'*105},clean_content_chars=105)
    kinds=['word']*4+['phrase']*10+['clause']*6
    pool=[n.make_candidate([dict(verse='1:1',start=i*5,before='甲'*5,after='')],[kind]) for i,kind in enumerate(kinds)]
    def cell(dose,indices):
        c=n.materialize(w,pool,[pool[i]['id'] for i in indices],'omission',dose)
        c.update(status='pass',checks=dict.fromkeys(ladder.m.review.ClauseChecks.model_fields,'yes'),flags=[],review=dict(reason='Approved'))
        return c
    fixed={'w':{'15':cell(15,[0,4,14]),'30':cell(30,[0,1,4,5,14,15])}}
    result=dict(windows=[w],pools={'w':pool},fixed=fixed,rounds=[],configuration=dict(seed=3,target_weights=dict(word=2,phrase=5,clause=3)))
    return result


def test_all_nine_doses_preserve_published_versions_and_high_nesting():
    result=fixture();original=deepcopy(result['fixed'])
    record=ladder.select_round(result,{'w':[]},0)
    result['rounds'].append(record)
    assert set(record['cells']['w'])==set(map(str,ladder.DOSES))
    assert result['fixed']==original
    assert all(record['cells']['w'][str(d)]==original['w'][str(d)] for d in ladder.FROZEN)
    ladder.verify(result)
    for a,b in zip(ladder.NESTED,ladder.NESTED[1:]):
        assert set(record['cells']['w'][str(a)]['selected_ids'])<=set(record['cells']['w'][str(b)]['selected_ids'])


def test_review_batches_are_bounded_and_frozen_versions_are_not_sent(monkeypatch,tmp_path):
    original={str(d):dict(status='pass' if d in ladder.FROZEN else 'pending_combined_review') for d in ladder.DOSES}
    calls=[]
    def fake(client,w,cells,source,folder):
        calls.append(set(cells))
        for c in cells.values():c['status']='pass'
        return cells
    monkeypatch.setattr(ladder.r,'review_window',fake)
    result=ladder.review_one(None,{},original,None,tmp_path)
    assert [len(x) for x in calls]==[4,3]
    assert not set.union(*calls)&set(map(str,ladder.FROZEN))
    assert all(c['status']=='pass' for c in result.values())
    assert original['5']['status']=='pending_combined_review'


def test_held_out_of_band_quality_failure_is_remembered():
    assert ladder.quality_failed(dict(status='held_dose',review={'reason':'Bad grammar'},checks={'fluent':'no'}))
    assert not ladder.quality_failed(dict(status='held_dose',reason='No fitting dose'))


def test_scope_matches_the_published_active_release():
    cfg,windows,sources,pools,fixed,history,baseline,generation=ladder.load_inputs(SimpleNamespace(seed=20261121))
    assert len(windows)==65 and len(fixed)==65
    assert cfg['nested_doses']==[30,40,50,60]
    assert sum(len(x) for x in fixed.values())==130
    assert not set(fixed)&set(cfg['excluded_held'])
    assert all(set(cs)==set(map(str,ladder.DOSES)) for cs in baseline.values())


def retention_fixture():
    result=fixture();w=result['windows'][0];w.update(clean={'1:1':'甲'*100},clean_content_chars=100)
    pool=result['pools']['w'];base=[0,1,4,5,14,15]
    def cell(dose,indices,status='pass'):
        c=ladder.n.materialize(w,pool,[pool[i]['id'] for i in indices],'omission',dose)
        c.update(status=status,checks=dict.fromkeys(ladder.m.review.ClauseChecks.model_fields,'yes'),
                 flags=[],review=dict(reason='Reviewed exact context'))
        if status=='rejected':c['checks']['fluent']='no'
        return c
    result['fixed']={'w':{'30':cell(30,base)}}
    for number,extra,status in [(1,[2,3,6,7,8,9],'pass'),(2,[10,11,12,13,16,17],'rejected')]:
        cs={'30':deepcopy(result['fixed']['w']['30'])}
        for d,size in [(40,2),(50,4),(60,6)]:cs[str(d)]=cell(d,base+extra[:size],status)
        result['rounds'].append(dict(round=number,cells={'w':cs},review_complete=True))
    return result


def test_final_retention_recovers_approved_nested_chain_without_editing_text():
    result=retention_fixture();old=deepcopy(result['rounds'][0]['cells']['w'])
    failed=deepcopy(result['rounds'][1]['cells']['w'])
    ladder.retain_reviewed_chains(result,{'w':[]})
    assert result['rounds'][-1]['cells']['w']==old
    assert result['reviewed_chain_retention']['w']['before']=={d:failed[d] for d in ['40','50','60']}
    ladder.n.validate_chain(result['windows'][0],old,'omission',doses=ladder.NESTED)
    snapshot=deepcopy(result)
    ladder.retain_reviewed_chains(result,{'w':[]})
    assert result==snapshot


def test_final_retention_does_not_resurrect_an_exact_context_failed_review():
    result=retention_fixture();conflict=deepcopy(result['rounds'][0]['cells']['w']['40'])
    conflict['status']='rejected';conflict['checks']['fluent']='no'
    ladder.retain_reviewed_chains(result,{'w':[{'40':conflict}]})
    assert result['rounds'][-1]['cells']['w']['40']['status']=='rejected'
    assert result['reviewed_chain_retention']=={}
