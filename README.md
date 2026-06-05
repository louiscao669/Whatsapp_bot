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
SUPABASE_AUDIO_BUCKET=participant-audio
```

Create a **private** Supabase Storage bucket named `participant-audio`, or set
`SUPABASE_AUDIO_BUCKET` to another bucket name. Audio answers are uploaded to
Supabase Storage and saved on `ParticipantResponse.media_url` as a storage URI,
for example `storage://participant-audio/whatsapp/2026/05/22/MEDIA_ID.ogg`.
The admin UI streams audio through authenticated `/admin/media/*` routes (not
public or signed Supabase URLs in HTML).

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
   from Meta, upload the audio file to Supabase Storage, and save its storage URI
   on `ParticipantResponse.media_url`.
6. If the session has a `current_assignment_id`, save a `ParticipantResponse`.
   Text answers and audio answers (Whisper STT when configured) are scored with
   **keyword matching** against the per-language rubric on
   [`/admin/record`](http://localhost:7860/admin/record). `correctness_score` is
   the fraction of required keywords matched; `matched_keywords` and
   `missing_keywords` are stored on each response. Placeholder or missing
   transcripts on audio answers are flagged for expert review without auto-pass.
7. Complete the assignment and return the session to `idle`.
8. When the session is idle, first check the current batch. If the number of
   completed assignments in `ParticipantSession.current_batch_id` has reached
   `Participant.preferred_batch_size`, clear the current batch, record a
   `batch_completed` event, and send a batch-complete message instead of another
   question on that turn.
9. After the batch-complete message, a `batch_next_assignment` reminder schedules
   the next batch. `BATCH_NEXT_ASSIGN_DELAY_MINUTES` defaults to `0` (due on the
   next reminder scheduler poll, typically within a few minutes). Larger values wait
   that many minutes (max 23h 59m, within the WhatsApp 24-hour service window). If
   the participant messages again before delivery, the scheduled handoff is cancelled
   and the normal inbound assignment flow runs on that message instead.
10. If the batch is still open, select the next eligible active `QAItem`, create
   an `Assignment`, update the session to `awaiting_response`, and send the
   audio passage plus question text over WhatsApp. A question is eligible only if
   experts have recorded its **question** audio at `/admin/record` for the
   participant's target language. Selection skips QA items already assigned to
   the participant and prioritizes: response gap
   (`min_responses_required - actual_response_count`), accuracy risk from low
   correctness/high flag rate, `review_priority`, and then lower coverage.

## Expert rubric and scoring (`/admin/record`)

After a QA pair is marked **reviewed** on Review QA, it appears on Record. For each
target language, experts record the **question** audio (the passage prompt
participants hear when answering). Keyword rubrics for scoring come from the UW import
and optional per-language overrides in `qa_item_language_keywords`.

Re-score stored responses locally:

```bash
python scripts/rescore_participant_responses.py --commit RESPONSE_ID
python scripts/rescore_participant_responses.py --retranscribe --commit RESPONSE_ID
```

## Keyword matching (fuzzy)

Text/transcript scoring uses [`app/services/keyword_matching_service.py`](app/services/keyword_matching_service.py) and [`app/services/qa_keywords_service.py`](app/services/qa_keywords_service.py).

**Important for lower-resource languages:** RapidFuzz compares **characters**, not meaning.
It does not know that two words are synonyms in Hausa, Swahili, etc. It helps with:

- Typos and spelling variants (any script Unicode supports)
- Short keywords appearing inside longer tokens (`partial_ratio`)
- Exact phrases after Unicode normalization

It does **not** replace a dictionary or stemmer for that language. For acceptable
variants in the target language, list them in import JSON:

```json
"required_keywords": {
  "ɗan": ["dan", "ɗan"],
  "gida": ["gidaje", "gidan"]
}
```

(same shape as UW import: keyword text → list of accepted synonyms)

For **English-only** dev/testing you can enable suffix stemming (`watch` ↔ `watching`):

```text
KEYWORD_USE_ENGLISH_STEMMING=true
KEYWORD_FUZZY_MATCH_THRESHOLD=85
```

Default: stemming **off** (multilingual-safe). Lower threshold = stricter, higher = more lenient.

Speech-to-text for voice answers ([`app/services/transcription_service.py`](app/services/transcription_service.py)):

```text
TRANSCRIPTION_ENABLED=true
OPENAI_API_KEY=...
WHISPER_MODEL=whisper-1
```

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

## Admin and expert dashboards

The app exposes token-protected HTML endpoints for the two internal user groups:

```text
/admin/qa-items      -> admin/distributor only
/admin/review        -> Review Response (admin or expert)
/admin/review-qa     -> Review QA (admin or expert)
/admin/analytics     -> admin/distributor or expert reviewer
/admin/participants  -> admin/distributor only
```

Configure strong tokens in the deployed Space:

```text
ADMIN_API_TOKEN=replace-with-a-long-random-admin-token
EXPERT_API_TOKEN=replace-with-a-long-random-expert-token
FLASK_SECRET_KEY=replace-with-a-long-random-session-secret
SUPABASE_ANON_KEY=your-supabase-anon-key
ADMIN_AUTH_PROVIDER=supabase
```

For browser access, open `/admin/login`, enter your approved email, then enter
the one-time code. By default, the app asks Supabase Auth to send and verify the
code. After verification, it checks the email against the `admin_users`
allowlist table and stores the allowed role in a signed Flask session cookie.
Use `/admin/logout` to clear the session. Set `FLASK_SECRET_KEY` in deployment
for stable signed sessions; if omitted, the app falls back to `APP_SECRET`.

The allowlist table is `admin_users`:

```text
email text unique
role text -- admin or expert
active boolean
```

Add admin/distributor emails with `role = 'admin'` and expert reviewer emails
with `role = 'expert'`. Set `active = false` to revoke access. Bearer tokens
still work for curl/Postman and emergency access. The participants view includes
WhatsApp IDs and should stay admin-only.

Example allowlist inserts:

```sql
insert into admin_users (email, role, active, display_name)
values
  ('admin@example.org', 'admin', true, 'Project Admin'),
  ('expert@example.org', 'expert', true, 'Expert Reviewer');
```

### SMTP login provider for development

Supabase Auth can rate-limit OTP emails during development. To bypass
`/auth/v1/otp`, switch the admin login code provider to SMTP:

```text
ADMIN_AUTH_PROVIDER=smtp
ADMIN_OTP_SECRET=replace-with-a-long-random-otp-secret
ADMIN_OTP_EXPIRY_MINUTES=10
ADMIN_OTP_CODE_LENGTH=6
ADMIN_OTP_MAX_ATTEMPTS=5
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@example.org
SMTP_FROM_NAME=WhatsApp QA Bot
SMTP_USE_TLS=true
```

With SMTP mode, the app generates a one-time code, stores only a hash in
`admin_login_codes`, sends the code using SMTP, and verifies the entered code
locally before checking the same `admin_users` allowlist table.

## Admin CSV exports

The app also exposes token-protected CSV exports for expert review and offline
analysis:

```text
GET /admin/export/responses.csv
GET /admin/export/flagged.csv
```

Call the endpoints with the admin bearer token:

```bash
curl -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  https://YOUR-SPACE.hf.space/admin/export/flagged.csv
```

`responses.csv` exports all participant responses. `flagged.csv` exports only
responses where `ParticipantResponse.is_correct` is `pending`. Both exports include
participant identifiers, passage/question metadata (`question_type` is `open`,
`mcq`, or `tf`), expected answer, response text or transcript, media URI, keyword
matches/misses, correctness score, flag reason, and review status.

Question types: **open** (keyword scoring), **mcq** (four labeled choices in UW
`content`, correct letter `A`–`D`), **tf** (two choices `A`/`B`). UW `content`
format:

`<question>Stem\n\nA. …\nB. …\nC. …\nD. …<question><answer>B<answer>`

Participants receive a WhatsApp list to tap a letter; text replies `A`–`D` also work.

## Security: recordings and participant identifiers

Participant voice recordings and WhatsApp IDs (`wa_id`) are sensitive. The app
enforces access in layers:

### Supabase Storage checklist (verify before production)

In the Supabase dashboard → Storage:

1. Bucket `participant-audio` (or your `SUPABASE_AUDIO_BUCKET` value) is **not**
   public.
2. No storage policy grants `anon` or unauthenticated `SELECT` on objects.
3. `SUPABASE_RECORDINGS_BUCKET`, if set separately, is also private.
4. Smoke test: an unauthenticated HTTP `GET` to a known object path under
   `/storage/v1/object/...` returns **403** or **404**, not audio bytes.
5. `SUPABASE_SERVICE_ROLE_KEY` is set only in server secrets (Space/host env),
   never committed to git or exposed to browsers.

### Admin access matrix

| Resource | Admin | Expert |
|----------|-------|--------|
| Participant voice (flagged review queue) | Yes | Yes (proxy + audit log) |
| Participant voice (non-flagged) | Yes | No |
| QA prompt recordings (question/answer) | Yes | Yes |
| WhatsApp IDs / Participants page | Yes | No |
| CSV exports, bulk audio ZIP | Yes | No |

Experts hear participant audio only for responses in the expert review queue
(`is_correct` is `pending` or `no (expert)`). Admins can play any stored
response when logged in.

### Authenticated media proxy

Browser playback uses session- or token-protected app routes:

```text
GET /admin/media/participant-response/<response_id>
GET /admin/media/qa-recording/<recording_id>
```

Optional `?download=1` for attachment download. Responses use `Cache-Control:
private, no-store`. Access is logged server-side (`admin_media_access`).

### Session and login hardening

```text
FLASK_SECRET_KEY=replace-with-a-long-random-session-secret
SESSION_COOKIE_SECURE=true
ADMIN_SESSION_LIFETIME_HOURS=8
ADMIN_ALLOW_TOKEN_LOGIN=false
```

Set `SESSION_COOKIE_SECURE=false` only for local HTTP development. In
production, use OTP login only (`ADMIN_ALLOW_TOKEN_LOGIN=false`) and rotate
`ADMIN_API_TOKEN` / `EXPERT_API_TOKEN` periodically.

### Production sign-off checklist

Before go-live, confirm:

- [ ] Storage buckets are private (see checklist above).
- [ ] `admin_users` allowlist matches intended admins and experts; revoked users
      have `active = false`.
- [ ] Unauthenticated `GET /admin/review` redirects to login or returns 401.
- [ ] Expert session cannot open `/admin/participants` or `/admin/export/*`.
- [ ] Logged-out request to `/admin/media/participant-response/<id>` returns 401.
- [ ] Expert cannot stream non-flagged participant audio (403).
- [ ] No service role key or `.env` in the repository.
- [ ] CSV/ZIP exports are transferred only over encrypted channels with a
      defined retention policy.
