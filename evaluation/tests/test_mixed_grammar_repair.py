"""Repair search must change rejected wording and retain the original evidence."""
from copy import deepcopy

from evaluation.scripts.pipeline import repair_mixed_grammar_ladder as r
from evaluation.scripts.variants.current import grammar_source_spans as s
from evaluation.scripts.variants.current import mixed_grammar as m


def bank():
    a='他认真阅读。'; b='他仔细阅读。'
    candidates=[]
    for i,(before,after,start) in enumerate([(a,'他阅读认真。',0),(b,'他阅读仔细。',len(a))]):
        candidates.append(s.annotate(dict(candidate_id=str(i),verse='1:1',start=start,
            before=before,after=after,subtype='misordering',status='pass',content_chars=5)))
    return dict(clean={'1:1':a+b+'甲'*90},clean_content_chars=100,candidates=candidates)


def failure(b, selected_ids, risk_spans):
    selected=[c for c in b['candidates'] if c['candidate_id'] in selected_ids]
    return dict(rate=4,status='flagged',selected_ids=selected_ids,
        draft_sha256=r.g.json_digest(m.apply_candidates(b['clean'],selected)),
        combined=dict(grammar={'explanation':'Synthetic grammar review.'},
            meaning={'judgment':{'explanation':'Synthetic risk.', 'risk_spans':risk_spans}}))


def test_unique_risk_excludes_implicated_edit_only_from_repair_selection():
    b=bank(); old=deepcopy(b)
    finding=r.feedback(b,failure(b,['0'],['阅读认真']))
    assert finding['excluded_candidate_ids']==['0']
    choices=r.options(b,4,[finding],2026)
    assert choices and all([c['candidate_id'] for c in x['selected']]==['1'] for x in choices)
    assert b==old


def test_ambiguous_risk_does_not_arbitrarily_reject_an_individual_candidate():
    b=bank()
    finding=r.feedback(b,failure(b,['0','1'],['阅读']))
    assert finding['excluded_candidate_ids']==[]
    assert finding['draft_sha256']


def test_unchanged_failed_draft_is_excluded_even_without_an_identified_edit():
    b=bank(); finding=r.feedback(b,failure(b,['0'],[]))
    choices=r.options(b,4,[finding],2026,draws=16)
    assert choices
    assert all(r.g.json_digest(m.apply_candidates(b['clean'],x['selected']))!=finding['draft_sha256'] for x in choices)
    assert r.options(b,4,[finding],2026,draws=16)==choices


def test_all_alternatives_excluded_returns_no_choice_without_relaxing_dose():
    b=bank()
    findings=[r.feedback(b,failure(b,[str(i)],[])) for i in range(2)]
    assert not r.options(b,4,findings,2026,draws=16)


def test_repair_defaults_are_bounded_and_scope_is_one_passage():
    args=r.parse_args([])
    assert args.passage=='t1_1kgs13'
    assert args.rounds==2 and args.max_extra==6
    assert args.output not in (args.source.parent,args.cache_run)


def test_remaining_passage_scope_preserves_the_completed_trial(tmp_path):
    args=r.parse_args(['--passage','all','--exclude-passages','t1_1kgs13',
        '--output',str(tmp_path/'run'),'--report',str(tmp_path/'report.html')])
    manifest=r.b.b.read(r.b.b.audit.MANIFEST)
    windows=r.b.select_windows(manifest,args.passage,args.exclude_passages)
    assert len(windows)==57
    assert all(w['passage_id']!='t1_1kgs13' for w in windows)
    assert not {w['id'] for w in windows}.intersection(manifest.get('held_for_review',[]))


def test_new_user_rejection_reopens_prior_pass_without_changing_raw_evidence():
    decision = next(d for d in m.adjudications.DECISIONS if d['id']=='2026-11-23-possessive-speaker')
    b = dict(candidates=[dict(candidate_id='rejected', before=decision['before'], after=decision['after'])])
    old = [dict(rate=25, status='pass', selected_ids=['rejected'], eligible_for_publication=True,
                combined={'status':'pass','evidence':'saved'}),
           dict(rate=20, status='pass', selected_ids=[], eligible_for_publication=True)]
    snapshot = deepcopy(old)
    rows = r.initial_rows(b, old)
    assert old == snapshot
    assert rows[25]['status']=='needs_repair' and rows[25]['model_status']=='pass'
    assert rows[25]['combined']==old[0]['combined']
    assert rows[25]['eligible_for_publication'] is False
    assert rows[20]==old[1]


def test_exact_window_scope_rejects_unknown_or_excluded_windows(tmp_path):
    import pytest
    wid='2kgs_6_24-33/v29-31:1'
    args=r.parse_args(['--passage','all','--window-ids',wid,
        '--output',str(tmp_path/'run'),'--report',str(tmp_path/'report.html')])
    manifest=r.b.b.read(r.b.b.audit.MANIFEST)
    assert [w['id'] for w in r.requested_windows(manifest,args)]==[wid]
    args.window_ids=['nonexistent-window']
    with pytest.raises(ValueError,match='outside active passage scope'):
        r.requested_windows(manifest,args)
