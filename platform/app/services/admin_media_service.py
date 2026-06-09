import logging
from typing import Optional, Tuple

from sqlalchemy import select

from eten_shared.database import get_session_factory
from eten_shared.models import ParticipantResponse, QAItemKeywordRecording, QAItemRecording
from eten_shared.media_storage import (
    download_storage_object,
    is_supabase_storage_configured,
    parse_storage_uri,
)

logger = logging.getLogger(__name__)

FLAGGED_IS_CORRECT_VALUES = frozenset({"pending", "no (expert)"})


def is_flagged_for_review(response: ParticipantResponse) -> bool:
    return (response.is_correct or "") in FLAGGED_IS_CORRECT_VALUES


def expert_may_access_participant_response(response: ParticipantResponse) -> bool:
    return is_flagged_for_review(response)


def load_participant_response_media(
    response_id: str,
) -> Tuple[Optional[ParticipantResponse], Optional[str], Optional[str]]:
    session_factory = get_session_factory()
    with session_factory() as db:
        response = db.get(ParticipantResponse, response_id)
        if not response:
            return None, None, None
        media_url = (response.media_url or "").strip()
        if not media_url:
            return response, None, None
        parsed = parse_storage_uri(media_url)
        if not parsed:
            return response, None, None
        bucket, object_path = parsed
    if not is_supabase_storage_configured():
        return response, None, None
    try:
        content, content_type = download_storage_object(bucket, object_path)
    except Exception:
        logger.exception("Failed to download participant response media %s", response_id)
        return response, None, None
    return response, content, content_type or "application/octet-stream"


def load_qa_recording_media(
    recording_id: str,
) -> Tuple[Optional[QAItemRecording], Optional[bytes], Optional[str]]:
    session_factory = get_session_factory()
    with session_factory() as db:
        recording = db.get(QAItemRecording, recording_id)
        if not recording:
            return None, None, None
        storage_uri = (recording.storage_uri or "").strip()
        content_type = recording.content_type
        if not storage_uri:
            return recording, None, None
        parsed = parse_storage_uri(storage_uri)
        if not parsed:
            return recording, None, None
        bucket, object_path = parsed
    if not is_supabase_storage_configured():
        return recording, None, None
    try:
        content, resolved_type = download_storage_object(bucket, object_path)
    except Exception:
        logger.exception("Failed to download QA recording %s", recording_id)
        return recording, None, None
    return recording, content, resolved_type or content_type or "application/octet-stream"


def load_qa_keyword_recording_media(
    recording_id: str,
) -> Tuple[Optional[QAItemKeywordRecording], Optional[bytes], Optional[str]]:
    session_factory = get_session_factory()
    with session_factory() as db:
        recording = db.get(QAItemKeywordRecording, recording_id)
        if not recording:
            return None, None, None
        storage_uri = (recording.storage_uri or "").strip()
        content_type = recording.content_type
        if not storage_uri:
            return recording, None, None
        parsed = parse_storage_uri(storage_uri)
        if not parsed:
            return recording, None, None
        bucket, object_path = parsed
    if not is_supabase_storage_configured():
        return recording, None, None
    try:
        content, resolved_type = download_storage_object(bucket, object_path)
    except Exception:
        logger.exception("Failed to download keyword recording %s", recording_id)
        return recording, None, None
    return recording, content, resolved_type or content_type or "application/octet-stream"


def log_media_access(asset_type: str, asset_id: str, role: str, email: Optional[str]):
    logger.info(
        "admin_media_access asset_type=%s asset_id=%s role=%s email=%s",
        asset_type,
        asset_id,
        role,
        email or "",
    )
