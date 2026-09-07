"""gunicorn configuration for the ETEN platform.

Run as:

    gunicorn --chdir /opt/eten-whatsapp-bot/platform \
             --config /opt/eten-whatsapp-bot/deploy/gunicorn/gunicorn.conf.py \
             wsgi:application

The point of moving off Werkzeug's development server is HTTP/1.1 with
keep-alive. The dev server answers ``HTTP/1.0`` with ``Connection: close``, so
every request from a participant's browser -- page, each API call, each static
asset -- paid a fresh TCP handshake. Submitting one answer costs three
sequential requests (``POST /answers``, ``GET /question``,
``POST /question/viewed``), so that was three handshakes where one connection
would do.
"""

import logging
import os

# --------------------------------------------------------------- networking
# 0.0.0.0 while the app is reached directly. Once nginx terminates TLS in
# front of it, change this to 127.0.0.1 so the app is no longer exposed to the
# internet on its own port -- that is the whole security benefit of a proxy,
# and it is lost if this stays open.
bind = os.getenv("PLATFORM_BIND", f"0.0.0.0:{os.getenv('PLATFORM_PORT', '7860')}")

# Hold an idle connection open long enough to cover a participant reading and
# answering the next question without reconnecting, but not so long that the
# scanners already probing this host can pin workers open.
keepalive = 15

# The slowest legitimate request is a first page load that mints an assignment
# against a remote Supabase. 60s is far above that and still bounds a hang.
timeout = 60
graceful_timeout = 30

# ------------------------------------------------------------------ workers
# Deliberately small. Each worker PROCESS holds its own SQLAlchemy connection
# pool to Supabase (pool_size 5 + overflow), so worker count multiplies
# database connections, and Supabase's ceiling is the real constraint here --
# not CPU. This study serves tens of participants, not thousands. Threads
# absorb concurrency instead: the work is almost entirely waiting on the
# database, not computing.
workers = int(os.getenv("PLATFORM_WORKERS", "2"))
worker_class = "gthread"
threads = int(os.getenv("PLATFORM_THREADS", "4"))

# Import the application once in the master, then fork. Combined with the
# hooks below this means the startup migrations run ONCE rather than once per
# worker -- see on_starting.
preload_app = True

# ------------------------------------------------------------------ logging
# gunicorn's access log is off by default; turn it on so the request history
# that journald has always carried does not disappear with this change. %(D)s
# is the request duration in microseconds, which is what made the keep-alive
# problem visible in the first place.
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("PLATFORM_LOG_LEVEL", "info")
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sus'


def _install_redaction():
    """Apply the log redaction filter to gunicorn's own loggers.

    ``install_log_redaction`` in the app covers the root handlers, which is
    where Flask and Werkzeug log. gunicorn's ``gunicorn.access`` and
    ``gunicorn.error`` loggers carry their own handlers and do not propagate,
    so without this the access log would reintroduce exactly what was removed:
    a client IP next to a path containing a participant id.
    """

    try:
        from eten_shared.log_redaction import install_log_redaction
    except Exception:  # pragma: no cover - never block startup on logging
        return
    for name in ("gunicorn.access", "gunicorn.error"):
        install_log_redaction(logging.getLogger(name))


def on_starting(server):
    """Warm the database engine in the master, before any worker exists.

    ``eten_shared.database.get_engine`` runs ~60 idempotent DDL statements plus
    a couple of full-table updates the first time it is called in a process.
    Left to the workers, every worker would run that on its first request, all
    at once, taking DDL locks on the same tables -- a needless way to make the
    first page load after a restart slow or, worse, deadlocked. Doing it here
    means it happens once, before the socket accepts anything.

    A failure is logged and swallowed: the workers will retry lazily, and a
    database that is briefly unreachable at boot should not stop the service
    from coming up.
    """

    _install_redaction()
    try:
        from dotenv import load_dotenv
        from eten_shared.repo_paths import REPO_ROOT

        load_dotenv(REPO_ROOT / ".env")
        from eten_shared.database import get_engine

        get_engine()
        server.log.info("database engine warmed in master; migrations applied once")
    except Exception as error:  # pragma: no cover - startup resilience
        server.log.warning("engine warm-up skipped (%s); workers will retry", error)


def post_fork(server, worker):
    """Give each worker its own connections.

    A pooled socket inherited across fork would be used concurrently by parent
    and child, which corrupts the protocol stream in ways that surface as
    baffling intermittent database errors. ``dispose()`` drops the inherited
    pool; SQLAlchemy reconnects lazily, per worker.
    """

    _install_redaction()
    try:
        from eten_shared.database import get_engine

        get_engine().dispose()
    except Exception as error:  # pragma: no cover - startup resilience
        worker.log.warning("post-fork engine dispose skipped (%s)", error)
