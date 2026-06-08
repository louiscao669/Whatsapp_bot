"""Multiple-choice and true/false question helpers."""

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.services.keyword_matching_service import normalize_response_text

MCQ_LABELS = ("A", "B", "C", "D")
QUESTION_TYPE_OPEN = "open"
QUESTION_TYPE_MCQ = "mcq"
QUESTION_TYPE_TF = "tf"
VALID_QUESTION_TYPES = frozenset({QUESTION_TYPE_OPEN, QUESTION_TYPE_MCQ, QUESTION_TYPE_TF})

CHOICE_LINE_PATTERN = re.compile(r"^\s*([A-D])\.\s*(.+)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class ParsedLabeledContent:
    question_type: str
    question_text: str
    mcq_choices: List[str]
    mcq_correct_choice: Optional[str]
    expected_answer: str


def question_type_value(qa_item) -> str:
    raw = getattr(qa_item, "question_type", None) or QUESTION_TYPE_OPEN
    normalized = str(raw).strip().lower() or QUESTION_TYPE_OPEN
    if normalized not in VALID_QUESTION_TYPES:
        return QUESTION_TYPE_OPEN
    return normalized


def is_choice_scored_item(qa_item) -> bool:
    return question_type_value(qa_item) in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF}


def choice_letters_for_type(question_type: str) -> Tuple[str, ...]:
    if question_type == QUESTION_TYPE_TF:
        return ("A", "B")
    if question_type == QUESTION_TYPE_MCQ:
        return MCQ_LABELS
    return ()


def expected_choice_count(question_type: str) -> int:
    if question_type == QUESTION_TYPE_TF:
        return 2
    if question_type == QUESTION_TYPE_MCQ:
        return 4
    return 0


def parse_mcq_correct_letter(raw) -> str:
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        raise ValueError("Correct choice is required (A, B, C, or D).")

    letter = str(raw).strip().upper()
    if len(letter) != 1 or letter not in MCQ_LABELS:
        raise ValueError("Correct choice must be a single letter A, B, C, or D.")
    return letter


def normalize_labeled_choices(raw, question_type: str) -> List[str]:
    required = expected_choice_count(question_type)
    if required == 0:
        return []

    if raw is None:
        raise ValueError("Choices are required for mcq and tf questions.")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("Choices are required for mcq and tf questions.")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in text.splitlines() if part.strip()]
        raw = parsed
    if not isinstance(raw, list):
        raise ValueError("Choices must be a list of strings.")

    choices = [str(choice).strip() for choice in raw if str(choice).strip()]
    if len(choices) != required:
        label = "four" if required == 4 else "two"
        raise ValueError(f"{question_type} requires exactly {label} non-empty choices.")
    return choices


def expected_answer_for_choice(choices: List[str], correct_letter: str) -> str:
    letters = choice_letters_for_type(
        QUESTION_TYPE_TF if len(choices) == 2 else QUESTION_TYPE_MCQ
    )
    if correct_letter not in letters[: len(choices)]:
        raise ValueError(f"Correct choice {correct_letter} is not valid for this question.")
    index = letters.index(correct_letter)
    return choices[index]


def parse_choice_lines_from_text(block: str) -> Tuple[List[str], str]:
    """Split labeled question body into ordered choice texts and stem."""
    choices_by_letter: Dict[str, str] = {}
    stem_lines: List[str] = []

    for line in (block or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = CHOICE_LINE_PATTERN.match(stripped)
        if match:
            choices_by_letter[match.group(1).upper()] = match.group(2).strip()
        else:
            stem_lines.append(stripped)

    ordered_letters = [letter for letter in MCQ_LABELS if letter in choices_by_letter]
    choices = [choices_by_letter[letter] for letter in ordered_letters]
    stem = "\n\n".join(stem_lines).strip()
    return choices, stem


def infer_question_type_from_choice_count(count: int) -> str:
    if count == 4:
        return QUESTION_TYPE_MCQ
    if count == 2:
        return QUESTION_TYPE_TF
    return QUESTION_TYPE_OPEN


def parse_mcq_response_letter(
    response_text: str,
    choices: List[str],
    *,
    question_type: str,
) -> Optional[str]:
    text = (response_text or "").strip()
    if not text:
        return None

    valid_letters = choice_letters_for_type(question_type)

    mcq_id_match = re.match(r"^mcq_([0-3])$", text, flags=re.IGNORECASE)
    if mcq_id_match:
        index = int(mcq_id_match.group(1))
        if index < len(valid_letters):
            return valid_letters[index]

    if len(text) == 1 and text.upper() in valid_letters:
        return text.upper()

    lower = text.lower()
    for letter in valid_letters[: len(choices)]:
        choice = choices[valid_letters.index(letter)]
        choice_lower = choice.lower()
        if lower == choice_lower or choice_lower in lower or lower in choice_lower:
            return letter
    return None


def format_choices_for_display(choices: List[str], question_type: str) -> str:
    letters = choice_letters_for_type(question_type)
    lines = []
    for index, choice in enumerate(choices):
        if index < len(letters):
            lines.append(f"{letters[index]}. {choice}")
    return "\n".join(lines)


def choice_response_letter(qa_item, response_text: str) -> Optional[str]:
    """Parsed participant choice letter (A–D or A–B), or None if unparseable."""
    question_type = question_type_value(qa_item)
    choices = normalize_labeled_choices(qa_item.mcq_choices, question_type)
    return parse_mcq_response_letter(
        response_text,
        choices,
        question_type=question_type,
    )


def choice_response_is_correct(qa_item, response_text: str) -> bool:
    """True if the reply matches the stored correct letter; False if wrong or unparseable."""
    selected_letter = choice_response_letter(qa_item, response_text)
    if selected_letter is None:
        return False
    correct_letter = parse_mcq_correct_letter(qa_item.mcq_correct_choice)
    return selected_letter == correct_letter


def validate_question_fields(
    question_type: str,
    mcq_choices,
    mcq_correct_choice,
    *,
    expected_answer: str = "",
) -> Tuple[str, List[str], Optional[str], str]:
    normalized_type = (question_type or QUESTION_TYPE_OPEN).strip().lower()
    if normalized_type not in VALID_QUESTION_TYPES:
        raise ValueError("question_type must be 'open', 'mcq', or 'tf'.")

    if normalized_type == QUESTION_TYPE_OPEN:
        answer = (expected_answer or "").strip()
        if not answer:
            raise ValueError("Expected answer is required.")
        return normalized_type, [], None, answer

    choices = normalize_labeled_choices(mcq_choices, normalized_type)
    letter = parse_mcq_correct_letter(mcq_correct_choice)
    valid_letters = choice_letters_for_type(normalized_type)
    if letter not in valid_letters[: len(choices)]:
        raise ValueError(
            f"Correct choice {letter} is invalid for {normalized_type} "
            f"(use {', '.join(valid_letters[: len(choices)])})."
        )
    return normalized_type, choices, letter, expected_answer_for_choice(choices, letter)
