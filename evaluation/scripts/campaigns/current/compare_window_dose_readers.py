"""Compare completed passage dose experiments without pooling repeated items as independent trials."""
import argparse
from collections import Counter
from html import escape
import json
import os
from pathlib import Path

from evaluation.scripts.campaigns.current import run_window_dose_readers as runner


def compare(report_dirs, output):
    passages=[]
    for folder in report_dirs:
        rows=json.loads((folder/'results.json').read_text())
        clean=[r for r in rows if r['family']=='clean']
        items={r['item'] for r in clean}
        n=len(items)
        expected={(i,f,d,item) for i in range(7) for f,d in
                  [('clean',0)]+[(f,d) for f in runner.FAMILIES for d in runner.DOSES]
                  for item in items}
        observed={(r['reader_index'],r['family'],r['dose'],r['item']) for r in rows}
        if observed!=expected or len(rows)!=len(expected):
            raise ValueError(f'Incomplete or duplicated experiment: {folder}')
        summary=[]
        for family,dose in [('clean',0)]+[(f,d) for f in runner.FAMILIES for d in runner.DOSES]:
            cell=[r for r in rows if r['family']==family and r['dose']==dose]
            counts=Counter(r['outcome'] for r in cell)
            summary.append(dict(family=family,dose=dose,n=len(cell),
                **{k:counts[k] for k in ('correct','incorrect','abstain','invalid')},
                accuracy=counts['correct']/len(cell),
                abstention_rate=counts['abstain']/len(cell),
                mean_actual_percent=sum(r['actual_percent'] for r in cell)/len(cell)))
        audit=dict(observations=len(rows),questions=n,
            mapped=sum(r['scoring_method']=='gpt-4.1-mini mapping' for r in rows),
            mapped_e=sum(r['scoring_method']=='gpt-4.1-mini mapping' and r['choice']=='E' for r in rows),
            invalid=sum(r['outcome']=='invalid' for r in rows),
            length_limited=sum(r['effort']['done_reason']=='length' for r in rows))
        passages.append(dict(label=runner.passage_label(rows),folder=str(folder.resolve()),
            n_questions=n,summary=summary,audit=audit))
    output.mkdir(parents=True,exist_ok=True)
    (output/'comparison.json').write_text(json.dumps(passages,ensure_ascii=False,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    colors=['#167d8d','#b65327','#6750a4']
    for metric,ylabel in [('accuracy','Accuracy against clean-source key'),
                           ('abstention_rate','Cannot-determine responses (E)')]:
        fig,axes=plt.subplots(1,2,figsize=(12,5),sharey=True)
        for ax,family in zip(axes,runner.FAMILIES):
            for p,color in zip(passages,colors):
                series=[s for s in p['summary'] if s['family'] in ('clean',family)]
                ax.plot([s['dose'] for s in series],[s[metric] for s in series],
                    marker='o',lw=2,color=color,label=f"{p['label']} ({p['n_questions']} questions)")
            ax.set_title(family.title())
            ax.set_xlabel('Target affected source characters (%)')
            ax.set_xticks([0,*runner.DOSES]);ax.set_ylim(-.03,1.03)
            ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.2)
        axes[0].set_ylabel(ylabel)
        fig.suptitle('Passage comparison · equal weight for the seven reader settings')
        fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',ncol=3,frameon=False)
        fig.tight_layout(rect=(0,.1,1,.95))
        for extension in ('png','svg'):fig.savefig(output/f'{metric}.{extension}',dpi=180)
        plt.close(fig)
    h=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>Three-passage dose experiment</title><style>body{font:16px/1.6 system-ui;color:#20343b;max-width:1150px;margin:32px auto;padding:0 20px}img{max-width:100%}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px;border-bottom:1px solid #d3dedc}.scroll{overflow:auto}.note{background:#edf4f2;padding:16px}a{color:#126378}</style></head><body>',
       '<h1>Omission and mistranslation across three passages</h1>',
       f'<p>{sum(p["n_questions"] for p in passages)} distinct questions · 7 reader settings · {sum(p["audit"]["observations"] for p in passages):,} responses including clean baselines.</p>',
       '<div class="note">These are descriptive averages over seven fixed reader settings. The same questions recur across readers and doses; the response counts are not independent question counts. Lines connect observations and are not fitted linear or logistic curves. No formal comparison of curve shapes or significance test is reported.</div>',
       '<p>Accuracy uses each question’s clean-source answer key. A defective passage may remove or contradict its evidence. E (无法判断) and invalid responses are included in the accuracy denominator and are reported separately below. The clean baseline is shared between the two panels.</p>',
       '<img src="accuracy.png" alt="Accuracy across doses for each passage"><img src="abstention_rate.png" alt="Cannot-determine response rates across doses for each passage">',
       '<p>Doses are percentages of affected clean Chinese content characters, with ±2 percentage-point tolerance. Versions from 30–60% are nested; those from 5–25% need not be. Consequently, low-dose fluctuations can reflect which evidence was changed as well as dose. Each cell has one generation per question and reader setting.</p>',
       '<h2>Full passage reports</h2><ul>']
    for p in passages:
        link=os.path.relpath(Path(p['folder'])/'index.html',output)
        h.append(f'<li><a href="{escape(link,quote=True)}">{escape(p["label"])}</a>: {p["n_questions"]} questions, {p["audit"]["observations"]:,} responses; individual model results, passages, choices, answers and recorded thinking.</li>')
    h.append('</ul>')
    for family in runner.FAMILIES:
        h.append(f'<h2>{family.title()}</h2><p>Each cell: correct / wrong A–D / E / invalid, followed by accuracy.</p><div class="scroll"><table><tr><th>Target dose</th>'+''.join(f'<th>{escape(p["label"])}<br>{7*p["n_questions"]} responses per dose</th>' for p in passages)+'</tr>')
        for dose in (0,*runner.DOSES):
            h.append(f'<tr><th>{"Clean" if dose==0 else str(dose)+"%"}</th>')
            for p in passages:
                s=next(s for s in p['summary'] if s['dose']==dose and s['family']==('clean' if dose==0 else family))
                h.append('<td>'+' / '.join(str(s[k]) for k in ('correct','incorrect','abstain','invalid'))+f'<br>{s["accuracy"]:.1%}</td>')
            h.append('</tr>')
        h.append('</table></div>')
    h.append('<h2>Response checks</h2><p>Mapped E choices are distinguished from a reader directly selecting E. Reaching the token limit does not automatically mean an invalid answer.</p><table><tr><th>Passage</th><th>Mapped choices</th><th>Mapped E</th><th>Invalid</th><th>Token limit reached</th></tr>')
    for p in passages:
        h.append(f'<tr><th>{escape(p["label"])}</th>'+''.join(f'<td>{p["audit"][k]}</td>' for k in ('mapped','mapped_e','invalid','length_limited'))+'</tr>')
    h.append('</table><p>The original two reader-prompt/parser families are preserved. Unmatched nonempty responses from the four primary reader settings use GPT-4.1-mini to map the response to an option, using only the response and choices. Empty responses remain invalid. All readers use temperature 0, an 8,192-token context, and a 2,500-token generation cap; thinking uses that cap.</p></body></html>')
    (output/'index.html').write_text(''.join(h),encoding='utf-8')
    print(output/'index.html')
    return passages


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',type=Path,nargs=3,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    compare(args.reports,args.output)
