"""Review Response dashboard and expert decisions."""

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from eten_shared.models import ParticipantResponse, QAItemRecording
from eten_shared.qa_keywords import get_all_language_keywords_for_qa_items
from app.utils.admin_formatters import format_correctness_score
from app.services.system_languages_service import (
    canonical_language_code,
    get_registered_system_languages,
    response_language_for_qa,
    sync_system_languages_registry,
)
from app.utils.media_urls import participant_response_media_url, qa_recording_media_url


class ReviewResponseError(Exception):
    pass


def _review_passage_sort_key(response):
    qa_item = response.qa_item
    received_at = response.received_at or datetime.min.replace(tzinfo=timezone.utc)
    received_sort = -received_at.timestamp()
    reference = (qa_item.passage_reference or qa_item.passage_id).strip() if qa_item else ""
    normalized = re.sub(r"\s+", " ", reference)
    match = re.search(r"^(.*?)(\d+):(\d+)\s*$", normalized)
    if match:
        book = match.group(1).strip().lower()
        chapter = int(match.group(2))
        verse = int(match.group(3))
        return (book, chapter, verse, received_sort)
    return (normalized.lower(), 0, 0, received_sort)


def _serialize_keywords(qa_item, language_keywords_row):
    if language_keywords_row:
        return {
            "required": list(language_keywords_row.required_keywords or []),
            "optional": list(language_keywords_row.optional_keywords or []),
        }
    if not qa_item:
        return {"required": [], "optional": []}
    return {
        "required": list(qa_item.required_keywords or []),
        "optional": list(qa_item.optional_keywords or []),
    }


def _serialize_prompt_recording(recording):
    if not recording:
        return None
    return {
        "recording_id": recording.id,
        "media_url": qa_recording_media_url(recording.id),
    }


def _serialize_answer(response):
    text = (response.transcript_text or response.response_text or "").strip()
    has_audio = bool((response.media_url or "").strip())
    return {
        "response_type": response.response_type,
        "text": text,
        "transcript": response.transcript_text or "",
        "audio_url": participant_response_media_url(response.id) if has_audio else None,
    }


def get_review_response_dashboard(db, *, language: str = ""):
    sync_system_languages_registry(db)
    selected_language = canonical_language_code(language)
    language_options = sorted(set(get_registered_system_languages(db)) - {""})

    responses = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.is_correct == "pending")
        .options(
            selectinload(ParticipantResponse.participant),
            selectinload(ParticipantResponse.qa_item),
        )
        .order_by(ParticipantResponse.received_at.desc())
    ).all()

    qa_item_ids = sorted({response.qa_item_id for response in responses if response.qa_item_id})
    recording_statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id.in_(qa_item_ids),
        QAItemRecording.recording_type == "question",
    )
    if selected_language:
        recording_statement = recording_statement.where(
            func.lower(QAItemRecording.language) == selected_language
        )
    prompt_recordings = db.scalars(
        recording_statement.order_by(QAItemRecording.created_at.desc())
    ).all()
    keywords_by_item_lang = get_all_language_keywords_for_qa_items(db, qa_item_ids)

    prompt_recording_map = {}
    for recording in prompt_recordings:
        language_code = canonical_language_code(recording.language)
        key = (recording.qa_item_id, recording.recording_type, language_code)
        existing = prompt_recording_map.get(key)
        if not existing or (recording.version, recording.created_at) > (
            existing.version,
            existing.created_at,
        ):
            prompt_recording_map[key] = recording

    filtered = []
    for response in responses:
        response_language = response_language_for_qa(response)
        if selected_language and response_language != selected_language:
            continue
        filtered.append(response)

    filtered.sort(key=_review_passage_sort_key)
    items = []
    for response in filtered:
        qa_item = response.qa_item
        response_language = response_language_for_qa(response)
        prompt_language = selected_language or response_language
        items.append(
            {
                "response_id": response.id,
                "qa_item_id": response.qa_item_id,
                "language": response_language,
                "passage": (qa_item.passage_reference or qa_item.passage_id) if qa_item else "",
                "passage_text": qa_item.passage_text if qa_item else "",
                "question": qa_item.question_text if qa_item else "",
                "expected_answer_en": qa_item.expected_answer if qa_item else "",
                "keywords": _serialize_keywords(
                    qa_item,
                    keywords_by_item_lang.get((response.qa_item_id, response_language))
                    if response.qa_item_id
                    else None,
                ),
                "question_target_audio": _serialize_prompt_recording(
                    prompt_recording_map.get((response.qa_item_id, "question", prompt_language))
                ),
                "answer": _serialize_answer(response),
                "score": format_correctness_score(response.correctness_score),
                "is_correct": response.is_correct,
                "review_status": response.review_status,
            }
        )

    return {
        "language": selected_language or None,
        "language_options": language_options,
        "items": items,
    }


def apply_review_response_decision(db, response_id: str, decision: str):
    normalized = (decision or "").strip().lower()
    if normalized not in {"correct", "incorrect"}:
        raise ReviewResponseError("Decision must be correct or incorrect")

    response = db.get(ParticipantResponse, response_id)
    if not response:
        raise ReviewResponseError("Response not found")

    if normalized == "correct":
        response.is_correct = "yes (expert)"
        response.review_status = "reviewed"
        response.flag_reason = ""
    else:
        response.is_correct = "no (expert)"
        response.review_status = "reviewed"
        if not (response.flag_reason or "").strip():
            response.flag_reason = "Marked incorrect by expert review."

    return response
