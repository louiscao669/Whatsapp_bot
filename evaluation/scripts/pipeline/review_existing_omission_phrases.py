"""Re-review the existing phrase bank with the shared five-check omission policy.

No new proposals. English localization and unit classification are not vetoes.
Candidate spans and previous verdicts are retained for local comparison only.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from evaluation.scripts.pipeline import review_omission_clauses as shared
from evaluation.scripts.pipeline.build_omission_phrase_bank import (
    DATA, ROOT, clean_digest, compile_bank, english_by_passage, locate, make_report,
)

PREVIOUS = DATA / 'perturbations/sol_scratch66_omission_phrase_bank_auto_v4.json'
BANK = DATA / 'perturbations/sol_scratch66_omission_phrase_bank_auto_v5.json'
REPORT = ROOT / 'deliverables/sol_scratch66_omission_phrases_auto_v5.html'
RUN = ROOT / 'evaluation/runs/sol_scratch66_omission_phrase_review_v5'


def prepare_existing(prior, manifest, sources):
    """Validate all Chinese locations without requiring a narrow English quotation."""
    if prior.get('unit') != 'phrase' or prior.get('mode') != 'automatic':
        raise ValueError('Expected an existing automatic phrase bank')
    roster = dict(release=prior['release'], provenance='Existing phrase candidates; no new proposals.',
        windows=[dict(window_id=w['window_id'], clean_zh_sha256=w['clean_zh_sha256'], phrases=[])
                 for w in prior['windows']])
    bank = compile_bank(roster, manifest, sources)
    old_windows = {w['window_id']:w for w in prior['windows']}
    clean_windows = {w['id']:w['conditions']['clean']['verses'] for w in manifest['windows']}
    prepared = {}
    for w in bank['windows']:
        old = old_windows[w['window_id']]
        if any(w[k] != old[k] for k in ('passage_id','verses','clean_zh_sha256','english_sha256')):
            raise ValueError(f'Prior window no longer matches the source: {w["reference"]}')
        clean = clean_windows[w['window_id']]
        if [c['number'] for c in old['candidates']] != list(range(1,len(old['candidates'])+1)):
            raise ValueError('Prior candidate numbers must be unique and contiguous')
        rows = []
        for c in old['candidates']:
            p = c['proposal']; v = p['verse']
            if v not in clean:
                raise ValueError('Candidate verse is outside its displayed window')
            start = locate(clean[v], p['chinese'], p.get('chinese_occurrence'))
            e = dict(verse=v, start=start, before=p['chinese'], after='')
            if not shared.mis.content_len(e['before']) or ('edit' in c and c['edit'] != e):
                raise ValueError('Stored candidate differs from its exact Chinese proposal')
            rows.append(dict(c, edit=e))
        if len({shared.edit_key(c['edit']) for c in rows}) != len(rows):
            raise ValueError('Duplicate Chinese deletions in prior window')
        prepared[w['window_id']] = dict(old, candidates=rows)
        w['no_proposals_reason'] = old.get('no_proposals_reason', '')
    return bank, prepared


def outcome(c):
    return ('pass_with_flags' if c['flags'] else 'pass') if c['status']=='accepted' else c['status']


def process_existing_window(client, run_dir, w, clean, source, prior, selected, reviewer):
    fixed = [c['edit'] for c in prior['candidates']]
    reviewed = shared.process_window(client, run_dir, w, clean, source, selected,
        reviewer=reviewer, previous=prior, fixed_edits=fixed, expected_unit='phrase')
    for c, old in zip(reviewed['candidates'], prior['candidates'], strict=True):
        if c['original_edit'] != old['edit']:
            raise ValueError('Review changed the original candidate identity')
        c.update(previous_proposal=old['proposal'], previous_number=old['number'],
                 previous_flags=old.get('flags', []), previous_review_note=old.get('review_note', ''),
                 review_outcome=outcome(c))
    return reviewed


def review_jobs(tasks, workers):
    """Verify one nonempty review can run before dispatching the rest of the bank."""
    if not tasks:
        return
    index, args = tasks[0]
    yield index, process_existing_window(*args)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_existing_window, *args):i for i,args in tasks[1:]}
        try:
            for future in as_completed(futures):
                yield futures[future], future.result()
        except Exception:
            # Preserve completed receipts, but do not keep submitting queued work
            # after a quota/authentication failure or another terminal error.
            for future in futures:
                future.cancel()
            pool.shutdown(wait=True, cancel_futures=True)
            raise


def run(manifest_path, prior_path=PREVIOUS, bank_path=BANK, report_path=REPORT, run_dir=RUN,
        workers=8, reviewer=shared.JUDGE, passage_id=None):
    manifest = shared.read(manifest_path)
    prior = shared.read(prior_path)
    sources = english_by_passage()
    bank, prepared = prepare_existing(prior, manifest, sources)
    if passage_id is not None:
        selected_windows = [w for w in bank['windows'] if w['passage_id']==passage_id]
        if not selected_windows:
            raise ValueError(f'No existing phrase windows for passage {passage_id!r}')
        bank['windows'] = selected_windows
        # A passage trial must not masquerade as the full-bank review.
        if bank_path.resolve()==BANK.resolve():
            bank_path = BANK.with_name(f'{BANK.stem}_{passage_id}{BANK.suffix}')
        if report_path.resolve()==REPORT.resolve():
            report_path = REPORT.with_name(f'{REPORT.stem}_{passage_id}{REPORT.suffix}')
    if bank_path.resolve()==prior_path.resolve():
        raise ValueError('Keep the prior bank unchanged; choose a new output')
    bank['review_scope'] = dict(kind='passage' if passage_id else 'full_bank', passage_id=passage_id,
        window_count=len(bank['windows']),
        candidate_count=sum(len(prepared[w['window_id']]['candidates']) for w in bank['windows']))
    windows = {w['id']:w for w in manifest['windows']}
    bank.update(unit='phrase', mode='automatic', review_version=8, reviewer=reviewer,
        original_writer=prior.get('writer'), writer=prior.get('writer'),
        provenance=f'Existing phrase proposals from {prior_path.name}, re-reviewed independently by {reviewer}. '
            'No new proposals or manually written Chinese. Full bilingual windows were supplied without QAs, '
            'earlier verdicts, or earlier English alignments. Boundary repairs preserve removed words and character doses.',
        required_checks=list(shared.ClauseChecks.model_fields), information_loss_policy='content_review_unit_metadata',
        semantic_distortion_policy='flag', alignment_policy='full_window_nonblocking_localization',
        unit_policy='classification_only', uncertainty_policy='held', boundary_policy='repair_then_original_fallback',
        candidate_scope='existing_phrase_bank', previous_audit=str(prior_path),
        previous_bank_sha256=sha256(prior_path.read_bytes()).hexdigest(),
        manifest_sha256=clean_digest(manifest), reviewer_prompt_sha256=sha256(shared.REVIEW.encode()).hexdigest(),
        report_outcomes='four', review_only=True)
    selection = {}
    for w in manifest['windows']:
        selected = defaultdict(list)
        for condition in ('omission15','omission30'):
            for e in w['conditions'][condition]['edits']:
                selected[shared.edit_key(e)].append(condition)
        selection[w['id']] = dict(selected)
    load_dotenv(ROOT/'.env')
    print(f'Review scope: {passage_id or "full bank"}; {bank["review_scope"]["window_count"]} windows; '
          f'{bank["review_scope"]["candidate_count"]} existing candidates', flush=True)
    with OpenAI(timeout=150.0, max_retries=3) as client:
        jobs = [(i, (client, run_dir, w,
            windows[w['window_id']]['conditions']['clean']['verses'], sources[w['passage_id']],
            prepared[w['window_id']], selection[w['window_id']], reviewer))
            for i,w in enumerate(bank['windows'])]
        jobs.sort(key=lambda task: not prepared[bank['windows'][task[0]]['window_id']]['candidates'])
        for done, (index, w) in enumerate(review_jobs(jobs, workers),1):
            bank['windows'][index] = w
            print(f'{done}/{len(jobs)} {w["reference"]} {dict(Counter(c["review_outcome"] for c in w["candidates"]))}', flush=True)
    bank['outcome_counts'] = dict(Counter(c['review_outcome'] for w in bank['windows'] for c in w['candidates']))
    shared.save(bank_path, bank)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(make_report(bank, manifest, sources), encoding='utf-8')
    return bank


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DATA/'passages/sol_scratch66_windows_v1.json')
    parser.add_argument('--prior-bank', type=Path, default=PREVIOUS)
    parser.add_argument('--bank', type=Path, default=BANK)
    parser.add_argument('--report', type=Path, default=REPORT)
    parser.add_argument('--run', type=Path, default=RUN)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--passage-id', help='Review only this passage and its existing QA windows')
    args = parser.parse_args()
    run(args.manifest, args.prior_bank, args.bank, args.report, args.run, args.workers,
        passage_id=args.passage_id)


if __name__=='__main__':
    main()
