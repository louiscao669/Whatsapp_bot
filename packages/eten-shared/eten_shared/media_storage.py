import logging
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import requests


DEFAULT_AUDIO_BUCKET = "participant-audio"


@dataclass
class StoredMedia:
    bucket: str
    object_path: str
    storage_uri: str
    content_type: str
    file_size: Optional[int] = None
    whatsapp_media_url: Optional[str] = None


def get_graph_api_version():
    return os.getenv("VERSION", "v25.0")


def get_audio_bucket():
    return os.getenv("SUPABASE_AUDIO_BUCKET", DEFAULT_AUDIO_BUCKET)


def get_recordings_bucket():
    return os.getenv("SUPABASE_RECORDINGS_BUCKET") or get_audio_bucket()


def get_profile_photo_bucket():
    return os.getenv("SUPABASE_PROFILE_PHOTO_BUCKET") or get_audio_bucket()


def is_supabase_storage_configured():
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def parse_storage_uri(storage_uri):
    if not storage_uri:
        return None

    prefix = "storage://"
    if not storage_uri.startswith(prefix):
        return None

    rest = storage_uri[len(prefix) :]
    bucket, separator, object_path = rest.partition("/")
    if not separator or not bucket or not object_path:
        return None

    return bucket, object_path


def encode_storage_object_path(object_path):
    return quote(object_path, safe="/")


def delete_storage_uri(storage_uri):
    """Best-effort delete of a storage:// object. Returns True if deleted or missing."""
    parsed = parse_storage_uri(storage_uri)
    if not parsed:
        return False
    if not is_supabase_storage_configured():
        return False

    bucket, object_path = parsed
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    encoded_path = encode_storage_object_path(object_path)
    delete_url = f"{supabase_url}/storage/v1/object/{bucket}/{encoded_path}"
    try:
        response = requests.delete(
            delete_url,
            headers=get_supabase_storage_headers(),
            timeout=30,
        )
        if response.ok or response.status_code == 404:
            return True
        logging.warning(
            "Failed to delete storage object %s/%s: %s %s",
            bucket,
            object_path,
            response.status_code,
            response.text[:200],
        )
    except requests.RequestException as exc:
        logging.warning(
            "Failed to delete storage object %s/%s: %s",
            bucket,
            object_path,
            exc,
        )
    return False


def get_supabase_storage_headers():
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
    }


def download_storage_object(bucket, object_path):
    if not is_supabase_storage_configured():
        raise RuntimeError("Supabase Storage is not configured")

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    encoded_path = encode_storage_object_path(object_path)
    download_url = f"{supabase_url}/storage/v1/object/{bucket}/{encoded_path}"

    response = requests.get(
        download_url,
        headers=get_supabase_storage_headers(),
        timeout=60,
    )
    if response.ok:
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        return response.content, content_type

    signed_url = create_signed_storage_url(bucket, object_path)
    if signed_url:
        signed_response = requests.get(signed_url, timeout=60)
        if signed_response.ok:
            content_type = signed_response.headers.get(
                "Content-Type", "application/octet-stream"
            )
            return signed_response.content, content_type

    detail = response.text[:200]
    if response.status_code in {400, 404}:
        raise RuntimeError(
            "Audio file not found in Supabase Storage or access denied. "
            f"Verify the object path ({object_path}), bucket ({bucket}), and that "
            "SUPABASE_SERVICE_ROLE_KEY is the service_role secret (not the anon key). "
            f"Storage API response: {detail}"
        )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    return response.content, content_type


def get_signed_storage_url_expiry_seconds():
    raw_value = os.getenv("SUPABASE_AUDIO_SIGNED_URL_EXPIRES_SECONDS", "3600")
    try:
        expires_in = int(raw_value)
    except ValueError:
        expires_in = 3600
    return max(expires_in, 60)


def build_absolute_signed_storage_url(signed_path):
    if not signed_path:
        return None

    if signed_path.startswith("http://") or signed_path.startswith("https://"):
        return signed_path

    if signed_path.startswith("/object/"):
        signed_path = f"/storage/v1{signed_path}"

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    return f"{supabase_url}{signed_path}"


def create_signed_storage_url(bucket, object_path, expires_in=None):
    if not is_supabase_storage_configured():
        return None

    if expires_in is None:
        expires_in = get_signed_storage_url_expiry_seconds()

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    encoded_path = encode_storage_object_path(object_path)
    sign_endpoint = f"{supabase_url}/storage/v1/object/sign/{bucket}/{encoded_path}"

    try:
        response = requests.post(
            sign_endpoint,
            headers={
                "Authorization": f"Bearer {service_role_key}",
                "apikey": service_role_key,
                "Content-Type": "application/json",
            },
            json={"expiresIn": expires_in},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        logging.exception(
            "Failed to create signed URL for %s/%s", bucket, object_path
        )
        return None

    signed_path = payload.get("signedURL") or payload.get("signedUrl")
    if not signed_path:
        logging.error("Supabase sign response missing signedURL: %s", payload)
        return None

    return build_absolute_signed_storage_url(signed_path)


def get_playback_url_for_storage_uri(storage_uri):
    parsed = parse_storage_uri(storage_uri)
    if not parsed:
        return None

    bucket, object_path = parsed
    return create_signed_storage_url(bucket, object_path)


def get_media_extension(mime_type):
    if not mime_type:
        return ".bin"

    base_mime_type = mime_type.split(";", 1)[0].strip().lower()
    if base_mime_type == "audio/ogg":
        return ".ogg"

    return mimetypes.guess_extension(base_mime_type) or ".bin"


def build_audio_object_path(media_id, mime_type):
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"whatsapp/{today}/{media_id}{get_media_extension(mime_type)}"


def fetch_whatsapp_media_metadata(media_id):
    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError("ACCESS_TOKEN is required to fetch WhatsApp media")

    url = f"https://graph.facebook.com/{get_graph_api_version()}/{media_id}"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def download_whatsapp_media(media_url):
    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError("ACCESS_TOKEN is required to download WhatsApp media")

    response = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content


def upload_to_supabase_storage(content, object_path, content_type):
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for audio storage"
        )

    bucket = get_audio_bucket()
    upload_url = (
        f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    )
    response = requests.post(
        upload_url,
        headers={
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
        data=content,
        timeout=30,
    )
    response.raise_for_status()
    return bucket


def upload_to_supabase_storage_bucket(content, bucket, object_path, content_type):
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for audio storage"
        )

    upload_url = (
        f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    )
    response = requests.post(
        upload_url,
        headers={
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
        data=content,
        timeout=30,
    )
    response.raise_for_status()
    return bucket


def store_qa_keyword_recording_audio(
    content: bytes,
    content_type: str,
    qa_item_id: str,
    language: str,
    keyword_kind: str,
    keyword_text: str,
    version: int | None = None,
):
    if not is_supabase_storage_configured():
        raise RuntimeError("Supabase Storage is not configured")
    if not content:
        raise RuntimeError("Recording content is empty")

    safe_qa_id = (qa_item_id or "unknown").strip().replace("/", "_")
    safe_language = (language or "unknown").strip().replace("/", "_")
    safe_kind = (keyword_kind or "required").strip().replace("/", "_")
    safe_keyword = (keyword_text or "keyword").strip().replace("/", "_")[:80]
    version_suffix = f"v{version}_" if version is not None else ""
    object_path = (
        f"qa-recordings/{safe_language}/{safe_qa_id}/"
        f"keyword_{safe_kind}_{safe_keyword}_{version_suffix}"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S%f')}"
        f"{get_media_extension(content_type)}"
    )
    bucket = get_recordings_bucket()
    upload_to_supabase_storage_bucket(content, bucket, object_path, content_type)
    return StoredMedia(
        bucket=bucket,
        object_path=object_path,
        storage_uri=f"storage://{bucket}/{object_path}",
        content_type=content_type,
        file_size=len(content),
    )


def store_participant_profile_photo(
    content: bytes,
    content_type: str,
    participant_id: str,
):
    if not is_supabase_storage_configured():
        raise RuntimeError("Supabase Storage is not configured")
    if not content:
        raise RuntimeError("Profile photo content is empty")

    safe_participant_id = (participant_id or "unknown").strip().replace("/", "_")
    object_path = (
        f"profile-photos/{safe_participant_id}/"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S%f')}"
        f"{get_media_extension(content_type)}"
    )
    bucket = get_profile_photo_bucket()
    upload_to_supabase_storage_bucket(content, bucket, object_path, content_type)
    return StoredMedia(
        bucket=bucket,
        object_path=object_path,
        storage_uri=f"storage://{bucket}/{object_path}",
        content_type=content_type,
        file_size=len(content),
    )


def store_qa_recording_audio(
    content: bytes,
    content_type: str,
    qa_item_id: str,
    recording_type: str,
    language: str,
    version: int | None = None,
):
    if not is_supabase_storage_configured():
        raise RuntimeError("Supabase Storage is not configured")
    if not content:
        raise RuntimeError("Recording content is empty")

    safe_qa_id = (qa_item_id or "unknown").strip().replace("/", "_")
    safe_type = (recording_type or "recording").strip().replace("/", "_")
    safe_language = (language or "unknown").strip().replace("/", "_")
    version_suffix = f"v{version}_" if version is not None else ""
    object_path = (
        f"qa-recordings/{safe_language}/{safe_qa_id}/"
        f"{safe_type}_{version_suffix}"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S%f')}"
        f"{get_media_extension(content_type)}"
    )
    bucket = get_recordings_bucket()
    upload_to_supabase_storage_bucket(content, bucket, object_path, content_type)
    return StoredMedia(
        bucket=bucket,
        object_path=object_path,
        storage_uri=f"storage://{bucket}/{object_path}",
        content_type=content_type,
        file_size=len(content),
    )


def store_whatsapp_audio(media_id, mime_type=None):
    if not media_id:
        return None

    if not is_supabase_storage_configured():
        logging.info("Supabase Storage is not configured; skipping audio upload")
        return None

    metadata = fetch_whatsapp_media_metadata(media_id)
    media_url = metadata.get("url")
    if not media_url:
        raise RuntimeError("WhatsApp media metadata did not include a download URL")

    content_type = metadata.get("mime_type") or mime_type or "application/octet-stream"
    content = download_whatsapp_media(media_url)
    object_path = build_audio_object_path(media_id, content_type)
    bucket = upload_to_supabase_storage(content, object_path, content_type)

    return StoredMedia(
        bucket=bucket,
        object_path=object_path,
        storage_uri=f"storage://{bucket}/{object_path}",
        content_type=content_type,
        file_size=metadata.get("file_size") or len(content),
        whatsapp_media_url=media_url,
    )
