import pytest

from evaluation.scripts.pipeline import review_omission_clauses as clause
from evaluation.scripts.pipeline.build_omission_phrase_bank import Passage, make_report


def review(number, **checks):
    values = dict.fromkeys(clause.ClauseChecks.model_fields, 'yes')
    values.update(checks)
    return clause.ClauseDecision(number=number, checks=clause.ClauseChecks(**values), flags=[],
        reason='Review of the exact deletion.',
        information_loss=dict(kind='content_detail', source_information='The source states a fact.',
                              edited_information='That statement is absent.', lost_content='The selected fact.'),
        key_content_category='event_or_outcome', key_content_reason='A concrete event disappears.',
        unit_kind='clause', unit_reason='Complete predication.', source_alignment='localized',
        alignment_reason='The full bilingual context supports the reading.', english_evidence=[])


def test_splitter_keeps_exact_offsets_without_removing_printed_verse_numbers():
    clean = {'13:1':'忽然，他来了。', '13:2':'他说，他说。'}
    rows = clause.candidate_spans(clean)
    assert rows[0] == dict(verse='13:1', start=0, before='忽然，', after='')
    assert rows[1] == dict(verse='13:1', start=3, before='他来了。', after='')
    for e in rows:
        assert clean[e['verse']][e['start']:e['start']+len(e['before'])] == e['before']
    assert sum(clause.mis.content_len(e['before']) for e in rows) == sum(map(clause.mis.content_len, clean.values()))


@pytest.mark.parametrize('body,before,expected', [
    ('他必将祭司献为祭，也必在你上面焚烧人的骨头。’”', '也必在你上面焚烧人的骨头。', '他必将祭司献为祭。’”'),
    ('他说：“他来了，然后走了。”', '“他来了，', '他说：“然后走了。”'),
    ('他说：“出发吧。”于是他们出发，走到了山上。', '”于是他们出发，', '他说：“出发吧。”走到了山上。'),
    ('他去了。他回来了。', '他回来了。', '他去了。'),
])
def test_boundary_repairs_are_pure_deletion_with_identical_content(body,before,expected):
    e = dict(verse='1:1', start=body.index(before), before=before, after='')
    fixed = clause.repair_boundary(e,body)
    assert body[:fixed['start']]+body[fixed['start']+len(fixed['before']):] == expected
    assert clause.CONTENT_CHAR_PATTERN.findall(fixed['before']) == clause.CONTENT_CHAR_PATTERN.findall(before)
    assert fixed['after'] == ''


def test_invalid_span_is_a_mechanical_error_not_silently_repaired():
    with pytest.raises(ValueError,match='exact deletion'):
        clause.repair_boundary(dict(verse='1:1',start=0,before='别人',after=''),'他来了。')


def test_full_window_review_size_alignment_and_uncertainty(monkeypatch,tmp_path):
    clean = {'1:1':'他们收集了书卷，当众焚烧书卷，然后回家了。', '1:2':'他说，他很高兴，他们就出发了。'}
    source = Passage('Test', {'1:1':'They collected books, burned the books publicly, and went home.',
                              '1:2':'He said, he was glad, and they left.'}, clean, 'test')
    all_decisions = [review(1),review(2),review(3,fluent='no'),review(4,key_content_removed='no'),
                     review(5),review(6,key_content_removed='uncertain')]
    all_decisions[0].unit_kind='phrase'
    all_decisions[0].english_evidence=[clause.Evidence(verse='1:1',quote='They collected books')]
    all_decisions[1].flags=['other_meaning_changed']
    all_decisions[1].source_alignment='distributed'
    all_decisions[1].english_evidence=[clause.Evidence(verse='1:1',quote='burned'),clause.Evidence(verse='1:1',quote='books publicly')]
    all_decisions[4].unit_kind='uncertain'
    all_decisions[4].source_alignment='uncertain'
    all_decisions[4].information_loss.kind='unaligned'
    requests=[]
    def stub(client,folder,stage,model,prompt,payload,schema,validate):
        requests.append(stage)
        assert stage in ('review','review-original-boundary') and 'SECRET_QA' not in str(payload)
        assert 'selected_conditions' not in str(payload) and 'previous_status' not in str(payload)
        assert set(payload['window']['1:1'])=={'english','chinese'}
        numbers=[c['number'] for c in payload['candidates']]
        if 3 in numbers and stage=='review':
            assert next(c for c in payload['candidates'] if c['number']==3)['edited_chinese_verse']=='他们收集了书卷，当众焚烧书卷。'
        result=clause.ClauseDecisions(decisions=[all_decisions[n-1] for n in numbers])
        validate(result); return result
    monkeypatch.setattr(clause,'ask',stub)
    original=clause.candidate_spans(clean)
    selected={clause.edit_key(original[1]):['omission30']}
    prior=dict(candidates=[dict(edit=e,status='rejected',issues=['valid_omission_unit']) for e in original])
    w=clause.process_window(None,tmp_path,dict(window_id='test',passage_id='test',reference='Test 1:1–2',question='SECRET_QA'),
                           clean,source,selected,'reviewer',prior)
    assert requests==['review','review','review-original-boundary']
    rows=w['candidates']
    assert [c['status'] for c in rows]==['accepted','accepted','rejected','rejected','accepted','held']
    assert 'unit_phrase' in rows[0]['flags']
    assert rows[1]['flags']==['distributed_alignment','other_meaning_changed']
    assert rows[2]['issues']==['fluent']
    assert rows[4]['issues']==[] and rows[4]['flags']==['unit_uncertain','unverified_alignment']
    assert rows[5]['review_holds']==['key_content_removed'] and rows[5]['issues']==[]
    assert all('valid_omission_unit' not in r['checks'] for r in rows)
    bank=dict(unit='clause',mode='automatic',review_version=8,provenance='Test',windows=[w],previous_audit='v1',
              required_checks=list(clause.ClauseChecks.model_fields),information_loss_policy='content_review_unit_metadata')
    manifest={'windows':[dict(id='test',conditions={'clean':{'verses':clean}})]}
    report=make_report(bank,manifest,{'test':source})
    assert '3 accepted' in report and '2 rejected' in report and '1 held for review' in report
    assert 'all 5 checks' in report and 'Automatic boundary repair' in report
    assert 'Unit classification (not a rejection check)' in report
    assert 'Needs review · key content removed' in report


def test_bad_quote_does_not_skip_bilingual_review_or_make_an_alignment_rejection(monkeypatch,tmp_path):
    clean={'1:1':'他来了，然后走了。'}
    source=Passage('Test',{'1:1':'He came, and then left.'},clean,'test')
    def stub(client,folder,stage,model,prompt,payload,schema,validate):
        assert stage in ('review','review-original-boundary')
        a=review(1); a.english_evidence=[clause.Evidence(verse='1:1',quote='Invented text')]
        b=review(2,valid_in_context='uncertain')
        numbers={x['number'] for x in payload['candidates']}
        result=clause.ClauseDecisions(decisions=[x for x in (a,b) if x.number in numbers]); validate(result); return result
    monkeypatch.setattr(clause,'ask',stub)
    w=clause.process_window(None,tmp_path,dict(window_id='test',passage_id='test'),clean,source,{})
    a,b=w['candidates']
    assert a['status']=='accepted' and a['issues']==[] and a['flags']==['unverified_alignment']
    assert a['source_phrase']=='' and a['invalid_english_evidence']
    assert b['status']=='held' and b['review_holds']==['valid_in_context']


def test_markers_and_empty_verse_policy_are_separate(monkeypatch,tmp_path):
    clean={'1:1':'忽然，他来了。','1:2':'他走了。'}
    source=Passage('Test',{'1:1':'Suddenly, he came.','1:2':'He left.'},clean,'test')
    def stub(client,folder,stage,model,prompt,payload,schema,validate):
        assert [c['number'] for c in payload['candidates']]==[2]
        result=clause.ClauseDecisions(decisions=[review(2,fluent='no')]); validate(result); return result
    monkeypatch.setattr(clause,'ask',stub)
    w=clause.process_window(None,tmp_path,dict(window_id='test',passage_id='test'),clean,source,{})
    assert w['candidates'][0]['issues']==['key_content_removed']
    assert w['candidates'][1]['issues']==['fluent']
    assert w['candidates'][2]['status']=='held' and w['candidates'][2]['review_holds']==['empty_verse_policy']


def test_exact_review_coverage_and_evidence_required():
    with pytest.raises(ValueError):
        clause.validate_clause_reviews(clause.ClauseDecisions(decisions=[review(1),review(1)]),[1,2])
    d=review(1); d.key_content_reason=''
    with pytest.raises(ValueError,match='before/after evidence'):
        clause.validate_clause_reviews(clause.ClauseDecisions(decisions=[d]),[1])


def test_failed_punctuation_repair_can_fall_back_to_fluent_original(monkeypatch,tmp_path):
    clean={'1:1':'当时，城里住着一个先知。村民来了。'}
    source=Passage('Test',{'1:1':'At that time a prophet lived in the city. The villagers came.'},clean,'test')
    seen=[]
    def stub(client,folder,stage,model,prompt,payload,schema,validate):
        seen.append(stage)
        ds=[]
        for item in payload['candidates']:
            d=review(item['number'])
            if item['number']==2:
                if stage=='review':
                    assert item['edited_chinese_verse']=='当时。村民来了。'
                    d.checks.fluent='no'
                else:
                    assert item['edited_chinese_verse']=='当时，村民来了。'
            ds.append(d)
        result=clause.ClauseDecisions(decisions=ds); validate(result); return result
    monkeypatch.setattr(clause,'ask',stub)
    w=clause.process_window(None,tmp_path,dict(window_id='test',passage_id='test'),clean,source,{})
    c=w['candidates'][1]
    assert c['status']=='accepted' and c['edit']==c['original_edit']
    assert c['boundary_repair_attempted'] and not c['boundary_repaired']
    assert [a['status'] for a in c['boundary_attempts']]==['rejected','accepted']
    assert c['checks']['fluent']=='yes'
    assert seen==['review','review-original-boundary']
