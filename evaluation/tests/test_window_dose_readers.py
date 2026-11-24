from copy import deepcopy

import pytest

from evaluation.scripts.campaigns.current import run_window_dose_readers as r


def test_current_one_passage_grid_is_complete_and_reviewed():
    stimuli=r.inputs('t1_1kgs13')
    assert len(stimuli)==152
    assert len({s['item'] for s in stimuli})==8
    assert all(s['review_status'] in ('clean','pass','pass_with_flags') for s in stimuli)
    assert all(abs(s['actual_percent']-s['dose'])<=2.000001 for s in stimuli)
    weights={m:'test-weight-'+m for m,t in r.old.MODELS}
    jobs=r.request_jobs(stimuli,weights)
    assert len(jobs)==1064
    assert len({j['signature'] for j in jobs})==1064
    for job in jobs:
        assert set(job['body'])<= {'model','messages','stream','options','think'}
        assert 'correct' not in job['public']
        if job['thinking'] is False:
            assert job['body']['think'] is False
            assert '/no_think' in job['body']['messages'][1]['content']
        elif job['thinking'] is True:
            assert job['body']['think'] is True
            assert '/no_think' not in job['body']['messages'][1]['content']


def test_held_variants_cannot_enter_reader_run(monkeypatch):
    original=r.old.read
    low=deepcopy(original(r.LOW))
    target=next(w for w in low['families']['omission']['windows'] if w['qa']['passage_id']=='t1_1kgs13')
    target['cells']['5']['status']='held'
    monkeypatch.setattr(r.old,'read',lambda path:low if path==r.LOW else original(path))
    with pytest.raises(ValueError,match='passed'):r.inputs('t1_1kgs13')


def test_empty_output_is_invalid_and_e_is_abstention_choice():
    for index in (0,4):
        job=dict(reader_index=index,public={'choices':dict(zip('ABCDE',['甲','乙','丙','丁','无法判断']))})
        assert r.parse_answer(job,'') is None
        assert r.parse_answer(job,'E')=='E'


@pytest.mark.parametrize('pid,n,title',[('t1_2chr26',6,'2 Chronicles 26'),('t1_2kgs6_7',10,'2 Kings 6–7')])
def test_additional_passage_grids_and_report_labels(pid,n,title):
    stimuli=r.inputs(pid)
    assert len(stimuli)==19*n
    assert r.passage_label(stimuli)==title
    weights={m:'test-weight-'+m for m,t in r.old.MODELS}
    assert len(r.request_jobs(stimuli,weights))==133*n


def test_skip_held_preserves_approved_cells_and_documents_the_two_missing_versions():
    with pytest.raises(ValueError,match='passed'):r.inputs('t1_acts23')
    excluded=[]
    stimuli=r.inputs('t1_acts23',skip_held=True,excluded=excluded)
    assert len(stimuli)==6*19-2
    assert {(e['item'],e['family'],e['dose']) for e in excluded}=={
        ('acts_23_12-35/v25-26:1','omission',5),
        ('acts_23_12-35/v25-26:1','omission',40)}
    assert all(e['status']=='held_dose' and e['reason'] for e in excluded)
    for family in r.FAMILIES:
        for dose in r.DOSES:
            n=sum(s['family']==family and s['dose']==dose for s in stimuli)
            assert n==(5 if family=='omission' and dose in (5,40) else 6)
    weights={m:'test-weight-'+m for m,t in r.old.MODELS}
    assert len(r.request_jobs(stimuli,weights))==784


def test_skip_held_does_not_bypass_validation_of_approved_cells(monkeypatch):
    original=r.old.read
    low=deepcopy(original(r.LOW))
    target=next(w for w in low['families']['omission']['windows'] if w['qa']['passage_id']=='t1_1kgs13')
    target['cells']['5']['actual_percent']=99
    monkeypatch.setattr(r.old,'read',lambda path:low if path==r.LOW else original(path))
    with pytest.raises(ValueError):r.inputs('t1_1kgs13',skip_held=True)


def test_held_cells_are_missing_not_errors_and_report_has_correct_denominators(tmp_path,monkeypatch):
    excluded=[];stimuli=r.inputs('t1_acts23',skip_held=True,excluded=excluded)
    jobs=r.request_jobs(stimuli,{m:'test-weight-'+m for m,t in r.old.MODELS})
    design=dict(question_ids=[s['item'] for s in stimuli if s['family']=='clean'],
                stimuli_sha256=r.old.digest(stimuli),expected=len(jobs),excluded_stimuli=excluded)
    folder=tmp_path/'run';report=tmp_path/'report'
    lookup={(s['family'],s['dose'],s['item']):s for s in stimuli}
    memory={folder/'stimuli.json':stimuli}
    for j in jobs:
        key=lookup[j['family'],j['dose'],j['item']]['qa']['correct']
        memory[folder/'answers'/(j['signature']+'.json')]=dict(
            request=j['body'],model_digest=j['model_digest'],answer=key,
            direct_choice=key,thinking_text='',started_at=0,completed_at=1,
            effort=dict(thinking_chars=0,done_reason='stop',output_tokens=1))
    original=r.old.read
    monkeypatch.setattr(r.old,'read',lambda p:memory[p] if p in memory else original(p))
    monkeypatch.setattr(r,'verify_inputs',lambda design:None)
    rows,summaries=r.render_report(folder,report,design,jobs)
    assert len(rows)==784 and all(x['outcome']=='correct' for x in rows)
    assert {x['n'] for x in summaries}=={5,6}
    assert all(x['accuracy']==1 and x['incorrect']==x['abstain']==x['invalid']==0 for x in summaries)
    html=(report/'index.html').read_text()
    assert 'n=5' in html and 'n=6' in html and 'Held versions excluded' in html
    assert original(report/'excluded_stimuli.json')==excluded
    assert original(folder/'verification.json')['per_cell_n']==[5,6]
