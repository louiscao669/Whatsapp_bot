"""Run the established seven SLM settings on approved source-span grammar drafts."""
import argparse
from collections import Counter
import fcntl
from hashlib import sha256
from html import escape
from pathlib import Path

from dotenv import load_dotenv
import requests

from evaluation.scripts.campaigns.current import run_window_dose_readers as runner
from evaluation.scripts.variants.current import mixed_grammar as grammar
from evaluation.scripts.variants.current import grammar_source_spans as spans

old = runner.old
ROOT = runner.ROOT
DOSES = (5, 10, 15, 20, 25, 30)
BANK = ROOT / 'evaluation/runs/sol_grammar_spans_repair_all65_speech_2026-11-23/results.json'


def stimuli_from_bank(bank, qas, passage_id):
    if bank['configuration']['dose_basis'] != 'source_spans':
        raise ValueError('Expected affected-source-span grammar doses')
    lookup = {q['id']: q for q in qas}
    windows = [w for w in bank['windows'] if lookup[w['id']]['passage_id'] == passage_id]
    if not windows:
        raise ValueError('No active windows for this passage')
    stimuli = []
    for w in windows:
        q = lookup[w['id']]
        if q['source'] != 'Hard77' or q['verses'] != w['clean']:
            raise ValueError('QA or clean window differs from reviewed source')
        if w['source_sha256'] != grammar.g.json_digest(w['clean']):
            raise ValueError('Stale clean source hash')
        if sum(grammar.g.content_len(t) for t in w['clean'].values()) != w['clean_content_chars']:
            raise ValueError('Incorrect clean character denominator')
        stimuli.append(dict(item=w['id'], reference=w['reference'], qa=q, family='clean', dose=0,
            actual_percent=0, review_status='clean', passage=' '.join(w['clean'].values()), verses=w['clean']))
    for dose in DOSES:
        for w in windows:
            variants = [v for v in w['variants'] if v['rate'] == dose]
            if len(variants) != 1:
                raise ValueError('Missing or duplicate grammar dose')
            v = variants[0]
            if v['status'] != 'pass' or not v['eligible_for_publication']:
                raise ValueError('Held grammar version cannot enter reader run')
            cs = {c['candidate_id']: c for c in w['candidates']}
            edits = [cs[cid] for cid in v['selected_ids']]
            if not all(grammar.adjudications.eligible(c) for c in edits):
                raise ValueError('Rejected edit cannot enter reader run')
            if grammar.apply_candidates(w['clean'], edits) != v['draft']:
                raise ValueError('Draft differs from selected edits')
            if grammar.g.json_digest(v['draft']) != v['draft_sha256']:
                raise ValueError('Changed reviewed draft')
            footprint = spans.selection_footprint(edits)
            actual = 100 * footprint['affected_chars'] / w['clean_content_chars']
            if footprint['source_positions'] != v['selection']['affected_source_positions'] or \
                    footprint['affected_chars'] != v['selection']['affected_chars'] or \
                    abs(actual-v['selection']['actual_percent']) > 1e-9 or abs(actual-dose) > 2+1e-9:
                raise ValueError('Incorrect grammar dose')
            shown, _ = grammar.render(v['draft'])
            if grammar.outcome(v['combined']['grammar'], v['combined']['meaning'], shown) != 'pass':
                raise ValueError('Full-window review does not pass')
            stimuli.append(dict(item=w['id'], reference=w['reference'], qa=lookup[w['id']],
                family='grammar', dose=dose, actual_percent=actual, review_status='pass',
                passage=' '.join(v['draft'].values()), verses=v['draft'], edits=edits))
    return stimuli


def prepare(args):
    stimuli = stimuli_from_bank(old.read(args.bank), old.read(runner.QA), args.passage_id)
    with requests.Session() as session:
        response = session.get(old.LOCAL+'/api/tags', timeout=20)
        response.raise_for_status(); inventory = response.json()['models']
        response = session.get(old.LOCAL+'/api/version', timeout=20)
        response.raise_for_status(); version = response.json()
    names = {m for m, _ in old.MODELS}
    weights = {m['name']: m['digest'] for m in inventory if m['name'] in names}
    historical = old.read(old.RUN/'design.json')['models']
    if set(weights) != names or any(weights[k] != historical[k] for k in weights):
        raise ValueError('Local model missing or weights differ from original experiment')
    jobs = runner.request_jobs(stimuli, weights)
    files = [args.bank, runner.QA, Path(__file__), Path(runner.__file__), Path(old.__file__),
             Path(old.gen.__file__), Path(old.small.__file__), Path(grammar.__file__),
             Path(spans.__file__), Path(grammar.adjudications.__file__)]
    design = dict(version='approved_grammar_source_span_readers_v1', passage_id=args.passage_id,
        question_ids=[s['item'] for s in stimuli if s['family']=='clean'], doses=list(DOSES), families=['grammar'],
        models=[dict(model=m, thinking=t, label=runner.LABELS[i]) for i, (m,t) in enumerate(old.MODELS)],
        weights=weights, inference=old.CONFIG, ollama_version=version,
        input_sha256={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files},
        stimuli_sha256=old.digest(stimuli), requests_sha256=old.digest(jobs), expected=len(jobs),
        scoring=dict(key='clean-source reference answer', abstention='E', mapper=old.JUDGE,
            mapper_scope='Unmatched nonempty answers from the four primary reader settings only',
            mapper_input='Reader answer and options only; no passage, question or key', random_fallback=False),
        protocol='Same seven model settings and reader-specific prompts as prior dose experiments; '
            'temperature 0, 8192-token context, 2500 generated-token cap including thinking. '
            'Fresh conversation per question and condition; raw responses and thinking retained. '
            'Clean baseline included. Exact request checkpoints reused only when resuming this run.',
        dose_basis='affected_clean_source_characters', tolerance_pp=2,
        grammar_mix_preference=dict(misselection=.30, misordering=.70, basis='error instances, soft preference'),
        nested=False, published=False)
    path = args.output/'design.json'
    if path.exists() and old.read(path) != design:
        raise ValueError('Frozen experiment changed; use a new output directory')
    old.save(path,design); old.save(args.output/'stimuli.json',stimuli)
    old.save(args.output/'requests.json',jobs)
    old.save(args.output/'model_inventory.json',[m for m in inventory if m['name'] in names])
    print('PREPARED',len(design['question_ids']),'questions',len(jobs),'responses',flush=True)
    return design,jobs


def summarize(records, design):
    summaries = []
    for i, (model,thinking) in enumerate(old.MODELS):
        for dose in (0,*DOSES):
            family = 'clean' if dose==0 else 'grammar'
            rows = [r for r in records if (r['reader_index'],r['family'],r['dose'])==(i,family,dose)]
            if len(rows)!=len(design['question_ids']) or {r['item'] for r in rows}!=set(design['question_ids']):
                raise ValueError('Missing or duplicate reader observations')
            counts=Counter(r['outcome'] for r in rows)
            summaries.append(dict(reader_index=i, label=runner.LABELS[i], model=model, thinking=thinking,
                family=family, dose=dose, n=len(rows), **{k:counts[k] for k in ('correct','incorrect','abstain','invalid')},
                accuracy=counts['correct']/len(rows), abstention_rate=counts['abstain']/len(rows),
                mean_actual_percent=sum(r['actual_percent'] for r in rows)/len(rows),
                generated_tokens=sum(r['effort']['output_tokens'] or 0 for r in rows),
                length_limited=sum(r['effort']['done_reason']=='length' for r in rows)))
    return summaries


def report(args,design,jobs):
    # The shared collector validates all requests, scores choices and saves thinking.
    # Its historical omission/mistranslation summaries are intentionally unused.
    records,_ = runner.results(args.output,design,jobs)
    summaries = summarize(records,design)
    args.report_dir.mkdir(parents=True,exist_ok=True)
    old.save(args.report_dir/'results.json',records); old.save(args.report_dir/'summary.json',summaries)
    title=runner.passage_label(records); n=len(design['question_ids'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    for metric,label in [('accuracy','Correct against clean-source key'),('abstention_rate','Cannot determine (E)')]:
        fig,axes=plt.subplots(2,4,figsize=(14,7),sharex=True,sharey=True)
        for i,ax in enumerate(axes.flat[:7]):
            rows=[s for s in summaries if s['reader_index']==i]
            ax.plot([s['dose'] for s in rows],[s[metric] for s in rows],marker='o',color='#167d8d',lw=2)
            ax.set_title(runner.LABELS[i],fontsize=10)
            ax.set_xticks([0,*DOSES]); ax.set_ylim(-.04,1.04); ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.grid(alpha=.2); ax.tick_params(labelbottom=True,labelleft=True)
            ax.set_xlabel('Target grammar dose (%)')
        axes.flat[7].axis('off')
        axes.flat[7].text(0,.9,f'{n} questions per point\n0% = clean baseline\n\nE and invalid answers stay\nin the accuracy denominator.\n\nLines connect observations;\nno fitted curve.',va='top')
        fig.suptitle(f'{title} · {label}'); fig.tight_layout(rect=(0,0,1,.94))
        for ext in ('png','svg'):fig.savefig(args.report_dir/f'{metric}.{ext}',dpi=170)
        plt.close(fig)
    h=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
       '<title>'+escape(title)+' · grammar SLM experiment</title><style>body{max-width:1400px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;color:#213b42}img{max-width:100%}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left}details{border:1px solid #ccd8d6;padding:12px;margin:10px 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}.hidden{display:none}select{padding:8px}</style>',
       '<h1>'+escape(title)+' · grammar, 5–30%</h1>',
       f'<p>{n} from-scratch questions × 7 conditions × 7 reader settings = {len(records)} responses. '
       'Conditions are clean and six independently selected grammar doses. All defect versions passed the current grammar and meaning checks.</p>',
       '<p>Dose counts affected clean Chinese source characters, with ±2 percentage-point tolerance. '
       'The generation bank uses a soft preference of 30% misselection and 70% misordering by error instances. '
       'Accuracy is against the clean-source key. E (“无法判断”), wrong A–D answers, and invalid responses are reported separately. '
       f'One answer changes a score by {100/n:.1f} percentage points; this small run is exploratory.</p>',
       '<p>'+escape(design['protocol'])+' Unmatched nonempty answers from the first four settings use the established GPT-4.1-mini choice mapper, receiving only response text and choices. No passages were published.</p>',
       '<img src="accuracy.png" alt="Grammar accuracy by model and dose"><img src="abstention_rate.png" alt="Cannot-determine rate by model and dose">',
       '<h2>Correct / wrong / E / invalid</h2><p>Every cell has the same denominator: '+str(n)+'.</p><table><tr><th>Model</th>'+''.join(f'<th>{d}%</th>' for d in (0,*DOSES))+'</tr>']
    for i,label in enumerate(runner.LABELS):
        rows=[s for s in summaries if s['reader_index']==i]
        h.append('<tr><th>'+escape(label)+'</th>'+''.join('<td>'+' / '.join(str(s[k]) for k in ('correct','incorrect','abstain','invalid'))+'</td>' for s in rows)+'</tr>')
    h.append('</table><h2>Response checks</h2><table><tr><th>Model</th><th>Mapped choices</th><th>E from mapping</th><th>Hit token limit</th></tr>')
    for i,label in enumerate(runner.LABELS):
        rows=[r for r in records if r['reader_index']==i]
        counts=[sum(r['scoring_method']=='gpt-4.1-mini mapping' for r in rows),sum(r['scoring_method']=='gpt-4.1-mini mapping' and r['choice']=='E' for r in rows),sum(r['effort']['done_reason']=='length' for r in rows)]
        h.append('<tr><th>'+escape(label)+'</th>'+''.join(f'<td>{c}</td>' for c in counts)+'</tr>')
    h.append('</table><h2>Individual responses</h2>')
    for key,values in [('reader',[(str(i),v) for i,v in enumerate(runner.LABELS)]),('dose',[(str(d),str(d)+'%') for d in (0,*DOSES)])]:
        h.append(f'<select id="{key}"><option value="all">All {key}s</option>'+''.join(f'<option value="{v}">{escape(label)}</option>' for v,label in values)+'</select>')
    for r in records:
        h.append(f'<details class="item" data-reader="{r["reader_index"]}" data-dose="{r["dose"]}"><summary>'+escape(f'{r["label"]} · {r["dose"]}% · {r["reference"]} · {r["choice"] or "—"} · {r["outcome"]}')+'</summary>')
        h.append(f'<p>Actual dose: {r["actual_percent"]:.2f}% · Key: {r["key"]} · Scoring: '+escape(r['scoring_method'])+'</p><p lang="zh">'+escape(r['passage'])+'</p><h3>'+escape(r['question'])+'</h3><ol type="A">')
        h.extend('<li>'+escape(c)+'</li>' for c in r['choices']);h.append('</ol><pre>'+escape(r['answer'] or '(empty)')+'</pre>')
        h.append(f'<p>Generated tokens: {r["effort"]["output_tokens"]} · Stop reason: '+escape(str(r['effort']['done_reason']))+'</p>')
        if r['thinking_text']:h.append('<details><summary>Recorded thinking</summary><pre>'+escape(r['thinking_text'])+'</pre></details>')
        h.append('</details>')
    h.append('<script>for(const key of ["reader","dose"])document.getElementById(key).addEventListener("change",()=>{for(const item of document.querySelectorAll(".item")){item.classList.toggle("hidden",["reader","dose"].some(k=>document.getElementById(k).value!=="all"&&document.getElementById(k).value!==item.dataset[k]));}});</script></html>')
    (args.report_dir/'index.html').write_text(''.join(h))
    runner.verify_inputs(design)
    old.save(args.output/'verification.json',dict(observations=len(records), expected=design['expected'],
        unique_observations=len({(r['reader_index'],r['dose'],r['item']) for r in records}),
        per_cell_n=n, summary_cells=len(summaries), source_hashes_unchanged=True, model_weights_pinned=True,
        raw_responses_saved=True, thinking_traces_retained=True,
        mapped_responses=sum(r['scoring_method']=='gpt-4.1-mini mapping' for r in records),
        length_limited=sum(r['effort']['done_reason']=='length' for r in records),
        outcomes=dict(Counter(r['outcome'] for r in records)),published=False))
    old.save(args.output/'state.json',dict(status='complete',completed=len(records),expected=len(jobs)))
    print('REPORT',args.report_dir/'index.html',flush=True)
    return records,summaries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=('prepare','read','map','report','all'))
    p.add_argument('--bank',type=Path,default=BANK)
    p.add_argument('--passage-id',default='t1_1kgs13')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report-dir',type=Path,required=True)
    p.add_argument('--limit',type=int)
    args=p.parse_args();args.bank=args.bank.resolve()
    args.output.mkdir(parents=True,exist_ok=True);load_dotenv(ROOT/'.env')
    with (args.output/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.stage in ('prepare','all'):design,jobs=prepare(args)
        else:design,jobs=old.read(args.output/'design.json'),old.read(args.output/'requests.json')
        if args.stage in ('read','all'):runner.read_all(args.output,design,jobs,args.limit)
        if args.stage in ('map','all'):runner.map_unmatched(args.output,jobs)
        if args.stage in ('report','all'):report(args,design,jobs)


if __name__=='__main__':main()
