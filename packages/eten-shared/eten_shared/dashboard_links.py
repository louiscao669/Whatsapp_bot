"""Signed dashboard deep links.

Nudge messages sent over messengers include an authenticated link that lands
the participant on their own dashboard page without typing a participant id.
Tokens are signed (HMAC via itsdangerous, which ships with Flask) with a
shared secret so both the message-bot (generates) and the platform (verifies)
can use them.

Env:
- DASHBOARD_LINK_SECRET (falls back to SECRET_KEY) - required, shared by
  the platform and message-bot processes.
- DASHBOARD_PUBLIC_BASE_URL - public base URL of the platform service,
  e.g. https://example.org (no trailing slash needed).
- DASHBOARD_LINK_MAX_AGE_SECONDS - token validity window
  (default 30 days; these are convenience links, not a security boundary
  beyond knowing the participant id).
"""

import os
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_SALT = "user-dashboard-deep-link"

DEFAULT_MAX_AGE_SECONDS = 30 * 24 * 3600


class DashboardLinkError(Exception):
    pass


def _secret() -> str:
    secret = os.getenv("DASHBOARD_LINK_SECRET") or os.getenv("SECRET_KEY")
    if not secret:
        raise DashboardLinkError(
            "Set DASHBOARD_LINK_SECRET (or SECRET_KEY) to use dashboard deep links"
        )
    return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret(), salt=_SALT)


def generate_dashboard_token(participant_id: str) -> str:
    return _serializer().dumps({"participant_id": participant_id})


def verify_dashboard_token(token: str, max_age: Optional[int] = None) -> str:
    """Return the participant_id for a valid token; raise DashboardLinkError
    otherwise. Accepts legacy ``wa_id`` payloads for older links."""

    if max_age is None:
        max_age = int(
            os.getenv("DASHBOARD_LINK_MAX_AGE_SECONDS", str(DEFAULT_MAX_AGE_SECONDS))
        )
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise DashboardLinkError("Dashboard link has expired") from exc
    except BadSignature as exc:
        raise DashboardLinkError("Invalid dashboard link") from exc
    payload = payload or {}
    participant_id = payload.get("participant_id") or payload.get("wa_id")
    if not participant_id:
        raise DashboardLinkError("Invalid dashboard link payload")
    return participant_id


def dashboard_public_base_url() -> str:
    return (os.getenv("DASHBOARD_PUBLIC_BASE_URL") or "http://127.0.0.1:7860").rstrip("/")


def build_dashboard_link(participant_id: str) -> str:
    token = generate_dashboard_token(participant_id)
    return f"{dashboard_public_base_url()}/user_dashboard/t/{token}"
