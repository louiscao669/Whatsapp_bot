"""Compare frozen screening prompts on a small, provisionally labelled challenge set."""
import ast
import concurrent.futures
import hashlib
import json
import random
import re
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
COMBO = Path('/Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo')
MODEL = 'gpt-6.1-sol'
MAPPING = {
    't1_1kgs13':'1kgs_13_1-34','t1_2chr26':'2chr_26_1-23',
    't1_2kgs11':'2kgs_11_1-21','t1_2kgs6_7':'2kgs_6_24-7_20',
    't1_2sam21':'2sam_21_15-22','t1_acts19':'acts_19_11-20',
    't1_acts20':'acts_20_7-12','t1_acts23':'acts_23_12-35',
    't1_judg17_18':'judg_17_1-18_31','t1_judg9':'judg_9_1-57',
}

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def source_prompt(name):
    tree = ast.parse((COMBO/'qa_generation/prompts/qa.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value.args[0])
    raise ValueError(name)

def index_chinese(text, pid):
    chapters = [17,18] if pid=='t1_judg17_18' else [6,7] if pid=='t1_2kgs6_7' else [int(re.search(r'(\d+)', MAPPING[pid].split('_',1)[1])[1])]
    marks=list(re.finditer(r'(?m)^\s*(\d+)\s+',text)); ci=0; out={}
    for i,m in enumerate(marks):
        v=int(m[1]); following=int(marks[i+1][1]) if i+1<len(marks) else None
        if i==0 and v==chapters[ci]:v=1
        elif ci+1<len(chapters) and v==chapters[ci+1] and following is not None and following<v:
            ci+=1;v=1
        key=f'{chapters[ci]}:{v}'
        if key in out:raise ValueError(('duplicate verse',pid,key))
        out[key]=text[m.start():marks[i+1].start() if i+1<len(marks) else len(text)].strip()
    return out

def cases():
    hard_bad={'ec63','f49c','9cf3','7628','3162','6d68','f36a'}
    hard_simple={'9a0c','4cb0','b13a','de9f','9035','1246','f988','8a66'}
    hard_border={'1cab','723e','9f00','6138','a6cd','fe00','725d','c2d9','97e8'}
    windows={x['content_id']:x['window'] for x in json.loads((ROOT/'evaluation/runs/hard66_full_ladder_2026-10-23/_inputs/windows.json').read_text())['windows']}
    result=[]
    for p in sorted((ROOT/'evaluation/datasets/qa/tier1_hard66_canonical').glob('*.json')):
        pid=p.stem
        text=(ROOT/f'evaluation/runs/full_ladder_2026-10-23/{pid}/omission/0%/passage_target_decanonicalized.txt').read_text()
        verses=index_chinese(text,pid)
        for x in json.loads(p.read_text()):
            short=x['passage_id'].split(':')[-1].rsplit('-',1)[0]
            if x['q_type']!='mcq' or short not in hard_bad|hard_simple|hard_border:continue
            label='wording_concern' if short in hard_bad else 'clear_control' if short in hard_simple else 'borderline'
            cid=x['passage_id'].removeprefix('uw-').removesuffix('-mcq')
            keys=windows[cid]
            passage='\n'.join(f'{k} {verses[k]}' for k in keys)
            result.append({'id':f'hard:{cid}:mcq','set':'hard66','form':'mcq','question':x['Q'],'options':x['A'],'expected_answer':x['A'][x['correct']], 'correct_option':x['correct'],'passage':passage,'context':'actual reviewed clean verse window','reference':x['reference'],'provisional_label':label})
    gold=[]
    for p in sorted((ROOT/'evaluation/datasets/qa/tier1_gold72_canonical_5opt').glob('*.json')):
        gold.extend(json.loads(p.read_text()))
    # Selection frozen before any model calls. Indices refer to the complete prior audit.
    gold_bad={4,38,39,52,54};gold_simple={12,14,22,34,47,58,71};gold_border={2,8,27,50}
    for n,x in enumerate(gold,1):
        if n not in gold_bad|gold_simple|gold_border:continue
        form='mcq' if n==39 else 'open'
        q=x['mcq']['mcq_stem'] if form=='mcq' else x['open']['original_question']
        opts=dict(zip('ABCDE',x['mcq']['mcq_options'])) if form=='mcq' else {}
        label='wording_concern' if n in gold_bad else 'clear_control' if n in gold_simple else 'borderline'
        result.append({'id':f'gold:{x["content_id"]}:{form}','set':'gold72','form':form,'question':q,'options':opts,'expected_answer':x['open']['original_answer'],'passage':(COMBO/f'qa_generation/fixtures/passages/tier1/{MAPPING[x["passage_id"]]}.txt').read_text(),'reference':x['reference'],'context':'full English source passage, not experimental target-language window','provisional_label':label})
    assert len(result)==40, len(result)
    return result

COMMON='''You screen comprehension QA items for a Bible-translation checking study.
The respondent should understand the supplied passage, not struggle to decode the question.
Assess the exact displayed wording in its own language (English or Chinese). Do not translate Chinese into English to assess its syntax. The English expected answer on a Chinese item is scoring metadata, not a respondent instruction.
Use only the supplied clean passage. Do not use prior biblical knowledge. Do not rewrite the passage or evaluate translation quality.
Decisions: KEEP = usable as written; REWRITE = preserve the intended meaning target but block this wording pending revision; DROP = answer/target is unsupported or unsuitable without changing the target itself.
Do not produce rewritten questions. Explain each decision briefly with exact words from the question or options when relevant.
'''
STRICT='''Apply a strict syntax admission gate before considering whether an answer is easy to find.
Mark REWRITE if any of the following occurs: (1) a subordinate or relative clause is nested inside another clause modifying the main question; (2) a fronted passive temporal setup delays identification of the questioned actor; (3) multiple reporting/belief/request predicates require tracking several actor roles; (4) archaic negative wording combines with unresolved pronouns; (5) malformed or unnatural question phrasing.
A main question plus ONE ordinary temporal clause is allowed. One short passive, one simple why question, or one normal relative modifier is not automatically a failure. Length and WH word are not substitutes for structural analysis.
Also DROP unsupported answers, wrong question-answer relations, or multiple defensible MCQ keys; REWRITE fixable unclear referents, overly broad sequence anchors or excessively burdensome choices.
When a structural trigger is present it overrides direct answer recoverability. In the reason identify the actual construction and quote it. Otherwise keep directly supported, clearly worded items.
'''
BALANCED='''Judge unnecessary processing burden separately from complexity of the meaning tested.
KEEP questions about agency, causation, temporal order, negation or conditions when wording is direct and the passage supports one answer. Do not reject because the intended relation is complex, the answer has a biblical name, or the question is why/how.
REWRITE wording when: nested modifiers or reporting clauses obscure actor/action roles; a pronoun has competing antecedents in this displayed context; unnatural compression forces mental rewording; an event-order question has no clear comparison interval; a long numerical/list setup is unnecessary for identifying the target; the setup discloses the answer; or choices impose avoidable long overlapping lists. Quote the actual problem, rather than merely counting clauses.
DROP if the expected answer is unsupported, the relation asked differs from that answered, or more than one choice is supported as the requested answer.
Do not change or ignore the target just to make a question short. Some clause-bearing questions are perfectly usable. Clarity must be judged from the exact respondent wording, not your ability as an expert to guess the intent.
'''
STAGED='''Evaluate in this order; do not let an explicit answer compensate for bad wording.
1. Parse the question: identify main queried role/action, event setup, any subordinate clauses inside that setup, reporting predicates and pronoun antecedents. Look at the entire question; never assign simplicity just from who/what/where.
2. Independent wording gate: REWRITE for nested clause processing, delayed actor identification inside a passive temporal setup, two-layer speech/request/belief tracking, malformed phrasing, or unresolved referents. Name the exact construction in the reason. A single clear temporal clause or simple passive is allowed. Test the relation, not reading endurance.
3. Grounding gate: verify the expected answer in the supplied text and that question and answer express the same relation. DROP if unsupported or ambiguous between distinct answers; mere paraphrases do not count as distinct answers.
4. Format gate: inspect choices for multiple true keys, unnecessary list comparison and ambiguity introduced by options; REWRITE avoidable option burden. A stem that gives away its own answer must be REWRITE.
5. Decision: KEEP only if all gates pass. A repairable wording failure is REWRITE, not DROP. Do not invent defects or penalize necessary semantic complexity. Quote exact evidence for any blocking decision.
'''

WORDING_ONLY='''You are the WORDING gate, one independent gate in a larger QA admission system. Answer grounding is checked elsewhere. Return only KEEP or REWRITE; do not use DROP.
Judge exact respondent-facing syntax, naturalness and avoidable reading burden. Use the passage only to resolve referents and determine whether context makes a short question clear. Do NOT reject a name spelling variant, a rendering difference, an unsupported expected answer, a missing extra descriptor in a choice, or a disputed passage interpretation: those belong to the separate grounding gate. Those issues must not substitute for assessing syntax.
Parse the ENTIRE question, not just the WH word. In your reason explicitly state the deepest clause/modifier structure and any unresolved referent, even for KEEP. This is mandatory before making the decision.
REWRITE when any of these wording failures is present:
- A relative clause is embedded inside a temporal/passive setup before the main question.
- A passive temporal setup with a modified actor delays the queried participant until the end.
- A temporal setup reports someone's speech and the main question reports another person's speech or perception, requiring nested viewpoint tracking.
- A relative actor description plus an archaic negative prediction requires resolving repeated pronouns.
- Two layers of request/desire/consultation require tracking three participant roles to identify what is asked.
- The wording is grammatically incomplete or unnatural enough that a reader must repair it mentally.
- A question setup itself supplies its answer, or response options create excessive overlapping-list decoding rather than a direct meaning check.
KEEP a main question plus one clear temporal clause, a simple passive, a normal single reported belief, or a short question whose intended referent is unique in the supplied context. Causal, conditional and temporal meanings are legitimate targets. Names, theological content and long answers alone are not syntax defects.
Clarity takes precedence over answer recoverability. An explicit answer does not rescue failed wording. Conversely do not invent a wording defect to justify concerns that belong to another gate. Quote exact wording supporting a REWRITE.
'''

SCHEMA={'type':'object','properties':{'items':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'decision':{'type':'string','enum':['KEEP','REWRITE','DROP']},'reason':{'type':'string'}},'required':['id','decision','reason'],'additionalProperties':False}}},'required':['items'],'additionalProperties':False}

def prompts():
    raw=source_prompt('difficult_qa_filter_prompt')
    # Preserve substantive current instructions; adapt only multi-case input/output wrapper.
    baseline=raw.split('        Passage:\n        {passage}')[0]
    baseline+='\nApply those rules independently to the cases supplied. Map Remove=false to KEEP and Remove=true to DROP. Return id, decision and reason in the requested JSON schema. Do not use REWRITE for this baseline.'
    return {'baseline_current_filter':baseline,'strict_syntax':COMMON+STRICT,'balanced_burden':COMMON+BALANCED,'staged_gate':COMMON+STAGED,'wording_only_v2':COMMON+WORDING_ONLY}

def judge(job):
    name,rep,batch,items,prompt=job
    dest=OUT/'responses'/f'{name}_r{rep}_b{batch}.json'
    if dest.exists():return json.loads(dest.read_text())
    payload=[{k:v for k,v in x.items() if k not in ('provisional_label','set','context')} for x in items]
    started=time.time()
    client=OpenAI(max_retries=1,timeout=180)
    response=client.responses.create(model=MODEL,input=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],text={'format':{'type':'json_schema','name':'screening','strict':True,'schema':SCHEMA}})
    data=json.loads(response.output_text)
    assert sorted(x['id'] for x in data['items'])==sorted(x['id'] for x in items)
    record={'prompt':name,'repeat':rep,'batch':batch,'model':response.model,'response_id':response.id,'elapsed_seconds':time.time()-started,'usage':response.usage.model_dump(),'items':data['items']}
    save(dest,record)
    print(f'{name} repeat {rep} batch {batch}: '+str(Counter(x['decision'] for x in data['items'])),flush=True)
    return record

def summarize(cs,records):
    lookup={x['id']:x for x in cs};summary={}
    for name in prompts():
        rs=[r for r in records if r['prompt']==name];per={}
        for r in rs:
            for x in r['items']:per.setdefault(x['id'],[]).append(x)
        groups={}
        for label in ('wording_concern','clear_control','borderline'):
            ids=[x['id'] for x in cs if x['provisional_label']==label]
            votes=[v for cid in ids for v in per.get(cid,[])]
            groups[label]={'items':len(ids),'judgments':len(votes),'blocked':sum(v['decision']!='KEEP' for v in votes),'blocked_both_runs':sum(len(per.get(cid,[]))==2 and all(v['decision']!='KEEP' for v in per[cid]) for cid in ids),'kept_both_runs':sum(len(per.get(cid,[]))==2 and all(v['decision']=='KEEP' for v in per[cid]) for cid in ids)}
        summary[name]={'groups':groups,'decision_disagreements':sum(len(v)==2 and v[0]['decision']!=v[1]['decision'] for v in per.values()),'admission_disagreements':sum(len(v)==2 and (v[0]['decision']=='KEEP')!=(v[1]['decision']=='KEEP') for v in per.values())}
    save(OUT/'summary.json',summary)
    lines=['# Screening prompt experiment: item-level results','', 'Four initial frozen prompts plus an adaptive wording-only follow-up; two runs each; one model; labels are provisional author judgments, not independent gold labels. English Gold72 and Chinese Hard66 results are not a language-controlled comparison. No production data changed.','', '| Item | Provisional group | Question | Baseline | Strict syntax | Balanced burden | Staged gate | Wording only (adaptive) |','|---|---|---|---|---|---|---|---|']
    allvotes={}
    for r in records:
        for x in r['items']:allvotes.setdefault((r['prompt'],x['id']),[]).append((r['repeat'],x))
    for x in cs:
        cells=[]
        for name in prompts():
            vs=sorted(allvotes.get((name,x['id']),[]))
            cells.append('<br/>'.join(f'r{rep}: {v["decision"]} — {v["reason"]}' for rep,v in vs))
        lines.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in [x['id'],x['provisional_label'],x['question'],*cells])+' |')
    (OUT/'item_results.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2),flush=True)

def main():
    load_dotenv(COMBO/'qa_generation/.env',override=True);load_dotenv(ROOT/'.env',override=False)
    cs=cases();ps=prompts()
    (OUT/'responses').mkdir(exist_ok=True)
    for name,prompt in ps.items():(OUT/f'prompt_{name}.txt').write_text(prompt+'\n')
    if (OUT/'cases.json').exists():assert json.loads((OUT/'cases.json').read_text())==cs,'Inputs changed'
    else:save(OUT/'cases.json',cs)
    save(OUT/'manifest.json',{'model':MODEL,'repeats':2,'batch_size':10,'cases':len(cs),'labels':dict(Counter(x['provisional_label'] for x in cs)),'prompt_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in ps.items()},'notes':['No prior scores, labels or audit notes shown to judges.','Purpose-built diagnostic set; not an independent benchmark.','Gold English full passage; Hard Chinese actual clean windows.','Baseline substantive instructions preserved; JSON response wrapper adapted.','No rewriting/removal of production QA.']})
    jobs=[]
    for name,prompt in ps.items():
        for rep in (1,2):
            shuffled=cs.copy();random.Random(20261027+rep).shuffle(shuffled)
            for batch,start in enumerate(range(0,len(shuffled),10)):
                jobs.append((name,rep,batch,shuffled[start:start+10],prompt))
    records=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futuremap={pool.submit(judge,j):j[:3] for j in jobs}
        for future in concurrent.futures.as_completed(futuremap):
            try:records.append(future.result())
            except Exception as exc:
                errors.append({'job':futuremap[future],'error':str(exc)});print('ERROR',futuremap[future],type(exc).__name__,flush=True)
    save(OUT/'errors.json',errors)
    summarize(cs,records)
    if errors:raise SystemExit(f'{len(errors)} jobs failed; rerun resumes saved successful calls')

if __name__=='__main__':main()
