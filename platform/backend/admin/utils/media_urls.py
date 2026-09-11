"""Canonical authenticated media URLs for the admin SPA."""


def participant_response_media_url(response_id: str, *, download: bool = False) -> str:
    base = f"/api/v1/media/participant-response/{response_id}"
    return f"{base}?download=1" if download else base


def qa_recording_media_url(recording_id: str, *, download: bool = False) -> str:
    base = f"/api/v1/media/qa-recording/{recording_id}"
    return f"{base}?download=1" if download else base


def qa_keyword_recording_media_url(recording_id: str, *, download: bool = False) -> str:
    base = f"/api/v1/media/qa-keyword-recording/{recording_id}"
    return f"{base}?download=1" if download else base
