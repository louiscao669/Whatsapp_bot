from copy import deepcopy
import pytest

from evaluation.scripts.campaigns.current import run_grammar_ladder_readers as r


@pytest.mark.parametrize('passage,n',[('t1_1kgs13',8),('t1_2kgs11',6),('t1_2kgs6_7',9)])
def test_current_kings_grid_uses_only_active_approved_windows(passage,n):
    stimuli=r.stimuli_from_bank(r.old.read(r.BANK),r.old.read(r.runner.QA),passage)
    assert len(stimuli)==n*7
    assert {s['dose'] for s in stimuli}=={0,5,10,15,20,25,30}
    assert all(s['item']!='2kgs_7_1-20/v17-18:1' for s in stimuli)
    jobs=r.runner.request_jobs(stimuli,{m:'test-'+m for m,_ in r.old.MODELS})
    assert len(jobs)==n*49
    assert all('correct' not in j['public'] for j in jobs)
    assert all(j['body']==r.old.request_for(
        s['qa'],s['passage'],j['model'],j['thinking'],'mcq',j['reader_index']>=4)[0]
        for j in jobs for s in stimuli if (s['item'],s['family'],s['dose'])==(j['item'],j['family'],j['dose']))


@pytest.mark.parametrize('change,error',[
    ('held','Held grammar'),('draft','Draft differs'),('dose','Incorrect grammar dose')])
def test_rejected_or_tampered_inputs_cannot_enter_run(change,error):
    bank=deepcopy(r.old.read(r.BANK))
    w=next(w for w in bank['windows'] if w['id'].startswith('1kgs_13_1-34/v1-3'))
    v=w['variants'][0]
    if change=='held':v['status']='flagged'
    elif change=='draft':v['draft'][next(iter(v['draft']))]+='多余内容'
    else:v['selection']['actual_percent']+=1
    with pytest.raises(ValueError,match=error):
        r.stimuli_from_bank(bank,r.old.read(r.runner.QA),'t1_1kgs13')


def test_stale_qa_window_is_rejected():
    qas=deepcopy(r.old.read(r.runner.QA))
    q=next(q for q in qas if q['id']=='1kgs_13_1-34/v1-3:1')
    q['verses'][next(iter(q['verses']))]+='多余内容'
    with pytest.raises(ValueError,match='QA or clean window'):
        r.stimuli_from_bank(r.old.read(r.BANK),qas,'t1_1kgs13')


def test_summaries_keep_e_and_invalid_in_accuracy_denominator():
    rows=[]
    for i in range(7):
        for dose in (0,*r.DOSES):
            for item,outcome in zip('abcd',('correct','incorrect','abstain','invalid')):
                rows.append(dict(reader_index=i,family='clean' if not dose else 'grammar',dose=dose,
                    item=item,outcome=outcome,actual_percent=dose,
                    effort=dict(output_tokens=1,done_reason='stop')))
    summaries=r.summarize(rows,dict(question_ids=list('abcd')))
    assert len(summaries)==49
    assert all(s['n']==4 and s['accuracy']==.25 and s['abstention_rate']==.25 for s in summaries)
    with pytest.raises(ValueError,match='Missing or duplicate'):
        r.summarize(rows[:-1],dict(question_ids=list('abcd')))
