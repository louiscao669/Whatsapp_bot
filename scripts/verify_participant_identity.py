#!/usr/bin/env python3
"""Confirm identity protection is intact: nothing readable, everything recoverable."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "eten-shared"))

from sqlalchemy import select

from eten_shared.database import get_session_factory
from eten_shared.models import Participant, ParticipantProviderContact
from eten_shared.participant_identity import blind_index, delivery_address, key_fingerprint

def main() -> int:
    problems = []
    with get_session_factory()() as db:
        contacts = list(db.scalars(select(ParticipantProviderContact)))
        participants = list(db.scalars(select(Participant)))
        print(f"key fingerprint: {key_fingerprint()}")
        print(f"contacts: {len(contacts)}   participants: {len(participants)}\n")

        for c in contacts:
            tag = f"contact {c.id[:8]}"
            idx = c.external_user_id or ""
            if len(idx) != 64 or any(ch not in "0123456789abcdef" for ch in idx.lower()):
                problems.append(f"{tag}: external_user_id is not a 64-hex blind index")
            for field in ("display_name", "username", "first_name", "last_name", "phone"):
                if getattr(c, field, None):
                    problems.append(f"{tag}: {field} still populated")
            try:
                recovered = delivery_address(c)
            except Exception as exc:
                problems.append(f"{tag}: cannot recover address -- {exc}")
                continue
            if blind_index(c.provider, recovered) != idx:
                problems.append(f"{tag}: index does not match its own sealed value")
            else:
                print(f"  {tag}: sealed id recovers and matches its index "
                      f"(…{recovered[-4:]}, {c.provider})")

        for p in participants:
            if p.display_name:
                problems.append(f"participant {p.id[:8]}: display_name still populated")

    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  -", p)
        return 1
    print("OK: no readable identifiers stored, every contact recovers via the key.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
