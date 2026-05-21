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
