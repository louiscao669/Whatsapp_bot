#!/usr/bin/env python3
"""Plot observed Hard66 MCQ outcomes, separating E from wrong A–D answers."""
from pathlib import Path
import json
import os
import zipfile

REPO=Path(__file__).resolve().parents[3]
REPORT=REPO/'evaluation/reports/qa_rewrite_model_results_2026-10-27'
OUT=REPORT/'individual_charts/e_separated'
OUT.mkdir(parents=True,exist_ok=True)
os.environ['MPLCONFIGDIR']=str(REPORT/'.matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from matplotlib.patches import Patch

MODELS=[('llama321b','Llama 3.2 1B'),('qwen2515b','Qwen 2.5 1.5B'),
        ('qwen317b_think','Qwen3 1.7B · thinking'),('qwen317b_nothink','Qwen3 1.7B · no thinking')]
CATEGORIES=[('mcq_correct','Correct A–D','#269275'),
            ('mcq_incorrect_ad_count','Incorrect A–D','#D98838'),
            ('mcq_e_count','E: cannot tell','#8575BE'),
            ('mcq_unresolved_count','No valid answer','#AAB3BD')]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'svg.fonttype':'none',
                     'axes.spines.top':False,'axes.spines.right':False,'text.color':'#172B3B',
                     'axes.labelcolor':'#405364','xtick.color':'#405364','ytick.color':'#405364'})


def main():
    data=json.loads((REPORT/'results_data.json').read_text())
    rows={(r['config'],r['condition']):r['after'] for r in data['conditions'] if r['dataset']=='hard'}
    audit=[];files=[]
    for family,title in [('grammar','Grammar'),('mistranslation','Mistranslation'),('omission','Omission'),('word_by_word','Word-by-word translation')]:
        fig,axes=plt.subplots(2,2,figsize=(14,9),sharey=True)
        fig.subplots_adjust(left=.075,right=.98,top=.79,bottom=.19,hspace=.50,wspace=.16)
        fig.text(.075,.94,'Hard66 · '+title,fontsize=25,weight='bold')
        fig.text(.075,.885,'E responses shown separately · updated results · each bar totals 100%',fontsize=14,color='#526578')
        if family=='word_by_word':
            methods=['omission/0%','google_word_by_word'];xs=[0,1];labels=['Clean','Word-by-word']
        else:
            methods=['omission/0%']+[f'{family}/{n}%' for n in (5,10,15,20,25,30)]
            xs=list(range(7));labels=['0','5','10','15','20','25','30']
            if family=='grammar':methods+=['grammar/max_approved'];xs+=[8];labels+=['Max*']
        for ax,(config,name) in zip(axes.flat,MODELS):
            values=[rows[config,m] for m in methods]
            for method,v in zip(methods,values):
                assert sum(v[k] for k,_,_ in CATEGORIES)==v['mcq_n']
                assert v['mcq_n']==(57 if method=='grammar/max_approved' else 65)
                audit.append({'family':family,'config':config,'condition':method,'n':v['mcq_n'],**{k:v[k] for k,_,_ in CATEGORIES}})
            bottom=[0.0]*len(methods)
            width=.48 if family=='word_by_word' else .72
            for key,label,color in CATEGORIES:
                heights=[v[key]/v['mcq_n'] for v in values]
                ax.bar(xs,heights,bottom=bottom,width=width,color=color,edgecolor='white',linewidth=.6,zorder=3)
                for x,h,b,v in zip(xs,heights,bottom,values):
                    if h>=.08:
                        ax.text(x,b+h/2,f'{h:.0%}',ha='center',va='center',fontsize=10.5,color='white' if key in ('mcq_correct','mcq_e_count') else '#172b3b',weight='bold')
                bottom=[b+h for b,h in zip(bottom,heights)]
            ax.set_title(name,loc='left',fontsize=14,pad=12,weight='bold')
            ax.set_xticks(xs,labels)
            if family!='word_by_word':ax.set_xlabel('Defect level (%)',labelpad=6)
            else:ax.set_xlim(-.6,1.6)
            ax.set_ylim(0,1.04);ax.set_yticks([0,.25,.5,.75,1]);ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=0))
            ax.grid(axis='y',color='#E1E7ED',zorder=0);ax.spines['left'].set_color('#B9C5CF');ax.spines['bottom'].set_color('#B9C5CF')
            if family=='grammar':
                ax.axvline(7,color='#B9C5CF',linestyle=':',linewidth=1)
        axes[0,0].set_ylabel('Share of all MCQ responses');axes[1,0].set_ylabel('Share of all MCQ responses')
        fig.legend(handles=[Patch(facecolor=c,label=label) for _,label,c in CATEGORIES],loc='lower center',bbox_to_anchor=(.53,.085),ncol=4,frameon=False,fontsize=12)
        fig.text(.075,.055,'65 active MCQs per condition. E = “cannot tell from the passage.” Counts use the original answer logs.',fontsize=11,color='#526578')
        if family=='grammar':
            fig.text(.075,.023,'*Max: approved sentence defects; original 8-passage subset of 57 MCQs. Shown separately from the 0–30% series.',fontsize=10.5,color='#526578')
        else:
            fig.text(.075,.023,'Percentages inside bars are rounded; small segments are left unlabeled. No valid answer is separate from E.',fontsize=10.5,color='#526578')
        for ext in ('png','svg'):
            path=OUT/f'hard66_{family}_e_separated.{ext}';fig.savefig(path,dpi=200,facecolor='white');files.append(path)
        plt.close(fig)
    counts=OUT/'outcome_counts.json';counts.write_text(json.dumps(audit,indent=2)+'\n');files.append(counts)
    bundle=OUT/'hard66_four_graphs_e_separated.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.name)
    print(json.dumps({'bundle':str(bundle),'outputs':[str(p) for p in files]},indent=2))


if __name__=='__main__':main()
