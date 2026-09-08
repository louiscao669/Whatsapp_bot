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

## Admin sign-in

Email one-time code, restricted to an explicit list of addresses. Set in `.env`:

```bash
ADMIN_AUTH_PROVIDER=smtp
ADMIN_ALLOWED_EMAILS=lcao4@nd.edu,colleague@nd.edu:expert   # bare address = admin
ADMIN_OTP_SECRET=<long random string>                       # or reuse APP_SECRET

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<the gmail account>
SMTP_PASSWORD=<16-char app password, not the account password>
SMTP_FROM_EMAIL=<the same gmail account>   # Gmail rewrites From to the authenticated user
```

`ADMIN_ALLOWED_EMAILS` is authoritative for **both** membership and role. An
address that is not listed gets no code mailed to it at all — the check happens
in `send_admin_login_otp`, before an OTP is generated, because `/otp/request` is
unauthenticated and reachable from the internet. A listed address with no
`admin_users` row gets one created on first login, so adding a collaborator is a
one-line `.env` edit plus a restart rather than SQL.

Two things the variable does *not* do. Setting `active = false` on an
`admin_users` row still denies access regardless of the list — that is the
revocation path that works without a restart. And leaving
`ADMIN_ALLOWED_EMAILS` unset restores the previous behaviour, where the
`admin_users` table alone decides.

Token login (`ADMIN_API_TOKEN` / `EXPERT_API_TOKEN`) still works as break-glass
access but is no longer shown on the login page; reach the form at
`/login?token=1`. Set `ADMIN_ALLOW_TOKEN_LOGIN=false` to disable it outright —
worth doing once email login is proven, since a static bearer token on a public
plain-HTTP IP is the weakest credential in the system.

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
