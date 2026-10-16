"""Shared constants for dashboard services."""

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
