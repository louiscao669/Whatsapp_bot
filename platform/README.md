# Platform (admin API + expert workbench + SPA)

Flask service for the React admin frontend: auth, QA management, review, record, analytics, exports.

## Run locally

From the **repository root** (`.env` lives here):

```bash
pip install -e packages/eten-shared
pip install -r platform/requirements.txt
cd platform/frontend && npm run build
python platform/app.py
```

Default: http://localhost:7860

- Admin JSON API: `/api/v1/*`
- React SPA: `/`
- Participant dashboard: `/user_dashboard/index.html/<participant_id>`
- Human-pilot study: `/pilot/<participant_id>` (see `platform/pilot/README.md`)

## Layout

```text
platform/
  app.py
  requirements.txt
  app/
    api/              # JSON API blueprints
    services/         # admin / expert business logic
    pilot/            # /pilot study routes + service
    spa_views.py      # SPA static files + /admin redirects
    utils/
  pilot/              # /pilot static participant interface
```

Shared assets: `packages/eten-shared/`, `supabase/`, `platform/frontend/dist/`.
