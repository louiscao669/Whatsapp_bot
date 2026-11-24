import json
from evaluation.scripts.campaigns.current import rerun_omission_ladder as campaign


def test_only_approved_cells_enter_readers_and_every_clean_window_is_included():
    bank=json.loads(campaign.bank.DEST.read_text());qas=json.loads(campaign.bank.QA.read_text())
    stimuli,held=campaign.stimuli_from_release(bank,qas)
    assert len(stimuli)==616 and len(held)==34
    assert sum(s['family']=='clean' for s in stimuli)==65
    keys={(s['item'],s['family'],s['dose']) for s in stimuli}
    assert len(keys)==len(stimuli)
    assert not keys&{(h['item'],h['family'],h['dose']) for h in held}
    assert not {s['item'] for s in stimuli}&set(bank['excluded_held'])
    weights={model:'fixture-weight-'+model for model,_ in campaign.old.MODELS}
    jobs=campaign.runner.request_jobs(stimuli,weights)
    assert len(jobs)==4312 and len({j['signature'] for j in jobs})==4312
    assert all(j['body']['options']==dict(temperature=0,num_ctx=8192,num_predict=2500) for j in jobs)
