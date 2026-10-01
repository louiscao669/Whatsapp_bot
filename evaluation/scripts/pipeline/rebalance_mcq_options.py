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
  * window check  -- an OpenAI model, BLIND to the key, labels every option correct /
                     incorrect / ambiguous using only the window the respondent sees, and
                     says whether each reads as natural Chinese in the question's form;
  * fact check    -- the same model, given the WHOLE passage, flags wrong options that
                     name the same person/thing as the key or are true answers elsewhere in
                     the passage (respondents who know the story would be marked wrong).
The key must come back "correct". A distractor failing either check is replaced.

Then overlap is measured deterministically (longest contiguous shared span / option
length vs the window, as in ``analysis/current/audit_option_overlap.py``). An item is
rebalanced when the key leads the best distractor by more than --tolerance, or leads the
SECOND-best by more than 0.35 (one verbatim lure plus throwaways is still a recognition
cue):

  1. generate  -- candidates, at least half copied verbatim from the window (true there but
                  wrong for this question), part-swaps for multi-part keys, paraphrases
                  only for inference answers; claimed spans are verified against the window;
  2. select    -- deterministically pick the 3-distractor set whose overlap and length best
                  match the key, penalising a weak runner-up, throwaways, stem echoes and
                  needless changes;
  3. validate  -- window check + naturalness (new options) + fact check; offenders are
                  banned and selection repeats (more candidates are generated if needed);
  4. gate      -- apply when validated and within tolerance ("rebalanced"), improved by
                  >= 0.15 ("partial"), or when an invalid distractor was replaced
                  ("replaced_invalid"); everything else is left unchanged (needs_review).

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
DEFAULT_MAX_ROUNDS = 3
MIN_IMPROVEMENT = 0.15
SECOND_GAP_TOLERANCE = 0.35   # key may lead the 2nd-best distractor by at most this
THROWAWAY_RATIO = 0.15        # a distractor this far from the text is a throwaway
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
            "second_gap": second_gap(k, others)}


def classify(stats: dict, tolerance: float) -> str:
    if stats["gap"] > tolerance:
        return "key_stands_out"
    if stats["key"] >= 0.5 and stats.get("second_gap", 0.0) > SECOND_GAP_TOLERANCE:
        return "single_lure"      # one distractor matches the key, the rest are far off
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

Rules for every candidate:
1. It must be clearly WRONG as an answer to the question, judged using ONLY the excerpt. Not \
partially right, not a synonym, restatement, superset or subset of the correct answer, and not \
another name or description of the same person, place or thing.
2. At least HALF of the candidates must be kind "span": a phrase COPIED VERBATIM (character for \
character) from the excerpt that is true there but does not answer THIS question -- the wrong \
person (someone else in the scene), the wrong time or order (an earlier or later event), the wrong \
place, object or role. Light trimming is fine; rewording is not.
3. If the correct answer lists several parts (e.g. "X和Y"), give at least one kind "swap" candidate \
that keeps one part and replaces the other with something else from the excerpt or the story.
4. Use kind "paraphrase" only for why/how questions whose answer is an inference, or when the \
excerpt offers nothing suitable.
5. Every candidate must read as a natural, grammatical answer to THIS question in Simplified \
Chinese, in the same form as the correct answer (if the answer is a noun phrase, give noun \
phrases; if it is an action the person was told to do, give actions; keep pronouns unambiguous). \
Match the correct answer's punctuation style and approximate length.
6. Do not reuse the question's own subject phrase as an option.
7. Do not propose anything listed under "do_not_propose".

Return a JSON object: {"candidates": [{"text": "...", "kind": "span|swap|paraphrase", \
"source": "verse number it comes from, or 'paraphrase'", "why_wrong": "one short sentence"}]}"""

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

Return a JSON object: {"options": [{"letter": "A", "label": "correct|incorrect|ambiguous", \
"natural": true, "reason": "one short sentence"}]}"""

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
    """Responses-API caller. Roles: generate -> generator model; judge and factcheck -> judge
    model. Reasoning models get ``reasoning.effort`` and no temperature; a model that rejects
    ``reasoning`` (classic chat models) is retried at temperature 0. Thread-safe."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    models = {"generate": generator_model, "judge": judge_model, "factcheck": judge_model}
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


def clean_candidates(raw: Sequence[dict], key_text: str, existing: Sequence[str],
                     window: str = "") -> List[Candidate]:
    """Drop restatements of the key and duplicates; re-label kind from the text itself
    (a claimed "span" that is not actually in the window becomes "paraphrase")."""
    out: List[Candidate] = []
    seen = [normalize(t) for t in existing]
    for entry in raw or []:
        text = str((entry or {}).get("text") or "").strip()
        if not text or len(normalize(text)) > 3 * len(normalize(key_text)) + 8:
            continue
        if _similar(text, key_text) >= 0.8:
            continue
        if any(_similar(text, s) >= 0.85 for s in seen):
            continue
        seen.append(normalize(text))
        kind = str(entry.get("kind") or "").strip().lower()
        if window:
            ratio = overlap_ratio(text, window)
            if kind == "span" and ratio < 0.8:
                kind = "paraphrase"
            elif not kind:
                kind = "span" if ratio >= 0.8 else "paraphrase"
        out.append(Candidate(text=text, origin="new", source=str(entry.get("source") or ""),
                             why_wrong=str(entry.get("why_wrong") or ""), kind=kind))
    return out


def second_gap(key_ratio: float, ratios: Sequence[float]) -> float:
    """How far the key leads the SECOND most-overlapping distractor (0 if < 2 distractors)."""
    ranked = sorted(ratios, reverse=True)
    return key_ratio - ranked[1] if len(ranked) > 1 else 0.0


def set_cost(key_ratio: float, key_text: str, stem: str, chosen: Sequence[Candidate],
             window: str) -> float:
    ratios = [overlap_ratio(c.text, window) for c in chosen]
    k_len = max(len(normalize(key_text)), 1)
    cost = abs(key_ratio - max(ratios))
    # one strong lure must not carry the item: the runner-up should be close as well
    cost += 0.6 * max(0.0, second_gap(key_ratio, ratios) - SECOND_GAP_TOLERANCE)
    cost += 0.25 * sum(abs(key_ratio - r) for r in ratios) / len(ratios)
    if key_ratio >= 0.5:      # throwaways (barely in the text) next to a verbatim key
        cost += 0.15 * sum(r < THROWAWAY_RATIO for r in ratios)
    cost += 0.15 * sum(abs(math.log(max(len(normalize(c.text)), 1) / k_len)) for c in chosen) / len(chosen)
    cost += 0.30 * sum(stem_echo(c.text, stem) for c in chosen)
    cost += 0.04 * sum(c.origin == "new" for c in chosen)
    return cost


def choose_set(item: dict, window: str, pool: Sequence[Candidate], banned: set) -> Optional[List[Candidate]]:
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
        cost = set_cost(key_ratio, key_text, item.get("Q") or "", combo, window)
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
    facts: Dict[str, str] = field(default_factory=dict)
    notes: Dict[str, str] = field(default_factory=dict)
    window: str = ""

    @property
    def changed(self) -> bool:
        return self.status in ("rebalanced", "partial", "replaced_invalid")


def judge_options(llm: LLM, item: dict, window_text: str, options: Dict[str, str]):
    """Blind window check: ({letter: label}, {letter: natural})."""
    raw = llm("judge", JUDGE_SYSTEM, judge_user_prompt(item, window_text, options))
    labels, natural = {}, {}
    for entry in raw.get("options") or []:
        letter = str(entry.get("letter") or "").strip()[:1].upper()
        if letter not in options:
            continue
        label = str(entry.get("label") or "").strip().lower()
        labels[letter] = label if label in ("correct", "incorrect", "ambiguous") else "ambiguous"
        natural[letter] = entry.get("natural") is not False
    for letter in options:
        labels.setdefault(letter, "ambiguous")   # a missing verdict never passes
        natural.setdefault(letter, True)
    return labels, natural


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


def validate(llm: LLM, item: dict, ctx: "PassageContext", display: str,
             content: Dict[str, str], key: str, new_letters: set):
    """Window judge + naturalness (new options only) + whole-passage fact check.
    Returns (labels, natural, facts, offending_letters, key_ok)."""
    labels, natural = judge_options(llm, item, display, content)
    if labels.get(key) != "correct":
        return labels, natural, {}, set(), False
    offending = {l for l, lab in labels.items() if l != key and lab != "incorrect"}
    offending |= {l for l in new_letters if not natural.get(l, True)}
    facts: Dict[str, str] = {}
    if not offending and ctx.fact_check:
        facts = factcheck_options(llm, item, ctx.text, display, content, key)
        offending |= {l for l, v in facts.items() if v != "ok"}
    return labels, natural, facts, offending, True


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
    # 1. audit the CURRENT options (every item): window judge + whole-passage fact check
    labels, natural, facts, offending, key_ok = validate(
        llm, item, ctx, display, options, key, new_letters=set())
    if not key_ok:
        return ItemResult(status="needs_review", reason="validator does not support the key",
                          before=before, judge=labels, natural=natural, **base)
    if not offending and kind in ("balanced", "distractor_dominates"):
        reason = ("balanced and validated" if kind == "balanced"
                  else "distractor out-overlaps key but validated wrong")
        return ItemResult(status="ok", reason=reason, before=before,
                          judge=labels, natural=natural, facts=facts, **base)
    if offending:
        kind = "invalid_distractor"

    banned = {normalize(options[l]) for l in offending}
    pool: List[Candidate] = [Candidate(text=v, origin=l) for l, v in options.items() if l != key]
    avoid: List[str] = [options[l] for l in offending]
    generated = 0
    last = dict(judge=labels, natural=natural, facts=facts)
    for _round in range(max_rounds):
        if generated == 0 or choose_set(item, window, pool, banned) is None:
            raw = llm("generate", GENERATE_SYSTEM,
                      generate_user_prompt(item, display, n_candidates, avoid))
            pool += clean_candidates(raw.get("candidates") or [], options[key],
                                     [c.text for c in pool], window)
            generated += 1
        chosen = choose_set(item, window, pool, banned)
        if chosen is None:
            break
        proposal = assign_letters(item, chosen)
        content = {l: v for l, v in proposal.items() if l in CONTENT_LETTERS}
        new_letters = {l for l in content if l != key and content[l] != options.get(l)}
        labels, natural, facts, offending, key_ok = validate(
            llm, item, ctx, display, content, key, new_letters)
        last = dict(judge=labels, natural=natural, facts=facts)
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
                notes[letter] = f"[{cand.kind}] {cand.source}: {cand.why_wrong}".strip(": ")
        lead2 = second_gap(after["key"], [r for l, r in after["ratios"].items() if l != key])
        if kind == "invalid_distractor":
            status = "replaced_invalid"
        elif abs(after["gap"]) <= tolerance and lead2 <= SECOND_GAP_TOLERANCE:
            status = "rebalanced"
        elif abs(after["gap"]) <= abs(before["gap"]) - MIN_IMPROVEMENT or (
                abs(after["gap"]) <= tolerance and new_letters):
            status = "partial"
        else:
            return ItemResult(status="needs_review", reason="no validated set improves the gap",
                              before=before, after=after, **last,
                              **{**base, "new_options": content})
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
                 "gap_after", "second_gap_before", "second_gap_after",
                 "old_A", "old_B", "old_C", "old_D", "new_A", "new_B", "new_C",
                 "new_D", "judge", "unnatural", "fact_check", "new_option_notes", "window"]


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
        "second_gap_before": f"{result.before['second_gap']:+.2f}" if result.before else "",
        "second_gap_after": f"{result.after['second_gap']:+.2f}" if result.after else "",
        "judge": " ".join(f"{l}:{v}" for l, v in sorted(result.judge.items())),
        "unnatural": " ".join(l for l, ok in sorted(result.natural.items()) if not ok),
        "fact_check": " ".join(f"{l}:{v}" for l, v in sorted(result.facts.items()) if v != "ok"),
        "new_option_notes": " | ".join(f"{l}: {v}" for l, v in sorted(result.notes.items())),
        "window": result.window,
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
    if measured:
        gaps = [abs((r.after or r.before)["gap"]) for r in measured]
        lead2 = [(r.after or r.before)["second_gap"] for r in measured]
        lines.append(f"mean |gap| after: {sum(gaps)/len(gaps):.3f}  "
                     f"within tolerance: {sum(g <= DEFAULT_TOLERANCE for g in gaps)}/{len(gaps)}  "
                     f"single-lure (2nd gap > {SECOND_GAP_TOLERANCE}): "
                     f"{sum(g > SECOND_GAP_TOLERANCE for g in lead2)}")
    return "\n".join(lines)


def rebalance_records(records: List[dict], ctx: PassageContext, llm: Optional[LLM],
                      workers: int = 1, **kw) -> List[tuple]:
    """Process every MCQ; ``workers`` > 1 runs items concurrently (order is preserved)."""
    todo = [r for r in records if r.get("q_type") == "mcq" and r.get("status") != "exclude"]
    if workers <= 1 or llm is None or len(todo) < 2:
        return [(r, rebalance_item(r, ctx, llm, **kw)) for r in todo]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda r: rebalance_item(r, ctx, llm, **kw), todo))
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
                             args.verse_window, fact_check=not args.no_fact_check)
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
                         args.verse_window, fact_check=not args.no_fact_check)
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
