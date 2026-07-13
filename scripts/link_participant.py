#!/usr/bin/env python3
"""Link provider identities to a single participant (researcher provisioning).

Attaches a WhatsApp phone and/or Telegram chat id (and iMessage handle) to one
``participant_id`` so the same person is one participant across surfaces — the
prerequisite for the platform-engagement crossover and for the dashboard login
resolving either identifier to the same dashboard.

Do this at setup, before either identity has activity: it is then a clean
attach. If an identity already belongs to a *different* participant, they are
merged (that participant's data is repointed and the record deleted) — safe
early, messy once both sides have batches/currency, so provision up front.

Usage (from repo root):
  # New participant with both identities
  python scripts/link_participant.py --whatsapp 15551234567 --telegram 987654321 \
      --display-name "Participant 03"

  # Attach a Telegram id to an existing participant
  python scripts/link_participant.py --participant-id <uuid> --telegram 987654321

  # Preview without writing
  python scripts/link_participant.py --whatsapp 15551234567 --telegram 987654321 --dry-run
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
from sqlalchemy import select  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.models import Participant, ParticipantProviderContact  # noqa: E402
from eten_shared.domain.identity import (  # noqa: E402
    PROVIDER_IMESSAGE,
    PROVIDER_TELEGRAM,
    PROVIDER_WHATSAPP,
    link_provider_contact,
    resolve_participant,
)


def _print_participant(db, participant):
    contacts = db.scalars(
        select(ParticipantProviderContact).where(
            ParticipantProviderContact.participant_id == participant.id
        )
    ).all()
    print(f"participant_id: {participant.id}")
    print(f"display_name  : {participant.display_name}")
    for c in contacts:
        print(f"  - {c.provider}: {c.external_user_id}")
    print(f"dashboard URL : /user_dashboard/index.html/{participant.id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--whatsapp", help="WhatsApp phone (digits, with country code)")
    parser.add_argument("--telegram", help="Telegram chat id (numeric)")
    parser.add_argument("--imessage", help="iMessage handle")
    parser.add_argument("--participant-id", help="Attach to this existing participant")
    parser.add_argument("--display-name", help="Display name when creating a new participant")
    parser.add_argument("--dry-run", action="store_true", help="Do not commit")
    args = parser.parse_args()

    provided = [
        (PROVIDER_WHATSAPP, args.whatsapp),
        (PROVIDER_TELEGRAM, args.telegram),
        (PROVIDER_IMESSAGE, args.imessage),
    ]
    provided = [(prov, val.strip()) for prov, val in provided if val and val.strip()]
    if not provided and not args.participant_id:
        parser.error("Provide at least one of --whatsapp / --telegram / --imessage")

    load_configurations(Flask(__name__))
    session_factory = get_session_factory()
    with session_factory() as db:
        base = None
        if args.participant_id:
            base = db.get(Participant, args.participant_id)
            if base is None:
                parser.error(f"No participant with id {args.participant_id!r}")

        if base is None:
            for prov, val in provided:
                existing = resolve_participant(db, prov, val)
                if existing is not None:
                    base = existing
                    print(f"Using existing participant matched by {prov}:{val}")
                    break

        if base is None:
            base = Participant(display_name=args.display_name)
            db.add(base)
            db.flush()
            print("Created new participant")

        for prov, val in provided:
            link_provider_contact(
                db,
                base,
                prov,
                val,
                phone=(val if prov == PROVIDER_WHATSAPP else None),
            )

        db.flush()
        db.refresh(base)
        print("-" * 60)
        _print_participant(db, base)
        print("-" * 60)

        if args.dry_run:
            db.rollback()
            print("dry-run: rolled back, nothing written.")
        else:
            db.commit()
            print("Committed.")


if __name__ == "__main__":
    main()
