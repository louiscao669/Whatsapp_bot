#!/usr/bin/env python3
"""Explain why a participant is (not) getting new questions.

Mirrors question_discovery.select_next_qa_item and reports how many QA items
survive each eligibility filter, so you can see which one is emptying the pool.

To be assignable, an item must be: active, not review-removed, not already
assigned to this participant, and have an expert 'question' recording whose
language matches the participant's target_language. Being 'reviewed' is NOT a
selection criterion.

Usage (from repo root):
  python scripts/diagnose_assignment.py --participant-id <uuid>
  python scripts/diagnose_assignment.py --identifier 15551234567     # phone or chat id
  python scripts/diagnose_assignment.py --identifier 987654321 --provider telegram
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _bootstrap import use_message_bot

use_message_bot()

from app.config import load_configurations  # loads .env  # noqa: E402
from flask import Flask  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from eten_shared.database import get_session_factory  # noqa: E402
from eten_shared.models import Assignment, QAItem, QAItemRecording, Participant  # noqa: E402
from eten_shared.domain.identity import resolve_login  # noqa: E402
from eten_shared.recordings import (  # noqa: E402
    participant_language_code,
    participant_question_audio_satisfied,
    question_audio_required,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant-id")
    parser.add_argument("--identifier", help="WhatsApp phone or Telegram chat id")
    parser.add_argument("--provider", help="whatsapp | telegram | imessage")
    args = parser.parse_args()

    load_configurations(Flask(__name__))
    with get_session_factory()() as db:
        if args.participant_id:
            participant = db.get(Participant, args.participant_id)
        elif args.identifier:
            participant = resolve_login(db, args.identifier, args.provider)
        else:
            parser.error("Provide --participant-id or --identifier")
        if participant is None:
            print("Participant not found.")
            return

        lang = participant_language_code(participant)
        print(f"participant_id : {participant.id}")
        print(f"display_name   : {participant.display_name}")
        print(f"target_language: {participant.target_language!r} -> selection uses {lang!r}")
        print("-" * 64)

        all_items = db.scalars(select(QAItem)).all()
        active = [q for q in all_items if q.active and q.review_removed_at is None]
        reviewed = [q for q in all_items if q.qa_reviewed_at is not None]
        assigned_ids = set(
            db.scalars(
                select(Assignment.qa_item_id).where(
                    Assignment.participant_id == participant.id
                )
            ).all()
        )

        not_assigned = [q for q in active if q.id not in assigned_ids]
        assignable = [
            q for q in not_assigned
            if participant_question_audio_satisfied(db, q.id, participant)
        ]
        audio_required = question_audio_required()
        print(f"REQUIRE_QUESTION_AUDIO -> audio required for assignment: {audio_required}")

        print(f"QA items total            : {len(all_items)}")
        print(f"  reviewed (qa_reviewed_at): {len(reviewed)}   (note: NOT a selection filter)")
        print(f"  active & not removed     : {len(active)}")
        print(f"  ...and not yet assigned  : {len(not_assigned)}")
        print(f"  ...with {lang!r} question audio (ASSIGNABLE): {len(assignable)}")
        print("-" * 64)

        # Why are active, unassigned items still not assignable?
        blocked = [q for q in not_assigned if q not in assignable]
        if blocked:
            print(f"{len(blocked)} active/unassigned item(s) blocked by MISSING {lang!r} question audio.")

        # What recording languages DO exist (question type)? Surfaces mismatches.
        rec_langs = db.execute(
            select(func.lower(QAItemRecording.language), func.count())
            .where(QAItemRecording.recording_type == "question")
            .group_by(func.lower(QAItemRecording.language))
        ).all()
        print("\nquestion-audio languages present in DB (lang -> #recordings):")
        if rec_langs:
            for l, n in sorted(rec_langs, key=lambda r: -r[1]):
                marker = "  <-- matches participant" if (l or "") == lang else ""
                print(f"  {l!r}: {n}{marker}")
        else:
            print("  (none — no question recordings exist at all)")

        print("-" * 64)
        if assignable:
            print(f"VERDICT: {len(assignable)} question(s) are assignable; the bot should serve them.")
        elif not active:
            print("VERDICT: no active/non-removed QA items — check the items are active.")
        elif not not_assigned:
            print("VERDICT: this participant has already been assigned every active item.")
        else:
            print(
                f"VERDICT: items exist but none have {lang!r} question audio. "
                "Record question audio for this language (expert /record), or fix the "
                "language-code mismatch shown above."
            )


if __name__ == "__main__":
    main()
