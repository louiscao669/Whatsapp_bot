"""Review existing grammar edits and their displayed windows without rewriting them."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from html import escape
import json
from pathlib import Path

from dotenv import load_dotenv

from evaluation.scripts.variants.current import create_grammar_variants as g

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / 'evaluation/datasets/passages/sol_scratch66_windows_v1.json'
DEFAULT_RUN = ROOT / 'evaluation/runs/sol_1kgs13_grammar_semantic_risk_2026-11-22'
DEFAULT_REPORT = ROOT / 'deliverables/sol_1kgs13_grammar_semantic_risk.html'
ALL_RUN = ROOT / 'evaluation/runs/sol_all65_grammar_semantic_risk_2026-11-22'
ALL_REPORT = ROOT / 'deliverables/sol_all65_grammar_semantic_risk.html'
SEVERITY = {'pass': 0, 'flagged': 1, 'needs_repair': 2}
LABELS = {'pass': 'Pass', 'flagged': 'Flagged for review', 'needs_repair': 'Needs repair'}
BOOKS = {'t1_1kgs13': '1 Kings', 't1_2chr26': '2 Chronicles',
         't1_2kgs11': '2 Kings', 't1_2kgs6_7': '2 Kings', 't1_2sam21': '2 Samuel',
         't1_acts19': 'Acts', 't1_acts20': 'Acts', 't1_acts23': 'Acts',
         't1_judg17_18': 'Judges', 't1_judg9': 'Judges'}
CACHE_FIELDS = {'grammar.json': 'judgments', 'combined_grammar.json': 'judgments',
                'meaning_readings.json': 'readings', 'meaning_judgments.json': 'reviews'}


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    g.write_json_atomic(path, value)


def render_passage(verses):
    parts = []; offsets = {}; cursor = 0
    for label, body in verses.items():
        prefix = label + '　'
        offsets[label] = cursor + len(prefix)
        line = prefix + body + '\n'
        parts.append(line); cursor += len(line)
    return ''.join(parts), offsets


def select_windows(manifest, all_active=False):
    windows = [w for w in manifest['windows'] if w['id'] not in manifest.get('held_for_review', [])
               and (all_active or w['passage_id'] == 't1_1kgs13')]
    expected = (65, 184) if all_active else (8, 24)
    actual = (len(windows), sum(len(w['conditions']['grammar30']['edits']) for w in windows))
    if actual != expected or len({w['id'] for w in windows}) != len(windows):
        raise ValueError(f'Expected {expected} windows/edits, got {actual}')
    return windows


def reference(window):
    start, end = window['verses'][0], window['verses'][-1]
    if start == end:
        span = start
    else:
        span = start + '–' + (end.split(':')[1] if start.split(':')[0] == end.split(':')[0] else end)
    return BOOKS[window['passage_id']] + ' ' + span


def edit_requests(window):
    """Each edit is contrasted in its actual displayed surrounding context.

    The blind reader sees the complete final window. For the paired comparison,
    only the focus edit is restored; the other displayed edits stay in place.
    A separate clean-versus-final review below checks combined semantic effects.
    """
    clean, _ = render_passage(window['conditions']['clean']['verses'])
    variant = window['conditions']['grammar30']
    shown, offsets = render_passage(variant['verses'])
    # Verify the complete displayed text is exactly the recorded replacements.
    rebuilt = dict(window['conditions']['clean']['verses'])
    for verse, original in rebuilt.items():
        cursor = 0; parts = []
        for edit in sorted((e for e in variant['edits'] if e['verse'] == verse), key=lambda e: e['start']):
            start = edit['start']; before = edit['before']
            if start < cursor or original[start:start + len(before)] != before:
                raise ValueError('Selected edit does not match displayed window source or overlaps another edit')
            parts.extend([original[cursor:start], edit['after']]);cursor = start + len(before)
        parts.append(original[cursor:]);rebuilt[verse] = ''.join(parts)
    if rebuilt != variant['verses']:
        raise ValueError('Displayed window contains unrecorded grammar changes')
    requests = []
    for i, edit in enumerate(variant['edits'], 1):
        start = offsets[edit['verse']] + edit['start']
        before, after = edit['before'], edit['after']
        if shown[start:start + len(after)] != after:
            raise ValueError('Selected edit does not match displayed window')
        if Counter(before) != Counter(after):
            raise ValueError('Selected grammar edit changed character inventory')
        context = shown[:start] + before + shown[start + len(after):]
        request = dict(original_passage=context, clause_start=start,
                       original_clause=before, edited_clause=after,
                       review_scope='one_edit_in_the_complete_displayed_window')
        if g.meaning_reader_request(request)['passage'] != shown:
            raise ValueError('Blind reader would see the wrong context')
        requests.append(dict(number=i, edit=edit, request=request))
    combined = dict(original_passage=clean, clause_start=0, original_clause=clean,
                    edited_clause=shown, review_scope='complete_displayed_window')
    return requests, combined


def evaluate(request, grammar_cache, meaning_cache):
    candidate = request['edited_clause']
    if not g.valid_structural_candidate(request['original_clause'], candidate, [g.LLM_OPERATION]):
        return dict(status='needs_repair', reason='Mechanical character, punctuation or protected-term check failed.',
                    grammar=None, meaning=None)
    grammar_id, judgment = grammar_cache.evaluate(request)
    meaning_id, meaning = meaning_cache.evaluate(request)
    return dict(status=g.grammar_review_outcome(judgment, meaning, candidate),
                grammar_id=grammar_id, meaning_id=meaning_id, grammar=judgment, meaning=meaning)


def review_window(window, folder, model, offline=False):
    folder.mkdir(parents=True, exist_ok=True)
    grammar = g.GrammarJudgmentCache(folder / 'grammar.json', model=model, offline=offline)
    sentences = g.GrammarJudgmentCache(folder / 'combined_grammar.json', model=model,
                                      offline=offline, unit_mode='sentence')
    meanings = g.GrammarMeaningCache(folder, model=model, offline=offline)
    requests, combined = edit_requests(window)
    rows = []
    for unit in requests:
        result = evaluate(unit['request'], grammar, meanings)
        rows.append(dict(number=unit['number'], **unit['edit'], **result))
        print(window['id'], 'edit', unit['number'], result['status'], flush=True)
    whole = evaluate(combined, sentences, meanings)
    overall = max([whole['status'], *(r['status'] for r in rows)], key=SEVERITY.__getitem__)
    result = dict(id=window['id'], passage_id=window['passage_id'], reference=reference(window),
                  clean=window['conditions']['clean']['verses'], shown=window['conditions']['grammar30']['verses'],
                  dose=100 * window['conditions']['grammar30']['affected_chars'] / window['clean_content_chars'],
                  edits=rows, combined=whole, status=overall)
    save(folder / 'result.json', result)
    print(window['id'], 'combined', whole['status'], 'overall', overall, flush=True)
    return result


def rationale(result):
    if result['grammar'] is None:
        return result['reason']
    return result['grammar']['explanation'] + '\n\n' + result['meaning']['judgment']['explanation']


def render_report(data, path):
    scope = 'All 65 active windows' if data['configuration'].get('all_active') else '1 Kings 13'
    edit_count = sum(len(w['edits']) for w in data['windows'])
    h = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>' + scope + ' · grammar review</title><style>body{max-width:1200px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;color:#233d43}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #d2dddd;text-align:left;vertical-align:top}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}.pass{color:#14724a}.flagged{color:#946400}.needs_repair{color:#ad3737}details{margin:15px 0;padding:12px;border:1px solid #d2dddd}summary{cursor:pointer}.note{background:#eef5f3;padding:15px}.scroll{overflow:auto}select{padding:8px;margin:10px}@media(max-width:760px){.grid{grid-template-columns:1fr}}</style>',
         '<h1>' + scope + ' · current Grammar 30% edits</h1>',
         f'<p>{edit_count} existing edits in {len(data["windows"])} windows. Review only: no passage, QA, assignment or published bank was changed.</p>',
         '<div class="note">Reading difficulty can pass when the underlying facts and roles remain recoverable. Newly plausible competing meanings and unresolved judgments are flagged for review. Clear meaning changes, unrecoverable meaning, broken words or insufficient grammatical disruption need repair. Flagged items are not automatic approvals. Each edit is checked in its final displayed context; a separate review compares the complete clean and edited window.</div>',
         '<p>Reviewer: ' + escape(data['configuration']['model']) + ' · Policy: ' + escape(g.MEANING_POLICY) + '</p>',
         '<h2>Results</h2><table><tr><th>Scope</th><th>Pass</th><th>Flagged</th><th>Needs repair</th></tr>']
    for name, counts in [('Individual edits', data['summary']['edits']), ('Complete-window comparisons', data['summary']['combined_windows']), ('Windows, including individual findings', data['summary']['windows'])]:
        h.append('<tr><th>' + name + '</th>' + ''.join('<td>' + str(counts.get(s, 0)) + '</td>' for s in SEVERITY) + '</tr>')
    h.append('</table><h2>Window summary</h2><div class="scroll"><table><tr><th>Window</th><th>Pass edits</th><th>Flagged edits</th><th>Repair edits</th><th>Combined review</th><th>Overall</th></tr>')
    for wi, window in enumerate(data['windows'], 1):
        counts = Counter(e['status'] for e in window['edits'])
        h.append(f'<tr><td><a href="#w{wi}">' + escape(window['reference']) + '</a></td>' + ''.join('<td>' + str(counts[s]) + '</td>' for s in SEVERITY) + '<td>' + LABELS[window['combined']['status']] + '</td><td>' + LABELS[window['status']] + '</td></tr>')
    h.append('</table></div><h2>Every edit</h2><label>Show <select id="status-filter"><option value="all">All edits</option><option value="attention">Flagged or needs repair</option><option value="pass">Pass</option><option value="flagged">Flagged</option><option value="needs_repair">Needs repair</option></select></label><div class="scroll"><table><tr><th>Window / edit</th><th>Clean</th><th>Current grammar wording</th><th>Result</th></tr>')
    for wi, window in enumerate(data['windows'], 1):
        for edit in window['edits']:
            h.append(f'<tr data-status="{edit["status"]}"><td><a href="#w{wi}e{edit["number"]}">' + escape(window['reference'] + ' · ' + str(edit['number'])) + '</a></td><td lang="zh">' + escape(edit['before']) + '</td><td lang="zh">' + escape(edit['after']) + '</td><td class="' + edit['status'] + '">' + LABELS[edit['status']] + '</td></tr>')
    h.append('</table></div>')
    for wi, window in enumerate(data['windows'], 1):
        h.append(f'<h2 id="w{wi}">' + escape(window['reference']) + '</h2><p>Actual dose: ' + f'{window["dose"]:.1f}%' + ' · Overall: ' + LABELS[window['status']] + ' · Combined-window reviewer: ' + LABELS[window['combined']['status']] + '</p><div class="grid">')
        for title, verses in [('Clean window', window['clean']), ('Displayed grammar window', window['shown'])]:
            h.append('<section><h3>' + title + '</h3>' + ''.join('<p lang="zh">' + escape(v + '　' + t) + '</p>' for v, t in verses.items()) + '</section>')
        h.append('</div><details><summary>Combined-window findings</summary><pre>' + escape(rationale(window['combined'])) + '</pre></details>')
        for edit in window['edits']:
            h.append(f'<details id="w{wi}e{edit["number"]}"><summary>' + escape('Edit ' + str(edit['number']) + ' · ' + edit['verse'] + ' · ' + LABELS[edit['status']]) + '</summary><p lang="zh">' + escape(edit['before']) + ' → ' + escape(edit['after']) + '</p><pre>' + escape(rationale(edit)) + '</pre>')
            if edit['meaning']:
                reading = edit['meaning']['candidate_reading']; judgment = edit['meaning']['judgment']
                h.append('<p>Processing difficulty: ' + escape(reading['processing_difficulty']) + ' · Semantic status: ' + escape(judgment['semantic_status']) + '</p><details><summary>Source-blind interpretation and review evidence</summary><pre>' + escape(json.dumps(dict(grammar=edit['grammar'], meaning=edit['meaning']), ensure_ascii=False, indent=2)) + '</pre></details>')
            h.append('</details>')
    h.append('<script>document.getElementById("status-filter").addEventListener("change",event=>{const s=event.target.value;document.querySelectorAll("tr[data-status]").forEach(row=>{row.hidden=!(s==="all"||(s==="attention"?row.dataset.status!=="pass":row.dataset.status===s));});});window.addEventListener("hashchange",()=>{const e=document.getElementById(location.hash.slice(1));if(e&&e.tagName==="DETAILS")e.open=true;});</script></html>');path.parent.mkdir(parents=True, exist_ok=True);path.write_text(''.join(h))


def reuse_cached_reviews(source, folder, windows, model):
    """Copy matching raw evidence; every reused record still passes cache validation."""
    source = source.resolve()
    cfg_path = source / 'configuration.json';cfg = read(cfg_path)
    if cfg['model'] != model or cfg['policy'] != g.MEANING_POLICY:
        raise ValueError('Cached review model or policy differs')
    for path in (MANIFEST, Path(g.__file__)):
        if cfg['inputs'].get(str(path.relative_to(ROOT))) != sha256(path.read_bytes()).hexdigest():
            raise ValueError('Cached review source or reviewer changed')
    reused = []
    for window in windows:
        name = g.json_digest(window['id'])[:16]
        if not (source / name).exists():
            continue
        for filename, field in CACHE_FIELDS.items():
            original = read(source / name / filename)
            target = folder / name / filename
            current = read(target) if target.exists() else {'schema_version': original['schema_version'], field: {}}
            if current['schema_version'] != original['schema_version']:
                raise ValueError('Incompatible cached review format')
            for key, record in original[field].items():
                if key in current[field] and current[field][key] != record:
                    raise ValueError('Conflicting cached review evidence')
                current[field][key] = record
            save(target, current)
        # No API call is possible here; mismatch fails before the wider run.
        review_window(window, folder / name, model, offline=True)
        reused.append(window['id'])
    return dict(source=str(source.relative_to(ROOT)),
                configuration_sha256=sha256(cfg_path.read_bytes()).hexdigest(), windows=reused)


def run(folder, report, model='gpt-6.1-sol', workers=3, offline=False, all_active=False, reuse_from=None):
    load_dotenv(ROOT / '.env')
    manifest = read(MANIFEST)
    windows = select_windows(manifest, all_active)
    for window in windows:
        edit_requests(window)  # Validate every window before making API calls.
    files = [MANIFEST, Path(g.__file__), Path(__file__)]
    cfg = dict(passage_id=None if all_active else 't1_1kgs13', all_active=all_active,
               window_ids=[w['id'] for w in windows], excluded_window_ids=manifest.get('held_for_review', []),
               model=model, policy=g.MEANING_POLICY,
               inputs={str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in files},
               review_only=True, questions_or_answers_sent=False, participant_data_sent=False)
    path = folder / 'configuration.json'
    if path.exists() and read(path) != cfg:
        raise ValueError('Review inputs changed; use a separate review run')
    save(path, cfg)
    if reuse_from:
        save(folder / 'cache_reuse.json', reuse_cached_reviews(reuse_from, folder, windows, model))
    completed = {};errors = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(review_window, w, folder / g.json_digest(w['id'])[:16], model, offline): w for w in windows}
        for future in as_completed(futures):
            window = futures[future]
            try:completed[window['id']] = future.result()
            except Exception as exc:errors[window['id']] = type(exc).__name__ + ': ' + str(exc)
            save(folder / 'state.json', dict(completed=len(completed), expected=len(windows), errors=errors))
    if errors:
        raise RuntimeError('Review incomplete; cached results are resumable. ' + str(errors))
    for p in files:
        if sha256(p.read_bytes()).hexdigest() != cfg['inputs'][str(p.relative_to(ROOT))]:
            raise ValueError('Input changed during review')
    data = dict(configuration=cfg, windows=[completed[w['id']] for w in windows])
    data['summary'] = dict(edits=dict(Counter(e['status'] for w in data['windows'] for e in w['edits'])),
                           windows=dict(Counter(w['status'] for w in data['windows'])),
                           combined_windows=dict(Counter(w['combined']['status'] for w in data['windows'])))
    save(folder / 'results.json', data);render_report(data, report)
    save(folder / 'verification.json', dict(complete=True, windows=len(windows),
         edits=sum(len(w['conditions']['grammar30']['edits']) for w in windows),
         exact_displayed_contexts=True, input_hashes_unchanged=True, published_materials_changed=False,
         report_sha256=sha256(report.read_bytes()).hexdigest()))
    print('SUMMARY', data['summary'], flush=True);print('REPORT', report, flush=True)
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--all-active', action='store_true', help='Explicitly review all 65 active windows')
    parser.add_argument('--reuse-from', type=Path)
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=3)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    run(args.output or (ALL_RUN if args.all_active else DEFAULT_RUN),
        args.report or (ALL_REPORT if args.all_active else DEFAULT_REPORT),
        args.model, args.workers, args.offline, args.all_active, args.reuse_from)
