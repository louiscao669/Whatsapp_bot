from copy import deepcopy
import pytest
from evaluation.scripts.campaigns.current import report_omission_ladder_rerun as report


def fixture():
    before=[];after=[]
    for i in range(7):
        for d in report.DOSES:
            for item in ('a','b'):
                row=dict(reader_index=i,family='clean' if d==0 else 'omission',dose=d,item=item,
                    question=item,choices=['甲','乙','丙','丁','无法判断'],key='A',choice='A',
                    outcome='correct',request_hash=f'{i}-{d}-{item}',passage='原文',label=str(i),reference='Book 1:1')
                before.append(row)
                if item=='b' and d==50:continue
                new=deepcopy(row)
                if item=='a' and d==60:new.update(choice='E',outcome='abstain',request_hash=row['request_hash']+'-new',passage='删节文本')
                after.append(new)
    return after,before


def test_curves_keep_same_items_and_e_is_separate_from_wrong_answers():
    after,before=fixture();result=report.analyze(after,before)
    assert result['matched_question_ids']==['a']
    assert all(r['n']==1 for r in result['matched_summary'])
    last=next(r for r in result['matched_summary'] if r['reader_index']==0 and r['dose']==60 and r['phase']=='after')
    assert last['accuracy']==0 and last['abstention_rate']==1
    assert last['incorrect']==0 and last['accuracy_among_A_D'] is None
    assert next(r for r in result['same_item_per_dose'] if r['reader_index']==0 and r['dose']==5)['after']['n']==2
    assert len(result['changed_answers'])==7


def test_changed_scoring_of_identical_request_is_detected():
    after,before=fixture();row=next(r for r in after if r['dose']==60 and r['item']=='a')
    row['request_hash']=row['request_hash'].removesuffix('-new')
    with pytest.raises(ValueError,match='unchanged request'):report.analyze(after,before)
