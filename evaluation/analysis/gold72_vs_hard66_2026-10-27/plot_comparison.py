import csv,json,os
from pathlib import Path
os.environ['MPLCONFIGDIR']='/tmp/gold72-matplotlib'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
REPO=Path(__file__).resolve().parents[3]
RUNS=REPO/'evaluation/runs'
OUT=Path(__file__).parent
models=[('llama321b_nothink','llama321b_think','Llama 3.2 1B'),('qwen2515b_nothink','qwen2515b_think','Qwen 2.5 1.5B'),('qwen317b_think','qwen317b_think','Qwen3 1.7B · thinking'),('qwen317b_nothink','qwen317b_nothink','Qwen3 1.7B · no thinking')]
rows=[]
def add(dataset,model,condition,correct,n,source,errors=0):
 family,rate=('wbw',None) if condition=='google_word_by_word' else condition.split('/')
 rate=None if rate is None else int(rate.rstrip('%'))
 rows.append(dict(dataset=dataset,model=model,family=family,defect_percent=rate,correct=correct,n=n,accuracy_percent=100*correct/n,generation_errors=errors,source=str(source.relative_to(REPO))))
for slug,hard_slug,label in models:
 p=RUNS/'gold72_four_configs_2026-10-27'/slug/'results_summary.json'
 for r in json.loads(p.read_text())['conditions']:add('Gold72',label,r['condition'],r['correct'],r['n'],p,r['generation_errors'])
 if slug=='qwen317b_nothink':
  for family in ['omission','mistranslation','grammar','google_word_by_word']:
   p=RUNS/f'hard66_{family}_mcq_qwen317b_nothink_2026-10-26/results_summary.json'
   for r in json.loads(p.read_text())['levels']:
    condition=r.get('condition')
    if condition=='clean':condition='omission/0%'
    if condition is None:condition=f"{family}/{r[f'nominal_{family}_percent']}%"
    if condition.endswith('/0%') and family!='omission':continue
    add('Hard66',label,condition,r['correct'],r['n'],p,r['generation_errors'])
 else:
  for run,families in [('hard66_full_ladder_2026-10-23',['omission','mistranslation','wbw']),('hard66_grammar_full_2026-10-24',['grammar'])]:
   root=RUNS/run
   state=json.loads((root/'campaign_state.json').read_text())
   groups={}
   for key,cell in state['cells'].items():
    stage,model,pid,method=key.split('/',3)
    expected=hard_slug.removesuffix('_think')
    if model.replace(':','').replace('.','')!=expected or cell['status']!='complete':continue
    if stage not in families and stage!='clean':continue
    p=root/pid/hard_slug/method/'scores_target_llama.json'
    data=json.loads(p.read_text()); data=data['items'] if isinstance(data,dict) else data
    groups.setdefault(method,[]).extend(r for r in data if r['q_type']=='mcq')
   for method,items in groups.items():add('Hard66',label,method,sum(bool(r['direct_correct']) for r in items),len(items),root)
with (OUT/'accuracy_percentages.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
fig,axes=plt.subplots(4,4,figsize=(16,12),sharey=True)
colors={'Gold72':'#1769aa','Hard66':'#d46822'}
for i,(_,_,label) in enumerate(models):
 for j,family in enumerate(['omission','mistranslation','grammar','wbw']):
  ax=axes[i,j]
  for dataset in ['Gold72','Hard66']:
   base=next(r for r in rows if r['dataset']==dataset and r['model']==label and r['family']=='omission' and r['defect_percent']==0)
   vals=[r for r in rows if r['dataset']==dataset and r['model']==label and r['family']==family and (r['defect_percent'] or family=='wbw')]
   vals=sorted(vals,key=lambda r:r['defect_percent'] or 0)
   vals=[base]+vals
   x=[0,1] if family=='wbw' else [0]+[r['defect_percent'] for r in vals[1:]]
   y=[r['accuracy_percent'] for r in vals]
   assert len(x)==len(y)
   ax.plot(x,y,color=colors[dataset],linestyle='-' if dataset=='Gold72' else '--',marker='o' if dataset=='Gold72' else 's',markersize=4,linewidth=1.8)
   ax.annotate(f'{y[-1]:.1f}%',(x[-1],y[-1]),xytext=(-3,7 if dataset=='Gold72' else -13),textcoords='offset points',ha='right',fontsize=8,color=colors[dataset])
  ax.set_ylim(0,105);ax.set_yticks([0,25,50,75,100]);ax.grid(alpha=.2)
  ax.spines[['top','right']].set_visible(False)
  if family=='wbw':ax.set_xticks([0,1],['Clean','WBW']);ax.set_xlim(-.15,1.15)
  else:ax.set_xticks([0,5,10,15,20,25,30]);ax.set_xlim(-1,32)
  if i==0:ax.set_title({'wbw':'Word by word'}.get(family,family.title()),fontsize=13,fontweight='bold')
  if j==0:ax.set_ylabel(label+'\nAccuracy (%)',fontsize=10)
  if i==3 and family!='wbw':ax.set_xlabel('Nominal defect level (%)')
fig.suptitle('Gold72 and Hard66 · MCQ accuracy across defect levels',fontsize=19,fontweight='bold',y=.985)
fig.legend(handles=[Line2D([0],[0],color=colors[d],linestyle='-' if d=='Gold72' else '--',marker='o' if d=='Gold72' else 's',label=d+(' (71 MCQs)' if d=='Gold72' else ' (65 MCQs)')) for d in colors],loc='upper center',bbox_to_anchor=(.5,.956),ncol=2,frameon=False)
fig.text(.06,.025,'Separate question sets; curves compare trends, not paired item effects. Hard66 grammar uses a later variant bank.\n0% is the common clean baseline. WBW is a separate condition, not a percentage dose. One Gold72 thinking-mode response had a generation error.',fontsize=10,color='#555555')
fig.tight_layout(rect=[.02,.07,.99,.92],h_pad=1.5)
fig.savefig(OUT/'accuracy_gradients.png',dpi=180)
fig.savefig(OUT/'accuracy_gradients.pdf')
lines=['# Gold72 vs Hard66 accuracy percentages','', 'Gold72: 71 MCQs per condition. Hard66: 65 MCQs per condition.','', 'Hard66 grammar uses a later variant bank; comparisons are descriptive across different question sets.','']
for _,_,model in models:
 lines += ['## '+model,'','| Condition | Gold72 | Hard66 |','|---|---:|---:|']
 for family in ['omission','mistranslation','grammar','wbw']:
  rates=[None] if family=='wbw' else ([0,5,10,15,20,25,30] if family=='omission' else [5,10,15,20,25,30])
  for rate in rates:
   cells=[next(r for r in rows if r['dataset']==d and r['model']==model and r['family']==family and r['defect_percent']==rate) for d in ['Gold72','Hard66']]
   name='WBW' if family=='wbw' else 'Clean' if rate==0 else f'{family.title()} {rate}%'
   lines.append(f"| {name} | {cells[0]['accuracy_percent']:.1f}% | {cells[1]['accuracy_percent']:.1f}% |")
 lines.append('')
(OUT/'accuracy_tables.md').write_text('\n'.join(lines))
print('Created PNG, PDF, CSV, and percentage tables; data rows:',len(rows))
