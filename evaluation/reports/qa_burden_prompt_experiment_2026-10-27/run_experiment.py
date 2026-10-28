"""Whole-question burden prompts, frozen before new model results."""
import concurrent.futures
import copy
import hashlib
import json
import random
import runpy
import time
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PREV=OUT.parent/'qa_screen_prompt_experiment_2026-10-27'
OLD=runpy.run_path(str(PREV/'run_experiment.py'))
MODEL='gpt-6.1-sol'

COMMON='''You evaluate respondent-facing comprehension questions for Bible translation checking.
Audience: ordinary adult native speakers of the displayed language, without specialist linguistic training. Do not assume a reading disability, a specific literacy level, or unusual biblical expertise. Your burden ratings are predictions requiring human validation.
Assess the WHOLE displayed item: introductory statements, question, and choices. Splitting a sentence does not reset its total processing burden. Assess the exact language, not an English translation of Chinese. Expected answers and target metadata are not shown to respondents.
The aim is an accessible question about the intended meaning. A complex meaning is a legitimate target. Do not penalize a question simply for using why/how, a passive, one temporal clause, a necessary condition, a biblical name, or more than one sentence. Do not judge solely by word count or grammar labels. Do not let an easy-to-find answer erase avoidable question burden.
Use passage context to resolve reference and assess necessity. Do not score passage complexity. Answer correctness, Bible-rendering differences, spelling aliases and absent nonessential answer descriptors are checked elsewhere; do not substitute those issues for a wording critique.
If intended_target is explicit, preserve it. Otherwise infer only the narrowest target supported by the question and answer, and mark its basis inferred. Do not invent a wider intended target to justify rejection.
Score four dimensions 0..3, higher worse:
naturalness: 0 idiomatic/direct; 1 minor stiffness; 2 wording requires mental repair or is markedly unnatural; 3 malformed/unclear.
processing: 0 readily parsed; 1 ordinary manageable reading demand; 2 substantial AVOIDABLE modifier/role/reference/option-comparison load; 3 layered or conflicting structures make decoding dominate. Identify actual load and its avoidability.
context: 0 sufficient useful context; 1 minor removable detail; 2 substantial irrelevant setup or missing disambiguation, repairable without changing the target; 3 serious missing/irrelevant framing prevents locating the intended event. Distinguish excess from insufficient context in the evidence. Redundancy alone is not necessarily burdensome.
leakage: 0 setup does not give the target answer; 1 possible cue, uncertain; 2 setup materially supplies the proposition being tested; 3 setup explicitly states the answer. A relevant event anchor is not leakage merely because it states a fact. In MCQ the correct answer's presence among choices is not leakage by itself. Asking for X after saying someone requested X happened does not necessarily state that X actually happened.
For every dimension supply a short reason grounded in the actual words. Use brief exact quotes where available. Decision is KEEP or REWRITE; do not delete records. Do not provide a final replacement question unless the particular strategy requests a diagnostic alternative. Return all IDs exactly once; the schema is mandatory.
'''

HOLISTIC='''Strategy: whole-item anchored rubric.
Read the item as an ordinary reader and score all four dimensions separately before deciding. In particular, background that can be read but adds substantial unnecessary parsing counts toward processing/context even when the final question is short.
REWRITE if any dimension is >=2. KEEP if every dimension is <=1. Do not average away a failed dimension. For alternative use an empty string; state no target-loss finding unless a target issue is actually present.
'''

COUNTERFACTUAL='''Strategy: target-preserving burden comparison.
First infer/identify the target. Compare the whole displayed item with the shortest NATURAL and UNAMBIGUOUS wording that preserves that target in the supplied context; do not aim for a minimum word count.
Provide one diagnostic alternative only when it removes a meaningful burden. Check that it preserves the participants, semantic relation, polarity, necessary time/condition and answer scope. An alternative that changes the target is invalid evidence of unnecessary burden. If no meaningful improvement exists, leave alternative empty.
Ask what the reader must hold in memory, unpack or resolve in the original beyond what this valid alternative requires. Use that contrast as evidence for processing/context >=2; being somewhat longer is not enough. Consider necessary background a benefit when it prevents ambiguity. If an apparently simpler question becomes vague, it must fail the context dimension.
REWRITE if any dimension is >=2, otherwise KEEP. Use target_preservation=preserved only for a valid alternative; uncertain if you cannot establish it; not_applicable for no alternative.
'''

STAGED='''Strategy: independent naturalness, burden, context and leakage gates.
1. Naturalness: could an ordinary native speaker ask this naturally without mental repair? Identify the problematic phrase, not just its grammar category.
2. Burden: list the mental operations needed before the respondent knows what is being asked, including long noun modifiers, passive role assignment, referent switching and overlapping choices. Ask whether each is needed to test the intended target. Evaluate introductions and the main query jointly, across sentence boundaries. Rate substantial combined avoidable load >=2 even if each sentence is grammatical.
3. Context: establish the minimal context needed to locate a unique event. Detailed background about another relationship should be removed when the passage already uniquely identifies the queried event; a modest necessary anchor should remain. Missing a needed anchor is also a failure.
4. Leakage: determine whether the setup itself provides the target answer, distinct from merely naming the event. If the target is unclear, explain uncertainty rather than automatically rejecting.
Conclude KEEP only if every dimension <=1; otherwise REWRITE. For alternative use an empty string. Do not let any passing gate offset a failing gate.
'''

def prompts():
    return {'previous_wording_gate':(PREV/'prompt_wording_only_v2.txt').read_text(),
            'whole_item_rubric':COMMON+HOLISTIC,
            'target_preserving_comparison':COMMON+COUNTERFACTUAL,
            'independent_dimensions':COMMON+STAGED}

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def build_cases():
    old=json.loads((PREV/'cases.json').read_text());transfer=json.loads((PREV/'transfer_cases.json').read_text())
    ids={'ec63','f49c','7628','6d68','f36a','b1be','rhwo','gfxe',
         '4cb0','b13a','de9f','f988','8a66','ryq4','w4ys','qysg',
         '1cab','723e','a6cd','725d'}
    result=[]
    for x in old:
        if x['id'].split(':')[-2] in ids:
            y=copy.deepcopy(x);y['group']='previous_controls' if x['provisional_label']=='clear_control' else 'previous_concerns' if x['provisional_label']=='wording_concern' else 'previous_borderline';result.append(y)
    assert len(result)==20,len(result)
    for wanted in ['transfer:handkerchief:original:zh','transfer:handkerchief:repair:zh','transfer:handkerchief:repair:en']:
        y=copy.deepcopy(next(x for x in transfer if x['id']==wanted));y['group']='focus_variants';y['intended_target']='What happened to the sick people (illnesses and evil spirits leaving), not which objects touched Paul or where the objects were taken.';result.append(y)
    y=copy.deepcopy(result[-3]);y['id']='focus:handkerchief:direct:zh';y['question']='根据这段经文，病人的情况有什么变化？';result.append(y)
    # New constructed contrast cases are diagnostic items, not corpus questions.
    for suffix,q,passage,answer,target,label in [
        ('leak','小林把书搬进屋里。是谁把书搬进屋里的？','下雨了，小林把书搬进屋里。小周留在门口。','小林','Identify who moved the books inside.','leakage'),
        ('direct','是谁把书搬进屋里的？','下雨了，小林把书搬进屋里。小周留在门口。','小林','Identify who moved the books inside.','clear'),
        ('anchor','谁把书带到图书馆？','早上，小林把书带到学校。下午，小周把书带到图书馆。','小周','Identify the person who took books to the library.','clear'),
        ('ambiguous','谁把书带走了？','早上，小林把书带到学校。下午，小周把书带到图书馆。','小周','Identify the person who took books to the library.','missing_anchor'),
    ]:
        result.append({'id':'constructed:'+suffix,'set':'constructed','form':'open','question':q,'options':{},'expected_answer':answer,'passage':passage,'intended_target':target,'group':'constructed','provisional_label':label})
    # Fresh to these prompt trials; seeded sample selected after prompts are written.
    previous_base={x['id'].rsplit(':',1)[0] for x in old};pool={'hard66':[],'gold72':[]}
    windows={x['content_id']:x['window'] for x in json.loads((ROOT/'evaluation/runs/hard66_full_ladder_2026-10-23/_inputs/windows.json').read_text())['windows']}
    for p in sorted((ROOT/'evaluation/datasets/qa/tier1_hard66_canonical').glob('*.json')):
        pid=p.stem;text=(ROOT/f'evaluation/runs/full_ladder_2026-10-23/{pid}/omission/0%/passage_target_decanonicalized.txt').read_text();verses=OLD['index_chinese'](text,pid)
        for x in json.loads(p.read_text()):
            if x['q_type']!='mcq' or x.get('status')=='exclude':continue
            cid=x['passage_id'].removeprefix('uw-').removesuffix('-mcq')
            if 'hard:'+cid in previous_base:continue
            pool['hard66'].append({'id':f'hard:{cid}:mcq','set':'hard66','form':'mcq','question':x['Q'],'options':x['A'],'expected_answer':x['A'][x['correct']],'correct_option':x['correct'],'passage':'\n'.join(f'{k} {verses[k]}' for k in windows[cid]),'context':'reviewed clean Chinese verse window','group':'fresh_corpus','provisional_label':'unlabelled'})
    for p in sorted((ROOT/'evaluation/datasets/qa/tier1_gold72_canonical_5opt').glob('*.json')):
        for x in json.loads(p.read_text()):
            if 'gold:'+x['content_id'] in previous_base:continue
            pool['gold72'].append({'id':f'gold:{x["content_id"]}:open','set':'gold72','form':'open','question':x['open']['original_question'],'options':{},'expected_answer':x['open']['original_answer'],'passage':(OLD['COMBO']/f'qa_generation/fixtures/passages/tier1/{OLD["MAPPING"][x["passage_id"]]}.txt').read_text(),'context':'full English source passage','group':'fresh_corpus','provisional_label':'unlabelled'})
    rng=random.Random(270126)
    for group in ('hard66','gold72'):result.extend(rng.sample(pool[group],6))
    assert len(result)==40 and len({x['id'] for x in result})==40
    return result

SCORE={'type':'object','properties':{'score':{'type':'integer','minimum':0,'maximum':3},'evidence':{'type':'string'}},'required':['score','evidence'],'additionalProperties':False}
FIELDS={'id':{'type':'string'},'decision':{'type':'string','enum':['KEEP','REWRITE']},'target':{'type':'string'},'target_basis':{'type':'string','enum':['explicit','inferred']},'naturalness':SCORE,'processing':SCORE,'context':SCORE,'leakage':SCORE,'alternative':{'type':'string'},'target_preservation':{'type':'string','enum':['preserved','uncertain','not_applicable']},'reason':{'type':'string'}}
SCHEMA={'type':'object','properties':{'items':{'type':'array','items':{'type':'object','properties':FIELDS,'required':list(FIELDS),'additionalProperties':False}}},'required':['items'],'additionalProperties':False}
BASE=OLD['SCHEMA']

def payload(items):
    passages={};cases=[]
    for x in items:
        key='p'+hashlib.sha256(x['passage'].encode()).hexdigest()[:12]
        passages[key]=x['passage']
        cases.append({**{k:v for k,v in x.items() if k in ['id','form','question','options','expected_answer','correct_option','intended_target']},'passage_id':key})
    return {'passages':passages,'items':cases}

def judge(job):
    name,rep,batch,items,prompt=job;dest=OUT/'responses'/f'{name}_r{rep}_b{batch}.json'
    request={'prompt':prompt,'payload':payload(items),'schema':BASE if name=='previous_wording_gate' else SCHEMA,'model':MODEL}
    digest=hashlib.sha256(json.dumps(request,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if dest.exists():
        r=json.loads(dest.read_text());assert r['request_hash']==digest;return r
    started=time.time()
    with OpenAI(max_retries=1,timeout=180) as client:
        response=client.responses.create(model=MODEL,input=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(request['payload'],ensure_ascii=False)}],text={'format':{'type':'json_schema','name':'qa_burden','strict':True,'schema':request['schema']}})
    data=json.loads(response.output_text)
    assert sorted(x['id'] for x in data['items'])==sorted(x['id'] for x in items)
    mismatches=[]
    for x in data['items']:
        if name!='previous_wording_gate':
            expected='REWRITE' if max(x[k]['score'] for k in ['naturalness','processing','context','leakage'])>=2 else 'KEEP'
            if x['decision']!=expected:mismatches.append(x['id'])
    r={'prompt':name,'repeat':rep,'batch':batch,'request_hash':digest,'model':response.model,'response_id':response.id,'elapsed_seconds':time.time()-started,'usage':response.usage.model_dump(),'threshold_mismatches':mismatches,'items':data['items']}
    save(dest,r);print(name,rep,batch,dict(Counter(x['decision'] for x in data['items'])),flush=True);return r

def summarize(cases,records):
    votes=defaultdict(list)
    for r in records:
        for x in r['items']:votes[r['prompt'],x['id']].append((r['repeat'],x))
    summary={}
    for name in prompts():
        groups={}
        for group in dict.fromkeys(x['group'] for x in cases):
            ids=[x['id'] for x in cases if x['group']==group]
            groups[group]={'n':len(ids),'keep_both':sum(len(votes[name,i])==2 and all(v['decision']=='KEEP' for _,v in votes[name,i]) for i in ids),'rewrite_both':sum(len(votes[name,i])==2 and all(v['decision']=='REWRITE' for _,v in votes[name,i]) for i in ids),'disagree':sum(len(votes[name,i])==2 and len({v['decision'] for _,v in votes[name,i]})>1 for i in ids)}
        summary[name]={'groups':groups,'threshold_mismatches':sum(len(r['threshold_mismatches']) for r in records if r['prompt']==name)}
    save(OUT/'summary.json',summary)
    lines=['# Whole-item burden prompt results','', 'Two repetitions per prompt. Provisional labels are not independent human judgments. All prompts were frozen before this experiment’s model calls; prompts were developed from prior examples. Fresh corpus items are new to model trials, not an independently labelled test set.','']
    for c in cases:
        lines+=['## '+c['id'],'',c['question'],'','Group: '+c['group'],'']
        for name in prompts():
            for rep,x in sorted(votes[name,c['id']]):
                dims='; '.join(f'{k}={x[k]["score"]}: {x[k]["evidence"]}' for k in ['naturalness','processing','context','leakage']) if name!='previous_wording_gate' else ''
                lines += [f'**{name}, run {rep}: {x["decision"]}**',x['reason'],dims]
                if x.get('alternative'):lines += ['Diagnostic alternative: '+x['alternative']+' (preservation: '+x['target_preservation']+')']
                lines+=['']
    (OUT/'item_results.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2),flush=True)

def main():
    OUT.mkdir(exist_ok=True);(OUT/'responses').mkdir(exist_ok=True)
    ps=prompts()
    for name,text in ps.items():
        path=OUT/f'prompt_{name}.txt'
        if path.exists():assert path.read_text()==text+'\n'
        else:path.write_text(text+'\n')
    cs=build_cases()
    if (OUT/'cases.json').exists():assert json.loads((OUT/'cases.json').read_text())==cs
    else:save(OUT/'cases.json',cs)
    save(OUT/'manifest.json',{'model':MODEL,'repeats':2,'batch_size':8,'calls':40,'cases':40,'groups':dict(Counter(x['group'] for x in cs)),'prompt_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in ps.items()},'baseline_schema':'original decision/reason; new prompts use dimension diagnostics','notes':['No labels or previous scores sent to model.','No automated human-difficulty ground truth.','12 new corpus questions, 4 constructed checks, 4 focus variants, 20 previously examined questions.','Mixed languages/formats/context scopes; no between-language performance claim.']})
    import sys
    if '--prepare-only' in sys.argv:
        print('Prepared',len(cs),'cases and',len(ps),'frozen prompts');return
    load_dotenv(OLD['COMBO']/'qa_generation/.env',override=True);load_dotenv(ROOT/'.env',override=False)
    jobs=[]
    for name,prompt in ps.items():
        for rep in (1,2):
            shuffled=cs.copy();random.Random(202610270+rep).shuffle(shuffled)
            for b,start in enumerate(range(0,len(shuffled),8)):jobs.append((name,rep,b,shuffled[start:start+8],prompt))
    records=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(judge,j):j[:3] for j in jobs}
        for f in concurrent.futures.as_completed(futures):
            try:records.append(f.result())
            except Exception as e:errors.append({'job':futures[f],'error':str(e)});print('ERROR',futures[f],type(e).__name__,flush=True)
    save(OUT/'errors.json',errors);summarize(cs,records)
    if errors:raise SystemExit(f'{len(errors)} failed jobs')

if __name__=='__main__':main()
