import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

from app.services.media_storage_service import download_storage_object, parse_storage_uri

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    confidence: Optional[float] = None


def is_transcription_enabled() -> bool:
    return os.getenv("TRANSCRIPTION_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def get_whisper_model() -> str:
    return os.getenv("WHISPER_MODEL", "whisper-1").strip() or "whisper-1"


def get_placeholder_transcript_text() -> str:
    return os.getenv(
        "PLACEHOLDER_AUDIO_TRANSCRIPT",
        "[placeholder transcript: speech-to-text model not connected]",
    ).strip()


def is_placeholder_transcript(transcript_text: str) -> bool:
    """True when STT is not connected and the stub transcript was stored."""
    text = (transcript_text or "").strip()
    if not text:
        return False

    normalized = text.lower()
    configured = get_placeholder_transcript_text().lower()
    if configured and normalized == configured:
        return True

    return (
        "placeholder transcript" in normalized
        or "speech-to-text model not connected" in normalized
    )


def whisper_language_hint(target_language: Optional[str]) -> Optional[str]:
    """Map participant target_language to ISO-639-1 for Whisper."""
    if not target_language:
        return None

    code = target_language.strip().lower()
    mapping = {
        "eng": "en",
        "english": "en",
        "en": "en",
        "chinese": "zh",
        "zh": "zh",
        "cmn": "zh",
        "mandarin": "zh",
        "spa": "es",
        "spanish": "es",
        "es": "es",
        "fra": "fr",
        "french": "fr",
        "fr": "fr",
    }
    if code in mapping:
        return mapping[code]
    if len(code) == 2:
        return code
    return None


def _download_audio_bytes(media_url: str) -> tuple[bytes, Optional[str]]:
    parsed = parse_storage_uri(media_url or "")
    if not parsed:
        raise ValueError(f"Invalid storage URI: {media_url}")
    bucket, object_path = parsed
    content, content_type = download_storage_object(bucket, object_path)
    if not content:
        raise ValueError("Audio file is empty")
    return content, content_type


def _suffix_for_content_type(content_type: Optional[str], object_path: str) -> str:
    if object_path and "." in object_path:
        return "." + object_path.rsplit(".", 1)[-1].lower()
    if content_type:
        lowered = content_type.lower().split(";", 1)[0].strip()
        type_map = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
            "audio/wav": ".wav",
        }
        return type_map.get(lowered, ".mp3")
    return ".mp3"


def transcribe_audio_bytes(
    content: bytes,
    content_type: Optional[str] = None,
    object_path: str = "",
    language_hint: Optional[str] = None,
) -> TranscriptionResult:
    if not is_transcription_enabled():
        return TranscriptionResult(
            text=get_placeholder_transcript_text(),
            provider="placeholder",
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; using placeholder transcript")
        return TranscriptionResult(
            text=get_placeholder_transcript_text(),
            provider="placeholder",
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required for transcription") from exc

    suffix = _suffix_for_content_type(content_type, object_path)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        client = OpenAI(api_key=api_key)
        whisper_language = whisper_language_hint(language_hint)
        with open(tmp_path, "rb") as audio_file:
            kwargs = {"model": get_whisper_model(), "file": audio_file}
            if whisper_language:
                kwargs["language"] = whisper_language
            response = client.audio.transcriptions.create(**kwargs)
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Whisper returned empty transcript")
        return TranscriptionResult(text=text, provider="openai-whisper")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def transcribe_whatsapp_audio(
    media_id,
    mime_type=None,
    sha256=None,
    media_url=None,
    language_hint=None,
):
    """
    Transcribe stored participant audio for keyword scoring.

    media_url should be a storage:// URI after upload. Falls back to placeholder
    when TRANSCRIPTION_ENABLED is false or OPENAI_API_KEY is missing.
    """
    if not media_url or not parse_storage_uri(media_url):
        return TranscriptionResult(
            text=get_placeholder_transcript_text(),
            provider="placeholder",
        )

    try:
        content, content_type = _download_audio_bytes(media_url)
        _, object_path = parse_storage_uri(media_url)
        return transcribe_audio_bytes(
            content,
            content_type=content_type or mime_type,
            object_path=object_path or "",
            language_hint=language_hint,
        )
    except Exception:
        logger.exception("Transcription failed for media_url %s", media_url)
        return TranscriptionResult(
            text=get_placeholder_transcript_text(),
            provider="placeholder",
        )
