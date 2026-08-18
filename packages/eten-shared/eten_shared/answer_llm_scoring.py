"""LLM scoring for participant open answers.

The evaluator mirrors the offline benchmark judge
(``evaluation/scripts/mcq/regen_mcq_tier01.py::judge_open``) so that human
open scores and proxy open scores live on the SAME scale and can be compared
directly by the human-pilot hypotheses (H-T1 / H-T2 / H-T7).

Parity contract with ``judge_open`` -- change these together or the pilot's
human leg stops being comparable to its own benchmarks:

  * score scale     0 / 0.5 / 1   (partial credit ALLOWED)
  * judge model     gpt-4o-mini   (``OPENAI_ANSWER_JUDGE_MODEL``)
  * temperature     0.0, always   (see below)
  * prompt          the passage the respondent actually read is supplied as
                    context, and the rubric wording is judge_open's

[2026-08-12] Temperature note: this module previously passed no ``temperature``
at all, so every call inherited the API default of 1.0. The 2026-08-03 sweep
that pinned all 7 OpenAI stages to 0 covered ``evaluation/main.py`` only and
missed this package, which meant the pilot's PRIMARY human instrument would
have run unpinned. All requests now pass temperature 0.0 explicitly.

The ``passage`` argument is the variant passage for the respondent's
experiment cell, not the clean chapter text -- see
``resolve_response_passage_text`` for why those differ.
"""

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Optional


DEFAULT_MODEL = "gpt-4o-mini"

# Scores the judge is allowed to return, matching judge_open's 1 / 0.5 / 0.
VALID_SCORES = (0.0, 0.5, 1.0)

# Pinned for reproducibility. judge_open uses temperature=0.0; so do we.
JUDGE_TEMPERATURE = 0.0

_SCORE_PATTERN = re.compile(r"(?<!\d)(0\.5|1(?:\.0)?|0(?:\.0)?)(?!\d)")


class AnswerLLMScoringError(RuntimeError):
    pass


def _label_for(score: float) -> str:
    if score == 1.0:
        return "correct"
    if score == 0.5:
        return "partial"
    return "incorrect"


@dataclass(frozen=True)
class AnswerScore:
    """A 0 / 0.5 / 1 judgement, on the same scale as the offline grid."""

    score: float
    label: str
    backtranslated_answer: str
    expected_answer_english: str
    rationale: str
    core_claim_expected: Optional[str] = None
    core_claim_found: Optional[bool] = None


# Retained so older imports keep resolving; the payload is no longer binary.
BinaryAnswerScore = AnswerScore


def llm_answer_scoring_enabled() -> bool:
    return os.getenv("ENABLE_LLM_ANSWER_SCORING", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AnswerLLMScoringError("Install openai to use LLM answer scoring") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise AnswerLLMScoringError("OPENAI_API_KEY is required for LLM answer scoring")
    return OpenAI()


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    choices = getattr(response, "choices", None) or []
    if choices:
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if content:
            return content
    chunks = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            if getattr(content, "text", None):
                chunks.append(content.text)
    if chunks:
        return "\n".join(chunks)
    raise AnswerLLMScoringError("LLM response did not contain text")


def _json_object(response: Any) -> dict:
    text = _response_text(response).strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AnswerLLMScoringError("LLM response was not a JSON object")


def _create(client, model: str, messages: list):
    """Send one request with temperature pinned at 0.

    The Responses API accepts ``temperature`` but not ``seed`` (documented in
    PROJECT_CONTEXT under the 2026-08-03 fix), so 0 buys near-determinism, not
    bit-reproducibility.
    """
    if hasattr(client, "responses"):
        return client.responses.create(
            model=model, input=messages, temperature=JUDGE_TEMPERATURE
        )
    if hasattr(client, "chat") and hasattr(client.chat, "completions"):
        return client.chat.completions.create(
            model=model, messages=messages, temperature=JUDGE_TEMPERATURE
        )
    raise AnswerLLMScoringError("OpenAI client has no text-generation interface")


def _request(client, model: str, system: str, payload: dict) -> dict:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        return _json_object(_create(client, model, messages))
    except AnswerLLMScoringError:
        raise
    except Exception as exc:
        raise AnswerLLMScoringError(f"LLM request failed: {exc}") from exc


def _coerce_score(raw: Any, label: str) -> Optional[float]:
    """Map the judge's reported score onto 0 / 0.5 / 1.

    judge_open regex-scans free text for the score token; we accept a JSON
    number first and fall back to the same scan so both judges tolerate the
    same sloppy outputs.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value in VALID_SCORES:
            return value
    text = str(raw if raw is not None else "").strip()
    if not text:
        text = (label or "").strip()
    match = _SCORE_PATTERN.search(text)
    if match:
        return float(match.group(1))
    normalized = (label or "").strip().lower()
    if normalized in {"correct", "yes", "true"}:
        return 1.0
    if normalized in {"partial", "partially correct", "half"}:
        return 0.5
    if normalized in {"incorrect", "no", "false"}:
        return 0.0
    return None


def score_open_answer(
    *,
    question: str,
    participant_answer: str,
    expected_answer: str,
    passage: Optional[str] = None,
    original_question: Optional[str] = None,
    original_expected_answer: Optional[str] = None,
    language: Optional[str] = None,
    client=None,
    translation_model: Optional[str] = None,
    judge_model: Optional[str] = None,
) -> AnswerScore:
    """Score one open answer on the grid judge's 0 / 0.5 / 1 scale.

    ``passage`` must be the VARIANT passage the respondent actually read (the
    text for their experiment cell), not the clean chapter. Passing the clean
    text would let the judge resolve claims the respondent could not have read,
    which biases exactly the degraded conditions the pilot is measuring.
    """
    answer = str(participant_answer or "").strip()
    expected = str(expected_answer or "").strip()
    if not answer:
        # judge_open short-circuits blank answers to 0 rather than asking.
        return AnswerScore(0.0, "incorrect", "", original_expected_answer or expected,
                           "No participant answer.", core_claim_found=False)
    if not expected and not original_expected_answer:
        raise AnswerLLMScoringError("Expected answer is required for LLM scoring")

    client = client or _client()
    translation_model = translation_model or os.getenv(
        "OPENAI_ANSWER_BACKTRANSLATION_MODEL", DEFAULT_MODEL
    )
    judge_model = judge_model or os.getenv("OPENAI_ANSWER_JUDGE_MODEL", DEFAULT_MODEL)

    translate_payload = {
        "task": "Translate the participant answer into concise English without evaluating it.",
        "source_language": language or "unknown",
        "question": question,
        "participant_answer": answer,
        "output_schema": {"backtranslated_answer": "English translation"},
    }
    if not original_expected_answer:
        translate_payload["expected_answer"] = expected
        translate_payload["output_schema"]["expected_answer_english"] = "English translation"
    translated = _request(
        client,
        translation_model,
        "You are a precise translation engine. Return valid JSON only.",
        translate_payload,
    )
    backtranslated = str(translated.get("backtranslated_answer") or "").strip()
    expected_english = str(
        original_expected_answer or translated.get("expected_answer_english") or expected
    ).strip()
    if not backtranslated or not expected_english:
        raise AnswerLLMScoringError("Backtranslation omitted required text")

    judge_payload = {
        # Wording tracks judge_open so the two judges apply one rubric.
        "task": (
            "Judge whether the participant answer contains the core claim required by the "
            "expected answer. Accept equivalent wording, paraphrases, anonymized names, and "
            "rough grammar. Do not accept merely related passage context. "
            "Output one score: 1, 0.5, or 0. "
            "1 = correct core claim; 0.5 = partially correct; 0 = incorrect or missing."
        ),
        "question": original_question or question,
        "expected_answer": expected_english,
        "participant_answer": backtranslated,
        "output_schema": {
            "score": "1 | 0.5 | 0",
            "label": "correct | partial | incorrect",
            "core_claim_expected": "short expected core claim",
            "core_claim_found": "true | false",
            "rationale": "short reason in English",
        },
    }
    # judge_open supplies the passage the respondent read; omit the key entirely
    # rather than sending an empty string, which reads as "passage was blank".
    if (passage or "").strip():
        judge_payload["passage"] = passage.strip()

    judged = _request(
        client,
        judge_model,
        "You are a strict QA evaluator. Return valid JSON only.",
        judge_payload,
    )
    label = str(judged.get("label") or "").strip().lower()
    score = _coerce_score(judged.get("score"), label)
    if score is None:
        raise AnswerLLMScoringError(
            f"Judge returned an unusable score: {judged.get('score')!r} (label {label!r})"
        )

    core_claim_found = judged.get("core_claim_found")
    return AnswerScore(
        score=score,
        label=_label_for(score),
        backtranslated_answer=backtranslated,
        expected_answer_english=expected_english,
        rationale=str(judged.get("rationale") or "").strip(),
        core_claim_expected=str(judged.get("core_claim_expected") or "").strip() or None,
        core_claim_found=(
            core_claim_found if isinstance(core_claim_found, bool) else score == 1.0
        ),
    )


# Deprecated name kept so any straggling import resolves. It no longer returns a
# binary score -- callers must handle 0.5.
score_open_answer_binary = score_open_answer


@dataclass(frozen=True)
class ChoiceResolution:
    """An LLM's reading of a free-text MCQ reply."""

    letter: Optional[str]          # "A".."D", or None if the reply picks nothing
    rationale: str
    resolved_by_llm: bool = True


def resolve_choice_letter(
    *,
    question: str,
    participant_answer: str,
    choices: dict,
    language: Optional[str] = None,
    client=None,
    model: Optional[str] = None,
) -> ChoiceResolution:
    """Map a free-text MCQ reply onto a choice letter.

    FALLBACK ONLY. ``eten_shared.mcq.parse_mcq_response_letter`` runs first and
    handles the clean cases (a bare letter, an ``mcq_N`` id, an exact choice
    restatement); this is for replies it returns None on.

    Why it exists: ``choice_response_is_correct`` scores an unparseable reply
    as FALSE, not as unscorable. A participant who writes "I think the second
    one" or answers in prose is therefore recorded as having answered WRONG.
    The proxy leg cannot produce that failure -- answer models emit clean
    letters -- so it is a bias that lives only in the human arm and pushes
    human MCQ accuracy down relative to its own benchmark.

    This does NOT re-judge parseable replies: those keep the exact letter-vs-key
    comparison the offline grid uses, so MCQ parity with the grid is preserved
    and no judge noise is added to cleanly-answered items.

    Returns ``letter=None`` when the reply genuinely selects nothing (refusal,
    "I don't know", off-topic). Callers must treat that as unscorable rather
    than as a wrong answer.
    """
    answer = str(participant_answer or "").strip()
    if not answer:
        return ChoiceResolution(None, "Empty reply.")
    if not choices:
        raise AnswerLLMScoringError("Choices are required to resolve an MCQ reply")

    client = client or _client()
    model = model or os.getenv("OPENAI_ANSWER_JUDGE_MODEL", DEFAULT_MODEL)

    judged = _request(
        client,
        model,
        "You map a reply onto one of the offered choices. Return valid JSON only.",
        {
            "task": (
                "The participant was shown a multiple-choice question and replied in free "
                "text. Decide which choice, if any, the reply selects. Accept paraphrases, "
                "restatements of a choice's content, ordinal references ('the second one'), "
                "and replies in any language. If the reply selects no choice, is a refusal, "
                "expresses not knowing, or is ambiguous between choices, return null. "
                "Do NOT judge whether the choice is correct -- only which one was picked."
            ),
            "language": language or "unknown",
            "question": question,
            "choices": choices,
            "participant_reply": answer,
            "output_schema": {
                "letter": "one of the choice letters, or null",
                "rationale": "short reason in English",
            },
        },
    )

    raw_letter = judged.get("letter")
    letter = str(raw_letter).strip().upper() if raw_letter is not None else ""
    if letter not in choices:
        letter = None
    return ChoiceResolution(
        letter=letter,
        rationale=str(judged.get("rationale") or "").strip(),
    )


def resolve_response_passage_text(response: Any) -> Optional[str]:
    """Return the passage text the respondent actually read, or None.

    Why this is not just ``response.qa_item.passage_text``: in the human pilot
    the QA set is SHARED across a chapter's conditions -- ``pilot_import.py``
    writes one QAItem per (chapter, question) with ``passage_id='luke{ch}'``
    and imports the 7 variant passages separately as ExperimentPassage rows.
    So ``qa_item.passage_text`` is condition-INVARIANT: for a participant in
    the omission-30% cell it holds text they never saw, including the very
    sentences the manipulation deleted.

    Resolution order:

    1. ``Assignment.passage_text`` -- the immutable snapshot stamped when the
       assignment was created. This is the exact text that was delivered, already
       sliced to the item's window/tile and in the cell's condition, so it is
       what the respondent actually read. Preferred over re-deriving anything.

    2. ``ExperimentPlanCell.experiment_passage`` -- the legacy per-chapter FK.
       Only meaningful for Luke-style cells, where one cell == one passage.

       [2026-08-12] It is NOT sufficient for tier-1. A tier-1 cell is a WINDOW
       GROUP that can span two source passages, so no single
       ``experiment_passage_id`` can identify the right variant -- see
       ``resolve_experiment_passage``, which keys on the item's
       ``passage_id`` plus the cell's condition instead. Relying on the FK alone
       here returned None for every tier-1 response, which the outbox correctly
       but unhelpfully treated as "refuse to judge".

    3. ``qa_item.passage_text`` -- non-experiment responses only, where no
       variant exists and the two texts are the same.

    An experiment response that resolves to nothing returns None rather than
    falling through to the condition-invariant chapter text: judging a degraded
    cell against clean text would credit claims the respondent could not read.
    """
    assignment = getattr(response, "assignment", None)

    delivered = getattr(assignment, "passage_text", None) if assignment else None
    if (delivered or "").strip():
        return delivered

    cell = getattr(assignment, "experiment_cell", None) if assignment else None
    passage = getattr(cell, "experiment_passage", None) if cell else None
    text = getattr(passage, "passage_text", None)
    if (text or "").strip():
        return text

    if cell is not None:
        # In an experiment cell but nothing resolved: either the SET NULL
        # footgun from reset_experiment_plan, or a tier-1 cell whose assignment
        # never got its snapshot stamped. Refuse rather than fabricate context.
        return None

    qa_item = getattr(response, "qa_item", None)
    return getattr(qa_item, "passage_text", None)
