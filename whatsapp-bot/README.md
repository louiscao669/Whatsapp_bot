# WhatsApp bot (webhook + participant workflow)

Flask service for Meta's WhatsApp webhook, outbound messaging, assignment loop, and reminders.

## Run locally

From the **repository root**:

```bash
pip install -e packages/eten-shared
pip install -r whatsapp-bot/requirements.txt
python whatsapp-bot/app.py
```

Default: http://localhost:7861

- WhatsApp webhook: `/webhook`

Requires `ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN`, `APP_SECRET`, and Supabase env vars.

## Layout

```text
whatsapp-bot/
  app.py
  requirements.txt
  app/
    webhook/          # inbound + outbound WhatsApp
    services/         # workflow, reminders, badges
    decorators/       # webhook signature verification
```

Shared assets: `packages/eten-shared/`, `supabase/`.
