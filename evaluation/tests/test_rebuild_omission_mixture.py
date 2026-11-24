from types import SimpleNamespace
import json
import pytest

from evaluation.scripts.pipeline import rebuild_omission_mixture as rebuild


def test_json_dose_keys_map_to_structured_review_decisions(monkeypatch, tmp_path):
    w=dict(id='w',clean={'1:1':'甲乙。'})
    cells={'15':dict(status='pending_combined_review',verses={'1:1':'乙。'},
                    edits=[dict(verse='1:1',start=0,before='甲',after='')],punctuation_cleanup=[])}
    def ask(client,folder,stage,model,prompt,payload,schema,validate):
        assert payload['variants'][0]['number']==15
        decision=rebuild.m.CombinedDecision(number=15,
            checks=dict.fromkeys(rebuild.m.review.ClauseChecks.model_fields,'yes'),flags=[],reason='Supported deletion.')
        result=rebuild.m.CombinedDecisions(decisions=[decision])
        validate(result)
        return result
    monkeypatch.setattr(rebuild.m.review,'ask',ask)
    result=rebuild.review_window(None,w,cells,SimpleNamespace(english={'1:1':'Original.'}),tmp_path)
    assert set(result)=={'15'} and result['15']['status']=='pass'


def test_assigned_preview_summary_counts_only_each_windows_delivered_dose():
    windows=[dict(id='a'),dict(id='b')]
    cells={'a':{'15':dict(unit_counts={'phrase':1},status='pass')},
           'b':{'30':dict(unit_counts={'word':1,'clause':1},status='pass_with_flags')}}
    result=rebuild.summary(windows,cells)
    assert result['15']['occurrences']=={'phrase':1}
    assert result['30']['percentages']=={'word':50,'phrase':0,'clause':50}
    assert result['15']['statuses']=={'pass':1}
    assert result['30']['statuses']=={'pass_with_flags':1}


def test_all_active_scope_excludes_held_across_passages():
    baseline=dict(windows=[dict(id='a',passage_id='one'),dict(id='b',passage_id='two'),
                           dict(id='held',passage_id='two')],held_for_review=['held'])
    assert [w['id'] for w in rebuild.selected_windows(baseline,all_active=True)]==['a','b']
    assert [w['id'] for w in rebuild.selected_windows(baseline,passage_id='two')]==['b']
    assert [w['id'] for w in rebuild.selected_windows(baseline,assignment={'a':'omission15'})]==['a']


def test_multi_clause_span_keeps_reviewed_classification_and_counts_once():
    original=dict(edits=[dict(before='甲。乙。')],kinds=['multiple_clauses'])
    grouped=rebuild.mixture_candidate(original)
    assert grouped['kinds']==['clause']
    assert grouped['reviewed_kinds']==original['kinds']==['multiple_clauses']
    with pytest.raises(ValueError,match='classification'):
        rebuild.mixture_candidate(dict(edits=[{}],kinds=['uncertain']))


def test_reused_reviews_require_unchanged_bilingual_context(tmp_path):
    source=SimpleNamespace(english={'1:1':'Original.'})
    w=dict(id='w',passage_id='p',clean={'1:1':'甲乙。'})
    verdict={'15':dict(status='rejected',verses={'1:1':'乙。'})}
    cfg=dict(passage_id='p',prompt_sha256=rebuild.m.clean_digest(rebuild.m.COMBINED_REVIEW),
             reviewer=rebuild.m.review.JUDGE,inputs={'bank':'hash'},
             source_sha256=rebuild.m.clean_digest(source.english))
    path=tmp_path/'prior.json'
    legacy_window={k:v for k,v in w.items() if k!='passage_id'}
    path.write_text(json.dumps(dict(configuration=cfg,windows=[legacy_window],rounds=[dict(cells={'w':verdict})])))
    histories={'w':[]}
    provenance=rebuild.reuse_histories([path],[w],histories,{'p':source},{'bank':'hash'})
    assert histories['w']==[verdict] and str(path) in provenance
    changed={**w,'clean':{'1:1':'甲丙。'}}
    with pytest.raises(ValueError,match='clean window changed'):
        rebuild.reuse_histories([path],[changed],{'w':[]},{'p':source},{'bank':'hash'})
    with pytest.raises(ValueError,match='English source changed'):
        rebuild.reuse_histories([path],[w],{'w':[]},{'p':SimpleNamespace(english={'1:1':'Changed.'})},{'bank':'hash'})
