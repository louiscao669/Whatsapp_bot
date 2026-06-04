#!/usr/bin/env python3
"""
Seed a UW translation QA item and assign it without sending WhatsApp.

Default entry: Luke 1:2, content_id 174314 from uw-translation-questions-eng-luke.json

Usage (from repo root):
  python scripts/test_luke_assignment.py
  python scripts/test_luke_assignment.py --seed-only
  python scripts/test_luke_assignment.py --content-id 174314
  python scripts/test_luke_assignment.py --json-path "/path/to/uw-translation-questions-eng-luke.json"
  python scripts/test_luke_assignment.py --answer "The eyewitnesses were with the apostles from the beginning of Jesus ministry"

  # Use an existing QA row in Supabase (no UW JSON file):
  python scripts/test_luke_assignment.py --from-db --content-id 174345 --wa-id 15551234567 --name "Test User 3"
  python scripts/test_luke_assignment.py --from-db --passage-id uw-174345 --assign --answer "In Rome"
  python scripts/test_luke_assignment.py --from-db --qa-item-id f787affd-26a9-4b3e-b3fa-46581965a21d --assign
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import select

from app import create_app
from app.database import get_session_factory
from app.models import QAItem, SessionState
from app.services.chatbot_workflow import (
    AssignmentAssignError,
    assign_qa_item_to_participant,
    create_assignment_prompt,
    get_or_create_participant,
    get_or_create_participant_session,
    record_whatsapp_text_message,
)
from app.utils.whatsapp_utils import get_assignment_prompt_text
from scripts.uw_qa_content import find_uw_entry, qa_item_payload_from_uw_entry

DEFAULT_CONTENT_ID = "174314"
DEFAULT_JSON_PATHS = [
    os.path.join(
        ROOT,
        "supabase",
        "seeds",
        "data",
        "uw_luke_1_2_174314.json",
    ),
    os.path.expanduser(
        "~/bible translation/ETEN-Bible-translation-project/v3/combo/uw-translation-questions-eng-luke.json"
    ),
]


def resolve_json_path(explicit_path):
    if explicit_path:
        return explicit_path

    for candidate in DEFAULT_JSON_PATHS:
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        "Could not find UW JSON. Pass --json-path or add "
        "supabase/seeds/data/uw_luke_1_2_174314.json"
    )


def get_test_wa_id(override):
    return (
        override
        or os.getenv("TEST_WA_ID")
        or os.getenv("RECIPIENT_WAID", "").split("#")[0].strip()
        or "15742568706"
    )


def passage_id_from_content_id(content_id):
    return f"uw-{content_id}"


def load_qa_item_from_db(db, qa_item_id=None, passage_id=None):
    if qa_item_id:
        qa_item = db.get(QAItem, qa_item_id)
        if qa_item is None:
            raise ValueError(f"No QA item with id {qa_item_id!r}")
        return qa_item

    if passage_id:
        qa_item = db.scalars(
            select(QAItem)
            .where(QAItem.passage_id == passage_id)
            .order_by(QAItem.created_at.desc())
        ).first()
        if qa_item is None:
            raise ValueError(f"No QA item with passage_id {passage_id!r}")
        return qa_item

    raise ValueError("load_qa_item_from_db requires qa_item_id or passage_id")


def print_qa_item_summary(qa_item, label="QA item"):
    keywords = ", ".join(qa_item.required_keywords or []) or "(none)"
    print(
        f"{label}: {qa_item.id} ({qa_item.passage_reference}, passage_id={qa_item.passage_id})"
    )
    print(f"  Question: {qa_item.question_text}")
    print(f"  Expected: {qa_item.expected_answer}")
    print(f"  Keywords: {keywords}")


def ensure_qa_item_from_db(db, qa_item_id=None, passage_id=None, content_id=None):
    if passage_id is None and content_id is not None:
        passage_id = passage_id_from_content_id(content_id)
    if not qa_item_id and not passage_id:
        raise ValueError(
            "--from-db requires one of --qa-item-id, --passage-id, or --content-id"
        )

    qa_item = load_qa_item_from_db(db, qa_item_id=qa_item_id, passage_id=passage_id)
    print_qa_item_summary(qa_item, label="Using QA item from database")
    return qa_item


def ensure_uw_qa_item(db, json_path, content_id):
    entry = find_uw_entry(json_path, content_id)
    payload = qa_item_payload_from_uw_entry(entry)
    passage_id = payload["passage_id"]

    qa_item = db.scalars(
        select(QAItem)
        .where(QAItem.passage_id == passage_id)
        .order_by(QAItem.created_at.desc())
    ).first()
    if qa_item:
        print(
            f"Using existing QA item: {qa_item.id} "
            f"({qa_item.passage_reference}, content_id={content_id})"
        )
        return qa_item, payload

    qa_item = QAItem(
        passage_id=payload["passage_id"],
        passage_reference=payload["passage_reference"],
        passage_text=payload.get("passage_text"),
        audio_url=payload["audio_url"],
        question_text=payload["question_text"],
        expected_answer=payload["expected_answer"],
        required_keywords=payload["required_keywords"],
        optional_keywords=payload["optional_keywords"],
        min_responses_required=payload["min_responses_required"],
        active=payload["active"],
        review_priority=payload["review_priority"],
    )
    db.add(qa_item)
    db.flush()
    print(
        f"Created QA item: {qa_item.id} "
        f"({qa_item.passage_reference}, content_id={content_id})"
    )
    print(f"  Question: {qa_item.question_text}")
    print(f"  Expected: {qa_item.expected_answer}")
    print(f"  Keywords: {', '.join(qa_item.required_keywords)}")
    return qa_item, payload


def assign_question(db, wa_id, display_name, language, qa_item=None):
    participant = get_or_create_participant(db, wa_id, display_name)
    participant.target_language = language
    participant.consented = True

    participant_session = get_or_create_participant_session(db, participant)
    if participant_session.state == SessionState.ONBOARDING.value:
        participant_session.state = SessionState.IDLE.value

    batch_completed = False
    completed_batch_size = 0

    if qa_item is not None:
        try:
            prompt = assign_qa_item_to_participant(
                db, participant, participant_session, qa_item
            )
        except AssignmentAssignError as exc:
            print(f"Assignment failed: {exc}")
            db.commit()
            return None
    else:
        prompt, batch_completed, completed_batch_size = create_assignment_prompt(
            db, participant, participant_session
        )

    db.commit()

    print(f"Participant ID: {participant.id}")
    print(f"WA ID: {participant.wa_id}")
    print(f"Session state: {participant_session.state}")

    if not prompt:
        print("No assignment created.")
        print(f"  batch_completed={batch_completed}, completed_batch_size={completed_batch_size}")
        if qa_item is None:
            print(
                "  Check: active QA items, language=chinese on participant, "
                "and no duplicate assignments."
            )
        return None

    print(f"Assignment ID: {prompt.assignment_id}")
    print(f"QA item ID: {prompt.qa_item_id}")
    print("\n--- Message preview (not sent to WhatsApp) ---\n")
    print(get_assignment_prompt_text(prompt))
    print("\n--- Admin URLs (log in first) ---")
    print(f"  QA item detail: /admin/qa-items/{prompt.qa_item_id}")
    print("  QA items list:  /admin/qa-items")
    print("  Participants:   /admin/participants")
    return prompt


def submit_test_answer(wa_id, display_name, answer_text):
    result = record_whatsapp_text_message(
        wa_id=wa_id,
        display_name=display_name,
        message_id=f"dev-test-uw-{os.getpid()}",
        message_text=answer_text,
    )
    print("\n--- Answer recorded ---")
    print(f"  response_id: {result.response_id}")
    print(f"  assignment_id: {result.assignment_id}")
    print(f"  session_state: {result.session_state}")
    if result.prompt:
        print("\n--- Next question preview ---\n")
        print(get_assignment_prompt_text(result.prompt))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Test UW translation QA assignment without WhatsApp."
    )
    parser.add_argument("--seed-only", action="store_true", help="Only create the QA item row.")
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Load QA item from Supabase only (no UW JSON). Requires an identifier below.",
    )
    parser.add_argument(
        "--qa-item-id",
        help="QA item UUID in Supabase (implies --from-db).",
    )
    parser.add_argument(
        "--passage-id",
        help="QA passage_id in Supabase, e.g. uw-174345 (implies --from-db).",
    )
    parser.add_argument(
        "--assign",
        action="store_true",
        help="Assign the identified QA item (with --from-db). Default: next eligible question.",
    )
    parser.add_argument(
        "--content-id",
        default=DEFAULT_CONTENT_ID,
        help="UW content_id for JSON seed, or uw-{id} lookup with --from-db.",
    )
    parser.add_argument("--json-path", help="Path to uw-translation-questions-eng-luke.json.")
    parser.add_argument("--wa-id", help="Test participant WhatsApp ID (digits, no +).")
    parser.add_argument("--name", default="UW Luke Test User", help="Participant display name.")
    parser.add_argument(
        "--answer",
        help="If set, simulate a text answer after assigning (scores keywords).",
    )
    args = parser.parse_args()

    from_db = args.from_db or bool(args.qa_item_id or args.passage_id)
    if args.qa_item_id or args.passage_id:
        args.from_db = True

    if from_db and args.seed_only:
        parser.error("--seed-only cannot be used with --from-db")

    if args.assign and not from_db:
        parser.error("--assign requires --from-db, --qa-item-id, or --passage-id")

    wa_id = get_test_wa_id(args.wa_id)
    app = create_app()

    with app.app_context():
        factory = get_session_factory()
        qa_item = None

        if from_db:
            with factory() as db:
                qa_item = ensure_qa_item_from_db(
                    db,
                    qa_item_id=args.qa_item_id,
                    passage_id=args.passage_id,
                    content_id=args.content_id,
                )
        else:
            json_path = resolve_json_path(args.json_path)
            with factory() as db:
                ensure_uw_qa_item(db, json_path, args.content_id)
                db.commit()

            if args.seed_only:
                print(f"Seed complete from {json_path}")
                return

        if args.seed_only:
            print("QA item is already in the database (--from-db).")
            return

        assign_target = qa_item if (from_db and args.assign) else None
        if from_db and not args.assign:
            print(
                "\nNote: loaded QA item from DB but did not assign it. "
                "Pass --assign to give this question to the participant, "
                "or omit --from-db to auto-pick the next eligible question."
            )

        with factory() as db:
            if assign_target is not None:
                assign_target = db.get(QAItem, assign_target.id)
            prompt = assign_question(
                db, wa_id, args.name, "chinese", qa_item=assign_target
            )

        if args.answer and prompt:
            submit_test_answer(wa_id, args.name, args.answer)


if __name__ == "__main__":
    main()
