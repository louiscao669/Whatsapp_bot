"""Plot each reader setting across the three completed passage experiments."""
import argparse
from collections import Counter
from html import escape
import json
import os
from pathlib import Path

from evaluation.scripts.campaigns.current import run_window_dose_readers as runner


def plot_models(report_dirs, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    from matplotlib.lines import Line2D

    passages=[]
    for folder in report_dirs:
        summaries=json.loads((folder/'summary.json').read_text())
        rows=json.loads((folder/'results.json').read_text())
        n=len({r['item'] for r in rows if r['family']=='clean'})
        expected={(i,f,d) for i in range(7) for f,d in
                  [('clean',0)]+[(f,d) for f in runner.FAMILIES for d in runner.DOSES]}
        index={(s['reader_index'],s['family'],s['dose']):s for s in summaries}
        if set(index)!=expected or len(summaries)!=len(expected):
            raise ValueError(f'Incomplete summary: {folder}')
        for (i,f,d),s in index.items():
            cell=[r for r in rows if (r['reader_index'],r['family'],r['dose'])==(i,f,d)]
            counts=Counter(r['outcome'] for r in cell)
            assert len(cell)==n==s['n'] and len({r['item'] for r in cell})==n
            assert all(s[k]==counts[k] for k in ('correct','incorrect','abstain','invalid'))
            assert s['accuracy']==counts['correct']/n
            assert s['abstention_rate']==counts['abstain']/n
        passages.append(dict(label=runner.passage_label(rows),n=n,folder=folder,index=index))
    output.mkdir(parents=True,exist_ok=True)
    colors=['#167d8d','#b65327','#6750a4']
    markers=['o','s','^']
    styles=['-','--','-.']
    labels=['Llama 3.2 1B','Qwen 2.5 1.5B','Qwen 3 1.7B\nThinking',
            'Qwen 3 1.7B\nNo thinking','Gemma 3 4B','Phi-4-mini 3.8B','Qwen 2.5 3B']
    dose_grid=[0,*runner.DOSES]
    figures=[]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,
                         'axes.spines.top':False,'axes.spines.right':False,
                         'axes.titleweight':'bold','svg.fonttype':'none'})
    for family in runner.FAMILIES:
        fig,axes=plt.subplots(2,4,figsize=(16,8.4),sharex=True,sharey=True)
        for i,ax in enumerate(axes.flat[:7]):
            for p,color,marker,style in zip(passages,colors,markers,styles):
                cells=[p['index'][i,'clean' if d==0 else family,d] for d in dose_grid]
                ax.plot(dose_grid,[s['accuracy'] for s in cells],color=color,marker=marker,
                        linestyle=style,linewidth=1.9,markersize=4.8,markeredgewidth=.7)
            ax.set_title(labels[i],fontsize=12.5,pad=12)
            ax.set_xlim(-2,62);ax.set_ylim(-.035,1.055)
            ax.set_xticks(dose_grid);ax.tick_params(axis='x',labelsize=9,labelbottom=True)
            ax.set_yticks([0,.25,.5,.75,1]);ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=0))
            ax.tick_params(axis='y',labelleft=True,labelsize=10)
            ax.grid(axis='y',alpha=.2);ax.grid(axis='x',alpha=.08)
            if i//4==1:ax.set_xlabel('Defect dose (%)',labelpad=9)
            if i%4==0:ax.set_ylabel('Accuracy against clean-source key',labelpad=9)
        key=axes.flat[7];key.axis('off')
        handles=[Line2D([0],[0],color=c,marker=m,linestyle=s,lw=2,
                       label=f"{p['label']}  ·  {p['n']} questions")
                 for p,c,m,s in zip(passages,colors,markers,styles)]
        key.legend(handles=handles,loc='upper left',bbox_to_anchor=(0,.97),
                   frameon=False,fontsize=11,labelspacing=1.25,handlelength=2.6)
        key.text(.03,.52,'0% = clean baseline\nSame axes in every panel\nOne response per question and setting',
                 va='top',fontsize=10.5,linespacing=1.65,color='#34464b')
        key.text(.03,.23,'Lines connect observed scores.\nThey are not fitted dose–response curves.',
                 va='top',fontsize=10,linespacing=1.6,color='#58686d')
        fig.suptitle(f'{family.title()} · each model across three passages',fontsize=20,y=.98)
        fig.text(.5,.918,'All seven reader settings · 5–60% target affected source characters',
                 ha='center',fontsize=12,color='#506168')
        fig.subplots_adjust(left=.062,right=.984,top=.82,bottom=.105,wspace=.29,hspace=.55)
        fig.text(.062,.025,'E (cannot determine) and invalid answers count as not correct.  '
                 '30–60% versions are nested; 5–25% versions need not be.',fontsize=10,color='#506168')
        stem=f'{family}_by_model'
        for extension in ('png','svg'):
            fig.savefig(output/f'{stem}.{extension}',dpi=180,facecolor='white')
        plt.close(fig);figures.append(stem)
    h=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>All models across three passages</title><style>body{font:16px/1.6 system-ui;max-width:1600px;margin:30px auto;padding:0 20px;color:#20343b}img{width:100%;height:auto}a{color:#126378}.note{background:#edf4f2;padding:16px}</style></head><body>',
       '<h1>All seven reader settings across three passages</h1>',
       '<p>Each panel is one model setting. The three colored lines compare the passages; the axes are identical across panels. Qwen 3 thinking and no-thinking are shown separately.</p>',
       '<p class="note">Accuracy is measured against the clean-source answer key. Each point contains 8 questions for 1 Kings 13, 6 for 2 Chronicles 26, and 10 for 2 Kings 6–7. These small, repeated item sets do not establish a fitted curve or significance. E and invalid responses remain in the denominator.</p>']
    for family,stem in zip(runner.FAMILIES,figures):
        h.append(f'<h2>{family.title()}</h2><p><a href="{stem}.svg">Open scalable figure</a> · <a href="{stem}.png">Open PNG</a></p><a href="{stem}.svg"><img src="{stem}.png" alt="{family.title()} accuracy, all seven model settings and three passages"></a>')
    h.append('<p>Doses count affected clean Chinese source characters, with ±2 percentage-point tolerance. The 30–60% versions are nested; the 5–25% versions need not be. A higher score after omission does not establish improved comprehension: a model can match the clean key despite missing evidence. Original reader-specific prompts and scoring are retained, including GPT-4.1-mini mapping for unmatched nonempty primary-reader responses.</p><h2>Full results and individual responses</h2><ul>')
    for p in passages:
        link=os.path.relpath(p['folder']/'index.html',output)
        h.append(f'<li><a href="{escape(link,quote=True)}">{escape(p["label"])}</a></li>')
    h.append('</ul><p><a href="index.html">Passage averages and cannot-determine rates</a></p></body></html>')
    (output/'by_model.html').write_text(''.join(h),encoding='utf-8')
    print(f'Verified {len(passages)*133} summary cells against individual responses.')
    print(output/'by_model.html')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',type=Path,nargs=3,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    plot_models(args.reports,args.output)
