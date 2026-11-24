from types import SimpleNamespace

import pytest

from evaluation.scripts.pipeline import generate_omission_phrases as g
from evaluation.scripts.pipeline.build_nested_window_defects import Proposals


def test_incomplete_json_retries_and_only_valid_output_is_cached(tmp_path):
    calls=[]
    result=Proposals(candidates=[],no_candidates_reason='No additional candidates')
    def parse(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:raise ValueError('Invalid JSON: EOF')
        return SimpleNamespace(output_parsed=result,id='review-2',model='test-model',usage=None,status='completed')
    client=SimpleNamespace(responses=SimpleNamespace(parse=parse))
    args=(client,tmp_path,'trial','test-model','review',{'source':'data'},Proposals,lambda x:None)
    assert g.ask(*args)==result
    assert len(calls)==2 and len(list(tmp_path.glob('trial-*.json')))==1
    assert [c['max_output_tokens'] for c in calls]==[6500,12000]
    assert g.ask(*args)==result and len(calls)==2


def test_repeated_parse_failure_stops_without_approval_or_cache(tmp_path):
    calls=[]
    def parse(**kwargs):
        calls.append(kwargs);raise ValueError('Invalid JSON: EOF')
    client=SimpleNamespace(responses=SimpleNamespace(parse=parse))
    with pytest.raises(ValueError,match='Invalid JSON'):
        g.ask(client,tmp_path,'trial','test-model','review',{},Proposals,lambda x:None)
    assert len(calls)==2 and not list(tmp_path.glob('*.json'))


def test_background_request_resumes_completed_response_without_resubmission(tmp_path,monkeypatch):
    from openai.types.responses import Response
    monkeypatch.setenv('ETEN_REVIEW_BACKGROUND','1')
    monkeypatch.setattr(g.time,'sleep',lambda seconds:None)
    result=Proposals(candidates=[],no_candidates_reason='Nothing additional')
    fields=dict(id='resp-test',created_at=0,model='test-model',object='response',output=[],
                parallel_tool_calls=False,tool_choice='auto',tools=[],
                text=dict(format=dict(type='json_schema',name='proposals',schema=Proposals.model_json_schema(),strict=True)))
    queued=Response.model_validate(dict(fields,status='queued'))
    completed=Response.model_validate(dict(fields,status='completed',output=[dict(
        id='message',type='message',status='completed',role='assistant',
        content=[dict(type='output_text',text=result.model_dump_json(),annotations=[])])]))
    calls=[]
    def parse(**kwargs):calls.append('create');return queued
    def retrieve(response_id):
        assert response_id=='resp-test';calls.append('retrieve');return completed
    client=SimpleNamespace(responses=SimpleNamespace(parse=parse,retrieve=retrieve))
    client.with_options=lambda **kwargs:client
    args=(client,tmp_path,'trial','test-model','review',{},Proposals,lambda x:None)
    assert g.ask(*args)==result
    next(tmp_path.glob('trial-*.json')).unlink()  # Simulated interruption before validated cache save.
    request_path=next(tmp_path.glob('request-*.json'))
    saved=g.read(request_path)
    format_config=saved['response']['text']['format']
    format_config['schema_']=format_config.pop('schema')  # Legacy SDK dump.
    g.save(request_path,saved)
    assert g.ask(*args)==result
    assert calls==['create','retrieve']
