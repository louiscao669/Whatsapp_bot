#!/usr/bin/env python3
"""Generate Chinese answers from a Chinese passage and QA questions.

The model sees only the passage, question text, and MCQ choices. Ground-truth
answers, correct letters, and keyword fields are removed before prompting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, List, Optional


CHOICE_LABELS = ("A", "B", "C", "D")
FULLWIDTH_CHOICE_LABELS = str.maketrans("ＡＢＣＤａｂｃｄ", "ABCDabcd")
VERSE_MARKER_RE = re.compile(r"(?<![\w\]])(\d{1,3})\s+")
PASSAGE_REFERENCE_RE = re.compile(r":\s*(\d+)(?:\s*[-–—]\s*(\d+))?")
ANSWER_FIELDS = {
    "A",
    "answer",
    "expected_answer",
    "correct",
    "correct_choice",
    "mcq_correct_choice",
    "required_keywords",
    "optional_keywords",
    "anchors",
}


class GenerationError(Exception):
    pass


class AnswerParseError(GenerationError):
    def __init__(self, message: str, raw_model_answer: str):
        super().__init__(message)
        self.raw_model_answer = raw_model_answer


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GenerationError(f"Invalid JSON in {path}: {exc}") from exc


def load_passage(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise GenerationError(f"Passage file is empty: {path}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for field in ("passage_text", "content", "text", "passage"):
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise GenerationError(
        "Passage JSON must be a string or object with passage_text/content/text/passage."
    )


def load_qa_items(path: Path) -> List[dict]:
    data = load_json(path)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    raise GenerationError("QA JSON must be an object or an array of objects.")


def q_type_value(item: dict) -> str:
    value = (
        item.get("q_type")
        or item.get("question_type")
        or ("mcq" if item.get("mcq_choices") or item.get("mcq_options") else "open")
    )
    normalized = str(value or "").strip().lower()
    if normalized in {"multiple_choice", "multiple-choice"}:
        return "mcq"
    if normalized == "mcq":
        return "mcq"
    return "open"


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


def compact_choices(raw: Any) -> dict:
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


def public_question(item: dict, index: int) -> dict:
    q_type = q_type_value(item)
    question = (
        item.get("Q")
        or item.get("question_text")
        or item.get("question")
        or item.get("mcq_stem")
        or item.get("original_question")
        or question_from_tagged_content(item.get("content"))
    )
    question = str(question or "").strip()
    if not question:
        raise GenerationError(f"Item {index}: question text is required.")

    public = {
        "item_index": index,
        "id": item.get("id") or item.get("content_id") or item.get("passage_id") or index,
        "passage_id": item.get("passage_id"),
        "passage_reference": item.get("passage_reference") or item.get("title"),
        "q_type": q_type,
        "question": question,
    }
    local_passage = (
        item.get("local_passage")
        or item.get("answer_passage")
        or item.get("qa_passage")
    )
    if isinstance(local_passage, str) and local_passage.strip():
        public["local_passage"] = local_passage.strip()

    if q_type == "mcq":
        choices = compact_choices(
            item.get("A")
            if isinstance(item.get("A"), (dict, list))
            else item.get("mcq_choices") or item.get("mcq_options") or item.get("choices")
        )
        missing = [label for label in CHOICE_LABELS if not choices.get(label)]
        if missing:
            raise GenerationError(
                f"Item {index}: MCQ choices missing labels: {', '.join(missing)}"
            )
        public["choices"] = choices

    return public


def public_questions(items: Iterable[dict]) -> List[dict]:
    return [
        public_question(item, index)
        for index, item in enumerate(expanded_items(items), start=1)
    ]


def prompt_question(question: dict) -> dict:
    public = {
        "q_type": question["q_type"],
        "question": question["question"],
    }
    if question["q_type"] == "mcq":
        public["choices"] = question["choices"]
    return public


def batched(items: List[dict], batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def index_passage_verses(passage: str) -> dict[int, List[str]]:
    matches = []
    for match in VERSE_MARKER_RE.finditer(passage):
        verse_number = int(match.group(1))
        if 1 <= verse_number <= 200:
            matches.append((verse_number, match.start()))

    verses = {}
    for index, (verse_number, start) in enumerate(matches):
        end = matches[index + 1][1] if index + 1 < len(matches) else len(passage)
        verse_text = passage[start:end].strip()
        if verse_text:
            verses.setdefault(verse_number, []).append(verse_text)
    return verses


def verse_range_from_reference(reference: Any) -> tuple[int, int] | None:
    match = PASSAGE_REFERENCE_RE.search(str(reference or ""))
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if end < start:
        start, end = end, start
    return start, end


def local_passage_for_question(
    passage: str,
    verse_index: dict[int, List[str]],
    question: dict,
    verse_window: int | None,
) -> str:
    if verse_window is None or not verse_index:
        return passage

    reference_range = verse_range_from_reference(question.get("passage_reference"))
    if not reference_range:
        return passage

    reference_start, reference_end = reference_range
    first_verse = max(min(verse_index), reference_start - verse_window)
    last_verse = min(max(verse_index), reference_end + verse_window)
    selected = []
    for verse_number in range(first_verse, last_verse + 1):
        selected.extend(verse_index.get(verse_number, []))
    return "\n".join(selected).strip() or passage


def extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text

    chunks = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    if chunks:
        return "\n".join(chunks)
    raise GenerationError("Model response did not include text output.")


def extract_json_text(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.DOTALL).strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        value = "\n".join(lines).strip()

    array_start = value.find("[")
    object_start = value.find("{")
    if array_start == -1 and object_start == -1:
        return value
    if object_start != -1 and (array_start == -1 or object_start < array_start):
        end = value.rfind("}")
        if end != -1 and end > object_start:
            return value[object_start : end + 1]
    if array_start != -1:
        end = value.rfind("]")
        if end != -1 and end > array_start:
            return value[array_start : end + 1]
    return value


def unwrap_answer_array(raw_answers: Any) -> Any:
    if isinstance(raw_answers, list):
        return raw_answers
    if isinstance(raw_answers, dict):
        for key in ("answers", "items", "results", "responses", "data"):
            value = raw_answers.get(key)
            if isinstance(value, list):
                return value
    return raw_answers


def looks_like_passage_excerpt(value: str) -> bool:
    text = value.strip()
    verse_markers = re.findall(r"(?<![\w\]])\d{1,3}\s+", text)
    return len(verse_markers) >= 2 or ("\n" in text and len(text) > 120)


def compact_passage_excerpt(value: str, question_text: str) -> str:
    text = re.sub(r"(?<![\w\]])\d{1,3}\s+", "", value.strip())
    pieces = [
        piece.strip(" \t\r\n。！？!?,，、；;")
        for piece in re.split(r"[\n。！？!?]+", text)
        if piece.strip(" \t\r\n。！？!?,，、；;")
    ]
    if not pieces:
        return text

    question_chars = {
        char
        for char in question_text
        if "\u4e00" <= char <= "\u9fff"
        and char not in {"什", "么", "谁", "哪", "何", "的", "了", "吗", "？"}
    }

    def score(piece: str) -> tuple[int, int]:
        overlap = sum(1 for char in set(piece) if char in question_chars)
        action_bonus = sum(
            2
            for marker in ("写", "名", "叫", "称", "站", "发生", "不能", "赞美", "预言")
            if marker in piece and marker in question_text
        )
        length_penalty = max(0, len(piece) - 80)
        return overlap + action_bonus - length_penalty, -len(piece)

    best = max(pieces, key=score)
    return best[:120].strip()


def answer_metadata(answer: dict) -> dict:
    return {
        "answer_confidence": normalize_answer_confidence(
            answer.get("answer_confidence")
        ),
        "insufficient_information": bool(
            answer.get("insufficient_information") or False
        ),
        "evidence_quality": normalize_evidence_quality(
            answer.get("evidence_quality")
        ),
    }


def validate_answers(
    raw_answers: Any,
    questions: List[dict],
    *,
    expanded_answer_format: bool,
    choice_mapper_client: Any | None = None,
    choice_mapper_model: str | None = None,
    retries: int = 0,
) -> List[dict]:
    if (
        isinstance(raw_answers, dict)
        and "generated_answer" in raw_answers
        and len(questions) == 1
    ):
        raw_answers = [{**raw_answers, "item_index": questions[0]["item_index"]}]
    raw_answers = unwrap_answer_array(raw_answers)
    if not isinstance(raw_answers, list):
        raise GenerationError("Model response must be a JSON array.")

    by_index = {int(question["item_index"]): question for question in questions}
    answers = []
    for position, answer in enumerate(raw_answers):
        if not isinstance(answer, dict):
            raise GenerationError("Each generated answer must be an object.")
        raw_item_index = answer.get("item_index")
        if raw_item_index is None:
            question = questions[position] if position < len(questions) else None
            item_index = int(question["item_index"]) if question else 0
        else:
            item_index = int(raw_item_index or 0)
            question = by_index.get(item_index)
        if not question:
            raise GenerationError(f"Model returned unknown item_index: {item_index}")

        output = {
            "item_index": item_index,
            "id": question.get("id"),
            "passage_id": question.get("passage_id"),
            "passage_reference": question.get("passage_reference"),
            "q_type": question["q_type"],
            "question": question["question"],
            "generated_answer": str(answer.get("generated_answer") or "").strip(),
        }
        if expanded_answer_format:
            output.update(answer_metadata(answer))
        if not output["generated_answer"]:
            raise GenerationError(f"Item {item_index}: generated_answer is empty.")
        if question["q_type"] != "mcq" and looks_like_passage_excerpt(
            output["generated_answer"]
        ):
            output["generated_answer"] = compact_passage_excerpt(
                output["generated_answer"],
                question["question"],
            )

        if question["q_type"] == "mcq":
            raw_choice = str(answer.get("selected_choice") or "").strip().upper()
            choice_source = None
            if raw_choice[:1] in CHOICE_LABELS:
                choice = raw_choice[:1]
                choice_source = "rules"
            elif raw_choice:
                choice = selected_choice_from_raw_answer(question, raw_choice)
                if choice:
                    choice_source = "rules"
            else:
                choice = None
            if not choice:
                choice = selected_choice_from_raw_answer(
                    question,
                    output["generated_answer"],
                )
                if choice:
                    choice_source = "rules"
            if not choice and choice_mapper_client is not None and choice_mapper_model:
                choice = openai_closest_mcq_choice(
                    choice_mapper_client,
                    choice_mapper_model,
                    raw_answer=output["generated_answer"],
                    choices=question["choices"],
                    retries=retries,
                )
                if choice:
                    choice_source = "openai"
            if not choice:
                raise AnswerParseError(
                    f"Item {item_index}: MCQ answer must be A, B, C, or D.",
                    json.dumps(answer, ensure_ascii=False),
                )
            output["mcq_choices"] = question["choices"]
            output["selected_choice"] = choice
            output["selected_choice_text"] = question["choices"][choice]
            if choice_source:
                output["selected_choice_source"] = choice_source
            if choice_source == "openai":
                output["raw_model_answer"] = output["generated_answer"]
            output["generated_answer"] = question["choices"][choice]

        answers.append(output)

    if len(answers) != len(questions):
        raise GenerationError(
            f"Model returned {len(answers)} answer(s), expected {len(questions)}."
        )
    return sorted(answers, key=lambda item: item["item_index"])


def build_generation_prompt(
    passage: str,
    questions: List[dict],
    *,
    expanded_answer_format: bool,
) -> dict:
    prompt_questions = [prompt_question(question) for question in questions]
    output_schema = [
        {
            "generated_answer": "简体中文答案",
            **(
                {"selected_choice": "A/B/C/D"}
                if question["q_type"] == "mcq"
                else {}
            ),
            **(
                {
                    "answer_confidence": 0.0,
                    "insufficient_information": False,
                    "evidence_quality": "none|weak|indirect|direct",
                }
                if expanded_answer_format
                else {}
            ),
        }
        for question in questions
    ]
    output_rules = [
        "Return a JSON object with exactly one key: answers.",
        "answers must be an array.",
        "Return exactly one answers array element for each input question.",
        "Keep answers in the same order as the input questions.",
        "Use only information explicitly present in the supplied passage and question.",
        "Do not use prior knowledge or canonical Bible facts.",
        "Use Simplified Chinese characters in generated_answer.",
        "Do not include verse numbers in generated_answer.",
        "Do not include multiple verses or copied passage text in generated_answer.",
        "For open questions, generated_answer should usually be under 20 Chinese characters.",
        "For MCQ items, selected_choice is required and must be exactly A, B, C, or D.",
        "Do not include hidden answer fields from the QA set.",
    ]
    if expanded_answer_format:
        output_rules.extend(
            [
                "answer_confidence must be a number from 0.0 to 1.0.",
                "insufficient_information must be true when the supplied passage does not contain enough evidence.",
                "evidence_quality must be one of: none, weak, indirect, direct.",
            ]
        )
    return {
        "task": (
            "Read the Chinese Bible passage and answer only the provided Chinese QA "
            "questions. The ground-truth answers are hidden. Use only the passage "
            "and the questions supplied in this prompt. Do not rely on prior "
            "knowledge, memorized Bible content, or outside context. If the passage "
            "differs from something you know, the passage in this prompt is the only "
            "authority. "
            "For open questions, write only the shortest Simplified Chinese "
            "phrase or sentence that directly answers the question. Do not copy "
            "a verse span or passage excerpt. "
            "For multiple-choice questions, choose exactly one letter: A, B, C, or D. "
            "Also include the chosen answer text in Simplified Chinese."
        ),
        "passage": passage,
        "questions": prompt_questions,
        "output_schema": {"answers": output_schema},
        "output_rules": output_rules,
    }


def generate_openai_batch(
    client: Any,
    model: str,
    passage: str,
    questions: List[dict],
    *,
    expanded_answer_format: bool,
    choice_mapper_client: Any | None = None,
    choice_mapper_model: str | None = None,
    retries: int = 0,
) -> List[dict]:
    prompt = build_generation_prompt(
        passage,
        questions,
        expanded_answer_format=expanded_answer_format,
    )
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You are an evaluator answer generator. Return valid JSON only. "
                    "Use only the supplied passage and questions. Do not use prior "
                    "knowledge, memorized Bible content, or outside facts. If your "
                    "knowledge conflicts with the supplied passage, the supplied passage "
                    "is the only authority. Return short direct answers only; do not "
                    "copy passage excerpts or include verse numbers. Do not include "
                    "markdown or explanations."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    try:
        raw_answers = json.loads(extract_json_text(extract_response_text(response)))
    except json.JSONDecodeError as exc:
        raise GenerationError(f"Model returned invalid JSON: {exc}") from exc
    return validate_answers(
        raw_answers,
        questions,
        expanded_answer_format=expanded_answer_format,
        choice_mapper_client=choice_mapper_client,
        choice_mapper_model=choice_mapper_model,
        retries=retries,
    )


def build_raw_answer_prompt(
    passage: str,
    question: dict,
    *,
    expanded_answer_format: bool,
) -> str:
    lines = [
        "Read the passage and answer the question using only the passage.",
        "Give only the shortest phrase or sentence that directly answers the question.",
        "Do not include verse numbers.",
        "Do not copy a verse span or passage excerpt.",
        "Do not repeat or echo the question.",
        "Do not add labels, numbering, explanations, markdown, or extra text.",
        "Use Simplified Chinese.",
    ]
    if expanded_answer_format:
        schema = (
            '{"generated_answer":"简体中文答案","answer_confidence":0.0,'
            '"insufficient_information":false,"evidence_quality":"none"}'
        )
        if question["q_type"] == "mcq":
            schema = (
                '{"selected_choice":"A","generated_answer":"选项文本",'
                '"answer_confidence":0.0,"insufficient_information":false,'
                '"evidence_quality":"direct"}'
            )
        lines.extend(
            [
                "Return only valid JSON.",
                "Use this schema:",
                schema,
                "answer_confidence must be between 0.0 and 1.0.",
                "insufficient_information must be true when the supplied passage does not contain enough evidence.",
                "evidence_quality must be one of: none, weak, indirect, direct.",
            ]
        )
    else:
        lines.append("Return only the answer text.")
    if question["q_type"] == "mcq":
        lines.extend(
            [
                "For multiple choice, choose the option best supported by explicit passage evidence.",
                (
                    "You must set selected_choice to exactly one uppercase letter: A, B, C, or D. "
                    "Do not answer MCQ questions in free text only. "
                    "generated_answer must be the selected option text, not a new paraphrase."
                    if expanded_answer_format
                    else "Return only one uppercase letter: A, B, C, or D."
                ),
            ]
        )

    lines.extend(["", "Passage:", passage, "", "Question:", question["question"]])
    if question["q_type"] == "mcq":
        lines.append("")
        lines.append("Choices:")
        for label in CHOICE_LABELS:
            lines.append(f"{label}. {question['choices'][label]}")
    return "\n".join(lines)


def apply_no_think(prompt: str) -> str:
    return "/no_think\n\n" + prompt


EVIDENCE_QUALITY_VALUES = {"none", "weak", "indirect", "direct"}


def normalize_answer_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def normalize_evidence_quality(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "no": "none",
        "none": "none",
        "unsupported": "none",
        "low": "weak",
        "weak": "weak",
        "inferred": "indirect",
        "inferential": "indirect",
        "indirect": "indirect",
        "clear": "direct",
        "explicit": "direct",
        "direct": "direct",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in EVIDENCE_QUALITY_VALUES else "none"


def normalize_answer_text(value: str) -> str:
    normalized = re.sub(r"[\s。！？!?,，、：:；;\"'“”‘’（）()［］\[\]]+", "", value).lower()
    equivalents = {
        "accept": "接受",
        "receive": "接受",
        "people": "人",
        "test": "试炼",
        "testing": "试炼",
        "fallaway": "跌倒",
        "猪群": "猪中",
        "猪里": "猪中",
        "到猪": "进入猪",
        "去猪": "进入猪",
        "道": "话语",
        "听道": "听话语",
        "果子": "结果",
        "得果": "结果",
        "结出果": "结果",
        "倒退": "跌倒",
        "绊倒": "跌倒",
        "复活": "灵魂回来起来",
        "活过来": "灵魂回来起来",
    }
    for source, target in equivalents.items():
        normalized = normalized.replace(source, target)
    return normalized


CHINESE_STOP_CHARS = set("的是了在人和与并就都也却但而被把给去来中里上下一这那他她它们个")


def chinese_bigrams(text: str) -> set[str]:
    chars = [
        char
        for char in text
        if "\u4e00" <= char <= "\u9fff" and char not in CHINESE_STOP_CHARS
    ]
    return {
        "".join(chars[index : index + 2])
        for index in range(len(chars) - 1)
    }


def meaningful_chars(text: str) -> set[str]:
    return {
        char
        for char in text
        if "\u4e00" <= char <= "\u9fff" and char not in CHINESE_STOP_CHARS
    }


def overlap_choice_from_answer(question: dict, normalized_answer: str) -> Optional[str]:
    if normalized_answer in {
        "听话语的人",
        "听了话语的人",
        "听话语人",
        "听了话语人",
    }:
        return None

    answer_bigrams = chinese_bigrams(normalized_answer)
    answer_chars = meaningful_chars(normalized_answer)
    if not answer_chars:
        return None

    scored = []
    for label in CHOICE_LABELS:
        normalized_choice = normalize_answer_text(question["choices"][label])
        choice_bigrams = chinese_bigrams(normalized_choice)
        choice_chars = meaningful_chars(normalized_choice)
        if not choice_chars:
            continue
        bigram_overlap = len(answer_bigrams & choice_bigrams)
        char_overlap = len(answer_chars & choice_chars)
        answer_coverage = char_overlap / len(answer_chars)
        choice_coverage = char_overlap / len(choice_chars)
        scored.append(
            {
                "label": label,
                "bigram_overlap": bigram_overlap,
                "char_overlap": char_overlap,
                "answer_coverage": answer_coverage,
                "choice_coverage": choice_coverage,
            }
        )

    candidates = [
        row
        for row in scored
        if (
            row["bigram_overlap"] >= 1
            and row["char_overlap"] >= 2
            and row["answer_coverage"] >= 0.55
        )
        or (
            row["char_overlap"] >= 3
            and row["answer_coverage"] >= 0.70
            and row["choice_coverage"] >= 0.20
        )
    ]
    if not candidates:
        return None

    candidates.sort(
        key=lambda row: (
            row["bigram_overlap"],
            row["answer_coverage"],
            row["choice_coverage"],
            row["char_overlap"],
        ),
        reverse=True,
    )
    best = candidates[0]
    if len(candidates) > 1:
        second = candidates[1]
        if (
            best["bigram_overlap"] == second["bigram_overlap"]
            and abs(best["answer_coverage"] - second["answer_coverage"]) < 0.15
        ):
            return None
    return str(best["label"])


def clean_raw_answer(value: str) -> str:
    stripped = value.strip()
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if lines and len(set(lines)) == 1:
        return lines[0]
    return stripped


def selected_choice_from_raw_answer(question: dict, raw_answer: str) -> Optional[str]:
    stripped = raw_answer.strip().translate(FULLWIDTH_CHOICE_LABELS)
    upper_text = stripped.upper()
    first_nonspace = re.search(r"\S", upper_text)
    if first_nonspace and first_nonspace.group(0) in CHOICE_LABELS:
        return first_nonspace.group(0)

    label_patterns = [
        r"(?:答案|答|选择|选项|选|choice|answer)\s*(?:是|为|:|：)?\s*([ABCD])\b",
        r"\b([ABCD])\s*(?:是|为|:|：|\.|、|\))",
    ]
    for pattern in label_patterns:
        matches = re.findall(pattern, upper_text, flags=re.IGNORECASE)
        labels = {match.upper() for match in matches if match.upper() in CHOICE_LABELS}
        if len(labels) == 1:
            return next(iter(labels))

    standalone_labels = {
        match.group(1).upper()
        for match in re.finditer(r"(?<![A-Z])([ABCD])(?![A-Z])", upper_text)
    }
    if len(standalone_labels) == 1:
        return next(iter(standalone_labels))

    normalized_answer = normalize_answer_text(stripped)
    for label in CHOICE_LABELS:
        choice_text = question["choices"][label]
        normalized_choice = normalize_answer_text(choice_text)
        if normalized_answer == normalized_choice:
            return label
        if normalized_choice and normalized_choice in normalized_answer:
            return label
        if normalized_answer and normalized_answer in normalized_choice:
            return label

    overlap_choice = overlap_choice_from_answer(question, normalized_answer)
    if overlap_choice:
        return overlap_choice

    return None


def create_openai_text_response(client: Any, *, model: str, input: Any) -> Any:
    if hasattr(client, "responses"):
        return client.responses.create(model=model, input=input)
    if hasattr(client, "chat") and hasattr(client.chat, "completions"):
        messages = input
        if isinstance(input, str):
            messages = [{"role": "user", "content": input}]
        return client.chat.completions.create(model=model, messages=messages)
    raise GenerationError(
        "OpenAI client supports neither responses.create nor chat.completions.create."
    )


def openai_closest_mcq_choice(
    client: Any,
    model: str,
    *,
    raw_answer: str,
    choices: dict,
    retries: int,
) -> Optional[str]:
    prompt = {
        "task": (
            "Map the raw model answer to the closest one of the four MCQ choices. "
            "You must choose exactly one option, even if the raw answer is vague, "
            "partial, paraphrased, or does not match exactly. Use only the raw "
            "answer and choices supplied here."
        ),
        "raw_model_answer": str(raw_answer or ""),
        "choices": {label: str(choices[label]) for label in CHOICE_LABELS},
        "output_schema": {
            "selected_choice": "A | B | C | D",
            "rationale": "brief reason",
        },
    }
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            response = create_openai_text_response(
                client,
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a deterministic MCQ answer mapper. Return valid "
                            "JSON only. The selected_choice field must be exactly one "
                            "uppercase letter: A, B, C, or D."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            raw = json.loads(extract_json_text(extract_response_text(response)))
            choice = str(raw.get("selected_choice") or "").strip().upper()
            if choice[:1] in CHOICE_LABELS:
                return choice[:1]
            raise GenerationError("OpenAI MCQ mapper did not return A, B, C, or D.")
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise GenerationError(f"OpenAI MCQ mapper failed: {last_error}") from last_error


def raw_answer_to_output(
    raw_answer: str,
    question: dict,
    *,
    expanded_answer_format: bool,
    choice_mapper_client: Any | None = None,
    choice_mapper_model: str | None = None,
    retries: int = 0,
) -> dict:
    parsed_answer = None
    generated_answer = clean_raw_answer(raw_answer)
    raw_mcq_choice = None
    if question["q_type"] == "mcq":
        raw_mcq_choice = selected_choice_from_raw_answer(question, generated_answer)
    if expanded_answer_format:
        try:
            raw_json = json.loads(extract_json_text(generated_answer))
        except json.JSONDecodeError as exc:
            if question["q_type"] == "mcq" and raw_mcq_choice:
                parsed_answer = {}
            else:
                raise AnswerParseError(
                    f"Item {question['item_index']}: invalid JSON answer.",
                    generated_answer,
                ) from exc
        else:
            if not isinstance(raw_json, dict):
                raise AnswerParseError(
                    f"Item {question['item_index']}: JSON answer must be an object.",
                    generated_answer,
                )
            parsed_answer = raw_json
            generated_answer = str(raw_json.get("generated_answer") or "").strip()
    if not generated_answer:
        raise AnswerParseError(
            f"Item {question['item_index']}: generated_answer is empty.",
            clean_raw_answer(raw_answer),
        )
    choice = None
    choice_source = None
    if question["q_type"] == "mcq":
        if parsed_answer is not None:
            raw_choice = str(parsed_answer.get("selected_choice") or "").strip().upper()
            if raw_choice[:1] in CHOICE_LABELS:
                choice = raw_choice[:1]
                choice_source = "rules"
            elif raw_choice:
                choice = selected_choice_from_raw_answer(question, raw_choice)
                if choice:
                    choice_source = "rules"
            if not choice:
                choice = selected_choice_from_raw_answer(question, generated_answer)
                if choice:
                    choice_source = "rules"
        else:
            choice = raw_mcq_choice or selected_choice_from_raw_answer(
                question,
                generated_answer,
            )
            if choice:
                choice_source = "rules"
        if not choice and choice_mapper_client is not None and choice_mapper_model:
            choice = openai_closest_mcq_choice(
                choice_mapper_client,
                choice_mapper_model,
                raw_answer=generated_answer,
                choices=question["choices"],
                retries=retries,
            )
            if choice:
                choice_source = "openai"
        if not choice:
            raise AnswerParseError(
                f"Item {question['item_index']}: MCQ answer must be A, B, C, or D.",
                clean_raw_answer(raw_answer),
            )
        if choice not in CHOICE_LABELS:
            raise AnswerParseError(
                f"Item {question['item_index']}: MCQ answer must be A, B, C, or D.",
                clean_raw_answer(raw_answer),
            )
        generated_answer = question["choices"][choice]
    if question["q_type"] != "mcq" and looks_like_passage_excerpt(generated_answer):
        generated_answer = compact_passage_excerpt(
            generated_answer,
            question["question"],
        )

    output = {
        "item_index": question["item_index"],
        "id": question.get("id"),
        "passage_id": question.get("passage_id"),
        "passage_reference": question.get("passage_reference"),
        "q_type": question["q_type"],
        "question": question["question"],
        "generated_answer": generated_answer,
    }
    if expanded_answer_format:
        output.update(answer_metadata(parsed_answer or {}))
    if question["q_type"] == "mcq":
        output["mcq_choices"] = question["choices"]
        output["selected_choice"] = choice
        output["selected_choice_text"] = question["choices"][choice]
        if choice_source:
            output["selected_choice_source"] = choice_source
        if choice_source == "openai":
            output["raw_model_answer"] = clean_raw_answer(raw_answer)
    return output


def failed_answer_output(
    question: dict,
    error: Exception,
    *,
    expanded_answer_format: bool,
) -> dict:
    output = {
        "item_index": question["item_index"],
        "id": question.get("id"),
        "passage_id": question.get("passage_id"),
        "passage_reference": question.get("passage_reference"),
        "q_type": question["q_type"],
        "question": question["question"],
        "generated_answer": "",
        "generation_error": str(error),
    }
    raw_model_answer = getattr(error, "raw_model_answer", None)
    if raw_model_answer is not None:
        output["raw_model_answer"] = str(raw_model_answer)
    if expanded_answer_format:
        output.update(
            {
                "answer_confidence": 0.0,
                "insufficient_information": True,
                "evidence_quality": "none",
            }
        )
    if question["q_type"] == "mcq":
        output["mcq_choices"] = question["choices"]
        output["selected_choice"] = None
        output["selected_choice_text"] = None
    return output


def random_mcq_fallback_output(question: dict, error: Exception) -> dict:
    """Return a reproducible pseudo-random MCQ choice after an empty response."""
    choices = question["choices"]
    labels = [label for label in CHOICE_LABELS if label in choices]
    if not labels:
        raise GenerationError(
            f"Item {question['item_index']}: MCQ has no available fallback choices."
        )
    identity = "|".join(
        str(question.get(key) or "")
        for key in ("id", "passage_id", "item_index", "question")
    )
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    selected = labels[int.from_bytes(digest[:8], "big") % len(labels)]
    return {
        "item_index": question["item_index"],
        "id": question.get("id"),
        "passage_id": question.get("passage_id"),
        "passage_reference": question.get("passage_reference"),
        "q_type": "mcq",
        "question": question["question"],
        "generated_answer": choices[selected],
        "mcq_choices": choices,
        "selected_choice": selected,
        "selected_choice_text": choices[selected],
        "selected_choice_source": "random_empty_response_fallback",
        "generation_error": str(error),
    }


def is_empty_answer_error(error: Exception) -> bool:
    return (
        isinstance(error, AnswerParseError)
        and not str(getattr(error, "raw_model_answer", "") or "").strip()
        and "generated_answer is empty" in str(error)
    )


def generate_ollama_single_raw(
    *,
    base_url: str,
    model: str,
    passage: str,
    question: dict,
    no_think: bool,
    expanded_answer_format: bool,
    choice_mapper_client: Any | None = None,
    choice_mapper_model: str | None = None,
    retries: int = 0,
) -> dict:
    prompt = build_raw_answer_prompt(
        passage,
        question,
        expanded_answer_format=expanded_answer_format,
    )
    if no_think:
        prompt = apply_no_think(prompt)
    messages = [
        {
            "role": "system",
            "content": (
                "Answer from the translated passage only. Do not include verse numbers, "
                "guess, or use outside knowledge. "
                "Do not repeat or echo the passage text in the answer. "
                "Do not echo the question. Do not output markdown or explanations. "
                + (
                    "Return only valid JSON matching the requested schema."
                    if expanded_answer_format
                    else "Return only the raw answer text."
                )
            ),
        },
        {"role": "user", "content": prompt},
    ]
    options = {
        "temperature": 0,
        "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "8192")),
    }
    num_predict = os.getenv("OLLAMA_NUM_PREDICT")
    if num_predict:
        options["num_predict"] = int(num_predict)
    timeout = float(os.getenv("OLLAMA_TIMEOUT", "600"))

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise GenerationError(
            f"Could not reach Ollama at {base_url}. Is `ollama serve` running?"
        ) from exc

    content = ((data.get("message") or {}).get("content") or "").strip()
    return raw_answer_to_output(
        content,
        question,
        expanded_answer_format=expanded_answer_format,
        choice_mapper_client=choice_mapper_client,
        choice_mapper_model=choice_mapper_model,
        retries=retries,
    )


def generate_answers(
    passage: str,
    questions: List[dict],
    *,
    provider: str,
    model: str,
    ollama_base_url: str,
    batch_size: int,
    verse_window: int | None,
    retries: int,
    dry_run: bool,
    allow_partial_answers: bool,
    ollama_no_think: bool,
    expanded_answer_format: bool,
    mcq_choice_mapper: str,
    mcq_choice_model: str,
) -> List[dict]:
    if dry_run:
        return [
            {
                **question,
                "generated_answer": "",
                **(
                    {
                        "answer_confidence": 0.0,
                        "insufficient_information": True,
                        "evidence_quality": "none",
                    }
                    if expanded_answer_format
                    else {}
                ),
                **({"selected_choice": ""} if question["q_type"] == "mcq" else {}),
            }
            for question in questions
        ]

    client = None
    choice_mapper_client = None
    if provider == "openai" or mcq_choice_mapper == "openai":
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise GenerationError(
                "Install the openai package before running this script."
            ) from exc

        if not os.getenv("OPENAI_API_KEY"):
            raise GenerationError(
                "OPENAI_API_KEY is required for OpenAI answer generation or "
                "--mcq-choice-mapper openai unless --dry-run is used."
            )
        openai_client = OpenAI()
        if provider == "openai":
            client = openai_client
        if mcq_choice_mapper == "openai":
            choice_mapper_client = openai_client

    answers: List[dict] = []
    verse_index = index_passage_verses(passage) if verse_window is not None else {}
    if provider == "ollama" or verse_window is not None:
        batches = [[question] for question in questions]
    else:
        batches = batched(questions, batch_size)

    for batch in batches:
        batch_passage = batch[0].get("local_passage")
        if not batch_passage:
            batch_passage = (
                local_passage_for_question(passage, verse_index, batch[0], verse_window)
                if verse_window is not None
                else passage
            )
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                if provider == "ollama":
                    answers.extend(
                        [
                            generate_ollama_single_raw(
                                base_url=ollama_base_url,
                                model=model,
                                passage=batch_passage,
                            question=batch[0],
                            no_think=ollama_no_think,
                            expanded_answer_format=expanded_answer_format,
                            choice_mapper_client=choice_mapper_client,
                            choice_mapper_model=mcq_choice_model,
                            retries=retries,
                        )
                    ]
                )
                else:
                    answers.extend(
                        generate_openai_batch(
                            client,
                            model,
                            batch_passage,
                            batch,
                            expanded_answer_format=expanded_answer_format,
                            choice_mapper_client=choice_mapper_client,
                            choice_mapper_model=mcq_choice_model,
                            retries=retries,
                        )
                    )
                last_error = None
                break
            except Exception as exc:  # OpenAI SDK exceptions vary by version.
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(2**attempt)
        if last_error:
            if len(batch) == 1 and is_empty_answer_error(last_error):
                if batch[0]["q_type"] == "mcq":
                    answers.append(random_mcq_fallback_output(batch[0], last_error))
                else:
                    # Preserve the skipped open question as an explicit failed
                    # row; scoring records it as incorrect without aborting the
                    # remaining questions in the cell.
                    answers.append(
                        failed_answer_output(
                            batch[0],
                            last_error,
                            expanded_answer_format=expanded_answer_format,
                        )
                    )
                continue
            if allow_partial_answers and len(batch) == 1:
                answers.append(
                    failed_answer_output(
                        batch[0],
                        last_error,
                        expanded_answer_format=expanded_answer_format,
                    )
                )
                continue
            raise GenerationError(str(last_error)) from last_error
    return answers


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate answers from a Chinese passage and Chinese QA set."
    )
    parser.add_argument("passage_file", type=Path, help="Chinese passage text or JSON file.")
    parser.add_argument("qa_json", type=Path, help="Chinese QA JSON file.")
    parser.add_argument("output_json", type=Path, help="Generated answers JSON file.")
    parser.add_argument(
        "--provider",
        choices=("openai", "ollama"),
        default=os.getenv("EVALUATOR_PROVIDER", "openai"),
        help="Model provider. Default: EVALUATOR_PROVIDER or openai.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Model to use. Defaults to llama3.2:3b for Ollama, or "
            "OPENAI_EVALUATOR_MODEL/gpt-4.1-mini for OpenAI."
        ),
    )
    parser.add_argument(
        "--ollama-base-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        help="Ollama server base URL. Default: OLLAMA_BASE_URL or localhost:11434.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help=(
            "Questions to answer per model call when --verse-window is -1. "
            "Default: 5."
        ),
    )
    parser.add_argument(
        "--verse-window",
        type=int,
        default=2,
        help=(
            "Verses before/after each question's passage_reference to send. "
            "Default: 2. Use -1 to send the full passage and allow batching."
        ),
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retry count per batch. Default: 2.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write redacted question payloads without calling the model.",
    )
    parser.add_argument(
        "--allow-partial-answers",
        action="store_true",
        help=(
            "Write failed item records instead of aborting when a question fails "
            "after retries. Failed MCQs use selected_choice null."
        ),
    )
    parser.add_argument(
        "--ollama-no-think",
        action="store_true",
        help="Prefix Ollama prompts with /no_think for Qwen3-style thinking models.",
    )
    parser.add_argument(
        "--expanded-answer-format",
        action="store_true",
        help=(
            "Ask the answer model to also return answer_confidence, "
            "insufficient_information, and evidence_quality."
        ),
    )
    parser.add_argument(
        "--mcq-choice-mapper",
        choices=("rules", "openai"),
        default=os.getenv("MCQ_CHOICE_MAPPER", "rules"),
        help=(
            "How to map raw MCQ answers to A-D. rules uses deterministic parsing. "
            "openai uses rules first, then asks OpenAI to choose the closest option. "
            "Default: MCQ_CHOICE_MAPPER or rules."
        ),
    )
    parser.add_argument(
        "--mcq-choice-model",
        default=os.getenv("OPENAI_MCQ_CHOICE_MODEL", "gpt-4.1-mini"),
        help=(
            "OpenAI model for --mcq-choice-mapper openai. "
            "Default: OPENAI_MCQ_CHOICE_MODEL or gpt-4.1-mini."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        print("--batch-size must be at least 1", file=sys.stderr)
        return 2
    if args.verse_window < -1:
        print("--verse-window must be -1 or greater", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("--retries must be zero or greater", file=sys.stderr)
        return 2

    try:
        model = args.model
        if not model:
            if args.provider == "ollama":
                model = os.getenv("OLLAMA_EVALUATOR_MODEL", "llama3.2:3b")
            else:
                model = os.getenv("OPENAI_EVALUATOR_MODEL", "gpt-4.1-mini")
        passage = load_passage(args.passage_file)
        questions = public_questions(load_qa_items(args.qa_json))
        answers = generate_answers(
            passage,
            questions,
            provider=args.provider,
            model=model,
            ollama_base_url=args.ollama_base_url,
            batch_size=args.batch_size,
            verse_window=None if args.verse_window < 0 else args.verse_window,
            retries=args.retries,
            dry_run=args.dry_run,
            allow_partial_answers=args.allow_partial_answers,
            ollama_no_think=args.ollama_no_think,
            expanded_answer_format=args.expanded_answer_format,
            mcq_choice_mapper=args.mcq_choice_mapper,
            mcq_choice_model=args.mcq_choice_model,
        )
        write_json(args.output_json, answers)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(answers)} generated answer(s) to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
