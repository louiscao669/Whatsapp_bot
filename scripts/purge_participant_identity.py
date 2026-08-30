#!/usr/bin/env python3
"""End-of-collection destruction of participant identifiers.

What the consent form promises: the identifier is "destroyed together with its
key once data collection ends". This performs the database half. The other
half -- deleting PARTICIPANT_ID_KEY from the secret store and destroying the
researcher-held mapping file -- is manual, and is the half that actually makes
the data unrecoverable.

Order matters:

    1. Run this with --apply. Sealed identifiers and blind indexes are cleared.
    2. Delete PARTICIPANT_ID_KEY from the environment and secret manager.
    3. Destroy the exported mapping file from migrate_participant_identity.py.
    4. Record the date and who performed it in the study file.

After step 2 nothing can be reversed even if a backup of this database is
restored, because the ciphertext is meaningless without the key. That is the
property the promise rests on -- which also means a database backup taken
BEFORE the purge, with the key still live, defeats it. Check your Supabase
point-in-time-recovery window before telling anyone the data is destroyed.

    python scripts/purge_participant_identity.py           # report
    python scripts/purge_participant_identity.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "eten-shared"))

from sqlalchemy import select

from eten_shared.database import get_session_factory
from eten_shared.models import Participant, ParticipantProviderContact


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true",
                    help="skip the confirmation prompt (for scripted teardown)")
    args = ap.parse_args()

    with get_session_factory()() as db:
        contacts = list(db.scalars(select(ParticipantProviderContact)))
        named = list(db.scalars(select(Participant).where(Participant.display_name.isnot(None))))
        sealed = [c for c in contacts if c.external_user_secret]

        print(f"contacts total            : {len(contacts)}")
        print(f"  with sealed identifier  : {len(sealed)}")
        print(f"participants with a name  : {len(named)}")

        if not args.apply:
            print("\ndry run: nothing written")
            return 0

        if not args.yes:
            print("\nThis permanently destroys the ability to contact every participant.")
            if input("Type PURGE to continue: ").strip() != "PURGE":
                print("aborted")
                return 1

        for contact in contacts:
            contact.external_user_secret = None
            contact.external_user_id = f"purged:{contact.id}"
            contact.identity_key_fingerprint = None
            contact.display_name = None
            contact.username = None
            contact.first_name = None
            contact.last_name = None
            contact.phone = None
        for participant in named:
            participant.display_name = None
        db.commit()

    print(f"\npurged {len(contacts)} contact(s).")
    print("NOT YET DONE -- the database half only. Now:")
    print("  1. delete PARTICIPANT_ID_KEY from the secret manager and every .env")
    print("  2. destroy the exported identity mapping file")
    print("  3. confirm no pre-purge backup or PITR window still holds the old rows")
    print("  4. record the date and operator in the study file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
