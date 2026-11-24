"""Compare completed grammar reader runs with the same frozen protocol."""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import os
from pathlib import Path

from evaluation.scripts.campaigns.current import run_grammar_ladder_readers as r


def compare(run_names, output):
    passages=[]
    protocol=None
    for name in run_names:
        run=r.ROOT/'evaluation/runs'/name
        report=r.ROOT/'evaluation/reports'/name
        design=r.old.read(run/'design.json')
        records=r.old.read(report/'results.json')
        saved=r.old.read(report/'summary.json')
        r.runner.verify_inputs(design)
        assert r.old.digest(r.old.read(run/'requests.json'))==design['requests_sha256']
        assert r.old.digest(r.old.read(run/'stimuli.json'))==design['stimuli_sha256']
        assert saved==r.summarize(records,design)
        n=len(design['question_ids'])
        assert len(records)==n*49==design['expected']
        assert len({(x['reader_index'],x['dose'],x['item']) for x in records})==len(records)
        settings={k:design[k] for k in ('models','weights','inference','doses','families','scoring','input_sha256','ollama_version')}
        if protocol is None:protocol=settings
        else:assert protocol==settings,'Experiment settings or source files differ'
        passages.append(dict(name=name,label=r.runner.passage_label(records),n=n,report=report,
            index={(s['reader_index'],s['dose']):s for s in saved},records=records,
            hashes={str(p.relative_to(r.ROOT)):sha256(p.read_bytes()).hexdigest() for p in
                    (run/'design.json',report/'results.json',report/'summary.json')}))
    output.mkdir(parents=True,exist_ok=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import PercentFormatter
    colors=['#167d8d','#b65327','#6750a4']
    markers=['o','s','^'];styles=['-','--','-.']
    for metric,title in [('accuracy','Correct against clean-source key'),('abstention_rate','Responses scored as E')]:
        fig,axes=plt.subplots(2,4,figsize=(16,8),sharex=True,sharey=True)
        for i,ax in enumerate(axes.flat[:7]):
            for p,color,marker,style in zip(passages,colors,markers,styles):
                series=[p['index'][i,d] for d in (0,*r.DOSES)]
                ax.plot([s['dose'] for s in series],[s[metric] for s in series],color=color,marker=marker,
                        linestyle=style,lw=1.8,ms=4)
            ax.set_title(r.runner.LABELS[i],fontsize=11)
            ax.set_xticks([0,*r.DOSES]);ax.set_ylim(-.04,1.04)
            ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.2)
            ax.tick_params(labelbottom=True,labelleft=True)
            ax.set_xlabel('Target grammar dose (%)')
        key=axes.flat[7];key.axis('off')
        handles=[Line2D([0],[0],color=c,marker=m,linestyle=s,lw=2,label=f'{p["label"]} · n={p["n"]}')
                 for p,c,m,s in zip(passages,colors,markers,styles)]
        key.legend(handles=handles,loc='upper left',frameon=False,fontsize=10)
        note = ('E includes mapped free-text\nresponses; it does not always\nmean explicit abstention.'
                if metric=='abstention_rate' else 'E and invalid responses remain\nin the accuracy denominator.')
        key.text(.03,.57,'0% = clean baseline\nSame axes in every panel\n\n'+note+'\n\nLines connect observations;\nno fitted curve.',va='top',fontsize=10,linespacing=1.5)
        fig.suptitle('Grammar · '+title,fontsize=17)
        fig.tight_layout(rect=(0,0,1,.94))
        for ext in ('png','svg'):fig.savefig(output/f'{metric}.{ext}',dpi=170)
        plt.close(fig)
    total=sum(len(p['records']) for p in passages)
    h=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>Grammar SLM comparison</title><style>body{max-width:1500px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;color:#213b42}img{width:100%}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left}.scroll{overflow:auto}</style>',
       '<h1>Grammar · seven SLM settings across three passages</h1>',
       '<p>'+escape(' · '.join(f'{p["label"]}: {p["n"]} active questions' for p in passages))+f'. {total} responses including clean baselines.</p>',
       '<p>Every passage uses the same model weights, prompts, scoring rules, temperature 0, 8,192-token context and 2,500-token generation cap. '
       'The cap includes thinking. Scores are against the clean-source key. Wrong A–D answers, E and invalid outputs remain separate. '
       'The held 2 Kings 7:17–18 question is excluded. Each point has only 6–9 questions; the lines are descriptive, not fitted dose–response curves.</p>',
       '<p>Grammar doses count affected clean source characters with ±2 percentage-point tolerance. '
       'The six doses are independently selected. The generation bank uses a soft preference of 30% misselection / 70% misordering by error instances.</p>',
       '<img src="accuracy.png" alt="Grammar accuracy compared across three passages">',
       '<img src="abstention_rate.png" alt="E response rates compared across three passages">']
    for p in passages:
        h.append('<h2>'+escape(p['label'])+f' · correct out of {p["n"]}</h2><div class="scroll"><table><tr><th>Reader</th>'+''.join(f'<th>{d}%</th>' for d in (0,*r.DOSES))+'</tr>')
        for i,label in enumerate(r.runner.LABELS):
            h.append('<tr><th>'+escape(label)+'</th>'+''.join(f'<td>{p["index"][i,d]["correct"]}</td>' for d in (0,*r.DOSES))+'</tr>')
        link=os.path.relpath(p['report']/'index.html',output)
        h.append('</table></div><p><a href="'+escape(link,quote=True)+'">Passages, choices, individual responses, E counts and thinking traces</a></p>')
    h.append('<h2>Response checks</h2><table><tr><th>Passage</th><th>Mapped responses</th><th>E from mapping</th><th>Invalid</th><th>Token limit</th></tr>')
    for p in passages:
        rows=p['records']
        counts=[sum(x['scoring_method']=='gpt-4.1-mini mapping' for x in rows),
                sum(x['scoring_method']=='gpt-4.1-mini mapping' and x['choice']=='E' for x in rows),
                sum(x['outcome']=='invalid' for x in rows),sum(x['effort']['done_reason']=='length' for x in rows)]
        h.append('<tr><th>'+escape(p['label'])+'</th>'+''.join(f'<td>{v}</td>' for v in counts)+'</tr>')
    h.append('</table><p>The original GPT-4.1-mini mapper receives only unmatched nonempty primary-reader responses and answer choices. '
             'An E supplied by mapping is distinguished from a direct E response. One generation per question and setting. No live pilot passages were changed.</p></html>')
    (output/'index.html').write_text(''.join(h))
    r.old.save(output/'verification.json',dict(complete=True,observations=total,passages=[dict(
        label=p['label'],n=p['n'],observations=len(p['records']),source_hashes=p['hashes'],
        outcomes=dict(Counter(x['outcome'] for x in p['records']))) for p in passages],
        same_frozen_protocol=True,all_summary_cells_recounted=True,published=False,
        report_sha256=sha256((output/'index.html').read_bytes()).hexdigest()))
    print('REPORT',output/'index.html',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs',nargs=3,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();compare(args.runs,args.output)
