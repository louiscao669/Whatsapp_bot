"""Upload and delete QA recordings for the Record workflow."""

import logging

from sqlalchemy import func, select

from eten_shared.models import QAItemRecording, utc_now
from eten_shared.mcq import choice_letters_for_type
from eten_shared.media_storage import (
    delete_storage_uri,
    is_supabase_storage_configured,
    store_qa_recording_audio,
)
from eten_shared.domain.qa_eligibility import qa_item_is_recordable
from app.services.record_api_service import choice_answer_recording_version
from app.services.system_languages_service import (
    canonical_language_code,
    upsert_system_language,
)


class RecordMutationError(Exception):
    pass


def delete_qa_recordings_for_slot(db, qa_item_id, recording_type, language):
    statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id == qa_item_id,
        QAItemRecording.recording_type == recording_type,
        QAItemRecording.language == language,
    )
    for existing in db.scalars(statement).all():
        if existing.storage_uri:
            delete_storage_uri(existing.storage_uri)
        db.delete(existing)


def delete_qa_recording_version(db, qa_item_id, recording_type, language, version):
    statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id == qa_item_id,
        QAItemRecording.recording_type == recording_type,
        QAItemRecording.language == language,
        QAItemRecording.version == version,
    )
    for existing in db.scalars(statement).all():
        if existing.storage_uri:
            delete_storage_uri(existing.storage_uri)
        db.delete(existing)


def upload_recording(
    db,
    *,
    qa_item_id,
    recording_type,
    language,
    content,
    content_type,
    mode,
    recording_id=None,
    version_raw="",
    choice_letter="",
    uploader=None,
):
    if not qa_item_id:
        raise RecordMutationError("qa_item_id is required")
    if recording_type not in {"question", "answer"}:
        raise RecordMutationError("recording_type must be question or answer")
    language = canonical_language_code(language)
    if not language:
        raise RecordMutationError("language is required")
    if not content:
        raise RecordMutationError("audio file is empty")
    if not is_supabase_storage_configured():
        raise RecordMutationError("Supabase Storage is not configured")

    from eten_shared.models import QAItem

    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise RecordMutationError("qa_item not found")
    if not qa_item_is_recordable(qa_item):
        raise RecordMutationError("QA must be reviewed on Review QA before recording.")

    mode = (mode or "new").strip().lower()
    question_type = (qa_item.question_type or "open").strip().lower()
    target_version = 1
    if recording_type == "answer" and choice_letter:
        choice_letter = choice_letter.strip().upper()
        allowed_letters = "".join(choice_letters_for_type(question_type))
        if choice_letter not in allowed_letters:
            raise RecordMutationError(f"choice_letter must be one of {allowed_letters}")
        target_version = choice_answer_recording_version(choice_letter)

    if mode == "new":
        if recording_type == "question":
            delete_qa_recordings_for_slot(db, qa_item_id, recording_type, language)
        else:
            delete_qa_recording_version(db, qa_item_id, recording_type, language, target_version)
        stored = store_qa_recording_audio(
            content=content,
            content_type=content_type or "audio/webm",
            qa_item_id=qa_item_id,
            recording_type=recording_type,
            language=language,
            version=target_version,
        )
        record = QAItemRecording(
            qa_item_id=qa_item_id,
            recording_type=recording_type,
            language=language,
            version=target_version,
            storage_uri=stored.storage_uri,
            content_type=stored.content_type,
            uploaded_by=uploader,
        )
        db.add(record)
        upsert_system_language(db, language, "recording")
        return record

    if mode == "retake":
        record = None
        if recording_id:
            record = db.get(QAItemRecording, recording_id)
        elif str(version_raw).isdigit():
            record = db.scalar(
                select(QAItemRecording).where(
                    QAItemRecording.qa_item_id == qa_item_id,
                    QAItemRecording.recording_type == recording_type,
                    QAItemRecording.language == language,
                    QAItemRecording.version == int(version_raw),
                )
            )
        if not record:
            raise RecordMutationError("Recording version not found")
        if (
            record.qa_item_id != qa_item_id
            or record.recording_type != recording_type
            or canonical_language_code(record.language) != language
        ):
            raise RecordMutationError("Recording does not match request")

        stored = store_qa_recording_audio(
            content=content,
            content_type=content_type or "audio/webm",
            qa_item_id=qa_item_id,
            recording_type=recording_type,
            language=language,
            version=record.version,
        )
        record.storage_uri = stored.storage_uri
        record.content_type = stored.content_type
        record.uploaded_by = uploader
        record.created_at = utc_now()
        duplicate_filters = [
            QAItemRecording.qa_item_id == qa_item_id,
            QAItemRecording.recording_type == recording_type,
            QAItemRecording.language == language,
            QAItemRecording.id != record.id,
        ]
        if recording_type == "answer":
            duplicate_filters.append(QAItemRecording.version == record.version)
        for duplicate in db.scalars(select(QAItemRecording).where(*duplicate_filters)).all():
            if duplicate.storage_uri:
                delete_storage_uri(duplicate.storage_uri)
            db.delete(duplicate)
        upsert_system_language(db, language, "recording")
        return record

    raise RecordMutationError("Use new or retake mode; additional versions are not supported")


def delete_recording(db, recording_id):
    if not recording_id:
        raise RecordMutationError("recording_id is required")

    record = db.get(QAItemRecording, recording_id)
    if not record:
        raise RecordMutationError("Recording not found")

    storage_uri = record.storage_uri
    db.delete(record)
    db.commit()

    if storage_uri:
        try:
            delete_storage_uri(storage_uri)
        except Exception:
            logging.exception("Failed to delete storage for recording %s", recording_id)

    return recording_id
