from itertools import combinations

import pytest

from evaluation.scripts.analysis.current import audit_omission_capacity as audit


def fixture_window():
    units=[('word',0,2),('phrase',2,3),('phrase',5,3),('clause',8,5),
           ('clause',13,5),('clause',17,6),('phrase',21,4),('word',23,2)]
    return dict(id='w',clean={'1:1':'甲'*25},clean_content_chars=25,
        candidates=[dict(id=str(i),kind=k,chars=n,edit=dict(verse='1:1',start=s,before='甲'*n,after=''))
                    for i,(k,s,n) in enumerate(units)])


def admissible_subsets(w,exact):
    for n in range(1,len(w['candidates'])+1):
        for subset in combinations(w['candidates'],n):
            positions=[set(range(c['edit']['start'],c['edit']['start']+c['chars'])) for c in subset]
            if any(a&b for a,b in combinations(positions,2)):continue
            if sum(c['chars'] for c in subset)>=w['clean_content_chars']:continue
            if exact and any(5*sum(c['kind']==k for c in subset)!=share*n for k,share in audit.m.SHARES.items()):continue
            yield subset


@pytest.mark.parametrize('exact',[False,True])
def test_numeric_ceiling_matches_exhaustive_search(exact):
    w=fixture_window()
    expected=max(target for subset in admissible_subsets(w,exact) for target in range(1,101)
                 if abs(100*sum(c['chars'] for c in subset)/25-target)<=2)
    plan=audit.capacity_plan([w],exact=exact)
    assert plan['target']==expected
    assert audit.capacity_plan([w],exact=exact,target=expected+1) is None


def test_raw_maximum_excludes_overlaps_and_empty_verses():
    w=fixture_window()
    assert audit.raw_maximum(w)['deleted_chars']==max(sum(c['chars'] for c in s) for s in admissible_subsets(w,False))
    w['candidates'].append(dict(id='entire',kind='clause',chars=25,
        edit=dict(verse='1:1',start=0,before='甲'*25,after='')))
    assert 'entire' not in audit.raw_maximum(w)['selected_ids']


def test_failed_selection_is_excluded_and_fixed_selection_preserved():
    w=fixture_window();first=audit.capacity_plan([w],target=40)
    second=audit.capacity_plan([w],target=40,banned=[('w',first['selected']['w'])])
    assert set(first['selected']['w'])!=set(second['selected']['w'])
    assert audit.capacity_plan([w],target=40,fixed=first['selected'])['selected']==first['selected']
