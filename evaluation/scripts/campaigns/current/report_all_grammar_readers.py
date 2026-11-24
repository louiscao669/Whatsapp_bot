"""Verify and report the completed grammar experiment across all 65 active QAs."""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import os
from pathlib import Path

from evaluation.scripts.campaigns.current import run_grammar_ladder_readers as r

RUNS = [f'sol_{stem}_grammar_readers_2026-11-23' for stem in (
    '1kgs13','2chr26','2kgs11','2kgs6_7','2sam21','acts19','acts20','acts23','judg17_18','judg9')]
OUTPUT = r.ROOT/'evaluation/reports/sol_all65_grammar_readers_2026-11-23'


def collect():
    passages=[];all_rows=[];question_ids=[];protocol=None
    bank=r.old.read(r.BANK)
    expected_ids={w['id'] for w in bank['windows']}
    for name in RUNS:
        run=r.ROOT/'evaluation/runs'/name;report=r.ROOT/'evaluation/reports'/name
        if r.old.read(run/'state.json')['status']!='complete':
            raise ValueError('Incomplete passage run: '+name)
        design=r.old.read(run/'design.json');jobs=r.old.read(run/'requests.json')
        stimuli=r.old.read(run/'stimuli.json')
        assert r.old.digest(jobs)==design['requests_sha256']
        assert r.old.digest(stimuli)==design['stimuli_sha256']
        rows,_=r.runner.results(run,design,jobs)
        assert rows==r.old.read(report/'results.json')
        summary=r.summarize(rows,design)
        assert summary==r.old.read(report/'summary.json')
        n=len(design['question_ids'])
        assert len(rows)==n*49==design['expected']
        assert len({(x['reader_index'],x['dose'],x['item']) for x in rows})==len(rows)
        assert not set(question_ids).intersection(design['question_ids'])
        question_ids.extend(design['question_ids'])
        settings={k:design[k] for k in ('models','weights','inference','doses','families','scoring','input_sha256','ollama_version')}
        if protocol is None:protocol=settings
        else:assert protocol==settings,'Frozen experiment settings differ: '+name
        lookup={(s['item'],s['family'],s['dose']):s for s in stimuli}
        clean={s['item']:s['passage'] for s in stimuli if s['family']=='clean'}
        for job in jobs:
            s=lookup[job['item'],job['family'],job['dose']]
            prompt='\n'.join(m['content'] for m in job['body']['messages'])
            assert s['passage'] in prompt
            if job['family']=='grammar':assert clean[job['item']] not in prompt
            raw=r.old.read(run/'answers'/(job['signature']+'.json'))
            assert raw['raw_response']['model']==job['model']
        passages.append(dict(name=name,label=r.runner.passage_label(rows),n=n,report=report,
            question_ids=design['question_ids'],rows=rows,summary=summary,
            index={(s['reader_index'],s['dose']):s for s in summary},
            hashes={str(p.relative_to(r.ROOT)):sha256(p.read_bytes()).hexdigest()
                    for p in (run/'design.json',report/'results.json',report/'summary.json')}))
        all_rows.extend(rows)
    assert len(question_ids)==65 and set(question_ids)==expected_ids
    assert len(all_rows)==3185
    assert '2kgs_7_1-20/v17-18:1' not in question_ids
    summary=r.summarize(all_rows,dict(question_ids=question_ids))
    for s in summary:
        rows=[x for x in all_rows if x['reader_index']==s['reader_index'] and x['dose']==s['dose']]
        s.update(direct_e=sum(x['choice']=='E' and x['scoring_method']=='rules' for x in rows),
                 mapped_e=sum(x['choice']=='E' and x['scoring_method']=='gpt-4.1-mini mapping' for x in rows),
                 mapped_responses=sum(x['scoring_method']=='gpt-4.1-mini mapping' for x in rows))
        assert s['direct_e']+s['mapped_e']==s['abstain']
    manifest=r.old.read(r.ROOT/'evaluation/runs/sol_remaining_grammar_readers_2026-11-23/manifest.json')
    assert all(sha256((r.ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest['preserved_files'].items())
    return passages,all_rows,summary,protocol


def figures(summary,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import PercentFormatter
    for metric,title in [('accuracy','Correct against clean-source key'),('e','E outcomes: direct and mapped')]:
        fig,axes=plt.subplots(2,4,figsize=(16,8),sharex=True,sharey=True)
        for i,ax in enumerate(axes.flat[:7]):
            ss=[s for s in summary if s['reader_index']==i]
            if metric=='accuracy':
                ax.plot([s['dose'] for s in ss],[s['accuracy'] for s in ss],color='#167d8d',marker='o',lw=2)
            else:
                for key,color,style,marker in [('direct_e','#167d8d','-','o'),('mapped_e','#b65327','--','s')]:
                    ax.plot([s['dose'] for s in ss],[s[key]/s['n'] for s in ss],color=color,ls=style,marker=marker,lw=2)
            ax.set_title(r.runner.LABELS[i],fontsize=11)
            ax.set_xticks([0,*r.DOSES]);ax.set_ylim(-.035,1.035)
            ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(alpha=.2)
            ax.tick_params(labelbottom=True,labelleft=True);ax.set_xlabel('Target grammar dose (%)')
        key=axes.flat[7];key.axis('off')
        top=.95
        if metric=='e':
            key.legend(handles=[Line2D([0],[0],color='#167d8d',marker='o',label='Directly parsed E'),
                                Line2D([0],[0],color='#b65327',marker='s',ls='--',label='Mapper-assigned E')],
                       loc='upper left',frameon=False,fontsize=10)
            top=.66
        note=('E and invalid responses remain\nin the accuracy denominator.' if metric=='accuracy' else
              'Mapped E can be an off-target\nfree-text response, not an\nexplicit abstention.')
        key.text(.03,top,'65 questions per point\n10 Bible passages\n0% = clean baseline\n\n'+note+
                 '\n\nQuestion-weighted results\nOne generation per item/setting\nLines are not fitted curves.',va='top',fontsize=10,linespacing=1.55)
        fig.suptitle('All 65 QAs · grammar · '+title,fontsize=17)
        fig.tight_layout(rect=(0,0,1,.94))
        for ext in ('png','svg'):fig.savefig(output/f'{metric}.{ext}',dpi=170)
        plt.close(fig)


def table(summary,n):
    h=['<div class="scroll"><table><tr><th>Reader</th>'+''.join(f'<th>{d}%</th>' for d in (0,*r.DOSES))+'</tr>']
    for i,label in enumerate(r.runner.LABELS):
        ss=[s for s in summary if s['reader_index']==i]
        h.append('<tr><th>'+escape(label)+'</th>'+''.join(
            f'<td>{s["correct"]}/{n}<br><small>{s["accuracy"]:.1%}</small></td>' for s in ss)+'</tr>')
    return ''.join(h)+'</table></div>'


def report(output):
    passages,rows,summary,protocol=collect()
    output.mkdir(parents=True,exist_ok=True)
    r.old.save(output/'results.json',rows);r.old.save(output/'summary.json',summary)
    r.old.save(output/'passage_summaries.json',[dict(name=p['name'],label=p['label'],n=p['n'],summary=p['summary']) for p in passages])
    figures(summary,output)
    h=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>All 65 QAs · grammar SLM experiment</title><style>body{max-width:1500px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;color:#213b42}img{width:100%}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left}.scroll{overflow:auto}details{border:1px solid #ccd8d6;padding:14px;margin:12px 0}summary{cursor:pointer;font-weight:600}small{color:#526970}</style>',
       '<h1>All 65 from-scratch QAs · grammar, 5–30%</h1>',
       '<p>65 active questions × 7 conditions × 7 reader settings = <b>3,185 responses</b>. '
       'The completed 1 Kings 13, 2 Kings 6–7 and 2 Chronicles 26 runs contribute 1,127 preserved responses. '
       'Seven remaining passages add 2,058 responses.</p>',
       '<p>Conditions: clean, 5%, 10%, 15%, 20%, 25% and 30% grammar. Doses count affected clean Chinese source characters, '
       'within ±2 percentage points. The versions are independently selected. The grammar bank uses a soft preference of '
       '30% misselection / 70% misordering by error instances.</p>',
       '<p>Every run uses the same model weights, reader-specific prompts, temperature 0, 8,192-token context and '
       '2,500-token generation cap including thinking. Accuracy uses the clean-source key; E and invalid responses remain '
       'in its denominator. All-65 results weight questions equally, so passages with more questions contribute more. '
       'Individual passage samples range from 2 to 12 questions. One generation per item and setting; no fitted dose–response curve.</p>',
       '<img src="accuracy.png" alt="All-65 grammar accuracy by model and dose">',
       '<h2>Overall correctness</h2><p>Correct answers out of 65. A change of one answer is 1.54 percentage points.</p>',table(summary,65),
       '<img src="e.png" alt="Direct E responses separately from mapper-assigned E">',
       '<h2>Responses by outcome</h2><p>Each entry is <b>correct / wrong A–D / direct E / mapped E / invalid</b>, out of 65.</p><div class="scroll"><table><tr><th>Reader</th>'+''.join(f'<th>{d}%</th>' for d in (0,*r.DOSES))+'</tr>']
    for i,label in enumerate(r.runner.LABELS):
        ss=[s for s in summary if s['reader_index']==i]
        h.append('<tr><th>'+escape(label)+'</th>'+''.join('<td>'+' / '.join(str(s[k]) for k in ('correct','incorrect','direct_e','mapped_e','invalid'))+'</td>' for s in ss)+'</tr>')
    h.append('</table></div><p>The established GPT-4.1-mini mapper receives only unmatched nonempty primary-reader answers and choices. '
             'An E assigned to an off-target free-text answer is not necessarily intentional abstention. No random fallback is used.</p><h2>Results by passage</h2>')
    for p in passages:
        link=os.path.relpath(p['report']/'index.html',output)
        h.append('<details><summary>'+escape(p['label'])+f' · {p["n"]} questions</summary>'+table(p['summary'],p['n'])+
                 '<p><a href="'+escape(link,quote=True)+'">Passages, questions, choices, raw answers and thinking traces</a></p></details>')
    h.append('<h2>Response checks</h2><table><tr><th>Passage</th><th>Responses</th><th>Mapped choices</th><th>Direct E</th><th>Mapped E</th><th>Invalid</th><th>Hit token limit</th></tr>')
    for p in passages:
        rr=p['rows'];counts=[len(rr),sum(x['scoring_method']=='gpt-4.1-mini mapping' for x in rr),
            sum(x['choice']=='E' and x['scoring_method']=='rules' for x in rr),
            sum(x['choice']=='E' and x['scoring_method']=='gpt-4.1-mini mapping' for x in rr),
            sum(x['outcome']=='invalid' for x in rr),sum(x['effort']['done_reason']=='length' for x in rr)]
        h.append('<tr><th>'+escape(p['label'])+'</th>'+''.join(f'<td>{c}</td>' for c in counts)+'</tr>')
    h.append('</table><p>The held 2 Kings 7:17–18 question remains excluded. All 390 active grammar versions passed their saved review checks. '
             'Exact displayed passages, model request snapshots, raw responses, available thinking traces and mapping records are retained. '
             'No live pilot content was changed.</p></html>')
    (output/'index.html').write_text(''.join(h))
    r.old.save(output/'verification.json',dict(complete=True,questions=65,passages=10,observations=len(rows),
        new_observations=2058,preserved_observations=1127,summary_cells=len(summary),per_model_condition_n=65,
        same_frozen_protocol=True,source_hashes_unchanged=True,raw_response_scores_recomputed=True,
        actual_server_models_verified=True,exact_grammar_passages_in_prompts_verified=True,
        full_clean_passages_not_leaked_to_grammar_prompts=True,all_active_questions_covered_once_per_setting=True,
        preserved_runs_unchanged=True,held_officer_question_excluded=True,
        outcomes=dict(Counter(x['outcome'] for x in rows)),
        direct_e=sum(x['choice']=='E' and x['scoring_method']=='rules' for x in rows),
        mapped_e=sum(x['choice']=='E' and x['scoring_method']=='gpt-4.1-mini mapping' for x in rows),
        length_limited=sum(x['effort']['done_reason']=='length' for x in rows),
        sources=[dict(label=p['label'],n=p['n'],hashes=p['hashes']) for p in passages],
        report_sha256=sha256((output/'index.html').read_bytes()).hexdigest(),published=False))
    print('REPORT',output/'index.html',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUTPUT)
    report(p.parse_args().output)
