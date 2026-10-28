#!/usr/bin/env python3
"""Evaluate Gold72 on the same maximum approved sentence defects as Hard66."""
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO))
from evaluation.scripts.campaigns.current import run_gold72_overnight as g
from evaluation.scripts.campaigns.current.run_hard66_grammar import verify_hashes
l=g.ladder
g.ROOT=REPO/'evaluation/runs/gold72_max_sentence_grammar_four_configs_2026-10-27'
g.METHODS=[('grammar','grammar/max_approved')]
GOLD=REPO/'evaluation/runs/gold72_four_configs_2026-10-27'
HARD=REPO/'evaluation/runs/hard66_grammar_sentence_all_mcq_qwen317b_nothink_2026-10-25'
def prepare():
 hard=l.read(HARD/'release.json')
 verify_hashes(HARD,hard['input_hashes'])
 methods={pid:method for _,_,pid,method in hard['cells']}
 stages=[]
 for model,think in g.CONFIGS:
  slug=model.replace(':','').replace('.','')+('_think' if think else '_nothink')
  root=g.ROOT/slug
  old=GOLD/slug
  release=l.read(old/'release.json');verify_hashes(old,release['input_hashes'])
  for path in (old/'_inputs').rglob('*'):
   if path.is_file():l.snapshot(path,root/path.relative_to(old))
  for pid in l.PASSAGES:
   for path in (old/pid/'_base/_shared').glob('*.json'):l.snapshot(path,root/path.relative_to(old))
   for name in l.ARTIFACTS+['grammar_metadata.json']:
    source=old/pid/'omission/0%'/name if name.startswith('qa_target') else HARD/pid/methods[pid]/name
    l.snapshot(source,root/pid/'grammar/max_approved'/name)
  manifest={**release,'source':str(HARD),'coverage':hard['coverage'],'coverage_definition':hard['coverage_definition'],
   'cells':[['grammar',model,pid,'grammar/max_approved'] for pid in l.PASSAGES], 'total_responses':release['questions_per_condition'],
   'input_hashes':{str(p.relative_to(root)):l.fingerprint(p) for p in root.rglob('*') if p.is_file() and (p.name in l.ARTIFACTS or p.name=='grammar_metadata.json' or '_inputs' in p.parts or '_shared' in p.parts)}}
  l.write_atomic(root/'release.json',manifest)
  stages.append({'root':str(root),'model':model,'thinking':think,'responses':manifest['total_responses']})
 plan={'stages':stages,'coverage':hard['coverage'],'total_responses':sum(s['responses'] for s in stages)}
 l.write_atomic(g.ROOT/'plan.json',plan)
 return plan
g.prepare=prepare
if __name__=='__main__':g.main()
