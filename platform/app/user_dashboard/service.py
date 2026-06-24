"""Participant wallet, store, and cosmetic helpers for the user dashboard."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select

from eten_shared.media_storage import (
    delete_storage_uri,
    download_storage_object,
    parse_storage_uri,
    store_participant_profile_photo,
)
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Participant,
    ParticipantBadge,
    ParticipantCurrencyEvent,
    ParticipantEvent,
    ParticipantResponse,
    ParticipantWallet,
    QAItem,
)
from eten_shared.domain.streaks import (
    STREAK_FREEZE_ITEM_ID,
    get_freeze_token_balance,
    latest_progress_report,
    set_streak_pause,
    streak_status_payload,
)
from user_dashboard.backend import compose_dashboard_view_model


LEADERBOARD_LIMIT = 10
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
PROFILE_PHOTO_CHANGE_COST = 5
ALLOWED_PROFILE_PHOTO_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
STORE_ITEMS = {
    "streak_freeze": {
        "item_id": "streak_freeze",
        "title": "Streak Freeze",
        "description": "Protects your streak for one missed day.",
        "cost": 8,
        "item_type": "consumable",
        "max_owned": 3,
    },
    "profile_frame_gold": {
        "item_id": "profile_frame_gold",
        "title": "Gold Profile Frame",
        "description": "Adds a gold frame to your dashboard profile.",
        "cost": 10,
        "item_type": "cosmetic",
        "max_owned": 1,
    },
    "dashboard_background_sunrise": {
        "item_id": "dashboard_background_sunrise",
        "title": "Sunrise Background",
        "description": "Changes your dashboard background to a warm sunrise color.",
        "cost": 8,
        "item_type": "cosmetic",
        "max_owned": 1,
    },
    "extra_life": {
        "item_id": "extra_life",
        "title": "Extra Life",
        "description": "A saved recovery chance for future retry mechanics.",
        "cost": 12,
        "item_type": "consumable",
        "max_owned": 3,
    },
}
COSMETIC_SLOTS = {
    "profile_frame_gold": "profile_frame",
    "dashboard_background_sunrise": "dashboard_background",
}


class StorePurchaseError(Exception):
    pass


class ProfilePhotoUploadError(Exception):
    pass


class ProfilePhotoNotFoundError(Exception):
    pass


class CosmeticUpdateError(Exception):
    pass


class StreakPauseUpdateError(Exception):
    pass


def _iso_datetime(value):
    return value.isoformat() if value else None


def _week_bounds(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return week_start, week_start + timedelta(days=7)


def _display_name_for_leaderboard(participant, fallback_index):
    name = (participant.display_name or "").strip()
    if name:
        return name
    return f"Participant {fallback_index}"


def _language_code(participant):
    return (participant.target_language or "unknown").strip() or "unknown"


def _participant_by_wa_id(db, wa_id):
    return db.scalars(select(Participant).where(Participant.wa_id == wa_id)).first()


def _profile_photo_url(wa_id, participant):
    if not (participant.profile_photo_uri or "").strip():
        return None
    version = int((participant.updated_at or participant.created_at).timestamp())
    return f"/user-dashboard/api/{wa_id}/profile-photo?v={version}"


def load_profile_photo(db, wa_id: str):
    participant = _participant_by_wa_id(db, wa_id)
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


def _get_or_create_wallet(db, participant):
    wallet = db.scalars(
        select(ParticipantWallet).where(
            ParticipantWallet.participant_id == participant.id
        )
    ).first()
    if wallet:
        return wallet

    wallet = ParticipantWallet(participant_id=participant.id)
    db.add(wallet)
    db.flush()
    return wallet


def _store_purchase_events(db, participant_id):
    return db.scalars(
        select(ParticipantCurrencyEvent).where(
            ParticipantCurrencyEvent.participant_id == participant_id,
            ParticipantCurrencyEvent.reason == "store_purchase",
        )
    ).all()


def get_store_inventory(db, participant_id):
    inventory = {
        item_id: {
            "owned": 0,
            "max_owned": item["max_owned"],
        }
        for item_id, item in STORE_ITEMS.items()
    }
    for event in _store_purchase_events(db, participant_id):
        metadata = event.currency_metadata or {}
        item_id = metadata.get("item_id")
        if item_id in inventory:
            inventory[item_id]["owned"] += 1
    participant = db.get(Participant, participant_id)
    if participant:
        inventory[STREAK_FREEZE_ITEM_ID]["owned"] = get_freeze_token_balance(
            db,
            participant,
        )["available"]
    return inventory


def get_store_payload(db, participant):
    inventory = get_store_inventory(db, participant.id)
    items = sorted(STORE_ITEMS.values(), key=lambda item: (item["cost"], item["title"]))
    return {
        "items": items,
        "inventory": inventory,
    }


def get_equipped_cosmetics(participant):
    preferences = participant.dashboard_preferences or {}
    return {
        "profile_frame": preferences.get("profile_frame"),
        "dashboard_background": preferences.get("dashboard_background"),
    }


def set_cosmetic_equipped(db, wa_id: str, item_id: str, equipped: bool):
    item = STORE_ITEMS.get((item_id or "").strip())
    if not item:
        raise CosmeticUpdateError("Store item not found")
    if item["item_type"] != "cosmetic":
        raise CosmeticUpdateError("Only cosmetic items can be equipped")
    slot = COSMETIC_SLOTS.get(item["item_id"])
    if not slot:
        raise CosmeticUpdateError("Cosmetic slot not found")

    participant = _participant_by_wa_id(db, wa_id)
    if not participant:
        raise CosmeticUpdateError("Participant not found")

    inventory = get_store_inventory(db, participant.id)
    owned = inventory.get(item["item_id"], {}).get("owned", 0)
    if owned <= 0:
        raise CosmeticUpdateError("Buy this cosmetic before equipping it")

    preferences = dict(participant.dashboard_preferences or {})
    if equipped:
        preferences[slot] = item["item_id"]
    elif preferences.get(slot) == item["item_id"]:
        preferences.pop(slot, None)

    participant.dashboard_preferences = preferences
    participant.updated_at = datetime.now(timezone.utc)
    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="cosmetic_updated",
            source="user_dashboard",
            event_metadata={
                "item_id": item["item_id"],
                "slot": slot,
                "equipped": bool(equipped),
            },
        )
    )
    db.flush()
    return get_user_dashboard_payload(db, wa_id)


def set_user_streak_pause(db, wa_id: str, paused: bool):
    participant = _participant_by_wa_id(db, wa_id)
    if not participant:
        raise StreakPauseUpdateError("Participant not found")

    try:
        set_streak_pause(db, participant, paused)
    except ValueError as exc:
        raise StreakPauseUpdateError(str(exc)) from exc
    return get_user_dashboard_payload(db, wa_id)


def purchase_store_item(db, wa_id: str, item_id: str):
    item = STORE_ITEMS.get((item_id or "").strip())
    if not item:
        raise StorePurchaseError("Store item not found")

    participant = _participant_by_wa_id(db, wa_id)
    if not participant:
        raise StorePurchaseError("Participant not found")

    wallet = _get_or_create_wallet(db, participant)
    inventory = get_store_inventory(db, participant.id)
    owned = inventory.get(item["item_id"], {}).get("owned", 0)
    if owned >= item["max_owned"]:
        raise StorePurchaseError("Item limit reached")
    if wallet.balance < item["cost"]:
        raise StorePurchaseError("Not enough diamonds")

    wallet.balance -= item["cost"]
    wallet.lifetime_spent += item["cost"]
    wallet.updated_at = datetime.now(timezone.utc)

    event = ParticipantCurrencyEvent(
        participant_id=participant.id,
        wallet_id=wallet.id,
        amount=-item["cost"],
        balance_after=wallet.balance,
        reason="store_purchase",
        source="user_dashboard",
        currency_metadata={
            "item_id": item["item_id"],
            "title": item["title"],
            "item_type": item["item_type"],
        },
    )
    db.add(event)
    db.flush()
    return get_user_dashboard_payload(db, wa_id)


def update_profile_photo(db, wa_id: str, content: bytes, content_type: str):
    participant = _participant_by_wa_id(db, wa_id)
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

    return get_user_dashboard_payload(db, wa_id)


def get_language_weekly_leaderboard(db, participant, limit=LEADERBOARD_LIMIT):
    language = _language_code(participant)
    week_start, week_end = _week_bounds()
    weekly_score = func.coalesce(func.sum(ParticipantCurrencyEvent.amount), 0).label(
        "weekly_score"
    )
    rows = db.execute(
        select(Participant, weekly_score)
        .join(
            ParticipantCurrencyEvent,
            ParticipantCurrencyEvent.participant_id == Participant.id,
        )
        .where(
            Participant.target_language == participant.target_language,
            ParticipantCurrencyEvent.created_at >= week_start,
            ParticipantCurrencyEvent.created_at < week_end,
            ParticipantCurrencyEvent.amount > 0,
        )
        .group_by(Participant.id)
        .order_by(weekly_score.desc(), Participant.created_at.asc())
    ).all()

    leaderboard_rows = []
    current_user_row = None
    previous_score = None
    current_rank = 0
    for index, (row_participant, score) in enumerate(rows, start=1):
        score = int(score or 0)
        if previous_score is None or score < previous_score:
            current_rank = index
        previous_score = score

        row = {
            "rank": current_rank,
            "participant_id": row_participant.id,
            "display_name": _display_name_for_leaderboard(row_participant, index),
            "weekly_earned": score,
            "is_current_user": row_participant.id == participant.id,
        }
        if len(leaderboard_rows) < limit:
            leaderboard_rows.append(row)
        if row["is_current_user"]:
            current_user_row = row

    if current_user_row is None:
        current_user_row = {
            "rank": None,
            "participant_id": participant.id,
            "display_name": _display_name_for_leaderboard(
                participant,
                len(rows) + 1,
            ),
            "weekly_earned": 0,
            "is_current_user": True,
        }

    return {
        "scope": "language",
        "language": language,
        "week_start": _iso_datetime(week_start),
        "week_end": _iso_datetime(week_end),
        "limit": limit,
        "current_user": current_user_row,
        "rows": leaderboard_rows,
    }


def get_luke_chapter_activity(db, participant_id, chapter_count=24):
    rows = db.execute(
        select(QAItem.passage_reference, func.count(ParticipantResponse.id))
        .join(QAItem, QAItem.id == ParticipantResponse.qa_item_id)
        .where(ParticipantResponse.participant_id == participant_id)
        .group_by(QAItem.passage_reference)
    ).all()
    counts = {chapter: 0 for chapter in range(1, chapter_count + 1)}
    for passage_reference, response_count in rows:
        reference = str(passage_reference or "")
        if not reference.lower().startswith("luke "):
            continue
        chapter_text = reference.split(" ", 1)[1].split(":", 1)[0].strip()
        if not chapter_text.isdigit():
            continue
        chapter = int(chapter_text)
        if chapter in counts:
            counts[chapter] += int(response_count or 0)

    max_count = max(counts.values(), default=0)
    output = []
    for chapter, count in counts.items():
        if count <= 0:
            level = 0
        elif max_count <= 1:
            level = 1
        else:
            level = min(4, max(1, round((count / max_count) * 4)))
        output.append(
            {
                "book": "Luke",
                "chapter": chapter,
                "answered_questions": count,
                "level": level,
            }
        )
    return output


def get_user_dashboard_payload(db, wa_id: str, event_limit: int = 100):
    participant = _participant_by_wa_id(db, wa_id)
    if not participant:
        return None

    wallet = _get_or_create_wallet(db, participant)
    currency_events = db.scalars(
        select(ParticipantCurrencyEvent)
        .where(ParticipantCurrencyEvent.participant_id == participant.id)
        .order_by(ParticipantCurrencyEvent.created_at.desc())
        .limit(event_limit)
    ).all()
    badges = db.scalars(
        select(ParticipantBadge)
        .where(ParticipantBadge.participant_id == participant.id)
        .order_by(ParticipantBadge.awarded_at.desc())
    ).all()
    total_questions_answered = db.scalar(
        select(func.count(ParticipantCurrencyEvent.id)).where(
            ParticipantCurrencyEvent.participant_id == participant.id,
            ParticipantCurrencyEvent.reason == "answer_completed",
            ParticipantCurrencyEvent.amount > 0,
        )
    )
    total_batches_answered = db.scalar(
        select(func.count(distinct(Assignment.batch_id))).where(
            Assignment.participant_id == participant.id,
            Assignment.status == AssignmentStatus.COMPLETED.value,
            Assignment.batch_id.is_not(None),
        )
    )

    history_summary = {
        "total_questions_answered": int(total_questions_answered or 0),
        "total_batches_answered": int(total_batches_answered or 0),
        "chapter_activity": get_luke_chapter_activity(db, participant.id),
    }
    serialized_events = [
        {
            "created_at": _iso_datetime(event.created_at),
            "reason": event.reason,
            "amount": event.amount,
            "balance_after": event.balance_after,
        }
        for event in currency_events
    ]
    serialized_badges = [
        {
            "badge_type": badge.badge_type,
            "title": badge.title,
            "description": badge.description or "",
            "awarded_at": _iso_datetime(badge.awarded_at),
        }
        for badge in badges
    ]
    leaderboard = get_language_weekly_leaderboard(db, participant)
    streak = {
        **streak_status_payload(db, participant),
        "progress_report": latest_progress_report(db, participant.id),
    }
    store = get_store_payload(db, participant)
    wallet_payload = {
        "balance": wallet.balance if wallet else 0,
    }
    view_model = compose_dashboard_view_model(
        participant=participant,
        wallet=wallet_payload,
        history_summary=history_summary,
        events=serialized_events,
        badges=serialized_badges,
        leaderboard=leaderboard,
        streak=streak,
        store=store,
    )

    return {
        "participant": {
            "id": participant.id,
            "display_name": participant.display_name or "",
            "wa_id": participant.wa_id,
            "profile_photo_url": _profile_photo_url(wa_id, participant),
        },
        "wallet": wallet_payload,
        "xp_points": 0,
        "events": serialized_events,
        "badges": serialized_badges,
        "streak": streak,
        "store": store,
        "cosmetics": {
            "equipped": get_equipped_cosmetics(participant),
        },
        **view_model,
    }
