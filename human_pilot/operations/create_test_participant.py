#!/usr/bin/env python3
"""Create a flagged test participant (and its pilot plan) without the admin UI.

    python human_pilot/operations/create_test_participant.py --name why_test
    python human_pilot/operations/create_test_participant.py --name why_test --qa-set hard66
    python human_pilot/operations/create_test_participant.py --name probe --no-plan
    python human_pilot/operations/create_test_participant.py --name why_only --qa-set hard66 --wh-types why

Same code path as POST /api/v1/participants/test -- it calls the identical service
function and commits the same way. It exists because that route sits behind
``@require_roles("admin")`` and the admin auth provider is email-OTP (Supabase or SMTP),
with no static token to script against; going through a browser login just to create a
throwaway account is friction, and hand-writing INSERTs would miss what the service does.

What the service does that a manual INSERT would not:
  * flags the row with TEST_PARTICIPANT_KEY in dashboard_preferences, which keeps the
    account out of the real Latin-square block order and out of the pilot exports, and
    is what makes the admin delete willing to remove it later;
  * picks block_index via next_test_block_index so test accounts do not collide;
  * writes the plan cells for the chosen question set;
  * leaves consented=False on purpose -- the /pilot/<id> link walks the tester through
    consent, and pre-consenting would skip the flow you are testing.

Requires DATABASE_URL (set -a; source .env; set +a).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "platform"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", help="display name (a TEST prefix is added by the service)")
    ap.add_argument("--language", default=None, help="target language (default: pilot default)")
    ap.add_argument("--qa-set", default=None, help="gold72 (default) or hard66")
    ap.add_argument("--wh-types", default=None,
                    help="restrict to these question stems, e.g. 'why' or 'why,how' "
                         "(cells with none are skipped)")
    ap.add_argument("--no-plan", action="store_true",
                    help="create the participant without writing plan cells")
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    a = ap.parse_args()

    from eten_shared.database import get_session_factory
    from backend.admin.services.test_participants_service import (
        TestParticipantError, create_test_participant,
    )

    try:
        factory = get_session_factory(a.database_url)
    except RuntimeError as exc:
        print(f"{exc}\n  set -a; source .env; set +a   (or pass --database-url)",
              file=sys.stderr)
        return 2

    with factory() as db:
        try:
            payload = create_test_participant(
                db,
                display_name=a.name,
                language=a.language,
                build_plan=not a.no_plan,
                qa_set=a.qa_set,
                wh_types=a.wh_types,
            )
            db.commit()
        except TestParticipantError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1

    print(json.dumps({k: v for k, v in payload.items() if k != "plan"}, indent=2))
    print(f"\n  participant_id : {payload['participant_id']}")
    if payload.get("pilot_path"):
        print(f"  open           : <your-host>{payload['pilot_path']}")
        print("                   (host = DASHBOARD_PUBLIC_BASE_URL on the serving VM)")
    print(f"  plan cells     : {len(payload.get('plan') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
