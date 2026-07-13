#!/usr/bin/env python3
"""Score generated Chinese QA answers against standard answers.

MCQ answers are scored by direct choice comparison. Open answers are scored with
OpenAI embedding cosine similarity and an LLM judgment after back-translation
to English.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.decanonicalize_chinese_dataset import (
    DEFAULT_ENGLISH_TOKEN_MAPPING,
    PROTECTED_TOKEN_MAPPING,
    replace_english_terms,
)


CHOICE_LABELS = ("A", "B", "C", "D")


CORE_CLAIM_JUDGE_TASK = """Grade the generated answer against the expected answer.

  Be semantically flexible: accept paraphrases, rough grammar, anonymized names, and equivalent wording.

  But require the generated answer to contain the expected answer's core claim. Do not mark an answer correct merely because it
  mentions related passage context, a nearby event, or something true from the passage.

  First identify the required answer slot:
  - person/group
  - object/place
  - action/event
  - reason/cause
  - time
  - statement/content
  - result/outcome

  Then check whether the generated answer fills that slot with the same meaning as the expected answer.

  Scores:
  1.0 = contains the core claim required by the expected answer.
  0.5 = partially answers the right slot but is incomplete, overly broad, or missing one important element.
  0.0 = wrong slot, nearby context only, contradiction, or missing the core claim.

  Return JSON:
  {
    "score": 0.0 | 0.5 | 1.0,
    "label": "correct" | "partial" | "incorrect",
    "required_slot": "...",
    "core_claim_expected": "...",
    "core_claim_found": true | false,
    "rationale": "..."
  }"""


class ScoreError(Exception):
    pass


def normalize_judgment(raw: dict) -> dict:
    label = str(raw.get("label") or "").strip().lower()
    try:
        score = float(raw.get("score"))
    except (TypeError, ValueError):
        score = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}.get(label, 0.0)

    if score >= 0.75:
        score = 1.0
        label = "correct"
    elif score >= 0.25:
        score = 0.5
        label = "partial"
    else:
        score = 0.0
        label = "incorrect"

    return {
        "label": label,
        "score": score,
        "rationale": str(raw.get("rationale") or "").strip(),
        "required_slot": str(raw.get("required_slot") or "").strip() or None,
        "core_claim_expected": str(raw.get("core_claim_expected") or "").strip() or None,
        "core_claim_found": raw.get("core_claim_found"),
    }


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScoreError(f"Invalid JSON in {path}: {exc}") from exc


def extract_items(data: Any) -> List[dict]:
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    if isinstance(data, dict):
        for key in ("items", "qa_items", "questions", "qas", "data"):
            value = data.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
        return [data]
    raise ScoreError("JSON must be an object or array of objects.")


def q_type_value(item: dict) -> str:
    value = (
        item.get("q_type")
        or item.get("question_type")
        or ("mcq" if item.get("mcq_choices") or isinstance(item.get("A"), dict) else "open")
    )
    normalized = str(value or "").strip().lower()
    if normalized in {"mcq", "multiple_choice", "multiple-choice"}:
        return "mcq"
    return "open"


def compact_choices(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        return {
            label: str(raw.get(label) or raw.get(label.lower()) or "").strip()
            for label in CHOICE_LABELS
        }
    if isinstance(raw, list):
        return {
            label: str(raw[index]).strip() if index < len(raw) else ""
            for index, label in enumerate(CHOICE_LABELS)
        }
    return {}


def answer_from_tagged_content(content: Any) -> Optional[str]:
    match = re.search(r"<answer>\s*(.*?)\s*<answer>", str(content or ""), re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def question_from_tagged_content(content: Any) -> Optional[str]:
    match = re.search(r"<question>\s*(.*?)\s*<question>", str(content or ""), re.DOTALL)
    if not match:
        return None
    question = re.sub(r"\n\s*[A-D]\.\s+.*$", "", match.group(1).strip(), flags=re.DOTALL)
    return question.strip() or None


def all_format_variants(item: dict) -> List[dict]:
    variants = []
    for q_type in ("open", "mcq"):
        nested = item.get(q_type)
        if not isinstance(nested, dict):
            continue
        merged = {
            key: value
            for key, value in item.items()
            if key not in {"open", "mcq"}
        }
        merged.update(nested)
        merged["q_type"] = q_type
        base_id = item.get("content_id") or item.get("id") or item.get("passage_id")
        if base_id:
            merged["content_id"] = f"{base_id}-{q_type}"
            merged["passage_id"] = f"uw-{base_id}-{q_type}"
        variants.append(merged)
    return variants


def expanded_items(items: Iterable[dict]) -> List[dict]:
    output = []
    for item in items:
        variants = all_format_variants(item)
        output.extend(variants or [item])
    return output


def protected_token_label(token: str) -> str:
    parts = str(token or "").strip("_").split("_")
    return " ".join(part.capitalize() for part in parts if part)


def default_standard_placeholder_mapping() -> Dict[str, str]:
    mapping = {}
    for source, token in DEFAULT_ENGLISH_TOKEN_MAPPING.items():
        label = protected_token_label(token)
        if source.endswith(("'s", "’s", "s'")):
            label = f"{label}'s"
        mapping[source] = label
    return mapping


def placeholderize_standard_answer(value: str, mapping: Dict[str, str] | None) -> str:
    if not mapping:
        return value
    result = replace_english_terms(value, mapping)
    placeholder_prefixes = (
        "Text|Author|Recipient|Person|Messenger|People|Ancestor|King|Village|"
        "Region|City|Division|Forefather|Ruler|Prophet|Most High|Master|"
        "Spirit|Honored|Worker|Place|Material|Request"
    )
    result = re.sub(
        rf"\b(?:A|An|a|an) ((?:{placeholder_prefixes}) [A-Z](?:'s)?)\b",
        r"\1",
        result,
    )
    return result


def chinese_placeholder_to_english_mapping() -> Dict[str, str]:
    return {
        chinese: protected_token_label(token)
        for token, chinese in PROTECTED_TOKEN_MAPPING.items()
    }


def normalize_chinese_placeholders_to_english(value: str) -> str:
    result = str(value or "")
    for chinese, english in sorted(
        chinese_placeholder_to_english_mapping().items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        result = result.replace(chinese, english)
    return result


def standard_answer(item: dict, placeholder_mapping: Dict[str, str] | None = None) -> str:
    answer = (
        item.get("A")
        if q_type_value(item) == "open"
        else None
    )
    if answer is None:
        answer = (
            item.get("expected_answer")
            or item.get("answer")
            or item.get("original_answer")
            or answer_from_tagged_content(item.get("content"))
        )
    return placeholderize_standard_answer(str(answer or "").strip(), placeholder_mapping)


def standard_correct_choice(item: dict) -> Optional[str]:
    correct = item.get("correct") or item.get("correct_choice") or item.get("mcq_correct_choice")
    if correct is not None:
        correct = str(correct).strip().upper()
        return correct if correct in CHOICE_LABELS else None

    expected = str(item.get("expected_answer") or "").strip()
    choices = compact_choices(item.get("A") or item.get("mcq_choices") or item.get("mcq_options"))
    for label, value in choices.items():
        if expected and expected == value:
            return label
    tagged_answer = answer_from_tagged_content(item.get("content"))
    if tagged_answer:
        tagged_answer = tagged_answer.strip().upper()
        return tagged_answer if tagged_answer in CHOICE_LABELS else None
    return None


def item_key_candidates(item: dict, index: int) -> List[str]:
    keys = [
        item.get("id"),
        item.get("content_id"),
        item.get("passage_id"),
        item.get("qa_item_id"),
        item.get("item_id"),
        f"index:{index}",
    ]
    return [str(key) for key in keys if key not in (None, "")]


def build_standard_index(
    items: List[dict],
    *,
    placeholder_mapping: Dict[str, str] | None = None,
) -> Dict[str, dict]:
    index = {}
    for position, item in enumerate(expanded_items(items), start=1):
        normalized = {
            "item_index": position,
            "id": item.get("id") or item.get("content_id") or item.get("passage_id") or position,
            "passage_id": item.get("passage_id"),
            "passage_reference": item.get("passage_reference") or item.get("title"),
            "q_type": q_type_value(item),
            "question": (
                item.get("Q")
                or item.get("question_text")
                or item.get("question")
                or item.get("mcq_stem")
                or item.get("original_question")
                or question_from_tagged_content(item.get("content"))
            ),
            "standard_answer": standard_answer(item, placeholder_mapping),
            "choices": compact_choices(
                item.get("A") if isinstance(item.get("A"), (dict, list)) else item.get("mcq_choices") or item.get("mcq_options")
            ),
            "correct_choice": standard_correct_choice(item),
        }
        for key in item_key_candidates(item, position):
            index[key] = normalized
    return index


def match_standard(generated: dict, standards: Dict[str, dict]) -> dict:
    for key in item_key_candidates(generated, int(generated.get("item_index") or 0)):
        if key in standards:
            return standards[key]
    raise ScoreError(
        "Could not match generated answer to standard item: "
        f"{generated.get('id') or generated.get('passage_id') or generated.get('item_index')}"
    )


def normalize_choice(value: Any, choices: Dict[str, str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    upper = text.upper()
    if upper in CHOICE_LABELS:
        return upper
    for label, choice_text in choices.items():
        if text == choice_text:
            return label
    return None


def cosine_similarity(left: List[float], right: List[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def batched(items: List[Any], batch_size: int) -> Iterable[List[Any]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def get_embedding_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ScoreError("Install the openai package to run embedding/LLM scoring.") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise ScoreError("OPENAI_API_KEY is required for embedding/LLM scoring.")
    return OpenAI()


def embed_texts(client: Any, model: str, texts: List[str], batch_size: int = 64) -> List[List[float]]:
    embeddings: List[List[float]] = []
    for batch in batched(texts, batch_size):
        response = client.embeddings.create(model=model, input=batch)
        embeddings.extend([item.embedding for item in response.data])
    return embeddings


def extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if content:
            return content
    chunks = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    if chunks:
        return "\n".join(chunks)
    raise ScoreError("Model response did not include text output.")


def create_text_response(client: Any, *, model: str, input: Any) -> Any:
    if hasattr(client, "responses"):
        return client.responses.create(model=model, input=input)
    if hasattr(client, "chat") and hasattr(client.chat, "completions"):
        messages = input
        if isinstance(input, str):
            messages = [{"role": "user", "content": input}]
        return client.chat.completions.create(model=model, messages=messages)
    raise ScoreError(
        "OpenAI client supports neither responses.create nor chat.completions.create."
    )


def extract_json_text(text: str) -> str:
    value = (text or "").strip()
    start = value.find("{")
    end = value.rfind("}")
    if start != -1 and end != -1 and end > start:
        return value[start : end + 1]
    return value


def extract_json_array_or_object_text(text: str) -> str:
    value = (text or "").strip()
    decoder = json.JSONDecoder()
    starts = sorted(
        index for index, char in enumerate(value) if char in "[{"
    )
    for start in starts:
        try:
            _, end = decoder.raw_decode(value[start:])
        except json.JSONDecodeError:
            continue
        return value[start : start + end]
    return value


def coerce_indexed_items(raw: Any, list_keys: tuple[str, ...]) -> List[dict]:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []

    for key in list_keys:
        value = raw.get(key)
        if isinstance(value, list):
            return value

    if "item_index" in raw:
        return [raw]

    indexed_items = []
    for key, value in raw.items():
        try:
            item_index = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            item = dict(value)
            item.setdefault("item_index", item_index)
        else:
            item = {"item_index": item_index, "translation": value}
        indexed_items.append(item)
    return indexed_items


def translate_open_answers_to_english(
    client: Any,
    model: str,
    rows: List[dict],
    retries: int,
    batch_size: int = 20,
) -> None:
    if not rows:
        return

    def request_translations(batch_rows: List[dict]) -> Dict[int, str]:
        prompt = {
            "task": (
                "Translate each generated answer into concise English. Preserve item_index "
                "exactly. Do not evaluate correctness and do not add explanations."
            ),
            "items": [
                {
                    "item_index": row["item_index"],
                    "question": row["question"],
                    "generated_answer": normalize_chinese_placeholders_to_english(
                        row["generated_answer"]
                    ),
                }
                for row in batch_rows
            ],
            "output_schema": [
                {
                    "item_index": 1,
                    "generated_answer_english": "English translation",
                }
            ],
        }
        last_error: Optional[Exception] = None
        translations_by_index: Dict[int, str] = {}
        for attempt in range(retries + 1):
            try:
                response = create_text_response(
                    client,
                    model=model,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "You are a precise translation engine. Return valid JSON only. "
                                "Do not include markdown."
                            ),
                        },
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                )
                raw = json.loads(
                    extract_json_array_or_object_text(extract_response_text(response))
                )
                raw = coerce_indexed_items(
                    raw,
                    ("items", "translations", "data", "results"),
                )
                if not isinstance(raw, list):
                    raise ScoreError("Back-translation response must be a JSON array.")
                for item in raw:
                    if not isinstance(item, dict):
                        raise ScoreError("Back-translation items must be objects.")
                    item_index = int(item.get("item_index") or 0)
                    translated = str(
                        item.get("generated_answer_english")
                        or item.get("english")
                        or item.get("translation")
                        or ""
                    ).strip()
                    if item_index and translated:
                        translations_by_index[item_index] = (
                            normalize_chinese_placeholders_to_english(translated)
                        )
                break
            except Exception as exc:
                last_error = exc
                translations_by_index = {}
                if attempt >= retries:
                    break
                time.sleep(2**attempt)

        if last_error and not translations_by_index:
            raise ScoreError(f"Back-translation failed: {last_error}") from last_error
        return translations_by_index

    for batch in batched(rows, batch_size):
        translations_by_index = request_translations(batch)

        missing_rows = []
        for row in batch:
            item_index = int(row["item_index"] or 0)
            translated = translations_by_index.get(item_index)
            if translated:
                row["generated_answer_english"] = translated
            else:
                missing_rows.append(row)

        for row in missing_rows:
            item_index = int(row["item_index"] or 0)
            translations_by_index = request_translations([row])
            translated = translations_by_index.get(item_index)
            if translated:
                row["generated_answer_english"] = translated

        still_missing = [
            str(row["item_index"])
            for row in batch
            if not row.get("generated_answer_english")
        ]
        if still_missing:
            raise ScoreError(
                "Back-translation omitted item_index value(s): "
                + ", ".join(still_missing)
            )


def backtranslate_generated_answers(
    generated_items: List[dict],
    standard_items: List[dict],
    *,
    translation_model: str,
    retries: int,
    batch_size: int = 20,
) -> List[dict]:
    standards = build_standard_index(standard_items)
    output = [dict(item) for item in generated_items]
    open_rows = []
    output_by_index = {}

    for generated in output:
        standard = match_standard(generated, standards)
        if q_type_value(standard) == "mcq":
            continue
        item_index = generated.get("item_index")
        if item_index in (None, ""):
            item_index = standard["item_index"]
            generated["item_index"] = item_index
        generated.setdefault("question", standard.get("question"))
        row = {
            "item_index": item_index,
            "question": generated.get("question") or standard.get("question"),
            "generated_answer": str(generated.get("generated_answer") or "").strip(),
            "generated_answer_english": str(
                generated.get("generated_answer_english") or ""
            ).strip() or None,
        }
        output_by_index[int(item_index)] = generated
        if row["generated_answer"] and not row["generated_answer_english"]:
            open_rows.append(row)

    if open_rows:
        client = get_embedding_client()
        translate_open_answers_to_english(
            client,
            translation_model,
            open_rows,
            retries,
            batch_size=batch_size,
        )
        for row in open_rows:
            output_by_index[int(row["item_index"])][
                "generated_answer_english"
            ] = row["generated_answer_english"]

    return output


def llm_judge_one(
    client: Any,
    model: str,
    item: dict,
    retries: int,
    *,
    answer_field: str,
    mode: str,
) -> dict:
    if mode == "english":
        task = CORE_CLAIM_JUDGE_TASK
    else:
        raise ScoreError(f"Unknown LLM judge mode: {mode}")

    prompt = {
        "task": task,
        "question": normalize_chinese_placeholders_to_english(item["question"]),
        "standard_answer": item["standard_answer"],
        "generated_answer": item[answer_field],
        "output_schema": {
            "score": "0.0 | 0.5 | 1.0",
            "label": "correct | partial | incorrect",
            "required_slot": "person/group | object/place | action/event | reason/cause | time | statement/content | result/outcome",
            "core_claim_expected": "short core claim from standard answer",
            "core_claim_found": "true if generated answer contains the core claim, else false",
            "rationale": "short reason in English",
        },
    }
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            response = create_text_response(
                client,
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict QA evaluator. Return valid JSON only. "
                            "Do not include markdown."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            raw = json.loads(
                extract_json_array_or_object_text(extract_response_text(response))
            )
            return normalize_judgment(raw)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise ScoreError(f"LLM judge failed for {mode} answer: {last_error}") from last_error


def llm_judge_batch(
    client: Any,
    model: str,
    rows: List[dict],
    retries: int,
    *,
    answer_field: str,
    mode: str,
) -> Dict[int, dict]:
    if not rows:
        return {}
    if mode != "english":
        raise ScoreError(f"Unknown LLM judge mode: {mode}")

    task = CORE_CLAIM_JUDGE_TASK
    prompt = {
        "task": task,
        "items": [
            {
                "item_index": row["item_index"],
                "question": normalize_chinese_placeholders_to_english(row["question"]),
                "standard_answer": row["standard_answer"],
                "generated_answer": row[answer_field],
            }
            for row in rows
        ],
        "output_schema": [
            {
                "item_index": 1,
                "score": "0.0 | 0.5 | 1.0",
                "label": "correct | partial | incorrect",
                "required_slot": "person/group | object/place | action/event | reason/cause | time | statement/content | result/outcome",
                "core_claim_expected": "short core claim from standard answer",
                "core_claim_found": "true if generated answer contains the core claim, else false",
                "rationale": "short reason in English",
            }
        ],
    }

    expected_indexes = {int(row["item_index"] or 0) for row in rows}
    expected_indexes.discard(0)
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            response = create_text_response(
                client,
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict QA evaluator. Return valid JSON only. "
                            "Do not include markdown."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            raw = json.loads(
                extract_json_array_or_object_text(extract_response_text(response))
            )
            raw = coerce_indexed_items(
                raw,
                ("items", "judgments", "data", "results"),
            )
            if not isinstance(raw, list):
                raise ScoreError("LLM judge response must be a JSON array.")

            judgments: Dict[int, dict] = {}
            for item in raw:
                if not isinstance(item, dict):
                    raise ScoreError("LLM judge items must be objects.")
                item_index = int(item.get("item_index") or 0)
                if item_index not in expected_indexes:
                    continue
                judgments[item_index] = normalize_judgment(item)

            missing = expected_indexes - set(judgments)
            if missing:
                raise ScoreError(
                    "LLM judge omitted item_index value(s): "
                    + ", ".join(str(index) for index in sorted(missing))
                )
            return judgments
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise ScoreError(f"LLM judge batch failed for {mode} answers: {last_error}") from last_error


def score_items(
    generated_items: List[dict],
    standard_items: List[dict],
    *,
    embedding_model: str,
    judge_model: str,
    translation_model: str,
    retries: int,
    skip_llm: bool,
    skip_embeddings: bool,
    placeholder_standard_answers: bool = False,
    judge_batch_size: int = 20,
) -> List[dict]:
    standards = build_standard_index(
        standard_items,
        placeholder_mapping=(
            default_standard_placeholder_mapping()
            if placeholder_standard_answers
            else None
        ),
    )
    scored = []
    open_rows = []

    for generated in generated_items:
        standard = match_standard(generated, standards)
        q_type = standard["q_type"]
        row = {
            "item_index": generated.get("item_index"),
            "id": generated.get("id") or standard.get("id"),
            "passage_id": generated.get("passage_id") or standard.get("passage_id"),
            "passage_reference": generated.get("passage_reference") or standard.get("passage_reference"),
            "q_type": q_type,
            "question": generated.get("question") or standard.get("question"),
            "standard_answer": standard["standard_answer"],
            "generated_answer": str(generated.get("generated_answer") or "").strip(),
            "generated_answer_english": str(
                generated.get("generated_answer_english") or ""
            ).strip() or None,
            "generation_error": generated.get("generation_error"),
        }
        if "answer_confidence" in generated:
            row["answer_confidence"] = generated.get("answer_confidence")
        if "insufficient_information" in generated:
            row["insufficient_information"] = generated.get("insufficient_information")
        if "evidence_quality" in generated:
            row["evidence_quality"] = generated.get("evidence_quality")
        if row["item_index"] in (None, ""):
            row["item_index"] = standard["item_index"]

        if q_type == "mcq":
            correct = standard["correct_choice"]
            selected = normalize_choice(
                generated.get("selected_choice") or generated.get("generated_answer"),
                standard["choices"],
            )
            row.update(
                {
                    "correct_choice": correct,
                    "selected_choice": selected,
                    "direct_correct": bool(correct and selected == correct),
                    "embedding_similarity": None,
                    "llm_label": None,
                    "llm_score": None,
                    "llm_rationale": None,
                    "llm_english_label": None,
                    "llm_english_rationale": None,
                    "llm_required_slot": None,
                    "llm_core_claim_expected": None,
                    "llm_core_claim_found": None,
                }
            )
        else:
            row.update(
                {
                    "direct_correct": None,
                    "embedding_similarity": None,
                    "llm_label": None,
                    "llm_score": None,
                    "llm_rationale": None,
                    "llm_english_label": None,
                    "llm_english_rationale": None,
                    "llm_required_slot": None,
                    "llm_core_claim_expected": None,
                    "llm_core_claim_found": None,
                }
            )
            if row["generated_answer"]:
                open_rows.append(row)
            else:
                row.update(
                    {
                        "llm_label": "incorrect",
                        "llm_score": 0.0,
                        "llm_rationale": "No generated answer.",
                        "llm_english_label": "incorrect",
                        "llm_english_rationale": "No generated answer.",
                        "llm_required_slot": None,
                        "llm_core_claim_expected": standard["standard_answer"],
                        "llm_core_claim_found": False,
                    }
                )

        scored.append(row)

    client = None
    if open_rows and (not skip_embeddings or not skip_llm):
        client = get_embedding_client()
        rows_missing_translation = [
            row
            for row in open_rows
            if row.get("generated_answer") and not row.get("generated_answer_english")
        ]
        if rows_missing_translation:
            translate_open_answers_to_english(
                client,
                translation_model,
                rows_missing_translation,
                retries,
            )

    if open_rows and not skip_embeddings:
        texts = []
        for row in open_rows:
            texts.extend([row["standard_answer"], row["generated_answer_english"]])
        embeddings = embed_texts(client, embedding_model, texts)
        for row_index, row in enumerate(open_rows):
            standard_embedding = embeddings[row_index * 2]
            generated_embedding = embeddings[(row_index * 2) + 1]
            row["embedding_similarity"] = cosine_similarity(
                standard_embedding,
                generated_embedding,
            )

    if open_rows and not skip_llm:
        for batch in batched(open_rows, judge_batch_size):
            try:
                judgments = llm_judge_batch(
                    client,
                    judge_model,
                    batch,
                    retries,
                    answer_field="generated_answer_english",
                    mode="english",
                )
            except ScoreError:
                judgments = {
                    int(row["item_index"]): llm_judge_one(
                        client,
                        judge_model,
                        row,
                        retries,
                        answer_field="generated_answer_english",
                        mode="english",
                    )
                    for row in batch
                }

            for row in batch:
                english_judgment = judgments[int(row["item_index"])]
                row["llm_english_label"] = english_judgment["label"]
                row["llm_english_rationale"] = english_judgment["rationale"]
                row["llm_label"] = english_judgment["label"]
                row["llm_score"] = english_judgment["score"]
                row["llm_rationale"] = english_judgment["rationale"]
                row["llm_required_slot"] = english_judgment.get("required_slot")
                row["llm_core_claim_expected"] = english_judgment.get(
                    "core_claim_expected"
                )
                row["llm_core_claim_found"] = english_judgment.get("core_claim_found")

    return scored


def summarize(scored: List[dict]) -> dict:
    mcq = [item for item in scored if item["q_type"] == "mcq"]
    open_items = [item for item in scored if item["q_type"] != "mcq"]
    similarities = [
        item["embedding_similarity"]
        for item in open_items
        if item.get("embedding_similarity") is not None
    ]
    llm_scores = [
        item["llm_score"]
        for item in open_items
        if item.get("llm_score") is not None
    ]
    confidence_values = [
        float(item["answer_confidence"])
        for item in scored
        if item.get("answer_confidence") is not None
    ]
    insufficient_items = [
        item
        for item in scored
        if item.get("insufficient_information") is not None
    ]
    evidence_items = [
        item
        for item in scored
        if item.get("evidence_quality") is not None
    ]
    wrong_high_confidence = [
        item
        for item in scored
        if item.get("answer_confidence") is not None
        and float(item.get("answer_confidence") or 0) >= 0.8
        and (
            (item["q_type"] == "mcq" and not item.get("direct_correct"))
            or (
                item["q_type"] != "mcq"
                and item.get("llm_score") is not None
                and float(item["llm_score"]) < 0.5
            )
        )
    ]
    correct_low_confidence = [
        item
        for item in scored
        if item.get("answer_confidence") is not None
        and float(item.get("answer_confidence") or 0) <= 0.4
        and (
            (item["q_type"] == "mcq" and item.get("direct_correct"))
            or (
                item["q_type"] != "mcq"
                and item.get("llm_score") is not None
                and float(item["llm_score"]) >= 0.5
            )
        )
    ]
    return {
        "total": len(scored),
        "mcq_count": len(mcq),
        "mcq_correct": sum(1 for item in mcq if item.get("direct_correct")),
        "open_count": len(open_items),
        "open_embedding_mean": (
            sum(similarities) / len(similarities) if similarities else None
        ),
        "open_llm_score_mean": (
            sum(llm_scores) / len(llm_scores) if llm_scores else None
        ),
        "answer_confidence_mean": (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else None
        ),
        "insufficient_information_rate": (
            sum(1 for item in insufficient_items if item.get("insufficient_information"))
            / len(insufficient_items)
            if insufficient_items
            else None
        ),
        "direct_evidence_rate": (
            sum(1 for item in evidence_items if item.get("evidence_quality") == "direct")
            / len(evidence_items)
            if evidence_items
            else None
        ),
        "evidence_supported_rate": (
            sum(
                1
                for item in evidence_items
                if item.get("evidence_quality") in {"direct", "indirect"}
            )
            / len(evidence_items)
            if evidence_items
            else None
        ),
        "wrong_high_confidence_count": len(wrong_high_confidence),
        "correct_low_confidence_count": len(correct_low_confidence),
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score generated Chinese QA answers against standard answers."
    )
    parser.add_argument("generated_answers_json", type=Path)
    parser.add_argument("standard_qa_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
    )
    parser.add_argument(
        "--judge-model",
        default=os.getenv("OPENAI_JUDGE_MODEL", "gpt-5.4-mini"),
    )
    parser.add_argument(
        "--translation-model",
        default=os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-5.4-mini"),
        help="OpenAI model for back-translating generated open answers to English.",
    )
    parser.add_argument(
        "--judge-batch-size",
        type=int,
        default=20,
        help="Open answers per LLM judge request. Default: 20.",
    )
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument(
        "--placeholder-standard-answers",
        action="store_true",
        help=(
            "Replace canonical English names/terms in standard answers with "
            "placeholder labels such as Person A before scoring."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.retries < 0:
        print("--retries must be zero or greater", file=sys.stderr)
        return 2
    if args.judge_batch_size < 1:
        print("--judge-batch-size must be at least 1", file=sys.stderr)
        return 2

    try:
        generated = extract_items(load_json(args.generated_answers_json))
        standards = extract_items(load_json(args.standard_qa_json))
        items = score_items(
            generated,
            standards,
            embedding_model=args.embedding_model,
            judge_model=args.judge_model,
            translation_model=args.translation_model,
            retries=args.retries,
            skip_llm=args.skip_llm,
            skip_embeddings=args.skip_embeddings,
            placeholder_standard_answers=args.placeholder_standard_answers,
            judge_batch_size=args.judge_batch_size,
        )
        output = {
            "summary": summarize(items),
            "items": items,
        }
        write_json(args.output_json, output)
    except ScoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote scores for {len(items)} item(s) to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
