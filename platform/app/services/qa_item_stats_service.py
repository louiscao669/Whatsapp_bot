"""Response statistics for QA item detail (stats tab)."""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from eten_shared.models import ParticipantResponse, QAItem
from eten_shared.mcq import (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_TF,
    choice_letters_for_type,
    choice_response_letter,
    is_choice_scored_item,
)
from app.services.system_languages_service import (
    get_registered_system_languages,
    parse_selected_languages,
    response_language_for_qa,
    sync_system_languages_registry,
)
from app.utils.admin_formatters import format_display_datetime


OPEN_RESPONSE_STATUS_LABELS = {
    "pending": "Pending",
    "yes (auto)": "Auto-correct",
    "no (auto)": "Auto-incorrect",
    "yes (expert)": "Expert-correct",
    "no (expert)": "Expert-incorrect",
}


def open_response_status_label(is_correct: str) -> str:
    value = (is_correct or "").strip().lower()
    return OPEN_RESPONSE_STATUS_LABELS.get(value, is_correct or "Unknown")


def format_choice_correctness_label(is_correct: str) -> str:
    value = (is_correct or "").strip().lower()
    if value.startswith("yes"):
        return "correct"
    return "incorrect"


def format_choice_response_answer_display(qa_item, response) -> str:
    stored = (response.response_text or "").strip().upper()
    if len(stored) == 1 and stored in {"A", "B", "C", "D"}:
        return stored
    analysis_text = response.transcript_text or response.response_text or ""
    letter = choice_response_letter(qa_item, analysis_text)
    return letter or "—"


def _truncate_text(value, max_length=80):
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def filter_responses_by_languages(responses, selected_languages):
    if not selected_languages:
        return list(responses)
    language_set = set(selected_languages)
    return [
        response
        for response in responses
        if response_language_for_qa(response) in language_set
    ]


def compute_response_stats(qa_item: QAItem, responses):
    question_type = (qa_item.question_type or QUESTION_TYPE_OPEN).strip().lower()
    total = len(responses)
    stats = {
        "question_type": question_type,
        "total_responses": total,
        "summary_cards": [],
        "bar_chart": [],
        "correct_choice": None,
    }

    if question_type == QUESTION_TYPE_OPEN:
        counts = {label: 0 for label in OPEN_RESPONSE_STATUS_LABELS.values()}
        for response in responses:
            label = open_response_status_label(response.is_correct)
            counts[label] = counts.get(label, 0) + 1
        stats["summary_cards"] = [
            {"label": label, "count": counts.get(label, 0)}
            for label in OPEN_RESPONSE_STATUS_LABELS.values()
        ]
        if counts.get("Unknown", 0):
            stats["summary_cards"].append({"label": "Unknown", "count": counts["Unknown"]})
        return stats

    correct = 0
    incorrect = 0
    for response in responses:
        if format_choice_correctness_label(response.is_correct) == "correct":
            correct += 1
        else:
            incorrect += 1
    stats["summary_cards"] = [
        {"label": "Correct", "count": correct},
        {"label": "Incorrect", "count": incorrect},
    ]

    if question_type == QUESTION_TYPE_MCQ:
        letters = list(choice_letters_for_type(QUESTION_TYPE_MCQ))
        distribution = {letter: 0 for letter in letters}
        unparsed = 0
        for response in responses:
            letter = format_choice_response_answer_display(qa_item, response)
            if letter in distribution:
                distribution[letter] += 1
            else:
                unparsed += 1
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        stats["correct_choice"] = correct_letter or None
        stats["bar_chart"] = [
            {
                "letter": letter,
                "count": distribution[letter],
                "is_correct": letter == correct_letter,
            }
            for letter in letters
        ]
        if unparsed:
            stats["bar_chart"].append({"letter": "—", "count": unparsed, "is_correct": False})

    return stats


def build_stats_participant_rows(qa_item: QAItem, responses):
    choice_scored = is_choice_scored_item(qa_item)
    rows = []
    for response in responses:
        participant = response.participant
        participant_label = ""
        if participant:
            participant_label = participant.display_name or participant.wa_id or participant.id

        if choice_scored:
            correctness = format_choice_correctness_label(response.is_correct)
            answer_value = format_choice_response_answer_display(qa_item, response)
        else:
            correctness = open_response_status_label(response.is_correct)
            answer_value = _truncate_text(response.transcript_text or response.response_text or "")

        rows.append(
            {
                "participant": participant_label,
                "language": response_language_for_qa(response),
                "received_at": format_display_datetime(response.received_at),
                "response_type": response.response_type,
                "answer": answer_value,
                "correctness": correctness,
            }
        )
    return rows


def get_qa_item_stats(db, qa_item_id: str, *, language_filter=None):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        return None

    sync_system_languages_registry(db)
    language_options = sorted(set(get_registered_system_languages(db)) - {""})
    selected_languages = parse_selected_languages(language_filter or [], "")
    if not selected_languages:
        selected_languages = list(language_options)

    responses = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.qa_item_id == qa_item_id)
        .options(selectinload(ParticipantResponse.participant))
        .order_by(ParticipantResponse.received_at.desc())
    ).all()
    filtered_responses = filter_responses_by_languages(responses, selected_languages)
    stats = compute_response_stats(qa_item, filtered_responses)

    return {
        "qa_item_id": qa_item.id,
        "question_type": stats["question_type"],
        "total_responses": stats["total_responses"],
        "selected_languages": selected_languages,
        "language_options": language_options,
        "summary_cards": stats["summary_cards"],
        "bar_chart": stats["bar_chart"],
        "correct_choice": stats["correct_choice"],
        "participants": build_stats_participant_rows(qa_item, filtered_responses),
    }
