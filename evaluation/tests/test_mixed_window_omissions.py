from copy import deepcopy
from types import SimpleNamespace

import pytest

from evaluation.scripts.pipeline import build_mixed_window_omissions as mix


def window():
    candidates=[];start=0
    for i,(kind,n) in enumerate(list(zip(('word','phrase','phrase','clause','clause'),(1,2,2,4,6)))*2):
        candidates.append(dict(id=str(i),kind=kind,chars=n,edit=dict(verse='1:1',start=start,before='甲'*n,after=''),flags=[]))
        start+=n
    return dict(id='w1',clean={'1:1':'甲'*100},clean_content_chars=100,candidates=candidates,conditions={})


def test_joint_mix_fits_each_dose_separately_and_preserves_nesting():
    w=window();plan,info=mix.fit([w],123)
    assert info['exact_ratio_feasible']['joint']
    assert set(plan[('w1',15)])<=set(plan[('w1',30)])
    for d in (15,30):
        cell=mix.materialize(w,plan[('w1',d)],d)
        counts=cell['unit_counts'];n=sum(counts.values())
        assert all(5*counts[k]==mix.SHARES[k]*n for k in mix.KINDS)
        assert d-2<=cell['actual_percent']<=d+2
    assert mix.fit([w],123)[0]==plan


def test_overlapping_candidates_cannot_inflate_event_count_or_dose():
    w=window();duplicate=deepcopy(w['candidates'][0]);duplicate['id']='overlap'
    w['candidates'].append(duplicate)
    plan,_=mix.fit([w],123)
    for ids in plan.values():assert not {'0','overlap'}<=set(ids)


def test_missing_word_candidates_report_inexact_mix_instead_of_relabeling():
    w=window();w['candidates']=[c for c in w['candidates'] if c['kind']!='word']
    plan,info=mix.fit([w],123)
    assert not info['exact_ratio_feasible']['joint']
    for d in (15,30):
        cell=mix.materialize(w,plan[('w1',d)],d)
        assert 'word' not in cell['unit_counts']
        assert d-2<=cell['actual_percent']<=d+2


def test_redraw_preserves_passed_low_variant_and_excludes_failed_high():
    w=window();plan,_=mix.fit([w],123)
    new,_=mix.fit([w],124,fixed={('w1',15):plan[('w1',15)]},banned=[(('w1',30),plan[('w1',30)])])
    assert new[('w1',15)]==plan[('w1',15)]
    assert set(new[('w1',30)])!=set(plan[('w1',30)])
    assert set(new[('w1',15)])<=set(new[('w1',30)])


@pytest.mark.parametrize('text,expected', [('，甲，。','甲。'),('甲。；乙','甲。乙'),('“，甲”','“甲”'),('甲“。”乙','甲乙')])
def test_punctuation_cleanup_does_not_rewrite_words(text,expected):
    assert mix.punctuation_only_cleanup(text)==expected


def test_combined_review_receives_full_text_but_no_question_or_candidate_verdicts(monkeypatch,tmp_path):
    w=window();w['question']='SECRET QUESTION';w['reference']='Test'
    plan,_=mix.fit([w],123);cells={d:mix.materialize(w,plan[('w1',d)],d) for d in mix.DOSES}
    for c in cells.values():
        for e in c['selected']:e['prior_review']='SECRET REVIEW'
    def stub(client,folder,stage,model,prompt,payload,schema,validate):
        assert 'SECRET' not in str(payload)
        assert payload['window']['1:1']['chinese']=='甲'*100
        assert {v['number'] for v in payload['variants']}=={15,30}
        ds=[]
        for dose in (15,30):
            checks=dict.fromkeys(mix.review.ClauseChecks.model_fields,'yes')
            if dose==30:checks['fluent']='no'
            ds.append(mix.CombinedDecision(number=dose,checks=checks,flags=[],reason='Combined-text judgment.'))
        result=mix.CombinedDecisions(decisions=ds);validate(result);return result
    monkeypatch.setattr(mix.review,'ask',stub)
    class Source:english={'1:1':'English source.'}
    result=mix.review_window(None,w,cells,Source(),tmp_path)
    assert result[15]['status']=='pass'
    assert result[30]['status']=='rejected'


def test_loading_uses_strict_word_bank_and_actual_phrase_classification():
    clean={'1:1':'甲乙丙丁戊己庚辛壬癸'}
    source=SimpleNamespace(chinese=clean,english_sha256='english-hash')
    manifest=dict(release='test',windows=[dict(id='w1',passage_id='p1',clean_content_chars=10,
        conditions={'clean':{'verses':clean}})])
    def bank(unit,candidates):
        return dict(unit=unit,release='test',windows=[dict(window_id='w1',reference='Test 1:1',
            clean_zh_sha256=mix.clean_digest(clean),english_sha256='english-hash',candidates=candidates)])
    def candidate(start,kind,status='accepted'):
        return dict(number=start+1,unit_kind=kind,status=status,flags=[],
            edit=dict(verse='1:1',start=start,before=clean['1:1'][start],after=''))
    banks=[('word.json',bank('word',[candidate(0,'word')])),
           ('phrase.json',bank('phrase',[candidate(1,'word'),candidate(2,'phrase')])),
           ('clause.json',bank('clause',[candidate(3,'phrase')]))]
    ws,conflicts=mix.load_candidates(manifest,banks,'p1',{'p1':source})
    assert [(c['kind'],c['edit']['start']) for c in ws[0]['candidates']]==[('word',0),('phrase',2),('phrase',3)]
    assert not conflicts
    banks[-1][1]['windows'][0]['candidates'].append(candidate(2,'phrase','rejected'))
    ws,conflicts=mix.load_candidates(manifest,banks,'p1',{'p1':source})
    assert len(conflicts)==1
    assert all(c['edit']['start']!=2 for c in ws[0]['candidates'])
