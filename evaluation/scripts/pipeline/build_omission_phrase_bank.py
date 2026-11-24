"""Compile bilingual omission proposals against the clean Sol windows.

Run from the repository root using python -m evaluation.scripts.pipeline.build_omission_phrase_bank.
The default input contains editorial phrase selections. Use --automatic with --unit word or phrase
for model proposals and review.
"""
import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from evaluation.scripts.pipeline.compare_clean_passages import (
    ROOT, load_tier1_metadata, numbered_verses, read, save,
)
from evaluation.scripts.variants._common import content_len

DATA = ROOT / "evaluation/datasets"
PASSAGES = DATA / "passages"
PROPOSALS = DATA / "perturbations/sol_scratch66_omission_phrase_proposals.json"
BANK = DATA / "perturbations/sol_scratch66_omission_phrase_bank.json"
REPORT = ROOT / "deliverables/sol_scratch66_omission_phrases.html"


@dataclass(frozen=True)
class Passage:
    book: str
    english: dict
    chinese: dict
    english_sha256: str


def clean_digest(verses):
    encoded = json.dumps(verses, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def locate(body, phrase, occurrence):
    if not phrase.strip():
        raise ValueError("Empty phrase")
    matches = [m.start() for m in re.finditer(re.escape(phrase), body)]
    if occurrence is None and len(matches) == 1:
        return matches[0]
    if type(occurrence) is int and 1 <= occurrence <= len(matches):
        return matches[occurrence - 1]
    raise ValueError(f"Cannot anchor {phrase!r} unambiguously ({len(matches)} matches)")


def anchor_phrase(proposal, clean, source, pid):
    verse, en, zh = proposal["verse"], proposal["english"], proposal["chinese"]
    if verse not in clean:
        raise ValueError(f"Verse {verse!r} is outside the window")
    body = clean[verse]
    start = locate(body, zh, proposal.get("chinese_occurrence"))
    source_start = locate(source.english[verse], en, proposal.get("english_occurrence"))
    end = start + len(zh)
    after = body[:start] + body[end:]
    candidate_id = f"{pid}/{verse}/{start}-{end}"
    if (content_len(zh) == 0 or content_len(after) == 0
            or content_len(body) - content_len(after) != content_len(zh)):
        raise ValueError(f"Invalid phrase deletion {candidate_id}")
    return dict(id=candidate_id, source_phrase=en, source_start=source_start,
                edit=dict(verse=verse, start=start, before=zh, after=""),
                affected_chars=content_len(zh), resulting_verse=after)


def english_by_passage():
    sources = {}
    for meta in load_tier1_metadata(ROOT / "evaluation"):
        passage = read(PASSAGES / "tier1_zh_sol_v1_2026-11-09" / (meta["id"] + ".json"))
        source = (ROOT / passage["english_path"]).read_bytes()
        digest = sha256(source).hexdigest()
        if digest != passage["english_sha256"]:
            raise ValueError(f'English source changed for {meta["id"]}')
        pairs = numbered_verses(source.decode("utf-8"), meta)
        verses = dict(pairs)
        if len(verses) != len(pairs) or list(verses) != list(passage["conditions"]["clean"]["verses"]):
            raise ValueError(f'English and Chinese verse labels differ for {meta["id"]}')
        sources[meta["id"]] = Passage(meta["book"], verses, passage["conditions"]["clean"]["verses"], digest)
    return sources


def compile_bank(proposals, manifest, sources):
    windows = {w["id"]: w for w in manifest["windows"]}
    ids = [w["window_id"] for w in proposals["windows"]]
    if (proposals["release"] != manifest["release"] or set(ids) != set(windows)
            or len(set(ids)) != len(ids) or len(windows) != len(manifest["windows"])):
        raise ValueError("Proposal roster differs from the window release")
    result = []
    for group in proposals["windows"]:
        item = windows[group["window_id"]]
        pid = item["passage_id"]
        clean = item["conditions"]["clean"]["verses"]
        source = sources[pid]
        if (group["clean_zh_sha256"] != clean_digest(clean)
                or any(source.chinese[v] != s for v, s in clean.items())
                or list(clean) != item["verses"]
                or sum(map(content_len, clean.values())) != item["clean_content_chars"]):
            raise ValueError(f'Clean window changed for {item["id"]}')
        candidates = []
        seen = set()
        for p in group["phrases"]:
            candidate = anchor_phrase(p, clean, source, pid)
            if candidate["id"] in seen:
                raise ValueError(f'Duplicate phrase deletion {candidate["id"]}')
            seen.add(candidate["id"])
            candidate.update(status="needs_review" if p.get("review_note") else "candidate",
                             review_note=p.get("review_note", ""))
            candidates.append(candidate)
        labels = list(clean)
        first, last = labels[0], labels[-1]
        last_chapter, last_verse = last.split(":")
        ref = f"{source.book} {first}"
        if last != first:
            ref += "–" + (last_verse if first.split(":")[0] == last_chapter else last)
        result.append(dict(window_id=item["id"], passage_id=pid, reference=ref, verses=labels,
                           clean_content_chars=item["clean_content_chars"],
                           clean_zh_sha256=group["clean_zh_sha256"], english_sha256=source.english_sha256,
                           candidates=candidates))
    return dict(release=manifest["release"], unit="phrase", provenance=proposals["provenance"],
                windows=result)


def make_report(bank, manifest, sources):
    unit = escape(bank.get("unit", "phrase"))
    clean = {w["id"]: w["conditions"]["clean"]["verses"] for w in manifest["windows"]}
    auto = bank.get("mode") == "automatic"
    three_outcomes = auto and bank.get("review_version") == 2
    classified_review = auto and bank.get("review_version") == 8
    four_outcomes = classified_review and bank.get('report_outcomes') == 'four'
    required_checks = auto and bank.get("review_version") in (3, 4, 5, 6, 7, 8)
    accepted, flagged = ("pass", "held") if auto else ("candidate", "needs_review")
    if required_checks:
        accepted, flagged = "accepted", "rejected"
    rejected_label = "Rejected" if required_checks else "Held"
    good_label = "passed" if auto else "candidates"
    if required_checks:
        good_label = "accepted"
    states = [(accepted, "Accepted" if required_checks else "Pass" if three_outcomes else "Passed phrases")]
    if three_outcomes:
        states.append(("pass_with_flags", "Pass with flags"))
    states.append((flagged, rejected_label))
    if classified_review:
        states.append(("held", "Held for review"))
    state_labels = dict(states)
    def display_outcome(c):
        if four_outcomes and c['status']=='accepted':
            return 'pass_with_flags' if c['flags'] else 'pass'
        return c['status']
    display_states = [('pass','Pass'), ('pass_with_flags','Pass with flags'),
                      ('held','Held for review'), ('rejected','Rejected')] if four_outcomes else states
    display_labels = dict(display_states)
    display_counts = Counter(display_outcome(c) for w in bank['windows'] for c in w['candidates'])
    counts = Counter(c["status"] for w in bank["windows"] for c in w["candidates"])
    usable = sum(any(c["status"] in (accepted, "pass_with_flags") for c in w["candidates"])
                 for w in bank["windows"])
    def summary(totals):
        side = f' · {totals["pass_with_flags"]} passed with flags' if three_outcomes else ''
        if classified_review:
            side += f' · {totals["held"]} held for review'
        return f'{totals[accepted]} {good_label}{side} · {totals[flagged]} {rejected_label.lower()}'
    heading = 'Omission candidate review' if classified_review else f'{unit.title()} omissions'
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Sol {unit} omissions</title><style>body{{max-width:54rem;margin:2rem auto;'
             'padding:0 1rem;color:#163537;font:16px/1.55 system-ui}details{border-top:1px solid #c7d5d2;'
             'padding:.6rem 0}summary{cursor:pointer}article{padding:.4rem 1rem;border-left:3px solid #c7d5d2;'
             'margin:1rem 0}p{margin:.4rem 0}mark{background:#ffe296}h3{margin:.2rem 0}'
             f'</style></head><body><h1>{heading} for the {len(bank["windows"])} Sol windows</h1>',
             f'<p>{summary(counts)} · '
             f'{usable} windows with at least one {"accepted omission" if required_checks else "pass" if auto else "candidate"}</p>',
             f'<p>{escape(bank["provenance"])} Each preview removes one highlighted span in isolation. '
             'Character counts exclude punctuation. Combining edits requires a new read of the window.</p>']
    if required_checks:
        accepted_rows = [c for w in bank["windows"] for c in w["candidates"] if c["status"] == accepted]
        with_flags = sum(bool(c["flags"]) for c in accepted_rows)
        parts.append(f'<p>Accepted without flags: {len(accepted_rows)-with_flags}. '
                     f'Accepted with flags: {with_flags} (included in the accepted total).</p>')
        if classified_review and bank.get('unit') == 'phrase':
            kinds = Counter(c.get('unit_kind', 'uncertain') for c in accepted_rows)
            gaps = [w for w in bank['windows'] if not any(
                c['status'] == accepted and c.get('unit_kind') == 'phrase' for c in w['candidates'])]
            parts.append('<h2>Phrase-level coverage</h2>'
                         f'<p>{len(bank["windows"])-len(gaps)} of {len(bank["windows"])} windows '
                         'have at least one accepted candidate classified as a phrase. '
                         'Accepted word and clause candidates remain in the bank with their actual '
                         'classification; they do not count toward phrase coverage.</p>'
                         '<p>Accepted classifications: '+escape(', '.join(
                             f'{kind}: {n}' for kind,n in sorted(kinds.items())))+'.</p>')
            if gaps:
                parts.append('<p>Windows without an accepted phrase:</p><ul>')
                for w in gaps:
                    other = Counter(c.get('unit_kind', 'uncertain') for c in w['candidates']
                                    if c['status'] == accepted)
                    reason = ('Accepted candidates are classified as '+', '.join(
                        f'{kind} ({n})' for kind,n in sorted(other.items()))+'.') if other else (
                        'No existing proposals.' if not w['candidates'] else 'No candidates passed.')
                    parts.append(f'<li><strong>{escape(w["reference"])}</strong>: {escape(reason)}</li>')
                parts.append('</ul>')
        if bank.get("unit") == "word":
            parts.append('<p>Word level refers to one source lexical item, '
                         'not one Chinese character. Necessary grammatical padding may be included.</p>')
        if bank.get("information_loss_policy") == "substantive_content_required":
            parts.append('<p>Word omissions must remove substantive passage content. Emphasis-only changes '
                         'and ordinary ellipsis preserving the same facts are rejected. Concrete attributes '
                         'can qualify when the reviewer identifies the specific detail lost.</p>')
        if bank.get("information_loss_policy") == "key_content_required":
            parts.append('<p>Word omissions must remove a key person/group identity, a specific place, '
                         'or a significant relationship. Standalone markers such as 忽然、就、不、因此 '
                         'are excluded even when their deletion changes meaning. Minor attributes and '
                         'quantity changes alone do not satisfy this additional key-content check.</p>')
        if bank.get("information_loss_policy") == "key_clause_content_required":
            parts.append('<p>These are all existing punctuation-split candidates, not all verified clauses. '
                         'Acceptance requires a complete predication AND loss of key passage information: '
                         'a fact, event, outcome, cause, condition, instruction, actor, place or relationship. '
                         'Clause length alone does not establish importance. Reviewers do not see the QAs.</p>')
            selected = Counter(c['status'] for w in bank['windows'] for c in w['candidates'] if c.get('selected_conditions'))
            parts.append(f'<p>Units used in current omission passages (each span counted once per window): '
                         f'{selected["accepted"]} accepted; {selected["rejected"]} rejected. '
                         'This is an individual-unit review, not a review of the combined current passages.</p>')
            exceptions = bank.get('selected_nonclause_exceptions', [])
            if exceptions:
                parts.append(f'<p>{len(exceptions)} selected edits do not match clause-split units; '
                             'they remain outside this clause review and are listed below.</p>')
            low_key = [(i,w,c) for i,w in enumerate(bank['windows']) for c in w['candidates']
                       if c.get('checks',{}).get('valid_omission_unit') == 'yes'
                       and c['checks'].get('key_content_removed') != 'yes']
            parts.append(f'<details><summary>Complete clauses with insufficient or uncertain importance ({len(low_key)})</summary><ul>')
            for i,w,c in low_key:
                parts.append(f'<li><a href="#p{i}-{c["number"]}">{escape(w["reference"])} · '
                             f'{escape(c["proposal"]["chinese"])}</a> — {escape(c["key_content_reason"])}</li>')
            parts.append('</ul></details>')
        if classified_review:
            origin = ('These are existing phrase-bank candidates; no new proposals were generated. '
                      if bank.get('candidate_scope') == 'existing_phrase_bank' else 'These are omission-splitter candidates. ')
            parts.append('<p>' + origin + 'Word/phrase/clause size is classification only; '
                         'narrow English alignment is supporting evidence, not an acceptance gate. '
                         'The reviewer reads the full paired window. A concrete event need not be central to the entire story. '
                         'Standalone markers and removals without substantive content remain ineligible.</p>')
            units = Counter(c.get('unit_kind', 'not classified') for c in accepted_rows)
            parts.append('<p>Accepted unit classifications · ' + ' · '.join(
                f'{escape(k.replace("_", " "))}: {n}' for k,n in sorted(units.items()))
                + '. Use these classifications, not the original bank label, for mixture accounting. '
                'Unit flags describe classification; they do not indicate a defective omission.</p>')
            repaired = sum(c.get('boundary_repaired', False) for w in bank['windows'] for c in w['candidates'])
            parts.append(f'<p>{repaired} candidates have automatic punctuation-boundary repairs, retaining the same removed '
                         'lexical content and character dose. Their original deletions are recorded below.</p>')
            selected = Counter(c['status'] for w in bank['windows'] for c in w['candidates'] if c.get('selected_conditions'))
            parts.append(f'<p>Original units selected in current passages: {summary(selected)}. '
                         'This audit does not replace those passages or validate combinations of edits.</p>')
            if bank.get('previous_audit'):
                parts.append('<details><summary>Changes from the earlier audit</summary><ul>')
                for before in ('accepted', 'rejected', 'held'):
                    totals = Counter(c['status'] for w in bank['windows'] for c in w['candidates'] if c.get('previous_status') == before)
                    if totals:
                        parts.append(f'<li>Previously {before}: {summary(totals)}</li>')
                parts.append('</ul></details>')
        rejected_checks = Counter(reason for w in bank["windows"] for c in w["candidates"]
                                  if c["status"] == flagged for reason in c["issues"])
        if rejected_checks:
            parts.append('<p>Failed checks · ' + ' · '.join(
                f'{escape(name.replace("_", " "))} ({n})' for name,n in rejected_checks.most_common())
                + '. One rejected candidate can fail more than one check.</p>')
        check_names = bank.get("required_checks", ["information_omitted", "fluent", "deletion_only",
                                                   "valid_omission_unit", "valid_in_context"])
        parts.append(f'<p>Acceptance requires yes on all {len(check_names)} checks — '
                     + ', '.join(escape(name.replace('_', ' ')) for name in check_names) + '. '
                     + ('A no causes rejection; unresolved required-check uncertainty is held for review. '
                        if classified_review else 'A no or uncertain answer causes rejection. ')
                     + 'Fluency requires natural, grammatical Chinese.</p>')
        if "other_meaning_preserved" in check_names:
            parts.append('<p>The intended information loss is permitted. Other meaning preserved requires '
                         'the remaining claims to retain their meaning after that loss. An additional '
                         'distortion introduces a mistranslation effect and excludes the candidate '
                         'from the controlled omission condition.</p>')
        if bank.get("semantic_distortion_policy") == "flag":
            parts.append('<p>The omission treatment removes source information through deletion. '
                         'Fluent omissions can be accepted with additional semantic distortion flags. '
                         'These flags record secondary mistranslation effects without causing rejection. '
                         'Possible other meaning changed records uncertainty about the secondary effect.</p>')
    if three_outcomes or required_checks:
        if three_outcomes:
            parts.append('<p>Pass with flags means the reviewer confirmed a phrase omission and identified '
                         'a side effect or evidence for recovering the detail elsewhere in the window.</p>')
        tag_counts = Counter(f for w in bank["windows"] for c in w["candidates"]
                             if c["status"] in (accepted, "pass_with_flags") for f in c["flags"])
        if tag_counts:
            parts.append('<p>Flags on accepted omissions · ' + ' · '.join(
                f'{escape(f.replace("_"," "))} ({n})' for f,n in tag_counts.most_common())
                + '. A candidate can have several flags.</p>')
    if bank.get("compared_to"):
        all_rows = [c for w in bank["windows"] for c in w["candidates"]]
        fresh = sum(c["proposed_this_run"] for c in all_rows)
        fresh_totals = Counter(c["status"] for c in all_rows if c["proposed_this_run"])
        if bank.get("review_only"):
            parts.append(f'<p>Re-reviewed {len(all_rows)} unchanged proposals from {escape(bank["compared_to"])}. '
                         'No new proposals were requested. Prior decisions were not shown to the reviewer.</p>')
        else:
            parts.append(f'<p>The writer proposed {fresh} deletions independently ({summary(fresh_totals)}). The reviewer also assessed '
                         f'{len(all_rows)-fresh} earlier deletions the writer did not propose again. '
                         'Prior and current entries are matched by their exact Chinese deletion in the same window.</p>')
        parts.append('<details><summary>Earlier decisions under the updated criteria</summary><ul>')
        for old_status in sorted({c["previous_status"] for c in all_rows if "previous_status" in c}):
            transitions = Counter(c["status"] for c in all_rows if c.get("previous_status") == old_status)
            parts.append(f'<li>Previously {escape(old_status.replace("_", " "))} ({sum(transitions.values())})'
                         f' → {summary(transitions)}</li>')
        parts.append('</ul></details>')
    held_only = [escape(w["reference"]) for w in bank["windows"]
                 if w["candidates"] and all(c["status"] == flagged for c in w["candidates"])]
    if held_only:
        parts.append(f'<p><b>Windows with only {rejected_label.lower()} proposals</b>　' + ' · '.join(held_only) + '</p>')
    if auto:
        empty = [escape(w["reference"]) for w in bank["windows"] if not w["candidates"]]
        if empty:
            parts.append('<p><b>Windows without proposals</b>　' + ' · '.join(empty) + '</p>')
        for state, title in display_states:
            parts.append(f'<details id="outcome-{state}"><summary><b>{title} ({display_counts[state]})</b></summary><ul>')
            for index, w in enumerate(bank["windows"]):
                for c in w["candidates"]:
                    if display_outcome(c) == state:
                        p = c["proposal"]
                        tags = " · ".join(f.replace("_", " ") for f in c.get("flags", []))
                        tags = f' ({escape(tags)})' if tags else ""
                        parts.append(f'<li><a href="#p{index}-{c["number"]}">{escape(w["reference"])} · '
                                     f'{escape(p["chinese"])}</a>{tags} — {escape(c["review_note"])}</li>')
            parts.append('</ul></details>')
    for index, w in enumerate(bank["windows"]):
        pid = w["passage_id"]
        bodies = clean[w["window_id"]]
        ref = w["reference"]
        window_counts = Counter(c["status"] for c in w["candidates"])
        parts.append(f'<details><summary><b>{escape(ref)}</b> · {summary(window_counts)}</summary>'
                     f'<p lang="zh">{" ".join(escape(t) for t in bodies.values())}</p>')
        if w.get("no_proposals_reason"):
            parts.append(f'<p>Writer proposed no fresh {unit} omissions. {escape(w["no_proposals_reason"])}</p>')
        for c in w["candidates"]:
            tag = f' id="p{index}-{c["number"]}"' if auto else ""
            if "edit" not in c:
                p = c["proposal"]
                parts.append(f'<article{tag}><h3>{escape(p["chinese"])}</h3><p>{rejected_label} during span check · '
                             f'{escape(p["verse"])} · {escape(p["english"])}</p><p>{escape(c["review_note"])}</p></article>')
                continue
            e = c["edit"]
            label, pos, deletion = e["verse"], e["start"], e["before"]
            original = bodies[label]
            marked = (escape(original[:pos]) + '<mark>' + escape(deletion) + '</mark>'
                      + escape(original[pos+len(deletion):]))
            en = sources[pid].english[label]
            start = c["source_start"]
            quote = c["source_phrase"]
            marked_en = escape(en[:start]) + '<mark>' + escape(quote) + '</mark>' + escape(en[start+len(quote):])
            status = display_labels[display_outcome(c)] if auto else ("Held for review" if c["status"] == flagged else "Candidate")
            parts.append(f'<article{tag}><h3>{escape(deletion)} · {c["affected_chars"]} characters</h3>'
                         f'<p>{escape(label)} · {status}</p><p>{marked_en}</p><p lang="zh">{marked}</p>'
                         f'<p lang="zh"><b>After</b>　{escape(c["resulting_verse"])}</p>')
            if c["review_note"]:
                parts.append(f'<p>{escape(c["review_note"])}</p>')
            if c.get('selected_conditions'):
                label = 'Original candidate selected in current window: ' if classified_review else 'Used in current window: '
                parts.append('<p>' + label + escape(', '.join(c['selected_conditions'])) + '</p>')
            if c.get('boundary_repaired'):
                parts.append('<p>Automatic boundary repair · original removal: '
                             + escape(c['original_edit']['before'])
                             + '. Removed lexical content and dose are unchanged; only punctuation boundaries differ.</p>')
            if c.get('boundary_attempts'):
                parts.append('<details><summary>Boundary alternatives checked</summary>')
                for attempt in c['boundary_attempts']:
                    parts.append('<p><b>' + escape(attempt['kind'].title()) + '</b> · '
                                 + escape(attempt['status']) + '</p><p lang="zh">'
                                 + escape(attempt['resulting_verse']) + '</p><p>'
                                 + escape(attempt['review_note']) + '</p>')
                parts.append('</details>')
            if classified_review and c.get('unit_kind'):
                parts.append('<p>Unit classification (not a rejection check) · '
                             + escape(c['unit_kind'].replace('_', ' ')) + ' · ' + escape(c.get('unit_reason', '')) + '</p>')
            if classified_review and c.get('source_alignment'):
                parts.append('<p>Source alignment (not a rejection check) · '
                             + escape(c['source_alignment']) + ' · ' + escape(c['alignment_reason']) + '</p>')
                for ev in c.get('english_evidence', []):
                    parts.append('<p>English evidence · ' + escape(ev['verse']) + ' · ' + escape(ev['quote']) + '</p>')
            if c.get('stage') == 'alignment_check':
                parts.append('<p>English alignment was not verified; this candidate has not passed the bilingual review.</p>')
            if required_checks and "checks" in c:
                parts.append('<p>Required checks · ' + ' · '.join(
                    f'{escape(name.replace("_", " "))} = {escape(answer)}'
                    for name, answer in c["checks"].items()) + '</p>')
            if "information_loss" in c:
                loss = c["information_loss"]
                parts.append(f'<p>Information loss · {escape(loss["kind"].replace("_", " "))}</p>')
                for key, title in (("source_information", "Source"), ("edited_information", "After deletion"),
                                   ("lost_content", "Content lost")):
                    parts.append(f'<p><b>{title}</b> · {escape(loss[key])}</p>')
                if c.get("check_overrides"):
                    parts.append('<p>Enforced content eligibility / verified deletion check overrides: '
                                 + escape(str(c["check_overrides"])) + '</p>')
            if "key_content_category" in c:
                parts.append(f'<p>Key-content category · {escape(c["key_content_category"].replace("_", " "))}</p>'
                             f'<p>{escape(c["key_content_reason"])}</p>')
            if three_outcomes or required_checks:
                for field, title in (("issues", "Rejection reasons" if required_checks else "Hold reasons"), ("flags", "Flags")):
                    if c[field]:
                        parts.append(f'<p>{title} · {escape(", ".join(s.replace("_", " ") for s in c[field]))}</p>')
                if c.get('review_holds'):
                    parts.append('<p>Needs review · ' + escape(', '.join(s.replace('_', ' ') for s in c['review_holds'])) + '</p>')
                if c.get("previous_status"):
                    origin = "also proposed this run" if c.get("proposed_this_run") else "carried forward for review"
                    parts.append(f'<p>Previously {escape(c["previous_status"].replace("_"," "))} · {origin}</p>')
                    if c.get('previous_review_note'):
                        parts.append('<details><summary>Previous review</summary><p>'
                                     + escape(c['previous_review_note']) + '</p></details>')
                for review in c.get("reviews", [])[:-1]:
                    if set(review["flags"]) - set(c["reviews"][-1]["flags"]):
                        parts.append(f'<p>Earlier reviewer explanation · {escape(review["reason"])}</p>')
            parts.append('</article>')
        parts.append('</details>')
    if bank.get('selected_nonclause_exceptions'):
        refs = {w['window_id']:w['reference'] for w in bank['windows']}
        parts.append('<details><summary>Selected non-clause edits outside this review</summary><ul>')
        for e in bank['selected_nonclause_exceptions']:
            parts.append(f'<li>{escape(refs[e["window_id"]])} · {escape(e["before"])} · '
                         f'{escape(", ".join(e["selected_conditions"]))}</li>')
        parts.append('</ul></details>')
    if auto:
        parts.append('<script>function reveal(){const e=document.getElementById(location.hash.slice(1));'
                     'if(e){e.closest("details").open=true;e.scrollIntoView()}}'
                     'addEventListener("hashchange",reveal);reveal()</script>')
    return "".join(parts) + "</body></html>\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--proposals", type=Path)
    mode.add_argument("--automatic", action="store_true", help="Generate and independently review bilingual omissions")
    parser.add_argument("--unit", choices=("word", "phrase"), default="phrase", help="Unit for automatic generation")
    parser.add_argument("--prior-bank", type=Path, help="Also re-review previous automatic candidates for the same window release")
    parser.add_argument("--review-only", action="store_true", help="Re-review the prior bank without generating new proposals")
    parser.add_argument("--manifest", type=Path, default=PASSAGES / "sol_scratch66_windows_v1.json")
    parser.add_argument("--bank", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.review_only and (not args.automatic or not args.prior_bank):
        parser.error("--review-only requires --automatic and --prior-bank")
    if args.automatic and args.review_only and args.unit == 'phrase':
        from evaluation.scripts.pipeline.review_existing_omission_phrases import (
            BANK as REVIEW_BANK, REPORT as REVIEW_REPORT, run as review_existing,
        )
        review_existing(args.manifest, args.prior_bank, args.bank or REVIEW_BANK, args.report or REVIEW_REPORT)
        return
    if args.automatic:
        from evaluation.scripts.pipeline.generate_omission_phrases import (
            AUTO_BANK, AUTO_REPORT, AUTO_WORD_BANK, AUTO_WORD_REPORT, run_automatic,
        )
        bank_path = AUTO_WORD_BANK if args.unit == "word" else AUTO_BANK
        report_path = AUTO_WORD_REPORT if args.unit == "word" else AUTO_REPORT
        run_automatic(args.manifest, args.bank or bank_path, args.report or report_path,
                      prior_bank_path=args.prior_bank, unit=args.unit, review_only=args.review_only)
        return
    if args.prior_bank:
        parser.error("--prior-bank requires --automatic")
    if args.unit != "phrase":
        parser.error("--unit word requires --automatic")
    manifest = read(args.manifest)
    sources = english_by_passage()
    bank = compile_bank(read(args.proposals or PROPOSALS), manifest, sources)
    report = make_report(bank, manifest, sources)
    save(args.bank or BANK, bank)
    destination = args.report or REPORT
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report, encoding="utf-8")
    print(dict(Counter(c["status"] for w in bank["windows"] for c in w["candidates"])))


if __name__ == "__main__":
    main()
