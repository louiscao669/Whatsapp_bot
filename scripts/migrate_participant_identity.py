#!/usr/bin/env python3
"""One-time conversion of existing contacts to keyed identifiers.

Existing rows hold a readable chat id in ``external_user_id`` and, for some,
names and usernames. This rewrites each row to the protected scheme:

    external_user_id      -> HMAC blind index of the current plaintext value
    external_user_secret  -> AES-GCM sealed copy of that value
    display_name / username / first_name / last_name / phone -> NULL

Run AFTER applying supabase/migrations/participant_identity_protection.sql and
with PARTICIPANT_ID_KEY set. Until it runs, existing participants cannot be
messaged, because the send path now expects a sealed value.

    python scripts/migrate_participant_identity.py            # report only
    python scripts/migrate_participant_identity.py --export contacts.json
    python scripts/migrate_participant_identity.py --apply

--export writes the code->identity mapping to a file BEFORE scrubbing. That
file is the only remaining link for compensation and re-contact; it belongs in
encrypted researcher-held storage, never in the repository or the database, and
is destroyed with the key at the end of collection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "eten-shared"))

from sqlalchemy import select

from eten_shared.database import get_session_factory
from eten_shared.models import Participant, ParticipantProviderContact
from eten_shared.participant_identity import (
    IdentityKeyError,
    blind_index,
    key_fingerprint,
    seal,
)

HEX64 = 64


def looks_converted(contact) -> bool:
    """A converted row has a 64-hex index and a sealed secret."""

    value = contact.external_user_id or ""
    return (
        len(value) == HEX64
        and all(c in "0123456789abcdef" for c in value.lower())
        and bool(contact.external_user_secret)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    ap.add_argument("--export", type=Path, help="write the identity mapping here before scrubbing")
    args = ap.parse_args()

    try:
        fingerprint = key_fingerprint()
    except IdentityKeyError as exc:
        return int(bool(sys.stderr.write(f"{exc}\n"))) or 1

    print(f"identity key fingerprint: {fingerprint}")
    exported = []
    converted = skipped = scrubbed = 0

    with get_session_factory()() as db:
        contacts = list(db.scalars(select(ParticipantProviderContact)))
        for contact in contacts:
            if looks_converted(contact):
                skipped += 1
                continue
            plaintext = contact.external_user_id
            exported.append({
                "participant_id": contact.participant_id,
                "provider": contact.provider,
                "external_user_id": plaintext,
                "display_name": contact.display_name,
                "username": contact.username,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "phone": contact.phone,
            })
            if args.apply:
                contact.external_user_secret = seal(plaintext)
                contact.external_user_id = blind_index(contact.provider, plaintext)
                contact.identity_key_fingerprint = fingerprint
                contact.display_name = None
                contact.username = None
                contact.first_name = None
                contact.last_name = None
                contact.phone = None
            converted += 1

        participants = list(db.scalars(select(Participant).where(Participant.display_name.isnot(None))))
        for participant in participants:
            scrubbed += 1
            if args.apply:
                participant.display_name = None

        if args.export:
            args.export.write_text(json.dumps(exported, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"exported {len(exported)} identity record(s) -> {args.export}")
            print("  KEEP THIS OUT OF THE REPO AND THE DATABASE.")

        if args.apply:
            if args.export is None and exported:
                print("refusing to scrub without --export: the code->person link "
                      "would be unrecoverable and you said you need it for "
                      "compensation and re-contact.", file=sys.stderr)
                db.rollback()
                return 2
            db.commit()
            print(f"converted {converted} contact(s), scrubbed {scrubbed} participant name(s)")
        else:
            print(f"would convert {converted} contact(s) "
                  f"({skipped} already converted), scrub {scrubbed} participant name(s)")
            print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
