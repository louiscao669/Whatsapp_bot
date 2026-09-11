import io
import logging
import os
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from eten_shared.database import get_session_factory
from eten_shared.models import ParticipantResponse, ResponseType
from eten_shared.media_storage import (
    download_storage_object,
    is_supabase_storage_configured,
    parse_storage_uri,
)


@dataclass
class AudioExportItem:
    response_id: str
    qa_item_id: str
    passage_id: str
    passage_label: str
    chapter_label: str
    question_text: str
    participant_id: str
    participant_label: str
    export_filename: str
    media_url: str
    received_at: Optional[datetime]
    has_storage: bool


@dataclass
class AudioExportQaGroup:
    qa_item_id: str
    question_label: str
    items: List[AudioExportItem] = field(default_factory=list)


@dataclass
class AudioExportChapter:
    chapter_label: str
    chapter_key: str
    qa_groups: List[AudioExportQaGroup] = field(default_factory=list)


def slugify_filename_part(value, max_length=80):
    text = re.sub(r"[^\w\-]+", "_", (value or "").strip())
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return "passage"
    return text[:max_length]


def slugify_group_key(value):
    return slugify_filename_part(value, max_length=120)


def chapter_label_from_reference(passage_reference):
    reference = (passage_reference or "").strip()
    if not reference:
        return "Other"
    if ":" in reference:
        chapter = reference.rsplit(":", 1)[0].strip()
        return chapter or reference
    return reference


def truncate_question_label(question_text, max_length=100):
    text = (question_text or "").strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def extension_from_object_path(object_path):
    if not object_path:
        return ".ogg"
    _, extension = object_path.rsplit(".", 1)
    if extension and len(extension) <= 5:
        return f".{extension.lower()}"
    return ".ogg"


def build_export_filename(passage_label, participant_id, object_path, used_names):
    passage_part = slugify_filename_part(passage_label)
    participant_part = slugify_filename_part(participant_id[:12], max_length=32)
    extension = extension_from_object_path(object_path)
    base_name = f"{passage_part}_{participant_part}{extension}"
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name

    suffix = 2
    while True:
        candidate = f"{passage_part}_{participant_part}_{suffix}{extension}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        suffix += 1


def load_audio_export_item(response, used_names=None) -> Optional[AudioExportItem]:
    if (response.response_type or "").lower() != ResponseType.AUDIO.value:
        return None

    qa_item = response.qa_item
    participant = response.participant
    if not qa_item or not participant:
        return None

    passage_id = qa_item.passage_id
    passage_label = qa_item.passage_reference or qa_item.passage_id
    chapter_label = chapter_label_from_reference(passage_label)
    media_url = response.media_url or ""
    parsed = parse_storage_uri(media_url)
    object_path = parsed[1] if parsed else ""
    filename_registry = used_names if used_names is not None else set()
    export_filename = build_export_filename(
        passage_label,
        participant.id,
        object_path,
        filename_registry,
    )

    return AudioExportItem(
        response_id=response.id,
        qa_item_id=qa_item.id,
        passage_id=passage_id,
        passage_label=passage_label,
        chapter_label=chapter_label,
        question_text=qa_item.question_text,
        participant_id=participant.id,
        participant_label=participant.display_name or participant.id,
        export_filename=export_filename,
        media_url=media_url,
        received_at=response.received_at,
        has_storage=bool(parsed),
    )


def get_audio_export_chapters() -> List[AudioExportChapter]:
    statement = (
        select(ParticipantResponse)
        .options(
            selectinload(ParticipantResponse.participant),
            selectinload(ParticipantResponse.qa_item),
        )
        .where(ParticipantResponse.response_type == ResponseType.AUDIO.value)
        .order_by(ParticipantResponse.received_at.desc())
    )

    session_factory = get_session_factory()
    chapters: Dict[str, AudioExportChapter] = {}
    filename_registry: Dict[str, set] = defaultdict(set)

    with session_factory() as db:
        responses = db.scalars(statement).all()

    for response in responses:
        used_names = filename_registry[response.qa_item_id if response.qa_item else ""]
        item = load_audio_export_item(response, used_names=used_names)
        if item is None:
            continue

        chapter_key = slugify_group_key(item.chapter_label)
        qa_item_id = item.qa_item_id

        if chapter_key not in chapters:
            chapters[chapter_key] = AudioExportChapter(
                chapter_label=item.chapter_label,
                chapter_key=chapter_key,
            )

        chapter = chapters[chapter_key]
        qa_group = next((g for g in chapter.qa_groups if g.qa_item_id == qa_item_id), None)
        if qa_group is None:
            qa_group = AudioExportQaGroup(
                qa_item_id=qa_item_id,
                question_label=truncate_question_label(item.question_text),
            )
            chapter.qa_groups.append(qa_group)

        qa_group.items.append(item)

    chapter_list = list(chapters.values())
    chapter_list.sort(key=lambda chapter: chapter.chapter_label.lower())
    for chapter in chapter_list:
        chapter.qa_groups.sort(key=lambda group: group.question_label.lower())
        for qa_group in chapter.qa_groups:
            qa_group.items.sort(
                key=lambda item: (
                    item.participant_id,
                    item.received_at or datetime.min.replace(tzinfo=timezone.utc),
                )
            )
    return chapter_list


def fetch_response_audio_bytes(response_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        response = db.get(ParticipantResponse, response_id)
        if response is None:
            return None, None, None

        item = load_audio_export_item(response)
        if item is None or not item.has_storage:
            return None, None, None

        parsed = parse_storage_uri(response.media_url)
        if not parsed:
            return None, None, None

        bucket, object_path = parsed
        content, content_type = download_storage_object(bucket, object_path)
        return content, content_type, item.export_filename


def build_zip_archive(response_ids):
    unique_ids = []
    seen = set()
    for response_id in response_ids or []:
        if not response_id or response_id in seen:
            continue
        seen.add(response_id)
        unique_ids.append(response_id)

    buffer = io.BytesIO()
    included = 0
    errors = []

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for response_id in unique_ids:
            try:
                content, _, filename = fetch_response_audio_bytes(response_id)
            except Exception as exc:
                logging.exception("Failed to fetch audio for response %s", response_id)
                errors.append(f"{response_id}: {exc}")
                continue

            if not content:
                errors.append(f"{response_id}: file not available")
                continue

            archive.writestr(filename, content)
            included += 1

    if included == 0:
        detail = "; ".join(errors[:3]) if errors else "No audio files could be downloaded"
        raise ValueError(detail)

    buffer.seek(0)
    return buffer.getvalue(), included, errors


def zip_download_filename(prefix="audio_export"):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{slugify_filename_part(prefix)}_{timestamp}.zip"
