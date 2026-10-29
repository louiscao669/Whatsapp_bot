"""Dashboard serialization services."""

import re

from eten_shared.domain.assignments import (
    assignment_passage_snapshot,
    surrounding_passage_text,
)
from eten_shared.domain.bible_books import qa_item_book
from eten_shared.mcq import is_choice_scored_item
from eten_shared.models import ParticipantResponse, QAItemRecording
from eten_shared.recordings import (
    get_latest_question_recording,
    participant_language_code,
)
from sqlalchemy import func, select

from backend.shared.response_labels import (
    format_choice_correctness_label,
    open_response_status_label,
)


def _iso_datetime(value):
    return value.isoformat() if value else None


def _luke_chapter_from_reference(passage_reference):
    # Admin-authored QA commonly uses "Luke 1:11" while the evaluation/pilot
    # importer uses "1:11" (and occasionally "1:35(#2)"). Both identify the
    # same dashboard chapter and must be visible to regular participants.
    match = re.match(
        r"^(?:luke\s+)?(?P<chapter>\d+):\d+(?:\(#\d+\))?",
        str(passage_reference or "").strip(),
        re.IGNORECASE,
    )
    return int(match.group("chapter")) if match else None


# "Judges 9:1-57", "2 Kings 6:24-7:20", "1 Kings 13:1-34", "Luke 1:11".
_BOOK_REFERENCE = re.compile(
    r"^(?P<book>.*?\S)\s+(?P<chapter>\d+):\d+"
    r"(?:\s*[-\u2013]\s*(?:(?P<end_chapter>\d+):)?\d+)?"
)
_LEGACY_BOOK = "luke"
# Books whose questions belong to the IRB study (tier-1 passages). The approved
# protocol (26-08-10268) says accuracy is never shown to participants, so the
# dashboard withholds correctness and the answer key for these items. Luke is
# the pre-study WhatsApp set and keeps its existing feedback.
_FEEDBACK_VISIBLE_BOOKS = {_LEGACY_BOOK}


def _book_display_name(book):
    words = str(book or "").split()
    return " ".join(
        word if word.isdigit() else (word if word == "of" else word.capitalize())
        for word in words
    )


def dashboard_book_chapter(qa_item):
    """``(book, chapter, label)`` grouping a QA item on the dashboard, or None.

    ``book`` is the canonical lower-case name from ``bible_books`` ("judges",
    "2 kings"); ``label`` is what the participant sees ("Judges 9",
    "Judges 17\u201318" for a passage that spans two chapters). Legacy bare
    references ("1:11") with no identifiable book are read as Luke, matching
    the old Luke-only behaviour.
    """

    reference = str(getattr(qa_item, "passage_reference", None) or "").strip()
    book = qa_item_book(qa_item)
    match = _BOOK_REFERENCE.match(reference)
    if book and match:
        chapter = int(match.group("chapter"))
        end_chapter = match.group("end_chapter")
        label = f"{_book_display_name(book)} {chapter}"
        if end_chapter and int(end_chapter) != chapter:
            label = f"{label}\u2013{int(end_chapter)}"
        return book, chapter, label

    # Bare "chapter:verse" ("1:11", "9:5"): book from the passage id when it
    # names one, else Luke (the only book the regular flow used to carry).
    legacy_chapter = _luke_chapter_from_reference(reference)
    if legacy_chapter:
        book = book or _LEGACY_BOOK
        return book, legacy_chapter, f"{_book_display_name(book)} {legacy_chapter}"
    return None


def answer_feedback_hidden(qa_item):
    """True when the dashboard must not reveal correctness or the answer key."""

    located = dashboard_book_chapter(qa_item)
    book = located[0] if located else qa_item_book(qa_item)
    return bool(book) and book not in _FEEDBACK_VISIBLE_BOOKS


def _choice_text_for_letter(qa_item, letter):
    normalized = (letter or "").strip().upper()
    choices = list(qa_item.mcq_choices or [])
    if not normalized or len(normalized) != 1:
        return ""
    index = ord(normalized) - ord("A")
    if index < 0 or index >= len(choices):
        return ""
    return str(choices[index] or "").strip()


def _format_choice_answer(qa_item, letter):
    normalized = (letter or "").strip().upper()
    text = _choice_text_for_letter(qa_item, normalized)
    if normalized and text:
        return f"{normalized}. {text}"
    return normalized or "No answer recorded"


def _latest_answer_recording(db, qa_item, participant):
    language = participant_language_code(participant)
    statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id == qa_item.id,
        QAItemRecording.recording_type == "answer",
        func.lower(QAItemRecording.language) == language.lower(),
    )
    if is_choice_scored_item(qa_item):
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        if correct_letter:
            statement = statement.where(
                QAItemRecording.version == ord(correct_letter) - ord("A") + 1
            )
    return db.scalars(
        statement.order_by(
            QAItemRecording.version.desc(),
            QAItemRecording.created_at.desc(),
        )
    ).first()


def _latest_question_audio_url(db, qa_item, participant):
    language = participant_language_code(participant)
    recording = get_latest_question_recording(db, qa_item.id, language)
    if recording:
        return f"/user-dashboard/api/{participant.id}/qa-question-recording/{recording.id}/audio"
    return qa_item.audio_url


def _serialize_dashboard_question(
    db,
    participant,
    assignment,
    qa_item,
    *,
    question_index=0,
):
    located = dashboard_book_chapter(qa_item)
    chapter_number = located[1] if located else None
    return {
        "assignment_id": assignment.id,
        "batch_id": assignment.batch_id,
        "question_index": max(int(question_index or 0), 0),
        "book": _book_display_name(located[0]) if located else None,
        "chapter": chapter_number,
        "chapter_label": located[2] if located else None,
        "passage_reference": qa_item.passage_reference,
        "passage_text": assignment_passage_snapshot(assignment)
        or surrounding_passage_text(db, assignment)
        or qa_item.passage_text,
        "question": qa_item.question_text,
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "mcq_choices": list(qa_item.mcq_choices or []),
        "audio_url": _latest_question_audio_url(db, qa_item, participant),
        "status": "current",
    }


def _serialize_completed_question_review(db, participant, assignment, qa_item):
    response = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.assignment_id == assignment.id)
        .order_by(ParticipantResponse.received_at.desc(), ParticipantResponse.id.desc())
    ).first()
    if not response:
        return None

    choice_scored = is_choice_scored_item(qa_item)
    if choice_scored:
        user_letter = (response.response_text or "").strip().upper()
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        participant_answer = _format_choice_answer(qa_item, user_letter)
        correct_answer = _format_choice_answer(qa_item, correct_letter)
        correctness = format_choice_correctness_label(response.is_correct)
    else:
        participant_answer = (
            response.transcript_text or response.response_text or ""
        ).strip() or "No answer recorded"
        correct_answer = (qa_item.expected_answer or "").strip() or "No answer recorded"
        correctness = open_response_status_label(response.is_correct)

    response_audio_url = (
        f"/user-dashboard/api/{participant.id}/participant-response/{response.id}/audio"
        if (response.media_url or "").strip()
        else None
    )
    feedback_hidden = answer_feedback_hidden(qa_item)
    if feedback_hidden:
        correct_answer = None
        correctness = None
    correct_recording = (
        None if feedback_hidden else _latest_answer_recording(db, qa_item, participant)
    )
    return {
        "question": qa_item.question_text,
        "passage_reference": qa_item.passage_reference,
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "participant_answer": participant_answer,
        "participant_audio_url": response_audio_url,
        "correct_answer": correct_answer,
        "correct_audio_url": (
            f"/user-dashboard/api/{participant.id}/qa-answer-recording/{correct_recording.id}/audio"
            if correct_recording
            else None
        ),
        "correctness": correctness,
        "feedback_hidden": feedback_hidden,
        "submitted_at": _iso_datetime(response.received_at),
    }
