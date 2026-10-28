"""Repeat focal checks with anonymous IDs and independently shuffled order."""
import concurrent.futures
import copy
import json
import random
import runpy
from pathlib import Path
from dotenv import load_dotenv

BASE=Path(__file__).resolve().parent
d=runpy.run_path(str(BASE/'run_experiment.py'))
OUT=BASE/'blind_check';(OUT/'responses').mkdir(parents=True,exist_ok=True)
allcases=json.loads((BASE/'cases.json').read_text())
selected=[x for x in allcases if x['group'] in ('focus_variants','constructed') or x['id'] in ['hard:t1_1kgs13:8a66:mcq','gold:t1_2chr26:ryq4:open']]
assert len(selected)==10
load_dotenv(d['OLD']['COMBO']/'qa_generation/.env',override=True)
load_dotenv(d['ROOT']/'.env',override=False)
judge=d['judge'];judge.__globals__['OUT']=OUT
jobs=[];maps={}
for rep in (1,2):
    items=copy.deepcopy(selected);random.Random(70102026+rep).shuffle(items)
    maps[str(rep)]={}
    for n,x in enumerate(items,1):
        anonymous=f'item_{n:02d}';maps[str(rep)][anonymous]=x['id'];x['id']=anonymous
    for name,prompt in d['prompts']().items():jobs.append((name,rep,0,items,prompt))
d['save'](OUT/'id_map.json',maps)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records=list(pool.map(judge,jobs))
mapped=[]
for r in records:
    for x in r['items']:
        mapped.append({'prompt':r['prompt'],'repeat':r['repeat'],'original_id':maps[str(r['repeat'])][x['id']],**x})
d['save'](OUT/'mapped_results.json',mapped)
print('Anonymous-ID repeat check complete:',len(mapped),'judgments')
