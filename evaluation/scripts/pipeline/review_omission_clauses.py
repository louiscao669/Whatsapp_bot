"""Review fixed omissions against full bilingual windows; size/alignment are metadata."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
import re
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from evaluation.scripts.pipeline.build_omission_phrase_bank import (
    DATA, ROOT, clean_digest, compile_bank, english_by_passage, make_report,
)
from evaluation.scripts.pipeline.build_prepared_window_conditions import omission, mis
from evaluation.scripts.pipeline.generate_omission_phrases import (
    JUDGE, Decision, WordInformationLoss, ask, excluded_word_marker, read, save, validate_reviews,
)
from evaluation.scripts.variants._common import CONTENT_CHAR_PATTERN

BANK = DATA / 'perturbations/sol_scratch66_omission_clause_bank_auto_v2.json'
REPORT = ROOT / 'deliverables/sol_scratch66_omission_clauses_auto_v2.html'
RUN = ROOT / 'evaluation/runs/sol_scratch66_automatic_omission_clauses_v2'
PREVIOUS = DATA / 'perturbations/sol_scratch66_omission_clause_bank_auto_v1.json'

REVIEW = """Independently review each deletion against the FULL paired English/clean Chinese
window and the EXACT edited Chinese verse. Candidates are separate alternatives, not cumulative.
No QA or answer key is supplied or should be inferred. Apply FIVE checks, yes/no/uncertain:
information_omitted: identify source-supported content no longer explicitly stated in the edited
statement. Mere emphasis removal or ellipsis expressing the SAME statement fails. Information
recoverable or repeated ELSEWHERE can pass with recoverable_from_context. Do not call a distinct
removed action information-preserving merely because its outcome survives.
fluent: remaining Chinese must be natural and grammatical in the displayed window. Use normal
Chinese allowance for implicit/recoverable subjects; removing an explicit subject does not
necessarily cause an error. Any punctuation boundary repairs have ALREADY been applied: judge
that exact supplied result, not an imagined unrepaired version. For a no, quote the specific
remaining construction and explain its problem, not merely that something was deleted.
deletion_only: mechanically verified exact deletion, without word additions or substitutions.
valid_in_context: original meaning and information loss must be supported by the FULL bilingual
window. English/Chinese may reorder, split, combine or distribute content. Do NOT require a single
continuous English match. Missing narrow alignment is not evidence of invalid meaning. A
concretely false source claim fails; unresolved substantive semantic uncertainty is held.
key_content_removed: a concrete participant, place, action/event, outcome, relationship, substantive
condition, cause, instruction or decision must disappear from the edited statement. It need not
be essential to the entire plot or answer a QA. Do not reject a real event merely as preparatory,
or a named setting merely as background. Exclude removal ONLY of a standalone discourse marker,
emphasis, minor decorative attribute, or redundant generic speech framing when attribution and
content remain explicit. Explain the particular content lost.

Unit size is CLASSIFICATION ONLY: word, phrase, clause, multiple_clauses, uncertain. A phrase,
implicit-subject clause, list item, dependent clause or compound span is not rejected for its size.
Record unit_kind and unit_reason for mixture accounting. There is NO valid_omission_unit gate.

Record source_alignment: localized, distributed or uncertain, with a reason. Supply zero or more
exact English evidence quotes with verse labels from the displayed window; they may be separated
or in different displayed verses. Quotes document the reading, not one-to-one alignment. If a
precise quote cannot be located, review the full paired window anyway. Alignment uncertainty alone
is a FLAG, not a failed check. Do not fabricate quotes or silently repair the Chinese.

Return information_loss with explicit source_information, edited_information and lost_content.
Its unaligned kind describes localization difficulty ONLY, not information-preserved or failure.
Use uncertain on a required check only for actual content/fluency uncertainty, not unit size or
narrow alignment. key_content_category is descriptive, not a separate veto; explain its reason.

Additional semantic distortion from deletion is a NONBLOCKING flag: other_meaning_changed or
possible_other_meaning_changed, explaining original/edited readings. ambiguous_reference and
recoverable_from_context also do not block acceptance. A recoverable referent need not make the
Chinese ungrammatical. Do not label awkward punctuation as semantic distortion.
All five yes => accepted; definite no => rejected; otherwise uncertain => held for review.
Give concrete failure evidence. Do not infer old decisions or try to achieve a pass rate."""

class ClauseChecks(BaseModel):
    information_omitted: Literal['yes','no','uncertain']
    fluent: Literal['yes','no','uncertain']
    deletion_only: Literal['yes','no','uncertain']
    valid_in_context: Literal['yes','no','uncertain']
    key_content_removed: Literal['yes','no','uncertain']

class Evidence(BaseModel):
    verse: str
    quote: str

class ClauseDecision(Decision):
    checks: ClauseChecks
    information_loss: WordInformationLoss
    key_content_category: str
    key_content_reason: str
    unit_kind: Literal['word','phrase','clause','multiple_clauses','uncertain']
    unit_reason: str
    source_alignment: Literal['localized','distributed','uncertain']
    alignment_reason: str
    english_evidence: list[Evidence]

class ClauseDecisions(BaseModel):
    decisions: list[ClauseDecision]

def validate_clause_reviews(result, numbers):
    validate_reviews(result, numbers)
    for d in result.decisions:
        if not all(s.strip() for s in (d.information_loss.source_information, d.information_loss.edited_information,
                d.information_loss.lost_content, d.key_content_category, d.key_content_reason,
                d.unit_reason, d.alignment_reason)):
            raise ValueError('Omission review needs before/after evidence and classification reasons')

def candidate_spans(clean):
    """Use actual splitter, clipping printed verse markers out of the edits."""
    candidates = []
    for verse, body in clean.items():
        prefix = verse.split(':')[1] + ' '
        cursor = 0
        for unit in omission.passage_units(prefix + body):
            raw = unit['text']
            lo, hi = max(0, cursor-len(prefix)), min(len(body), cursor+len(raw)-len(prefix))
            cursor += len(raw)
            if not unit['omittable'] or not unit['content_chars']:
                continue
            before = body[lo:hi]
            if mis.content_len(before) != unit['content_chars']:
                raise ValueError(f'Clause splitter changed visible span in {verse}')
            candidates.append(dict(verse=verse, start=lo, before=before, after=''))
        if cursor != len(prefix + body):
            raise ValueError(f'Clause splitter did not cover {verse}')
    return candidates

def repair_boundary(edit, body):
    """Preserve boundary quotes/terminal marks; never alter removed lexical content."""
    lo, hi = edit['start'], edit['start'] + len(edit['before'])
    if edit['after'] or body[lo:hi] != edit['before']:
        raise ValueError('Not an exact deletion in clean Chinese')
    quotes = '“”‘’「」『』'
    while lo < hi and body[lo] in quotes:
        lo += 1
    while hi > lo and body[hi-1] in quotes:
        hi -= 1
    # Last conjunct: include preceding separator, retain existing sentence terminator.
    if lo and hi > lo and body[lo-1] in '，；,;' and body[hi-1] in '。！？.!?':
        lo -= 1
        hi -= 1
    repaired = dict(edit, start=lo, before=body[lo:hi])
    if CONTENT_CHAR_PATTERN.findall(repaired['before']) != CONTENT_CHAR_PATTERN.findall(edit['before']):
        raise ValueError('Boundary repair changed lexical content')
    return repaired

def edit_key(e):
    return (e['verse'], e['start'], e['before'])

def chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start+size]

def apply_decision(row, decision, source, clean, expected_unit='clause'):
    checks = decision.checks.model_dump()
    checks['deletion_only'] = 'yes'  # Verified by source reconstruction.
    flags = set(decision.flags)
    if decision.unit_kind != expected_unit:
        flags.add('unit_' + decision.unit_kind)
    evidence, invalid = [], []
    for quote in decision.english_evidence:
        if quote.verse not in clean or not quote.quote.strip() or quote.quote not in source.english[quote.verse]:
            invalid.append(quote.model_dump())
        else:
            evidence.append(quote.model_dump())
    if decision.source_alignment == 'uncertain' or not evidence or invalid:
        flags.add('unverified_alignment')
    elif decision.source_alignment == 'distributed':
        flags.add('distributed_alignment')
    local = next((e for e in evidence if e['verse'] == row['edit']['verse']), None)
    if local:
        row['source_phrase'] = local['quote']
        row['source_start'] = source.english[local['verse']].find(local['quote'])
        row['proposal'].update(english=local['quote'], english_occurrence=1)
    failures = [k for k,v in checks.items() if v == 'no']
    uncertain = [k for k,v in checks.items() if v == 'uncertain']
    row.update(status='rejected' if failures else 'held' if uncertain else 'accepted', stage='model_review',
        checks=checks, issues=failures, review_holds=uncertain, review_note=decision.reason, flags=sorted(flags),
        reviews=[dict(stage='review', **decision.model_dump())], information_loss=decision.information_loss.model_dump(),
        key_content_category=decision.key_content_category, key_content_reason=decision.key_content_reason,
        unit_kind=decision.unit_kind, unit_reason=decision.unit_reason,
        source_alignment=decision.source_alignment, alignment_reason=decision.alignment_reason,
        english_evidence=evidence, invalid_english_evidence=invalid,
        check_overrides={k:v for k,v in checks.items() if v != decision.checks.model_dump()[k]})

def process_window(client, run, w, clean, source, selected, reviewer=JUDGE, previous=None,
                   fixed_edits=None, expected_unit='clause'):
    folder = run / sha256(w['window_id'].encode()).hexdigest()[:20]
    aligned = {v:dict(english=source.english[v], chinese=t) for v,t in clean.items()}
    rows = []
    old_rows = {edit_key(c['edit']):c for c in (previous or {}).get('candidates', [])}
    originals = candidate_spans(clean) if fixed_edits is None else fixed_edits
    for number, original in enumerate(originals, 1):
        e = repair_boundary(original, clean[original['verse']])
        v, start, before = e['verse'], e['start'], e['before']
        body = clean[v]; edited = body[:start] + body[start+len(before):]
        occurrence = [m.start() for m in re.finditer(re.escape(before), body)].index(start) + 1
        row = dict(number=number, id=f'{w["passage_id"]}/{v}/{start}-{start+len(before)}',
            proposal=dict(verse=v, chinese=before, chinese_occurrence=occurrence, english='', english_occurrence=None),
            edit=e, original_edit=original, boundary_repaired=(e != original), affected_chars=mis.content_len(before),
            resulting_verse=edited, source_phrase='', source_start=0, flags=[],
            selected_conditions=selected.get(edit_key(original), []),
            candidate_origin='existing_clause_splitter' if fixed_edits is None else 'existing_candidate_bank')
        if edit_key(original) in old_rows:
            old = old_rows[edit_key(original)]
            row.update(previous_status=old['status'], previous_issues=old['issues'])
        if not mis.content_len(edited):
            row.update(status='held', stage='eligibility_check', issues=[], review_holds=['empty_verse_policy'],
                review_note='Removal empties this verse. Held under the existing preserve-verse design constraint; omission validity was not judged.')
        elif excluded_word_marker(before):
            row.update(status='rejected', stage='eligibility_check', issues=['key_content_removed'], review_holds=[],
                key_content_category='excluded_marker', key_content_reason='Standalone marker excluded by the study content rule.',
                review_note='Removal only of a standalone marker is excluded by the explicit study rule.', unit_kind='word')
        rows.append(row)
    reviewable = [r for r in rows if 'status' not in r]
    for part in chunks(reviewable, 4):
        items = [dict(number=r['number'], verse=r['edit']['verse'], chinese_removed=r['edit']['before'],
            original_chinese_verse=clean[r['edit']['verse']], edited_chinese_verse=r['resulting_verse'],
            exact_deletion=r['edit']) for r in part]
        result = ask(client, folder, 'review', reviewer, REVIEW, dict(window=aligned, candidates=items),
            ClauseDecisions, lambda x:validate_clause_reviews(x, [r['number'] for r in part]))
        for d in result.decisions:
            apply_decision(rows[d.number-1], d, source, clean, expected_unit)
    # A terminal-mark repair can strand a temporal fragment that the original
    # comma would have joined to the next sentence. Freshly review original
    # boundaries before disqualifying a candidate whose repair did not pass.
    fallback = []
    for row in rows:
        if row['boundary_repaired'] and row['stage'] == 'model_review' and row['status'] != 'accepted':
            original = row['original_edit']
            v, start, before = original['verse'], original['start'], original['before']
            body = clean[v]
            occurrence = [m.start() for m in re.finditer(re.escape(before), body)].index(start) + 1
            alternative = dict(row, edit=original, boundary_repaired=False,
                id=f'{w["passage_id"]}/{v}/{start}-{start+len(before)}',
                proposal=dict(verse=v, chinese=before, chinese_occurrence=occurrence, english='', english_occurrence=None),
                resulting_verse=body[:start]+body[start+len(before):], source_phrase='', source_start=0)
            fallback.append(alternative)
    for part in chunks(fallback, 4):
        items = [dict(number=r['number'], verse=r['edit']['verse'], chinese_removed=r['edit']['before'],
            original_chinese_verse=clean[r['edit']['verse']], edited_chinese_verse=r['resulting_verse'],
            exact_deletion=r['edit']) for r in part]
        result = ask(client, folder, 'review-original-boundary', reviewer, REVIEW,
            dict(window=aligned, candidates=items), ClauseDecisions,
            lambda x:validate_clause_reviews(x, [r['number'] for r in part]))
        alternatives = {r['number']:r for r in part}
        for decision in result.decisions:
            original = alternatives[decision.number]
            apply_decision(original, decision, source, clean, expected_unit)
            repaired = rows[decision.number-1]
            choose_original = original['status'] == 'accepted' or (original['status'] == 'held' and repaired['status'] == 'rejected')
            chosen = dict(original if choose_original else repaired)
            chosen['boundary_repair_attempted'] = True
            chosen['boundary_attempts'] = [dict(kind=kind, edit=r['edit'], resulting_verse=r['resulting_verse'],
                status=r['status'], checks=r['checks'], issues=r['issues'], review_holds=r['review_holds'],
                flags=r['flags'], review_note=r['review_note'], reviews=r['reviews'])
                for kind,r in (('repaired',repaired),('original',original))]
            rows[decision.number-1] = chosen
    return dict(w, candidates=rows)

def run(manifest_path, bank_path=BANK, report_path=REPORT, run_dir=RUN, workers=8, reviewer=JUDGE, previous_path=PREVIOUS):
    manifest = read(manifest_path); sources = english_by_passage()
    windows = {w['id']:w for w in manifest['windows']}
    previous = read(previous_path) if previous_path and previous_path.exists() else None
    if previous and previous['manifest_sha256'] != clean_digest(manifest):
        raise ValueError('Previous audit belongs to a different passage manifest')
    prior_windows = {w['window_id']:w for w in previous['windows']} if previous else {}
    roster = dict(release=manifest['release'], provenance=(
        f'All existing omission-splitter units with deterministic punctuation-boundary repairs and independent full-window review by {reviewer}. '
        'Failed boundary repairs receive a fresh review of the original boundaries. Removed lexical content and doses are unchanged. '
        'No Chinese wording was written by hand. No QAs or prior decisions were sent to the reviewer.'),
        windows=[dict(window_id=w['id'], clean_zh_sha256=clean_digest(w['conditions']['clean']['verses']), phrases=[])
                 for w in manifest['windows']])
    bank = compile_bank(roster, manifest, sources)
    bank.update(unit='clause', mode='automatic', review_version=8, reviewer=reviewer,
        required_checks=list(ClauseChecks.model_fields), information_loss_policy='content_review_unit_metadata',
        semantic_distortion_policy='flag', alignment_policy='full_window_nonblocking_localization',
        unit_policy='classification_only', uncertainty_policy='held',
        boundary_policy='repair_then_original_fallback',
        candidate_scope='all_existing_clause_splitter_units', manifest_sha256=clean_digest(manifest))
    if previous:
        bank['previous_audit'] = str(previous_path)
    selection = {}; exceptions = []
    for w in manifest['windows']:
        selected = defaultdict(list)
        for condition in ('omission15', 'omission30'):
            for e in w['conditions'][condition]['edits']:
                if e['after'] or w['conditions']['clean']['verses'][e['verse']][e['start']:e['start']+len(e['before'])] != e['before']:
                    raise ValueError('A selected omission is not an exact source deletion')
                selected[edit_key(e)].append(condition)
        known = {edit_key(e) for e in candidate_spans(w['conditions']['clean']['verses'])}
        for key, conditions in selected.items():
            if key not in known:
                exceptions.append(dict(window_id=w['id'], verse=key[0], start=key[1], before=key[2], selected_conditions=conditions))
        selection[w['id']] = dict(selected)
    bank['selected_nonclause_exceptions'] = exceptions
    load_dotenv(ROOT/'.env')
    with OpenAI(timeout=150.0, max_retries=3) as client, ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(process_window, client, run_dir, w, windows[w['window_id']]['conditions']['clean']['verses'],
            sources[w['passage_id']], selection[w['window_id']], reviewer, prior_windows.get(w['window_id'])):i
            for i,w in enumerate(bank['windows'])}
        for done, future in enumerate(as_completed(jobs), 1):
            result = future.result(); bank['windows'][jobs[future]] = result
            print(f'{done}/{len(jobs)} {result["reference"]} {dict(Counter(c["status"] for c in result["candidates"]))}', flush=True)
    save(bank_path, bank)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(make_report(bank, manifest, sources), encoding='utf-8')
    return bank

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DATA/'passages/sol_scratch66_windows_v1.json')
    parser.add_argument('--bank', type=Path, default=BANK)
    parser.add_argument('--report', type=Path, default=REPORT)
    parser.add_argument('--run', type=Path, default=RUN)
    parser.add_argument('--previous-bank', type=Path, default=PREVIOUS)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    run(args.manifest, args.bank, args.report, args.run, args.workers, previous_path=args.previous_bank)

if __name__ == '__main__':
    main()
