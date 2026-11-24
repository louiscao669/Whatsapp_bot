from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

from evaluation.scripts.pipeline import extend_omission_preview as x


def test_five_targets_include_new_15_without_changing_fixed_30(monkeypatch,tmp_path):
    clean={'1:1':'甲'*50,'1:2':'乙'*50}
    w=dict(id='w',reference='Example 1:1–2',clean=clean,clean_content_chars=100)
    pool=[x.n.make_candidate([dict(verse=v,start=i,before=t[i:i+5],after='')],['clause'])
          for v,t in clean.items() for i in range(0,40,5)]
    fit=x.n.plan([w],{'w':pool},'omission',doses=(30,),strict=True)
    cell=x.n.materialize(w,pool,fit['selected'][('w',30)],'omission',30)
    cell.update(status='pass',checks=dict.fromkeys(x.m.review.ClauseChecks.model_fields,'yes'),flags=[],review={'reason':'Approved'})
    fixed={'cells':{'30':deepcopy(cell)}}
    original={'pool':pool,'history':[]}
    sizes=[]
    def approve(client,w,cells,source,folder,family):
        sizes.append(len(cells))
        for c in cells.values():
            c.update(status='pass',checks=dict.fromkeys(x.m.review.ClauseChecks.model_fields,'yes'),flags=[],review={'reason':'Approved'})
    monkeypatch.setattr(x.m,'OpenAI',lambda **kw:nullcontext(None))
    monkeypatch.setattr(x.n,'review_cells',approve)
    state=x.build_one(w,fixed,original,SimpleNamespace(english={}),tmp_path,
        target_doses=(5,10,15,20,25),writer_prompt='Explicit five-dose preview')
    assert state['cells']['30']==cell
    assert set(state['cells'])=={'5','10','15','20','25','30'}
    assert all(c['status']=='pass' for c in state['cells'].values())
    assert max(sizes)<=4 and state['batches']==0
    assert state['configuration']['targets']==[5,10,15,20,25]


def test_mistranslation_subset_requires_identical_replacements_and_prerequisites():
    a=x.n.make_candidate([dict(verse='1:1',start=0,before='男子',after='女子')])
    different=x.n.make_candidate([dict(verse='1:1',start=0,before='男子',after='老人')])
    companion=x.n.make_candidate([dict(verse='1:1',start=3,before='他',after='她')])
    a['requires']=[companion['id']]
    assert x.pool_within([a,different,companion],{'edits':a['edits']},'mistranslation')==[]
    upper={'edits':a['edits']+companion['edits']}
    assert x.pool_within([a,different,companion],upper,'mistranslation')==[a,companion]


def test_mistranslation_preview_uses_six_checks_and_preserves_forbidden_sets(monkeypatch,tmp_path):
    clean={'1:1':'甲'*50,'1:2':'乙'*50}
    w=dict(id='w',reference='Example 1:1–2',clean=clean,clean_content_chars=100)
    pool=[x.n.make_candidate([dict(verse=v,start=i,before=t[i:i+5],after='丙'*5)])
          for v,t in clean.items() for i in range(0,40,5)]
    forbidden=[pool[0]['id'],pool[1]['id']]
    fit=x.n.plan([w],{'w':pool},'mistranslation',doses=(30,),strict=True,forbidden=[('w',forbidden)])
    cell=x.n.materialize(w,pool,fit['selected'][('w',30)],'mistranslation',30)
    cell.update(status='pass',checks=dict.fromkeys(x.n.mr.Checks.model_fields,'yes'),flags=[],review={'reason':'Approved'})
    original=dict(pool=pool,history=[],baseline={'forbidden_candidate_sets':[forbidden]})
    def approve(client,w,cells,source,folder,family):
        assert family=='mistranslation'
        for c in cells.values():
            assert not set(forbidden)<=set(c['selected_ids'])
            c.update(status='pass',checks=dict.fromkeys(x.n.mr.Checks.model_fields,'yes'),flags=[],review={'reason':'Approved'})
    monkeypatch.setattr(x.m,'OpenAI',lambda **kw:nullcontext(None))
    monkeypatch.setattr(x.n,'review_cells',approve)
    result=x.build_one(w,{'cells':{'30':deepcopy(cell)}},original,SimpleNamespace(english={}),tmp_path,
        target_doses=(5,10,15,20,25),writer_prompt='Mistranslation preview',family='mistranslation')
    assert result['cells']['30']==cell
    assert all(c['checks']['gender_agreement']=='yes' for c in result['cells'].values())
