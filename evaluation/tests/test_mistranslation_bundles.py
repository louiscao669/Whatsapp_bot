from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from evaluation.scripts.variants.banks import mistranslation_bundles as b
from evaluation.scripts.variants.banks import mistranslation_validation as validation
from evaluation.scripts.variants.current import create_mistranslation_variants as variants
from evaluation.scripts.pipeline.refit_window_doses import new_groups, window_input
from evaluation.scripts.pipeline import match_window_defects as matched

TEXT='他母亲来到门口。\n他母亲回家。'


def atom(source='母亲',target='妻子',occurrence=1):
    return dict(source=source,target=target,occurrence=occurrence)


def proposal(*edits):return dict(edits=list(edits),rationale='DO NOT SEND THIS RATIONALE TO REVIEW')


class FakeClient:
    def __init__(self,batches,fail_combined=False,failure_quote=None):
        self.batches=batches;self.calls=[];self.fail_combined=fail_combined;self.failure_quote=failure_quote
        self.responses=SimpleNamespace(create=self.create)
    def create(self,**kw):
        self.calls.append(deepcopy(kw));payload=json.loads(kw['input'])
        if kw['text']['format']['name']=='mistranslation_bundle_proposals':
            rows=self.batches[min(payload['round']-1,len(self.batches)-1)]
            value=dict(candidates=deepcopy(rows[:payload['max_items']]))
        else:
            assert 'RATIONALE' not in kw['input']
            checks=dict.fromkeys(b.FIELDS,'yes')
            if self.fail_combined and len(payload['edits'])>1:checks['fluent']='no'
            value=dict(checks=checks,claims=[dict(edit_numbers=[e['number'] for e in payload['edits']],
                original_claim='Original '+str([e['source'] for e in payload['edits']]),
                changed_claim='Changed '+str([e['target'] for e in payload['edits']]))],
                flags=[],explanation=(f'“{self.failure_quote}”不流畅。' if self.failure_quote and checks['fluent']=='no'
                                      else 'Synthetic test decision.'))
        return SimpleNamespace(status='completed',output=[],output_text=json.dumps(value),id=str(len(self.calls)),
                               model=kw['model'],usage=dict(input_tokens=20,output_tokens=20))


def build(tmp_path,client,**kw):
    return b.build_bank(passage=TEXT,chapter='Test',cache_dir=tmp_path,client=client,workers=1,
                        **{'max_candidates':12,'batch_size':12,'max_batches':1,'target_rate':.1,**kw})


def test_occurrence_specific_approval_and_atomic_bundle_rendering(tmp_path):
    client=FakeClient([[proposal(atom(occurrence=2),atom('回家','出城'))]])
    bank=build(tmp_path,client)
    validation.validate_reviewed_bank(bank,TEXT)
    text,meta=variants.apply_mistranslations(TEXT,rate=.3,seed=1,bank=bank,selected_group_indices=[0])
    assert text=='他母亲来到门口。\n他妻子出城。'
    assert meta['substitution_group_count']==1 and meta['substitution_occurrence_count']==2
    assert meta['changed_content_chars']==4
    assert bank['acquisition']['target_met']
    review_payload=json.loads(client.calls[1]['input'])
    assert [e['start'] for e in review_payload['edits']]==[10,12]
    assert len([c for c in client.calls if c['text']['format']['name']=='mistranslation_bundle_judgment'])==1


def test_competing_candidates_survive_bank_but_cannot_overlap_at_application(tmp_path):
    client=FakeClient([[proposal(atom()),proposal(atom(target='父亲')),proposal(atom('回家','出城'))]])
    bank=build(tmp_path,client)
    assert len(bank['candidates'])==3
    with pytest.raises(validation.MistranslationValidationError,match='overlapping'):
        variants.apply_mistranslations(TEXT,rate=.3,seed=1,bank=bank,selected_group_indices=[0,1])
    text,meta=variants.apply_mistranslations(TEXT,rate=.3,seed=1,bank=bank)
    assert meta['substitution_group_count']==2
    assert ('父亲' in text) != ('妻子' in text)


def test_candidate_limit_counts_duplicates_and_stops_without_unbounded_refill(tmp_path):
    client=FakeClient([[proposal(atom())]*12])
    bank=build(tmp_path,client,max_candidates=60,max_batches=5,target_rate=.9)
    assert bank['acquisition']['proposed_count']==60
    assert bank['acquisition']['rounds_used']==5
    assert bank['acquisition']['stop_reason']=='candidate_limit_reached'
    assert not bank['acquisition']['target_met'] and len(bank['candidates'])==1
    assert len(client.calls)==6  # Five proposal batches and one reusable review.


def test_combined_failure_does_not_count_as_achieved_coverage(tmp_path):
    client=FakeClient([[proposal(atom()),proposal(atom('回家','出城'))]],fail_combined=True)
    bank=build(tmp_path,client,target_rate=.3)
    assert len(bank['candidates'])==2
    assert not bank['acquisition']['target_met']
    assert bank['acquisition']['numeric_available_rate']>bank['acquisition']['reviewed_available_rate']
    assert any(c['review']['status']=='rejected' for c in bank['reviewed_combinations'])


def test_cached_run_replays_without_new_calls_and_source_changes_invalidate_it(tmp_path):
    client=FakeClient([[proposal(atom())]])
    bank=build(tmp_path,client)
    assert build(tmp_path,None,offline=True)==bank
    with pytest.raises(validation.MistranslationValidationError):validation.validate_reviewed_bank(bank,TEXT+'新内容')
    altered=deepcopy(bank);altered['candidates'][0]['edits'][0]['start']+=1
    with pytest.raises(validation.MistranslationValidationError):validation.validate_reviewed_bank(altered,TEXT)


def test_longer_spans_are_not_rejected_by_old_length_caps():
    text='父'*35+'。'
    c=b.normalize(proposal(atom('父'*35,'母'*36)),text)
    assert len(c['edits'][0]['source'])==35
    assert b.render(text,c['edits'])=='母'*36+'。'


def test_unchanged_edges_do_not_inflate_dose_and_polarity_changes_remain_possible():
    text='他站在祭坛旁。他没有死罪。'
    c=b.normalize(proposal(atom('站在祭坛旁','跪在祭坛旁'),atom('没有死罪','有死罪')),text)
    assert c['edits']==[dict(start=1,source='站',target='跪'),dict(start=8,source='没有',target='有')]
    assert b.weight(c['edits'])==3
    assert b.render(text,c['edits'])=='他跪在祭坛旁。他有死罪。'


@pytest.mark.parametrize('value',['no','uncertain'])
def test_every_quality_check_blocks_approval(value):
    for field in b.FIELDS:
        checks=dict.fromkeys(b.FIELDS,'yes');checks[field]=value
        r=dict(checks=checks,claims=[dict(edit_numbers=[1],original_claim='a',changed_claim='b')],flags=[],explanation='Reason')
        assert b.decision(r,1)==('rejected' if value=='no' else 'held')


def test_window_integration_retains_bundle_and_enforces_combined_gate(tmp_path,monkeypatch):
    client=FakeClient([[proposal(atom()),proposal(atom('回家','出城'))]])
    bank=build(tmp_path,client)
    clean={'1:1':'他母亲来到门口。','1:2':'他母亲回家。'}
    w=dict(id='w',reference='Test',conditions={'clean':{'verses':clean}},clean_content_chars=12)
    pool=new_groups(w,'mistranslation',bank,set())
    assert len(pool)==2
    native=lambda family,dose,ids,labels:clean
    failing=FakeClient([],fail_combined=True)
    original=b.verify_window_cell
    monkeypatch.setattr(b,'verify_window_cell',lambda w,c,bank:original(w,c,bank,client=failing))
    result=matched.materialize(w,'mistranslation',33,list(pool),pool,native,bank,2)
    assert result['status']=='held' and result['dose_status']=='within_target'
    assert result['combined_review']['judgment']['checks']['fluent']=='no'


def test_legacy_publisher_cannot_bypass_new_final_window_review(tmp_path):
    bank=build(tmp_path,FakeClient([[proposal(atom())]]))
    with pytest.raises(variants.MistranslationError,match='final combined review'):
        variants.create_variant(source_method_dir=tmp_path,output_dir=tmp_path/'out',rate=.3,seed=1,bank=bank,force=False)
    assert not (tmp_path/'out').exists()


def test_unchanged_failed_interaction_cannot_pass_by_changing_unrelated_choice(tmp_path):
    passage='他的手恢复了。他回家。'
    proposals=[proposal(atom('手','脚')),proposal(atom('恢复了','长出手指了')),proposal(atom('回家','出城'))]
    candidates=[b.normalize(p,passage) for p in proposals]
    identity=dict(model='test',prompt_sha256=b.digest(b.JUDGE_PROMPT))
    edits=b.selected_edits(candidates,[c['id'] for c in candidates[:2]])
    checks=dict.fromkeys(b.FIELDS,'yes');checks['fluent']='no'
    judgment=dict(checks=checks,claims=[dict(edit_numbers=[1,2],original_claim='手恢复',changed_claim='脚长手指')],
                  flags=[],explanation='“脚长出手指了”词语搭配不自然。')
    failed=dict(candidate_ids=[c['id'] for c in candidates[:2]],edits=edits,text=b.render(passage,edits),
        review=dict(status='rejected',judge=identity,judgment=judgment,
                    judgment_id=b.digest(dict(identity=identity,request=b.request(passage,edits)))))
    cuts=b.failure_cuts(passage,[failed],candidates)
    assert len(cuts)==1 and set(cuts[0]['candidate_ids'])==set(failed['candidate_ids'])
    ids=b.select(candidates,b.content_len(passage),forbidden=[cuts[0]['candidate_ids']])
    assert candidates[2]['id'] in ids
    assert not set(failed['candidate_ids'])<=set(ids)
    forged=deepcopy(failed);forged['review']['judgment_id']='stale'
    assert not b.failure_cuts(passage,[forged],candidates)


def test_final_window_gate_honors_verified_failure_memory_without_new_model_call(tmp_path):
    client=FakeClient([[proposal(atom()),proposal(atom('回家','出城'))]],fail_combined=True,
                      failure_quote='他妻子来到门口')
    bank=build(tmp_path,client)
    assert bank['failure_cuts']
    validation.validate_reviewed_bank(bank,TEXT)
    clean={'1:1':'他母亲来到门口。','1:2':'他母亲回家。'}
    w=dict(conditions={'clean':{'verses':clean}})
    pool=new_groups(w,'mistranslation',bank,set())
    edits=[e for group in pool.values() for e in group]
    cell=dict(status='within_target',edits=[matched.asdict(e) for e in edits],verses=matched.render(clean,edits))
    result=b.verify_window_cell(w,cell,bank,offline=True)
    assert result['status']=='held'
    assert result['combined_review']['type']=='unchanged_fluency_failure'
