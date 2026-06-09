# Platform (admin API + expert workbench + SPA)

Flask service for the React admin frontend: auth, QA management, review, record, analytics, exports.

## Run locally

From the **repository root** (`.env` lives here):

```bash
pip install -e packages/eten-shared
pip install -r platform/requirements.txt
cd frontend && npm run build
python platform/app.py
```

Default: http://localhost:7860

- Admin JSON API: `/api/v1/*`
- React SPA: `/`

## Layout

```text
platform/
  app.py
  requirements.txt
  app/
    api/              # JSON API blueprints
    services/         # admin / expert business logic
    spa_views.py      # SPA static files + /admin redirects
    utils/
```

Shared assets: `packages/eten-shared/`, `supabase/`, `frontend/dist/`.
