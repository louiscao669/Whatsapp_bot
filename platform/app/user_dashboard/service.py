"""Participant wallet, store, and cosmetic helpers for the user dashboard."""

from datetime import datetime, timedelta, timezone
import hashlib
import os
import random
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, distinct, func, select

from eten_shared.answer_llm_scoring import llm_answer_scoring_enabled

from eten_shared.domain.batch_schedules import (
    BATCH_NEXT_ASSIGNMENT_TYPE,
    cancel_pending_next_batch_schedules,
)
from eten_shared.domain.assignments import (
    automatic_assignment_enabled,
    complete_current_batch_if_needed,
    create_assignment_for_qa_item,
    experiment_passage_assignment_kwargs,
    experiment_assignment_enabled,
    get_incomplete_assignment,
    get_or_create_participant_session,
    record_participant_event,
    surrounding_passage_text,
    try_complete_assignment,
)
from eten_shared.domain.qa_eligibility import qa_item_is_assignable
from eten_shared.keyword_matching import (
    keyword_matches_in_response,
    normalize_response_text,
)
from eten_shared.media_storage import (
    delete_storage_uri,
    download_storage_object,
    parse_storage_uri,
    store_participant_profile_photo,
)
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    CommunityTeam,
    CommunityTeamMember,
    DashboardEngagementSession,
    OutboxNotification,
    OutboxStatus,
    Participant,
    ParticipantBadge,
    ParticipantCurrencyEvent,
    ParticipantEvent,
    ParticipantResponse,
    ParticipantWallet,
    ExperimentPassage,
    QAItem,
    QAItemRecording,
    Reminder,
    ReminderStatus,
    ResponseType,
    ReviewStatus,
    SessionState,
    SourceChannel,
    utc_now,
)
from eten_shared.mcq import (
    choice_response_is_correct,
    choice_response_letter,
    is_choice_scored_item,
)
from eten_shared.qa_keywords import get_language_keywords
from eten_shared.question_discovery import (
    experiment_batch_should_reset,
    select_next_experiment_cell_item,
    select_next_qa_item,
)
from eten_shared.recordings import (
    get_latest_question_recording,
    participant_language_code,
)
from eten_shared.domain.streaks import (
    STREAK_FREEZE_ITEM_ID,
    get_freeze_token_balance,
    latest_progress_report,
    set_streak_pause,
    streak_status_payload,
    update_streak_for_response,
)
from app.services.qa_item_stats_service import (
    format_choice_correctness_label,
    open_response_status_label,
)
from user_dashboard.backend import compose_dashboard_view_model


LEADERBOARD_LIMIT = 10
TEAM_MAX_MEMBERS = 4
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
PROFILE_PHOTO_CHANGE_COST = 5
CHEST_REWARD_MIN = 2
CHEST_REWARD_MAX = 5
ANSWER_COMPLETED_DIAMONDS = 1
FIRST_ANSWER_COMPLETED_DIAMONDS = 5
BATCH_COMPLETED_BONUS_DIAMONDS = 3
DEFAULT_NEXT_BATCH_HOUR = 8
DEFAULT_NEXT_BATCH_TIMEZONE = "UTC"
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
    "dashboard_background_night_sky": {
        "item_id": "dashboard_background_night_sky",
        "title": "Night Sky Background",
        "description": "Gives your dashboard a deep purple starry theme.",
        "cost": 15,
        "item_type": "cosmetic",
        "max_owned": 1,
    },
    "profile_frame_ocean": {
        "item_id": "profile_frame_ocean",
        "title": "Ocean Profile Ring",
        "description": "Adds a cool blue ring around your profile photo.",
        "cost": 10,
        "item_type": "cosmetic",
        "max_owned": 1,
    },
    "profile_frame_emerald_square": {
        "item_id": "profile_frame_emerald_square",
        "title": "Emerald Square Frame",
        "description": "Displays your profile photo in a bright emerald frame.",
        "cost": 12,
        "item_type": "cosmetic",
        "max_owned": 1,
    },
}
COSMETIC_SLOTS = {
    "profile_frame_gold": "profile_frame",
    "profile_frame_ocean": "profile_frame",
    "profile_frame_emerald_square": "profile_frame",
    "dashboard_background_sunrise": "dashboard_background",
    "dashboard_background_night_sky": "dashboard_background",
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


class ChestRewardError(Exception):
    pass


class DashboardAnswerError(Exception):
    pass


class CommunityTeamError(Exception):
    pass


def _iso_datetime(value):
    return value.isoformat() if value else None


def _luke_chapter_from_reference(passage_reference):
    # Admin-authored QA commonly uses "Luke 1:11" while the evaluation/pilot
    # importer uses "1:11" (and occasionally "1:35(#2)"). Both identify the
    # same dashboard chapter and must be visible to regular participants.
    match = re.match(
        r"^(?:luke\s+)?(?P<chapter>\d+):\d+(?:\(#\d+\))?",
        str(passage_reference or "").strip(),
        re.IGNORECASE,
    )
    return int(match.group("chapter")) if match else None


def _choice_text_for_letter(qa_item, letter):
    normalized = (letter or "").strip().upper()
    choices = list(qa_item.mcq_choices or [])
    if not normalized or len(normalized) != 1:
        return ""
    index = ord(normalized) - ord("A")
    if index < 0 or index >= len(choices):
        return ""
    return str(choices[index] or "").strip()


def _format_choice_answer(qa_item, letter):
    normalized = (letter or "").strip().upper()
    text = _choice_text_for_letter(qa_item, normalized)
    if normalized and text:
        return f"{normalized}. {text}"
    return normalized or "No answer recorded"


def _latest_answer_recording(db, qa_item, participant):
    language = participant_language_code(participant)
    statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id == qa_item.id,
        QAItemRecording.recording_type == "answer",
        func.lower(QAItemRecording.language) == language.lower(),
    )
    if is_choice_scored_item(qa_item):
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        if correct_letter:
            statement = statement.where(
                QAItemRecording.version == ord(correct_letter) - ord("A") + 1
            )
    return db.scalars(
        statement.order_by(
            QAItemRecording.version.desc(),
            QAItemRecording.created_at.desc(),
        )
    ).first()


def _latest_question_audio_url(db, qa_item, participant):
    language = participant_language_code(participant)
    recording = get_latest_question_recording(db, qa_item.id, language)
    if recording:
        return f"/user-dashboard/api/{participant.id}/qa-question-recording/{recording.id}/audio"
    return qa_item.audio_url


def _serialize_dashboard_question(
    db,
    participant,
    assignment,
    qa_item,
    *,
    question_index=0,
):
    chapter_number = _luke_chapter_from_reference(qa_item.passage_reference)
    return {
        "assignment_id": assignment.id,
        "batch_id": assignment.batch_id,
        "question_index": max(int(question_index or 0), 0),
        "chapter": chapter_number,
        "chapter_label": f"Chapter {chapter_number}" if chapter_number else None,
        "passage_reference": qa_item.passage_reference,
        "passage_text": surrounding_passage_text(db, assignment)
        or assignment.passage_text
        or qa_item.passage_text,
        "question": qa_item.question_text,
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "mcq_choices": list(qa_item.mcq_choices or []),
        "audio_url": _latest_question_audio_url(db, qa_item, participant),
        "status": "current",
    }


def _score_text_response_with_rubric(response_text, rubric):
    normalized_text = normalize_response_text(response_text or "")
    required_keywords = rubric.required_keywords or []
    matched_keywords = []
    missing_keywords = []

    for keyword in required_keywords:
        if keyword_matches_in_response(
            keyword,
            response_text or "",
            keyword_specs=rubric.required_keyword_specs,
        ):
            matched_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    if not required_keywords:
        return (
            normalized_text,
            None,
            matched_keywords,
            missing_keywords,
            True,
            "Pending expert review: no required keywords configured for this language.",
        )

    correctness_score = len(matched_keywords) / len(required_keywords)
    needs_expert_review = bool(missing_keywords)
    flag_reason = (
        "Missing required keywords: " + ", ".join(missing_keywords)
        if missing_keywords
        else None
    )
    return (
        normalized_text,
        correctness_score,
        matched_keywords,
        missing_keywords,
        needs_expert_review,
        flag_reason,
    )


def _score_open_dashboard_response(db, participant, qa_item, response_text):
    rubric = get_language_keywords(db, qa_item.id, participant.target_language or "eng")
    return _score_text_response_with_rubric(response_text, rubric)


def _award_dashboard_currency(
    db,
    participant,
    amount,
    reason,
    *,
    assignment_id=None,
    response_id=None,
    source_event_id=None,
    metadata=None,
):
    if not amount:
        return None
    existing = None
    if response_id:
        existing = db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant.id,
                ParticipantCurrencyEvent.reason == reason,
                ParticipantCurrencyEvent.response_id == response_id,
            )
        ).first()
    elif source_event_id:
        existing = db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant.id,
                ParticipantCurrencyEvent.reason == reason,
                ParticipantCurrencyEvent.source_event_id == source_event_id,
            )
        ).first()
    if existing:
        return None

    wallet = _get_or_create_wallet(db, participant)
    wallet.balance += amount
    wallet.updated_at = utc_now()
    if amount > 0:
        wallet.lifetime_earned += amount
    else:
        wallet.lifetime_spent += abs(amount)
    event = ParticipantCurrencyEvent(
        participant_id=participant.id,
        wallet_id=wallet.id,
        assignment_id=assignment_id,
        response_id=response_id,
        amount=amount,
        balance_after=wallet.balance,
        reason=reason,
        source="user_dashboard",
        source_event_id=source_event_id,
        currency_metadata=metadata or {},
    )
    db.add(event)
    db.flush()
    return {
        "event_id": event.id,
        "amount": event.amount,
        "balance_after": event.balance_after,
        "reason": event.reason,
    }


def _select_next_dashboard_qa_item(db, participant):
    """Return ``(qa_item, cell)``. In designed-assignment (pilot) mode the item comes
    from the participant's plan and ``cell`` is the ``ExperimentPlanCell``; otherwise
    ``cell`` is None (coverage / fallback path)."""
    if experiment_assignment_enabled():
        return select_next_experiment_cell_item(db, participant)

    qa_item = select_next_qa_item(db, participant)
    if qa_item:
        return qa_item, None

    assigned_qa_item_ids = set(
        db.scalars(
            select(Assignment.qa_item_id).where(
                Assignment.participant_id == participant.id
            )
        ).all()
    )
    candidates = [
        row
        for row in db.scalars(
            select(QAItem)
            .where(
                QAItem.active.is_(True),
                QAItem.review_removed_at.is_(None),
            )
            .order_by(QAItem.review_priority.desc(), QAItem.created_at.asc())
        ).all()
        if row.id not in assigned_qa_item_ids
        and (not row.automatic_form or row.question_type == row.automatic_form)
        and qa_item_is_assignable(row)
    ]
    return (candidates[0] if candidates else None), None


def _experiment_assignment_kwargs(db, participant_session, cell, qa_item):
    """create_assignment_for_qa_item kwargs for a designed-assignment cell (empty for
    the production path). Clears the batch at a cell boundary so a batch never mixes
    conditions, and stamps the cell + its variant passage text."""
    if cell is None:
        return {}
    if experiment_batch_should_reset(db, participant_session.current_batch_id, cell):
        participant_session.current_batch_id = None
    result = {"experiment_cell_id": cell.id}
    if cell.experiment_passage_id:
        experiment_passage = db.get(ExperimentPassage, cell.experiment_passage_id)
        if experiment_passage:
            result.update(
                experiment_passage_assignment_kwargs(db, experiment_passage, qa_item)
            )
    return result


def _next_batch_hour():
    raw = os.getenv("BATCH_NEXT_ASSIGN_HOUR", str(DEFAULT_NEXT_BATCH_HOUR)).strip()
    try:
        hour = int(raw)
    except ValueError:
        return DEFAULT_NEXT_BATCH_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_NEXT_BATCH_HOUR


def _participant_zone(participant):
    for candidate in (
        getattr(participant, "timezone", None),
        os.getenv("BATCH_NEXT_ASSIGN_DEFAULT_TIMEZONE"),
        os.getenv("MESSAGE_BOT_DEFAULT_TIMEZONE"),
        DEFAULT_NEXT_BATCH_TIMEZONE,
    ):
        name = (candidate or "").strip()
        if not name:
            continue
        try:
            return name, ZoneInfo(name)
        except ZoneInfoNotFoundError:
            continue
    return DEFAULT_NEXT_BATCH_TIMEZONE, ZoneInfo(DEFAULT_NEXT_BATCH_TIMEZONE)


def _next_batch_scheduled_time(participant):
    timezone_name, participant_tz = _participant_zone(participant)
    local_now = utc_now().astimezone(participant_tz)
    scheduled_local = (local_now + timedelta(days=1)).replace(
        hour=_next_batch_hour(),
        minute=0,
        second=0,
        microsecond=0,
    )
    return scheduled_local.astimezone(timezone.utc), scheduled_local, timezone_name


def _pending_next_batch_reminder(db, participant_id):
    return db.scalars(
        select(Reminder)
        .where(
            Reminder.participant_id == participant_id,
            Reminder.reminder_type == BATCH_NEXT_ASSIGNMENT_TYPE,
            Reminder.status == ReminderStatus.PENDING.value,
        )
        .order_by(Reminder.scheduled_for.asc())
    ).first()


def _schedule_dashboard_next_batch(db, participant):
    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason="Superseded by dashboard batch-completion schedule",
    )
    scheduled_for, scheduled_local, timezone_name = _next_batch_scheduled_time(participant)
    reminder = Reminder(
        participant_id=participant.id,
        assignment_id=None,
        reminder_type=BATCH_NEXT_ASSIGNMENT_TYPE,
        message_text="Auto-assign next dashboard batch after completion",
        status=ReminderStatus.PENDING.value,
        scheduled_for=scheduled_for,
        delivery_metadata={
            "schedule": "next_day_local_time",
            "local_time": scheduled_local.isoformat(),
            "timezone": timezone_name,
            "source_surface": "user_dashboard",
        },
    )
    db.add(reminder)
    db.flush()
    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="batch_next_scheduled",
            source="user_dashboard",
            event_metadata={
                "reminder_id": reminder.id,
                "scheduled_for": scheduled_for.isoformat(),
                "scheduled_local": scheduled_local.isoformat(),
                "timezone": timezone_name,
            },
        )
    )
    return reminder


def _assign_dashboard_next_batch(db, participant, *, source, reminder=None):
    participant_session = get_or_create_participant_session(db, participant)
    if participant_session.state not in (
        SessionState.IDLE.value,
        SessionState.ONBOARDING.value,
    ):
        raise DashboardAnswerError("Finish the current question before starting a new batch")

    cancel_pending_next_batch_schedules(
        db,
        participant.id,
        reason=f"Dashboard next batch started by {source}",
    )
    participant_session.current_assignment_id = None
    participant_session.current_batch_id = None
    participant_session.state = SessionState.IDLE.value

    assignment = get_incomplete_assignment(db, participant)
    if assignment:
        qa_item = db.get(QAItem, assignment.qa_item_id)
        if not qa_item:
            raise DashboardAnswerError("Queued question is no longer available")
        participant_session.current_assignment_id = assignment.id
        participant_session.current_batch_id = assignment.batch_id
        participant_session.state = SessionState.AWAITING_RESPONSE.value
        participant_session.last_prompt_sent_at = utc_now()
        newly_assigned = False
    else:
        if not (automatic_assignment_enabled() or experiment_assignment_enabled()):
            raise DashboardAnswerError("Automatic assignment is currently disabled")
        qa_item, cell = _select_next_dashboard_qa_item(db, participant)
        if not qa_item:
            raise DashboardAnswerError("No eligible question is available for a new batch")

        prompt = create_assignment_for_qa_item(
            db,
            participant,
            participant_session,
            qa_item,
            completed_batch_size=0,
            assignment_source=source,
            **_experiment_assignment_kwargs(db, participant_session, cell, qa_item),
        )
        assignment = db.get(Assignment, prompt.assignment_id)
        newly_assigned = True
    # The question is now available on the dashboard. Stamp delivery here —
    # this is EARLIER than started_at (set when the participant opens the
    # question card, see mark_dashboard_question_viewed), so the gap
    # delivered_at -> started_at measures dashboard wait time.
    assignment.delivered_at = assignment.delivered_at or utc_now()
    if reminder:
        reminder.status = ReminderStatus.SENT.value
        reminder.sent_at = utc_now()
        reminder.updated_at = reminder.sent_at
    db.add(
        ParticipantEvent(
            participant_id=participant.id,
            event_type="batch_next_delivered",
            source="user_dashboard",
            event_metadata={
                "assignment_id": assignment.id,
                "qa_item_id": qa_item.id,
                "batch_id": assignment.batch_id,
                "reminder_id": reminder.id if reminder else None,
                "delivery": source,
                "assigned": newly_assigned,
            },
        )
    )
    db.flush()
    return assignment


def _materialize_due_dashboard_next_batch(db, participant):
    reminder = _pending_next_batch_reminder(db, participant.id)
    if not reminder or reminder.scheduled_for > utc_now():
        return None
    try:
        return _assign_dashboard_next_batch(
            db,
            participant,
            source="scheduled",
            reminder=reminder,
        )
    except DashboardAnswerError as exc:
        reminder.status = ReminderStatus.FAILED.value
        reminder.failure_reason = str(exc)
        reminder.updated_at = utc_now()
        return None


def _serialize_completed_question_review(db, participant, assignment, qa_item):
    response = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.assignment_id == assignment.id)
        .order_by(ParticipantResponse.received_at.desc(), ParticipantResponse.id.desc())
    ).first()
    if not response:
        return None

    choice_scored = is_choice_scored_item(qa_item)
    if choice_scored:
        user_letter = (response.response_text or "").strip().upper()
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        participant_answer = _format_choice_answer(qa_item, user_letter)
        correct_answer = _format_choice_answer(qa_item, correct_letter)
        correctness = format_choice_correctness_label(response.is_correct)
    else:
        participant_answer = (
            response.transcript_text or response.response_text or ""
        ).strip() or "No answer recorded"
        correct_answer = (qa_item.expected_answer or "").strip() or "No answer recorded"
        correctness = open_response_status_label(response.is_correct)

    response_audio_url = (
        f"/user-dashboard/api/{participant.id}/participant-response/{response.id}/audio"
        if (response.media_url or "").strip()
        else None
    )
    correct_recording = _latest_answer_recording(db, qa_item, participant)
    return {
        "question": qa_item.question_text,
        "passage_reference": qa_item.passage_reference,
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "participant_answer": participant_answer,
        "participant_audio_url": response_audio_url,
        "correct_answer": correct_answer,
        "correct_audio_url": (
            f"/user-dashboard/api/{participant.id}/qa-answer-recording/{correct_recording.id}/audio"
            if correct_recording
            else None
        ),
        "correctness": correctness,
        "submitted_at": _iso_datetime(response.received_at),
    }


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


def set_cosmetic_equipped(db, participant_id: str, item_id: str, equipped: bool):
    item = STORE_ITEMS.get((item_id or "").strip())
    if not item:
        raise CosmeticUpdateError("Store item not found")
    if item["item_type"] != "cosmetic":
        raise CosmeticUpdateError("Only cosmetic items can be equipped")
    slot = COSMETIC_SLOTS.get(item["item_id"])
    if not slot:
        raise CosmeticUpdateError("Cosmetic slot not found")

    participant = _participant_by_id(db, participant_id)
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
    return get_user_dashboard_payload(db, participant_id)


def set_user_streak_pause(db, participant_id: str, paused: bool):
    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise StreakPauseUpdateError("Participant not found")

    try:
        set_streak_pause(db, participant, paused)
    except ValueError as exc:
        raise StreakPauseUpdateError(str(exc)) from exc
    return get_user_dashboard_payload(db, participant_id)


def purchase_store_item(db, participant_id: str, item_id: str):
    item = STORE_ITEMS.get((item_id or "").strip())
    if not item:
        raise StorePurchaseError("Store item not found")

    participant = _participant_by_id(db, participant_id)
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
    return get_user_dashboard_payload(db, participant_id)


def _batch_reward_event(db, participant_id, batch_id):
    if not batch_id:
        return None
    return db.scalars(
        select(ParticipantCurrencyEvent)
        .where(
            ParticipantCurrencyEvent.participant_id == participant_id,
            ParticipantCurrencyEvent.reason == "batch_chest_reward",
            ParticipantCurrencyEvent.source_event_id == batch_id,
        )
        .order_by(ParticipantCurrencyEvent.created_at.desc())
    ).first()


def _batch_is_complete(db, participant_id, batch_id):
    if not batch_id:
        return False
    assignments = db.scalars(
        select(Assignment).where(
            Assignment.participant_id == participant_id,
            Assignment.batch_id == batch_id,
        )
    ).all()
    return bool(assignments) and all(
        assignment.status == AssignmentStatus.COMPLETED.value
        for assignment in assignments
    )


def claim_batch_chest_reward(db, participant_id: str, batch_id: str):
    batch_id = (batch_id or "").strip()
    if not batch_id:
        raise ChestRewardError("Batch is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise ChestRewardError("Participant not found")
    if not _batch_is_complete(db, participant.id, batch_id):
        raise ChestRewardError("Complete this batch before opening the chest")
    if _batch_reward_event(db, participant.id, batch_id):
        raise ChestRewardError("This chest is already opened")

    wallet = _get_or_create_wallet(db, participant)
    amount = random.randint(CHEST_REWARD_MIN, CHEST_REWARD_MAX)
    wallet.balance += amount
    wallet.lifetime_earned += amount
    wallet.updated_at = datetime.now(timezone.utc)

    db.add(
        ParticipantCurrencyEvent(
            participant_id=participant.id,
            wallet_id=wallet.id,
            amount=amount,
            balance_after=wallet.balance,
            reason="batch_chest_reward",
            source="user_dashboard",
            source_event_id=batch_id,
            currency_metadata={
                "batch_id": batch_id,
                "reward_type": "chest",
                "min": CHEST_REWARD_MIN,
                "max": CHEST_REWARD_MAX,
            },
        )
    )
    db.flush()
    payload = get_user_dashboard_payload(db, participant_id)
    payload["last_reward"] = {
        "type": "batch_chest",
        "batch_id": batch_id,
        "amount": amount,
        "currency": "diamonds",
    }
    return payload


DASHBOARD_ANSWER_SYNCED_NOTIFICATION = "dashboard_answer_synced"
ANSWER_LLM_SCORE_REQUESTED_NOTIFICATION = "answer_llm_score_requested"


def _enqueue_outbox_notification(db, participant, notification_type, payload):
    """Queue a cross-surface notification for the message-bot poller.

    Older pending notifications of the same type for the same participant
    are superseded so rapid dashboard answering collapses into one push.
    """

    stale = [] if notification_type == ANSWER_LLM_SCORE_REQUESTED_NOTIFICATION else db.scalars(
        select(OutboxNotification).where(
            OutboxNotification.participant_id == participant.id,
            OutboxNotification.notification_type == notification_type,
            OutboxNotification.status == OutboxStatus.PENDING.value,
        )
    ).all()
    for notification in stale:
        notification.status = OutboxStatus.SUPERSEDED.value
        notification.failure_reason = "Superseded by a newer notification"

    notification = OutboxNotification(
        participant_id=participant.id,
        notification_type=notification_type,
        payload=payload or {},
        status=OutboxStatus.PENDING.value,
    )
    db.add(notification)
    return notification


def mark_dashboard_question_viewed(db, participant_id: str, assignment_id: str):
    """Record that a question was first rendered on the dashboard.

    Starts the time-on-task clock (assignment.started_at) if it has not
    already been started by a messenger delivery.
    """

    assignment_id = (assignment_id or "").strip()
    if not assignment_id:
        raise DashboardAnswerError("Assignment is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")

    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.participant_id != participant.id:
        raise DashboardAnswerError("Assignment not found")

    started_now = False
    if (
        assignment.status != AssignmentStatus.COMPLETED.value
        and assignment.started_at is None
    ):
        now = utc_now()
        # Fallback: if the question was never marked delivered (e.g. it was
        # created and opened without going through the batch-delivery path),
        # treat this first render as the delivery moment too.
        assignment.delivered_at = assignment.delivered_at or now
        assignment.started_at = now
        started_now = True

    record_participant_event(
        db,
        participant,
        "question_viewed",
        {
            "assignment_id": assignment.id,
            "qa_item_id": assignment.qa_item_id,
            "batch_id": assignment.batch_id,
            "started_clock": started_now,
            "source_surface": "user_dashboard",
        },
        source="user_dashboard",
    )
    return {
        "assignment_id": assignment.id,
        "started_at": _iso_datetime(assignment.started_at),
        "started_clock": started_now,
    }


# Client posts a heartbeat on this cadence while the dashboard tab is visible.
DASHBOARD_HEARTBEAT_INTERVAL_SECONDS = 15
# A gap larger than this means the tab was backgrounded/closed between beats, so
# the intervening time is NOT counted as engaged dwell (prevents inflation).
DASHBOARD_HEARTBEAT_MAX_GAP_SECONDS = 3 * DASHBOARD_HEARTBEAT_INTERVAL_SECONDS


def _as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def record_dashboard_heartbeat(db, participant_id: str, session_key: str, *, active: bool = True):
    """Accumulate engaged dwell time for one dashboard browser session.

    Idempotent-ish upsert keyed by (participant_id, session_key). Each call
    advances ``active_seconds`` by the elapsed time since the previous
    heartbeat, but only when the page reported itself active and the gap is
    within ``DASHBOARD_HEARTBEAT_MAX_GAP_SECONDS`` (so an idle/hidden tab that
    resumes does not book the away-time as engagement). Dashboard-only; there is
    no messenger equivalent.
    """

    session_key = (session_key or "").strip()
    if not session_key:
        raise DashboardAnswerError("Session key is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")

    now = utc_now()
    session = db.scalars(
        select(DashboardEngagementSession).where(
            DashboardEngagementSession.participant_id == participant.id,
            DashboardEngagementSession.session_key == session_key,
        )
    ).first()

    if session is None:
        session = DashboardEngagementSession(
            participant_id=participant.id,
            session_key=session_key,
            started_at=now,
            last_heartbeat_at=now,
            active_seconds=0,
            heartbeat_count=1,
        )
        db.add(session)
    else:
        delta = (now - _as_utc(session.last_heartbeat_at)).total_seconds()
        if active and 0 < delta <= DASHBOARD_HEARTBEAT_MAX_GAP_SECONDS:
            session.active_seconds = int(session.active_seconds + round(delta))
        session.last_heartbeat_at = now
        session.heartbeat_count = (session.heartbeat_count or 0) + 1

    return {
        "session_key": session_key,
        "active_seconds": session.active_seconds,
        "heartbeat_count": session.heartbeat_count,
    }


def submit_dashboard_answer(db, participant_id: str, assignment_id: str, response_text: str):
    assignment_id = (assignment_id or "").strip()
    answer_text = (response_text or "").strip()
    if not assignment_id:
        raise DashboardAnswerError("Assignment is required")
    if not answer_text:
        raise DashboardAnswerError("Answer is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")

    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.participant_id != participant.id:
        raise DashboardAnswerError("Assignment not found")
    if assignment.status == AssignmentStatus.COMPLETED.value:
        raise DashboardAnswerError("This question is already answered")

    qa_item = assignment.qa_item or db.get(QAItem, assignment.qa_item_id)
    if not qa_item:
        raise DashboardAnswerError("Question not found")

    # Race guard: atomically claim the assignment; the first surface
    # (dashboard or messenger) to complete it wins.
    if not try_complete_assignment(db, assignment):
        raise DashboardAnswerError("This question is already answered")

    participant_session = get_or_create_participant_session(db, participant)
    participant_session.current_assignment_id = assignment.id
    participant_session.current_batch_id = assignment.batch_id
    participant_session.state = SessionState.AWAITING_RESPONSE.value

    normalized_text = None
    correctness_score = None
    matched_keywords = []
    missing_keywords = []
    flag_reason = None
    needs_expert_review = False
    stored_response_text = answer_text
    backtranslated_text = None
    scoring_metadata = {}

    if is_choice_scored_item(qa_item):
        choice_correct = choice_response_is_correct(qa_item, answer_text)
        stored_response_text = choice_response_letter(qa_item, answer_text)
        is_correct_label = "yes (auto)" if choice_correct else "no (auto)"
        review_status = ReviewStatus.AUTO.value
    else:
        (
            normalized_text,
            correctness_score,
            matched_keywords,
            missing_keywords,
            needs_expert_review,
            flag_reason,
        ) = _score_open_dashboard_response(db, participant, qa_item, answer_text)
        if needs_expert_review:
            is_correct_label = "pending"
        elif correctness_score is not None and correctness_score < 1.0:
            is_correct_label = "no (auto)"
        else:
            is_correct_label = "yes (auto)"
        review_status = (
            ReviewStatus.PENDING.value
            if needs_expert_review
            else ReviewStatus.AUTO.value
        )
        if llm_answer_scoring_enabled():
            correctness_score = None
            is_correct_label = "pending"
            review_status = ReviewStatus.PENDING.value
            flag_reason = "LLM scoring queued."
            scoring_metadata = {"method": "backtranslation_binary_llm", "status": "queued"}

    response = ParticipantResponse(
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        assignment_id=assignment.id,
        response_type=ResponseType.TEXT.value,
        response_text=stored_response_text,
        normalized_text=normalized_text,
        backtranslated_text=backtranslated_text,
        scoring_metadata=scoring_metadata,
        correctness_score=correctness_score,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        is_correct=is_correct_label,
        flag_reason=flag_reason,
        review_status=review_status,
        source_channel=SourceChannel.USER_DASHBOARD.value,
    )
    db.add(response)
    db.flush()
    if not is_choice_scored_item(qa_item) and llm_answer_scoring_enabled():
        _enqueue_outbox_notification(
            db, participant, ANSWER_LLM_SCORE_REQUESTED_NOTIFICATION,
            {"response_id": response.id},
        )

    now = utc_now()
    # status/completed_at/attempt_count were set atomically by
    # try_complete_assignment above; keep the started_at backfill as a
    # fallback for assignments never marked viewed.
    assignment.started_at = assignment.started_at or assignment.completed_at or now
    participant.completed_count = (participant.completed_count or 0) + 1
    participant.last_seen_at = now
    participant_session.current_assignment_id = None
    participant_session.state = SessionState.IDLE.value

    record_participant_event(
        db,
        participant,
        "response_recorded",
        {
            "assignment_id": assignment.id,
            "qa_item_id": qa_item.id,
            "response_type": ResponseType.TEXT.value,
            "correctness_score": correctness_score,
            "is_correct": is_correct_label,
            "choice_scored": is_choice_scored_item(qa_item),
            "question_type": qa_item.question_type,
            "source_surface": "user_dashboard",
        },
        source="user_dashboard",
    )
    db.flush()

    response_amount = (
        FIRST_ANSWER_COMPLETED_DIAMONDS
        if (participant.completed_count or 0) == 1
        else ANSWER_COMPLETED_DIAMONDS
    )
    _award_dashboard_currency(
        db,
        participant,
        response_amount,
        "answer_completed",
        assignment_id=assignment.id,
        response_id=response.id,
        metadata={
            "qa_item_id": qa_item.id,
            "response_type": response.response_type,
            "first_answer_bonus": response_amount == FIRST_ANSWER_COMPLETED_DIAMONDS,
        },
    )
    update_streak_for_response(db, participant, response)

    batch_completed, completed_batch_size = complete_current_batch_if_needed(
        db,
        participant,
        participant_session,
    )
    next_assignment_id = None
    next_question = None
    if batch_completed:
        _schedule_dashboard_next_batch(db, participant)
        batch_event = db.scalars(
            select(ParticipantEvent)
            .where(
                ParticipantEvent.participant_id == participant.id,
                ParticipantEvent.event_type == "batch_completed",
            )
            .order_by(ParticipantEvent.created_at.desc(), ParticipantEvent.id.desc())
        ).first()
        _award_dashboard_currency(
            db,
            participant,
            BATCH_COMPLETED_BONUS_DIAMONDS,
            "batch_completed_bonus",
            source_event_id=batch_event.id if batch_event else assignment.batch_id,
            metadata={
                "batch_id": assignment.batch_id,
                "completed_batch_size": completed_batch_size,
            },
        )
    else:
        participant_session.current_batch_id = assignment.batch_id
        next_assignment = db.scalar(
            select(Assignment)
            .where(
                Assignment.participant_id == participant.id,
                Assignment.batch_id == participant_session.current_batch_id,
                Assignment.status == AssignmentStatus.ASSIGNED.value,
            )
            .order_by(Assignment.assigned_at, Assignment.id)
        )
        if next_assignment:
            next_qa_item = db.get(QAItem, next_assignment.qa_item_id)
            if next_qa_item:
                participant_session.current_assignment_id = next_assignment.id
                participant_session.state = SessionState.AWAITING_RESPONSE.value
                participant_session.last_prompt_sent_at = utc_now()
                next_assignment_id = next_assignment.id
                next_question = _serialize_dashboard_question(
                    db,
                    participant,
                    next_assignment,
                    next_qa_item,
                    question_index=completed_batch_size,
                )
        else:
            next_qa_item, next_cell = (
                _select_next_dashboard_qa_item(db, participant)
                if (automatic_assignment_enabled() or experiment_assignment_enabled())
                else (None, None)
            )
        if not next_assignment and next_qa_item:
            next_prompt = create_assignment_for_qa_item(
                db,
                participant,
                participant_session,
                next_qa_item,
                completed_batch_size=completed_batch_size,
                assignment_source="user_dashboard",
                **_experiment_assignment_kwargs(
                    db, participant_session, next_cell, next_qa_item
                ),
            )
            next_assignment_id = next_prompt.assignment_id if next_prompt else None
            if next_assignment_id:
                next_assignment = db.get(Assignment, next_assignment_id)
                next_question = _serialize_dashboard_question(
                    db,
                    participant,
                    next_assignment,
                    next_qa_item,
                    question_index=completed_batch_size,
                )
        elif not next_assignment:
            participant_session.state = SessionState.IDLE.value

    _enqueue_outbox_notification(
        db,
        participant,
        DASHBOARD_ANSWER_SYNCED_NOTIFICATION,
        {
            "response_id": response.id,
            "assignment_id": assignment.id,
            "qa_item_id": qa_item.id,
            "batch_id": assignment.batch_id,
            "batch_completed": batch_completed,
            "completed_batch_size": completed_batch_size,
            "next_assignment_id": next_assignment_id,
        },
    )

    db.flush()
    wallet = _get_or_create_wallet(db, participant)
    return {
        "answer_submission": {
            "assignment_id": assignment.id,
            "response_id": response.id,
            "batch_id": assignment.batch_id,
            "batch_completed": batch_completed,
            "completed_batch_size": completed_batch_size,
            "next_assignment_id": next_assignment_id,
            "is_correct": is_correct_label,
        },
        "next_question": next_question,
        "wallet": {
            "balance": wallet.balance,
        },
        "awards": {
            "answer": response_amount,
            "batch_completed": BATCH_COMPLETED_BONUS_DIAMONDS if batch_completed else 0,
        },
    }


def start_dashboard_new_batch(db, participant_id: str):
    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")
    _assign_dashboard_next_batch(db, participant, source="manual")
    return get_user_dashboard_payload(db, participant_id)


def update_profile_photo(db, participant_id: str, content: bytes, content_type: str):
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


def _normalized_team_name(name):
    value = " ".join(str(name or "").split())
    if not value:
        raise CommunityTeamError("Team name is required")
    if len(value) > 64:
        raise CommunityTeamError("Team name must be 64 characters or fewer")
    return value


def _participant_team_membership(db, participant_id):
    return db.scalar(
        select(CommunityTeamMember).where(
            CommunityTeamMember.participant_id == participant_id
        )
    )


def create_community_team(db, participant_id, name):
    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise CommunityTeamError("Participant not found")
    if _participant_team_membership(db, participant.id):
        raise CommunityTeamError("You are already on a team")
    name = _normalized_team_name(name)
    existing = db.scalar(
        select(CommunityTeam).where(func.lower(CommunityTeam.name) == name.lower())
    )
    if existing:
        raise CommunityTeamError("A team with that name already exists")

    team = CommunityTeam(
        name=name,
        creator_participant_id=participant.id,
        target_language=participant.target_language,
    )
    db.add(team)
    db.flush()
    db.add(CommunityTeamMember(team_id=team.id, participant_id=participant.id))
    db.flush()
    return get_user_dashboard_payload(db, participant.id)


def join_community_team(db, participant_id, team_id):
    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise CommunityTeamError("Participant not found")
    if _participant_team_membership(db, participant.id):
        raise CommunityTeamError("You are already on a team")
    team = db.scalar(
        select(CommunityTeam).where(CommunityTeam.id == str(team_id or "")).with_for_update()
    )
    if not team:
        raise CommunityTeamError("Team not found")
    if team.target_language != participant.target_language:
        raise CommunityTeamError("You can only join a team in your language community")
    member_count = db.scalar(
        select(func.count(CommunityTeamMember.id)).where(
            CommunityTeamMember.team_id == team.id
        )
    )
    if int(member_count or 0) >= TEAM_MAX_MEMBERS:
        raise CommunityTeamError("This team already has 4 members")
    db.add(CommunityTeamMember(team_id=team.id, participant_id=participant.id))
    db.flush()
    return get_user_dashboard_payload(db, participant.id)


def rename_community_team(db, participant_id, team_id, name):
    team = db.scalar(select(CommunityTeam).where(CommunityTeam.id == str(team_id or "")))
    if not team:
        raise CommunityTeamError("Team not found")
    if team.creator_participant_id != participant_id:
        raise CommunityTeamError("Only the team creator can change its name")
    name = _normalized_team_name(name)
    existing = db.scalar(
        select(CommunityTeam).where(
            func.lower(CommunityTeam.name) == name.lower(),
            CommunityTeam.id != team.id,
        )
    )
    if existing:
        raise CommunityTeamError("A team with that name already exists")
    team.name = name
    team.updated_at = datetime.now(timezone.utc)
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


def leave_community_team(db, participant_id, team_id):
    membership = db.scalar(
        select(CommunityTeamMember).where(
            CommunityTeamMember.team_id == str(team_id or ""),
            CommunityTeamMember.participant_id == participant_id,
        )
    )
    if not membership:
        raise CommunityTeamError("You are not a member of this team")
    team = db.scalar(select(CommunityTeam).where(CommunityTeam.id == membership.team_id))
    if team and team.creator_participant_id == participant_id:
        raise CommunityTeamError("Team creators must remove the team instead of leaving it")
    db.delete(membership)
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


def remove_community_team(db, participant_id, team_id):
    team = db.scalar(select(CommunityTeam).where(CommunityTeam.id == str(team_id or "")))
    if not team:
        raise CommunityTeamError("Team not found")
    if team.creator_participant_id != participant_id:
        raise CommunityTeamError("Only the team creator can remove the team")
    # Explicit deletion keeps this operation correct in SQLite tests as well as
    # PostgreSQL, where the foreign key also cascades team membership deletion.
    db.execute(
        delete(CommunityTeamMember).where(CommunityTeamMember.team_id == team.id)
    )
    db.delete(team)
    db.flush()
    return get_user_dashboard_payload(db, participant_id)


def get_language_team_leaderboard(db, participant, week_start, week_end):
    teams = db.scalars(
        select(CommunityTeam)
        .where(CommunityTeam.target_language == participant.target_language)
        .order_by(CommunityTeam.created_at.asc())
    ).all()
    if not teams:
        return []
    team_ids = [team.id for team in teams]
    memberships = db.execute(
        select(CommunityTeamMember, Participant)
        .join(Participant, Participant.id == CommunityTeamMember.participant_id)
        .where(CommunityTeamMember.team_id.in_(team_ids))
        .order_by(CommunityTeamMember.joined_at.asc())
    ).all()
    member_ids = [member.participant_id for member, _ in memberships]
    scores = {}
    if member_ids:
        scores = {
            participant_id: int(score or 0)
            for participant_id, score in db.execute(
                select(
                    ParticipantCurrencyEvent.participant_id,
                    func.coalesce(func.sum(ParticipantCurrencyEvent.amount), 0),
                )
                .where(
                    ParticipantCurrencyEvent.participant_id.in_(member_ids),
                    ParticipantCurrencyEvent.created_at >= week_start,
                    ParticipantCurrencyEvent.created_at < week_end,
                    ParticipantCurrencyEvent.amount > 0,
                )
                .group_by(ParticipantCurrencyEvent.participant_id)
            ).all()
        }
    members_by_team = {team_id: [] for team_id in team_ids}
    for membership, member_participant in memberships:
        members_by_team[membership.team_id].append(
            {
                "participant_id": member_participant.id,
                "display_name": _display_name_for_leaderboard(member_participant, 0),
            }
        )
    rows = [
        {
            "team_id": team.id,
            "display_name": team.name,
            "weekly_earned": sum(
                scores.get(member["participant_id"], 0)
                for member in members_by_team[team.id]
            ),
            "members": members_by_team[team.id],
            "member_ids": [member["participant_id"] for member in members_by_team[team.id]],
            "member_count": len(members_by_team[team.id]),
            "is_current_user": any(
                member["participant_id"] == participant.id
                for member in members_by_team[team.id]
            ),
            "is_creator": team.creator_participant_id == participant.id,
        }
        for team in teams
    ]
    rows.sort(key=lambda row: (-row["weekly_earned"], row["display_name"].lower()))
    previous_score = None
    rank = 0
    for index, row in enumerate(rows, start=1):
        if previous_score is None or row["weekly_earned"] < previous_score:
            rank = index
        row["rank"] = rank
        previous_score = row["weekly_earned"]
    return rows


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
        "teams": get_language_team_leaderboard(db, participant, week_start, week_end),
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
        chapter = _luke_chapter_from_reference(passage_reference)
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


def get_luke_journey_chapters(db, participant_id):
    participant = db.get(Participant, participant_id)
    preferred_batch_size = max(int(getattr(participant, "preferred_batch_size", 3) or 3), 1)
    chest_reward_events = {
        event.source_event_id: event
        for event in db.scalars(
            select(ParticipantCurrencyEvent).where(
                ParticipantCurrencyEvent.participant_id == participant_id,
                ParticipantCurrencyEvent.reason == "batch_chest_reward",
                ParticipantCurrencyEvent.source_event_id.is_not(None),
            )
        ).all()
    }
    rows = db.execute(
        select(Assignment, QAItem)
        .join(QAItem, QAItem.id == Assignment.qa_item_id)
        .where(Assignment.participant_id == participant_id)
        .order_by(Assignment.assigned_at.asc(), Assignment.id.asc())
    ).all()
    batches = []
    batch_index = {}
    for assignment, qa_item in rows:
        chapter_number = _luke_chapter_from_reference(qa_item.passage_reference)
        if not chapter_number:
            continue
        batch_id = assignment.batch_id or f"single-{assignment.id}"
        batch = batch_index.get(batch_id)
        if not batch:
            batch = {
                "batch_id": batch_id,
                "label": f"Batch {len(batches) + 1}",
                "target_size": preferred_batch_size,
                "questions": [],
            }
            batch_index[batch_id] = batch
            batches.append(batch)
        complete = assignment.status == AssignmentStatus.COMPLETED.value
        question = {
            **_serialize_dashboard_question(
                db,
                participant,
                assignment,
                qa_item,
                question_index=len(batch["questions"]),
            ),
            "status": "complete" if complete else "current",
        }
        if complete:
            question["review"] = _serialize_completed_question_review(
                db, participant, assignment, qa_item
            )
        batch["questions"].append(question)

    if not batches:
        return []

    completed_questions = 0
    total_questions = 0
    active_batch_index = None
    for index, batch in enumerate(batches):
        total_questions += len(batch["questions"])
        batch_completed = all(
            question["status"] == "complete" for question in batch["questions"]
        )
        if batch_completed:
            batch["status"] = "complete"
            completed_questions += len(batch["questions"])
        elif active_batch_index is None:
            active_batch_index = index
            batch["status"] = "active"
            batch["target_size"] = max(preferred_batch_size, len(batch["questions"]))
            found_current = False
            for question in batch["questions"]:
                if question["status"] == "complete":
                    completed_questions += 1
                elif not found_current:
                    question["status"] = "current"
                    found_current = True
                else:
                    question["status"] = "locked"
            while len(batch["questions"]) < batch["target_size"]:
                batch["questions"].append(
                    {
                        "assignment_id": None,
                        "qa_item_id": None,
                        "chapter": None,
                        "chapter_label": None,
                        "passage_reference": None,
                        "question": f"Question {len(batch['questions']) + 1}",
                        "status": "locked",
                        "placeholder": True,
                    }
                )
        else:
            batch["status"] = "locked"
            for question in batch["questions"]:
                if question["status"] != "complete":
                    question["status"] = "locked"
        reward_event = chest_reward_events.get(batch["batch_id"])
        batch["reward"] = {
            "type": "chest",
            "min": CHEST_REWARD_MIN,
            "max": CHEST_REWARD_MAX,
            "currency": "diamonds",
            "claimed": bool(reward_event),
            "claimable": batch["status"] == "complete" and not reward_event,
            "amount": reward_event.amount if reward_event else None,
        }
    if active_batch_index is None:
        active_batch_index = max(0, len(batches) - 1)

    return [
        {
            "title": "Question Path",
            "batches": batches,
            "progress": completed_questions / total_questions if total_questions else 0,
            "status": (
                "complete"
                if total_questions and completed_questions == total_questions
                else "continue"
            ),
            "current_batch_index": active_batch_index,
        }
    ]


def get_user_dashboard_payload(db, participant_id: str, event_limit: int = 100):
    participant = _participant_by_id(db, participant_id)
    if not participant:
        return None

    _materialize_due_dashboard_next_batch(db, participant)
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
        "journey_chapters": get_luke_journey_chapters(db, participant.id),
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
            "participant_id": participant.id,
            "profile_photo_url": _profile_photo_url(participant_id, participant),
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
        "settings": {
            "language": (participant.dashboard_preferences or {}).get("language", "en"),
            "batch_size": max(int(participant.preferred_batch_size or 3), 1),
        },
        **view_model,
    }


SUPPORTED_DASHBOARD_LANGUAGES = ("en", "zh")


class DashboardSettingsError(Exception):
    pass


def update_dashboard_settings(db, participant_id: str, *, language=None, batch_size=None):
    """Persist the participant's dashboard language and/or preferred batch size,
    then return the fresh dashboard payload."""
    from eten_shared.domain.batch_size_nudges import clamp_batch_size

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardSettingsError("Participant not found")

    changed = {}
    if language is not None:
        lang = str(language).strip().lower()
        if lang not in SUPPORTED_DASHBOARD_LANGUAGES:
            raise DashboardSettingsError("Unsupported language")
        preferences = dict(participant.dashboard_preferences or {})
        preferences["language"] = lang
        participant.dashboard_preferences = preferences
        changed["language"] = lang

    if batch_size is not None:
        try:
            size = clamp_batch_size(int(batch_size))
        except (TypeError, ValueError) as exc:
            raise DashboardSettingsError("Batch size must be a whole number") from exc
        participant.preferred_batch_size = size
        changed["batch_size"] = size

    if changed:
        participant.updated_at = datetime.now(timezone.utc)
        db.add(
            ParticipantEvent(
                participant_id=participant.id,
                event_type="dashboard_settings_updated",
                source="user_dashboard",
                event_metadata=changed,
            )
        )
        db.flush()

    return get_user_dashboard_payload(db, participant_id)
