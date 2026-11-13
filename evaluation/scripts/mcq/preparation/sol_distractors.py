"""Generate and review Chinese Sol MCQs, including targeted repairs of held items."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from eten_shared.manual_wording import manual_fields
from eten_shared.mcq_retirement import REPAIR_STAGES as EXTENDED_REPAIR_STAGES, published_signature, validate_final_review
from evaluation.scripts.mcq.preparation import relevance_chain as audit, rewrite_distractors as writer
from evaluation.scripts.pipeline.verify_reviewed122_zh import OPTION_DETAIL_RULE, read, write
from qa_generation.services import mcq_complexity, mcq_target
from qa_generation.services.window_mcq import CHOICE_REVIEW_PROMPT, WindowReview, four_distinct

ROOT = Path(__file__).resolve().parents[4]
BANK = ROOT / "evaluation/datasets/qa/reviewed122_sol"
MODEL = "gpt-6.1-sol"
JUDGE = "gpt-6-astra"
LETTERS = "ABCD"
CLAIM_SCOPE = (
    "Preserve who or what the passage describes, the property it states, and its scope. "
    "Availability in a place does not by itself establish what its inhabitants possessed, "
    "needed, received, or experienced. Check whether the added link is established in "
    "the displayed verses. Accept ordinary paraphrases and unambiguous references to the same entity."
)
SOURCE_TARGET = (
    "Keep the information the reader must supply. If the source asks whom someone killed, "
    "helped or addressed, the reader must still identify that person. Giving the identity "
    "in the question and asking for an action, relationship, or title changes the target. "
    "A description answers a different question from a cause. If the displayed Chinese "
    "cannot support the original target or a fair four-choice menu, hold the item. "
    "An editor can separately approve a substitute question or response format."
) + " " + CLAIM_SCOPE
DIRECT_STEM = (
    "Start with the source question's unknown. Ask about the passage action with that "
    "participant or object left blank. For an identity target, use an ordinary verb and 谁. "
    "Keep a role question when the source actually asks about someone's role. "
    "If an introductory speaker, narrator or verse reference can be removed without "
    "changing who did what or whose view matters, drop the introduction. Anchor the event "
    "in its actors or addressees from these verses. Preserve a request, wish, condition or "
    "belief as such. When competing accounts make attribution necessary, use a speaker "
    "identified in the displayed Chinese. Never supply a name solely from the source, "
    "chapter context, or a reviewer's suggestion."
)
WINDOW_GUIDE = (
    "Ground the question's setup, including anonymous roles, recipients and whether events "
    "were proposed or happened, in the displayed window. Ask for the same fact through the "
    "supported action if its surrounding context is absent. Use the excerpt's precise ranks "
    "and institutions. Preserve the action attached to each participant, including the "
    "difference between what they do and what is predicted to happen to them. "
    "Write direct Chinese questions and read each choice as its answer. "
    "For a who-question, use parallel person or role labels without an orphan possessive. "
    "Distinguish a group's place of origin from the place of an event, and a pronoun's "
    "addressee from people named in a different clause. Avoid a quoted lookup phrase or "
    "verse number that points directly to the answer. Balance recurring components across "
    "list positions, including the endings of the three distractors."
)
STEM_SIMPLICITY = (
    "If an action with a companion, place and time already identifies the episode, drop "
    "extra possessor chains and reflexives that add no distinction. Use an ordinary verb "
    "and the short, unambiguous name of the place. Keep kinship, ownership and formal "
    "titles when the question tests them or multiple people, places or offices compete. "
    "When asking for a location, give locations in all four choices and retain any essential "
    "purpose in the stem. Name a person the excerpt identifies if 'that woman' or a similar "
    "phrase requires the reader to resolve an unrelated reference."
)
CLAUSE_STRUCTURE_GUIDE = (
    "Compare the structures of all four substantive choices. Avoid a three-versus-one pattern "
    "that singles out the key: for example, three event-plus-consequence choices versus a "
    "bare event, or a key giving two coordinated actions versus three single-action choices. "
    "Look at predicates and their relationships, even when connectives or punctuation differ. "
    "A natural two-and-two split is fine. Prefer revising just enough wrong choices that the "
    "key has a structural peer. Preserve both parts of a keyed fact and the direction of actions. "
    "Use nearby, plausible mix-ups that remain unambiguously wrong as answers to this stem. "
    "Check openings as well as endings. If the key alone repeats a reporting or passive "
    "frame from the stem and the other three give direct answers, remove the needless "
    "opening from the key during repair. A shared ending does not hide a unique opening. "
    "Both parts of a paired alternative must contribute to its answer. Prefer two plausible "
    "grievances, outcomes or actions involving the same participants or objects as the key. "
    "Avoid an incidental gesture added to a real cause, filler consequences, invented subplots, "
    "and a one-part truth masquerading as false."
)
MENU_DESIGN_GUIDE = (
    "Compress the whole menu when several choices repeat a setting or carry a dispensable "
    "second clause. Keep roles, mutual actions, and wishes versus predictions clear. "
    "Build wrong alternatives from plausible mix-ups among the passage's actors, objects, "
    "outcomes or sequence. Do not import three unrelated episodes. If only the correct "
    "personal name appears among the options in the excerpt, use plausible in-window "
    "candidates who could be confused in this scene. Preserve the original question's "
    "unknown. Hold an identity item if a fair menu cannot be constructed. Avoid making "
    "the key the lone semantic category among three near-duplicate choices. In a negative "
    "question each wrong option must describe an action that really occurred in the excerpt. "
    "For an explicit cause, prefer other events the reader just encountered in the excerpt "
    "as wrong causes. Retain only one textually supported cause and keep the choices parallel."
) + " " + CLAUSE_STRUCTURE_GUIDE
GUIDE = ("Write concise, natural Simplified Chinese for each wrong answer. Keep necessary "
         "contrasts and names as written in the clean passage. For a who or where question "
         "a name or place can stand alone. Avoid repeating the stem or adding unasked traits. "
         "Keep the supplied key and its position verbatim. " + MENU_DESIGN_GUIDE + " " + WINDOW_GUIDE)
MAX_DRAFTS = 3
REPAIR_STAGES = EXTENDED_REPAIR_STAGES[:2]


def digest(v):
    return sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class StrictCompletions:
    """Expose the project's existing writer API and surface malformed completions for retry."""

    def __init__(self, client):
        self.client = client

    def create(self, **kwargs):
        response = self.client.chat.completions.create(**kwargs,
                                                       store=False,
                                                       response_format={"type": "json_object"})
        choice = response.choices[0]
        if choice.finish_reason != "stop": raise ValueError("Incomplete writer response")
        result = writer.parse_json(choice.message.content or "")
        if not isinstance(result, dict) or not all(
                isinstance(result.get(l), str) and result[l].strip() for l in LETTERS):
            raise ValueError("Writer omitted a study choice")
        return response


def cached(directory, name, signature, compute):
    path = directory / (name + ".json")
    token = digest(signature)
    if path.exists():
        rec = read(path)
        if rec["signature"] != token: raise RuntimeError("Checkpoint differs: " + str(path))
        return rec["result"]
    result = compute()
    write(path, dict(signature=token, result=result))
    return result


def parsed(client, messages, schema, expected, field):
    response = client.responses.parse(model=JUDGE,
                                      store=False,
                                      input=messages,
                                      text_format=schema,
                                      reasoning={"effort": "medium"},
                                      max_output_tokens=5000)
    if response.output_parsed is None: raise ValueError("Reviewer returned no structured verdict")
    result = getattr(response.output_parsed, field)
    if sorted(v.letter for v in result) != sorted(expected):
        raise ValueError("Reviewer returned incomplete letter coverage")
    return {v.letter: v.model_dump() for v in result}


def audit_messages(template, args):
    return [
        dict(role="system" if m.type == "system" else "user", content=m.content)
        for m in template.format_messages(**args)
    ]


class OptionCue(BaseModel):
    letter: Literal["A", "B", "C", "D"]
    kind: Literal["shared_context", "avoidable_detail"]
    excerpt: str
    reason: str


class MenuWithCues(WindowReview):
    cues: list[OptionCue]


MENU_CUES = """ Also inspect all options side by side for wording that gives away a choice.
Report a cue when optional details, modifiers or distinctive echoes of the verse let one
choice stand out from its peers even before the reader understands the answer. Do not
flag essential content or length alone. Use shared_context only when one option spells
out an actor or circumstance shared by all options that could be named once in the
question without revealing the answer. Otherwise use avoidable_detail. Record the letter,
exact option excerpt and concrete reason for every cue. Use an empty list if none."""


class BlindMenu(MenuWithCues):
    stem_issue: Literal["none", "ambiguous", "compound", "unsupported_premise"]
    stem_reason: str


class KeyCueReview(BaseModel):
    redundant_stem_excerpt: str
    avoidable_length_excerpt: str
    reason: str


KEY_CUES = """Review the correct answer of this Simplified Chinese passage-comprehension item
for two cues. Read the stem with the answer as a pair and compare the other three choices.
For redundant_stem_excerpt, quote exact words from the key that needlessly restate the
question's setup, subject and predicate, or premise. Look for paraphrases as well as copied
words. Flag this even when the answer is short or the other answers are equally long.
A who/where/which question can often be answered by the name, place or list alone. For
example, when asked whom someone fought, keep the enemies and drop a repeated introduction
saying that the person fought them. A shared name alone, natural pronoun, or grammatical
link is insufficient evidence of a cue. Preserve repeated material that identifies a necessary
referent, distinguishes roles, gives a requested reason, or makes the answer intelligible.

When length_screen is true, decide whether the unusually long key includes avoidable
framing, optional details, or a clause that could be compressed without changing the full
answer. If so, copy that span into avoidable_length_excerpt. If the length is needed for
the requested list, direction, quantities, qualifiers, or contrasts, explain this in reason
and leave the excerpt empty. When length_screen is false leave avoidable_length_excerpt
empty. Use empty strings for absent cues. Give a brief, specific English reason. Never
suggest padding distractors or dropping required detail to meet a length target."""


def key_cue_review(client, row, folder):
    options = dict(zip(LETTERS, row["choices"][:4], strict=True))
    key = row["correct"]
    lengths = {letter: sum(ch.isalnum() for ch in wording) for letter, wording in options.items()}
    _, median, longest = sorted(n for letter, n in lengths.items() if letter != key)
    screen = lengths[key] - longest >= 3 and lengths[key] >= 1.35 * median
    payload = dict(question=row["question"], options=options, correct_letter=key, verses=row["verses"],
                   lengths=lengths, length_screen=screen)

    def assess():
        for attempt in range(2):
            prompt = KEY_CUES
            if attempt:
                prompt += "\nCopy flagged excerpts verbatim from the key. Follow the length_screen setting."
            review = model_review(client, JUDGE, prompt, payload, KeyCueReview)
            excerpts = [review["redundant_stem_excerpt"], review["avoidable_length_excerpt"]]
            if (review["reason"].strip() and all(not s or (s.strip() and s in options[key]) for s in excerpts)
                    and (screen or not review["avoidable_length_excerpt"])):
                return review
        raise ValueError("Key cue review did not supply valid evidence for the current key.")

    review = cached(folder, "key_cues", [JUDGE, KEY_CUES, payload], assess)
    findings = []
    for field, title in (("redundant_stem_excerpt", "repeats the question"),
                         ("avoidable_length_excerpt", "stands out by length")):
        if review[field]:
            findings.append(f"Fixed key {key} {title}: “{review[field]}”. {review['reason']}")
    return dict(lengths=lengths, length_screen=screen, **review), findings


class TranslationFinding(BaseModel):
    field: Literal["Q", "A", "B", "C", "D"]
    excerpt: str
    reason: str


class TranslationReview(BaseModel):
    findings: list[TranslationFinding]


class StemIdentity(BaseModel):
    name: str
    verdict: Literal["grounded", "unsupported"]
    verse: str
    quote: str
    suggested_description: str
    reason: str


class StemIdentityReview(BaseModel):
    names: list[StemIdentity]


class MenuDesignFinding(BaseModel):
    kind: Literal["menu_wordiness", "unrelated_distractors", "name_matching", "semantic_outlier", "asymmetric_frame", "clause_structure_cue"]
    letter: Literal["A", "B", "C", "D"]
    excerpt: str
    reason: str


class MenuDesignReview(BaseModel):
    findings: list[MenuDesignFinding]


class SharedContextReview(BaseModel):
    move_to_stem: bool
    reason: str


def repeated_menu_context(options):
    """Locate substantial repeated Chinese wording for a semantic compression check."""
    if sum(sum(ch.isalnum() for ch in text) >= 15 for text in options.values()) < 3:
        return ""
    counts = Counter()
    for text in options.values():
        spans = {word[start:end] for word in re.findall(r"[\u3400-\u9fff]+", text)
                 for start in range(len(word)) for end in range(start + 5, len(word) + 1)}
        counts.update(spans)
    return max((span for span in counts if counts[span] >= 3),
               key=lambda span: (len(span), counts[span], span), default="")


COMPRESSION = """Several Chinese choices repeat the supplied span. Read the entire menu and
clean verses. Can the shared participants or setting be named once in the question so that
three or more options can be substantially shorter? Show a specific way to express the
stem and the option contrasts. Preserve distinct actors, direction, both sides of a
reciprocal act, modality and the unique key. Different actors within the same setting can
use short references once the identities are clear. Return false if this leaks the answer,
changes the target or merely removes necessary distinctions. Length alone is insufficient."""


MENU_DESIGN = """Evaluate these design defects in a Chinese reading-comprehension menu.
(1) menu_wordiness: multiple options have redundant scene setting or needless elaboration.
Identify concrete compression that retains each option's distinct main claim and the target,
including both parties, direction, force and qualifications. May put shared context in the
stem if it does not reveal the answer. Similar lengths do not excuse wordiness. Do not
flag a single long option, essential lists, or merely deleting one ordinary connective.
(2) unrelated_distractors: the wrong answers as a set import unrelated events or concepts.
Show how scanning for their distinctive vocabulary would eliminate them without understanding
the target AND identify a plausible mix-up using more of the excerpt. Check actions as
well as nouns: reusing a local object in three invented events still allows elimination.
A plausible nearby
alternative is allowed even if its precise words are absent. Do not require a wrong
proposition to be stated or treat ordinary numeric/date alternatives as imported episodes.
(3) name_matching: the stem asks for a person or named group and the correct name is the
only candidate recognizable in the excerpt. Check each competing candidate, including
transparent aliases/roles. Can the reader choose the key without working out who did what
or how the people are related? If the same names recur across choices in different roles,
this cue does not apply. Do not flag a question simply because its answer is mentioned.
(4) semantic_outlier: three options repeat closely related actions or objects in one
narrow category, making the key guessable as the only different kind. Give the specific
three-versus-one grouping. Include a sole personal name competing with three labels for
employees when this lets readers guess the employer without understanding the passage.
For negative stems check polarity: every distractor must describe
something that happened. Identify a grounded distractor from the underrepresented category.
Do not flag two-versus-two contrasts or legitimate factual distinctions merely for being
different. Cite a representative wrong choice from the group of three.
(5) asymmetric_frame: the key alone either retains or omits a needless reporting clause,
actor, opening or closing frame. Compare both ends independently. If three options are bare
answers and only the key begins by repeating the question (including a passive reporting
phrase), cite the key's removable opening even when all four share the same ending.
Prefer dropping a needless frame rather than spreading it to other choices. A two-and-two
split does not isolate the key by form. Do not flag necessary attribution or length alone.
(6) clause_structure_cue: compare the construction of each full option, excluding E.
Flag when the key is the only choice with (or without) a salient grammatical pattern the
other three share. Three event-plus-result options can use different words (e.g. 使 or 将).
Two coordinated actions can share a subject and omit a comma, while a single action can
take two nouns. Compare independent actions/results, not numbers of verbs, objects or commas.
A necessary second action in the key still needs a structural peer among the distractors.
Accept a two-and-two split, four parallel choices, or an outlier that is a distractor.
Only flag a two-and-two menu if a DIFFERENT concrete construction independently isolates
the key three to one. Cite a verbatim span of the key. In the reason identify each
letter's construction and explain which wrong choice(s) could remove the shortcut.
Use this finding for an imbalance in the number or relationship of actions, even if the
options are the same length. Use asymmetric_frame for repeated reporting/answer wrappers.
Report each applicable kind once. For each quote a short exact span from the option at
the reported letter and give a specific explanation and repair direction. For name_matching
cite the key; for unrelated_distractors cite a wrong choice. Use an empty list when clear."""


def menu_design_review(client, row, folder):
    options = dict(zip(LETTERS, row["choices"][:4], strict=True))
    key = row["correct"]
    payload = dict(question=row["question"], options=options, correct_letter=key, clean_verses=row["verses"])
    # Point the reviewer to either comma pattern without treating punctuation as a verdict.
    breaks = {letter: bool(re.search(r"[,，;；]", text)) for letter,text in options.items()}
    if all(breaks[l] != breaks[key] for l in LETTERS if l != key):
        payload["clause_screen"] = ("Only the key contains an internal clause separator." if breaks[key] else
                                    "All three wrong choices contain an internal separator; the key has none.")
    # A shared subject alone can be necessary. Let the reviewer distinguish it from a dispensable wrapper.
    for length in range(min(len(options[key]) - 1, len(row["question"])), 2, -1):
        prefix = options[key][:length]
        if prefix in row["question"] and not any(v.startswith(prefix) for l,v in options.items() if l != key):
            payload["unique_stem_opening"] = prefix
            break

    def assess():
        for suffix in ("", "\nEach cited span must occur verbatim in the option at the stated letter."):
            record = model_review(client, JUDGE, MENU_DESIGN + suffix, payload, MenuDesignReview)
            issues = record["findings"]
            if (len({v["kind"] for v in issues}) == len(issues)
                    and all(v["reason"].strip() and v["excerpt"].strip() and v["excerpt"] in options[v["letter"]]
                            and (v["kind"] not in ("name_matching", "asymmetric_frame", "clause_structure_cue")
                                 or v["letter"] == key)
                            and (v["kind"] not in ("unrelated_distractors", "semantic_outlier")
                                 or v["letter"] != key) for v in issues)):
                return record
        raise ValueError("Menu design review lacks valid option evidence.")

    record = cached(folder, "menu_design", [JUDGE, MENU_DESIGN, payload], assess)
    shared = repeated_menu_context(options)
    if shared and not any(v["kind"] == "menu_wordiness" for v in record["findings"]):
        comparison = dict(payload, shared_span=shared)
        check = cached(folder, "shared_menu_context", [JUDGE, COMPRESSION, comparison],
                       lambda: model_review(client, JUDGE, COMPRESSION, comparison, SharedContextReview))
        if not check["reason"].strip():
            raise ValueError("Shared context review omitted the reason.")
        if check["move_to_stem"]:
            letter = next(l for l in LETTERS if shared in options[l])
            record = dict(findings=[*record["findings"], dict(kind="menu_wordiness", letter=letter,
                                                            excerpt=shared, reason=check["reason"])])
    fixed, other = [], []
    for issue in record["findings"]:
        if issue["kind"] == "clause_structure_cue":
            other.append(f"Menu (clause_structure_cue): Key {key}, “{issue['excerpt']}”. {issue['reason']}")
            continue
        message = f"{issue['letter']} ({issue['kind']}): “{issue['excerpt']}”. {issue['reason']}"
        (other if issue["kind"] in ("unrelated_distractors", "semantic_outlier") else fixed).append(message)
    return dict(checks={"menu_design": record}, fixed_findings=fixed, findings=other)


STEM_IDENTITY = """Read the current Chinese stem and only the displayed Chinese verses.
Inventory the personal names and named groups the stem uses to identify participants.
For each, check whether this excerpt establishes the name AND attaches it to the actor
in that role or action. A named person elsewhere in the same excerpt need not be this
speaker. A recoverable answer does not license an unsupported identity. Do not look up
the book, use Bible knowledge or infer a name solely because a familiar event occurs.
Distinguish naming the person from unambiguously following an ordinary pronoun, role,
short form of a name or direct narrative continuation. Ordinary role descriptions and
equivalent titles for God are fine. Exclude place names used solely as locations,
names in choices, and identities the question asks the reader to supply.
For a personal or group name known only from outside the window, a wrong name, or a
name assigned to the wrong actor, mark unsupported even if the action itself is clear.
Give the shortest natural Chinese replacement describing that same participant if the
window supports one. Prefer an actual role noun in the excerpt. Leave it empty if a
substitution would be ambiguous, introduce a fact, or give away the answer.
For every name give its exact text in the stem, one verse label and a short contiguous
verbatim Chinese quote identifying the participant or showing how the passage refers
to them. An unsupported name with no relevant evidence can have an empty label and quote.
Grounded names require evidence and an empty suggested_description. Explain briefly in
English. Return each distinct name once and an empty list when there are none."""


def stem_identity_review(client, row, folder):
    payload = dict(question=row["question"], verses=row["verses"])

    def assess():
        for hint in ("", "\nUse exact stem text and copy each quotation from its labeled verse."):
            result = model_review(client, JUDGE, STEM_IDENTITY + hint, payload, StemIdentityReview)
            names = result["names"]
            if len({n["name"] for n in names}) != len(names):
                continue
            for n in names:
                cited = (n["quote"].strip() and n["verse"] in row["verses"]
                         and n["quote"] in row["verses"][n["verse"]])
                absent = n["verdict"] == "unsupported" and not any(
                    n[k] for k in ("verse", "quote", "suggested_description"))
                if (not n["name"].strip() or n["name"] not in row["question"] or not n["reason"].strip()
                        or not (cited or absent) or n["verdict"] == "grounded" and n["suggested_description"]):
                    break
            else:
                return result
        raise ValueError("Stem identity review did not supply valid names and passage evidence.")

    result = cached(folder, "stem_identity", [JUDGE, STEM_IDENTITY, payload], assess)
    issues = []
    for n in result["names"]:
        if n["verdict"] == "unsupported":
            issue = f"Fixed question (identity): “{n['name']}”. {n['reason']}"
            if n["suggested_description"]:
                issue += f" Use the passage description “{n['suggested_description']}” if it preserves the target."
            issues.append(issue)
    return dict(checks={"stem_identity": result}, fixed_findings=issues, findings=[])


class PremiseFinding(BaseModel):
    excerpt: str
    verse: str
    quote: str
    reason: str


class PremiseReview(BaseModel):
    findings: list[PremiseFinding]


class UsageFinding(PremiseFinding):
    field: Literal["Q", "A", "B", "C", "D"]
    kind: Literal["grammar", "indirect_wording", "unclear_reference", "terminology", "grammatical_cue", "answer_locator", "unsupported_detail"]


class UsageReview(BaseModel):
    findings: list[UsageFinding]


PREMISE = """Read only the question and the displayed Chinese verses. Separate what the
question ASKS from what it already ASSERTS. Check every presupposed role, participant,
speaker, addressee, object, relationship, location, cause, and time or completed action.
An implied invitation can be clear while the inviter's title is unknowable. Check who says
something, including plans, reported beliefs and speculation presented as accomplished fact.
Do not import surrounding verses or infer a title from wealth, speech or Bible knowledge.
Distinguish a person named in the next narrated action from the speaker of preceding
dialogue. A speaker may dispute the observer's identification. Do not adopt that identification
as a shared premise. Separate a future expectation from an experienced benefit, a wish
from a prediction, and an event immediately preceding another from a sustained activity.
For reasons and complaints, check whether two events at different times fit the open stem.
Co-occurrence or narrative sequence alone seldom establishes why an event occurred.
Distinguish a request from its performance, a group's origin from the scene of its death,
and an audience addressed by a pronoun from a group named in another conditional branch.
Allow unambiguous pronoun resolution, ordinary synonyms and direct, necessary inferences
within the window. Do not flag the identity or event being asked for merely because the stem
does not state the answer. For a causal question, establish that the displayed verses actually
connect a cause to the outcome. If they only describe abundance, safety, or another state,
do not assume a cause from a restatement, or import a causal clause from another translation.
Flag the why-phrase when the relationship the question presupposes is absent. For each
unsupported premise quote its shortest exact span in
the question and the nearest relevant exact text from one labeled verse. Explain in English
what the passage establishes and what the question adds. Return no findings if grounded."""

USAGE = """Review the displayed Chinese stem and A–D one by one as a native reader.
Check for a stem that quotes a nonessential search phrase immediately adjacent to the
answer in the displayed verse. Report answer_locator only if this gives away where to
copy the answer. Check for extra demographic or geographic details in descriptions
of the same actors or site (unsupported_detail). A deliberate wrong alternative may
misdescribe the answer; flag an incidental unsupported premise only if it mislabels a
shared participant or setting. Distinguish nearby senses such as lodging and tribal territory.
Report concrete grammar errors, including a dangling or missing possessive, broken syntax,
or an answer that grammatically cannot complete the question. Chinese ellipsis, a bare name,
or a grammatical nominalized 的 are legitimate. Flag a grammatical cue when only one answer
fits (or conspicuously breaks) the grammar, even if one can infer the intended key.
Compare the choice endings explicitly. If one bare personal name bears possessive 的 and the
other comparable names have no possessive, report grammatical_cue on that choice even if
ellipsis could license that answer in isolation. Assess the stem's wording independently.
Flag an indirect stem when an abstract or nested frame obscures a simple action or relationship
and you can express the same target directly. Do not flag stylistic preferences.
Check if a chain identifying whose relative or caregiver is involved can be removed while
the companion, place and time still uniquely identify the episode. Use indirect_wording for
an unnecessary chain. A single natural possessive can remain when it adds a distinction.
Check for literal or literary wording that suggests a different event (such as a physical
arrival for the reception of a message), nested descriptions of two people in one family,
and route or speech details that can be removed while the intended episode remains unique.
Flag unclear_reference when a pronoun, passive attribution, or generic speech event makes
readers guess who saw, spoke, or made a claim. Trace the referent in the actual stem and
window. A clear ordinary pronoun is fine. For an indirect or unclear stem, diagnose the
wording and quote the passage evidence. Leave drafting the repair to the source-aware
writer. Check whether the question can ask about the action directly. A speaker matters
when the passage distinguishes competing claims or when attribution is the tested fact.
Do not demand a speaker's name merely because the action appears in dialogue.
Check ranks, titles, offices, institutions, and technical roles in the stem and each choice.
When a field refers to the same passage entity, flag a substitution that changes rank, conflates
distinct roles, or makes identification rely on a specialist synonym or a chapter outside the
window. Compare official terms field by field, including the stem's institutional label even
when a key uses a different rank as well. For a named institution or office with a specific
formal label in the window, flag an unexplained shortened or alternate formal title even
when a specialist would recognize it. Explain whether this is terminology consistency or
a substantive change of rank. A short familiar place label such as 圣殿 for 耶和华的殿 is
appropriate when these verses contain one temple and the question does not test its dedication.
Keep separate places, such as the temple and an inner sanctuary, distinct. Accept ordinary synonyms for everyday roles and labels used
interchangeably for the same entity in these verses. A genuinely different role offered as a wrong alternative is
allowed. Do not make every distractor use the correct entity. Quote an exact span of the
affected field, and short exact evidence from a labeled verse. Explain the issue and a
minimal correction in English. Report each distinct (field, kind) at most once."""


def window_wording_review(client, row, folder):
    fields = dict(zip(LETTERS, row["choices"][:4], strict=True), Q=row["question"])
    checks, fixed, other = {}, [], []
    for name, prompt, schema, payload in (
        ("stem_premise", PREMISE, PremiseReview, dict(question=row["question"], verses=row["verses"])),
        ("chinese_usage", USAGE, UsageReview, dict(fields=fields, verses=row["verses"])),
    ):
        def assess():
            for hint in ("", "\nCopy every cited span exactly, without adding punctuation or ellipses.",
                         "\nUse only short contiguous verbatim spans and the supplied verse labels."):
                verdict = model_review(client, JUDGE, prompt + hint, payload, schema)
                findings = verdict["findings"]
                ids = [(f.get("field", "Q"), f.get("kind", "premise"), f["excerpt"]) for f in findings]
                if len(set(ids)) == len(ids) and all(
                    f["excerpt"].strip() and f["excerpt"] in fields[f.get("field", "Q")]
                    and f["quote"].strip() and f["quote"] in row["verses"].get(f["verse"], "")
                    and f["reason"].strip() for f in findings
                ):
                    return verdict
            raise ValueError(f"{name} review lacks verbatim field or passage evidence.")

        checks[name] = cached(folder, name, [JUDGE, prompt, payload], assess)
        if name == "chinese_usage":
            checks[name] = dict(findings=local_title_findings(row, checks[name]["findings"]))
        for f in checks[name]["findings"]:
            field = f.get("field", "Q")
            label = "Fixed question" if field == "Q" else f"Fixed key {field}" if field == row["correct"] else field
            issue = f"{label} ({f.get('kind', 'premise')}): “{f['excerpt']}”. {f['reason']}"
            (fixed if field in ("Q", row["correct"]) else other).append(issue)

    choices = row["choices"][:4]
    lists = position_cue(choices, row["correct"])
    checks["list_position_cue"] = lists
    if lists:
        fixed.append("List positions reconstruct the key: " + " / ".join(lists))
    shortlist = modal_shortlist(choices, row["correct"])
    if shortlist:
        checks["list_shortlist"] = shortlist
        fixed.append("Frequent entries in at least two list positions narrow the choices to "
                     + " and ".join(shortlist) + ". Rebalance the lists.")
    endings = shared_distractor_members(choices, row["correct"])
    checks["list_distractor_cue"] = endings
    fixed.extend(f"All three distractors have {word} in position {position}; the key omits it."
                 for position, word in endings)
    return dict(checks=checks, fixed_findings=fixed, findings=other)


def local_title_findings(row, findings):
    """Preserve the formal council label used in this window when the stem names it."""
    short, formal = "公会", "公议会"
    verses = row["verses"]
    if (short not in row["question"] or any(short in s for s in verses.values())
            or any(f["field"] == "Q" and f["kind"] == "terminology" and short in f["excerpt"] for f in findings)):
        return findings
    for label, text in verses.items():
        if formal in text:
            return [*findings, dict(field="Q", kind="terminology", excerpt=short, verse=label,
                                    quote=formal, reason="Use the formal council label 公议会 supplied in this window.")]
    return findings


def option_lists(choices):
    if not all("、" in choice for choice in choices):
        return []
    lists = []
    for choice in choices:
        parts = choice.strip().rstrip("。").split("、")
        # A final conjunction can introduce the last member of an enumerated list.
        # Bare 及 also occurs within names such as 埃及人.
        parts[-1:] = re.split(r"以及|(?<!耶)和|与", parts[-1], maxsplit=1)
        lists.append([part.strip() for part in parts])
    if len({len(parts) for parts in lists}) != 1 or any(not all(parts) for parts in lists):
        return []
    return lists


def shared_distractor_members(choices, key):
    lists = option_lists(choices)
    if not lists:
        return []
    answer = lists[LETTERS.index(key)]
    others = [parts for letter, parts in zip(LETTERS, lists, strict=True) if letter != key]
    return [(index, column[0]) for index, column in enumerate(zip(*others, strict=True), 1)
            if len(set(column)) == 1 and column[0] not in answer]


def position_cue(choices, key):
    """Identify a complete key reconstructed by unique modes across varying list positions."""
    lists = option_lists(choices)
    if not lists:
        return []
    modes, varying = [], 0
    for parts in zip(*lists, strict=True):
        most = Counter(parts).most_common()
        if len(most) > 1:
            if most[0][1] == most[1][1]:
                return []
            varying += 1
        modes.append(most[0][0])
    return modes if varying >= 2 and lists[LETTERS.index(key)] == modes and lists.count(modes) == 1 else []


def modal_shortlist(choices, key):
    """Return both surviving letters when two or more informative positions narrow the menu."""
    lists = option_lists(choices)
    if not lists:
        return []
    survivors = set(LETTERS)
    informative = 0
    for column in zip(*lists, strict=True):
        counts = Counter(column)
        largest = max(counts.values())
        if len(set(counts.values())) == 1:
            continue  # A fixed entry or a tie across all alternatives gives no clue.
        informative += 1
        survivors.intersection_update(l for l, value in zip(LETTERS, column) if counts[value] == largest)
    return sorted(survivors) if informative >= 2 and len(survivors) == 2 and key in survivors else []


TRANSLATION_REVIEW = """Read the Chinese question (Q) and all four options as material a
translator will have to render in another language. Review each field, including short
or equal-length choices. Flag a concrete, avoidable difficulty when the same comprehension
target can be expressed directly: a perception wrapped around reported speech or another
event with shifting actors; an ambiguous pronoun or unnecessarily formal idiom; a chain
of purpose or consequence clauses that restates a single idea. Compare with the passage:
flag carrying over a whole clause and then saying substantially the same thing again when
the answer can instead give the reason or event once in ordinary words. Shared names and
necessary facts from the passage are expected. Consider whether an event-based stem would
let the choices name the events directly. Only flag Q for a coordinated change if it helps
retain the exact event tested or if its own wording is difficult. Preserve who did what
to whom, complicity, quantities, timing, and distinctions on which the answer depends.
An ordinary direct event, an essential relationship, or a necessary quotation can pass.
When the target is someone's interpretation of another person's observation, a short
attribution with both roles explicit is necessary. Flag only a specific removable layer
or real ambiguity. Exchanging two equally simple ways to express the same attribution
does not demonstrate a translation difficulty. Keep the speaker's claim distinct from
the narrator's description.
Judge wording in context, independently of length and of whether the options are parallel.
For each affected field give one exact excerpt and a specific reason, including the
meaning the repair must retain. Return no findings for wording that is already plain."""


def translation_review(client, row, folder):
    fields = dict(zip(LETTERS, row["choices"][:4], strict=True), Q=row["question"])
    payload = dict(fields=fields, clean_verses=row["verses"])

    def assess():
        for suffix in ("", "\nQuote the flagged text exactly, record each affected field only once."):
            result = model_review(client, JUDGE, TRANSLATION_REVIEW + suffix, payload, TranslationReview)
            findings = result["findings"]
            if (len({f["field"] for f in findings}) == len(findings)
                    and all(f["reason"].strip() and f["excerpt"].strip()
                            and f["excerpt"] in fields[f["field"]] for f in findings)):
                return result
        raise ValueError("Translation review returned duplicate fields or invalid evidence.")

    record = cached(folder, "translation_review", [JUDGE, TRANSLATION_REVIEW, payload], assess)
    fixed, other = [], []
    for finding in record["findings"]:
        field = finding["field"]
        label = "Fixed question" if field == "Q" else (
            f"Fixed key {field}" if field == row["correct"] else field)
        issue = f"{label} (translation): “{finding['excerpt']}”. {finding['reason']}"
        (fixed if field in ("Q", row["correct"]) else other).append(issue)
    return dict(checks={"translation_review": record}, fixed_findings=fixed, findings=other)


def review_choices(client, row, d, *, full_review=False):
    key = row["correct"]
    question = row["question"]
    window = "\n".join(f"{number}  {verse}" for number, verse in row["verses"].items())
    opts = dict(zip(LETTERS, row["choices"][:4], strict=True))
    others = [letter for letter in LETTERS if letter != key]
    args = dict(question=question,
                correct=key,
                correct_text=opts[key],
                window=window,
                distractors="\n".join(f"{l}. {opts[l]}" for l in others))
    findings = []
    fixed = []
    checks = {}
    if not four_distinct(list(opts.values())) or any(t == row["choices"][4] for t in opts.values()):
        findings.append("Supply distinct A–D options, each different from the fixed E response.")
    if any(not re.search(r"[\u3400-\u9fff]", opts[l]) for l in others):
        findings.append("Use natural Simplified Chinese for each distractor.")
    if not findings:
        wording = window_wording_review(client, row, d)
        checks.update(wording["checks"])
        fixed.extend(wording["fixed_findings"])
        findings.extend(wording["findings"])
        design = menu_design_review(client, row, d)
        checks.update(design["checks"])
        fixed.extend(design["fixed_findings"])
        findings.extend(design["findings"])
        identity = stem_identity_review(client, row, d)
        checks.update(identity["checks"])
        fixed.extend(identity["fixed_findings"])
        translation = translation_review(client, row, d)
        checks.update(translation["checks"])
        fixed.extend(translation["fixed_findings"])
        findings.extend(translation["findings"])
        checks["key_cues"], cue_findings = key_cue_review(client, row, d)
        fixed.extend(cue_findings)
        for title, template, schema in (("relevance", audit.relevance_prompt, audit.RelevanceAudit),
                                        ("falseness", audit.falseness_prompt, audit.FalsenessAudit)):
            messages = audit_messages(template, args)
            raw = cached(d, title, [JUDGE, messages],
                         lambda: parsed(client, messages, schema, others, "verdicts"))
            checks[title] = raw
            if title == "relevance":
                failing = [(l, v) for l, v in raw.items() if not v["is_possible_answer"]]
            else:
                failing = [(l, v) for l, v in raw.items() if v["answer_status"] == "supported"]
            for l, v in failing:
                findings.append(f"{l} ({title}): {v['reason']} {v.get('suggested_fix') or ''}".strip())
        payload = dict(question=question, window=window, options=opts)
        instructions = CHOICE_REVIEW_PROMPT + MENU_CUES + (
            " Also assess whether the question itself has an ambiguous referent, asks for two independent facts,"
            " or assumes an unsupported event. Record a stem_issue only when editing the choices alone would"
            " leave the question defective. Use none when the wording clearly asks for one supported fact.")
        menu = reviewed_blind_menu(client, d, "blind", instructions, payload, BlindMenu, key)
        blind = {v["letter"]: v for v in menu["choices"]}
        checks["stem_issue"] = menu["stem_issue"]
        if menu["stem_issue"] != "none":
            fixed.append("Fixed question: " + menu["stem_reason"])
        checks["blind"] = blind
        checks["option_cues"] = menu["cues"]
        fixed.extend(option_cue_findings(menu, opts, key))
        for l, v in blind.items():
            if l == key:
                if v["verdict"] != "supported" or v.get("circular"):
                    fixed.append(f"Fixed key {l}: {v['reason']}")
            elif v["verdict"] != "wrong" or v.get("circular"):
                findings.append(f"{l} ({v['verdict']}): {v['reason']}")
        if full_review:
            checks["key_complexity"] = cached(
                d, "key_complexity",
                [JUDGE, mcq_complexity.complexity_version(), question, window, opts[key]],
                lambda: mcq_complexity.review_complexity(client, JUDGE, question, window, {"key": opts[key]}))
            finding = checks["key_complexity"]["choices"]["key"]
            if finding["verdict"] != "pass":
                fixed.append(f"Fixed key {key}: {finding['reason']}")
        if full_review or not fixed:
            distractors = {l: opts[l] for l in others}
            complexity = cached(
                d, "complexity", [JUDGE, mcq_complexity.complexity_version(), question, window, opts],
                lambda: mcq_complexity.review_complexity(
                    client, JUDGE, question, window, distractors, correct_answer=opts[key]))
            checks["complexity"] = complexity
            findings.extend(f"{l} (wording): {v['reason']}" for l, v in complexity["choices"].items()
                            if v["verdict"] == "flag")
        if full_review or (not findings and not fixed):
            target = cached(d, "target", [JUDGE, mcq_target.target_version(), question, window, opts],
                            lambda: mcq_target.review_target(client, JUDGE, question, window, opts))
            checks["target"] = target
            if target["verdict"] != "pass":
                (fixed if target["verdict"] in ("compound_stem", "both", "ungrounded_event",
                                                "review_grounding") else findings).append(target["reason"])
    return {"checks": checks, "findings": findings, "fixed_findings": fixed}


class Edit(BaseModel):
    field: Literal["Q", "A", "B", "C", "D"]
    text: str


class Proposal(BaseModel):
    repairable: bool
    edits: list[Edit]
    reason: str


class Fidelity(BaseModel):
    same_target: bool
    clear_question: bool
    faithful_answer: bool
    evidence: str
    reason: str


REPAIR = """Repair this Chinese passage-comprehension item in a single proposal. Only edit
the listed editable fields; omit fields that do not need edits. Q is the question. Use the
clean verses for evidence. The reference question and answer establish the intended fact;
correct mistakes in the held version without changing what the reader must understand.
First try the shortest natural answer that fully answers the existing question. For who/where,
often only a name or role is needed. Keep necessary qualifiers, actors, direction, quantity
and polarity. Remove a needless restatement of the stem, keeping the information required to
answer it. Do not lengthen distractors to disguise a long key. For a translation finding,
ask for the same event or purpose directly, untangle embedded clauses, and state the
passage's point once in everyday words. Keep the evidence required for the clean answer. Repair a flagged question
by asking for the same fact clearly, without giving the answer away. Repair a flagged wrong
option as one plausible but incorrect answer to this question. Use names as printed in the
passage, natural Simplified Chinese and parallel option forms. If the passage cannot support
a faithful repair within these fields, return repairable=false with a reason. Do not move
the key letter or alter E.""" + "\n" + SOURCE_TARGET + "\n" + OPTION_DETAIL_RULE + "\n" + MENU_DESIGN_GUIDE + "\n" + WINDOW_GUIDE + "\n" + STEM_SIMPLICITY

REPAIR += """
Use the reported findings to select a repair. If a peripheral place, speaker or time is
unsupported, drop it while retaining the requested fact. Anchor competing causes to the
specific complaint or event. Preserve time, agency, reported beliefs, wishes and reciprocal
direction. If a simple person, group, place or method can answer the question, write all four
choices in the same form. Resolve passage scanning cues with plausible confusions about the
same encounter. For lists, try rotating members across positions and check the final choices.
When an edit shortens the key, check whether the same introductory or trailing words should
also be removed from the distractors. In a later round, use a different construction if
the previous repair left the same issue. Never move the tested identity into the question
to solve a shortage of alternatives. Hold the item if the original fact cannot be tested."""

FIDELITY = """Independently judge a proposed Chinese comprehension question and keyed answer.
Use the reference question and answer only to identify the intended comprehension target.
Determine from the clean excerpt alone whether the question clearly and naturally asks for
that same fact and whether the revised key gives precisely the supported answer with the
needed specificity, direction and qualifiers. Correcting an erroneous name or extra claim
in an earlier draft is appropriate if the intended fact is preserved. Consider antecedents,
awkward duplication, unsupported premises, and meaningful lost detail. A grammatical
reference question need not be worded identically. Give concise reasons. For a supported
answer, copy a short exact contiguous evidence quote from one of the supplied verses.""" + "\n" + SOURCE_TARGET


def model_review(client, model, instructions, data, schema):
    response = client.responses.parse(model=model,
                                      store=False,
                                      reasoning={"effort": "medium"},
                                      instructions=instructions,
                                      input=json.dumps(data, ensure_ascii=False),
                                      text_format=schema,
                                      max_output_tokens=4000)
    if response.output_parsed is None:
        raise ValueError(f"Incomplete {schema.__name__} response")
    return response.output_parsed.model_dump()


class AnswerMeaning(BaseModel):
    verdict: Literal["faithful", "repair"]
    target_changed: bool
    verse: str
    quote: str
    reader_meaning: str
    reason: str


MEANING = """Review the keyed Chinese answer as a native reader would understand it together
with the current question. State its ordinary meaning before judging. Use the source question
and key in their verse context to identify the intended fact. Require the Chinese clean
excerpt to support the answer as written. Compare actors, actions, objects, pronoun referents,
direction, polarity, timing, quantity, and cause or result when relevant to the question.
A different plausible everyday reading that changes the answer is a repair, even if this
is clearly the best multiple-choice option. A changed name, a claim stronger than the text,
or ambiguity about who did what also needs repair. Do not assume that being handed a key
means it is correct. Short answers, genuine paraphrases, and dropping incidental details
are fine when the question still has the same answer. Do not flag style, length or difficulty.
An older source key can compress the passage or use different terminology. The current
Chinese question may be an approved rephrasing. Compare what is given and what the reader
must supply in both versions. Require support for the
specific answer from the displayed Chinese. If the sources conflict, identify exactly
what cannot be supported. Consider any prior risk note against the exact current wording.
Use 'faithful' only when it preserves the answer in context. Give a concise English reason
and quote verbatim a short relevant part of a labeled Chinese verse. If the evidence is
entirely absent, return 'repair' and empty strings for verse and quote.""" + "\n" + SOURCE_TARGET


def meaning_review(client, row, directory, source, flags=()):
    key = row["correct"]
    answer = row["choices"][LETTERS.index(key)]
    payload = dict(question=row["question"], answer=answer, clean_verses=row["verses"],
                   source_question=source["question"], source_answer=reference_answer(source, key),
                   source_verses=source["verses"],
                   prior_risks=[f["note"] for f in flags if f["kind"] == "risk"
                                and f["field"] == key and f["after"] == answer])

    def assess():
        for suffix in ("", "\nGive the exact Chinese verse label and verbatim Chinese quote."):
            check = model_review(client, JUDGE, MEANING + suffix, payload, AnswerMeaning)
            quote, verse = check["quote"], check["verse"]
            cited = bool(quote.strip() and verse in row["verses"] and quote in row["verses"][verse])
            if (not (check.get("target_changed") and check["verdict"] == "faithful")
                    and check["reason"].strip() and check["reader_meaning"].strip() and
                    (cited or (check["verdict"] == "repair" and not verse and not quote))):
                return check
        raise ValueError("Contextual meaning review has no valid evidence.")

    check = cached(directory, "answer_meaning", [JUDGE, MEANING, payload], assess)
    fixed = []
    if check["verdict"] == "repair":
        fixed.append(f"Fixed key {key} (meaning in context): {check['reason']} "
                     f"Reader meaning: {check['reader_meaning']}. Evidence: {check['verse']} {check['quote']}")
    return dict(checks={"answer_meaning": check}, fixed_findings=fixed, findings=[])


def reference_answer(source, key):
    return source["answer"] if "answer" in source else source["choices"][LETTERS.index(key)]


def fidelity_review(client, row, folder, question, answer):
    payload = dict(verses=row["verses"], reference_question=question, reference_answer=answer,
                   revised_question=row["question"], revised_key=row["choices"][LETTERS.index(row["correct"])])
    def assess():
        for hint in ("", "\nFor a pass copy a short contiguous quote exactly as printed in the Chinese."):
            verdict = model_review(client, JUDGE, FIDELITY + hint, payload, Fidelity)
            passes = all(verdict[k] for k in ("same_target", "clear_question", "faithful_answer"))
            cited = verdict["evidence"].strip() and any(verdict["evidence"] in v for v in row["verses"].values())
            if verdict["reason"].strip() and (not passes or cited):
                return verdict
        raise ValueError("Fidelity reviewer returned no usable reason or passage evidence.")
    verdict = cached(folder, "fidelity", [JUDGE, FIDELITY, payload, "validated evidence"], assess)
    if not all(verdict[k] for k in ("same_target", "clear_question", "faithful_answer")):
        return verdict, ["Fidelity: " + verdict["reason"]]
    return verdict, []


def check_repaired_menu(client, row, directory):
    options = dict(zip(LETTERS, row["choices"][:4], strict=True))
    payload = dict(question=row["question"], window=row["verses"], options=options)
    instructions = CHOICE_REVIEW_PROMPT + MENU_CUES
    menu = reviewed_blind_menu(client, directory, "blind_menu", instructions, payload, MenuWithCues, row["correct"])
    issues = option_cue_findings(menu, options, row["correct"])
    for c in menu["choices"]:
        key = row["correct"]
        if c["verdict"] != ("supported" if c["letter"] == key else "wrong") or c["circular"]:
            issues.append(f"Fixed key {key} (blind menu): {c['letter']} {c['reason']}")
    if not four_distinct(list(options.values())) or row["choices"][4] in options.values():
        issues.append(f"Fixed key {row['correct']} (blind menu): duplicate option.")
    return menu, issues


def reviewed_blind_menu(client, folder, name, instructions, payload, schema, key):
    def assess():
        for hint in ("", " Return A through D once each and copy every cue verbatim from its own choice.",
                     " For each cue use a short exact contiguous substring of the cited letter."):
            menu = model_review(client, JUDGE, instructions + hint, payload, schema)
            if sorted(v["letter"] for v in menu["choices"]) != list(LETTERS):
                continue
            try:
                option_cue_findings(menu, payload["options"], key)
            except ValueError:
                continue
            return menu
        raise ValueError("Blind review lacks four distinct letters or verbatim cue evidence.")
    return cached(folder, name, [JUDGE, instructions, payload, "validated cues v1"], assess)


class EditorialVerdict(BaseModel):
    resolved: bool
    fields: list[Literal["Q", "A", "B", "C", "D"]]
    reason: str


EDITORIAL_REVIEW = """Check whether the specific recorded editorial concern still applies to
this candidate. Read the Chinese window, question and all four choices. Use the source only
to identify the intended target. Test the actual shortcut, ambiguity or mismatch described.
A concern may mention a discarded draft or overstate a frequency clue. Evaluate only the
candidate shown. Count the actual list members before concluding which letters survive.
A proposed next step is a suggestion, never the required wording. A sound repair can use
another construction if it preserves the original unknown and resolves all material issues.
A different wording can fully resolve it. Do not give credit merely for an edit. Report the
reason and fields needing repair, or resolved=true with no fields. For a menu shortcut,
include the fields needed to rebuild the choices.""" + "\n" + SOURCE_TARGET


def check_editorial_concern(client, directory, row, source_question, source_key, concern, review):
    key = row["correct"]
    task = dict(verses=row["verses"], reference_question=source_question, reference_answer=source_key,
                revised_question=row["question"], revised_key=row["choices"][LETTERS.index(key)],
                concern=concern, correct=key, choices=dict(zip(LETTERS, row["choices"][:4], strict=True)))
    def assess():
        verdict = model_review(client, JUDGE, EDITORIAL_REVIEW, task, EditorialVerdict)
        if not verdict["reason"].strip() or verdict["resolved"] == bool(verdict["fields"]):
            raise ValueError("Editorial reviewer returned inconsistent resolution and fields.")
        return verdict
    verdict = cached(directory, "editorial_review", [JUDGE, EDITORIAL_REVIEW, task], assess)
    review["checks"]["editorial_review"] = verdict
    if not verdict["resolved"]:
        review["fixed_findings"].append("Editorial review: " + verdict["reason"])


def option_cue_findings(menu, options, key):
    findings = []
    for cue in menu["cues"]:
        if (not cue["reason"].strip() or not cue["excerpt"].strip()
                or cue["excerpt"] not in options[cue["letter"]]):
            raise ValueError("Option cue lacks evidence in the cited choice.")
        if cue["letter"] == key:
            findings.append(f"Fixed key {key} ({cue['kind']}): “{cue['excerpt']}”. {cue['reason']}")
    return findings


def key_shares_context(checks, key):
    return any(c["letter"] == key and c["kind"] == "shared_context"
               for c in checks.get("option_cues", []))


def fields_for_review(last, key):
    target = last["checks"].get("target", {}).get("verdict")
    allowed = set()
    fidelity = last["checks"].get("fidelity")
    if fidelity:
        if not fidelity["same_target"]:
            allowed.update("QABCD")
        if not fidelity["clear_question"]:
            allowed.add("Q")
        if not fidelity["faithful_answer"]:
            allowed.add(key)
    if last["checks"].get("answer_meaning", {}).get("target_changed"):
        allowed.update("QABCD")
    if last["checks"].get("stem_premise", {}).get("findings"):
        allowed.add("Q")
    for issue in last["checks"].get("chinese_usage", {}).get("findings", []):
        allowed.add(issue["field"])
    if any(last["checks"].get(k) for k in ("list_position_cue", "list_distractor_cue", "list_shortlist")):
        allowed.update(LETTERS)
    concern = last["checks"].get("editorial_review")
    if concern and not concern["resolved"]:
        allowed.update(concern["fields"])
    design = last["checks"].get("menu_design", {}).get("findings", [])
    if any(f["kind"] == "semantic_outlier" for f in design):
        allowed.update(set(LETTERS) - {key})
    if any(f["kind"] == "clause_structure_cue" for f in design):
        allowed.update(set(LETTERS) - {key})
    if any(f["kind"] == "asymmetric_frame" for f in design):
        allowed.update(LETTERS)
    if any(f["kind"] not in ("semantic_outlier", "asymmetric_frame", "clause_structure_cue") for f in design):
        # A set of unrelated alternatives may need a neutral outcome stem and a
        # grammatically matching key to contrast events from the same excerpt.
        allowed.update("QABCD")
    if any(f.startswith("Fixed key") for f in last["fixed_findings"]):
        allowed.add(key)
    if last["checks"].get("stem_issue", "none") != "none" or key_shares_context(last["checks"], key):
        allowed.add("Q")
    if any(f["field"] == "Q" for f in last["checks"].get("translation_review", {}).get("findings", [])):
        allowed.add("Q")
    if any(n["verdict"] == "unsupported" for n in last["checks"].get("stem_identity", {}).get("names", [])):
        allowed.add("Q")
    if target in ("compound_stem", "both", "ungrounded_event", "review_grounding"):
        allowed.update(("Q", key))
    if target in ("both", "off_target_choices") or last["findings"]:
        for issue in last["findings"]:
            label = re.match(r"^([A-D]) \(", issue)
            if label:
                allowed.add(label[1])
            else:
                allowed.update(set(LETTERS) - {key})
        if target == "both":
            allowed.update(set(LETTERS) - {key})
    return allowed


def repair_feedback(result, previous=None):
    """Route findings against the version the writer will actually edit."""
    row = result["after"]
    key = row["correct"]
    if previous is None:
        last = result["attempts"][-1]
        allowed = fields_for_review(last, key)
        findings = last["fixed_findings"] + last["findings"]
        current = dict(zip(LETTERS, row["choices"][:4]), Q=row["question"])
        for flag in result.get("source_flags", []):
            field = flag["field"]
            if field in ("Q", key) and flag["after"] == current[field] and flag["kind"] == "risk":
                findings.append(flag["note"])
                allowed.add(field)
    elif "review" in previous:
        allowed = fields_for_review(previous["review"], key)
        findings = previous["findings"]
        fidelity = previous["fidelity"]
        if not fidelity["same_target"]:
            # Restoring the unknown can also require replacing role or action choices with people.
            allowed.update("QABCD")
        if not fidelity["clear_question"]:
            allowed.add("Q")
        if not fidelity["faithful_answer"]:
            allowed.add(key)
    else:
        # No edit was applied. The original findings still describe the same wording.
        allowed = previous["editable_fields"]
        findings = previous["original_findings"] + previous["findings"]
    return [field for field in "QABCD" if field in allowed], findings


def writer_wording_findings(checks, findings):
    """A blind wording reviewer can diagnose an indirect stem without knowing its source target."""
    evidence = {}
    for issue in checks.get("chinese_usage", {}).get("findings", []):
        if issue["field"] == "Q" and issue["kind"] in {"unclear_reference", "indirect_wording"}:
            label = f"Fixed question ({issue['kind']}): “{issue['excerpt']}”."
            evidence[f"{label} {issue['reason']}"] = f"{label} Passage evidence ({issue['verse']}): “{issue['quote']}”."
    return [evidence.get(finding, finding) for finding in findings]


def apply_edits(row, fields, proposal):
    changes = {e["field"]: e["text"].strip() for e in proposal["edits"]}
    if len(changes) != len(proposal["edits"]) or changes.keys() - set(fields):
        raise ValueError("Writer returned a duplicate or out-of-scope edit.")
    if any(not re.search(r"[\u3400-\u9fff]", wording) for wording in changes.values()):
        raise ValueError("Writer returned empty or non-Chinese wording.")
    choices = [changes.get(l, text) for l, text in zip("ABCDE", row["choices"], strict=True)]
    candidate = dict(row, question=changes.get("Q", row["question"]), choices=choices)
    if candidate == row:
        raise ValueError("Writer proposed no wording change.")
    return candidate


def remove_shared_stem_prefix(row, candidate, cue):
    """Keep parallel options when the key drops a confirmed, identical stem echo."""
    prefix = cue.get("redundant_stem_excerpt", "")
    key_index = LETTERS.index(row["correct"])
    options = row["choices"][:4]
    if (not prefix or not all(s.startswith(prefix) for s in options)
            or candidate["choices"][key_index].startswith(prefix)
            or candidate["question"] != row["question"]):
        return candidate, {}
    choices = list(candidate["choices"])
    edits = {}
    for index, option in enumerate(options):
        if index == key_index:
            continue
        if choices[index] != option:  # Keep independently proposed distractor edits.
            continue
        rest = option[len(prefix):].lstrip(" ，,：:")
        for opening, closing in (("‘", "’"), ("“", "”"), ("「", "」"), ("『", "』")):
            if rest.startswith(opening) and rest.endswith(closing) and closing not in rest[1:-1]:
                rest = rest[1:-1].strip()
                break
        if not mcq_complexity.HAN.search(rest):
            return candidate, {}
        choices[index] = rest
        edits[LETTERS[index]] = rest
    return dict(candidate, choices=choices), edits


def dropped_shared_quote_frame(row, candidate):
    """Check whether a key edit leaves only the distractors with the shared speech introduction."""
    options = row["choices"][:4]
    match = re.match(r"^([^：:‘“「『]+[：:])\s*(?=[‘“「『])", options[0])
    if not match or row["question"] != candidate["question"]:
        return False
    prefix = match[1]
    key = LETTERS.index(row["correct"])
    return (all(text.startswith(prefix) for text in options)
            and not candidate["choices"][key].startswith(prefix))


def remove_shared_stem_suffix(row, candidate, cue):
    """Drop a reviewer-confirmed trailing clause when all four choices used it."""
    tail = cue.get("redundant_stem_excerpt", "").strip(" ，,。")
    options = row["choices"][:4]
    key = LETTERS.index(row["correct"])
    if not tail or candidate["choices"][key].rstrip("。").endswith(tail):
        return candidate, {}
    pattern = re.compile(r"[，,]\s*" + re.escape(tail) + r"[。.]?$")
    if not all(pattern.search(o) for o in options):
        return candidate, {}
    choices = list(candidate["choices"])
    edits = {}
    for index, option in enumerate(options):
        if index == key or choices[index] != option:
            continue
        shortened = pattern.sub("。" if option.endswith("。") else "", option)
        if not mcq_complexity.HAN.search(shortened):
            return candidate, {}
        choices[index] = shortened
        edits[LETTERS[index]] = shortened
    return dict(candidate, choices=choices), edits


class SuffixVerdict(BaseModel):
    redundant: bool
    reason: str


SUFFIX = """The key has already been revised. Compare the supplied current and shorter
choices under the same revised stem. The only proposed changes remove a shared ending
from the indicated distractors. Does that ending repeat a contrast already established,
so that each indicated option keeps its meaning, including polarity and attribution?
Consider only the stated changes. Keep the clause if it supplies independent information."""


def review_dropped_suffix(client, row, candidate, folder):
    options = row["choices"][:4]
    tail = re.search(r"[，,]([^，,。！？]+)[。.]?$", options[0])
    if not tail:
        return candidate, {}
    phrase = tail[1]
    shortened, edits = remove_shared_stem_suffix(row, candidate, {"redundant_stem_excerpt": phrase})
    if not edits:
        return candidate, {}
    task = dict(question=candidate["question"], before=candidate["choices"][:4],
                after=shortened["choices"][:4], changed_letters=list(edits),
                verses=row["verses"], clause=phrase)
    check = cached(folder, "shared_suffix", [JUDGE, SUFFIX, task],
                   lambda: model_review(client, JUDGE, SUFFIX, task, SuffixVerdict))
    return (shortened, edits) if check["redundant"] and check["reason"].strip() else (candidate, {})


def repair_once(result, reference, client, folder, *, stage="repair", meaning_source=None):
    if stage not in EXTENDED_REPAIR_STAGES:
        raise ValueError(f"Unknown repair stage: {stage}")
    if result["status"] != "held" or stage in result:
        return result
    number = EXTENDED_REPAIR_STAGES.index(stage)
    previous = result[EXTENDED_REPAIR_STAGES[number - 1]] if number else None
    row = result["after"]
    key = row["correct"]
    fields, findings = repair_feedback(result, previous)
    last_review = next((result[s]["review"] for s in reversed(EXTENDED_REPAIR_STAGES[:number])
                        if "review" in result[s]), result["attempts"][-1])
    checks = last_review["checks"]
    clause_cue_seen = any(
        issue["kind"] == "clause_structure_cue"
        for review in [*result["attempts"], *(result[s].get("review", {}) for s in EXTENDED_REPAIR_STAGES[:number])]
        for issue in review.get("checks", {}).get("menu_design", {}).get("findings", [])
    )
    if clause_cue_seen and set(fields).intersection(set(LETTERS) - {key}):
        # If the first structural peer was rejected as padding, the writer may repair another distractor instead.
        fields = [field for field in "QABCD" if field in fields or (field in LETTERS and field != key)]
    shared_context = key_shares_context(checks, key)
    if result.get("key_only"):
        unclear_stem = (
            bool(checks.get("stem_premise", {}).get("findings"))
            or any(f["field"] == "Q" for f in checks.get("chinese_usage", {}).get("findings", []))
            or bool(previous and previous.get("fidelity", {}).get("clear_question") is False)
        )
        restore_target = result.get("meaning_only") and (
            checks.get("answer_meaning", {}).get("target_changed")
            or previous and previous.get("fidelity", {}).get("same_target") is False)
        if not restore_target:
            fields = [field for field in fields if field == key or (field == "Q" and (
                unclear_stem or result.get("meaning_only") and shared_context))]
    if result.get("identity_only"):
        fields = [field for field in fields if field == "Q"]
    if result.get("pinned_distractors"):
        fields = [field for field in fields if field not in result["pinned_distractors"]]
    if (row["id"] != reference["id"] or key != reference["correct"] or row["verses"] != reference["verses"]
            or len(row["choices"]) != 5 or row["choices"][4] != reference["choices"][4]):
        raise ValueError(f"Reference or clean passage mismatch for {row['id']}")
    inputs = dict(question=row["question"],
                  options=dict(zip("ABCD", row["choices"][:4])),
                  correct_letter=key,
                  verses=row["verses"],
                  reference_question=reference["question"],
                  reference_answer=reference["choices"][LETTERS.index(key)])
    if meaning_source is not None:
        inputs.update(reference_question=meaning_source["question"],
                      reference_answer=reference_answer(meaning_source, key),
                      reference_verses=meaning_source["verses"])
    record = dict(status="held", editable_fields=fields, before=row, original_findings=findings, findings=[])
    output = dict(result, initial_status="held")
    output[stage] = record
    if not fields:
        record["findings"] = ["No supported edit route for the recorded review finding."]
        return output
    task = dict(inputs, editable_fields=fields, findings=writer_wording_findings(checks, findings))
    if clause_cue_seen:
        task["clause_structure_guidance"] = CLAUSE_STRUCTURE_GUIDE
        if previous:
            task["clause_structure_guidance"] += (
                " Keep a structural peer for the key while fixing the latest findings. If that peer used padding, "
                "replace its pair of actions with a substantive pair, or give another distractor that structure. "
                "Do not return to a previously flagged menu."
            )
    if previous:
        task["previous_attempt"] = previous.get("proposal", {}).get("reason", "")
    if result.get("editorial_concern"):
        task["editorial_concern"] = result["editorial_concern"]
        if result.get("repair_direction"):
            task["suggested_direction"] = result["repair_direction"]
    if "Q" in fields:
        task["stem_guidance"] = DIRECT_STEM
    if checks.get("menu_design", {}).get("findings"):
        task["menu_guidance"] = (
            "For a name-matching finding, when you cannot find three plausible people in the window, "
            "first consider different people and groups actually mentioned in the scene, "
            "including those in other roles. The reader must still identify the person. "
            "If the menu would give away the answer, hold it. For unrelated alternatives, "
            "use plausible errors about who acted, what the objects did, and what was attempted or "
            "actually happened. Avoid choices that also correctly describe the key. For a wordy menu "
            "shorten all four options that can be shortened and name shared parties once in the stem. "
            "For speech such as a wish, report its content in its original mood."
        )
        if any(f["kind"] == "menu_wordiness" for f in checks["menu_design"]["findings"]):
            task["compression_guidance"] = (
                "Read the proposed stem and each option aloud together. Use the short referring form "
                "once both parties are clearly identified. Express a one-sided outcome with 'only' "
                "where accurate instead of adding a clause about the other party escaping harm. "
                "For a reciprocal outcome, use plain wording for both directions and preserve the "
                "text's agency. Ask directly about the event or wish without adding a reporting "
                "frame about a speaker. Keep all distinctions needed to select the answer."
            )
        if any(f["kind"] == "unrelated_distractors" for f in checks["menu_design"]["findings"]):
            task["distractor_guidance"] = (
                "A familiar noun attached to a fanciful new mechanism is a weak distractor. "
                "Use plausible confusions about relationships and outcomes actually described. "
                "When the key gives two outcomes and the passage reports both, try contrasting "
                "both, only the first, only the second, and neither before inventing other events. "
                "Make each incorrect combination explicitly false, avoiding a merely incomplete "
                "true answer. If using these combinations, ask neutrally about the outcome "
                "for the recipients in that episode. A question that presupposes a miracle or "
                "asks which action occurred does not fit a 'neither' answer. In that case "
                "rewrite the stem and align all four choices as parallel descriptions of what "
                "happened. Keep the existing key wording when it already fits; otherwise "
                "preserve its two outcomes and its letter."
            )
    if result.get("identity_only"):
        task["repair_guidance"] = ("Change only the participant identification. Where a grounded title "
                                   "fits, substitute that title verbatim and keep the rest of the stem.")
    if shared_context and "Q" in fields:
        task.update(earlier_key=reference["choices"][LETTERS.index(key)],
                    repair_guidance="Name the shared actor or circumstance once in the question. "
                    "Prefer the earlier short key verbatim if the revised question makes it clear. "
                    "Keep the answer contrast and avoid introducing optional wording from the passage.")
    proposal = cached(folder, "proposal", [MODEL, REPAIR, task],
                      lambda: model_review(client, MODEL, REPAIR, task, Proposal))
    record["proposal"] = proposal
    if not proposal["repairable"]:
        record["findings"] = [proposal["reason"]]
        return output
    try:
        candidate = apply_edits(row, fields, proposal)
    except ValueError as exc:
        record["findings"] = [str(exc)]
        return output
    cue = checks.get("key_cues", {})
    if not cue.get("redundant_stem_excerpt") and dropped_shared_quote_frame(row, candidate):
        cue, _ = key_cue_review(client, row, folder / "before_shared_prefix")
    candidate, shared = remove_shared_stem_prefix(row, candidate, cue)
    if shared:
        record["shared_prefix"] = cue["redundant_stem_excerpt"]
        record["shared_prefix_edits"] = shared
    candidate, shared_tail = remove_shared_stem_suffix(row, candidate, cue)
    if not shared_tail:
        candidate, shared_tail = review_dropped_suffix(client, row, candidate, folder)
    if shared_tail:
        record["shared_suffix_edits"] = shared_tail
    if any(candidate["choices"][LETTERS.index(l)] != row["choices"][LETTERS.index(l)]
           for l in result.get("pinned_distractors", [])):
        record["findings"] = ["The shared wording edit changed a pinned distractor. Keep it verbatim."]
        return output
    output["after"] = candidate
    if result.get("meaning_only"):
        review = meaning_review(client, candidate, folder, meaning_source, result.get("source_flags", []))
        wording = window_wording_review(client, candidate, folder)
        review["checks"].update(wording["checks"])
        review["fixed_findings"].extend(wording["fixed_findings"])
        review["findings"].extend(wording["findings"])
        design = menu_design_review(client, candidate, folder)
        review["checks"].update(design["checks"])
        review["fixed_findings"].extend(design["fixed_findings"])
        review["findings"].extend(design["findings"])
        if candidate["question"] != reference["question"]:
            identity = stem_identity_review(client, candidate, folder)
            review["checks"].update(identity["checks"])
            review["fixed_findings"].extend(identity["fixed_findings"])
        menu, issues = check_repaired_menu(client, candidate, folder)
        review["checks"]["blind"] = menu["choices"]
        review["checks"]["option_cues"] = menu["cues"]
        review["fixed_findings"].extend(issues)
    else:
        review = review_choices(client, candidate, folder, full_review=True)
        if meaning_source is not None:
            meaning = meaning_review(client, candidate, folder, meaning_source, result.get("source_flags", []))
            review["checks"].update(meaning["checks"])
            review["fixed_findings"].extend(meaning["fixed_findings"])
    fidelity, fidelity_issues = fidelity_review(client, candidate, folder, inputs["reference_question"],
                                               inputs["reference_answer"])
    if result.get("editorial_concern"):
        check_editorial_concern(client, folder, candidate, inputs["reference_question"], inputs["reference_answer"],
                                result["editorial_concern"], review)
    problems = review["fixed_findings"] + review["findings"] + fidelity_issues
    status = "held" if problems else "passed"
    record.update(status=status, review=review, fidelity=fidelity, findings=problems)
    output["status"] = status
    return output


def run_item(entry, client, folder):
    row = entry["row"]
    key = row["correct"]
    opts = dict(zip(LETTERS, row["choices"][:4], strict=True))
    pinned = entry.get("pinned_distractors", [])
    if not isinstance(pinned, list) or any(letter not in set(LETTERS) - {key} for letter in pinned):
        raise ValueError("Pinned distractors must be letters of existing wrong choices.")
    guide = GUIDE
    if pinned:
        fixed_text = {letter: opts[letter] for letter in pinned}
        guide += " Keep these author-selected distractors verbatim: " + json.dumps(fixed_text, ensure_ascii=False)
    window = "\n".join(f"{number}  {verse}" for number, verse in row["verses"].items())
    rounds = []
    feedback = ""
    strict = SimpleNamespace(chat=SimpleNamespace(completions=StrictCompletions(client)))
    for number in range(1, MAX_DRAFTS + 1):
        draft = folder / f"draft{number}"
        task = dict(opts, correct=key)
        proposed = cached(
            draft, "writer", [MODEL, row, task, feedback, guide],
            lambda: writer.rewrite_distractors(strict,
                                               MODEL,
                                               task,
                                               row["question"],
                                               window,
                                               effort="medium",
                                               feedback=(feedback + "\n" + guide).strip(),
                                               language="Simplified Chinese"))
        if proposed["correct"] != key or proposed[key] != row["choices"][LETTERS.index(key)]:
            raise ValueError("Distractor draft changed the fixed key.")
        opts = {l: (row["choices"][LETTERS.index(l)] if l in pinned else proposed[l]) for l in LETTERS}
        after = dict(row, choices=[*opts.values(), row["choices"][4]])
        review = review_choices(client, after, draft)
        meaning = meaning_review(client, after, folder, entry["meaning_source"], entry.get("source_flags", []))
        review["checks"].update(meaning["checks"])
        review["fixed_findings"].extend(meaning["fixed_findings"])
        rounds.append(dict(number=number, options=opts, **review))
        status = "held" if review["fixed_findings"] or review["findings"] else "passed"
        if status == "passed" or (review["fixed_findings"] and not entry.get("distractors_only")):
            break
        if entry.get("distractors_only") and meaning["fixed_findings"]:
            break  # Changing the wrong choices cannot repair an unsupported fixed key.
        feedback = "Previous alternatives and findings:\n" + json.dumps(
            opts, ensure_ascii=False) + "\n" + "\n".join(review["findings"] + review["fixed_findings"])
    return dict(index=entry["index"],
                id=row["id"],
                reference=row["reference"],
                before=row,
                after=after,
                status=status,
                pinned_distractors=pinned,
                source_flags=entry.get("source_flags", []),
                attempts=rounds)


def editorial_repair_inputs(directory, bank):
    """Start from the exact wording reviewed, including earlier unpublished drafts."""
    reviewed = read(directory / "results.json")
    by_id = {r["id"]: r for r in reviewed}
    decisions = read(directory / "dispositions.json")["items"]
    if (len(by_id) != len(reviewed) or len(decisions) != len(reviewed)
            or {r["id"] for r in decisions} != set(by_id)):
        raise ValueError("Review and dispositions do not cover the same unique items.")
    entries = []
    for decision in decisions:
        if decision["category"] == "No material issue identified":
            continue
        if decision["category"] not in {"Flagged by the pipeline", "Additional editorial review"}:
            raise ValueError(f"Unknown editorial decision: {decision['category']}")
        item = by_id[decision["id"]]
        row = item["row"]
        if (item["index"] != decision["index"] or row["id"] != item["id"]
                or item["local"] != bank.get(item["id"]) or not decision["reason"].strip()):
            raise ValueError(f"Stale bank wording or incomplete decision for {item['id']}")
        checks = dict(item["checks"])
        concern = decision["reason"]
        checks["editorial_review"] = dict(resolved=False, fields=list("QABCD"), reason=concern)
        review = dict(checks=checks, fixed_findings=[*item["issues"], concern], findings=[])
        entries.append(dict(index=item["index"], id=row["id"], reference=row["reference"],
                            status="held", before=row, after=row, attempts=[review],
                            editorial_concern=concern, wording_source=item["source"]))
    return entries


def readiness_repair_inputs(decisions, bank, release):
    """Use the published baseline even when the assessor also examined an unsuccessful draft."""
    index = {cid: i for i, cid in enumerate(bank, 1)}
    entries = []
    for decision in decisions:
        if decision["disposition"] != "Further review":
            continue
        cid = decision["id"]
        row = bank.get(cid)
        if (row is None or decision["local_question"] != row["question"]
                or decision["local_choices"] != row["choices"] or decision["key"] != row["correct"]
                or decision["clean_verses"] != row["verses"]):
            raise ValueError(f"Stale held wording or verse window for {cid}")
        finding = decision["finding"]
        concern = finding["reason"].strip()
        if not concern:
            raise ValueError(f"Missing editorial concern for {cid}")
        shortlist = modal_shortlist(row["choices"][:4], row["correct"])
        if shortlist:
            concern += (" On the published menu, counting the list positions narrows the choices to "
                        + " and ".join(shortlist) + ". Evaluate this partial clue.")
        review = dict(checks={"editorial_review": dict(resolved=False, fields=list("QABCD"), reason=concern)},
                      fixed_findings=[concern], findings=[])
        entries.append(dict(index=index[cid], id=cid, reference=row["reference"], before=row, after=row,
                            status="held", attempts=[review], editorial_concern=concern,
                            repair_direction=finding["next_step"], wording_source="published", set=decision["set"]))
    if Counter(e["id"] for e in entries) != Counter(release["held_for_review"]):
        raise ValueError("Readiness decisions must cover the released held items exactly once.")
    return entries


def replacement_inputs(approvals, prior_results, bank):
    prior = {item["id"]: item for item in prior_results}
    if len(prior) != len(prior_results):
        raise ValueError("Prior results contain duplicate IDs.")
    entries, new_ids = [], set()
    for spec in approvals:
        old_id, new_id = spec["replaces"], spec["replacement_id"]
        original = prior.get(old_id)
        if not original or original["status"] != "held" or digest(original["after"]) != spec["held_sha256"]:
            raise ValueError(f"Replacement requires the matching held wording for {old_id}")
        if not new_id.strip() or new_id in bank or new_id in new_ids:
            raise ValueError(f"Replacement needs a distinct new ID: {new_id}")
        old = original["after"]
        if old["id"] != old_id or old["correct"] != spec["correct"]:
            raise ValueError(f"Unexpected source identity or key position for {old_id}")
        if (len(spec["choices"]) != 4 or not all(isinstance(v, str) and v.strip() for v in spec["choices"])
                or not spec["question"].strip() or not spec["target"]["question"].strip()
                or not spec["target"]["answer"].strip() or not spec["concern"].strip()):
            raise ValueError(f"Missing replacement question, target, rationale or choices for {old_id}")
        if not spec["quote"].strip() or spec["quote"] not in old["verses"].get(spec["verse"], ""):
            raise ValueError(f"Replacement evidence must come from the displayed Chinese for {old_id}")
        # Keep the source ID until the normal bank, roster, key and window validation completes.
        row = dict(old, question=spec["question"], choices=[*spec["choices"], old["choices"][4]])
        entries.append(dict(index=original["index"], row=row, approval=spec))
        new_ids.add(new_id)
    return entries


class TargetSupport(BaseModel):
    verdict: Literal["supported", "unsupported"]
    passage_claim: str
    target_claim: str
    missing_link: str
    verse: str
    quote: str


TARGET_SUPPORT = """Determine whether the proposed comprehension target can be answered
from the displayed Chinese alone. State the claim the text makes and the claim required
by the proposed question and answer. Check the cited phrase in the full window in case
another verse supplies the link. Approval of the target is not evidence for its truth.
With supported, leave missing_link empty. With unsupported, identify the extra premise
needed. Cite a short contiguous Chinese phrase from one labeled verse, including the
closest relevant evidence when the required link is absent.""" + " " + CLAIM_SCOPE


def target_support(client, row, spec, folder):
    task = dict(target=spec["target"], clean_verses=row["verses"], cited_verse=spec["verse"], cited_phrase=spec["quote"])

    def assess():
        for hint in ("", " Provide a verbatim Chinese quote and a missing link only for an unsupported claim."):
            check = model_review(client, JUDGE, TARGET_SUPPORT + hint, task, TargetSupport)
            if (check["passage_claim"].strip() and check["target_claim"].strip()
                    and check["quote"].strip() and check["quote"] in row["verses"].get(check["verse"], "")
                    and (check["verdict"] == "unsupported") == bool(check["missing_link"].strip())):
                return check
        raise ValueError("Replacement target review lacks a consistent verdict or verbatim passage evidence.")

    return cached(folder, "target_support", [JUDGE, TARGET_SUPPORT, task], assess)


def review_replacement(entry, english, client, folder):
    spec = entry["approval"]
    row = dict(entry["row"], id=spec["replacement_id"])
    target = dict(spec["target"], verses=english["verses"])
    support = target_support(client, row, spec, folder)
    result = dict(index=entry["index"], id=row["id"], reference=row["reference"], replaces=spec["replaces"],
                  approval=spec, old_target=dict(question=english["question"], answer=reference_answer(english, row["correct"])),
                  before=row, after=row, editorial_concern=spec["concern"], target_support=support)
    if support["verdict"] == "unsupported":
        reason = "Unsupported replacement target: " + support["missing_link"]
        review = dict(checks={"target_support": support}, fixed_findings=[reason], findings=[])
        return dict(result, attempts=[review], status="rejected", rejection_reasons=[reason])
    review = review_choices(client, row, folder, full_review=True)
    meaning = meaning_review(client, row, folder, target)
    review["checks"].update(meaning["checks"])
    review["fixed_findings"].extend(meaning["fixed_findings"])
    fidelity, issues = fidelity_review(client, row, folder, target["question"], target["answer"])
    review["checks"]["fidelity"] = fidelity
    review["fixed_findings"].extend(issues)
    check_editorial_concern(client, folder, row, target["question"], target["answer"], spec["concern"], review)
    result.update(attempts=[review], status="held" if review["fixed_findings"] or review["findings"] else "passed")
    for stage in REPAIR_STAGES:
        if result["status"] == "passed":
            break
        result = repair_once(result, row, client, folder / stage, stage=stage, meaning_source=target)
    if result["status"] == "held":
        result["status"] = "rejected"
        result["rejection_reasons"] = result[REPAIR_STAGES[-1]]["findings"]
    return result


def retained_manual_fields(result, initial, fields):
    """Track supplied fields across accepted edits, including rewrites back to an earlier string."""
    rows = [initial]
    rows.extend(result[stage]["before"] for stage in EXTENDED_REPAIR_STAGES if stage in result)
    rows.append(result["after"])
    values = [dict(zip("QABCD", [row["question"], *row["choices"][:4]], strict=True)) for row in rows]
    if not isinstance(fields, list) or any(f not in values[0] for f in fields):
        raise ValueError("Manually written fields must name question Q or options A–D.")
    return [f for f in "QABCD" if f in fields and all(v[f] == values[0][f] for v in values)]


def replacement_selection(results):
    if any(item["status"] not in {"passed", "rejected"} for item in results):
        raise ValueError("Replacement selection requires completed reviews.")
    return dict(
        excluded_originals=[item["replaces"] for item in results],
        candidates=[dict(row=item["after"], replaces=item["replaces"], target=item["approval"]["target"],
                         manually_written_fields=item.get("manually_written_fields", []))
                    for item in results if item["status"] == "passed"],
        rejected=[dict(id=item["id"], replaces=item["replaces"], reasons=item["rejection_reasons"])
                  for item in results if item["status"] == "rejected"])


class FinalMCQReview(BaseModel):
    verdict: Literal["hold", "unsupported_target", "unfair_menu"]
    target_support: Literal["supported", "unsupported", "uncertain"]
    repair_possible: Literal["yes", "no", "uncertain"]
    verse: str
    quote: str
    missing_link: str
    menu_shortcut: str
    alternatives_considered: str
    reason: str


FINAL_MCQ_REVIEW = """Independently decide whether this PUBLISHED Chinese multiple-choice item
should be retired after repairs were exhausted. The source question and answer identify the
original unknown. Only the displayed Chinese verses are evidence. The pilot scores the fact
supported in this window; unambiguous inferences are legitimate. Prior repair failures are
not evidence. Quote one exact contiguous span from a labeled Chinese verse and explain your
decision in English. Use one of these outcomes:
- unsupported_target: the precise fact asked for is not established in the window, even
after considering ordinary phrasing, inference and a minimal stem repair. Identify the
missing link. For a why question distinguish the reason for acting from the reason for
the duration of the action. Consider whether E is defensible. If the passage does establish
the original unknown and the current key is simply inaccurate, leave it held for repair.
- unfair_menu: the original fact is supported but a reader can identify the published key by
matching names or another form cue without understanding it AND no fair four-choice menu
can preserve this target in this window. Describe the shortcut and actually try constructing
three parallel, plausible wrong choices using individuals, roles, groups or descriptions.
Options need not repeat passage words. Consider synonyms, indirect clues, and whether an
alternative refers to the same person as the key. Apply the repair pipeline's source
fidelity rule to the proposed menu itself: when the original question requires identifying
a named person, the key must still supply that person's identity at the original specificity.
An anonymous role, kinship or quote alone does not identify that person by name. Including
the name only in the key while giving the other choices anonymous roles can expose it again.
If arguing a fair menu exists, give the complete proposed Chinese A–D choices so an editor
can assess the claim. Do not treat a proposed replacement target as a repair.
Explain precisely why the menu cannot work, or choose hold if a faithful repair looks possible.
- hold: neither reason is confirmed, a faithful repair is possible, or there is uncertainty.
Wording difficulty, an unattractive distractor, a disputed nuance, or exhaustion alone cannot
retire an item. Give empty strings for inapplicable evidence fields.""" + "\n" + SOURCE_TARGET


def final_mcq_review(client, published, source, result, stages, folder):
    if (result["status"] != "held" or not stages or any(
            result.get(s, {}).get("status") != "held" or not result[s].get("findings") for s in stages)):
        raise ValueError("Final review requires a held item and completed failed repairs.")
    task = dict(question=published["question"], choices=dict(zip("ABCDE", published["choices"], strict=True)),
                correct=published["correct"], verses=published["verses"], source_question=source["question"],
                source_answer=reference_answer(source, published["correct"]))
    metadata = dict(id=published["id"], published_signature=published_signature(published), model=JUDGE,
                    version=digest(FINAL_MCQ_REVIEW), repair_stages=list(stages))
    def assess():
        for hint in ("", " Copy the evidence exactly. Check verdict, repair feasibility and evidence fields for consistency."):
            answer = model_review(client, JUDGE, FINAL_MCQ_REVIEW + hint, task, FinalMCQReview)
            decision = dict(answer, **metadata)
            try:
                validate_final_review(published, decision)
                return decision
            except ValueError:
                continue
        raise ValueError(f"Final reviewer returned invalid evidence for {published['id']}")
    return cached(folder, "final_mcq_review", [metadata, task], assess)


def apply_final_retirements(bank_path, results, release):
    """Update only the local eligibility roster, once the entire batch has finished."""
    reviews = {r["id"]: r["final_mcq_review"] for r in results if "final_mcq_review" in r}
    if not reviews:
        return
    directory = os.open(bank_path, os.O_RDONLY)
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        if (read(bank_path / "choice_release.json") != release
                or sha256((bank_path / "zh.json").read_bytes()).hexdigest() != release["zh_sha256"]):
            raise ValueError("The published release changed during final review.")
        rows = {r["id"]: r for r in read(bank_path / "zh.json")}
        roster_path = bank_path / "pilot_review.json"
        roster = read(roster_path)
        by_id = {r["id"]: r for r in roster}
        if len(roster) != len(by_id) or set(rows) != set(by_id):
            raise ValueError("Eligibility roster differs from the question bank.")
        retired = []
        for cid, decision in reviews.items():
            validate_final_review(rows[cid], decision)
            entry = by_id[cid]
            if decision["verdict"] == "hold" or entry.get("final_mcq_review") == decision:
                continue
            if entry["status"] != "eligible":
                raise ValueError(f"Eligibility changed during final review for {cid}")
            entry.update(status="withheld", retired_from_pilot=True, reason=decision["reason"], final_mcq_review=decision)
            retired.append(cid)
        if retired:
            mode = stat.S_IMODE(roster_path.stat().st_mode)
            write(roster_path, roster)
            roster_path.chmod(mode)
            print("Retired from the local roster:", ", ".join(retired), flush=True)
    finally:
        os.close(directory)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--inputs",
                        type=Path,
                        help="Normal batch: each entry has index, row and optional source_flags.")
    source.add_argument("--repair-held-from",
                        type=Path,
                        help="Continue held items from their last completed repair, up to two total.")
    source.add_argument("--final-review-from", type=Path, metavar="RUN_DIR",
                        help="Run the final review on exhausted published questions from a completed repair run.")
    ap.add_argument("--preview-retirements", action="store_true",
                    help="Record final decisions without applying confirmed retirements to the local roster.")
    source.add_argument("--repair-reviewed-from", type=Path, metavar="REVIEW_DIR",
                        help="Repair the flagged items in a completed editorial or published readiness review.")
    source.add_argument("--review-replacements", type=Path, metavar="APPROVALS",
                        help="Test approved alternative MCQs against their new targets and export passing candidates.")
    ap.add_argument("--held-results", type=Path, help="Completed results containing the held originals being replaced.")
    source.add_argument("--audit-published-keys", action="store_true",
                        help="Check every eligible published key for stem repetition and excess length.")
    source.add_argument("--audit-translatability", action="store_true",
                        help="Check eligible published questions and choices for avoidable translation difficulty.")
    source.add_argument("--audit-stem-identities", action="store_true",
                        help="Check names in each eligible stem against its clean excerpt and review stem-only repairs.")
    source.add_argument("--audit-menu-design", action="store_true",
                        help="Check whole-menu wordiness, unrelated distractors and name-matching shortcuts.")
    source.add_argument("--audit-window-wording", action="store_true",
                        help="Check stem premises, Chinese grammar, titles and menu cues against each published window.")
    source.add_argument("--audit-draft-wording", type=Path, metavar="INPUTS",
                        help="Apply the same window and source checks to draft entries with index and row.")
    ap.add_argument("--inspect-only", action="store_true", help="Record findings from a published-bank audit without repairs.")
    source.add_argument("--audit-answer-meaning", action="store_true",
                        help="Check each published key against its source and clean excerpt, then repair meaning changes.")
    ap.add_argument("--source-flags-from", type=Path, help="Earlier item results with optional source risk notes.")
    ap.add_argument("--item-id", action="append", help="Limit a published-bank audit to this source ID (repeatable).")
    ap.add_argument("--output",
                    required=True,
                    type=Path,
                    help="Separate directory for checkpoints and reviewed candidates.")
    ap.add_argument("--bank", type=Path, default=BANK)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--repair-rounds", type=int, choices=range(1, len(EXTENDED_REPAIR_STAGES) + 1),
                    help="Maximum repair attempts per item. Default two, or four for readiness holds.")
    args = ap.parse_args(argv)
    if bool(args.review_replacements) != bool(args.held_results):
        ap.error("--review-replacements and --held-results must be used together.")
    if args.review_replacements and args.source_flags_from:
        ap.error("Source risk notes belong to the old targets. Record replacement concerns in the approval file.")
    if args.final_review_from and (args.repair_rounds or args.source_flags_from):
        ap.error("Final review uses the completed run's repair limit and published wording.")
    wording_audit = args.audit_window_wording or args.audit_draft_wording is not None
    focused = (args.audit_published_keys or args.audit_translatability or args.audit_answer_meaning
               or args.audit_stem_identities or args.audit_menu_design or wording_audit)
    if args.inspect_only and not focused:
        ap.error("--inspect-only requires a published-bank audit.")
    if args.item_id and not focused:
        ap.error("--item-id requires a published-bank audit.")
    path = (args.inputs or args.repair_held_from or args.audit_draft_wording or args.review_replacements or
            (args.final_review_from / "results.json" if args.final_review_from else None) or
            (args.repair_reviewed_from / "dispositions.json" if args.repair_reviewed_from else args.bank / "zh.json"))
    decisions = read(path)["items"] if args.repair_reviewed_from else []
    readiness = bool(decisions and "disposition" in decisions[0])
    stages = EXTENDED_REPAIR_STAGES[:args.repair_rounds or (4 if readiness else len(REPAIR_STAGES))]
    if args.final_review_from:
        prior_manifest = read(args.final_review_from / "manifest.json")
        limit = prior_manifest["max_repair_rounds"]
        if (not 1 <= limit <= len(EXTENDED_REPAIR_STAGES) or prior_manifest["inspect_only"]
                or prior_manifest["mode"] == "approved_replacements" or read(args.final_review_from / "errors.json")):
            ap.error("Final review requires a completed repair run on original questions.")
        stages = EXTENDED_REPAIR_STAGES[:limit]
    if args.review_replacements and args.repair_rounds:
        ap.error("--repair-rounds applies to existing questions.")
    out = args.output
    if path.resolve() == (out / "results.json").resolve() or out.resolve() == path.parent.resolve():
        ap.error("Choose a separate output directory to preserve the input run.")
    if args.held_results and out.resolve() == args.held_results.resolve().parent:
        ap.error("Choose a separate output directory to preserve the held review.")
    replay = bool(args.repair_held_from or args.repair_reviewed_from or args.final_review_from)
    bank = {r["id"]: r for r in read(args.bank / "zh.json")}
    original_path = args.bank / "english.json"
    if not original_path.exists() and (args.audit_answer_meaning or wording_audit or args.review_replacements or readiness or args.bank.resolve() == BANK.resolve()):
        ap.error("Missing independent English question and answer bank.")
    originals = {r["id"]: r for r in read(original_path)} if original_path.exists() else bank
    release_path = args.bank / "choice_release.json"
    published = release_path.exists() and original_path.exists()
    if args.final_review_from and not published:
        ap.error("Final review requires a published bank and source questions.")
    if published:
        release = read(release_path)
        if sha256((args.bank / "zh.json").read_bytes()).hexdigest() != release["zh_sha256"]:
            ap.error("Published bank differs from the release.")
        if release.get("english_sha256") and sha256(original_path.read_bytes()).hexdigest() != release["english_sha256"]:
            ap.error("Source questions differ from the release.")
    roster_entries = {r["id"]: r for r in read(args.bank / "pilot_review.json")}
    roster = {cid: r["status"] for cid, r in roster_entries.items()}
    # Recreate this run's original selection when it already applied its own retirements.
    if (out / "results.json").exists() and (out / "manifest.json").exists():
        for r in read(out / "results.json"):
            if r.get("final_mcq_review") and roster_entries.get(r["id"], {}).get("final_mcq_review") == r["final_mcq_review"]:
                roster[r["id"]] = "eligible"
    if focused or args.review_replacements:
        release = read(args.bank / "choice_release.json")
        if (sha256((args.bank / "zh.json").read_bytes()).hexdigest() != release["zh_sha256"] or set(roster) != set(bank)):
            ap.error("Published Chinese bank and eligibility roster must match the release.")
        if args.review_replacements:
            data = replacement_inputs(read(path), read(args.held_results), bank)
        elif args.audit_draft_wording:
            data = read(path)
        else:
            data = [dict(index=i, row=row) for i, row in enumerate(bank.values(), 1)
                    if roster[row["id"]] == "eligible"]
        if args.item_id:
            selected = set(args.item_id)
            data = [entry for entry in data if entry["row"]["id"] in selected]
            if len(data) != len(selected):
                ap.error("Unknown or ineligible source ID for this bank.")
    elif args.repair_reviewed_from:
        if readiness:
            release = read(args.bank / "choice_release.json")
            if (sha256((args.bank / "zh.json").read_bytes()).hexdigest() != release["zh_sha256"]
                    or sha256(path.read_bytes()).hexdigest() != release["readiness_publication"]["report_sha256"]):
                ap.error("The bank and readiness assessment must match the published release.")
            data = readiness_repair_inputs(decisions, bank, release)
            data = [r for r in data if roster[r["id"]] == "eligible"]
        else:
            data = editorial_repair_inputs(args.repair_reviewed_from, bank)
    else:
        data = read(path)
    if args.final_review_from:
        if len(data) != prior_manifest["items"]:
            ap.error("The completed run is missing question results.")
        data = [r for r in data if r["status"] == "held" and stages[-1] in r and roster.get(r["id"]) == "eligible"]
        if any(r["before"] != bank[r["id"]] for r in data):
            ap.error("The held result was not generated from the currently published wording.")
    elif replay:
        data = [r for r in data if r["status"] == "held" and stages[-1] not in r]
    if not data:
        print("No items require processing.")
        return
    if args.source_flags_from:
        previous = {r["id"]:r for r in read(args.source_flags_from)}
        for entry in data:
            row = entry["after"] if replay else entry["row"]
            old = previous.get(row["id"], {})
            if old and all(old["before"][k] == row[k] for k in ("passage_id", "verses", "correct")):
                entry.setdefault("source_flags", old.get("source_flags", []))
    rows = [r["after"] if replay else r["row"] for r in data]
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids) or len({r["index"] for r in data}) != len(data):
        ap.error("Duplicate item identity or index.")
    for row in rows:
        ref = bank[row["id"]]
        original = originals[row["id"]]
        if (original["passage_id"] != row["passage_id"] or original["correct"] != row["correct"]
                or list(original["verses"]) != list(row["verses"])):
            ap.error(f"Source key or verse window mismatch for {row['id']}")
        if (roster.get(row["id"]) != "eligible" or row["correct"] not in LETTERS or len(row["choices"]) != 5
                or row["choices"][4] != ref["choices"][4]
                or any(row[k] != ref[k] for k in ("source", "passage_id", "verses", "correct"))):
            ap.error(f"Ineligible item or mismatched reference for {row['id']}")
    mode = ("draft_wording_audit" if args.audit_draft_wording else "window_wording_audit" if args.audit_window_wording else
            "menu_design_audit" if args.audit_menu_design else "stem_identity_audit" if args.audit_stem_identities else
            "answer_meaning_audit" if args.audit_answer_meaning else
            "translation_audit" if args.audit_translatability else "published_key_audit") if focused else (
        "approved_replacements" if args.review_replacements else
        "exhausted_final_review" if args.final_review_from else
        "readiness_repair" if readiness else "editorial_repair" if args.repair_reviewed_from else "held_repair" if replay else "full_pipeline")
    manifest = dict(mode=mode,
                    items=len(data),
                    inspect_only=args.inspect_only,
                    writer=MODEL,
                    reviewer=JUDGE,
                    inputs_sha256=digest(data),
                    references_sha256=digest([bank[cid] for cid in ids]),
                    meaning_reference_sha256=digest([originals[cid] for cid in ids]),
                    recipe_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                    target_version=mcq_target.target_version(),
                    complexity_version=mcq_complexity.complexity_version(),
                    max_repair_rounds=len(stages))
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = out / "manifest.json"
        if m.exists() and read(m) != manifest:
            raise ValueError("Output directory belongs to a different run.")
        write(m, manifest)
        load_dotenv(ROOT / ".env")
        client = OpenAI(base_url="https://api.openai.com/v1", timeout=180, max_retries=2)

        def process(entry):
            folder = out / "items" / f"{entry['index']:03}"
            final = folder / "result.json"
            if final.exists():
                return read(final)
            if args.review_replacements:
                result = review_replacement(entry, originals[entry["row"]["id"]], client, folder)
                row = result["before"]
                fields = entry["approval"].get("manually_written_fields")
                if fields is None:
                    fields = manual_fields(args.bank.name, row["id"], row["question"], row["choices"], row["correct"])
                result["manually_written_fields"] = retained_manual_fields(result, row, fields)
                write(final, result)
                return result
            if focused:
                row = entry["row"]
                if args.audit_draft_wording:
                    review = review_choices(client, row, folder, full_review=True)
                elif args.audit_window_wording:
                    review = window_wording_review(client, row, folder)
                    design = menu_design_review(client, row, folder)
                    review["checks"].update(design["checks"])
                    review["fixed_findings"].extend(design["fixed_findings"])
                    review["findings"].extend(design["findings"])
                    cue, cue_findings = key_cue_review(client, row, folder)
                    review["checks"]["key_cues"] = cue
                    review["fixed_findings"].extend(cue_findings)
                elif args.audit_menu_design:
                    review = menu_design_review(client, row, folder)
                    if review["fixed_findings"] or review["findings"]:
                        identity = stem_identity_review(client, row, folder)
                        review["checks"].update(identity["checks"])
                        review["fixed_findings"].extend(identity["fixed_findings"])
                elif args.audit_stem_identities:
                    review = stem_identity_review(client, row, folder)
                elif args.audit_answer_meaning:
                    review = meaning_review(client, row, folder, originals[row["id"]], entry.get("source_flags", []))
                elif args.audit_translatability:
                    review = translation_review(client, row, folder)
                else:
                    cue, findings = key_cue_review(client, row, folder)
                    review = dict(checks={"key_cues": cue}, fixed_findings=findings, findings=[])
                    if cue.get("redundant_stem_excerpt"):
                        wording = window_wording_review(client, row, folder)
                        review["checks"].update(wording["checks"])
                        review["fixed_findings"].extend(wording["fixed_findings"])
                        review["findings"].extend(wording["findings"])
                if not (args.audit_answer_meaning or args.audit_stem_identities or args.audit_menu_design):
                    meaning = meaning_review(client, row, folder, originals[row["id"]], entry.get("source_flags", []))
                    review["checks"].update(meaning["checks"])
                    review["fixed_findings"].extend(meaning["fixed_findings"])
                if entry.get("editorial_concern"):
                    source = originals[row["id"]]
                    check_editorial_concern(client, folder, row, source["question"], source["choices"][LETTERS.index(row["correct"])],
                                            entry["editorial_concern"], review)
                result = dict(index=entry["index"], id=row["id"], reference=row["reference"],
                              before=row, after=row, attempts=[review], source_flags=entry.get("source_flags", []),
                              identity_only=args.audit_stem_identities,
                              meaning_only=args.audit_answer_meaning, key_only=args.audit_published_keys or args.audit_answer_meaning,
                              status="held" if review["fixed_findings"] or review["findings"] else "passed")
                if entry.get("editorial_concern"):
                    result["editorial_concern"] = entry["editorial_concern"]
            else:
                result = entry if replay else run_item(dict(entry, meaning_source=originals[entry["row"]["id"]]), client, folder)
            if not args.inspect_only and not args.final_review_from and result["status"] == "held" and (
                    focused or replay or not entry.get("distractors_only") or result["attempts"][-1]["fixed_findings"]):
                for stage in stages:
                    if result["status"] != "held":
                        break
                    if stage not in result:
                        result = repair_once(result, bank[result["id"]], client, folder / stage, stage=stage,
                                             meaning_source=originals[result["id"]])
            row = entry["after"] if replay else entry["row"]
            fields = entry.get("manually_written_fields")
            if fields is None:
                fields = manual_fields(args.bank.name, row["id"], row["question"], row["choices"], row["correct"])
            if not focused and not replay:  # The distractor writer supplies every unpinned alternative.
                kept = {"Q", row["correct"], *entry.get("pinned_distractors", [])}
                fields = [field for field in fields if field in kept]
            # A replay starts at the input result's last wording. Its prior repairs already have provenance.
            new_stages = {s: result[s] for s in stages if s in result and (not replay or s not in entry)}
            result["manually_written_fields"] = retained_manual_fields(dict(after=result["after"], **new_stages), row, fields)
            if (published and not args.inspect_only and result["status"] == "held" and stages[-1] in result
                    and result["before"] == bank[result["id"]]):
                cid = result["id"]
                result["final_mcq_review"] = final_mcq_review(client, bank[cid], originals[cid], result, stages, folder)
            write(final, result)
            return result

        results, errors = [], {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = {pool.submit(process, entry): row["id"] for entry, row in zip(data, rows, strict=True)}
            for job in as_completed(jobs):
                try:
                    result = job.result()
                    results.append(result)
                    print(result["id"], result["status"], flush=True)
                except Exception as exc:
                    errors[jobs[job]] = f"{type(exc).__name__}: {exc}"
                    print(jobs[job], errors[jobs[job]], flush=True)
        write(out / "errors.json", errors)
        if errors:
            raise SystemExit(2)
        results.sort(key=lambda r: r["index"])
        write(out / "results.json", results)
        if args.review_replacements:
            write(out / "selection.json", replacement_selection(results))
        final_reviews = {r["id"]: r["final_mcq_review"] for r in results if "final_mcq_review" in r}
        if final_reviews:
            write(out / "final_reviews.json", final_reviews)
            if not args.preview_retirements:
                apply_final_retirements(args.bank, results, release)
            print("Final review:", dict(Counter(v["verdict"] for v in final_reviews.values())), flush=True)
        print(dict(Counter(r["status"] for r in results)), flush=True)


if __name__ == "__main__":
    main()
