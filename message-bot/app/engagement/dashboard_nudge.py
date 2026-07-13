"""Route batch-ready notifications and reminders to the participant's
nudged surface (dashboard vs messenger).

Platform-engagement experiment (see
`EXPERIMENT_PLATFORM_ENGAGEMENT_2026-07-12.md`, ops items 5 & 6). Each
participant carries a `nudge_platform_sequence`; `nudge_platform_for_next_batch`
resolves which surface the current/next batch should be nudged toward. For
dashboard-nudged batches we send a messenger message containing a signed
dashboard deep link instead of delivering the question in chat. Everyone
without a sequence (the default) keeps the current messenger behaviour.

If a deep link cannot be built (no shared secret configured), we fall back
to messenger delivery rather than sending a link-less nudge — this keeps the
feature safe to enable incrementally.
"""

import logging
from typing import Optional

from eten_shared.dashboard_links import DashboardLinkError, build_dashboard_link
from eten_shared.database import get_session_factory
from eten_shared.domain.identity import (
    PROVIDER_WHATSAPP,
    get_or_create_participant_by_contact,
)
from eten_shared.domain.platform_nudges import (
    PLATFORM_DASHBOARD,
    nudge_platform_for_next_batch,
)


def is_dashboard_nudged(db, participant) -> bool:
    """Whether the participant's current/next batch should point at the
    dashboard rather than the messenger surface."""

    return nudge_platform_for_next_batch(db, participant) == PLATFORM_DASHBOARD


def dashboard_deep_link(participant) -> Optional[str]:
    """Signed dashboard deep link for the participant, or None if links are
    not configured (missing shared secret)."""

    try:
        return build_dashboard_link(participant.id)
    except DashboardLinkError as exc:
        logging.warning("Dashboard deep link unavailable: %s", exc)
        return None


def batch_ready_message(link: str) -> str:
    return (
        "Your next set of questions is ready. "
        f"Open your dashboard to answer them: {link}"
    )


def question_reminder_message(link: str) -> str:
    return (
        "You still have a question waiting. "
        f"Answer it on your dashboard: {link}"
    )


# --- On-demand dashboard link ("/dashboard" command) ----------------------

DASHBOARD_COMMAND_ALIASES = {
    "dashboard",
    "my dashboard",
    "dashboard link",
    "open dashboard",
    "my link",
}


def is_dashboard_command(text) -> bool:
    """True when an inbound message is a request for the dashboard link
    (e.g. "/dashboard", "dashboard", "my dashboard")."""

    if not text:
        return False
    return text.strip().lower().lstrip("/") in DASHBOARD_COMMAND_ALIASES


def dashboard_link_reply(participant) -> str:
    """Reply text handing the participant their signed dashboard deep link."""

    link = dashboard_deep_link(participant)
    if link:
        return "Here's your dashboard link — tap to open it:\n" + link
    return (
        "Sorry, your dashboard link isn't available right now. "
        "Please let the study team know."
    )


def dashboard_link_reply_for_contact(
    provider: str, external_user_id, display_name: Optional[str] = None
) -> str:
    """Resolve the participant for a provider identity and return the dashboard
    link reply. Used by surfaces (WhatsApp) that hold an external id rather than
    a participant object."""

    extra = {"phone": external_user_id} if provider == PROVIDER_WHATSAPP else {}
    with get_session_factory()() as db:
        participant, _contact, _created = get_or_create_participant_by_contact(
            db, provider, external_user_id, display_name=display_name, **extra
        )
        reply = dashboard_link_reply(participant)
        db.commit()
        return reply


def resolve_dashboard_nudge(db, participant) -> Optional[str]:
    """Return a dashboard deep link when the participant should be nudged to
    the dashboard for their current/next batch, else None (deliver in chat)."""

    if not is_dashboard_nudged(db, participant):
        return None
    return dashboard_deep_link(participant)
