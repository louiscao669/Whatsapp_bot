# Backend (Flask API + WhatsApp webhook)

Python service for the ETEN WhatsApp bot: webhook, admin (SSR during migration), services, and DB.

## Run locally

From the **repository root** (`.env` lives here):

```bash
pip install -r backend/requirements.txt
python backend/app.py
```

Or from this directory:

```bash
pip install -r requirements.txt
python app.py
```

Default: http://localhost:7860

- WhatsApp webhook: `/webhook`
- Admin UI (legacy SSR): `/admin/*`

## Layout

```text
backend/
  app.py              # entrypoint
  requirements.txt
  app/
    views.py          # webhook blueprint
    admin_views.py    # admin UI (to migrate to JSON API)
    services/         # business logic
    models.py
    database.py
  scripts/            # CLI utilities
```

Shared repo assets: `supabase/` (schema, migrations, seeds) at repository root.

## Scripts

Run from repository root:

```bash
python backend/scripts/rescore_participant_responses.py --help
python backend/scripts/test_luke_assignment.py --help
```
