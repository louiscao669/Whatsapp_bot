import csv,json,os,time
from pathlib import Path
os.environ['MPLCONFIGDIR']='/tmp/gold72-matplotlib'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
REPO=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
RUNS=REPO/'evaluation/runs'
ROOT=RUNS/'gold72_max_sentence_grammar_four_configs_2026-10-27'
MODELS=[('llama321b_nothink','llama321b','Llama 3.2 1B'),('qwen2515b_nothink','qwen2515b','Qwen 2.5 1.5B'),('qwen317b_think','qwen317b','Qwen3 1.7B · thinking'),('qwen317b_nothink',None,'Qwen3 1.7B · no thinking')]
def build():
 with (OUT/'accuracy_percentages.csv').open() as f:data=list(csv.DictReader(f))
 fig,axes=plt.subplots(4,2,figsize=(12,13),gridspec_kw={'width_ratios':[2,1]},sharey=True)
 records=[]
 for i,(slug,hard_slug,label) in enumerate(MODELS):
  p=ROOT/slug/'results_summary.json'
  gold=json.loads(p.read_text())['conditions'][0] if p.exists() else None
  hardpath=RUNS/'hard66_grammar_sentence_all_mcq_models_2026-10-25'/hard_slug/'results_summary.json' if hard_slug else RUNS/'hard66_grammar_sentence_all_mcq_qwen317b_nothink_2026-10-25/results_summary.json'
  hard=json.loads(hardpath.read_text())
  for j,dataset in enumerate(['Gold72','Hard66']):
   color=['#1769aa','#d46822'][j]
   rs=[r for r in data if r['model']==label and r['dataset']==dataset and (r['family']=='grammar' or (r['family']=='omission' and r['defect_percent']=='0'))]
   rs.sort(key=lambda r:int(r['defect_percent']))
   axes[i,0].plot([int(r['defect_percent']) for r in rs],[float(r['accuracy_percent']) for r in rs],color=color,marker='o' if j==0 else 's',linestyle='-' if j==0 else '--')
   r=gold if j==0 else hard
   if r:
    n=r.get('n',r.get('total'));correct=r['correct'];pct=100*correct/n
    axes[i,1].bar(j,pct,color=color,width=.55)
    axes[i,1].text(j,pct+2,f'{pct:.1f}%\n({correct}/{n})',ha='center',fontsize=10)
    records.append({'model':label,'dataset':dataset,'correct':correct,'n':n,'accuracy_percent':pct,'sentence_coverage_percent':100*345/358})
   else:axes[i,1].text(j,15,'Running',ha='center',color=color)
  for ax in axes[i]:
   ax.set_ylim(0,108);ax.set_yticks([0,25,50,75,100]);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.spines[['top','right']].set_visible(False)
  axes[i,0].set_xticks([0,5,10,15,20,25,30]);axes[i,0].set_ylabel(label+'\nAccuracy (%)')
  axes[i,1].set_xticks([0,1],['Gold72','Hard66']);axes[i,1].set_xlim(-.6,1.6)
 axes[0,0].set_title('Grammar gradient: 0–30% nominal dose',fontweight='bold')
 axes[0,1].set_title('Maximum sentence defects\n96.4% sentence coverage',fontweight='bold')
 axes[-1,0].set_xlabel('Nominal grammar defect level (%)')
 fig.suptitle('Gold72 vs Hard66 · grammar including maximum coverage',fontsize=17,fontweight='bold',y=.985)
 fig.legend(handles=[Line2D([0],[0],color=c,label=d,linestyle=s,marker=m) for d,c,s,m in [('Gold72','#1769aa','-','o'),('Hard66','#d46822','--','s')]],loc='upper center',bbox_to_anchor=(.5,.96),ncol=2,frameon=False)
 fig.text(.08,.025,'The “100%” sentence run contains approved defects in 345/358 sentences (96.4%); 13 remain unchanged.\nSentence coverage differs from the 0–30% dose metric, so the maximum point is shown separately.\nGold72: 71 MCQs; Hard66: 65 MCQs. Maximum-coverage passages are identical across the two sets.',fontsize=9,color='#555555')
 fig.tight_layout(rect=[.02,.085,.99,.93],h_pad=2)
 fig.savefig(OUT/'grammar_with_max_coverage.png',dpi=180);fig.savefig(OUT/'grammar_with_max_coverage.pdf');plt.close(fig)
 with (OUT/'grammar_max_coverage_percentages.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
 return records
if __name__=='__main__':
 import sys
 if '--wait' in sys.argv:
  while True:
   p=ROOT/'job.json'
   job=json.loads(p.read_text()) if p.exists() else {}
   if job.get('status') in ['complete','failed']:break
   time.sleep(20)
 print(json.dumps(build()))
