"""Adaptive check: exact Chinese example and candidate wording repairs."""
import concurrent.futures
import copy
import json
import runpy
from pathlib import Path

from dotenv import load_dotenv

OUT=Path(__file__).resolve().parent
d=runpy.run_path(str(OUT/'run_experiment.py'))
cs=json.loads((OUT/'cases.json').read_text())
load_dotenv(d['COMBO']/'qa_generation/.env',override=True)
load_dotenv(d['ROOT']/'.env',override=False)
gold=next(x for x in cs if x['id']=='gold:t1_acts19:b1be:open')
hard=next(x for x in cs if x['id']=='hard:t1_acts19:7628:mcq')
test=[]
x=copy.deepcopy(gold);x['id']='transfer:handkerchief:original:zh';x['question']='当触摸过保罗的手帕和围裙被带到病人那里时发生了什么？';x['form']='mcq';x['options']={'A':'病人陷入了深度睡眠','B':'疾病和邪灵离开了病人','C':'犹太驱魔师给病人驱魔','D':'病人变得无法说话','E':'根据这段文字无法判断'};x['expected_answer']=x['options']['B'];x['correct_option']='B';x['passage']=(d['ROOT']/'evaluation/runs/full_ladder_2026-10-23/t1_acts19/omission/0%/passage_target_decanonicalized.txt').read_text();x['context']='full Chinese clean passage';test.append(x)
x=copy.deepcopy(x);x['id']='transfer:handkerchief:repair:zh';x['question']='摸过保罗的手帕和围裙被带到病人那里。病人随后怎么样了？';test.append(x)
x=copy.deepcopy(gold);x['id']='transfer:handkerchief:repair:en';x['question']='Cloths that had touched Paul were taken to the sick. What happened to the sick?';test.append(x)
x=copy.deepcopy(hard);x['id']='transfer:exorcists:original:zh';test.append(x)
x=copy.deepcopy(hard);x['id']='transfer:exorcists:repair:zh';x['question']='谁受伤逃出了那房子？';test.append(x)
x=copy.deepcopy(next(x for x in cs if x['id']=='hard:t1_1kgs13:8a66:mcq'));x['id']='transfer:passive:control:zh';test.append(x)
d['save'](OUT/'transfer_cases.json',test)
prompt=d['prompts']()['wording_only_v2']
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    records=list(pool.map(d['judge'],[('wording_only_transfer',rep,0,test,prompt) for rep in (1,2)]))
d['save'](OUT/'transfer_results.json',records)
for r in records:
    print('REPEAT',r['repeat'])
    for x in r['items']:print(x['id'],x['decision'],x['reason'])
