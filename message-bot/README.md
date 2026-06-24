# Messaging bot (WhatsApp provider + participant workflow)

Flask service for participant messaging. The current provider is Meta's
WhatsApp webhook, with shared participant workflow and engagement logic split
away from the provider transport.

## Run locally

From the **repository root**:

```bash
pip install -e packages/eten-shared
pip install -r message-bot/requirements.txt
python message-bot/app.py
```

Default: http://localhost:7861

- WhatsApp webhook: `/webhook`

Requires `ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN`, `APP_SECRET`, and Supabase env vars.

## Layout

```text
message-bot/
  app.py
  requirements.txt
  app/
    messaging/        # provider-neutral participant workflow
    engagement/       # reminders, badges, batch continuation
    providers/
      whatsapp/       # WhatsApp webhook, security, and Graph API transport
    services/         # compatibility wrappers for old imports
    webhook/          # compatibility wrappers for old WhatsApp imports
    decorators/       # compatibility wrappers for old security imports
```

Shared assets: `packages/eten-shared/`, `supabase/`.
