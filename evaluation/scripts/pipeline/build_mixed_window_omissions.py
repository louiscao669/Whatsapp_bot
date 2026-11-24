"""Fit and review a one-passage omission mixture from existing reviewed candidates."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from html import escape
from itertools import combinations
from pathlib import Path
from random import Random
import re

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from evaluation.scripts.pipeline import review_omission_clauses as review
from evaluation.scripts.pipeline.build_omission_phrase_bank import DATA, ROOT, clean_digest, english_by_passage
from evaluation.scripts.pipeline.build_prepared_window_conditions import Edit, render
from evaluation.scripts.pipeline.draw_window_omissions import band

KINDS = ('word', 'phrase', 'clause')
SHARES = dict(word=1, phrase=2, clause=2)  # Fifths, by selected deletion occurrences.
DOSES = (15, 30)
BANKS = (
    DATA/'perturbations/sol_scratch66_omission_word_bank_auto_v6.json',
    DATA/'perturbations/sol_scratch66_omission_phrase_bank_auto_v5.json',
    DATA/'perturbations/sol_scratch66_omission_clause_bank_auto_v2.json',
)
MANIFEST = DATA/'passages/sol_scratch66_windows_v1.json'


def points(e):
    return {(e['verse'], e['start']+i) for i,c in enumerate(e['before']) if review.mis.content_len(c)}


def load_candidates(manifest, banks, passage_id, sources):
    windows = deepcopy([w for w in manifest['windows'] if w['passage_id']==passage_id])
    if not windows:
        raise ValueError(f'No windows for {passage_id!r}')
    rejected_duplicates = []
    for w in windows:
        clean=w['conditions']['clean']['verses']; source=sources[passage_id]
        if any(source.chinese[v]!=t for v,t in clean.items()):
            raise ValueError('Clean source differs from the window')
        entries=defaultdict(list)
        for name,b in banks:
            if b['release']!=manifest['release']:
                raise ValueError('Candidate bank belongs to a different release')
            prior=next(x for x in b['windows'] if x['window_id']==w['id'])
            if prior['clean_zh_sha256']!=clean_digest(clean) or prior['english_sha256']!=source.english_sha256:
                raise ValueError('Stale bilingual candidate bank')
            w['reference']=prior['reference']
            for c in prior['candidates']:
                kind=c.get('unit_kind',b['unit'])
                # Word events must pass the dedicated, stricter word-level policy.
                if kind not in KINDS or (kind=='word' and b['unit']!='word'):
                    continue
                if 'edit' not in c:
                    continue
                e=c['edit']; v=e['verse']; start=e['start']
                if e['after'] or clean[v][start:start+len(e['before'])]!=e['before']:
                    raise ValueError('Candidate is not an exact deletion')
                entries[frozenset(points(e))].append(dict(edit=e,kind=kind,status=c['status'],
                    flags=c.get('flags',[]),bank=name,number=c['number']))
        pool=[]
        for footprint,rows in entries.items():
            accepted=[r for r in rows if r['status']=='accepted']
            if not accepted:
                continue
            if len({r['kind'] for r in rows})!=1 or any(r['status']!='accepted' for r in rows):
                rejected_duplicates.append(dict(window_id=w['id'],reason='conflicting_reviews',sources=rows))
                continue
            # Prefer the phrase bank for phrases, the clause bank for clauses.
            row=min(accepted,key=lambda r: (r['kind'] not in r['bank'],r['bank']))
            e=row['edit']; cid=sha256(repr(sorted(footprint)).encode()).hexdigest()[:16]
            pool.append(dict(id=cid,kind=row['kind'],edit=e,chars=len(footprint),
                flags=sorted({f for r in rows for f in r['flags']}),provenance=rows))
        w['candidates']=sorted(pool,key=lambda c:(c['edit']['verse'],c['edit']['start'],c['edit']['before']))
        w['clean']=clean
    return windows,rejected_duplicates


class Model:
    def __init__(self):
        self.upper=[];self.rows=[];self.low=[];self.high=[]
    def var(self,upper=1):
        self.upper.append(upper);return len(self.upper)-1
    def constrain(self,terms,low=-np.inf,high=np.inf):
        self.rows.append(terms);self.low.append(low);self.high.append(high)
    def solve(self,cost):
        rs=[];cs=[];vs=[]
        for i,row in enumerate(self.rows):
            for j,v in row.items():rs.append(i);cs.append(j);vs.append(v)
        matrix=coo_matrix((vs,(rs,cs)),shape=(len(self.rows),len(self.upper))).tocsc()
        objective=np.zeros(len(self.upper))
        for i,v in cost.items():objective[i]=v
        result=milp(objective,integrality=np.ones(len(self.upper)),
            bounds=Bounds(np.zeros(len(self.upper)),self.upper),
            constraints=LinearConstraint(matrix,self.low,self.high),options={'mip_rel_gap':0,'time_limit':60})
        if result.status==2:return None
        if not result.success:raise RuntimeError(f'Mixture optimization did not finish: {result.message}')
        return np.rint(result.x).astype(int)
    def feasible_with(self,terms):
        self.constrain(terms,0,0)
        try:return self.solve({}) is not None
        finally:self.rows.pop();self.low.pop();self.high.pop()
    def minimize_and_fix(self,cost):
        solution=self.solve(cost)
        if solution is None:raise ValueError('No nested, in-band combination satisfies the current constraints')
        value=sum(v*solution[i] for i,v in cost.items())
        self.constrain(cost,value,value)
        return int(value)


def fit(windows,seed,tolerance=2,fixed=None,banned=()):
    model=Model();variables={};mix_errors={};dose_errors={};match_cost={}
    for w in windows:
        clean=w['clean'];pool=w['candidates'];total=w['clean_content_chars']
        conflicts=[(a,b) for a,b in combinations(range(len(pool)),2)
            if pool[a]['edit']['verse']==pool[b]['edit']['verse']
            and max(pool[a]['edit']['start'],pool[b]['edit']['start']) < min(
                pool[a]['edit']['start']+len(pool[a]['edit']['before']),
                pool[b]['edit']['start']+len(pool[b]['edit']['before']))]
        for dose in DOSES:
            key=(w['id'],dose);ids={c['id']:model.var() for c in pool};variables[key]=ids
            lo,hi=band(total,dose,tolerance)
            model.constrain({ids[c['id']]:c['chars'] for c in pool},lo,hi)
            for a,b in conflicts:model.constrain({ids[pool[a]['id']]:1,ids[pool[b]['id']]:1},high=1)
            for v,text in clean.items():
                model.constrain({ids[c['id']]:c['chars'] for c in pool if c['edit']['verse']==v},
                    high=review.mis.content_len(text)-1)
            if dose==30:
                for cid,var in ids.items():model.constrain({variables[(w['id'],15)][cid]:1,var:-1},high=0)
            if fixed and key in fixed:
                for cid,var in ids.items():
                    value=int(cid in fixed[key]);model.constrain({var:1},value,value)
            for bad_key,bad_ids in banned:
                if bad_key==key:
                    model.constrain({var:(1 if cid in bad_ids else -1) for cid,var in ids.items()},high=len(bad_ids)-1)
            err=model.var(100*total);dose_errors[err]=1
            for sign in (1,-1):
                model.constrain({**{ids[c['id']]:sign*100*c['chars'] for c in pool},err:-1},
                    high=sign*dose*total)
            # Prefer matching the clauses touched by the fixed comparison variants.
            refs=['mistranslation15'] if dose==15 else ['mistranslation30','grammar30']
            for clause in review.candidate_spans(clean):
                cp=points(clause);touch=[ids[c['id']] for c in pool if points(c['edit']) & cp]
                if not touch:continue
                mark=model.var()
                for var in touch:model.constrain({var:1,mark:-1},high=0)
                model.constrain({**dict.fromkeys(touch,-1),mark:1},high=0)
                weight=0
                for ref in refs:
                    if ref in w['conditions']:
                        touched=any(points(e)&cp for e in w['conditions'][ref]['edits'])
                        weight+=-1 if touched else 1
                match_cost[mark]=weight
    for dose in DOSES:
        errors={}
        for kind,target in SHARES.items():
            delta={variables[(w['id'],dose)][c['id']]:(5*int(c['kind']==kind)-target)
                   for w in windows for c in w['candidates']}
            err=model.var(5*sum(len(w['candidates']) for w in windows));errors[err]=1
            for sign in (1,-1):model.constrain({**{i:sign*v for i,v in delta.items()},err:-1},high=0)
        mix_errors[dose]=errors
    all_errors={i:1 for group in mix_errors.values() for i in group}
    if model.solve({}) is None:
        raise ValueError('No nested, in-band combination satisfies the current constraints')
    exact=dict(joint=model.feasible_with(all_errors),
               by_dose={str(d):model.feasible_with(mix_errors[d]) for d in DOSES})
    # Each stage is fixed before the next. This is a seeded tie-break, not uniform sampling.
    objectives=dict(mixture_count_deviation=model.minimize_and_fix(all_errors),
        fixed_condition_clause_disagreement=model.minimize_and_fix(match_cost),
        dose_center_deviation=model.minimize_and_fix(dose_errors))
    rng=Random(seed);solution=model.solve({v:rng.uniform(-1,1) for ids in variables.values() for v in ids.values()})
    chosen={key:[cid for cid,var in ids.items() if solution[var]] for key,ids in variables.items()}
    return chosen,dict(exact_ratio_feasible=exact,objectives=objectives,
        priority=['dose bands, nonoverlap, nesting, verse preservation',
                  'absolute event-count deviation from 20/40/40 at each dose',
                  'agreement with fixed comparison clause locations','distance from dose centers','seeded tie-break'])


def punctuation_only_cleanup(text):
    """Delete orphan/repeated punctuation; never add characters or rewrite words."""
    before=text
    for _ in range(3):
        text=re.sub(r'^[，；：,;:]+','',text)
        text=re.sub(r'([“‘「『])[，；：,;:]+',r'\1',text)
        text=re.sub(r'[，；：,;:]+([。！？.!?])',r'\1',text)
        text=re.sub(r'([。！？.!?])[，；：,;:]+',r'\1',text)
        text=re.sub(r'([，；：,;:。！？.!?])\1+',r'\1',text)
        text=re.sub(r'“[，；：,;:。！？.!?\s]*”|‘[，；：,;:。！？.!?\s]*’','',text)
    if review.CONTENT_CHAR_PATTERN.findall(before)!=review.CONTENT_CHAR_PATTERN.findall(text):
        raise ValueError('Punctuation cleanup altered lexical content')
    return text


def materialize(w,ids,dose):
    selected=[c for c in w['candidates'] if c['id'] in ids]
    raw=render(w['clean'],[Edit(**c['edit']) for c in selected])
    verses={v:punctuation_only_cleanup(t) for v,t in raw.items()}
    deleted=sum(c['chars'] for c in selected);total=w['clean_content_chars']
    if total-sum(map(review.mis.content_len,verses.values()))!=deleted:
        raise ValueError('Rendered dose disagrees with selected deletions')
    return dict(target_percent=dose,actual_percent=100*deleted/total,deleted_chars=deleted,
        selected_ids=ids,selected=selected,unit_counts=dict(Counter(c['kind'] for c in selected)),
        verses=verses,punctuation_cleanup=[dict(verse=v,before=raw[v],after=t) for v,t in verses.items() if t!=raw[v]],
        status='pending_combined_review')


COMBINED_REVIEW = """Review complete Chinese Bible windows after multiple omission edits were combined.
Each numbered variant is independent. Read its full original English, clean Chinese and exact edited
Chinese. No QA, answer key, prior verdict or desired mix is supplied. Do not infer an answer target.
For each variant return five yes/no/uncertain checks:
information_omitted: concrete source information is lost; ordinary ellipsis preserving the same fact
does not establish loss. Distinguish an implicit local object from a distinct deleted assertion.
key_content_removed: the omissions remove substantive actors, places, events, relationships,
instructions, conditions or outcomes. Minor decorative details or discourse markers alone do not qualify.
fluent: the ENTIRE edited window remains natural and grammatical. Individually valid deletions can
combine into a broken construction, dangling complement, contradictory connective, or orphaned
quotation attribution. Judge the supplied punctuation, not an imagined repair. Normal Chinese
implicit subjects are allowed. For failure quote the exact resulting construction and explain why.
deletion_only: only listed source spans and documented punctuation were deleted; no lexical additions,
substitutions or reordering. The program verifies this mechanically.
valid_in_context: lost content and the interpretation of retained wording are supported by the full
bilingual window. Do not use outside Bible knowledge. Removing information may broaden a claim or
change apparent actors, scope or causal logic; this is a NONBLOCKING semantic-distortion flag, not
by itself a failure. Grammatical failure still fails fluent. Recoverability elsewhere is a flag.
Use flags recoverable_from_context, ambiguous_reference, other_meaning_changed or
possible_other_meaning_changed as applicable. Explain lost information and every flag or failure.
All five yes => pass; any no => reject; otherwise uncertain => held. Do not rewrite any text.
Assess the full combined result, not merely whether each deletion passed separately."""


class CombinedDecision(BaseModel):
    number:int
    checks:review.ClauseChecks
    flags:list[str]
    reason:str


class CombinedDecisions(BaseModel):
    decisions:list[CombinedDecision]


def review_window(client,w,cells,source,folder):
    todo={d:c for d,c in cells.items() if c['status']=='pending_combined_review'}
    if not todo:return cells
    payload=dict(window={v:dict(english=source.english[v],chinese=t) for v,t in w['clean'].items()},
        variants=[dict(number=d,edited_chinese=c['verses'],deletions=[x['edit'] for x in c['selected']],
            punctuation_cleanup=c['punctuation_cleanup']) for d,c in todo.items()])
    result=review.ask(client,folder/sha256(w['id'].encode()).hexdigest()[:20],'combined-review',review.JUDGE,
        COMBINED_REVIEW,payload,CombinedDecisions,lambda x:review.validate_reviews(x,list(todo)))
    for decision in result.decisions:
        cell=cells[decision.number];checks=decision.checks.model_dump();checks['deletion_only']='yes'
        cell.update(review=decision.model_dump(),checks=checks,flags=decision.flags,
            status='rejected' if 'no' in checks.values() else 'held' if 'uncertain' in checks.values()
                else 'pass_with_flags' if decision.flags else 'pass')
    return cells


def mixture_summary(windows,cells):
    result={}
    for dose in DOSES:
        counts=Counter();chars=Counter();statuses=Counter()
        for w in windows:
            c=cells[w['id']][dose];counts.update(c['unit_counts']);statuses[c['status']]+=1
            for e in c['selected']:chars[e['kind']]+=e['chars']
        n=sum(counts.values())
        result[str(dose)]=dict(occurrences={k:counts[k] for k in KINDS},total_occurrences=n,
            percentages={k:100*counts[k]/n if n else 0 for k in KINDS},
            deleted_characters={k:chars[k] for k in KINDS},statuses=dict(statuses))
    return result


def report_html(result):
    labels=dict(pass_with_flags='Pass with flags',passed='Pass',rejected='Rejected',held='Held',
                pending_combined_review='Awaiting combined review')
    labels['pass']='Pass'
    def counts_text(counts):
        return ', '.join(f'{labels.get(k,k)}: {n}' for k,n in counts.items())
    title=result.get('passage_title') or result['rounds'][-1]['windows'][0]['reference'].split(':')[0]
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>One-passage omission mixture</title><style>body{font:16px/1.65 system-ui;max-width:1150px;margin:2rem auto;padding:0 1rem;color:#18343b}table{border-collapse:collapse;width:100%}th,td{padding:.55rem;border:1px solid #d2dfe0;text-align:left}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.cell{padding:1rem;background:#f2f6f5;border-radius:8px}.text{font-size:1.1rem}del{background:#ffe2d9;color:#8a3022}small{color:#53656b}details{margin:1rem 0}li{margin:.3rem 0}@media(max-width:750px){.grid{grid-template-columns:1fr}}</style>',
        '<h1>'+escape(title)+' · Trial omission mixture</h1>',
        '<p>Local draft. Target mix: 20% word, 40% phrase, 40% clause by deletion occurrences, separately at each dose. '
        'Each window targets 15% or 30% of clean content characters, within ±2 percentage points. '
        '15% selections are contained in 30%. No questions, answer keys or participant data went to the reviewer.</p>',
        '<p>Word candidates must pass the dedicated word-level criteria. Other accepted candidates use their reviewed unit classification. '
        'Overlapping deletions cannot be counted twice. Adjacent separately reviewed units count as separate occurrences.</p>']
    latest=result['rounds'][-1]
    parts.append('<h2>Achieved mix</h2><table><tr><th>Dose</th><th>Word</th><th>Phrase</th><th>Clause</th><th>Combined review</th></tr>')
    for d,s in latest['mixture'].items():
        parts.append('<tr><td>'+d+'%</td>'+''.join(f'<td>{s["occurrences"][k]} ({s["percentages"][k]:.1f}%)</td>' for k in KINDS)
            +'<td>'+escape(counts_text(s['statuses']))+'</td></tr>')
    exact=latest['fit']['exact_ratio_feasible']
    feasibility=', '.join(f'{d}% dose: {"yes" if value else "no"}' for d,value in exact['by_dose'].items())
    parts.append('</table><p>Exact 20/40/40 feasibility under these constraints: '+escape(feasibility)+
        f'; both doses together: {"yes" if exact["joint"] else "no"}. '
        'Selection first minimizes absolute event-count deviation, then favors existing cross-defect clause locations, '
        'then dose centers. Seeded tie-breaking is not uniform sampling.</p>')
    parts.append('<p>The mix above counts deletion occurrences. Character contributions differ because units have different lengths.</p>'
        '<table><tr><th>Dose</th><th>Characters removed by word edits</th><th>By phrase edits</th><th>By clause edits</th></tr>')
    for d,s in latest['mixture'].items():
        total=sum(s['deleted_characters'].values())
        parts.append('<tr><td>'+d+'%</td>'+''.join(f'<td>{s["deleted_characters"][k]} '
            f'({100*s["deleted_characters"][k]/total:.1f}%)</td>' for k in KINDS)+'</tr>')
    parts.append('</table>')
    if result.get('stop_reason'):parts.append('<p>'+escape(result['stop_reason'])+'</p>')
    parts.append('<p>Review rounds: '+str(len(result['rounds']))+'. Passing combinations are kept fixed during one optional redraw of failures. '
        'A numeric dose fit alone is not a semantic approval.</p>')
    for w in latest['windows']:
        parts.append('<h2>'+escape(w['reference'])+'</h2><details><summary>Clean Chinese and English</summary>')
        for v,t in w['clean'].items():parts.append(f'<p>{escape(v)}　{escape(t)}</p><p><small>{escape(w["english"][v])}</small></p>')
        parts.append('</details><div class="grid">')
        for dose,cell in w['conditions'].items():
            parts.append(f'<article class="cell"><h3>{dose}% target · {cell["actual_percent"]:.1f}% achieved</h3>'
                f'<p>{escape(labels.get(cell["status"],cell["status"]))} · '+
                escape(', '.join(f'{kind}: {cell["unit_counts"].get(kind,0)}' for kind in KINDS))+'</p>')
            for v,t in cell['verses'].items():parts.append(f'<p class="text">{escape(v)}　{escape(t)}</p>')
            if 'review' in cell:parts.append('<p>'+escape(cell['review']['reason'])+'</p><p><small>'+escape(str(cell['checks']))+'</small></p>')
            if cell.get('flags'):parts.append('<p>Flags: '+escape(', '.join(cell['flags']))+'</p>')
            parts.append('<details><summary>Deleted units and original wording</summary><ul>')
            for c in cell['selected']:parts.append('<li>'+escape(c['kind'])+' · '+escape(c['edit']['verse'])+' · <del>'+escape(c['edit']['before'])+'</del></li>')
            parts.append('</ul>')
            for v,t in w['clean'].items():
                cursor=0;pieces=[]
                for c in sorted((c for c in cell['selected'] if c['edit']['verse']==v),key=lambda c:c['edit']['start']):
                    e=c['edit'];pieces.extend([escape(t[cursor:e['start']]),'<del>'+escape(e['before'])+'</del>']);cursor=e['start']+len(e['before'])
                pieces.append(escape(t[cursor:]));parts.append('<p>'+escape(v)+'　'+''.join(pieces)+'</p>')
            if cell['punctuation_cleanup']:parts.append('<p>Punctuation-only deletions: '+escape(str(cell['punctuation_cleanup']))+'</p>')
            parts.append('</details></article>')
        parts.append('</div>')
    return ''.join(parts)+'</html>'


def run(passage_id,out,report,cache,seed=20261118,with_review=False,max_rounds=2):
    manifest=review.read(MANIFEST);sources=english_by_passage()
    banks=[(p.name,review.read(p)) for p in BANKS]
    windows,conflicts=load_candidates(manifest,banks,passage_id,sources)
    result=dict(passage_id=passage_id,
        passage_title=f'{sources[passage_id].book} {next(iter(windows[0]["clean"]))}–{list(windows[-1]["clean"])[-1]}',
        seed=seed,target_mix=SHARES,mixture_denominator=5,
        dose_tolerance_percentage_points=2,manifest_sha256=clean_digest(manifest),
        bank_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in BANKS},
        excluded_conflicting_candidates=conflicts,rounds=[],published=False)
    previous={};fixed={};banned=[]
    def save_result():
        review.save(out,result);report.parent.mkdir(parents=True,exist_ok=True);report.write_text(report_html(result))
    for iteration in range(max_rounds if with_review else 1):
        try:chosen,fit_info=fit(windows,seed+iteration,fixed=fixed,banned=banned)
        except ValueError as exc:
            if not result['rounds']:raise
            result['stop_reason']=str(exc);save_result();break
        cells={w['id']:{d:(deepcopy(previous[(w['id'],d)]) if (w['id'],d) in fixed else
            materialize(w,chosen[(w['id'],d)],d)) for d in DOSES} for w in windows}
        record=dict(round=iteration+1,fit=fit_info,mixture=mixture_summary(windows,cells),windows=[])
        def update_record():
            record['mixture']=mixture_summary(windows,cells)
            record['windows']=[dict(id=w['id'],reference=w['reference'],clean=w['clean'],
                english={v:sources[passage_id].english[v] for v in w['clean']},
                conditions={str(d):cells[w['id']][d] for d in DOSES}) for w in windows]
        update_record();result['rounds'].append(record);save_result()
        print(f'Round {iteration+1}: {record["mixture"]}; exact fit: {fit_info["exact_ratio_feasible"]}',flush=True)
        if not with_review:break
        load_dotenv(ROOT/'.env')
        with OpenAI(timeout=150,max_retries=3) as client:
            jobs=[w for w in windows if any(c['status']=='pending_combined_review' for c in cells[w['id']].values())]
            if jobs:
                w=jobs[0];cells[w['id']]=review_window(client,w,cells[w['id']],sources[passage_id],cache)
                update_record();save_result();print(w['reference'],{d:c['status'] for d,c in cells[w['id']].items()},flush=True)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[(w,pool.submit(review_window,client,w,cells[w['id']],sources[passage_id],cache)) for w in jobs[1:]]
                for w,future in futures:
                    cells[w['id']]=future.result();update_record();save_result()
                    print(w['reference'],{d:c['status'] for d,c in cells[w['id']].items()},flush=True)
        failures=0
        for w in windows:
            for d,cell in cells[w['id']].items():
                key=(w['id'],d);previous[key]=cell
                if cell['status'] in ('pass','pass_with_flags'):fixed[key]=cell['selected_ids']
                else:failures+=1;banned.append((key,cell['selected_ids']))
        if not failures:break
    return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--passage-id',required=True)
    cli.add_argument('--seed',type=int,default=20261118)
    cli.add_argument('--review',action='store_true')
    cli.add_argument('--max-rounds',type=int,choices=(1,2),default=2)
    cli.add_argument('--output',type=Path)
    cli.add_argument('--report',type=Path)
    cli.add_argument('--cache',type=Path,default=ROOT/'evaluation/runs/sol_omission_mix_204040_2026-11-18/reviews')
    args=cli.parse_args();name='sol_omission_mix_204040_'+args.passage_id
    out=args.output or ROOT/'evaluation/runs/sol_omission_mix_204040_2026-11-18'/args.passage_id/'mixture.json'
    report=args.report or ROOT/'deliverables'/(name+'.html')
    run(args.passage_id,out,report,args.cache,args.seed,args.review,args.max_rounds)


if __name__=='__main__':main()
