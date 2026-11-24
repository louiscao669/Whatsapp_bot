"""Compare omission releases using matched questions and unchanged reader settings."""
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from evaluation.scripts.campaigns.current import rerun_omission_ladder as campaign

old=campaign.old
DOSES=(0,*campaign.runner.DOSES)
OUTCOMES=('correct','incorrect','abstain','invalid')
STYLE='body{font:16px/1.6 system-ui;color:#243b43;max-width:1250px;margin:30px auto;padding:0 18px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:8px;border-bottom:1px solid #d5dfdf}img{max-width:100%}.scroll{overflow:auto}.note{background:#eef5f3;padding:16px}details{border:1px solid #d8e1e0;margin:12px 0;padding:12px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}.hidden{display:none}a{color:#096e75}select{padding:8px;margin:5px}'


def key(r):return r['reader_index'],r['family'],r['dose'],r['item']


def compatible(a,b):
    return all(a[k]==b[k] for k in ('question','choices','key'))


def count(rows):
    counts=Counter(r['outcome'] for r in rows);n=len(rows);answered=counts['correct']+counts['incorrect']
    return dict(n=n,**{k:counts[k] for k in OUTCOMES},accuracy=counts['correct']/n if n else None,
        abstention_rate=counts['abstain']/n if n else None,
        accuracy_among_A_D=counts['correct']/answered if answered else None)


def analyze(after,before):
    a={key(r):r for r in after};b={key(r):r for r in before}
    if len(a)!=len(after) or len(b)!=len(before):raise ValueError('Duplicate observations')
    comparable={k for k in a.keys()&b.keys() if compatible(a[k],b[k])}
    sets=[{k[3] for k in comparable if k[:3]==(i,'clean' if d==0 else 'omission',d)} for i in range(7) for d in DOSES]
    common=set.intersection(*sets)
    if not common:raise ValueError('No matched questions')
    matched=[];per_dose=[]
    for i,label in enumerate(campaign.runner.LABELS):
        for d in DOSES:
            ks={k for k in comparable if k[:3]==(i,'clean' if d==0 else 'omission',d)}
            per_dose.append(dict(reader_index=i,label=label,dose=d,before=count([b[k] for k in ks]),after=count([a[k] for k in ks])))
            for phase,lookup in [('before',b),('after',a)]:
                matched.append(dict(reader_index=i,label=label,dose=d,phase=phase,
                    **count([lookup[k] for k in ks if k[3] in common])))
    transitions=Counter();changes=[];unchanged_request_choice_changes=[]
    for k in sorted(comparable):
        left,right=b[k],a[k];transitions[left['outcome']+' → '+right['outcome']]+=1
        if left['choice']!=right['choice']:
            changes.append(dict(reader_index=k[0],label=right['label'],family=k[1],dose=k[2],item=k[3],
                reference=right['reference'],before_choice=left['choice'],after_choice=right['choice'],
                before_outcome=left['outcome'],after_outcome=right['outcome'],
                passage_changed=left['passage']!=right['passage']))
            if left['request_hash']==right['request_hash']:unchanged_request_choice_changes.append(changes[-1])
    if unchanged_request_choice_changes:raise ValueError('An unchanged request received a different scored choice')
    return dict(matched_question_ids=sorted(common),matched_question_count=len(common),matched_summary=matched,
        same_item_per_dose=per_dose,comparable_observations=len(comparable),
        noncomparable_new_observations=len(a)-len(comparable),transitions=dict(transitions),changed_answers=changes)


def figures(analysis,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    for metric,title in [('accuracy','Accuracy against the clean-source key'),('abstention_rate','Cannot-determine responses (E)')]:
        fig,axes=plt.subplots(4,2,figsize=(13,14),sharex=True,sharey=True)
        for i,ax in enumerate(axes.flat):
            if i==7:
                ax.axis('off');ax.text(.05,.85,f"Same {analysis['matched_question_count']} questions at every dose\n\nDashed gray: previous omission passages\nSolid teal: new 20/50/30 preference\n\nHeld passage variants are excluded.\nLines connect observations; no curve fit.\nOne answer per question and reader setting.",va='top',fontsize=12);continue
            for phase,color,linestyle in [('before','#7f8790','--'),('after','#087f82','-')]:
                rows=sorted([s for s in analysis['matched_summary'] if s['reader_index']==i and s['phase']==phase],key=lambda s:s['dose'])
                ax.plot([s['dose'] for s in rows],[s[metric] for s in rows],marker='o',ms=4,lw=1.8,color=color,ls=linestyle,label=phase)
            ax.set_title(campaign.runner.LABELS[i].replace(' · ',' — '),fontsize=12)
            ax.set_ylim(-.03,1.03);ax.set_xticks(DOSES);ax.tick_params(axis='x',labelsize=9,labelbottom=True)
            ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.2)
            ax.set_xlabel('Target omission dose (%)')
        fig.suptitle(title+' · before and after',fontsize=17)
        fig.tight_layout(rect=(0,0,1,.97))
        for ext in ('png','svg'):fig.savefig(output/f'{metric}_before_after.{ext}',dpi=170)
        plt.close(fig)


def passage_reports(rows,before,release,output):
    lookup={key(r):r for r in before};groups={}
    item_passage={w['id']:w['passage_id'] for w in release['windows']}
    for r in rows:groups.setdefault(item_passage[r['item']],[]).append(r)
    links=[]
    for pid,records in groups.items():
        title=campaign.runner.passage_label(records);filename=pid+'.html';links.append((title,filename,len(records)))
        h=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>'+escape(title)+'</title><style>'+STYLE+'</style><p><a href="index.html">Back to comparison</a></p><h1>'+escape(title)+'</h1>',
           '<p>Correct/incorrect is agreement with the clean-source key. E responses are shown separately; they may be appropriate when the defective passage removes the answer evidence.</p>']
        for field,choices in [('reader',[(str(i),label) for i,label in enumerate(campaign.runner.LABELS)]),('dose',[(str(d),'Clean' if d==0 else str(d)+'%') for d in DOSES]),('outcome',[(o,o) for o in OUTCOMES])]:
            h.append('<select id="'+field+'"><option value="all">All '+field+'s</option>'+''.join('<option value="'+v+'">'+escape(label)+'</option>' for v,label in choices)+'</select>')
        for r in records:
            previous=lookup.get(key(r));changed=previous and r['passage']!=previous['passage']
            h.append(f'<details class="item" data-reader="{r["reader_index"]}" data-dose="{r["dose"]}" data-outcome="{r["outcome"]}"><summary>'+escape(f'{r["label"]} · {r["reference"]} · {r["dose"]}% · {r["choice"] or "invalid"} · {r["outcome"]}')+'</summary>')
            if previous:h.append('<p>Previous choice: '+escape(str(previous['choice']))+' · New choice: '+escape(str(r['choice']))+' · Clean key: '+escape(r['key'])+'</p>')
            h.append('<h3>'+escape(r['question'])+'</h3><ol type="A">'+''.join('<li>'+escape(c)+'</li>' for c in r['choices'])+'</ol>')
            if changed:h.append('<h4>Previous passage</h4><p lang="zh">'+escape(previous['passage'])+'</p>')
            h.append('<h4>Current passage</h4><p lang="zh">'+escape(r['passage'])+'</p><h4>Model response</h4><pre>'+escape(r['answer'] or '(empty)')+'</pre>')
            h.append('<p>Actual dose: '+f'{r["actual_percent"]:.2f}%'+'. Scoring: '+escape(r['scoring_method'])+'. Generated tokens: '+str(r['effort']['output_tokens'])+'. Stop: '+escape(str(r['effort']['done_reason']))+'.</p>')
            if r['thinking_text']:h.append('<details><summary>Recorded thinking</summary><pre>'+escape(r['thinking_text'])+'</pre></details>')
            h.append('</details>')
        h.append('<script>for(const k of ["reader","dose","outcome"])document.getElementById(k).addEventListener("change",()=>{for(const e of document.querySelectorAll(".item"))e.classList.toggle("hidden",["reader","dose","outcome"].some(k=>document.getElementById(k).value!=="all"&&document.getElementById(k).value!==e.dataset[k]));});</script></html>')
        (output/filename).write_text(''.join(h))
    return links


def render():
    folder=campaign.RUN;output=campaign.REPORT;design=old.read(folder/'design.json')
    campaign.runner.verify_inputs(design)
    for path,digest in old.read(folder/'before_sources.json').items():
        if sha256((campaign.ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('Prior report changed')
    rows=old.read(output/'results.json');before=old.read(folder/'before_results.json');release=old.read(campaign.bank.DEST)
    if len(rows)!=4312:raise ValueError('Incomplete responses')
    analysis=analyze(rows,before)
    audits=[]
    for i,label in enumerate(campaign.runner.LABELS):
        selected=[r for r in rows if r['reader_index']==i]
        audits.append(dict(label=label,responses=len(selected),
            mapped=sum(r['scoring_method']=='gpt-4.1-mini mapping' for r in selected),
            mapped_e=sum(r['scoring_method']=='gpt-4.1-mini mapping' and r['choice']=='E' for r in selected),
            direct_e=sum(r['direct_choice']=='E' for r in selected),
            invalid=sum(r['outcome']=='invalid' for r in selected),
            length_limited=sum(r['effort']['done_reason']=='length' for r in selected),
            generated_tokens=sum(r['effort']['output_tokens'] or 0 for r in selected),
            thinking_traces=sum(bool(r['thinking_text']) for r in selected)))
    analysis.update(release=release['release'],observations=len(rows),reused_requests=design['reused_requests'],new_requests=design['new_requests'],
        held_variants=34,publication=old.read(folder/'publication.json'),response_audit=audits,
        source_sha256={str(p.relative_to(campaign.ROOT)):sha256(p.read_bytes()).hexdigest() for p in [output/'results.json',folder/'before_results.json',campaign.bank.DEST]},
        interpretation='Clean-source key agreement; E is separate. No new defective-text answerability labels were inferred. Main curves use the same questions at every dose and in both releases.')
    old.save(output/'analysis.json',analysis);figures(analysis,output)
    links=passage_reports(rows,before,release,output)
    pilot_table=['<h2>Pilot rates: all 65 questions</h2><p>Previous → new counts, out of the same 65 questions per reader at each rate. Correct means agreement with the clean-source key; E is shown separately.</p><div class="scroll"><table><tr><th>Reader</th><th>15% correct</th><th>30% correct</th><th>15% E</th><th>30% E</th></tr>']
    for i,label in enumerate(campaign.runner.LABELS):
        pilot_table.append('<tr><th>'+escape(label)+'</th>')
        for metric,dose in [('correct',15),('correct',30),('abstain',15),('abstain',30)]:
            cell=next(s for s in analysis['same_item_per_dose'] if s['reader_index']==i and s['dose']==dose)
            if cell['before']['n']!=65 or cell['after']['n']!=65:raise ValueError('Incomplete pilot-rate comparison')
            pilot_table.append(f'<td>{cell["before"][metric]} → {cell["after"][metric]}</td>')
        pilot_table.append('</tr>')
    pilot_table.append('</table></div>')
    h=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>New omission passages · model comparison</title><style>'+STYLE+'</style>',
       '<h1>New omission passages: small-model rerun</h1>',
       '<p>65 active from-scratch questions · 551 approved omission variants · 7 reader settings · 4,312 responses including clean baselines.</p>',
       f'<div class="note">The main graphs use the same <b>{analysis["matched_question_count"]} questions</b> at every dose in both releases. All 34 held variants are excluded from inference, rather than counted as wrong or E. All 551 approved variants were evaluated; their varying denominators appear below.</div>',
       '<p>Published to the separate hosted research bank. The human pilot still uses its existing conditions; its 15% and 30% passages were already current. The new 40–60% texts preserve every earlier deletion from 30%. The 20/50/30 mix is an occurrence-based preference and is not achieved at the high doses.</p>',
       f'<p>{design["new_requests"]:,} fresh local requests; {design["reused_requests"]:,} exact prior requests reused. Model weights, server version, prompts, choice order, temperature 0, 8,192-token context and 2,500-token output cap match the prior experiment. Thinking uses the output cap. Only unmatched nonempty primary-reader answers use the original GPT-4.1-mini response-to-choice mapper.</p>',
       '<p>Accuracy means agreement with the <b>clean-source key</b>. E may be appropriate for a corrupted passage; these results do not treat it as proof of failed comprehension. There is one response per question, dose and reader setting. Questions recur across doses, so the 4,312 responses are not independent samples. Lines connect observations; no significance or linear/logistic fit is claimed.</p>',
       '<p>The rebuild changes the specific information removed as well as the omission mixture. Differences between releases therefore cannot be attributed to the word/phrase/clause proportions alone. The 20/50/30 preference applies across the full bank; the matched 42-question subset can have different achieved proportions.</p>',
       ''.join(pilot_table),
       '<img src="accuracy_before_after.png" alt="Matched-question accuracy before and after by model"><img src="abstention_rate_before_after.png" alt="Matched-question E response rate before and after by model">',
       '<p><a href="accuracy_before_after.svg">Accuracy SVG</a> · <a href="abstention_rate_before_after.svg">E-rate SVG</a> · <a href="analysis.json">Comparison data</a> · <a href="results.json">All model responses</a></p>',
       '<h2>All approved questions at each dose</h2><p>Each entry is correct / wrong A–D / E / invalid. Denominators can vary across doses. The clean baseline includes all 65 questions.</p><div class="scroll"><table><tr><th>Reader</th>'+''.join('<th>'+('Clean' if d==0 else str(d)+'%')+'</th>' for d in DOSES)+'</tr>']
    for i,label in enumerate(campaign.runner.LABELS):
        h.append('<tr><th>'+escape(label)+'</th>')
        for d in DOSES:
            s=count([r for r in rows if r['reader_index']==i and r['dose']==d])
            h.append('<td>'+' / '.join(str(s[k]) for k in OUTCOMES)+f'<br>{s["accuracy"]:.1%} · n={s["n"]}</td>')
        h.append('</tr>')
    h.append('</table></div><h2>Response checks</h2><p>Direct E choices and E assigned by the original response-to-choice mapper are separated here. Reaching the token cap does not automatically make an answer invalid.</p><div class="scroll"><table><tr><th>Reader</th><th>Responses</th><th>Mapped</th><th>Mapped E</th><th>Direct E</th><th>Invalid</th><th>Token cap reached</th></tr>')
    for audit in audits:h.append('<tr><th>'+escape(audit['label'])+'</th>'+''.join('<td>'+str(audit[k])+'</td>' for k in ['responses','mapped','mapped_e','direct_e','invalid','length_limited'])+'</tr>')
    h.append('</table></div><h2>Inspect passages and answers</h2><p>'+str(len(analysis['changed_answers']))+' choices changed on comparable observations.</p><ul>')
    for title,filename,n in links:h.append('<li><a href="'+filename+'">'+escape(title)+'</a> · '+str(n)+' responses</li>')
    h.append('</ul><h2>Held variants</h2><ul>')
    for x in design['excluded_stimuli']:h.append('<li>'+escape(f'{x["reference"]} · {x["dose"]}%: {x["reason"]}')+'</li>')
    h.append('</ul></html>');(output/'index.html').write_text(''.join(h))
    print('REPORT',output/'index.html');print('MATCHED',analysis['matched_question_count'],'CHANGED ANSWERS',len(analysis['changed_answers']))


if __name__=='__main__':render()
