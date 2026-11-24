"""Repair held grammar variants; default model scope is 1 Kings 13 only."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from hashlib import sha256
from html import escape
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from evaluation.scripts.pipeline import build_mixed_grammar_ladder as b
from evaluation.scripts.variants.current import mixed_grammar as m
from evaluation.scripts.variants.current import mixed_grammar_ladder as ladder
from evaluation.scripts.variants.current import grammar_source_spans as spans

g = b.g
ROOT = b.ROOT
POLICY = 'held_grammar_reselection_and_replenishment_v1'
SOURCE = ROOT / 'evaluation/runs/sol_grammar_spans_mix3070_all65_adjudicated_2026-11-23/results.json'
CACHE_RUN = ROOT / 'evaluation/runs/sol_grammar_spans_mix3070_1kgs13_5_to_30_2026-11-23'
OUTPUT = ROOT / 'evaluation/runs/sol_grammar_spans_repair_1kgs13_2026-11-23'
REPORT = ROOT / 'deliverables/sol_grammar_spans_repair_1kgs13.html'
WRITER_PROMPT = b.SPAN_MISORDER_PROMPT + """
This is a repair, not a request to approve the old wording. Review findings and
manual rejections identify what must be avoided. Propose different edits from
the CLEAN clause, preferably on the failed clause and in the same error family.
Never preserve an accidental new noun compound, participant, ownership, quantity,
direction or event reading simply because the intended meaning is recoverable.
Do not repeat an existing rejected edit. Missing doses and previous failed
combinations are supplied as repair constraints, not permission to weaken any
rule. All proposals in this refill are misordering; the existing approved bank
also contains misselection edits, and final selection retains the pooled 30/70
preference. Do not write questions or answers.
"""


def selected(bank, variant):
    by_id = {c['candidate_id']: c for c in bank['candidates']}
    return [by_id[cid] for cid in variant.get('selected_ids', [])]


def initial_rows(bank, variants):
    """A new user rejection overrides a prior pass before freezing versions."""
    rows = {}
    for variant in variants:
        row = m.adjudications.apply_review(deepcopy(variant), selected(bank, variant))
        if row.get('manual_adjudications'):
            row['eligible_for_publication'] = False
        rows[row['rate']] = row
    return rows


def requested_windows(manifest, args):
    windows = b.select_windows(manifest, args.passage, args.exclude_passages)
    if args.window_ids:
        missing = set(args.window_ids) - {w['id'] for w in windows}
        if missing:
            raise ValueError(f'Requested windows outside active passage scope: {sorted(missing)}')
        windows = [w for w in windows if w['id'] in args.window_ids]
    return windows


def feedback(bank, variant):
    """Quarantine a unique implicated edit for repair, or only the failed draft.

    These contextual exclusions do not retroactively overturn other separately
    approved combinations. Explicit user rejections remain global pair rules.
    """
    if variant['status'] == 'pass': return None
    edits = selected(bank, variant)
    review = variant.get('combined') or {}
    risks = review.get('meaning', {}).get('judgment', {}).get('risk_spans', [])
    ids = {c['candidate_id'] for c in edits if m.adjudications.decisions_for(c)}
    matched = []
    for risk in risks:
        hits = [c for c in edits if risk and risk in c['after']]
        if len(hits) == 1:
            ids.add(hits[0]['candidate_id'])
            matched.append(dict(span=risk, candidate_id=hits[0]['candidate_id']))
    return dict(rate=variant['rate'], status=variant['status'],
        draft_sha256=variant.get('draft_sha256'),
        excluded_candidate_ids=sorted(ids), matched_risk_spans=matched,
        exclusion_scope='repair_selection_in_this_window',
        reason=b.b.reasons(review) if review else variant.get('reason', ''))


def options(bank, rate, findings, seed, draws=8):
    """Bounded seeded alternatives; unchanged failed wording is never retried."""
    excluded = {cid for row in findings for cid in row['excluded_candidate_ids']}
    failed = {row['draft_sha256'] for row in findings if row.get('draft_sha256')}
    pool = [c for c in bank['candidates'] if c['candidate_id'] not in excluded]
    found = {}
    for draw in range(draws):
        choices = ladder.combinations(pool, bank['clean_content_chars'], rate / 100,
            2, seed + draw * 7919, dose_basis='source_spans')
        for choice in choices:
            draft_hash = g.json_digest(m.apply_candidates(bank['clean'], choice['selected']))
            if draft_hash in failed: continue
            ids = tuple(sorted(c['candidate_id'] for c in choice['selected']))
            found.setdefault(ids, choice)
    return [found[key] for key in sorted(found)]


def refill(bank, window, findings, missing, round_number, args):
    folder = args.output / g.json_digest(bank['id'])[:16]
    units = [u for u in m.clauses(window) if u['content_chars'] >= 2]
    clean, offsets = m.render(bank['clean'])
    writer = m.StructuredCache(folder / 'repair_proposals.json', args.model,
        WRITER_PROMPT, b.MISORDER_SCHEMA, 'repair_misordering_writer', 7000, args.offline)
    request = dict(clean_passage=clean, eligible_clauses=units,
        protected_names=bank['protected_names'], max_candidates=args.max_extra,
        missing_doses=missing, round=round_number, repair_findings=findings,
        existing_candidates=[dict(candidate_id=c['candidate_id'], verse=c['verse'], start=c['start'],
            before=c['before'], after=c['after'], status=c['status'],
            affected_source_chars=c.get('dose_content_chars')) for c in bank['candidates']])
    proposal_id, response = writer.call(request)
    b.validate_extra(response, request)
    judge, _, meanings = b.reviewers(folder, args.model, args.offline)
    by_unit = {u['unit_index']: u for u in units}
    seen = {(c['verse'], c['start'], c['after']) for c in bank['candidates']}
    added = []
    for proposal in response['candidates']:
        unit = by_unit[proposal['unit_index']]
        key = unit['verse'], unit['start'], proposal['edited_clause']
        if key in seen: continue
        seen.add(key)
        c = dict(verse=unit['verse'], start=unit['start'], before=unit['text'],
            after=proposal['edited_clause'], content_chars=unit['content_chars'],
            subtype='misordering', family='misordering', provenance='model_grammar_repair_proposal',
            proposal_id=proposal_id, proposal_explanation=proposal['explanation'], repair_round=round_number)
        c['operations'] = m.edit_operations(c['before'], c['after'])
        c['candidate_id'] = g.json_digest(dict(window_id=bank['id'], **c))
        failures = m.hard_failures(c['before'], c['after'], c['subtype'], bank['protected_names'])
        if failures or m.adjudications.decisions_for(c):
            c.update(status='needs_repair', hard_failures=failures, grammar=None, meaning=None)
            c = m.adjudications.apply_candidate(c)
        else:
            paired = dict(original_passage=clean, clause_start=offsets[c['verse']] + c['start'],
                original_clause=c['before'], edited_clause=c['after'], proposed_subtype=c['subtype'],
                protected_names=bank['protected_names'], review_scope='one_edit_in_clean_window')
            c.update(b.b.review(paired, judge, meanings))
            c = spans.annotate(c)
        bank['candidates'].append(c); added.append(c['candidate_id'])
        m.save(folder / 'repair_candidates.json', bank)
        print(bank['id'], 'REPAIR CANDIDATE', c['status'], flush=True)
    bank.setdefault('repair_acquisition_history', []).append(dict(round=round_number,
        missing_doses=missing, proposal_id=proposal_id, added_ids=added,
        unavailable_reason=response['unavailable_reason']))
    return bank


def summaries(windows):
    rates = {}
    for rate in sorted({v['rate'] for w in windows for v in w['variants']}):
        vs = [v for w in windows for v in w['variants'] if v['rate'] == rate]
        def counts(rows):
            ss = [v['selection'] for v in rows if v['selection']]
            return dict(misselection=sum(s['misselection_count'] for s in ss),
                misordering=sum(s['edit_count']-s['misselection_count'] for s in ss))
        passed = [v for v in vs if v['status'] == 'pass']
        rates[f'{rate:g}'] = dict(statuses=dict(Counter(v['status'] for v in vs)),
            all_selected=counts(vs), passing_selected=counts(passed),
            passing_actual_doses=[v['selection']['actual_percent'] for v in passed])
    return dict(rates=rates, statuses=dict(Counter(v['status'] for w in windows for v in w['variants'])))


def render(data, changes, attempts, path):
    b.render_report(data, path)
    indexes = {w['id']: i for i, w in enumerate(data['windows'])}
    html = ['<h2>Repair results</h2><p>Previously passing versions are frozen unless a new explicit user rejection affects a selected edit. '
        'Held versions first use existing approved alternatives, with up to two '
        'additional repair rounds and up to six model proposals per affected window '
        'per replenishment round. Failed wording is not resubmitted for a different '
        'verdict. Contextual risk exclusions apply to repair selection; manual '
        'rejections override all selection. Family balance is a soft preference '
        f'across the {len(data["windows"])} windows at each dose, including frozen versions.</p>',
        '<table><tr><th>Window</th><th>Dose</th><th>Before</th><th>After</th><th>Review attempts</th></tr>']
    for row in changes:
        html.append(f'<tr><td><a href="#w{indexes[row["id"]]}r{row["rate"]:g}">'
            + escape(row['reference']) + f'</a></td><td>{row["rate"]:g}%</td><td>'
            + escape(row['before_status']) + '</td><td>' + escape(row['after_status'])
            + '</td><td>' + str(row['attempt_count']) + '</td></tr>')
    html.append('</table><h2>Changed edits</h2>')
    for row in changes:
        html.append('<details><summary>' + escape(row['reference']) + f' · {row["rate"]:g}%</summary>')
        for label, edits in [('Removed from prior draft', row['removed_edits']), ('Added to repaired draft', row['added_edits'])]:
            html.append('<p>' + label + '</p>')
            html.extend('<p lang="zh">' + escape(c['before']) + ' → ' + escape(c['after']) + '</p>' for c in edits)
        html.append('</details>')
    html.append('<h2>New repair candidates</h2>')
    for w in data['windows']:
        for c in w['candidates']:
            if c['provenance'] != 'model_grammar_repair_proposal': continue
            html.append('<details><summary>' + escape(w['reference'] + ' · ' + c['status'])
                + '</summary><p lang="zh">' + escape(c['before']) + ' → ' + escape(c['after'])
                + '</p><pre>' + escape(b.b.reasons(c)) + '</pre></details>')
    text = path.read_text().replace('<h2>Window overview</h2>', ''.join(html) + '<h2>Window overview</h2>')
    text = text.replace('Unattainable', 'No approved combination')
    path.write_text(text)


def run(args):
    load_dotenv(ROOT / '.env')
    source = b.b.read(args.source); manifest = b.b.read(b.b.audit.MANIFEST)
    windows = requested_windows(manifest, args)
    if not windows: raise ValueError('No active windows in requested scope')
    original = {w['id']: w for w in source['windows'] if w['id'] in {x['id'] for x in windows}}
    if len(original) != len(windows): raise ValueError('Source does not cover every requested window')
    if source['configuration']['dose_basis'] != 'source_spans': raise ValueError('Source-span input required')
    files = [Path(__file__), Path(b.__file__), Path(b.b.__file__), Path(m.__file__), Path(ladder.__file__),
        Path(spans.__file__), Path(g.__file__), Path(m.adjudications.__file__), args.source,
        args.cache_run / 'results.json', b.b.audit.MANIFEST, b.b.NAMES]
    cfg = dict(source['configuration'], repair_policy=POLICY, passage=args.passage, exclude_passages=args.exclude_passages,
        window_ids=[w['id'] for w in windows], model=args.model, repair_rounds=args.rounds,
        max_repair_candidates=args.max_extra, repair_seed=args.seed, alternative_draws=args.draws,
        repair_source=str(args.source), cache_run=str(args.cache_run),
        repair_source_files={str(p.resolve()): sha256(p.read_bytes()).hexdigest() for p in files},
        freeze_passing=True, user_rejections_override_frozen_pass=True,
        replenishment_family='misordering', manual_candidate_wording=False,
        reselection_performed=True, scope='Repair held versions in the requested windows; preserve passing versions except newly rejected edits',
        questions_sent=False, participant_data_sent=False, published=False)
    cfg.pop('new_model_calls', None)
    config = args.output / 'configuration.json'
    if config.exists() and b.b.read(config) != cfg: raise ValueError('Changed inputs; use a new output directory')
    m.save(config, cfg)
    banks = {}; rows = {}; findings = {}; attempts = []; plans = []; additions = []
    initial_statuses = {}
    names = b.b.read(b.b.NAMES)
    prep = SimpleNamespace(**vars(args)); prep.candidate_run=args.cache_run; prep.span_refill_rounds=0; prep.offline=True
    for w in windows:
        if w['conditions']['clean']['verses'] != original[w['id']]['clean']: raise ValueError('Stale clean source')
        bank = b.prepare_span_bank(w, prep, names)
        banks[w['id']] = bank
        rows[w['id']] = initial_rows(bank, original[w['id']]['variants'])
        initial_statuses[w['id']] = {rate: v['status'] for rate, v in rows[w['id']].items()}
        prior_findings = deepcopy(original[w['id']].get('repair_findings', []))
        prior_findings += [f for v in rows[w['id']].values() if (f := feedback(bank, v))]
        findings[w['id']] = list({g.json_digest(f): f for f in prior_findings}.values())
    targets = {(wid, rate) for wid, vs in rows.items() for rate, v in vs.items() if v['status'] != 'pass'}
    def checkpoint(stage, round_number):
        pending = [(wid, rate) for wid, rate in sorted(targets) if rows[wid][rate]['status'] != 'pass']
        m.save(args.output / 'state.json', dict(stage=stage, round=round_number, targets=len(targets),
            repaired=len(targets)-len(pending), pending=pending))
        m.save(args.output / 'repair_attempts.json', attempts)
        m.save(args.output / 'repair_findings.json', findings)
        m.save(args.output / 'selection_plans.json', plans)
    last_attempt_round = 0
    for round_number in range(args.rounds + 1):
        pending = {(wid, rate) for wid, rate in targets if rows[wid][rate]['status'] != 'pass'}
        if not pending: break
        last_attempt_round = round_number
        checkpoint('selecting', round_number)
        def get_options(wid, rate):
            return options(banks[wid], rate, findings[wid],
                args.seed + g.seed_offset(wid) + int(rate) + 100003 * round_number, args.draws)
        choices = {key: get_options(*key) for key in sorted(pending)}
        if round_number:
            missing = {wid: [rate for w, rate in sorted(pending) if w == wid and not choices[(w, rate)]] for wid in banks}
            jobs = {wid: rates for wid, rates in missing.items() if rates}
            checkpoint('replenishing', round_number)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(refill, banks[w['id']], w, findings[w['id']], jobs[w['id']], round_number, args): w['id']
                    for w in windows if w['id'] in jobs}
                for future in as_completed(futures):
                    wid=futures[future]; banks[wid]=future.result()
                    for w,rate in sorted(pending):
                        if w == wid: choices[(wid,rate)] = get_options(wid,rate)
                    additions.append(dict(window_id=wid, round=round_number,
                        acquisition=banks[wid]['repair_acquisition_history'][-1]))
                    m.save(args.output / 'replenishment_history.json', additions)
        scheduled = {wid: [] for wid in banks}
        for rate in cfg['rates']:
            per_window = {}
            for wid, bank in banks.items():
                if rows[wid][rate]['status'] == 'pass':
                    per_window[wid] = [dict(rows[wid][rate]['selection'], selected=selected(bank, rows[wid][rate]))]
                else: per_window[wid] = choices.get((wid,rate), [])
            plan = ladder.balance_windows(per_window, cfg['misselection_share'], args.seed + int(rate), dose_basis='source_spans')
            plans.append(dict(round=round_number, rate=rate, **plan))
            for wid, choice in plan['choices'].items():
                if (wid,rate) in pending: scheduled[wid].append((rate,choice))
        checkpoint('reviewing', round_number)
        review_args = SimpleNamespace(**vars(args)); review_args.dose_basis='source_spans'
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(b.review_variants, banks[wid], selections, review_args):wid
                for wid,selections in scheduled.items() if selections}
            for future in as_completed(futures):
                wid=futures[future]; result=future.result()
                for v in result['variants']:
                    key=(wid,v['rate'])
                    failed_hashes={f['draft_sha256'] for f in findings[wid] if f.get('draft_sha256')}
                    if v['draft_sha256'] in failed_hashes: raise ValueError('Unchanged failed draft was retried')
                    v['repair_round']=round_number
                    rows[wid][v['rate']]=v
                    attempts.append(dict(window_id=wid, round=round_number, variant=deepcopy(v)))
                    f=feedback(banks[wid],v)
                    if f: findings[wid].append(f)
                checkpoint('reviewing', round_number)
    output_windows=[dict(**banks[w['id']], variants=[rows[w['id']][r] for r in cfg['rates']],
                         repair_findings=findings[w['id']]) for w in windows]
    data=dict(configuration=cfg,windows=output_windows,summary=summaries(output_windows))
    changes=[]
    for w in output_windows:
        for v in w['variants']:
            old=next(vv for vv in original[w['id']]['variants'] if vv['rate']==v['rate'])
            if initial_statuses[w['id']][v['rate']]=='pass':
                if v!=old: raise ValueError('A frozen passing version changed')
            else:
                old_ids=set(old.get('selected_ids',[])); new_ids=set(v.get('selected_ids',[]))
                changes.append(dict(id=w['id'],reference=w['reference'],rate=v['rate'],
                    before_status=old['status'],after_status=v['status'],
                    initial_effective_status=initial_statuses[w['id']][v['rate']],
                    attempt_count=sum(a['window_id']==w['id'] and a['variant']['rate']==v['rate'] for a in attempts),
                    changed=old.get('draft')!=v.get('draft'),
                    removed_edits=[c for c in w['candidates'] if c['candidate_id'] in old_ids-new_ids],
                    added_edits=[c for c in w['candidates'] if c['candidate_id'] in new_ids-old_ids]))
            if not v['selection']: continue
            edits=selected(w,v)
            if m.apply_candidates(w['clean'],edits)!=v['draft']: raise ValueError('Draft reconstruction failed')
            if spans.selection_footprint(edits)['affected_chars']!=v['selection']['affected_chars']: raise ValueError('Dose footprint mismatch')
            if abs(v['selection']['actual_percent']-v['rate'])>2+1e-9: raise ValueError('Dose tolerance exceeded')
            if v['status']=='pass' and not all(m.adjudications.eligible(c) for c in edits): raise ValueError('Rejected edit passed')
            shown,_=m.render(v['draft'])
            model_status=m.outcome(v['combined']['grammar'],v['combined']['meaning'],shown)
            effective=m.adjudications.apply_review(dict(status=model_status),edits)['status']
            if effective!=v['status']: raise ValueError('Final status differs from review evidence')
    for path,digest in cfg['repair_source_files'].items():
        if sha256(Path(path).read_bytes()).hexdigest()!=digest: raise ValueError('Source changed during repair')
    m.save(args.output/'results.json',data)
    m.save(args.output/'repair_changes.json',changes)
    m.save(args.output/'held_variants.json',[dict(id=w['id'],reference=w['reference'],**v) for w in output_windows for v in w['variants'] if v['status']!='pass'])
    m.save(args.output/'approved_window_drafts.json',dict(published=False,windows=[dict(id=w['id'],source_sha256=w['source_sha256'],
        variants=[v for v in w['variants'] if v['status']=='pass']) for w in output_windows]))
    for w in output_windows: m.save(args.output/g.json_digest(w['id'])[:16]/'ladder_variants.json',w['variants'])
    render(data,changes,attempts,args.report)
    m.save(args.output/'verification.json',dict(complete=True,source_files_unchanged=True,
        passing_versions_frozen=True,exact_reconstruction=True,source_span_doses_verified=True,
        manual_rejections_enforced=True,unchanged_failed_drafts_not_retried=True,
        manual_wording_added=False,published_materials_changed=False,
        report_sha256=sha256(args.report.read_bytes()).hexdigest()))
    checkpoint('complete',last_attempt_round)
    print('SUMMARY',data['summary']['statuses'],flush=True)
    return data


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=SOURCE)
    p.add_argument('--cache-run',type=Path,default=CACHE_RUN)
    p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--report',type=Path,default=REPORT)
    p.add_argument('--passage',default='t1_1kgs13')
    p.add_argument('--exclude-passages',nargs='*',default=[],help='Preserve separately completed passage trials')
    p.add_argument('--window-ids',nargs='+',default=[],help='Limit repair to these active windows within the passage scope')
    p.add_argument('--model',default='gpt-6.1-sol')
    p.add_argument('--rounds',type=int,choices=(1,2),default=2)
    p.add_argument('--max-extra',type=int,choices=range(1,7),default=6)
    p.add_argument('--draws',type=int,choices=(4,8,16),default=8)
    p.add_argument('--workers',type=int,choices=range(1,9),default=4)
    p.add_argument('--seed',type=int,default=20261123)
    p.add_argument('--offline',action='store_true')
    args=p.parse_args(argv)
    for field in ('source','cache_run','output','report'): setattr(args,field,getattr(args,field).resolve())
    if args.output in (args.source.parent,args.cache_run): p.error('Use a new repair output directory')
    if args.passage!='t1_1kgs13' and (args.output==OUTPUT or args.report==REPORT):
        p.error('Expanded scope needs separate output and report paths')
    return args


if __name__=='__main__': run(parse_args())
