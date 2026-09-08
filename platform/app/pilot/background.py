"""Work that must not sit on a participant's critical path.

The pilot's latency is round-trip bound: the database is ~22ms away (Supabase
in AWS us-east-2, app in GCP us-east5 -- cross-cloud, measured 2026-09-07), and
``GET /question`` issued ~40 of them because it minted the next assignment
while the participant waited. Measured: 1123ms when it mints, 397ms when an
assignment is already there.

The fix is not fewer queries but better timing. A participant spends tens of
seconds reading a passage; the server spends that time idle. Jobs submitted
here run in that window instead.

Rules this module enforces, because getting them wrong is subtle:

* **Its own session.** SQLAlchemy sessions are not thread-safe, and one that
  outlives its request produces intermittent, unreproducible failures. Each
  job opens a session, commits, and closes it.
* **Never raises into the caller.** A background job is by definition not what
  the participant is waiting for; a failure is logged and the request is
  unaffected. Everything scheduled here is re-derivable, so losing one costs
  nothing that the next request cannot redo.
* **De-duplicated by key.** Two overlapping pre-mints for one participant would
  race; the key drops the second while the first is in flight. This is an
  optimization, not the safety net -- correctness comes from the per-participant
  advisory lock inside the mint itself, which also covers the background-vs-
  inline race that no in-process set can see.
"""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from eten_shared.database import get_session_factory

logger = logging.getLogger(__name__)

#: Small on purpose. These jobs are database-round-trip bound, they are never
#: what a participant waits on, and each one holds a connection from the
#: worker's pool while it runs.
_MAX_WORKERS = int(os.getenv("PILOT_BACKGROUND_WORKERS", "2"))

_executor = None
_executor_lock = threading.Lock()
_inflight = set()
_inflight_lock = threading.Lock()


def _get_executor():
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=_MAX_WORKERS, thread_name_prefix="pilot-bg"
                )
    return _executor


def _run(job, key, args, kwargs):
    try:
        with get_session_factory()() as db:
            job(db, *args, **kwargs)
            db.commit()
    except Exception:
        # Deliberately broad: a background failure must never escape into a
        # worker thread's traceback, and every job here is re-derivable on the
        # next request.
        logger.exception(
            "pilot background job %r failed", getattr(job, "__name__", job)
        )
    finally:
        if key is not None:
            with _inflight_lock:
                _inflight.discard(key)


def run_in_background(job, *args, key=None, **kwargs):
    """Schedule ``job(db, *args, **kwargs)`` on a thread with its own session.

    Returns True when the job was scheduled, False when an identical one (same
    ``key``) is already in flight. Callers do not wait on the result and must
    not depend on it having run.
    """

    if key is not None:
        with _inflight_lock:
            if key in _inflight:
                return False
            _inflight.add(key)
    try:
        _get_executor().submit(_run, job, key, args, kwargs)
    except RuntimeError:
        # Interpreter or pool shutting down (worker restart). Run it inline
        # rather than drop it; the request has already been answered, so the
        # only cost is this thread finishing a little later.
        _run(job, key, args, kwargs)
    return True
