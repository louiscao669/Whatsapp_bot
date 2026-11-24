"""Summarize completed passage experiments using a constant question set within each defect family."""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path

from evaluation.scripts.campaigns.current import run_window_dose_readers as runner


def load_passage(folder):
    rows=json.loads((folder/'results.json').read_text())
    summaries=json.loads((folder/'summary.json').read_text())
    held_path=folder/'excluded_stimuli.json'
    held=json.loads(held_path.read_text()) if held_path.exists() else []
    items={r['item'] for r in rows if r['family']=='clean'}
    missing={(h['item'],h['family'],h['dose']) for h in held}
    expected={(i,f,d,item) for i in range(7) for f,d in
              [('clean',0)]+[(f,d) for f in runner.FAMILIES for d in runner.DOSES]
              for item in items if (item,f,d) not in missing}
    actual={(r['reader_index'],r['family'],r['dose'],r['item']) for r in rows}
    if len(rows)!=len(expected) or actual!=expected:
        raise ValueError(f'Missing or duplicated observations: {folder}')
    assert len(summaries)==133
    for s in summaries:
        cell=[r for r in rows if (r['reader_index'],r['family'],r['dose'])==
              (s['reader_index'],s['family'],s['dose'])]
        counts=Counter(r['outcome'] for r in cell)
        assert len(cell)==s['n']
        assert all(s[k]==counts[k] for k in ('correct','incorrect','abstain','invalid'))
    common={}
    for family in runner.FAMILIES:
        sets=[{r['item'] for r in rows if r['reader_index']==i and r['family']==f and r['dose']==d}
              for i in range(7) for f,d in [('clean',0)]+[(family,d) for d in runner.DOSES]]
        common[family]=sorted(set.intersection(*sets))
    return dict(label=runner.passage_label(rows),folder=str(folder.resolve()),
                items=sorted(items),rows=rows,held=held,common=common,
                source_sha256={str((folder/n).resolve()):sha256((folder/n).read_bytes()).hexdigest()
                               for n in ('results.json','summary.json')})


def summaries_for(passages):
    result=[]
    for family in runner.FAMILIES:
        for i in range(7):
            for dose in (0,*runner.DOSES):
                cell=[r for p in passages for r in p['rows'] if r['item'] in p['common'][family]
                      and r['reader_index']==i and r['family']==('clean' if dose==0 else family)
                      and r['dose']==dose]
                n=len(cell);counts=Counter(r['outcome'] for r in cell)
                result.append(dict(family=family,dose=dose,reader_index=i,label=runner.LABELS[i],n=n,
                    **{k:counts[k] for k in ('correct','incorrect','abstain','invalid')},
                    accuracy=counts['correct']/n if n else None,
                    abstention_rate=counts['abstain']/n if n else None))
    return result


def report_bank(folders,output):
    passages=[load_passage(p) for p in folders]
    all_ids=[item for p in passages for item in p['items']]
    assert len(all_ids)==len(set(all_ids)),'Passage reports overlap'
    overall=summaries_for(passages)
    for p in passages:p['matched_summary']=summaries_for([p])
    output.mkdir(parents=True,exist_ok=True)
    total=sum(len(p['rows']) for p in passages)
    sizes={f:sum(len(p['common'][f]) for p in passages) for f in runner.FAMILIES}
    metadata=dict(passages=len(passages),questions=len(all_ids),observations=total,
        matched_questions=sizes,
        analysis_policy='Within each defect family, plot only questions available at every dose for every reader. Clean baselines use that same set. No reader responses are regenerated.',
        overall_summary=overall,passage_summaries=[{k:v for k,v in p.items() if k!='rows'} for p in passages])
    (output/'analysis.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    for metric,title in [('accuracy','Accuracy against clean-source key'),('abstention_rate','Cannot-determine responses (E)')]:
        fig,axes=plt.subplots(1,2,figsize=(13,6),sharey=True)
        for ax,family in zip(axes,runner.FAMILIES):
            for i,label in enumerate(runner.LABELS):
                points=[s for s in overall if s['family']==family and s['reader_index']==i]
                ax.plot([s['dose'] for s in points],[s[metric] for s in points],
                        marker=['o','s','^','v','D','P','X'][i],ms=4,lw=1.6,label=label)
            ax.set_title(f'{family.title()} · same {sizes[family]} questions at every dose')
            ax.set_xlabel('Target affected source characters (%)');ax.set_xticks([0,*runner.DOSES])
            ax.set_ylim(-.03,1.03);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.2)
        axes[0].set_ylabel(title)
        fig.suptitle(f'{len(passages)} passages · all seven reader settings',fontsize=16)
        fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=3,frameon=False,fontsize=10)
        fig.tight_layout(rect=(0,.18,1,.94))
        for ext in ('png','svg'):fig.savefig(output/f'{metric}.{ext}',dpi=180)
        plt.close(fig)
    h=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>Full-bank dose experiment</title><style>body{max-width:1300px;margin:32px auto;padding:0 20px;font:16px/1.6 system-ui;color:#20343b}img{max-width:100%}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ccd9d8;text-align:left}.scroll{overflow:auto}.note{padding:18px;background:#edf4f2}details{border:1px solid #d5dfdd;padding:12px;margin:12px 0}summary{cursor:pointer;font-weight:600}a{color:#126378}</style></head><body>',
       '<h1>Omission and mistranslation across the question bank</h1>',
       f'<p>{len(passages)} passages · {len(all_ids)} distinct questions · 7 reader settings · {total:,} recorded responses.</p>',
       f'<div class="note">The main graphs use the same questions at every dose: <b>{sizes["omission"]} for omission</b> and <b>{sizes["mistranslation"]} for mistranslation</b>. A question missing any approved dose is left out of that family’s comparison, including its clean baseline. All available responses are preserved in the individual passage reports. Missing held cells are not counted as incorrect or E.</div>',
       '<p>Accuracy uses the clean-source key. E means 无法判断. Matching the key after its evidence is deleted does not establish comprehension of the displayed passage. These are descriptive results, with one response per item and setting; lines connect observations and are not fitted curves. Models and doses reuse questions, so the response total is not an independent sample size.</p>',
       '<p><a href="accuracy.svg">Scalable accuracy figure</a> · <a href="abstention_rate.svg">Scalable E-rate figure</a></p>',
       '<img src="accuracy.png" alt="All reader models by defect dose using matched questions"><img src="abstention_rate.png" alt="Cannot-determine responses by defect dose using matched questions">',
       '<p>30–60% versions are nested; 5–25% versions need not be. Doses count affected clean Chinese content characters, with ±2 percentage-point tolerance. The original reader-specific prompts and parsers, model weights, temperature 0 and 2,500-token output cap are retained. Thinking counts toward that cap. Unmatched nonempty primary-reader answers use the original GPT-4.1-mini choice mapper; no passage or answer key is sent to that mapper.</p>',
       '<h2>Passage comparison</h2><p>Percentages below average the seven settings, using a constant question set within each family. Clean baselines may differ between families if a held version removes a question from one comparison.</p><div class="scroll"><table><tr><th>Passage</th><th>Omission questions</th><th>Clean → 30% → 60%</th><th>Mistranslation questions</th><th>Clean → 30% → 60%</th></tr>']
    for p in passages:
        h.append('<tr><th>'+escape(p['label'])+'</th>')
        for family in runner.FAMILIES:
            values=[]
            for dose in (0,30,60):
                cells=[s for s in p['matched_summary'] if s['family']==family and s['dose']==dose]
                n=sum(s['n'] for s in cells);values.append(f'{sum(s["correct"] for s in cells)/n:.1%}' if n else '—')
            h.append(f'<td>{len(p["common"][family])}</td><td>'+ ' → '.join(values)+'</td>')
        h.append('</tr>')
    h.append('</table></div><h2>Individual passage graphs and responses</h2>')
    for p in passages:
        link=os.path.relpath(Path(p['folder'])/'index.html',output)
        plot=os.path.relpath(Path(p['folder'])/'accuracy.png',output)
        h.append('<details><summary>'+escape(f'{p["label"]} · {len(p["items"])} questions · {len(p["rows"]):,} responses')+'</summary>')
        h.append(f'<p><a href="{escape(link,quote=True)}">Full report: all choices, answers, thinking traces and response checks</a></p><img src="{escape(plot,quote=True)}" alt="'+escape(p['label'])+' model accuracy">')
        if p['held']:h.append('<p>This individual report uses all available items and shows its varying cell denominators.</p>')
        h.append('</details>')
    h.append('<h2>Held versions</h2><ul>')
    for p in passages:
        for held in p['held']:
            h.append('<li>'+escape(f'{held["reference"]} · {held["family"]} {held["dose"]}%: {held["reason"]}')+'</li>')
    h.append('</ul><h2>Response checks</h2><table><tr><th>Passage</th><th>Mapped choices</th><th>Mapped E</th><th>Invalid</th><th>Token limit reached</th></tr>')
    for p in passages:
        rows=p['rows'];values=[sum(r['scoring_method']=='gpt-4.1-mini mapping' for r in rows),
            sum(r['scoring_method']=='gpt-4.1-mini mapping' and r['choice']=='E' for r in rows),
            sum(r['outcome']=='invalid' for r in rows),sum(r['effort']['done_reason']=='length' for r in rows)]
        h.append('<tr><th>'+escape(p['label'])+'</th>'+''.join(f'<td>{v}</td>' for v in values)+'</tr>')
    h.append('</table><p><a href="analysis.json">Download the numeric summaries and analysis provenance</a></p></body></html>')
    (output/'index.html').write_text(''.join(h),encoding='utf-8')
    print(output/'index.html');print({k:metadata[k] for k in ('passages','questions','observations','matched_questions')})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',nargs='+',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report_bank(args.reports,args.output)
