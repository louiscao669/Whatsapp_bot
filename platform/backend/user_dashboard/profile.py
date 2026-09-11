"""Dashboard profile services."""

from ._common import *  # noqa: F401,F403

def _participant_by_id(db, participant_id):
    return db.scalars(select(Participant).where(Participant.id == participant_id)).first()


def _profile_photo_url(participant_id, participant):
    storage_uri = (participant.profile_photo_uri or "").strip()
    if not storage_uri:
        return None
    # Settings and other participant changes also update ``updated_at``. Using
    # it here made an unchanged photo appear to have a new URL after switching
    # dashboard language. The storage URI changes whenever a new photo is
    # uploaded, so it is the correct stable cache-busting source.
    version = hashlib.sha256(storage_uri.encode("utf-8")).hexdigest()[:12]
    return f"/user-dashboard/api/{participant_id}/profile-photo?v={version}"


def load_profile_photo(db, participant_id: str):
    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise ProfilePhotoNotFoundError("Participant not found")

    parsed = parse_storage_uri(participant.profile_photo_uri or "")
    if not parsed:
        raise ProfilePhotoNotFoundError("Profile photo not found")

    bucket, object_path = parsed
    content, content_type = download_storage_object(bucket, object_path)
    if not content:
        raise ProfilePhotoNotFoundError("Profile photo not found")

    version_source = participant.updated_at or participant.created_at
    version = int(version_source.timestamp()) if version_source else 0
    return {
        "content": content,
        "content_type": content_type or "application/octet-stream",
        "etag": f'W/"profile-photo-{participant.id}-{version}"',
        "version": version,
    }


def update_profile_photo(db, participant_id: str, content: bytes, content_type: str):
    from .store import _get_or_create_wallet
    from .payload import get_user_dashboard_payload

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise ProfilePhotoUploadError("Participant not found")

    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type not in ALLOWED_PROFILE_PHOTO_TYPES:
        raise ProfilePhotoUploadError("Please choose a JPEG, PNG, WebP, or GIF image")
    if not content:
        raise ProfilePhotoUploadError("Profile photo file is empty")
    if len(content) > MAX_PROFILE_PHOTO_BYTES:
        raise ProfilePhotoUploadError("Profile photo must be 5 MB or smaller")

    wallet = _get_or_create_wallet(db, participant)
    if wallet.balance < PROFILE_PHOTO_CHANGE_COST:
        raise ProfilePhotoUploadError("Changing profile photo costs 5 diamonds")

    previous_uri = participant.profile_photo_uri
    stored = store_participant_profile_photo(
        content,
        normalized_content_type,
        participant.id,
    )
    wallet.balance -= PROFILE_PHOTO_CHANGE_COST
    wallet.lifetime_spent += PROFILE_PHOTO_CHANGE_COST
    wallet.updated_at = datetime.now(timezone.utc)
    participant.profile_photo_uri = stored.storage_uri
    participant.updated_at = datetime.now(timezone.utc)
    event = ParticipantCurrencyEvent(
        participant_id=participant.id,
        wallet_id=wallet.id,
        amount=-PROFILE_PHOTO_CHANGE_COST,
        balance_after=wallet.balance,
        reason="profile_photo_change",
        source="user_dashboard",
        currency_metadata={
            "content_type": normalized_content_type,
        },
    )
    db.add(event)
    db.flush()

    if previous_uri and previous_uri != stored.storage_uri:
        delete_storage_uri(previous_uri)

    return get_user_dashboard_payload(db, participant_id)


