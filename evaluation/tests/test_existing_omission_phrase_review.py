from copy import deepcopy

import pytest

from evaluation.scripts.pipeline import review_existing_omission_phrases as phrase
from evaluation.scripts.pipeline.build_omission_phrase_bank import Passage, clean_digest, make_report


def fixture():
    clean = {'1:1':'他奉命从犹大来到伯特利，当众宣告。'}
    english = {'1:1':'He came from Judah to Bethel by command and proclaimed it publicly.'}
    source = Passage('Test', english, clean, 'source-hash')
    manifest = dict(release='test-release', windows=[dict(id='w1', passage_id='p1', verses=list(clean),
        clean_content_chars=sum(map(phrase.shared.mis.content_len, clean.values())),
        question='SECRET_QA', conditions={'clean':{'verses':clean}, 'omission15':{'edits':[]}, 'omission30':{'edits':[]}})])
    prior = dict(release='test-release', unit='phrase', mode='automatic', writer='writer', windows=[dict(
        window_id='w1', passage_id='p1', verses=list(clean), clean_zh_sha256=clean_digest(clean), english_sha256='source-hash',
        no_proposals_reason='', candidates=[dict(number=i, proposal=dict(verse='1:1', chinese=s,
            chinese_occurrence=1, english='BAD_ALIGNMENT', english_occurrence=1), status='rejected',
            issues=['unverified_alignment'], flags=[], review_note='SECRET_PRIOR_REVIEW')
            for i,s in enumerate(('从犹大','奉命','伯特利','当众'),1)])])
    return manifest, prior, {'p1':source}


def decision(number, **checks):
    values=dict.fromkeys(phrase.shared.ClauseChecks.model_fields,'yes'); values.update(checks)
    return phrase.shared.ClauseDecision(number=number, checks=phrase.shared.ClauseChecks(**values), flags=[],
        reason='Concrete review evidence.', information_loss=dict(kind='content_detail',
            source_information='The source states a fact.', edited_information='The fact is absent.', lost_content='The fact.'),
        key_content_category='place', key_content_reason='A specific location is omitted.',
        unit_kind='phrase', unit_reason='A prepositional relation.', source_alignment='localized',
        alignment_reason='Supported in the full window.',
        english_evidence=[phrase.shared.Evidence(verse='1:1',quote='He came from Judah to Bethel')])


def test_existing_chinese_candidates_survive_unmatched_english_and_are_not_mutated():
    manifest, prior, sources=fixture(); before=deepcopy(prior)
    bank, prepared=phrase.prepare_existing(prior,manifest,sources)
    assert prior==before
    assert len(prepared['w1']['candidates'])==4
    assert [c['edit']['before'] for c in prepared['w1']['candidates']]==['从犹大','奉命','伯特利','当众']
    assert len(bank['windows'])==1 and bank['windows'][0]['candidates']==[]


def test_fixed_candidates_use_five_checks_without_proposals_or_prior_verdicts(monkeypatch,tmp_path):
    manifest,prior,sources=fixture()
    bank,prepared=phrase.prepare_existing(prior,manifest,sources)
    clean=manifest['windows'][0]['conditions']['clean']['verses']
    calls=[]
    def stub(client,folder,stage,model,prompt,payload,schema,validate):
        calls.append(stage)
        assert stage=='review'
        assert [c['number'] for c in payload['candidates']]==[1,2,3,4]
        assert all(s not in str(payload) for s in ('SECRET_QA','SECRET_PRIOR_REVIEW','BAD_ALIGNMENT','selected_conditions'))
        ds=[decision(1),decision(2),decision(3,valid_in_context='uncertain'),decision(4,key_content_removed='no')]
        ds[1].flags=['other_meaning_changed']; ds[1].unit_kind='word'
        result=phrase.shared.ClauseDecisions(decisions=ds); validate(result); return result
    monkeypatch.setattr(phrase.shared,'ask',stub)
    result=phrase.process_existing_window(None,tmp_path,bank['windows'][0],clean,sources['p1'],prepared['w1'],{},'reviewer')
    assert calls==['review']
    assert [c['review_outcome'] for c in result['candidates']]==['pass','pass_with_flags','held','rejected']
    assert [c['previous_number'] for c in result['candidates']]==[1,2,3,4]
    assert result['candidates'][1]['flags']==['other_meaning_changed','unit_word']
    assert all(c['previous_proposal']['english']=='BAD_ALIGNMENT' for c in result['candidates'])
    assert all('valid_omission_unit' not in c['checks'] for c in result['candidates'])
    bank.update(windows=[result], unit='phrase', mode='automatic', review_version=8, report_outcomes='four',
        candidate_scope='existing_phrase_bank', required_checks=list(phrase.shared.ClauseChecks.model_fields),
        previous_audit='v4', information_loss_policy='content_review_unit_metadata')
    html=make_report(bank,manifest,sources)
    assert 'Pass (1)' in html and 'Pass with flags (1)' in html and 'Held for review (1)' in html and 'Rejected (1)' in html
    assert 'existing phrase-bank candidates' in html and 'These are omission-splitter candidates' not in html
    assert 'Previous review' in html


def test_empty_window_does_not_generate_replacement_candidates(monkeypatch,tmp_path):
    manifest,prior,sources=fixture(); prior['windows'][0]['candidates']=[]
    bank,prepared=phrase.prepare_existing(prior,manifest,sources)
    def forbidden(*args,**kwargs): raise AssertionError('No API call for an empty prior window')
    monkeypatch.setattr(phrase.shared,'ask',forbidden)
    result=phrase.process_existing_window(None,tmp_path,bank['windows'][0],sources['p1'].chinese,
        sources['p1'],prepared['w1'],{},'reviewer')
    assert result['candidates']==[]


@pytest.mark.parametrize('change', ['hash','span','duplicate','outside'])
def test_stale_or_invalid_chinese_input_is_not_silently_repaired(change):
    manifest,prior,sources=fixture(); w=prior['windows'][0]
    if change=='hash': w['clean_zh_sha256']='stale'
    elif change=='span': w['candidates'][0]['proposal']['chinese']='不存在的文字'
    elif change=='duplicate': w['candidates'][1]['proposal']=deepcopy(w['candidates'][0]['proposal'])
    else: w['candidates'][0]['proposal']['verse']='2:1'
    with pytest.raises(ValueError): phrase.prepare_existing(prior,manifest,sources)


def test_initial_api_failure_does_not_dispatch_entire_bank(monkeypatch):
    calls=[]
    def blocked(value):
        calls.append(value)
        raise RuntimeError('project_spend_limit_exceeded')
    monkeypatch.setattr(phrase,'process_existing_window',blocked)
    with pytest.raises(RuntimeError,match='spend_limit'):
        list(phrase.review_jobs([(i,(i,)) for i in range(66)],8))
    assert calls==[0]


def test_passage_trial_never_sends_other_passages_or_overwrites_full_bank(monkeypatch,tmp_path):
    manifest,prior,sources=fixture()
    second=deepcopy(manifest['windows'][0]); second.update(id='w2',passage_id='p2')
    manifest['windows'].append(second)
    second=deepcopy(prior['windows'][0]); second.update(window_id='w2',passage_id='p2')
    prior['windows'].append(second); sources['p2']=sources['p1']
    manifest_path=tmp_path/'manifest.json'; prior_path=tmp_path/'prior.json'
    bank_path=tmp_path/'full.json'; report_path=tmp_path/'full.html'
    phrase.shared.save(manifest_path,manifest); phrase.shared.save(prior_path,prior)
    bank_path.write_text('FULL_BANK_UNCHANGED'); report_path.write_text('FULL_REPORT_UNCHANGED')
    monkeypatch.setattr(phrase,'BANK',bank_path); monkeypatch.setattr(phrase,'REPORT',report_path)
    monkeypatch.setattr(phrase,'english_by_passage',lambda:sources)
    monkeypatch.setattr(phrase,'load_dotenv',lambda *a,**k:None)
    class LocalClient:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setattr(phrase,'OpenAI',LocalClient)
    calls=[]
    original=phrase.process_existing_window
    def scoped(*args):
        calls.append(args[2]['passage_id'])
        assert args[2]['passage_id']=='p1'
        return original(*args)
    monkeypatch.setattr(phrase,'process_existing_window',scoped)
    def stub(client,folder,stage,model,prompt,payload,schema,validate):
        result=phrase.shared.ClauseDecisions(decisions=[decision(c['number']) for c in payload['candidates']])
        validate(result); return result
    monkeypatch.setattr(phrase.shared,'ask',stub)
    result=phrase.run(manifest_path,prior_path,bank_path,report_path,tmp_path/'run',passage_id='p1')
    assert calls==['p1']
    assert result['review_scope']==dict(kind='passage',passage_id='p1',window_count=1,candidate_count=4)
    assert [w['window_id'] for w in result['windows']]==['w1']
    assert bank_path.read_text()=='FULL_BANK_UNCHANGED'
    assert report_path.read_text()=='FULL_REPORT_UNCHANGED'
    assert (tmp_path/'full_p1.json').exists() and (tmp_path/'full_p1.html').exists()
    with pytest.raises(ValueError,match='No existing phrase windows'):
        phrase.run(manifest_path,prior_path,bank_path,report_path,tmp_path/'run',passage_id='missing')
    assert calls==['p1']
