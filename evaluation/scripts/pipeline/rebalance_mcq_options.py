#!/usr/bin/env python3
"""Rebalance MCQ options so the key does not stand out by verbatim overlap with its window.

WHY. A respondent can answer an MCQ without understanding it by picking the option that
is lifted most completely from the text they just read. Measured 2026-09-30: model
accuracy rises with the key's overlap margin over its best distractor (r = +0.12 gold72,
+0.22 hard66), and wrong answers land on the highest-overlap distractor above chance.
The property is NOT translation-invariant (Chinese Bible register collapses English
paraphrases onto the passage's wording), so it has to be fixed on the TARGET-language
QA, against the window the respondent actually sees.

WHAT. Every MCQ is first AUDITED as it stands:
  * window check  -- the candidate-screening prompt (the SAME prompt new candidates get,
                     one scale for old and new options), BLIND to the key, labels every
                     option correct / incorrect / ambiguous using only the window the
                     respondent sees, rates naturalness and plausibility 1-5; a distractor
                     rated 1-2 fails the audit (--no-plausibility-gate: report only);
  * fact check    -- the same model, given the WHOLE passage, flags wrong options that
                     name the same person/thing as the key or are true answers elsewhere in
                     the passage (respondents who know the story would be marked wrong).
The key must come back "correct". A distractor failing either check is replaced.

Then overlap is measured deterministically (longest contiguous shared span / option
length vs the window, as in ``analysis/current/audit_option_overlap.py``). An item is
rebalanced when the key leads the best distractor by more than --tolerance, or leads ANY
distractor by more than 0.40 (a verbatim lure plus leftover throwaways is still a
recognition cue -- every distractor has to be in range):

  1. generate  -- the generator first states the key's answer type and what the question
                  assumes; every candidate must be that type and carry a "why_tempting"
                  reason (candidates without one, or of another type, are dropped);
                  about half copied verbatim from the window (true there but
                  wrong for this question) when the window can supply them, part-swaps for
                  multi-part keys (the swapped-in part may be an outside name of the same
                  kind), paraphrases for inference answers or exhausted windows; claimed
                  spans are verified against the window and duplicates dropped;
  2. select    -- deterministically pick the 3-distractor set whose overlap and length best
                  match the key, penalising every distractor far below the key, stem echoes,
                  needless changes and low plausibility (which outranks a slightly better
                  overlap match);
  2a. screen   -- ALL new candidates are rated in one blind call (correct/incorrect/
                  ambiguous, natural, plausibility 1-5 "would a careless reader be tempted?");
                  only incorrect, natural candidates rated >= 3 can be chosen. Each candidate
                  is scored once, so a score cannot flip between rounds;
  3. validate  -- the chosen set is re-checked blind for correctness (in context of the
                  other options) + whole-passage fact check; offenders are banned and
                  selection repeats, up to 5 rounds (more candidates generated if needed);
  4. gate      -- apply when validated and both gaps are within tolerance ("rebalanced"),
                  when the WORSE of the two gaps improved by >= 0.15 ("partial"), or when
                  an invalid distractor was replaced
                  ("replaced_invalid"); everything else is left unchanged (needs_review).

Key rewording (report-only): when an item ends needs_review because it could not be
balanced AND its key is copied from the window (overlap >= 0.8), the generator proposes
rewordings of the key that mean exactly the same, about the original's length and one
clause; each is checked blind (still correct, natural) and against the original (same
meaning, not narrower/broader; fluency 1-5); among the valid ones the choice weighs the
overlap target, fluency and length match to the other options (no "longest option" cue),
and the distractors are rebalanced against it. The proposal goes to the report columns key_proposal_status / proposed_key /
proposed_options for a human to approve -- it is NEVER applied. --no-key-rewording skips it.

Never changed: the key's text and letter, option E (the meta-option), the open form,
items with status "exclude". Every change is recorded on the item (``option_rebalance``)
and in a review CSV, which a human should skim before import: the two checks lower but do
not remove the risk of a second correct answer. Unnatural EXISTING options are reported
(column "unnatural") but only new candidates are rejected for it. --no-fact-check skips
the whole-passage check.

Models: OpenAI only. Defaults ``gpt-6.1-sol`` (generate) and ``gpt-6-astra`` (window and
fact checks),
reasoning effort ``high``; override with --generator-model / --judge-model or
OPENAI_DISTRACTOR_MODEL / OPENAI_DISTRACTOR_JUDGE_MODEL. If your account has no Astra
access, pass --judge-model gpt-6.1-sol.

USAGE
  # tier-1 corpus tree (QA + passage from <pid>/omission/0%, windows file), dry run:
  python -m evaluation.scripts.pipeline.rebalance_mcq_options tier1 \\
      --tier1-root ~/mnt/eten-research-outputs/evaluation/outputs/tier1_bsb_unblinded_5opt_think \\
      --windows-json QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json \\
      --report rebalance_gold72.csv
  # ... then write it into every qa_target*.json copy under each passage:
  ... tier1 ... --apply
  # hard66-style per-passage QA files (window_verses on each record):
  ... tier1 --tier1-root <same> --qa-dir evaluation/datasets/qa/tier1_hard66_canonical --apply
  # copy the reference options into every condition/model copy (after hand edits):
  ... tier1 --tier1-root <same> --apply --sync --measure-only   (measure-only: no API calls)
  # measurement only, no API calls:
  ... tier1 ... --measure-only
  # a single pipeline QA file against one passage (what main.py --rebalance-mcq uses):
  ... file --qa-json _shared/run_qa_zh.json --passage llm_prompt_high/passage_target.txt \\
      --out _shared/run_qa_zh.json --report _shared/run_mcq_rebalance.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import itertools
import json
import math
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.agents.generate_chinese_answers import (  # noqa: E402
    chapters_from_reference,
    index_passage_verses,
    item_reference_key,
    load_verse_windows,
    local_passage_for_question,
)

CONTENT_LETTERS = "ABCD"
DEFAULT_GENERATOR_MODEL = os.getenv("OPENAI_DISTRACTOR_MODEL", "gpt-6.1-sol")
DEFAULT_JUDGE_MODEL = os.getenv("OPENAI_DISTRACTOR_JUDGE_MODEL", "gpt-6-astra")
DEFAULT_EFFORT = os.getenv("OPENAI_DISTRACTOR_EFFORT", "high")
DEFAULT_TOLERANCE = 0.15
DEFAULT_CANDIDATES = 10
DEFAULT_MAX_ROUNDS = 5
MIN_IMPROVEMENT = 0.15
WEAKEST_GAP_TOLERANCE = 0.40  # key may lead its WEAKEST distractor by at most this, so every
                              # distractor -- not just the best one or two -- is in range
MIN_PLAUSIBILITY = 3          # judge rates 1-5; new options rated below this are rejected
PLAUSIBILITY_WEIGHT = 0.1     # selection cost per plausibility point below 5
BACKUP_TAG = "bak_rebalance"

# LLM interface: (role, system, user) -> parsed JSON object; role is generate/judge/factcheck.
LLM = Callable[[str, str, str], dict]


class RebalanceError(Exception):
    pass


# ----------------------------------------------------------------------- measurement
def normalize(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def longest_shared_span(option: str, window: str) -> int:
    best = 0
    for start in range(len(option)):
        for end in range(start + best + 1, len(option) + 1):
            if option[start:end] in window:
                best = end - start
            else:
                break
    return best


def overlap_ratio(option: Any, window: str) -> float:
    option = normalize(option)
    return longest_shared_span(option, window) / len(option) if option else 0.0


def content_options(item: dict) -> Dict[str, str]:
    options = item.get("A") if isinstance(item.get("A"), dict) else {}
    return {k: str(v) for k, v in options.items() if k in CONTENT_LETTERS}


def key_letter(item: dict) -> str:
    return str(item.get("correct") or "").strip()[:1]


def measure(options: Dict[str, str], key: str, window: str) -> dict:
    ratios = {letter: overlap_ratio(text, window) for letter, text in options.items()}
    others = [r for letter, r in ratios.items() if letter != key]
    best = max(others) if others else 0.0
    k = ratios.get(key, 0.0)
    return {"ratios": ratios, "key": k, "best_distractor": best, "gap": k - best,
            "weakest_gap": weakest_gap(k, others)}


def classify(stats: dict, tolerance: float) -> str:
    if stats["gap"] > tolerance:
        return "key_stands_out"
    if stats.get("weakest_gap", 0.0) > WEAKEST_GAP_TOLERANCE:
        return "uneven"           # some distractor is far below the key: a leftover throwaway
    if stats["gap"] < -tolerance:
        return "distractor_dominates"
    return "balanced"


# --------------------------------------------------------------------------- windows
@dataclass
class PassageContext:
    text: str
    reference: str = ""
    verse_windows: Optional[dict] = None
    verse_window: int = 2
    fact_check: bool = True
    key_rewording: bool = True
    plausibility_gate: bool = True    # existing distractors rated 1-2 fail the audit
    index: dict = field(default_factory=dict)
    order: list = field(default_factory=list)

    def __post_init__(self):
        chapters = chapters_from_reference(self.reference)
        self.index, self.order = index_passage_verses(self.text, chapters)

    def window_for(self, item: dict) -> str:
        labels = item.get("window_verses")
        if labels:
            chapters = chapters_from_reference(item.get("passage_reference") or self.reference)
            ref = item_reference_key(item.get("reference"), chapters)
            chapter = ref[0] if ref else (chapters[0] if chapters else None)
            keys = []
            for label in labels:
                text = str(label)
                if ":" in text:
                    c, v = text.split(":", 1)
                    keys.append((int(c), int(v)))
                else:
                    keys.append((chapter, int(text)))
            chosen = [self.index[k] for k in keys if k in self.index]
            if chosen:
                return normalize("".join(chosen))
        question = dict(item)
        question.setdefault("passage_reference", self.reference)
        return normalize(local_passage_for_question(
            self.text, self.index, question, self.verse_window, self.order,
            self.verse_windows,
        ))

    def display_window_for(self, item: dict) -> str:
        """The window as readable text (with verse markers) for prompts and reports."""
        labels = item.get("window_verses")
        question = dict(item)
        question.setdefault("passage_reference", self.reference)
        if labels:
            chapters = chapters_from_reference(item.get("passage_reference") or self.reference)
            ref = item_reference_key(item.get("reference"), chapters)
            chapter = ref[0] if ref else (chapters[0] if chapters else None)
            keys = []
            for label in labels:
                text = str(label)
                if ":" in text:
                    c, v = text.split(":", 1)
                    keys.append((int(c), int(v)))
                else:
                    keys.append((chapter, int(text)))
            chosen = [self.index[k] for k in keys if k in self.index]
            if chosen:
                return "\n".join(chosen)
        return local_passage_for_question(
            self.text, self.index, question, self.verse_window, self.order,
            self.verse_windows,
        )


# ------------------------------------------------------------------------- prompts
GENERATE_SYSTEM = """You write WRONG options (distractors) for a Simplified-Chinese multiple-choice \
reading-comprehension question. Respondents see ONLY the excerpt given, and the purpose of the \
question is to test whether they understood it.

First decide, and return, the correct answer's TYPE (person, group, place, time, object, \
action, reason, quantity or other) and what the question ASSUMES about the answer (e.g. "kings or \
armies that could be hired to attack the Syrians").

Rules for every candidate:
0. It must be the SAME TYPE as the correct answer and fit what the question assumes, so it is a \
believable answer to someone who read carefully but misremembered or skimmed. Give, for each, \
"why_tempting": one short sentence on why a careless reader might pick it. If you cannot give a \
real reason, do not propose it. Outside names must fit the passage's period and region.
1. It must be clearly WRONG as an answer to the question, judged using ONLY the excerpt. Not \
partially right, not a synonym, restatement, superset or subset of the correct answer, and not \
another name or description of the same person, place or thing.
2. Prefer kind "span": a phrase COPIED VERBATIM (character for character) from the excerpt that is \
true there but does not answer THIS question -- the wrong person (someone else in the scene), the \
wrong time or order (an earlier or later event), the wrong place, object or role. Light trimming is \
fine; rewording is not. Aim for about half spans, BUT only as many as the excerpt can genuinely \
supply: never repeat a candidate, never give the same phrase twice in different wording, and never \
use a span that is a strained or implausible answer just to fill the quota. If the excerpt runs out \
of suitable phrases, set "excerpt_exhausted": true and fill the rest with swaps or paraphrases.
3. If the correct answer lists several parts (e.g. "X和Y"), give at least two kind "swap" \
candidates for EACH part -- some keeping the first part, some keeping the second -- replacing \
the other part with something of the SAME KIND. The \
replacement may come from OUTSIDE the excerpt (e.g. another nation or group of kings for a \
nation/group of kings) as long as it is plausible for the question and clearly not what the \
excerpt says. Do not swap in anything that would make the option partly true.
4. Use kind "paraphrase" for why/how questions whose answer is an inference, or when the excerpt \
and swaps offer nothing suitable.
5. Every candidate must read as a natural, grammatical answer to THIS question in Simplified \
Chinese, in the same form as the correct answer (if the answer is a noun phrase, give noun \
phrases; if it is an action the person was told to do, give actions; keep pronouns unambiguous). \
Match the correct answer's punctuation style and approximate length. Write each candidate as a \
plain answer phrase: no quotation marks, no "X说：" lead-ins, no quoted sentences copied whole; \
end with 。 only if the correct answer does.
6. Do not reuse the question's own subject phrase as an option.
7. Do not propose anything listed under "do_not_propose".

Return a JSON object: {"answer_type": "...", "question_assumes": "...", \
"excerpt_exhausted": false, "candidates": [{"text": "...", "type": "same value as answer_type", \
"kind": "span|swap|paraphrase", "source": "verse number it comes from, 'outside' for an outside \
name in a swap, or 'paraphrase'", "why_wrong": "one short sentence", \
"why_tempting": "one short sentence"}]}"""

JUDGE_SYSTEM = """You check multiple-choice reading-comprehension items. Using ONLY the excerpt \
(no outside knowledge), decide for EACH option whether it is a correct answer to the question:
- "correct": the excerpt supports it as an answer to the question;
- "incorrect": the excerpt shows it does not answer the question, or it answers a different question;
- "ambiguous": a careful reader could reasonably defend it as correct from the excerpt.
More than one option may be correct. Judge each option on its own.
Also judge each option's LANGUAGE: "natural" is true only if it is grammatical Simplified Chinese \
that reads as a sensible answer to this question in form (a noun phrase for who/what questions, an \
action for what-did-X-do questions, a reason for why questions, with clear pronouns). Whether it \
is right or wrong does not matter for "natural".

Finally rate each option's PLAUSIBILITY from 1 to 5: "Would a reader who skimmed or \
half-remembered the excerpt be tempted to choose it?" 1 = nobody would pick it (wrong kind of \
answer, absurd, or obviously not what the question is about); 3 = some readers might; 5 = very \
tempting. Rate correct options 5.

Return a JSON object: {"options": [{"letter": "A", "label": "correct|incorrect|ambiguous", \
"natural": true, "plausibility": 4, "reason": "one short sentence"}]}"""

SCREEN_SYSTEM = """You screen candidate answers for a multiple-choice reading-comprehension \
question. Using ONLY the excerpt (no outside knowledge), judge EACH candidate on its own:
- "label": "correct" if the excerpt supports it as an answer to the question, "incorrect" if the \
excerpt shows it does not answer the question (or answers a different one), "ambiguous" if a \
careful reader could reasonably defend it as correct;
- "natural": true only if it is grammatical Simplified Chinese that reads as a sensible answer to \
this question in form (whether it is right or wrong does not matter);
- "plausibility" 1-5: "Would a reader who skimmed or half-remembered the excerpt be tempted to \
choose it?" 1 = nobody would (wrong kind of answer, absurd, obviously off-topic); 3 = some \
readers might; 5 = very tempting. Rate correct candidates 5.
Use the same standard for every candidate so their scores are comparable.

Return a JSON object: {"candidates": [{"id": "c1", "label": "correct|incorrect|ambiguous", \
"natural": true, "plausibility": 3, "reason": "one short sentence"}]}"""

KEYGEN_SYSTEM = """The correct answer of a Simplified-Chinese multiple-choice reading question \
is copied word for word from the excerpt, so readers can find it by recognition without \
understanding. Write REWORDINGS of the correct answer that:
- mean EXACTLY the same thing in this context: not more specific, not vaguer, no added or \
dropped detail, still clearly the right answer to the question from the excerpt alone;
- do NOT copy the excerpt's wording: change the words and/or structure (synonyms, a different \
but natural construction); a few shared characters such as names are fine;
- read as a natural answer to the question in the same form as the original (noun phrase for \
who/what, action for what-did-X-do, and so on), with no quotation marks;
- stay close to the original's LENGTH (within about a third longer or shorter) and use a \
single clause: no commas splitting it into two clauses. Longer or wordier rewordings make the \
correct answer stand out as the longest option.

Return a JSON object: {"rewordings": [{"text": "...", "why_same": "one short sentence"}]}"""

KEYCHECK_SYSTEM = """You check proposed rewordings of the correct answer to a multiple-choice \
reading question. For EACH rewording decide whether it means EXACTLY the same as the original \
correct answer in the context of the excerpt and question: "same", or "narrower" (adds detail or \
is more specific), "broader" (vaguer or drops detail), "different" (changes the meaning). Also \
say whether it reads naturally, and rate its FLUENCY 1-5 as an answer to this question (5 = \
exactly how a native speaker would phrase it; 3 = understandable but a little stiff; 1 = awkward).

Return a JSON object: {"rewordings": [{"id": "r1", "verdict": "same|narrower|broader|different", \
"natural": true, "fluency": 4, "reason": "one short sentence"}]}"""

FACTCHECK_SYSTEM = """You check the WRONG options of a multiple-choice question about one excerpt of \
a longer Bible passage. Respondents see only the excerpt, but some of them know the whole story. \
Using the FULL passage, flag a wrong option if EITHER:
- "same_referent": it names or describes the same person, group, place, object or event as the \
correct answer (another name, title or description for it), or
- "true_in_passage": the full passage shows it is also a true answer to the question.
Otherwise it is "ok". Being mentioned in the passage is not enough; it must actually answer the \
question or be the same thing as the correct answer.

Return a JSON object: {"options": [{"letter": "B", "verdict": "ok|same_referent|true_in_passage", \
"reason": "one short sentence citing the verse"}]}"""


def generate_user_prompt(item: dict, window_text: str, n: int, avoid: Sequence[str] = ()) -> str:
    key = key_letter(item)
    options = content_options(item)
    return json.dumps({
        "excerpt": window_text,
        "question": item.get("Q"),
        "correct_answer": options.get(key),
        "current_wrong_options": [v for k, v in options.items() if k != key],
        "do_not_propose": list(avoid),
        "number_of_candidates": n,
    }, ensure_ascii=False, indent=1)


def judge_user_prompt(item: dict, window_text: str, options: Dict[str, str]) -> str:
    return json.dumps({
        "excerpt": window_text,
        "question": item.get("Q"),
        "options": {k: options[k] for k in sorted(options)},
    }, ensure_ascii=False, indent=1)


def screen_user_prompt(item: dict, window_text: str, candidates: Sequence[str]) -> str:
    return json.dumps({
        "excerpt": window_text,
        "question": item.get("Q"),
        "candidates": {f"c{i + 1}": text for i, text in enumerate(candidates)},
    }, ensure_ascii=False, indent=1)


def factcheck_user_prompt(item: dict, passage: str, window_text: str,
                          options: Dict[str, str], key: str) -> str:
    return json.dumps({
        "full_passage": passage,
        "excerpt_shown_to_respondents": window_text,
        "question": item.get("Q"),
        "correct_answer": options[key],
        "wrong_options": {k: v for k, v in sorted(options.items()) if k != key},
    }, ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------- OpenAI
def parse_json_object(text: str) -> dict:
    text = (text or "").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RebalanceError(f"model returned no JSON object: {text[:200]!r}")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RebalanceError("model returned JSON that is not an object")
    return value


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    parts = []
    for out in getattr(response, "output", None) or []:
        for content in getattr(out, "content", None) or []:
            value = getattr(content, "text", None)
            if value:
                parts.append(value)
    return "".join(parts)


def openai_llm(generator_model: str, judge_model: str, effort: Optional[str],
               retries: int = 2, client: Any = None) -> LLM:
    """Responses-API caller. Roles: generate -> generator model; judge, screen and factcheck ->
    judge model. Reasoning models get ``reasoning.effort`` and no temperature; a model that rejects
    ``reasoning`` (classic chat models) is retried at temperature 0. Thread-safe."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    models = {"generate": generator_model, "judge": judge_model, "screen": judge_model,
              "factcheck": judge_model, "keygen": generator_model, "keycheck": judge_model}
    no_reasoning: set = set()

    def call(role: str, system: str, user: str) -> dict:
        model = models[role]
        last: Optional[Exception] = None
        for attempt in range(retries + 1):
            kwargs: Dict[str, Any] = {
                "model": model,
                "input": [{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                "text": {"format": {"type": "json_object"}},
            }
            if effort and model not in no_reasoning:
                kwargs["reasoning"] = {"effort": effort}
            else:
                kwargs["temperature"] = 0
            try:
                return parse_json_object(_response_text(client.responses.create(**kwargs)))
            except Exception as exc:  # noqa: BLE001 -- SDK raises many types
                last = exc
                if "reasoning" in str(exc).lower() and model not in no_reasoning:
                    no_reasoning.add(model)
                    continue
                time.sleep(min(2 ** attempt, 10))
        raise RebalanceError(f"{role} call to {model} failed: {last}")

    return call


# ------------------------------------------------------------------------ selection
@dataclass
class Candidate:
    text: str
    origin: str               # existing letter ("B") or "new"
    source: str = ""
    why_wrong: str = ""
    kind: str = ""
    why_tempting: str = ""


def _similar(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def stem_echo(option: str, stem: str) -> bool:
    option = normalize(option).rstrip("。．.!！?？")
    return len(option) >= 3 and option in normalize(stem)


QUOTE_CHARS = "“”‘’\"'「」『』"
SPEECH_LEAD = re.compile(r"^[^，。：:“”]{1,12}[说道问答][：:]\s*")


def tidy_option(text: str, key_ends_with_stop: bool) -> str:
    """Make a candidate look like an answer, not a quotation: drop quote marks and a
    "X说：" lead-in, and match the key's sentence-final stop."""
    text = text.strip()
    stripped = SPEECH_LEAD.sub("", text)
    if stripped != text and any(q in text for q in QUOTE_CHARS):
        text = stripped
    text = "".join(ch for ch in text if ch not in QUOTE_CHARS).strip()
    text = text.rstrip("。.").strip()
    return text + "。" if key_ends_with_stop and text else text


def clean_candidates(raw: Sequence[dict], key_text: str, existing: Sequence[str],
                     window: str = "", answer_type: str = "") -> List[Candidate]:
    """Drop restatements of the key, duplicates, candidates of a different answer type than
    the key, and candidates without a reason a careless reader would pick them; re-label
    kind from the text itself (a claimed "span" not in the window becomes "paraphrase")."""
    out: List[Candidate] = []
    seen = [normalize(t) for t in existing]
    answer_type = str(answer_type or "").strip().lower()
    key_ends = normalize(key_text).endswith(("。", "."))
    for entry in raw or []:
        text = tidy_option(str((entry or {}).get("text") or ""), key_ends)
        why_tempting = str((entry or {}).get("why_tempting") or "").strip()
        if not why_tempting:
            continue
        cand_type = str((entry or {}).get("type") or "").strip().lower()
        if answer_type and cand_type and cand_type != answer_type:
            continue
        if not text or len(normalize(text)) > 3 * len(normalize(key_text)) + 8:
            continue
        kind = str(entry.get("kind") or "").strip().lower()
        # A swap differs from the key (and from sibling swaps) in exactly one part by design,
        # so character similarity says nothing; drop it only if it equals or contains them.
        is_swap = kind == "swap"
        contains = lambda a, b: normalize(a) == normalize(b) or (
            len(normalize(a)) >= 2 and len(normalize(b)) >= 2
            and (normalize(a) in normalize(b) or normalize(b) in normalize(a)))
        if (contains(text, key_text) if is_swap else _similar(text, key_text) >= 0.8):
            continue
        if any((contains(text, s) if is_swap else _similar(text, s) >= 0.85) for s in seen):
            continue
        seen.append(normalize(text))
        if window:
            ratio = overlap_ratio(text, window)
            if kind == "span" and ratio < 0.8:
                kind = "paraphrase"
            elif not kind:
                kind = "span" if ratio >= 0.8 else "paraphrase"
        out.append(Candidate(text=text, origin="new", source=str(entry.get("source") or ""),
                             why_wrong=str(entry.get("why_wrong") or ""), kind=kind,
                             why_tempting=why_tempting))
    return out


def weakest_gap(key_ratio: float, ratios: Sequence[float]) -> float:
    """How far the key leads its LEAST-overlapping distractor (0 with no distractors)."""
    return key_ratio - min(ratios) if ratios else 0.0


def worst_gap(stats: dict) -> float:
    """The larger of |key - best distractor| and the key's lead over its weakest one."""
    return max(abs(stats["gap"]), max(0.0, stats.get("weakest_gap", 0.0)))


KEY_PART_SPLIT = re.compile(r"以及|[和与、，,]")   # not 及 alone: it is inside 埃及


def key_parts(key_text: str) -> List[str]:
    """Parts of a multi-part key ("赫人的诸王和埃及的诸王" -> ["赫人的诸王", "埃及的诸王"])."""
    parts = [p for p in KEY_PART_SPLIT.split(normalize(key_text).rstrip("。.")) if len(p) >= 2]
    return parts if len(parts) >= 2 else []


def same_part_penalty(key_text: str, chosen: Sequence["Candidate"]) -> float:
    """Swaps should not all keep the SAME part of a multi-part key: if every swap keeps
    "埃及的诸王", a reader who remembers only the other part still finds the answer."""
    parts = key_parts(key_text)
    if not parts:
        return 0.0
    kept = [frozenset(p for p in parts if p in normalize(c.text)) for c in chosen]
    kept = [k for k in kept if k]
    if len(kept) < 2:
        return 0.0
    from collections import Counter
    most = Counter(kept).most_common(1)[0][1]
    if most == len(chosen):          # every option keeps the same part
        return 0.25
    return 0.08 * (most - 1)


def set_cost(key_ratio: float, key_text: str, stem: str, chosen: Sequence[Candidate],
             window: str, plaus: Optional[Dict[str, int]] = None) -> float:
    ratios = [overlap_ratio(c.text, window) for c in chosen]
    k_len = max(len(normalize(key_text)), 1)
    cost = abs(key_ratio - max(ratios))
    # EVERY distractor must be in range, not just the best one or two: each one the key
    # leads by more than the tolerance is penalised, so no leftover throwaway survives
    cost += 0.6 * sum(max(0.0, (key_ratio - r) - WEAKEST_GAP_TOLERANCE) for r in ratios)
    cost += 0.25 * sum(abs(key_ratio - r) for r in ratios) / len(ratios)
    cost += 0.15 * sum(abs(math.log(max(len(normalize(c.text)), 1) / k_len)) for c in chosen) / len(chosen)
    cost += 0.30 * sum(stem_echo(c.text, stem) for c in chosen)
    cost += 0.04 * sum(c.origin == "new" for c in chosen)
    cost += same_part_penalty(key_text, chosen)
    # plausibility outranks a slightly better overlap match: each point below 5 costs
    # about as much as 0.1 of overlap gap (unknown = 3, i.e. not yet judged)
    if plaus is not None:
        cost += PLAUSIBILITY_WEIGHT * sum(5 - plaus.get(normalize(c.text), 3) for c in chosen)
    return cost


def choose_set(item: dict, window: str, pool: Sequence[Candidate], banned: set,
               plaus: Optional[Dict[str, int]] = None) -> Optional[List[Candidate]]:
    key = key_letter(item)
    options = content_options(item)
    key_text = options[key]
    key_ratio = overlap_ratio(key_text, window)
    usable = [c for c in pool if normalize(c.text) not in banned]
    n = len([l for l in options if l != key])
    if len(usable) < n:
        return None
    best, best_cost = None, None
    for combo in itertools.combinations(usable, n):
        cost = set_cost(key_ratio, key_text, item.get("Q") or "", combo, window, plaus)
        if best_cost is None or cost < best_cost:
            best, best_cost = list(combo), cost
    return best


def assign_letters(item: dict, chosen: Sequence[Candidate]) -> Dict[str, str]:
    """Keep surviving existing options in their letters; new ones fill the freed slots."""
    key = key_letter(item)
    options = dict(item.get("A") or {})
    slots = [l for l in CONTENT_LETTERS if l in options and l != key]
    kept = {c.origin for c in chosen if c.origin != "new"}
    free = [l for l in slots if l not in kept]
    new = [c for c in chosen if c.origin == "new"]
    for letter, cand in zip(free, new):
        options[letter] = cand.text
    return options


# --------------------------------------------------------------------- per item loop
@dataclass
class ItemResult:
    item_id: str
    status: str
    reason: str
    before: dict
    old_options: Dict[str, str]
    after: Optional[dict] = None
    new_options: Optional[Dict[str, str]] = None
    judge: Dict[str, str] = field(default_factory=dict)
    natural: Dict[str, bool] = field(default_factory=dict)
    plausibility: Dict[str, int] = field(default_factory=dict)
    facts: Dict[str, str] = field(default_factory=dict)
    notes: Dict[str, str] = field(default_factory=dict)
    window: str = ""
    # report-only proposal to reword a verbatim key (never applied automatically)
    proposal: Optional[dict] = None

    @property
    def changed(self) -> bool:
        return self.status in ("rebalanced", "partial", "replaced_invalid")


def judge_options(llm: LLM, item: dict, window_text: str, options: Dict[str, str]):
    """Blind window check: ({letter: label}, {letter: natural}, {letter: plausibility 1-5})."""
    raw = llm("judge", JUDGE_SYSTEM, judge_user_prompt(item, window_text, options))
    labels, natural, plaus = {}, {}, {}
    for entry in raw.get("options") or []:
        letter = str(entry.get("letter") or "").strip()[:1].upper()
        if letter not in options:
            continue
        label = str(entry.get("label") or "").strip().lower()
        labels[letter] = label if label in ("correct", "incorrect", "ambiguous") else "ambiguous"
        natural[letter] = entry.get("natural") is not False
        try:
            plaus[letter] = max(1, min(5, int(round(float(entry.get("plausibility"))))))
        except (TypeError, ValueError):
            pass
    for letter in options:
        labels.setdefault(letter, "ambiguous")   # a missing verdict never passes
        natural.setdefault(letter, True)
        plaus.setdefault(letter, 3)              # unrated: neutral, neither kept nor rejected for it
    return labels, natural, plaus


def factcheck_options(llm: LLM, item: dict, passage: str, window_text: str,
                      options: Dict[str, str], key: str) -> Dict[str, str]:
    """Whole-passage check of the WRONG options: {letter: ok|same_referent|true_in_passage}."""
    raw = llm("factcheck", FACTCHECK_SYSTEM,
              factcheck_user_prompt(item, passage, window_text, options, key))
    verdicts = {}
    for entry in raw.get("options") or []:
        letter = str(entry.get("letter") or "").strip()[:1].upper()
        verdict = str(entry.get("verdict") or "").strip().lower()
        if letter in options and letter != key:
            verdicts[letter] = verdict if verdict in ("ok", "same_referent", "true_in_passage") else "ok"
    for letter in options:
        if letter != key:
            verdicts.setdefault(letter, "ok")
    return verdicts


def screen_candidates(llm: LLM, item: dict, window_text: str,
                      candidates: Sequence["Candidate"]) -> Dict[str, dict]:
    """One blind call rating every new candidate: {text: {label, natural, plausibility}}.
    A candidate the screener skips gets a failing verdict (it is never chosen unscreened)."""
    if not candidates:
        return {}
    texts = [c.text for c in candidates]
    raw = llm("screen", SCREEN_SYSTEM, screen_user_prompt(item, window_text, texts))
    by_id = {str(e.get("id") or "").strip(): e for e in raw.get("candidates") or []}
    out = {}
    for i, text in enumerate(texts):
        entry = by_id.get(f"c{i + 1}")
        if entry is None:
            out[text] = {"label": "ambiguous", "natural": False, "plausibility": 1}
            continue
        label = str(entry.get("label") or "").strip().lower()
        try:
            score = max(1, min(5, int(round(float(entry.get("plausibility"))))))
        except (TypeError, ValueError):
            score = 1
        out[text] = {"label": label if label in ("correct", "incorrect", "ambiguous") else "ambiguous",
                     "natural": entry.get("natural") is not False, "plausibility": score}
    return out


def screen_passes(verdict: dict) -> bool:
    return (verdict["label"] == "incorrect" and verdict["natural"]
            and verdict["plausibility"] >= MIN_PLAUSIBILITY)


def audit_existing(llm: LLM, item: dict, ctx: "PassageContext", display: str,
                   options: Dict[str, str], key: str):
    """Audit an item's CURRENT options with the candidate-screening prompt (each option rated
    on its own, blind to the key) -- the same prompt and scale new candidates get -- then
    the whole-passage fact check. Returns (labels, natural, plaus, facts, offending, key_ok).

    Offending: a distractor that is not "incorrect", and -- when ``ctx.plausibility_gate``
    is on -- a distractor rated below MIN_PLAUSIBILITY. Unnatural existing options are
    only reported."""
    letters = sorted(options)
    verdicts = screen_candidates(llm, item, display, [Candidate(options[l], l) for l in letters])
    labels = {l: verdicts[options[l]]["label"] for l in letters}
    natural = {l: verdicts[options[l]]["natural"] for l in letters}
    plaus = {l: verdicts[options[l]]["plausibility"] for l in letters}
    if labels.get(key) != "correct":
        return labels, natural, plaus, {}, set(), False
    offending = {l for l in letters if l != key and labels[l] != "incorrect"}
    if ctx.plausibility_gate:
        offending |= {l for l in letters if l != key and plaus[l] < MIN_PLAUSIBILITY}
    facts: Dict[str, str] = {}
    if not offending and ctx.fact_check:
        facts = factcheck_options(llm, item, ctx.text, display, options, key)
        offending |= {l for l, v in facts.items() if v != "ok"}
    return labels, natural, plaus, facts, offending, True


def validate(llm: LLM, item: dict, ctx: "PassageContext", display: str,
             content: Dict[str, str], key: str, new_letters: set, screened: bool = False):
    """Window judge + naturalness and plausibility (new options only) + whole-passage fact
    check. Returns (labels, natural, plaus, facts, offending_letters, key_ok).

    ``screened``: the new options already passed the candidate screen, so their naturalness
    and plausibility are NOT re-judged here (each candidate is scored once; re-rating made
    the same option flip between 3 and 2). Correctness is still re-checked in context of
    the full set, and the fact check runs as usual."""
    labels, natural, plaus = judge_options(llm, item, display, content)
    if labels.get(key) != "correct":
        return labels, natural, plaus, {}, set(), False
    offending = {l for l, lab in labels.items() if l != key and lab != "incorrect"}
    if not screened:
        offending |= {l for l in new_letters if not natural.get(l, True)}
        offending |= {l for l in new_letters if plaus.get(l, 3) < MIN_PLAUSIBILITY}
    facts: Dict[str, str] = {}
    if not offending and ctx.fact_check:
        facts = factcheck_options(llm, item, ctx.text, display, content, key)
        offending |= {l for l, v in facts.items() if v != "ok"}
    return labels, natural, plaus, facts, offending, True


def rebalance_item(item: dict, ctx: PassageContext, llm: Optional[LLM], *,
                   tolerance: float = DEFAULT_TOLERANCE, n_candidates: int = DEFAULT_CANDIDATES,
                   max_rounds: int = DEFAULT_MAX_ROUNDS) -> ItemResult:
    item_id = str(item.get("passage_id") or item.get("id") or "")
    key = key_letter(item)
    options = content_options(item)
    window = ctx.window_for(item)
    base = dict(item_id=item_id, old_options=options, window=window)
    if key not in options or len(options) < 2:
        return ItemResult(status="skipped", reason="no key/options", before={}, **base)
    if not window:
        return ItemResult(status="skipped", reason="window not found in passage", before={}, **base)
    before = measure(options, key, window)
    kind = classify(before, tolerance)
    if llm is None:
        return ItemResult(status="measured", reason=kind, before=before, **base)

    display = ctx.display_window_for(item)
    # 1. audit the CURRENT options (every item) with the SAME screening prompt new candidates
    #    get, so existing and new options are scored on one scale; then the fact check
    labels, natural, plaus, facts, offending, key_ok = audit_existing(
        llm, item, ctx, display, options, key)
    if not key_ok:
        return ItemResult(status="needs_review", reason="validator does not support the key",
                          before=before, judge=labels, natural=natural, plausibility=plaus,
                          **base)
    if not offending and kind in ("balanced", "distractor_dominates"):
        reason = ("balanced and validated" if kind == "balanced"
                  else "distractor out-overlaps key but validated wrong")
        return ItemResult(status="ok", reason=reason, before=before, judge=labels,
                          natural=natural, plausibility=plaus, facts=facts, **base)
    # plausibility of every text the screen has rated, used by selection
    plaus_by_text = {normalize(options[l]): v for l, v in plaus.items() if l != key}
    # once an item is being rewritten, existing throwaways (rated 1-2) go too (this is what
    # the plausibility gate already enforces; it still applies when the gate is off)
    weak_existing = {l for l, v in plaus.items() if l != key and v < MIN_PLAUSIBILITY}
    if offending:
        kind = "invalid_distractor"

    banned = {normalize(options[l]) for l in offending | weak_existing}
    pool: List[Candidate] = [Candidate(text=v, origin=l) for l, v in options.items() if l != key]
    avoid: List[str] = [options[l] for l in offending]
    generated = 0
    exhausted = False
    answer_type = ""
    screened: Dict[str, dict] = {}
    last = dict(judge=labels, natural=natural, plausibility=plaus, facts=facts)
    for _round in range(max_rounds):
        if generated == 0 or choose_set(item, window, pool, banned, plaus_by_text) is None:
            raw = llm("generate", GENERATE_SYSTEM,
                      generate_user_prompt(item, display, n_candidates, avoid))
            exhausted = exhausted or bool(raw.get("excerpt_exhausted"))
            answer_type = answer_type or str(raw.get("answer_type") or "")
            fresh = clean_candidates(raw.get("candidates") or [], options[key],
                                     [c.text for c in pool], window, answer_type)
            # screen ALL new candidates in one call before choosing: selection then only
            # sees candidates that are wrong, natural and plausible, scored once
            for text, verdict in screen_candidates(llm, item, display, fresh).items():
                screened[normalize(text)] = verdict
                plaus_by_text[normalize(text)] = verdict["plausibility"]
                if not screen_passes(verdict):
                    banned.add(normalize(text))
                    avoid.append(text)
            pool += fresh
            generated += 1
        chosen = choose_set(item, window, pool, banned, plaus_by_text)
        if chosen is None:
            break
        proposal = assign_letters(item, chosen)
        content = {l: v for l, v in proposal.items() if l in CONTENT_LETTERS}
        new_letters = {l for l in content if l != key and content[l] != options.get(l)}
        labels, natural, plaus, facts, offending, key_ok = validate(
            llm, item, ctx, display, content, key, new_letters, screened=True)
        for l in new_letters:          # report the screened (single) scores for new options
            verdict = screened.get(normalize(content[l]))
            if verdict:
                plaus[l], natural[l] = verdict["plausibility"], verdict["natural"]
        last = dict(judge=labels, natural=natural, plausibility=plaus, facts=facts)
        if not key_ok:
            return ItemResult(status="needs_review", reason="validator does not support the key",
                              before=before, **last, **base)
        if offending:
            banned |= {normalize(content[l]) for l in offending}
            avoid += [content[l] for l in offending]
            continue
        after = measure(content, key, window)
        notes = {}
        for letter in new_letters:
            cand = next((c for c in chosen if c.text == content[letter]), None)
            if cand:
                notes[letter] = (f"[{cand.kind}] {cand.source}: {cand.why_wrong}"
                                 f" | tempting: {cand.why_tempting}").strip(": ")
        if kind == "invalid_distractor":
            status = "replaced_invalid"
        elif abs(after["gap"]) <= tolerance and after["weakest_gap"] <= WEAKEST_GAP_TOLERANCE:
            status = "rebalanced"
        elif worst_gap(after) <= worst_gap(before) - MIN_IMPROVEMENT:
            # partial only when the WORSE of the two gaps improved: fixing the best
            # distractor while leaving throwaways behind is not an improvement
            status = "partial"
        else:
            return ItemResult(status="needs_review", reason="no validated set improves the gap",
                              before=before, after=after, **last,
                              **{**base, "new_options": content})
        if exhausted:
            notes["*"] = "generator: excerpt has no more suitable phrases"
        return ItemResult(status=status, reason=kind, before=before, after=after,
                          notes=notes, **last, **{**base, "new_options": content})
    reason = ("an invalid distractor could not be replaced" if kind == "invalid_distractor"
              else "candidates exhausted (every set had a rejected distractor)")
    return ItemResult(status="needs_review", reason=reason, before=before, **last, **base)


# ------------------------------------------------------------------------ apply/report
def provenance(args_like: dict) -> dict:
    return {"date": _dt.date.today().isoformat(), **args_like}


def apply_to_records(records: List[dict], results: Dict[str, ItemResult], meta: dict) -> int:
    """Replace options in-place on records whose id and CURRENT options match the result."""
    changed = 0
    for record in records:
        if record.get("q_type") != "mcq":
            continue
        result = results.get(str(record.get("passage_id") or record.get("id") or ""))
        if not result or not result.changed or not result.new_options:
            continue
        options = record.get("A")
        if not isinstance(options, dict) or content_options(record) != result.old_options:
            continue          # already edited by hand, or a different copy -- leave it
        replaced = {}
        for letter, text in result.new_options.items():
            if options.get(letter) != text:
                replaced[letter] = {"old": options.get(letter), "new": text}
                options[letter] = text
        if replaced:
            record["option_rebalance"] = {**meta, "status": result.status, "replaced": replaced}
            changed += 1
    return changed


def backup_once(path: Path) -> None:
    backup = path.with_name(f"{path.name}.{BACKUP_TAG}_{_dt.date.today():%Y-%m-%d}")
    if not backup.exists():
        shutil.copy2(path, backup)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


REPORT_FIELDS = ["passage", "item", "status", "reason", "question", "key", "key_text",
                 "key_overlap", "best_distractor_before", "gap_before", "best_distractor_after",
                 "gap_after", "weakest_gap_before", "weakest_gap_after",
                 "old_A", "old_B", "old_C", "old_D", "new_A", "new_B", "new_C",
                 "new_D", "judge", "plausibility", "unnatural", "fact_check", "new_option_notes",
                 "key_proposal_status", "proposed_key", "proposed_options", "key_proposal_note",
                 "window"]


def report_row(passage: str, item: dict, result: ItemResult) -> dict:
    key = key_letter(item)
    fmt = lambda opts, stats, l: (f"{opts[l]} ({stats['ratios'][l]:.2f})"
                                  if opts and stats and l in opts else "")
    row = {
        "passage": passage, "item": result.item_id, "status": result.status,
        "reason": result.reason, "question": item.get("Q"), "key": key,
        "key_text": result.old_options.get(key, ""),
        "key_overlap": f"{result.before.get('key', 0):.2f}" if result.before else "",
        "best_distractor_before": f"{result.before['best_distractor']:.2f}" if result.before else "",
        "gap_before": f"{result.before['gap']:+.2f}" if result.before else "",
        "best_distractor_after": f"{result.after['best_distractor']:.2f}" if result.after else "",
        "gap_after": f"{result.after['gap']:+.2f}" if result.after else "",
        "weakest_gap_before": f"{result.before['weakest_gap']:+.2f}" if result.before else "",
        "weakest_gap_after": f"{result.after['weakest_gap']:+.2f}" if result.after else "",
        "judge": " ".join(f"{l}:{v}" for l, v in sorted(result.judge.items())),
        "unnatural": " ".join(l for l, ok in sorted(result.natural.items()) if not ok),
        "plausibility": " ".join(f"{l}:{v}" for l, v in sorted(result.plausibility.items())
                                 if l != key),
        "fact_check": " ".join(f"{l}:{v}" for l, v in sorted(result.facts.items()) if v != "ok"),
        "new_option_notes": " | ".join(f"{l}: {v}" for l, v in sorted(result.notes.items())),
        "window": result.window,
        "key_proposal_status": (result.proposal or {}).get("status", ""),
        "proposed_key": ((result.proposal or {}).get("key", "")
                         + (f" ({result.proposal['key_overlap']:.2f})"
                            if (result.proposal or {}).get("key_overlap") is not None else "")),
        "proposed_options": " | ".join(f"{l}:{v}" for l, v in sorted(
            ((result.proposal or {}).get("options") or {}).items())),
        "key_proposal_note": (result.proposal or {}).get("note", "") or (
            f"gap {result.proposal['gap']:+.2f}, weakest {result.proposal['weakest_gap']:+.2f}"
            if result.proposal and "gap" in result.proposal else ""),
    }
    for l in CONTENT_LETTERS:
        row[f"old_{l}"] = fmt(result.old_options, result.before, l)
        row[f"new_{l}"] = (fmt(result.new_options, result.after, l)
                           if result.new_options and result.after else "")
    return row


def write_report(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def summarize(results: List[ItemResult]) -> str:
    from collections import Counter
    counts = Counter(r.status for r in results)
    measured = [r for r in results if r.before]
    flagged = [r for r in measured if r.reason not in ("balanced", "balanced and validated")]
    lines = [f"items: {len(results)}  measured: {len(measured)}  flagged: {len(flagged)}",
             "status: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    proposals = Counter((r.proposal or {}).get("status") for r in results if r.proposal)
    if proposals:
        lines.append("key-rewording proposals (report only): "
                     + ", ".join(f"{k}={v}" for k, v in sorted(proposals.items())))
    if measured:
        gaps = [abs((r.after or r.before)["gap"]) for r in measured]
        lead2 = [(r.after or r.before)["weakest_gap"] for r in measured]
        lines.append(f"mean |gap| after: {sum(gaps)/len(gaps):.3f}  "
                     f"within tolerance: {sum(g <= DEFAULT_TOLERANCE for g in gaps)}/{len(gaps)}  "
                     f"uneven (weakest distractor > {WEAKEST_GAP_TOLERANCE} below key): "
                     f"{sum(g > WEAKEST_GAP_TOLERANCE for g in lead2)}")
    return "\n".join(lines)


VERBATIM_KEY = 0.8
REWORDING_ELIGIBLE = ("no validated set improves the gap",
                      "candidates exhausted (every set had a rejected distractor)")


def rewording_cost(text: str, window: str, target: float, ref_len: int, fluency: int) -> float:
    """Lower is better: near the overlap target, fluent, about the options' length, one clause."""
    cost = abs(overlap_ratio(text, window) - target)
    cost += 0.1 * (5 - fluency)
    cost += 0.5 * abs(math.log(max(len(normalize(text)), 1) / ref_len))
    cost += 0.2 * ("，" in text or "," in text)
    return cost


def needs_key_rewording(result: ItemResult) -> bool:
    """The item could not be balanced AND its key is copied from the window: the
    recognition cue lives in the key itself, which only a reworded key can remove."""
    return (result.status == "needs_review" and result.reason in REWORDING_ELIGIBLE
            and bool(result.before) and result.before.get("key", 0.0) >= VERBATIM_KEY)


def propose_key_rewording(item: dict, ctx: PassageContext, llm: LLM, result: ItemResult,
                          n: int = 4, **kw) -> dict:
    """REPORT-ONLY. Reword a verbatim key, check it blind (still correct, natural) and
    against the original (same meaning), pick the rewording whose overlap is nearest the
    distractors', and rebalance the distractors against it. Nothing is written to QA files.

    Returns {"status": proposed|no_valid_rewording|rebalance_failed, "key": ..., ...}."""
    key = key_letter(item)
    options = content_options(item)
    original = options[key]
    display = ctx.display_window_for(item)
    window = ctx.window_for(item)
    raw = llm("keygen", KEYGEN_SYSTEM, json.dumps({
        "excerpt": display, "question": item.get("Q"), "correct_answer": original,
        "number_of_rewordings": n}, ensure_ascii=False, indent=1))
    ends = normalize(original).endswith(("。", "."))
    texts, seen = [], {normalize(original)}
    for entry in raw.get("rewordings") or []:
        text = tidy_option(str((entry or {}).get("text") or ""), ends)
        if text and normalize(text) not in seen and overlap_ratio(text, window) < VERBATIM_KEY:
            seen.add(normalize(text))
            texts.append(text)
    if not texts:
        return {"status": "no_valid_rewording", "note": "every rewording still copied the window"}

    # 1) blind: is each rewording, on its own, a correct and natural answer?
    blind = screen_candidates(llm, item, display, [Candidate(t, "new") for t in texts])
    # 2) against the original: same meaning, not narrower/broader?
    check = llm("keycheck", KEYCHECK_SYSTEM, json.dumps({
        "excerpt": display, "question": item.get("Q"), "original_correct_answer": original,
        "rewordings": {f"r{i + 1}": t for i, t in enumerate(texts)}}, ensure_ascii=False, indent=1))
    same, fluency = {}, {}
    for entry in check.get("rewordings") or []:
        rid = str(entry.get("id") or "")
        if rid.startswith("r") and rid[1:].isdigit() and int(rid[1:]) <= len(texts):
            text = texts[int(rid[1:]) - 1]
            same[text] = (str(entry.get("verdict") or "").lower() == "same"
                          and entry.get("natural") is not False)
            try:
                fluency[text] = max(1, min(5, int(round(float(entry.get("fluency"))))))
            except (TypeError, ValueError):
                fluency[text] = 3
    valid = [t for t in texts if blind.get(t, {}).get("label") == "correct"
             and blind.get(t, {}).get("natural") and same.get(t)]
    if not valid:
        return {"status": "no_valid_rewording", "candidates": texts,
                "note": "no rewording was judged correct, natural and same-meaning"}

    # choose by overlap target AND fluency AND length: the overlap target alone picked the
    # stiffest or longest rewording (耶和华传来的言语 over 耶和华所说的话; a two-clause key
    # longer than every distractor -- "pick the longest option" is its own cue)
    others = [overlap_ratio(v, window) for l, v in options.items() if l != key]
    target = max(0.3, max(others) if others else 0.3)
    lengths = sorted(len(normalize(v)) for v in options.values())
    ref_len = max(lengths[len(lengths) // 2], 1)          # median of key + distractors
    chosen = min(valid, key=lambda t: rewording_cost(t, window, target, ref_len,
                                                     fluency.get(t, 3)))

    # 3) rebalance the distractors against the reworded key (no further key rewording)
    trial = dict(item, A={**item["A"], key: chosen})
    sub_ctx = PassageContext(ctx.text, ctx.reference, ctx.verse_windows, ctx.verse_window,
                             fact_check=ctx.fact_check, key_rewording=False,
                             plausibility_gate=True)   # always: no throwaways in a proposal
    sub = rebalance_item(trial, sub_ctx, llm, **kw)
    proposal = {"key": chosen, "key_overlap": round(overlap_ratio(chosen, window), 2),
                "key_fluency": fluency.get(chosen), "fluency": fluency,
                "original_key": original, "candidates": texts, "valid": valid,
                "sub_status": sub.status, "sub_reason": sub.reason}
    if sub.status in ("rebalanced", "partial", "replaced_invalid", "ok"):
        opts = sub.new_options or {l: v for l, v in trial["A"].items() if l in CONTENT_LETTERS}
        stats = sub.after or sub.before
        balanced = (abs(stats["gap"]) <= kw.get("tolerance", DEFAULT_TOLERANCE)
                    and stats["weakest_gap"] <= WEAKEST_GAP_TOLERANCE)
        # a reworded key far BELOW verbatim distractors is the reverse cue ("pick the one
        # that is not copied"): still reported, but flagged
        proposal.update(status="proposed" if balanced else "proposed_unbalanced", options=opts,
                        gap=round(stats["gap"], 2), weakest_gap=round(stats["weakest_gap"], 2),
                        plausibility=sub.plausibility, notes=sub.notes)
    else:
        proposal.update(status="rebalance_failed",
                        note="reworded key accepted, but distractors still could not be balanced")
    return proposal


def process_item(record: dict, ctx: PassageContext, llm: Optional[LLM], **kw) -> ItemResult:
    result = rebalance_item(record, ctx, llm, **kw)
    if llm is not None and ctx.key_rewording and needs_key_rewording(result):
        try:
            result.proposal = propose_key_rewording(record, ctx, llm, result, **kw)
        except RebalanceError as exc:
            result.proposal = {"status": "error", "note": str(exc)}
    return result


def rebalance_records(records: List[dict], ctx: PassageContext, llm: Optional[LLM],
                      workers: int = 1, **kw) -> List[tuple]:
    """Process every MCQ; ``workers`` > 1 runs items concurrently (order is preserved)."""
    todo = [r for r in records if r.get("q_type") == "mcq" and r.get("status") != "exclude"]
    if workers <= 1 or llm is None or len(todo) < 2:
        return [(r, process_item(r, ctx, llm, **kw)) for r in todo]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda r: process_item(r, ctx, llm, **kw), todo))
    return list(zip(todo, results))


# --------------------------------------------------------------------------- CLI
def _load_text(directory: Path, names: Sequence[str]) -> Optional[Path]:
    return next((directory / n for n in names if (directory / n).exists()), None)


def sync_copies(root: Path, pid: str, reference_dir: str) -> int:
    """Make every qa_target*.json copy under a passage carry the reference copy's MCQ options.

    Copies are matched by FILE NAME (qa_target.json <- reference qa_target.json, and the
    same for the decanonicalized file), so a pseudonymized tree never receives
    canonical-name text. Returns the number of files written.
    """
    written = 0
    for name in ("qa_target.json", "qa_target_decanonicalized.json"):
        ref_path = root / pid / reference_dir / name
        if not ref_path.exists():
            continue
        ref = {str(r.get("passage_id")): r for r in json.loads(ref_path.read_text(encoding="utf-8"))
               if r.get("q_type") == "mcq"}
        for path in sorted((root / pid).rglob(name)):
            if path == ref_path:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            dirty = False
            for record in data:
                src = ref.get(str(record.get("passage_id")))
                if (src and record.get("q_type") == "mcq" and record.get("correct") == src.get("correct")
                        and record.get("A") != src.get("A")):
                    record["A"] = dict(src["A"])
                    if "option_rebalance" in src:
                        record["option_rebalance"] = src["option_rebalance"]
                    dirty = True
            if dirty:
                backup_once(path)
                write_json(path, data)
                written += 1
    return written


def run_tier1(args, llm: Optional[LLM], meta: dict) -> List[dict]:
    root = args.tier1_root.expanduser()
    verse_windows = load_verse_windows(args.windows_json) if args.windows_json else None
    rows, all_results = [], []
    passages = sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("t1_"))
    if args.passages:
        passages = [p for p in passages if p in set(args.passages)]
    for pid in passages:
        ref_dir = root / pid / args.reference_dir
        passage_path = _load_text(ref_dir, ("passage_target_decanonicalized.txt", "passage_target.txt"))
        if passage_path is None:
            print(f"  ! {pid}: no passage in {ref_dir}", file=sys.stderr)
            continue
        if args.qa_dir:
            qa_path = args.qa_dir / f"{pid}.json"
        else:
            qa_path = _load_text(ref_dir, ("qa_target_decanonicalized.json", "qa_target.json"))
        if qa_path is None or not qa_path.exists():
            print(f"  ! {pid}: no QA file", file=sys.stderr)
            continue
        records = json.loads(qa_path.read_text(encoding="utf-8"))
        reference = next((r.get("passage_reference") for r in records if r.get("passage_reference")), "")
        ctx = PassageContext(passage_path.read_text(encoding="utf-8"), reference, verse_windows,
                             args.verse_window, fact_check=not args.no_fact_check,
                             key_rewording=not args.no_key_rewording,
                             plausibility_gate=not args.no_plausibility_gate)
        pairs = rebalance_records(records, ctx, llm, workers=args.workers,
                                  tolerance=args.tolerance,
                                  n_candidates=args.candidates, max_rounds=args.max_rounds)
        results = {r.item_id: r for _, r in pairs}
        all_results += [r for _, r in pairs]
        rows += [report_row(pid, rec, res) for rec, res in pairs]
        if args.apply and any(r.changed for r in results.values()):
            targets = ([qa_path] if args.qa_dir else
                       sorted(p for p in (root / pid).rglob("qa_target*.json")))
            n_files = 0
            for path in targets:
                data = json.loads(path.read_text(encoding="utf-8"))
                if apply_to_records(data, results, meta):
                    backup_once(path)
                    write_json(path, data)
                    n_files += 1
            print(f"  {pid}: {sum(r.changed for r in results.values())} items rebalanced, "
                  f"{n_files} files written")
        if args.sync and not args.qa_dir:
            n = sync_copies(root, pid, args.reference_dir)
            if n:
                print(f"  {pid}: synced reference options into {n} other qa_target files")
    print(summarize(all_results))
    return rows


def run_file(args, llm: Optional[LLM], meta: dict) -> List[dict]:
    records = json.loads(args.qa_json.read_text(encoding="utf-8"))
    verse_windows = load_verse_windows(args.windows_json) if args.windows_json else None
    reference = next((r.get("passage_reference") for r in records if r.get("passage_reference")), "")
    ctx = PassageContext(args.passage.read_text(encoding="utf-8"), reference, verse_windows,
                         args.verse_window, fact_check=not args.no_fact_check,
                         key_rewording=not args.no_key_rewording,
                         plausibility_gate=not args.no_plausibility_gate)
    pairs = rebalance_records(records, ctx, llm, workers=args.workers, tolerance=args.tolerance,
                              n_candidates=args.candidates, max_rounds=args.max_rounds)
    results = {r.item_id: r for _, r in pairs}
    out = args.out or args.qa_json
    if args.apply or args.out:
        if apply_to_records(records, results, meta):
            if out.exists():
                backup_once(out)
            write_json(out, records)
    print(summarize([r for _, r in pairs]))
    return [report_row(args.qa_json.stem, rec, res) for rec, res in pairs]


def rebalance_qa_file(qa_path: Path, passage_path: Path, report_path: Path, *,
                      windows_json: Optional[Path] = None, verse_window: int = 2,
                      generator_model: str = DEFAULT_GENERATOR_MODEL,
                      judge_model: str = DEFAULT_JUDGE_MODEL, effort: Optional[str] = DEFAULT_EFFORT,
                      tolerance: float = DEFAULT_TOLERANCE, retries: int = 2,
                      workers: int = 4, fact_check: bool = True,
                      llm: Optional[LLM] = None) -> int:
    """Library entry point for main.py: rebalance one QA file in place. Returns #items changed."""
    records = json.loads(qa_path.read_text(encoding="utf-8"))
    verse_windows = load_verse_windows(windows_json) if windows_json else None
    reference = next((r.get("passage_reference") for r in records if r.get("passage_reference")), "")
    ctx = PassageContext(passage_path.read_text(encoding="utf-8"), reference, verse_windows,
                         verse_window, fact_check=fact_check)
    llm = llm or openai_llm(generator_model, judge_model, effort, retries)
    pairs = rebalance_records(records, ctx, llm, workers=workers, tolerance=tolerance)
    meta = provenance({"generator_model": generator_model, "judge_model": judge_model,
                       "effort": effort, "tolerance": tolerance})
    changed = apply_to_records(records, {r.item_id: r for _, r in pairs}, meta)
    if changed:
        backup_once(qa_path)
        write_json(qa_path, records)
    write_report(report_path, [report_row(qa_path.stem, rec, res) for rec, res in pairs])
    print(summarize([r for _, r in pairs]))
    return changed


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--report", type=Path, required=True, help="review CSV to write")
    common.add_argument("--windows-json", type=Path,
                        help="curated per-question windows (tier1_qa_verse_windows_canonical.json)")
    common.add_argument("--verse-window", type=int, default=2,
                        help="+/- verses around the item reference when no curated window (default 2)")
    common.add_argument("--generator-model", default=DEFAULT_GENERATOR_MODEL)
    common.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    common.add_argument("--effort", default=DEFAULT_EFFORT,
                        help="reasoning effort for both models (low..max); '' to omit")
    common.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    common.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES)
    common.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    common.add_argument("--retries", type=int, default=2)
    common.add_argument("--workers", type=int, default=4, help="items processed concurrently")
    common.add_argument("--no-plausibility-gate", action="store_true",
                        help="do not fail items whose EXISTING distractors are rated 1-2 "
                             "(they are then only reported); key-rewording proposals always "
                             "apply the gate")
    common.add_argument("--no-key-rewording", action="store_true",
                        help="do not propose rewordings for verbatim keys of items that could "
                             "not be balanced (proposals are report-only either way)")
    common.add_argument("--no-fact-check", action="store_true",
                        help="skip the whole-passage check for distractors that are true "
                             "elsewhere in the passage / another name for the key")
    common.add_argument("--measure-only", action="store_true",
                        help="no API calls: measure and report which items would be rebalanced")
    common.add_argument("--apply", action="store_true",
                        help="write changes (default is a dry run that only writes the report)")

    t = sub.add_parser("tier1", parents=[common], help="a tier-1 corpus tree")
    t.add_argument("--tier1-root", type=Path, required=True)
    t.add_argument("--reference-dir", default="omission/0%",
                   help="per-passage dir holding the reference passage (+ QA unless --qa-dir)")
    t.add_argument("--qa-dir", type=Path,
                   help="per-passage QA files <pid>.json (hard66 layout); only these are written")
    t.add_argument("--passages", nargs="+", help="limit to these passage ids")
    t.add_argument("--sync", action="store_true",
                   help="also copy the reference dir's MCQ options into every other "
                        "qa_target*.json of the passage (same file name only); fixes copies "
                        "left behind by hand edits")

    f = sub.add_parser("file", parents=[common], help="one QA file against one passage")
    f.add_argument("--qa-json", type=Path, required=True)
    f.add_argument("--passage", type=Path, required=True)
    f.add_argument("--out", type=Path, help="write here instead of in place (implies --apply)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    effort = args.effort or None
    llm = None if args.measure_only else openai_llm(args.generator_model, args.judge_model,
                                                     effort, args.retries)
    meta = provenance({"generator_model": args.generator_model, "judge_model": args.judge_model,
                       "effort": effort, "tolerance": args.tolerance})
    apply_requested = args.apply
    if args.measure_only and args.apply:
        print("--measure-only: no options are rebalanced (only --sync writes)", file=sys.stderr)
        args.apply = False
    if getattr(args, "sync", False) and not apply_requested:
        print("--sync only runs with --apply", file=sys.stderr)
        args.sync = False
    try:
        rows = run_tier1(args, llm, meta) if args.mode == "tier1" else run_file(args, llm, meta)
    except RebalanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    write_report(args.report, rows)
    print(f"report: {args.report}")
    if not args.apply and not args.measure_only:
        print("dry run: nothing written to QA files (pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
