"""Shared dependencies, constants, and errors for dashboard services."""

"""Participant wallet, store, and cosmetic helpers for the user dashboard."""

from datetime import datetime, timedelta, timezone

import hashlib

import os

import random

import re

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, distinct, func, select

from eten_shared.answer_llm_scoring import llm_answer_scoring_enabled

from eten_shared.answer_receipts import create_answer_receipt

from eten_shared.domain.batch_schedules import (
    BATCH_NEXT_ASSIGNMENT_TYPE,
    cancel_pending_next_batch_schedules,
)

from eten_shared.domain.assignments import (
    automatic_assignment_enabled,
    complete_current_batch_if_needed,
    create_assignment_for_qa_item,
    ExperimentPassageMissingError,
    experiment_passage_assignment_kwargs,
    resolve_experiment_passage,
    experiment_assignment_enabled,
    get_incomplete_assignment,
    get_or_create_participant_session,
    record_participant_event,
    surrounding_passage_text,
    assignment_passage_snapshot,
    try_complete_assignment,
)

from eten_shared.domain.qa_eligibility import qa_item_is_assignable

from eten_shared.keyword_matching import normalize_response_text

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
    choice_letters_for_type,
    choice_response_is_correct,
    choice_response_letter,
    is_choice_scored_item,
    question_type_value,
)

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

from backend.shared.response_labels import (
    format_choice_correctness_label,
    open_response_status_label,
)

from backend.user_dashboard.view_model import compose_dashboard_view_model
from backend.user_dashboard.errors import (
    ChestRewardError,
    CommunityTeamError,
    CosmeticUpdateError,
    DashboardAnswerError,
    DashboardSettingsError,
    ProfilePhotoNotFoundError,
    ProfilePhotoUploadError,
    StorePurchaseError,
    StreakPauseUpdateError,
)

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

