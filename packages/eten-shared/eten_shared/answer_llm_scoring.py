"""Binary LLM scoring for participant open answers.

The evaluator mirrors the evaluation pipeline: translate a target-language
answer back to English, then judge its core claim against the source answer.
It deliberately exposes only binary scores (0.0 or 1.0) for human responses.
"""

from dataclasses import dataclass
import json
import os
from typing import Any, Optional


DEFAULT_MODEL = "gpt-4.1-mini"


class AnswerLLMScoringError(RuntimeError):
    pass


@dataclass(frozen=True)
class BinaryAnswerScore:
    score: float
    label: str
    backtranslated_answer: str
    expected_answer_english: str
    rationale: str
    core_claim_expected: Optional[str] = None
    core_claim_found: Optional[bool] = None


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


def _request(client, model: str, system: str, payload: dict) -> dict:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        if hasattr(client, "responses"):
            response = client.responses.create(model=model, input=messages)
        elif hasattr(client, "chat") and hasattr(client.chat, "completions"):
            response = client.chat.completions.create(model=model, messages=messages)
        else:
            raise AnswerLLMScoringError("OpenAI client has no text-generation interface")
        return _json_object(response)
    except AnswerLLMScoringError:
        raise
    except Exception as exc:
        raise AnswerLLMScoringError(f"LLM request failed: {exc}") from exc


def score_open_answer_binary(
    *,
    question: str,
    participant_answer: str,
    expected_answer: str,
    original_question: Optional[str] = None,
    original_expected_answer: Optional[str] = None,
    language: Optional[str] = None,
    client=None,
    translation_model: Optional[str] = None,
    judge_model: Optional[str] = None,
) -> BinaryAnswerScore:
    answer = str(participant_answer or "").strip()
    expected = str(expected_answer or "").strip()
    if not answer:
        return BinaryAnswerScore(0.0, "incorrect", "", original_expected_answer or expected,
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

    judged = _request(
        client,
        judge_model,
        "You are a strict QA evaluator. Return valid JSON only; never award partial credit.",
        {
            "task": (
                "Judge whether the participant answer contains the expected answer's core claim. "
                "Accept semantic equivalents and rough grammar. Related context without the core "
                "claim is incorrect. The score must be exactly 1 or 0."
            ),
            "question": original_question or question,
            "expected_answer": expected_english,
            "participant_answer": backtranslated,
            "output_schema": {
                "score": "1 | 0",
                "label": "correct | incorrect",
                "core_claim_expected": "short expected core claim",
                "core_claim_found": "true | false",
                "rationale": "short reason in English",
            },
        },
    )
    raw_score = judged.get("score")
    label = str(judged.get("label") or "").strip().lower()
    score = 1.0 if raw_score in {1, 1.0, "1", "1.0", True} and label != "incorrect" else 0.0
    return BinaryAnswerScore(
        score=score,
        label="correct" if score == 1.0 else "incorrect",
        backtranslated_answer=backtranslated,
        expected_answer_english=expected_english,
        rationale=str(judged.get("rationale") or "").strip(),
        core_claim_expected=str(judged.get("core_claim_expected") or "").strip() or None,
        core_claim_found=judged.get("core_claim_found") if isinstance(
            judged.get("core_claim_found"), bool
        ) else score == 1.0,
    )
