# Running the platform under gunicorn

Replaces Werkzeug's development server. Nothing in the application changes:
gunicorn imports the same `create_app()` through `platform/wsgi.py`, the same
blueprints are registered, and every route behaves identically.

## Why

Werkzeug's dev server answers `HTTP/1.0` with `Connection: close`, so a
participant's browser opened a new TCP connection for every request. Submitting
one answer is three sequential requests — `POST /answers`, `GET /question`,
`POST /question/viewed` — so it paid three handshakes. Measured on 2026-09-07:
the server itself answered `/question` in 0.26–0.31s from localhost, which does
not account for the wait participants see; the connection setup does.

gunicorn speaks HTTP/1.1 with keep-alive, so those three requests share one
connection.

It also fixes two things that were true of the dev server and easy to forget:
one request at a time per process, and no bound on how long a stuck request
holds the server.

## Install

```bash
cd /opt/eten-whatsapp-bot
git pull origin main
.venv/bin/pip install -r platform/requirements.txt      # brings in gunicorn

# Look at the current unit before overriding it.
systemctl cat eten-platform

sudo mkdir -p /etc/systemd/system/eten-platform.service.d
sudo cp deploy/gunicorn/override.conf /etc/systemd/system/eten-platform.service.d/
sudo systemctl daemon-reload
sudo systemctl restart eten-platform
```

Check the unit's `EnvironmentFile` and `WorkingDirectory` in `systemctl cat`
before restarting — the drop-in keeps whatever is there and replaces only
`ExecStart`.

## Verify

```bash
systemctl status eten-platform --no-pager        # several gunicorn processes, not one python
curl -sI http://127.0.0.1:7860/pilot/ | head -3  # HTTP/1.1, no "Connection: close"
```

The startup banner about a development server should be gone. The access log
now carries request duration, e.g. `... "GET /pilot/api/... " 200 1234 262000us`.

The real check is in a browser: DevTools → Network, submit an answer, and
confirm the second and third requests reuse the connection instead of showing
"Connecting" time of their own.

## Rolling back

```bash
sudo rm /etc/systemd/system/eten-platform.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart eten-platform
```

The original unit is untouched, so this returns to the dev server exactly as it
was.

## Tuning, and the one thing to be careful about

`workers` and `threads` are env-overridable (`PLATFORM_WORKERS`,
`PLATFORM_THREADS`) and default to 2 × 4. Raise threads before workers:
**each worker process holds its own SQLAlchemy pool to Supabase**, so worker
count multiplies database connections, and Supabase's connection ceiling is the
binding constraint — not CPU. The work is nearly all waiting on the database
anyway.

Two hooks in `gunicorn.conf.py` earn their place:

- `on_starting` warms the engine in the master, so the ~60 idempotent DDL
  statements in `eten_shared.database._run_startup_migrations` run **once**
  before any worker forks, rather than in every worker's first request
  simultaneously.
- `post_fork` disposes the inherited pool, so no TCP socket to Postgres is ever
  shared between two processes.

## Next step: nginx and TLS

gunicorn is still facing the internet directly on :7860 over plain HTTP. Adding
nginx in front gives TLS (removing the browser's "Not secure" warning beside
the consent form), serves `/pilot/static/` without touching Python, and drops
scanner traffic before it reaches the app. That needs a hostname pointed at the
VM — Let's Encrypt will not issue a certificate for a bare IP.

When nginx is added, set `PLATFORM_BIND=127.0.0.1:7860` so the app is no longer
reachable except through the proxy, and give nginx's own `access_log` the same
IP/id treatment as `deploy/journald/` — it will not inherit the application's
redaction.
