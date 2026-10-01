#!/usr/bin/env python3
"""Rebalance MCQ options so the key does not stand out by verbatim overlap with its window.

WHY. A respondent can answer an MCQ without understanding it by picking the option that
is lifted most completely from the text they just read. Measured 2026-09-30: model
accuracy rises with the key's overlap margin over its best distractor (r = +0.12 gold72,
+0.22 hard66), and wrong answers land on the highest-overlap distractor above chance.
The property is NOT translation-invariant (Chinese Bible register collapses English
paraphrases onto the passage's wording), so it has to be fixed on the TARGET-language
QA, against the window the respondent actually sees.

WHAT. Per MCQ, deterministically measure each content option's overlap with its window
(longest contiguous shared span / option length -- the same metric as
``analysis/current/audit_option_overlap.py``). Items whose key stands out
(key - best distractor > --tolerance) are rebalanced:

  1. generate  -- an OpenAI model proposes candidate distractors, preferably phrases
                  from the same window that are true in the passage but wrong for this
                  question (wrong person / time / role), matching the key's form;
  2. select    -- deterministically choose the 3-distractor set whose overlap and length
                  best match the key, penalising stem echoes and needless changes;
  3. validate  -- a second OpenAI call, BLIND to the key, labels every option
                  correct / incorrect / ambiguous using only the window. The key must
                  come back correct and every distractor incorrect; offending
                  candidates are banned and selection repeats;
  4. gate      -- apply only when validated and the gap is within tolerance
                  ("rebalanced") or improved by >= 0.15 ("partial"); everything else
                  is left unchanged and reported as needs_review.

Items where a distractor out-overlaps the key by more than the tolerance get the blind
validation only (that is where a second correct answer hides); a distractor judged
correct/ambiguous is replaced through the same loop.

Never changed: the key's text and letter, option E (the meta-option), the open form,
items with status "exclude". Every change is recorded on the item (``option_rebalance``)
and in a review CSV, which a human should skim before import: the validator lowers but
does not remove the risk of a second correct answer (e.g. an alias of the key known only
from outside the window).

Models: OpenAI only. Defaults ``gpt-6.1-sol`` (generate) and ``gpt-6-astra`` (validate),
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
DEFAULT_CANDIDATES = 8
DEFAULT_MAX_ROUNDS = 3
MIN_IMPROVEMENT = 0.15
BACKUP_TAG = "bak_rebalance"

# LLM interface: (role, system, user) -> parsed JSON object. role is "generate"/"judge".
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
    return {"ratios": ratios, "key": ratios.get(key, 0.0), "best_distractor": best,
            "gap": ratios.get(key, 0.0) - best}


def classify(stats: dict, tolerance: float) -> str:
    if stats["gap"] > tolerance:
        return "key_stands_out"
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
another name for the same person, place or thing.
2. Prefer phrases that APPEAR in the excerpt and are true there, but do not answer THIS question: \
the wrong person (someone else in the scene), the wrong time or order (an earlier or later event), \
the wrong place, object or role. Copy such phrases verbatim from the excerpt where natural. For \
why/how questions whose answer is an inference, write plausible paraphrase-style wrong reasons \
instead.
3. Match the correct answer's grammatical form, punctuation style and approximate length, so form \
does not give the answer away.
4. Do not reuse the question's own subject phrase as an option (it can be ruled out from the \
question alone).
5. Do not depend on knowledge from outside the excerpt. Avoid names that are absent from the \
excerpt unless it offers no suitable alternatives.
6. Natural Simplified Chinese in the register of the excerpt.

Return a JSON object: {"candidates": [{"text": "...", "source": "verse number it comes from, or \
'paraphrase'", "why_wrong": "one short sentence"}]}"""

JUDGE_SYSTEM = """You check multiple-choice reading-comprehension items. Using ONLY the excerpt \
(no outside knowledge), decide for EACH option whether it is a correct answer to the question:
- "correct": the excerpt supports it as an answer to the question;
- "incorrect": the excerpt shows it does not answer the question, or it answers a different question;
- "ambiguous": a careful reader could reasonably defend it as correct from the excerpt.
More than one option may be correct. Judge each option on its own.

Return a JSON object: {"options": [{"letter": "A", "label": "correct|incorrect|ambiguous", \
"reason": "one short sentence"}]}"""


def generate_user_prompt(item: dict, window_text: str, n: int) -> str:
    key = key_letter(item)
    options = content_options(item)
    return json.dumps({
        "excerpt": window_text,
        "question": item.get("Q"),
        "correct_answer": options.get(key),
        "current_wrong_options": [v for k, v in options.items() if k != key],
        "number_of_candidates": n,
    }, ensure_ascii=False, indent=1)


def judge_user_prompt(item: dict, window_text: str, options: Dict[str, str]) -> str:
    return json.dumps({
        "excerpt": window_text,
        "question": item.get("Q"),
        "options": {k: options[k] for k in sorted(options)},
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
    """Responses-API caller. Reasoning models get ``reasoning.effort`` and no temperature;
    if a model rejects ``reasoning`` (classic chat models) it is retried at temperature 0."""
    if client is None:
        from openai import OpenAI
        client = OpenAI()
    models = {"generate": generator_model, "judge": judge_model}
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


def clean_candidates(raw: Sequence[dict], key_text: str, existing: Sequence[str]) -> List[Candidate]:
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
        out.append(Candidate(text=text, origin="new", source=str(entry.get("source") or ""),
                             why_wrong=str(entry.get("why_wrong") or "")))
    return out


def set_cost(key_ratio: float, key_text: str, stem: str, chosen: Sequence[Candidate],
             window: str) -> float:
    ratios = [overlap_ratio(c.text, window) for c in chosen]
    k_len = max(len(normalize(key_text)), 1)
    cost = abs(key_ratio - max(ratios))
    cost += 0.25 * sum(abs(key_ratio - r) for r in ratios) / len(ratios)
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
    notes: Dict[str, str] = field(default_factory=dict)
    window: str = ""

    @property
    def changed(self) -> bool:
        return self.status in ("rebalanced", "partial", "replaced_second_correct")


def judge_labels(llm: LLM, item: dict, window_text: str, options: Dict[str, str]) -> Dict[str, str]:
    raw = llm("judge", JUDGE_SYSTEM, judge_user_prompt(item, window_text, options))
    labels = {}
    for entry in raw.get("options") or []:
        letter = str(entry.get("letter") or "").strip()[:1].upper()
        label = str(entry.get("label") or "").strip().lower()
        if letter in options:
            labels[letter] = label if label in ("correct", "incorrect", "ambiguous") else "ambiguous"
    for letter in options:
        labels.setdefault(letter, "ambiguous")   # a missing verdict never passes
    return labels


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
    if llm is None or kind == "balanced":
        return ItemResult(status="measured" if llm is None else "balanced", reason=kind,
                          before=before, **base)

    display = ctx.display_window_for(item)
    banned: set = set()
    pool: List[Candidate] = [Candidate(text=v, origin=l) for l, v in options.items() if l != key]
    judge: Dict[str, str] = {}

    if kind == "distractor_dominates":
        judge = judge_labels(llm, item, display, options)
        if judge.get(key) != "correct":
            return ItemResult(status="needs_review", reason="validator does not support the key",
                              before=before, judge=judge, **base)
        bad = [l for l, lab in judge.items() if l != key and lab != "incorrect"]
        if not bad:
            return ItemResult(status="checked", reason="distractor out-overlaps key but validated wrong",
                              before=before, judge=judge, **base)
        banned |= {normalize(options[l]) for l in bad}

    generated = 0
    for round_no in range(max_rounds):
        if generated == 0 or choose_set(item, window, pool, banned) is None:
            raw = llm("generate", GENERATE_SYSTEM, generate_user_prompt(item, display, n_candidates))
            pool += clean_candidates(raw.get("candidates") or [], options[key],
                                     [c.text for c in pool])
            generated += 1
        chosen = choose_set(item, window, pool, banned)
        if chosen is None:
            break
        proposal = assign_letters(item, chosen)
        content = {l: v for l, v in proposal.items() if l in CONTENT_LETTERS}
        judge = judge_labels(llm, item, display, content)
        if judge.get(key) != "correct":
            return ItemResult(status="needs_review", reason="validator does not support the key",
                              before=before, judge=judge, **base)
        offending = [l for l, lab in judge.items() if l != key and lab != "incorrect"]
        if offending:
            banned |= {normalize(content[l]) for l in offending}
            continue
        after = measure(content, key, window)
        notes = {}
        for letter in content:
            if letter != key and content[letter] != options.get(letter):
                cand = next((c for c in chosen if c.text == content[letter]), None)
                if cand:
                    notes[letter] = f"{cand.source}: {cand.why_wrong}".strip(": ")
        replaced_bad = kind == "distractor_dominates"
        if abs(after["gap"]) <= tolerance:
            status = "replaced_second_correct" if replaced_bad else "rebalanced"
        elif abs(after["gap"]) <= abs(before["gap"]) - MIN_IMPROVEMENT or replaced_bad:
            status = "replaced_second_correct" if replaced_bad else "partial"
        else:
            return ItemResult(status="needs_review", reason="no validated set improves the gap",
                              before=before, after=after, judge=judge,
                              **{**base, "new_options": content})
        return ItemResult(status=status, reason=kind, before=before, after=after,
                          judge=judge, notes=notes, **{**base, "new_options": content})
    return ItemResult(status="needs_review",
                      reason="candidates exhausted (every set had a non-incorrect distractor)",
                      before=before, judge=judge, **base)


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
                 "gap_after", "old_A", "old_B", "old_C", "old_D", "new_A", "new_B", "new_C",
                 "new_D", "judge", "new_option_notes", "window"]


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
        "judge": " ".join(f"{l}:{v}" for l, v in sorted(result.judge.items())),
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
    flagged = [r for r in measured if r.reason in ("key_stands_out", "distractor_dominates")]
    lines = [f"items: {len(results)}  measured: {len(measured)}  flagged: {len(flagged)}",
             "status: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))]
    if measured:
        gaps = [abs((r.after or r.before)["gap"]) for r in measured]
        lines.append(f"mean |gap| after: {sum(gaps)/len(gaps):.3f}  "
                     f"within tolerance: {sum(g <= DEFAULT_TOLERANCE for g in gaps)}/{len(gaps)}")
    return "\n".join(lines)


def rebalance_records(records: List[dict], ctx: PassageContext, llm: Optional[LLM], **kw) -> List[tuple]:
    out = []
    for record in records:
        if record.get("q_type") != "mcq" or record.get("status") == "exclude":
            continue
        out.append((record, rebalance_item(record, ctx, llm, **kw)))
    return out


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
                             args.verse_window)
        pairs = rebalance_records(records, ctx, llm, tolerance=args.tolerance,
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
                         args.verse_window)
    pairs = rebalance_records(records, ctx, llm, tolerance=args.tolerance,
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
                      llm: Optional[LLM] = None) -> int:
    """Library entry point for main.py: rebalance one QA file in place. Returns #items changed."""
    records = json.loads(qa_path.read_text(encoding="utf-8"))
    verse_windows = load_verse_windows(windows_json) if windows_json else None
    reference = next((r.get("passage_reference") for r in records if r.get("passage_reference")), "")
    ctx = PassageContext(passage_path.read_text(encoding="utf-8"), reference, verse_windows,
                         verse_window)
    llm = llm or openai_llm(generator_model, judge_model, effort, retries)
    pairs = rebalance_records(records, ctx, llm, tolerance=tolerance)
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
