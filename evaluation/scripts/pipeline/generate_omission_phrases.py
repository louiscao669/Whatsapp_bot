"""Automatically propose and independently review bilingual word or phrase omissions."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
import os
import re
import time
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from evaluation.scripts.pipeline.build_omission_phrase_bank import (
    DATA, ROOT, anchor_phrase, clean_digest, compile_bank, english_by_passage, make_report,
)
from evaluation.scripts.pipeline.compare_clean_passages import JUDGE, WRITER, read, save

AUTO_BANK = DATA / "perturbations/sol_scratch66_omission_phrase_bank_auto_v4.json"
AUTO_REPORT = ROOT / "deliverables/sol_scratch66_omission_phrases_auto_v4.html"
AUTO_WORD_BANK = DATA / "perturbations/sol_scratch66_omission_word_bank_auto_v6.json"
AUTO_WORD_REPORT = ROOT / "deliverables/sol_scratch66_omission_words_auto_v6.html"
RUN = ROOT / "evaluation/runs/sol_scratch66_automatic_omission_phrases"

KEY_CONTENT_CATEGORIES = {"person_or_group", "place", "significant_relationship"}
# Reject only whole marker deletions, allowing punctuation around them. Never substring-match
# a name or content expression containing one of these characters. The reviewer handles other markers.
EXCLUDED_WORD_MARKERS = {
    "忽然", "突然", "就", "才", "便", "也", "还", "又", "再", "再次", "先", "赶快",
    "不", "不可", "不能", "未", "没有", "没", "莫", "别", "无", "因此", "所以", "于是",
    "然后", "随后", "最后", "仍", "仍然", "已经", "正在", "必", "只", "都",
}


def excluded_word_marker(quote):
    return re.sub(r"[\W_]+", "", quote) in EXCLUDED_WORD_MARKERS


UNIT_RULES = {
    "phrase": """Target a meaningful source phrase below clause level, e.g. a prepositional relation
with its complement or a substantive multiword nominal. A lone content word with a determiner,
particle or grammatical padding does not qualify; a multiword name alone is also one lexical item.
A whole additional event, assertion, finite clause or entire reduced relative does not qualify.""",
    "word": """Target ONE content-bearing lexical item that removes KEY PASSAGE INFORMATION:
a person/group identity, a specific place, or a significant relationship such as kinship,
ownership, allegiance, authority, or who acted toward whom. These are the eligible categories.
The reviewer must explain the concrete who/where/relationship gap left in the narrative.
Do not accept incidental labels merely because they are names or nouns. A title or relationship
term qualifies only if its loss materially obscures the actor's role or a significant relationship.
Word-level does NOT mean one Chinese character or necessarily one whitespace-delimited English
token. A compound name or number can be one lexical item, but lexical size alone NEVER establishes
key-content eligibility. Include an adjacent article, classifier,
particle or punctuation in the corresponding contiguous span only when grammatically necessary
for the same removal; grammatical padding does not turn a word omission into a phrase omission.
Measure and currency units such as years, meters or shekels carry source information; they are
NOT grammatical padding. Removing a numeral together with such a unit is a quantity/duration
PHRASE, even if the Chinese needs both removed to remain fluent. Ordinary classifiers such as
个 or 名 can be padding. Classify the whole Chinese deletion against its full English context,
not only the writer's quoted English word: deleting a full locative relation such as 'in Judah'
is phrase-level even if the proposal quotes only 'Judah'.
Do not remove arbitrary parts of a Chinese word, multiple independent details, a full prepositional
relation with its complement, or a whole event/assertion (including an entire reduced relative).
Deleting a complete predication counts as clause-level even if it has only one English verb.
Standalone grammatical, discourse, temporal/aspectual, modal, causal or polarity markers are
EXCLUDED, including 忽然, 就, 不, 因此 and similar words. This exclusion applies EVEN WHEN
deletion changes truth conditions, chronology, causality or the reader's interpretation.
A negation-only deletion cannot be rescued by calling its polarity reversal a significant
relationship. A connective-only deletion cannot qualify merely because it changes causal logic.
Minor attributes, evaluative descriptions, manner/intensity, approximation and isolated quantity
changes are insufficient. For example, removing 'new', 'old', 'very', 'suddenly', 'not', 'therefore'
or 'again' does not meet this study's key-content rule. Material meaning change alone is insufficient.
For information_omitted, still distinguish actual information loss from ordinary ellipsis or
emphasis alone; a meaningful but excluded negation may pass information_omitted while failing
key_content_removed. Record secondary semantic distortion as a flag, never as a substitute for
key-content eligibility. Explicitly compare the original fact with what the edited text conveys.
For key_content_removed, require the loss of an actual key person/group, place or significant
relationship detail. Do not invent a relationship to justify deleting an ordinary modifier.
Do not demand that a deletion hit a particular QA answer; no questions or answers are supplied.
If no qualifying word omission remains fluent, propose none rather than substitute minor edits.""",
}

WORD_LOSS_REVIEW = """
Also return information_loss with kind content_detail, emphasis_only, meaning_preserved,
unaligned, or uncertain. Supply source_information, edited_information and lost_content as
concrete before/after evidence. Only content_detail can satisfy information_omitted=yes.
For emphasis_only, explain what nuance changes but why the same substantive facts remain.
This is the study's eligibility threshold, not a claim that emphasis has no linguistic meaning.
An uncertain substantive contrast requires information_omitted=uncertain and rejection.
Return the sixth required check, key_content_removed, as yes/no/uncertain. Also return
key_content_category and key_content_reason. Only person_or_group, place, or
significant_relationship can satisfy key_content_removed=yes. For excluded_marker, minor_detail,
not_key_content, use no; for uncertain, use uncertain. Explain the specific key fact or relationship
lost and why it matters within the displayed passage. A category label alone is not evidence.
All six required checks must be yes. An additional semantic-distortion flag cannot bypass this gate.
The original_chinese_verse and exact_deletion fields show the precise edit, which the program
has already reconstructed without any addition, substitution or reordering. Do not infer a
different original wording or claim that additional text was removed. Judge semantic alignment
and the omission unit separately from this mechanical deletion check.
"""

PROPOSE = """Read the supplied aligned English / clean simplified Chinese Bible window. Propose up to four
distinct, plausible {unit}-level translation omissions (typically two to four candidates if warranted).
Select solely from those texts. For each candidate quote exactly ONE contiguous English span and its
corresponding contiguous Chinese deletion in the SAME verse. Copy punctuation and case literally.
Both occurrence numbers are one-based, including for unique matches. The edit is deletion only.
The exact Chinese left after deletion must remain natural, grammatical and idiomatic in its
displayed window, including its punctuation. Screen out edits that leave broken constructions,
awkward fragments, or incomplete verb complements. Do not repair the remainder by adding or
replacing words. Use the naturally bounded span; include adjacent punctuation or a conjunction
only when it belongs to that removal. Confirm information is omitted, fluency is maintained,
the edit is deletion only, the omission unit is valid, and the deletion is valid in context.
The intended loss of information is allowed, including leaving a detail unspecified or making
the statement less specific. For example, 他在耶路撒冷作王五十二年 can become 他在耶路撒冷作王:
the duration is lost and the remaining claim is preserved. An omission may remove answer evidence.
Treatments are defined by the editing operation. Omission removes source information through
deletion; the separate mistranslation treatment introduces inaccurate information through
substitution. A fluent deletion can qualify even when it also changes scope, polarity, an actor,
or another retained assertion. Propose these candidates for review and flagging rather than
screening them out for that semantic consequence. For example, removing 沿原路 from 不可沿原路返回
removes the route qualification and broadens the prohibition. It is eligible for omission review,
with the broader prohibition recorded as an additional mistranslation effect. Keep fluency required.
{unit_rules}
Identify source information no longer expressed by the edited
statement. Readers may still infer it from a different sentence. Include such an omission if the
deleted span carried identifiable content. Conventional implicit wording that fully expresses
the same meaning in that statement does not qualify. Seek variety where the text supports it.
Proposals are alternatives tested one at a time. Zero is permissible. Give a short English explanation
in no_proposals_reason only when you find no candidate. Never invent or paraphrase quoted text."""

REVIEW = """Independently judge each numbered deletion. Use the full aligned English and clean Chinese
window, and the exact Chinese verse produced by the deletion. Apply one deletion at a time. For each:
Treatments are defined by editing operation: omission deletes source information, while the
separate mistranslation treatment substitutes inaccurate information. A deletion can qualify
as omission and also produce a secondary mistranslation effect.
Return yes, no, or uncertain for EACH of these {check_count} required checks:

information_omitted: identify the specific source information that disappears from the edited
statement. Check that the English and Chinese spans convey the same information in the same verse,
allowing differences in how they mark a relation (e.g. tell someone and 向某人报信).
Use no if the remaining local wording still expresses the full meaning through ordinary Chinese
ellipsis, or if the deleted detail was absent from the English source. If information is omitted
here but inferable from other evidence in the window, it can pass with recoverable_from_context.
A broader, inaccurate statement may logically imply part of the original without preserving its
restriction. For example, 不可返回 after deleting 沿原路 loses the explicit route qualification
even though the new prohibition covers that route too. This qualifies as information omitted.

fluent: the exact resulting Chinese must be natural, grammatical and idiomatic, including word
order, word boundaries, punctuation and verb complements. Newly awkward or unfinished wording
fails this check even when the intended information is clearly omitted. For example, removing
在自己家中 from 以利沙正坐在自己家中 leaves the unfinished 以利沙正坐. Do not silently fix it.

deletion_only: the specified Chinese text is removed and all other wording is retained exactly.
Any addition, replacement, reordering or rewriting fails. Removing adjacent punctuation as part
of the quoted span is permitted.

valid_omission_unit: this bank requests {unit}-level deletions. Count the smallest semantic unit
lost in English. {unit_rules}
Explain the actual level when rejecting an item for size. Arbitrary word fragments and
punctuation-only deletions fail. An omission at another level fails this bank's unit check,
but can still be a genuine omission.

valid_in_context: evaluate the actual selected occurrence in the full displayed window. Confirm
that the aligned source detail and the alleged omission have the stated interpretation in context.
Use no if this interpretation depends on another unapplied edit or outside Bible knowledge.
Judge each alternative separately and do not speculate about a comprehension question. A secondary
semantic distortion does not itself fail this check. Identify the lost source information in the
actual window and record the changed interpretation as a flag.

Acceptance requires yes to all {check_count} checks. A no or uncertain on ANY required check causes rejection.
Separately record nonblocking flags for ambiguous_reference (a newly unclear referent),
recoverable_from_context, and other_meaning_changed (additional semantic distortion caused by
deletion, such as altered scope, agent or polarity). Mere loss of the selected information does
not require other_meaning_changed. For that flag, identify the affected retained assertion and
compare its original and edited readings in the explanation. If the additional distortion is
uncertain, use possible_other_meaning_changed and explain the uncertainty. Uncertainty solely
about this secondary effect does not cause rejection. Reject only when a required check fails
or is uncertain. A newly ungrammatical sentence still fails fluent, including when it also has
semantic distortion. Do not use a semantic flag to override failed fluency.
For example, fluent 不可返回 can pass after deletion of 沿原路, with other_meaning_changed recording
the broader prohibition. A natural deletion leaving a duration unspecified can pass without that flag.
For each number give a concise English reason
identifying the lost detail and explaining every failed/uncertain check and flag against concrete
wording. Do not rewrite or repair the proposed deletion."""

UNIT_CHECK = REVIEW + """
In particular, distinguish a phrase that contains a relative clause from deleting that clause itself.
For this study an entire reduced relative that ascribes an action or state to an entity counts as
a clause (e.g. removing 'waiting at the bridge' from 'the soldiers waiting at the bridge'). Removing
only 'at the bridge' is a phrase omission. A participial adjective or a preposition may also end in
-ed or -ing, so decide from the actual sentence and lost meaning. Flag the complete loss of a
predication with valid_omission_unit=no even if the subject or finite auxiliary is implicit."""

LIST_CHECK = REVIEW + """
Check the boundary of the selected English constituent in the full sentence. A list member can
qualify if it fits the requested unit level. If a selection cuts two separately enumerated items out of a
longer list and grabs the conjunction leading to a surviving item, set valid_omission_unit=no: it
packages two omissions into one event. Trailing punctuation alone is not a reason to hold."""

class Phrase(BaseModel):
    verse: str
    english: str
    chinese: str
    english_occurrence: int
    chinese_occurrence: int


class Proposals(BaseModel):
    phrases: list[Phrase]
    no_proposals_reason: str


class Checks(BaseModel):
    information_omitted: Literal["yes", "no", "uncertain"]
    fluent: Literal["yes", "no", "uncertain"]
    deletion_only: Literal["yes", "no", "uncertain"]
    valid_omission_unit: Literal["yes", "no", "uncertain"]
    valid_in_context: Literal["yes", "no", "uncertain"]


class Decision(BaseModel):
    number: int
    checks: Checks
    flags: list[Literal["ambiguous_reference", "recoverable_from_context",
                        "other_meaning_changed", "possible_other_meaning_changed"]]
    reason: str


class Decisions(BaseModel):
    decisions: list[Decision]


class WordInformationLoss(BaseModel):
    kind: Literal["content_detail", "emphasis_only", "meaning_preserved", "unaligned", "uncertain"]
    source_information: str
    edited_information: str
    lost_content: str


class WordChecks(Checks):
    key_content_removed: Literal["yes", "no", "uncertain"]


class WordDecision(Decision):
    checks: WordChecks
    information_loss: WordInformationLoss
    key_content_category: Literal["person_or_group", "place", "significant_relationship",
                                 "excluded_marker", "minor_detail", "not_key_content", "uncertain"]
    key_content_reason: str


class WordDecisions(BaseModel):
    decisions: list[WordDecision]


def background_response(client, folder, stage, signature, attempt, request):
    """Persist request IDs before polling; resume rather than resubmit accepted work."""
    from openai.types.responses import Response
    from openai import NotFoundError
    path=folder/f"request-{stage}-{signature}-{attempt+1}.json"
    saved=read(path) if path.exists() else None
    resubmissions=saved.get('resubmissions',0) if saved else 0
    api=client.with_options(timeout=30,max_retries=2)
    if saved:
        # Older SDK dumps used the Python field name schema_; validation expects
        # the API alias schema. Restore the alias without resubmitting the job.
        payload=saved['response']
        format_config=(payload.get('text') or {}).get('format') or {}
        if 'schema_' in format_config and 'schema' not in format_config:
            format_config['schema']=format_config.pop('schema_')
        response=Response.model_validate(payload)
    else:
        response=api.responses.parse(**request,background=True)
        save(path,dict(signature=signature,attempt=attempt+1,resubmissions=resubmissions,response=response.model_dump(mode='json',by_alias=True)))
    deadline=time.monotonic()+1800
    while response.status in ('queued','in_progress'):
        if time.monotonic()>deadline:
            raise TimeoutError(f'{stage}: request {response.id} still pending; saved for resumption')
        time.sleep(10)
        try:
            response=api.responses.retrieve(response.id)
        except NotFoundError:
            if resubmissions>=1:raise
            # store=False background responses have a temporary retrieval window.
            # Preserve the expired ID and resubmit only after an explicit 404.
            save(folder/f'expired-{stage}-{signature}-{attempt+1}.json',read(path))
            resubmissions+=1
            response=api.responses.parse(**request,background=True)
        save(path,dict(signature=signature,attempt=attempt+1,resubmissions=resubmissions,response=response.model_dump(mode='json',by_alias=True)))
    return response


def ask(client, folder, stage, model, prompt, payload, schema, validate):
    signature = clean_digest(dict(model=model, prompt=prompt, payload=payload,
                                  schema=schema.model_json_schema(), effort="medium"))
    dest = folder / f"{stage}-{signature}.json"
    if dest.exists():
        result = schema.model_validate(read(dest)["result"])
        validate(result)
        return result
    for attempt in range(2):
        background=os.environ.get('ETEN_REVIEW_BACKGROUND')=='1'
        # The limit includes reasoning as well as JSON. A bounded retry gives a
        # truncated response more room, without changing the model or rubric.
        budget=6500 if attempt==0 else 12000
        request=dict(model=model,instructions=prompt,input=json.dumps(payload,ensure_ascii=False),
            text_format=schema,reasoning={"effort":"medium"},store=False,max_output_tokens=budget)
        try:
            response=(background_response(client,folder,stage,signature,attempt,request)
                      if background else client.responses.parse(**request))
            if response.status!='completed':
                raise ValueError(f'{stage}: incomplete model response ({response.status})')
            result=schema.model_validate_json(response.output_text) if background else response.output_parsed
            if result is None:
                raise ValueError(f'{stage}: no structured model result')
        except ValueError as exc:
            # Structured output can be truncated before SDK/Pydantic parsing.
            # Retry within the existing two-attempt bound; never cache or use it.
            if hasattr(exc, 'errors'):
                errors=exc.errors(include_url=False)
                save(folder / f"invalid-{stage}-{signature}-{attempt+1}.json",
                     dict(model=model,signature=signature,attempt=attempt+1,errors=errors))
            if attempt == 0:
                continue
            raise
        try:
            validate(result)
        except ValueError:
            if attempt == 0:
                continue
            raise
        save(dest, dict(request_id=response.id, model=response.model, signature=signature,
                        transport='background' if background else 'synchronous',max_output_tokens=budget,
                        usage=response.usage.model_dump() if response.usage else {}, result=result.model_dump()))
        return result


def validate_writer(output):
    if len(output.phrases) > 4 or (not output.phrases and not output.no_proposals_reason.strip()):
        raise ValueError("Expected up to four proposals or an explanation for an empty window")


def validate_reviews(output, numbers):
    if (Counter(d.number for d in output.decisions) != Counter(numbers)
            or any(not d.reason.strip() for d in output.decisions)):
        raise ValueError("Reviewer did not provide exactly one reasoned decision per candidate")
    for d in output.decisions:
        if isinstance(d, WordDecision) and not all(value.strip() for value in (
                d.information_loss.source_information, d.information_loss.edited_information,
                d.information_loss.lost_content, d.key_content_reason)):
            raise ValueError("Word review must explain the source, edited reading, and lost content")


def check_source_boundaries(text, start, quote, unit="phrase"):
    end = start + len(quote)
    if ((start and text[start-1].isalnum() and text[start].isalnum())
            or (end < len(text) and text[end-1].isalnum() and text[end].isalnum())):
        raise ValueError("English span splits a word")
    minimum = 2 if unit == "phrase" else 1
    if len(re.findall(r"[\w]+(?:[’'-][\w]+)*", quote)) < minimum:
        raise ValueError(f"English span contains fewer than {minimum} words")


def possible_clause_start(quote):
    # These forms can head either phrases or relative/participial clauses; the model resolves them in context.
    match = re.search(r"[a-z]+", quote.lower())
    first = match.group() if match else ""
    return (first in {"who", "whom", "which", "that", "whose", "when", "while", "having", "being"}
            or (len(first) >= 5 and first.endswith(("ing", "ed", "en"))))


def proposal_location(p):
    return (p["verse"], p["chinese"], p["chinese_occurrence"])


def process_window(client, run, w, clean, source, writer, reviewer, prior=None, unit="phrase", review_only=False):
    if unit not in UNIT_RULES:
        raise ValueError(f"Unknown omission unit: {unit}")
    def prompt(template):
        return template.format(unit=unit, unit_rules=UNIT_RULES[unit], check_count="six" if unit == "word" else "five")
    folder = run / sha256(w["window_id"].encode()).hexdigest()[:20]
    aligned = {k: dict(english=source.english[k], chinese=v) for k,v in clean.items()}
    if review_only and prior is None:
        raise ValueError("Review-only mode requires prior candidates")
    proposed = (Proposals(phrases=[], no_proposals_reason="") if review_only else
                ask(client, folder, "propose", writer, prompt(PROPOSE), aligned, Proposals, validate_writer))
    phrases = [phrase.model_dump() for phrase in proposed.phrases]
    fresh_count = len(phrases)
    prior_by_location = {proposal_location(c["proposal"]): c for c in (prior or {}).get("candidates", [])}
    fresh_locations = {proposal_location(p) for p in phrases}
    phrases.extend(c["proposal"] for key, c in prior_by_location.items() if key not in fresh_locations)
    records = []
    batch = []
    seen = set()
    for n, p in enumerate(phrases, 1):
        previous = prior_by_location.get(proposal_location(p))
        row = dict(number=n, proposal=p, proposed_this_run=n <= fresh_count, flags=[])
        if previous:
            row["previous_status"] = previous["status"]
            row["previous_issues"] = previous["issues"]
        try:
            anchored = anchor_phrase(p, clean, source, w["passage_id"])
            row.update(anchored)
            check_source_boundaries(source.english[p["verse"]], anchored["source_start"], p["english"], unit)
            if anchored["id"] in seen:
                raise ValueError("Duplicate Chinese deletion in this window")
            seen.add(anchored["id"])
            if unit == "word" and excluded_word_marker(p["chinese"]):
                reason = ("This standalone marker is excluded by the study's key-content rule, "
                          "even if deleting it changes meaning. No model judgment can override this exclusion.")
                row.update(status="rejected", stage="eligibility_check", issues=["key_content_removed"],
                           key_content_category="excluded_marker", key_content_reason=reason, review_note=reason)
                records.append(row)
                continue
            batch.append(dict(number=n, verse=p["verse"], english_phrase=p["english"],
                              chinese_removed=p["chinese"], edited_chinese_verse=anchored["resulting_verse"]))
            if unit == "word":
                batch[-1].update(original_chinese_verse=clean[p["verse"]], exact_deletion=anchored["edit"])
        except ValueError as exc:
            row.update(status="rejected", stage="span_check", issues=["invalid_span"], review_note=str(exc))
        records.append(row)
    def review_batch(items, stage, prompt):
        numbers = [item["number"] for item in items]
        schema = WordDecisions if unit == "word" else Decisions
        if unit == "word":
            prompt += WORD_LOSS_REVIEW
        review = ask(client, folder, stage, reviewer, prompt, dict(window=aligned, candidates=items),
                     schema, lambda output: validate_reviews(output, numbers))
        for decision in review.decisions:
            row = records[decision.number-1]
            row.setdefault("reviews", []).append(dict(stage=stage, **decision.model_dump()))
            # A focused unit or list check can add a blocker without erasing an observed side effect.
            row["flags"] = sorted(set(row["flags"]) | set(decision.flags))
            checks = decision.checks.model_dump()
            if unit == "word":
                row["information_loss"] = decision.information_loss.model_dump()
                kind = decision.information_loss.kind
                # A model's yes cannot override its own finding of no substantive content loss.
                if kind != "content_detail":
                    checks["information_omitted"] = "uncertain" if kind == "uncertain" else "no"
                # All reviewed rows have already passed exact span anchoring and are rendered
                # by deletion alone. A reviewer cannot overturn that mechanical invariant.
                checks["deletion_only"] = "yes"
                row["key_content_category"] = decision.key_content_category
                row["key_content_reason"] = decision.key_content_reason
                if decision.key_content_category not in KEY_CONTENT_CATEGORIES:
                    checks["key_content_removed"] = "uncertain" if decision.key_content_category == "uncertain" else "no"
                row["check_overrides"] = {k: v for k, v in checks.items()
                                          if v != decision.checks.model_dump()[k]}
            issues = [name for name, answer in checks.items() if answer != "yes"]
            row.update(status="rejected" if issues else "accepted", checks=checks,
                       stage="model_review" if stage == "review" else stage,
                       issues=issues, review_note=decision.reason)
    if batch:
        review_batch(batch, "review", prompt(REVIEW))
        ambiguous = [item for item in batch if records[item["number"]-1]["status"] == "accepted"
                     and possible_clause_start(item["english_phrase"])]
        if ambiguous:
            review_batch(ambiguous, "unit_review", prompt(UNIT_CHECK))
        list_fragments = [item for item in batch if records[item["number"]-1]["status"] == "accepted"
                          and re.search(r"\b(?:and|or)[\s,;]*$", item["english_phrase"], re.I)]
        if list_fragments:
            review_batch(list_fragments, "list_review", prompt(LIST_CHECK))
    return dict(w, candidates=records, fresh_count=fresh_count,
                no_proposals_reason=proposed.no_proposals_reason if not fresh_count else "")


def run_automatic(manifest_path, bank_path, report_path, run=RUN, workers=8, writer=WRITER, reviewer=JUDGE,
                  prior_bank_path=None, unit="phrase", review_only=False):
    if unit not in UNIT_RULES:
        raise ValueError(f"Unknown omission unit: {unit}")
    if review_only and not prior_bank_path:
        raise ValueError("Review-only mode requires --prior-bank")
    if prior_bank_path and bank_path.resolve() == prior_bank_path.resolve():
        raise ValueError("Save the new review separately from its prior bank")
    manifest = read(manifest_path)
    sources = english_by_passage()
    clean = {w["id"]: w["conditions"]["clean"]["verses"] for w in manifest["windows"]}
    # Validate all input bindings before incurring model calls. Supply only clean verses to the models.
    roster = dict(release=manifest["release"], provenance=f"Proposed by {writer}. Independently reviewed by {reviewer}.",
                  windows=[dict(window_id=i, clean_zh_sha256=clean_digest(v), phrases=[]) for i,v in clean.items()])
    bank = compile_bank(roster, manifest, sources)
    bank.update(mode="automatic", unit=unit, review_version=6 if unit == "word" else 4, writer=writer, reviewer=reviewer,
                required_checks=list(WordChecks.model_fields if unit == "word" else Checks.model_fields),
                semantic_distortion_policy="flag")
    if unit == "word":
        bank["information_loss_policy"] = "key_content_required"
        bank["key_content_categories"] = sorted(KEY_CONTENT_CATEGORIES)
        bank["excluded_word_markers"] = sorted(EXCLUDED_WORD_MARKERS)
    if review_only:
        bank["review_only"] = True
    prior_by_window = {}
    if prior_bank_path:
        prior = read(prior_bank_path)
        prior_by_window = {w["window_id"]:w for w in prior["windows"]}
        if (prior["release"] != bank["release"] or prior.get("mode") != "automatic" or prior.get("unit") != unit
                or set(prior_by_window) != set(clean) or len(prior["windows"]) != len(clean)):
            raise ValueError("Prior automatic bank does not match this release")
        for w in bank["windows"]:
            old = prior_by_window[w["window_id"]]
            if any(old[k] != w[k] for k in ("passage_id", "verses", "clean_zh_sha256", "english_sha256")):
                raise ValueError(f'Prior window changed: {w["reference"]}')
            keys = [proposal_location(c["proposal"]) for c in old["candidates"]]
            if len(keys) != len(set(keys)):
                raise ValueError(f'Prior window has duplicate phrase locations: {w["reference"]}')
        bank["compared_to"] = prior_bank_path.name
        if review_only:
            bank["writer"] = prior["writer"]
            bank["provenance"] = (f'Existing proposals by {prior["writer"]} from {prior_bank_path.name}. '
                                  f'Re-reviewed independently by {reviewer}; no new proposals.')
    load_dotenv(ROOT / ".env")
    with OpenAI(timeout=150.0, max_retries=3) as client, ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(process_window, client, run, w, clean[w["window_id"]], sources[w["passage_id"]],
                            writer, reviewer, prior_by_window.get(w["window_id"]), unit, review_only):i
                for i,w in enumerate(bank["windows"])}
        done = 0
        for future in as_completed(jobs):
            w = future.result()
            bank["windows"][jobs[future]] = w
            done += 1
            print(f'{unit} {done}/{len(jobs)} {w["reference"]} {dict(Counter(c["status"] for c in w["candidates"]))}', flush=True)
    report = make_report(bank, manifest, sources)
    save(bank_path, bank)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return bank
