# User Currency Dashboard

Standalone static dashboard for viewing a participant wallet, badges, weekly language leaderboard, and currency ledger.

Open `index.html` in a browser. The page loads sample data by default when no WhatsApp id is present.

Profile photos are uploaded from the dashboard with the `Change photo` control.
Changing the photo costs 5 diamonds. On mobile browsers, this opens the phone photo
picker/camera options. Uploaded photos are stored in Supabase Storage and saved
on the participant profile.

To load from the platform database, start the Flask platform API and open one of:

```text
http://127.0.0.1:7860/user_dashboard/index.html/<user_wa_id>
http://127.0.0.1:5500/user_dashboard/index.html/<user_wa_id>
http://127.0.0.1:5500/user_dashboard/index.html?wa_id=<user_wa_id>
http://127.0.0.1:5500/user_dashboard/index.html#<user_wa_id>
```

The dashboard calls:

```text
http://127.0.0.1:7860/user-dashboard/api/<user_wa_id>
```

If your platform API runs elsewhere, add `?api_base=http://host:port`.

For the exact `/index.html/<user_wa_id>` URL shape, use the bundled static server:

```bash
python platform/user_dashboard/server.py
```

API payload shape:

```json
{
  "participant": {
    "id": "participant-id",
    "display_name": "Participant Name",
    "wa_id": "15551234567",
    "profile_photo_url": "https://signed-storage-url.example"
  },
  "wallet": {
    "balance": 18
  },
  "xp_points": 0,
  "history_summary": {
    "total_questions_answered": 12,
    "total_batches_answered": 4
  },
  "events": [
    {
      "created_at": "2026-06-16T12:05:00Z",
      "reason": "batch_completed_bonus",
      "amount": 3,
      "balance_after": 18
    }
  ],
  "badges": [
    {
      "badge_type": "first_batch",
      "title": "First Batch",
      "description": "Completed the first question batch.",
      "awarded_at": "2026-06-14T15:18:00Z"
    }
  ],
  "leaderboard": {
    "scope": "language",
    "language": "eng",
    "week_start": "2026-06-15T00:00:00+00:00",
    "week_end": "2026-06-22T00:00:00+00:00",
    "current_user": {
      "rank": 2,
      "participant_id": "participant-id",
      "display_name": "Participant Name",
      "weekly_earned": 12,
      "is_current_user": true
    },
    "rows": []
  },
  "store": {
    "items": [
      {
        "item_id": "streak_freeze",
        "title": "Streak Freeze",
        "description": "Protects your streak for one missed day.",
        "cost": 8,
        "item_type": "consumable",
        "max_owned": 3
      },
      {
        "item_id": "dashboard_background_sunrise",
        "title": "Sunrise Background",
        "description": "Changes your dashboard background to a warm sunrise color.",
        "cost": 8,
        "item_type": "cosmetic",
        "max_owned": 1
      },
      {
        "item_id": "profile_frame_gold",
        "title": "Gold Profile Frame",
        "description": "Adds a gold frame to your dashboard profile.",
        "cost": 10,
        "item_type": "cosmetic",
        "max_owned": 1
      },
      {
        "item_id": "extra_life",
        "title": "Extra Life",
        "description": "A saved recovery chance for future retry mechanics.",
        "cost": 12,
        "item_type": "consumable",
        "max_owned": 3
      }
    ],
    "inventory": {
      "streak_freeze": {
        "owned": 0,
        "max_owned": 3
      },
      "profile_frame_gold": {
        "owned": 0,
        "max_owned": 1
      },
      "dashboard_background_sunrise": {
        "owned": 0,
        "max_owned": 1
      },
      "extra_life": {
        "owned": 0,
        "max_owned": 3
      }
    }
  },
  "cosmetics": {
    "equipped": {
      "profile_frame": null,
      "dashboard_background": null
    }
  }
}
```
