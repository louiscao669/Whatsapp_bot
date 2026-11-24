"""Generate reviewed 15% previews beside ten frozen, reviewed 30% windows."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
from html import escape
import os
from pathlib import Path

from evaluation.scripts.pipeline import build_nested_window_defects as n

m = n.m


def deleted_positions(edits):
    return set().union(*(m.points(e) for e in edits))


def build_one(w, original, source, folder):
    path = folder / 'preview.json'
    configuration = dict(window_id=w['id'], clean_sha256=m.clean_digest(w['clean']),
        original_sha256=m.clean_digest(original), target=15, tolerance_pp=2,
        reviewer=m.review.JUDGE, review_prompt_sha256=m.clean_digest(m.COMBINED_REVIEW),
        max_nested_attempts=3, max_independent_attempts=3)
    state = m.review.read(path) if path.exists() else dict(configuration=configuration,
        history=[], attempts=[], cells={'30': deepcopy(original['cells']['30'])})
    if state['configuration'] != configuration:
        raise ValueError('Preview inputs changed')
    if state['cells'].get('15', {}).get('status') in n.PASS:
        return state
    high = deleted_positions(state['cells']['30']['edits'])
    pool = deepcopy(original['pool'])
    nested_pool = [c for c in pool if deleted_positions(c['edits']) <= high]
    # A prerequisite bundle must remain available in the candidate subset.
    for _ in range(len(nested_pool)):
        ids = {c['id'] for c in nested_pool}
        nested_pool = [c for c in nested_pool if set(c.get('requires', [])) <= ids]
    with m.OpenAI(timeout=180, max_retries=2) as client:
        for mode, candidates in [('subset_of_30', nested_pool), ('independent_15', pool)]:
            for attempt in range(3):
                token = [mode, attempt]
                if any(a['token'] == token for a in state['attempts']):
                    continue
                banned = [(w['id'], 15, h['15']['selected_ids']) for h in state['history']
                    if h['15']['status'] in ('held', 'rejected')
                    and set(h['15']['selected_ids']) <= {c['id'] for c in candidates}]
                fit = n.plan([w], {w['id']: candidates}, 'omission', doses=(15,),
                    strict=True, banned=banned, seed=20261119+attempt)
                if fit is None:
                    state['attempts'].append(dict(token=token, result='no_in_band_selection'))
                    m.review.save(path, state)
                    break
                cell = n.materialize(w, candidates, fit['selected'][(w['id'], 15)], 'omission', 15)
                old = n.remembered_review(original['history']+state['history'], cell)
                n.apply_remembered_review(w, 15, cell, old)
                n.review_cells(client, w, {1: cell}, source, folder, 'omission')
                n.validate_chain(w, {'15': cell}, 'omission', doses=(15,))
                cell['deletions_contained_in_30'] = deleted_positions(cell['edits']) <= high
                state['cells']['15'] = cell
                state['history'].append({'15': deepcopy(cell)})
                state['attempts'].append(dict(token=token, result=cell['status'],
                    optimization_fallback_stages=fit.get('optimization_fallback_stages', [])))
                m.review.save(path, state)
                print(w['reference'], '15%', round(cell['actual_percent'], 1), cell['status'], mode, flush=True)
                if cell['status'] in n.PASS:
                    return state
    state['stop_reason'] = 'bounded_preview_selection_exhausted'
    m.review.save(path, state)
    return state


def report(data):
    p = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>10 omission questions · 30% and 15%</title>',
        '<style>body{font:16px/1.65 system-ui;max-width:1300px;margin:32px auto;padding:0 22px;color:#213c43}'
        'h1{line-height:1.2}h2{margin-top:2.5em}.note{background:#edf4f2;padding:16px;border-left:4px solid #378474}'
        '.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.card{background:#f3f6f5;border:1px solid #d6e1dd;border-radius:8px;padding:20px}'
        '.held{border-top:5px solid #a94827}.zh{font-size:18px}small{color:#536973}li{margin:.45em 0}'
        'summary{cursor:pointer;font-weight:600}details{margin:14px 0}del{background:#ffe5dc;color:#862e20}'
        'a{color:#08677a}select{padding:8px;margin:14px 0;font:inherit}body[data-view="30"] .dose15,body[data-view="15"] .dose30{display:none}'
        'body[data-view="30"] .grid,body[data-view="15"] .grid{grid-template-columns:1fr}'
        'table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #d5dfdc;text-align:left}'
        '@media(max-width:800px){.grid{grid-template-columns:1fr}}</style></head><body data-view="both">',
        '<h1>10 questions at 30% omission and 10 at 15%</h1>',
        '<p>The same ten from-scratch questions appear at both doses, one window from each Bible passage group. '
        'Each card contains the omission passage, question and unchanged answer options.</p>',
        '<div class="note">The 30% passages come from the completed November 19 nested run. '
        'The 15% passages are newly assembled from its reviewed omission candidates and reviewed with the updated '
        'five required checks. No manual passage or QA rewrites were inserted. '
        'Actual rates count deleted clean Chinese content characters, with ±2 percentage points allowed. '
        'Local preview only; not published.</div>',
        '<p>Pass with flags means all required checks passed; ambiguity or additional semantic distortion may still be recorded. '
        'The subset column says whether all text omitted at 15% is also omitted in the unchanged 30% version. '
        'This compares deleted source positions, not necessarily identical candidate bundles.</p>',
        '<table><tr><th>Window</th><th>30% actual / review</th><th>15% actual / review</th><th>15% deletions within 30%?</th></tr>']
    for index, row in enumerate(data['windows'], 1):
        a = row['cells']['30']; b = row['cells'].get('15')
        p.append('<tr><td><a href="#q'+str(index)+'">'+escape(row['reference'])+'</a></td><td>'+f'{a["actual_percent"]:.1f}% · '+escape(a['status'])+'</td><td>'+
            (f'{b["actual_percent"]:.1f}% · '+escape(b['status']) if b else 'Held: no selection')+'</td><td>'+
            ('Yes' if b and b['deletions_contained_in_30'] else 'No — independent selection')+'</td></tr>')
    p.append('</table><label>Show <select onchange="document.body.dataset.view=this.value"><option value="both">Both doses side by side</option><option value="30">30% only</option><option value="15">15% only</option></select></label>')
    for index, row in enumerate(data['windows'], 1):
        q = row['qa']
        p.append('<h2 id="q'+str(index)+'">'+str(index)+'. '+escape(row['reference'])+'</h2><div class="grid">')
        for dose in ('30', '15'):
            cell = row['cells'].get(dose)
            if not cell:
                p.append('<article class="card held dose15"><h3>15% held</h3><p>No reviewed, in-band selection was found.</p></article>')
                continue
            p.append('<article class="card dose'+dose+(' held' if cell['status'] not in n.PASS else '')+'"><h3>'+dose+'% omission</h3>'+
                '<p><small>'+f'{cell["actual_percent"]:.1f}% actual · {cell["affected_chars"]}/{row["clean_content_chars"]} characters · '+escape(cell['status'])+'</small></p>')
            p.extend('<p class="zh"><small>'+escape(v)+'</small>　'+escape(t)+'</p>' for v,t in cell['verses'].items())
            p.append('<h3 class="zh">'+escape(q['question'])+'</h3><ol type="A" class="zh">'+''.join('<li>'+escape(x)+'</li>' for x in q['choices'])+'</ol>')
            p.append('<details><summary>See removed text</summary>')
            for verse, body in row['clean'].items():
                cursor=0; parts=[]
                for e in sorted((e for e in cell['edits'] if e['verse']==verse), key=lambda e:e['start']):
                    parts.extend([escape(body[cursor:e['start']]),'<del>'+escape(e['before'])+'</del>']);cursor=e['start']+len(e['before'])
                parts.append(escape(body[cursor:]));p.append('<p class="zh">'+escape(verse)+'　'+''.join(parts)+'</p>')
            p.append('</details><details><summary>Review findings</summary><p>'+escape(cell.get('review',{}).get('reason',''))+'</p><p>'+escape(', '.join(cell.get('flags',[])))+'</p></details></article>')
        key_index = ord(q['correct'])-ord('A')
        p.append('</div><details><summary>Clean-source answer key</summary><p>'+escape(q['correct']+'. '+q['choices'][key_index])+ '</p><p>This key refers to the clean passage. Omission may remove its supporting evidence; it is not a fresh answerability judgment for either defective version.</p></details>')
    return ''.join(p)+'</body></html>'


def run(folder, report_path, workers=2):
    os.environ.setdefault('ETEN_REVIEW_BACKGROUND','1')
    m.load_dotenv(m.ROOT/'.env')
    source_path=m.ROOT/'evaluation/runs/sol_nested_defects_all66_2026-11-19/all_windows.json'
    original=m.review.read(source_path)['families']['omission']['windows']
    manifest=m.review.read(m.MANIFEST);sources=m.english_by_passage()
    banks=[(p.name,m.review.read(p)) for p in m.BANKS]
    qa_path=m.DATA/'qa/reviewed122_sol/zh.json';qas={q['id']:q for q in m.review.read(qa_path)}
    seen=set();windows=[]
    for raw in manifest['windows']:
        if raw['passage_id'] in seen:continue
        seen.add(raw['passage_id'])
        windows.append(m.load_candidates(manifest,banks,raw['passage_id'],sources)[0][0])
    assert len(windows)==10
    for w in windows:
        assert w['question']==qas[w['id']]['question']
        assert original[w['id']]['cells']['30']['status'] in n.PASS
    config=dict(source=str(source_path),source_sha256=sha256(source_path.read_bytes()).hexdigest(),
        qa_sha256=sha256(qa_path.read_bytes()).hexdigest(),
        selection='First active manifest window in each of ten passage groups; same IDs at both doses',
        selected_ids=[w['id'] for w in windows],published=False)
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'configuration.json').exists() and m.review.read(folder/'configuration.json')!=config:
        raise ValueError('Preview configuration changed')
    m.review.save(folder/'configuration.json',config)
    errors={}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks={executor.submit(build_one,w,original[w['id']],sources[w['passage_id']],folder/m.clean_digest(w['id'])[:16]):w for w in windows}
        for future in as_completed(tasks):
            w=tasks[future]
            try:future.result()
            except Exception as exc:errors[w['id']]=type(exc).__name__+': '+str(exc)[:500]
    output=dict(configuration=config,windows=[],execution_errors=errors,published=False)
    for w in windows:
        state=m.review.read(folder/m.clean_digest(w['id'])[:16]/'preview.json')
        output['windows'].append(dict(id=w['id'],reference=original[w['id']]['reference'],qa=qas[w['id']],
            clean=w['clean'],clean_content_chars=w['clean_content_chars'],**state))
    m.review.save(folder/'examples.json',output)
    report_path.write_text(report(output),encoding='utf-8')
    if errors:raise RuntimeError(str(errors))
    print('REPORT',report_path,flush=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--workers',type=int,choices=(1,2,3,4),default=2)
    args=parser.parse_args();run(args.output,args.report,args.workers)
