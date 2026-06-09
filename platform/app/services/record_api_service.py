"""Read payloads for Record JSON API."""

from datetime import timezone

from sqlalchemy import func, select

from eten_shared.models import QAItemRecording
from eten_shared.media_storage import parse_storage_uri
from eten_shared.mcq import QUESTION_TYPE_MCQ, QUESTION_TYPE_OPEN, QUESTION_TYPE_TF
from app.services.qa_review_service import load_recordable_qa_items, sort_qa_items_by_passage
from app.services.system_languages_service import (
    canonical_language_code,
    get_registered_system_languages,
    sync_system_languages_registry,
)
from app.utils.admin_formatters import format_display_datetime
from app.utils.media_urls import qa_recording_media_url


def choice_answer_recording_version(letter: str) -> int:
    return ord(letter.upper()) - ord("A") + 1


def choice_letter_for_answer_recording(recording: QAItemRecording):
    if (recording.recording_type or "").strip().lower() != "answer":
        return None
    if recording.version < 1 or recording.version > 4:
        return None
    return chr(ord("A") + recording.version - 1)


def _iso_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def get_recordings_grouped_by_kind(db, qa_item_ids, language):
    if not qa_item_ids:
        return {}

    statement = select(QAItemRecording).where(QAItemRecording.qa_item_id.in_(qa_item_ids))
    if language:
        statement = statement.where(
            func.lower(QAItemRecording.language) == canonical_language_code(language)
        )

    recordings = db.scalars(
        statement.order_by(QAItemRecording.version.asc(), QAItemRecording.created_at.asc())
    ).all()
    grouped = {}
    for recording in recordings:
        key = (recording.qa_item_id, recording.recording_type)
        grouped.setdefault(key, []).append(recording)
    return grouped


def serialize_recording(recording: QAItemRecording | None, *, label_prefix: str):
    if not recording:
        return None
    has_storage = bool(parse_storage_uri(recording.storage_uri or ""))
    choice_letter = choice_letter_for_answer_recording(recording)
    label = format_recording_take_label(label_prefix, recording.version, recording.created_at)
    return {
        "id": recording.id,
        "recording_type": recording.recording_type,
        "language": recording.language,
        "version": recording.version,
        "choice_letter": choice_letter,
        "media_url": qa_recording_media_url(recording.id),
        "has_storage": has_storage,
        "created_at": _iso_datetime(recording.created_at),
        "label": label,
    }


def format_recording_take_label(recording_type_label, version, created_at):
    timestamp = format_display_datetime(created_at)
    return f"{recording_type_label} v{version} {timestamp}".strip()


def _serialize_answer_slots(qa_item, answer_recordings, language):
    question_type = (qa_item.question_type or QUESTION_TYPE_OPEN).strip().lower()
    recordings_by_version = {recording.version: recording for recording in answer_recordings}

    if question_type in {QUESTION_TYPE_MCQ, QUESTION_TYPE_TF}:
        choice_slots = 4 if question_type == QUESTION_TYPE_MCQ else 2
        choices = list(qa_item.mcq_choices or [])
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        slots = []
        for index in range(choice_slots):
            letter = chr(ord("A") + index)
            raw = choices[index] if index < len(choices) else ""
            version = choice_answer_recording_version(letter)
            recording = recordings_by_version.get(version)
            slots.append(
                {
                    "letter": letter,
                    "text": str(raw).strip(),
                    "is_correct": letter == correct_letter,
                    "recording": serialize_recording(recording, label_prefix="Answer"),
                }
            )
        return {"kind": question_type, "slots": slots}

    recording = max(answer_recordings, key=lambda row: (row.version, row.created_at), default=None)
    if recording is None and answer_recordings:
        recording = answer_recordings[0]
    return {
        "kind": "open",
        "text": (qa_item.expected_answer or "").strip(),
        "recording": serialize_recording(recording, label_prefix="Answer"),
    }


def get_record_dashboard(db, *, language: str = ""):
    sync_system_languages_registry(db)
    language_options = sorted(set(get_registered_system_languages(db)) - {""})
    selected_language = canonical_language_code(language)
    if not selected_language and language_options:
        selected_language = language_options[0]

    qa_items = sort_qa_items_by_passage(load_recordable_qa_items(db))
    grouped_recordings = get_recordings_grouped_by_kind(
        db,
        [item.id for item in qa_items],
        selected_language,
    )

    rows = []
    for qa_item in qa_items:
        question_recordings = grouped_recordings.get((qa_item.id, "question"), [])
        answer_recordings = grouped_recordings.get((qa_item.id, "answer"), [])
        question_recording = None
        if question_recordings:
            latest = max(
                question_recordings,
                key=lambda recording: (recording.version, recording.created_at),
            )
            question_recording = serialize_recording(latest, label_prefix="Question")

        rows.append(
            {
                "qa_item_id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id,
                "question": qa_item.question_text,
                "question_type": (qa_item.question_type or QUESTION_TYPE_OPEN).strip().lower(),
                "answer": _serialize_answer_slots(qa_item, answer_recordings, selected_language),
                "question_recording": question_recording,
            }
        )

    return {
        "language": selected_language or None,
        "language_options": language_options,
        "items": rows,
    }
