#!/usr/bin/env python3
"""Find a participant's dashboard URL by participant id.

The user dashboard is keyed by ``Participant.id`` (a UUID). Every external
identity (WhatsApp phone, Telegram chat id, ...) is a row in
``participant_provider_contacts``; a person can carry several. This script
lists participants with their provider contacts and prints the dashboard URL
and a signed deep link for each.

Usage (from repo root):
  python scripts/find_dashboard_url.py                 # list recent participants
  python scripts/find_dashboard_url.py --query louis   # filter by name/id/contact
  python scripts/find_dashboard_url.py --provider telegram
  python scripts/find_dashboard_url.py --base-url http://localhost:7860
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_message_bot

use_message_bot()

from app.config import load_configurations  # loads .env  # noqa: E402
from flask import Flask  # noqa: E402
from sqlalchemy import or_, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.models import Participant, ParticipantProviderContact  # noqa: E402
from eten_shared.dashboard_links import (  # noqa: E402
    DashboardLinkError,
    build_dashboard_link,
)


def _deep_link(participant_id, base_url):
    try:
        link = build_dashboard_link(participant_id)
    except DashboardLinkError:
        return None
    if base_url:
        token = link.rsplit("/", 1)[-1]
        return f"{base_url.rstrip('/')}/user_dashboard/t/{token}"
    return link


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", help="substring: display name, participant id, or provider contact id")
    parser.add_argument("--provider", help="filter by provider (telegram | whatsapp | imessage)")
    parser.add_argument("--base-url", default="http://localhost:7860", help="dashboard base URL")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    load_configurations(Flask(__name__))

    session_factory = get_session_factory()
    with session_factory() as db:
        stmt = (
            select(Participant)
            .options(selectinload(Participant.provider_contacts))
            .order_by(Participant.last_seen_at.desc().nullslast())
        )
        if args.query or args.provider:
            stmt = stmt.join(
                ParticipantProviderContact,
                ParticipantProviderContact.participant_id == Participant.id,
                isouter=True,
            )
        if args.query:
            like = f"%{args.query}%"
            stmt = stmt.where(
                or_(
                    Participant.id.ilike(like),
                    Participant.display_name.ilike(like),
                    ParticipantProviderContact.external_user_id.ilike(like),
                    ParticipantProviderContact.username.ilike(like),
                    ParticipantProviderContact.display_name.ilike(like),
                )
            )
        if args.provider:
            stmt = stmt.where(ParticipantProviderContact.provider == args.provider)
        participants = db.scalars(stmt.limit(args.limit)).unique().all()

    if not participants:
        print("No participants matched.")
        return

    for p in participants:
        contacts = list(getattr(p, "provider_contacts", []) or [])
        providers = ", ".join(
            f"{c.provider}:{c.external_user_id}"
            + (f" (@{c.username})" if c.username else "")
            for c in contacts
        ) or "(none)"
        url = f"{args.base_url.rstrip('/')}/user_dashboard/index.html/{p.id}"
        print("-" * 72)
        print(f"display_name  : {p.display_name}")
        print(f"participant_id: {p.id}")
        print(f"contacts      : {providers}")
        print(f"dashboard URL : {url}")
        link = _deep_link(p.id, args.base_url)
        if link:
            print(f"deep link     : {link}")
    print("-" * 72)
    print(
        "Tip: the query form also works:\n  "
        f"{args.base_url.rstrip('/')}/user_dashboard/index.html?participant_id=<id>"
    )


if __name__ == "__main__":
    main()
