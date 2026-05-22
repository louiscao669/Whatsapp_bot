import logging
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests


DEFAULT_AUDIO_BUCKET = "whatsapp-audio"


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


def is_supabase_storage_configured():
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


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
