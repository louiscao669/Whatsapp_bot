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
REMINDER_TEMPLATE_NAME=question_pending_reminder
REMINDER_TEMPLATE_LANGUAGE=en_US
REMINDER_TEMPLATE_BODY_PARAMS={name}
REMINDER_TEMPLATE_FIRST_DELAY_HOURS=48
REMINDER_TEMPLATE_REPEAT_HOURS=48
REMINDER_TEMPLATE_MAX_COUNT=0
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
after the participant last messaged the bot. The free-form reminders are
scheduled at 3h, 9h, and 21h so they normally fit inside that window. If a
free-form reminder becomes due after the 24-hour window, the prototype cancels
it.

To contact participants after 24 hours, create an approved WhatsApp message
template in Meta WhatsApp Manager. Set `REMINDER_TEMPLATE_NAME` to that approved
template name and `REMINDER_TEMPLATE_LANGUAGE` to its language code. When a
template name is configured, the app schedules a template reminder 48 hours
after assignment creation by default: this is the first 24-hour service window
plus another 24 hours. After each successful template send, it schedules the
next template reminder 48 hours later until the assignment is completed, the
participant opts out, or `REMINDER_TEMPLATE_MAX_COUNT` is reached. Use
`REMINDER_TEMPLATE_MAX_COUNT=0` for no fixed maximum.

`REMINDER_TEMPLATE_BODY_PARAMS` is optional. Use a comma-separated list of text
parameters if your approved template has body variables. Supported placeholders
include `{name}`, `{wa_id}`, `{assignment_id}`, and `{reminder_type}`. For a
template with no variables, leave it empty.

## Badge awards

The workflow awards lightweight participation badges after answers and batch
completion. Awarded badges are saved in `participant_badges`, mirrored as
`ParticipantEvent(badge_awarded)`, and announced through WhatsApp. Initial badge
rules are:

- `first_response`: awarded after the participant submits the first answer.
- `completed_first_batch`: awarded after the first completed batch.
- `completed_5_questions`: awarded after 5 completed answers.
- `completed_10_questions`: awarded after 10 completed answers.
- `completed_25_questions`: awarded after 25 completed answers.

Badges are idempotent per participant because the database enforces uniqueness
across `participant_id` and `badge_type`.

## Admin CSV exports

The app exposes token-protected CSV exports for expert review and offline
analysis:

```text
GET /admin/export/responses.csv
GET /admin/export/flagged.csv
```

Configure a strong admin token in the deployed Space:

```text
ADMIN_API_TOKEN=replace-with-a-long-random-token
```

Then call the endpoints with a bearer token:

```bash
curl -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  https://YOUR-SPACE.hf.space/admin/export/flagged.csv
```

`responses.csv` exports all participant responses. `flagged.csv` exports only
responses where `ParticipantResponse.is_flagged` is true. Both exports include
participant identifiers, passage/question metadata, expected answer, response
text or transcript, media URI, keyword matches/misses, correctness score, flag
reason, and review status.
