---
title: Eten Whatsapp Bot
emoji: 🐨
colorFrom: yellow
colorTo: yellow
sdk: docker
pinned: false
---

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference

## WhatsApp webhook

The Flask app exposes the WhatsApp webhook at:

```text
/webhook
```

Meta sends incoming WhatsApp events to this endpoint. When the app receives a
valid text message, it now sends the response back to the sender's WhatsApp ID
from the webhook payload instead of a fixed `RECIPIENT_WAID` value.

## Database

This project is prepared to use Supabase Postgres for the translation quality
validation workflow. Set the Supabase connection string in the deployed Space:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/postgres
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR-SERVICE-ROLE-KEY
SUPABASE_AUDIO_BUCKET=whatsapp-audio
```

Create a private Supabase Storage bucket named `whatsapp-audio`, or set
`SUPABASE_AUDIO_BUCKET` to another bucket name. Audio answers are uploaded to
Supabase Storage and saved on `ParticipantResponse.media_url` as a storage URI,
for example `storage://whatsapp-audio/whatsapp/2026/05/22/MEDIA_ID.ogg`. Use
Supabase Storage signed URLs to access private audio objects later.

The app normalizes `postgres://` and `postgresql://` URLs for SQLAlchemy's
`psycopg` driver. The core ORM models are defined in `app/models.py`:

- `Participant`: target-language speaker using the WhatsApp chatbot.
- `QAItem`: audio passage question, expected answer, and keyword metadata.
- `Assignment`: question assigned to a participant as part of a microtask batch.
- `ParticipantResponse`: text/audio response, scoring data, and review flags.
- `ParticipantEvent`: engagement analytics events such as joined, answered, completed, or opted out.
- `Reminder`: scheduled reminder messages and delivery history.
- `ParticipantBadge`: badges or recognition milestones awarded to participants.
- `ParticipantSession`: current chatbot state, active batch/assignment, and reminder preferences.

For Supabase setup, run `supabase/schema.sql` in the Supabase SQL editor to
create the prototype tables and indexes.

## Chatbot workflow persistence

When a WhatsApp text message arrives, the webhook now records the core workflow
before sending the chat response:

1. Find or create the `Participant` by WhatsApp `wa_id`.
2. Update `Participant.last_seen_at`.
3. Create a `ParticipantEvent` with `event_type = message_received`.
4. Find or create the participant's `ParticipantSession`.
5. If the incoming WhatsApp message is an audio/voice note, fetch the media
   from Meta, upload the audio file to Supabase Storage, save its storage URI
   on `ParticipantResponse.media_url`, and pass that URI through the placeholder
   transcription adapter in `app/services/transcription_service.py`. Replace
   that adapter with the team speech-to-text model when it is ready.
6. If the session has a `current_assignment_id`, save a `ParticipantResponse`,
   score the text answer or audio transcript against the QA item's required
   keywords, complete the assignment, and return the session to `idle`.
7. When the session is idle, first check the current batch. If the number of
   completed assignments in `ParticipantSession.current_batch_id` has reached
   `Participant.preferred_batch_size`, clear the current batch, record a
   `batch_completed` event, and send a batch-complete message instead of another
   question.
8. If the batch is still open, select the next eligible active `QAItem`, create
   an `Assignment`, update the session to `awaiting_response`, and send the
   audio passage plus question text over WhatsApp. Selection skips QA items
   already assigned to the participant and prioritizes: response gap
   (`min_responses_required - actual_response_count`), accuracy risk from low
   correctness/high flag rate, `review_priority`, and then lower coverage.

## Reminder scheduler

When a new assignment is created, the app schedules three pending reminders for
that assignment:

- `assignment_pending_3h`: 3 hours after assignment creation.
- `assignment_pending_9h`: 9 hours after assignment creation, which is another
  6 hours after the first reminder.
- `assignment_pending_21h`: 21 hours after assignment creation, which is another
  12 hours after the second reminder.

A lightweight Flask background thread starts with the app and polls for due
reminders every 300 seconds by default. Configure it with:

```text
REMINDER_SCHEDULER_ENABLED=true
REMINDER_POLL_INTERVAL_SECONDS=300
REMINDER_MAX_RETRIES=3
REMINDER_RETRY_BACKOFF_MINUTES=5,15,30
```

The scheduler sends only pending reminders whose assignments are still
incomplete, whose participant has reminders enabled, and whose participant has
not opted out. It marks reminders as `sent`, `failed`, or `cancelled`, and
records `ParticipantEvent(reminder_sent)` when a reminder is delivered. If a
WhatsApp send fails, the reminder is returned to `pending` and retried with the
configured backoff sequence. Retry metadata is stored in
`Reminder.delivery_metadata`; after `REMINDER_MAX_RETRIES` is exceeded, the
reminder is marked `failed`.

WhatsApp allows free-form customer-service messages only inside a 24-hour window
after the participant last messaged the bot. These reminders are scheduled at
3h, 9h, and 21h so they normally fit inside that window. If a reminder becomes
due after the 24-hour window, the prototype cancels it. To contact participants
after 24 hours, create an approved WhatsApp message template in Meta WhatsApp
Manager, wait for approval, and send that template through the Graph API instead
of a normal text message.
