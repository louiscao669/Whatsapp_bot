"""QA item expert recordings (question prompts for participants)."""

import os
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eten_shared.models import QAItemRecording
from eten_shared.media_storage import get_playback_url_for_storage_uri
from eten_shared.languages import LanguageError as QAImportError, normalize_language_code

_FALSEY = {"false", "0", "no", "off", ""}


def question_audio_required() -> bool:
    """Whether a matching-language expert question recording is required before
    a QA item can be assigned.

    Defaults to True (audio-first delivery for low-resource-language native
    speakers). Set REQUIRE_QUESTION_AUDIO=false to allow text-only assignment
    (e.g. Telegram / dashboard text testing), where questions are delivered as
    text and audio is used only when a recording happens to exist.
    """

    return os.getenv("REQUIRE_QUESTION_AUDIO", "true").strip().lower() not in _FALSEY


def participant_language_code(participant) -> str:
    raw = (getattr(participant, "target_language", None) or "eng").strip() or "eng"
    try:
        return normalize_language_code(raw).lower()
    except QAImportError:
        return raw.lower()


def get_latest_question_recording(
    db: Session, qa_item_id: str, language: str
) -> Optional[QAItemRecording]:
    language_code = (language or "").strip().lower()
    if not language_code:
        return None

    return db.scalars(
        select(QAItemRecording)
        .where(
            QAItemRecording.qa_item_id == qa_item_id,
            QAItemRecording.recording_type == "question",
            func.lower(QAItemRecording.language) == language_code,
        )
        .order_by(
            QAItemRecording.version.desc(),
            QAItemRecording.created_at.desc(),
        )
    ).first()


def has_question_recording(db: Session, qa_item_id: str, language: str) -> bool:
    return get_latest_question_recording(db, qa_item_id, language) is not None


def has_question_recording_for_participant(db: Session, qa_item_id: str, participant) -> bool:
    return has_question_recording(
        db, qa_item_id, participant_language_code(participant)
    )


def participant_question_audio_satisfied(db: Session, qa_item_id: str, participant) -> bool:
    """Audio-eligibility check for assignment: satisfied when question audio is
    not required (REQUIRE_QUESTION_AUDIO=false), or a matching-language question
    recording exists. When audio isn't required, the question is delivered as
    text."""

    if not question_audio_required():
        return True
    return has_question_recording_for_participant(db, qa_item_id, participant)


def question_recording_playback_url(recording: Optional[QAItemRecording]) -> Optional[str]:
    if not recording or not (recording.storage_uri or "").strip():
        return None
    return get_playback_url_for_storage_uri(recording.storage_uri)
