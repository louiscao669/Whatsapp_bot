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
```

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
5. If the incoming WhatsApp message is an audio/voice note, pass its media ID
   through the placeholder transcription adapter in
   `app/services/transcription_service.py`. Replace that adapter with the team
   speech-to-text model when it is ready.
6. If the session has a `current_assignment_id`, save a `ParticipantResponse`,
   score the text answer or audio transcript against the QA item's required
   keywords, complete the assignment, and return the session to `idle`.
7. When the session is idle, select the next eligible active `QAItem`, create an
   `Assignment`, update the session to `awaiting_response`, and send the audio
   passage plus question text over WhatsApp. Selection skips QA items already
   assigned to the participant and prioritizes: response gap
   (`min_responses_required - actual_response_count`), accuracy risk from low
   correctness/high flag rate, `review_priority`, and then lower coverage.
