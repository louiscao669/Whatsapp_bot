import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    confidence: Optional[float] = None


def transcribe_whatsapp_audio(media_id, mime_type=None, sha256=None):
    """
    Placeholder adapter for the project speech-to-text model.

    Replace this function body with the team model call once it is available.
    The rest of the chatbot workflow expects a TranscriptionResult with text.
    """
    placeholder_text = os.getenv(
        "PLACEHOLDER_AUDIO_TRANSCRIPT",
        "[placeholder transcript: speech-to-text model not connected]",
    )
    return TranscriptionResult(
        text=placeholder_text,
        provider="placeholder",
        confidence=None,
    )
