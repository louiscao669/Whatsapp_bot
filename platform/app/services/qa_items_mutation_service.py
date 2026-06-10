"""Write operations for QA items (import, settings, assign, delete, bulk)."""

import json
import re

from sqlalchemy import select

from eten_shared.models import Participant, QAItem
from eten_shared.repo_paths import REPO_ROOT
from app.services.workflow_bridge import (
    AssignmentAssignError,
    assign_qa_item_to_participant,
    get_or_create_participant_session,
)
from eten_shared.languages import LanguageError as QAImportError
from app.services.uw_qa_import_service import import_qa_entries, parse_entries_from_json_text
from app.utils.privacy import hash_wa_id_for_display


class QaItemsMutationError(Exception):
    pass


QA_JSON_INPUT_HINT = (
    '[{"passage_id": "luke-2-3", "passage_reference": "Luke 2:3", '
    '"passage_text": "...", "question_type": "open", "question_text": "...", '
    '"content": "<question>Stem\\n\\nA. ...\\nB. ...\\nC. ...\\nD. ...'
    '<question><answer>B<answer>", "question_type": "mcq"}'
)


def get_uw_json_import_example():
    example_path = REPO_ROOT / "supabase" / "seeds" / "data" / "uw_luke_1_2_174314.json"
    if example_path.exists():
        return example_path.read_text(encoding="utf-8").strip()

    return json.dumps(
        {
            "content_id": "174314",
            "reference_id": 128899,
            "version": "1.0.2",
            "title": "Luke 1:2",
            "passage_text": "even as those who from the beginning were eyewitnesses...",
            "media_type": "Text",
            "index_reference": "42001002",
            "language": "eng",
            "review_level": "None",
            "content": (
                "<p><strong>Who were the eyewitnesses that Luke mentions?</strong></p>"
                "<p>The eyewitnesses were with the apostles from the beginning.</p>"
            ),
            "associations": {
                "passage": [
                    {
                        "start_ref": "42001002",
                        "start_ref_usfm": "LUK 1:2",
                        "end_ref": "42001002",
                        "end_ref_usfm": "LUK 1:2",
                    }
                ],
                "resource": [],
                "acai": [],
            },
        },
        indent=2,
    )


def parse_selected_qa_item_ids(raw_ids):
    if not raw_ids:
        return []
    selected = []
    seen = set()
    for value in raw_ids:
        qa_item_id = str(value).strip()
        if not qa_item_id or qa_item_id in seen:
            continue
        seen.add(qa_item_id)
        selected.append(qa_item_id)
    return selected


def normalize_keyword_list(keywords):
    deduped = []
    seen = set()
    for keyword in keywords or []:
        text = str(keyword).strip()
        if not text:
            continue
        normalized = text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(text)
    return deduped


def parse_import_defaults(payload):
    payload = payload or {}
    try:
        min_responses_required = int(payload.get("min_responses_required", 3))
    except (TypeError, ValueError) as exc:
        raise QaItemsMutationError("Min responses required must be a whole number") from exc

    if min_responses_required < 1:
        raise QaItemsMutationError("Min responses required must be at least 1")

    try:
        review_priority = int(payload.get("review_priority", 0))
    except (TypeError, ValueError) as exc:
        raise QaItemsMutationError("Review priority must be a whole number") from exc

    active = payload.get("active", True)
    if isinstance(active, str):
        active = active.lower() in {"1", "true", "yes", "on"}

    return {
        "min_responses_required": min_responses_required,
        "review_priority": review_priority,
        "active": bool(active),
    }


def parse_settings_payload(payload):
    payload = payload or {}
    try:
        min_responses_required = int(payload.get("min_responses_required"))
    except (TypeError, ValueError) as exc:
        raise QaItemsMutationError("Min responses required must be a whole number") from exc

    if min_responses_required < 1:
        raise QaItemsMutationError("Min responses required must be at least 1")

    try:
        review_priority = int(payload.get("review_priority"))
    except (TypeError, ValueError) as exc:
        raise QaItemsMutationError("Review priority must be a whole number") from exc

    regenerate_required = bool(payload.get("regenerate_required_keywords"))
    required_keywords = normalize_keyword_list(payload.get("required_keywords"))
    optional_keywords = normalize_keyword_list(payload.get("optional_keywords"))

    new_required = payload.get("new_required_keywords", "")
    if isinstance(new_required, str) and new_required.strip():
        required_keywords = normalize_keyword_list(
            required_keywords
            + [part.strip() for part in re.split(r"[\n,]+", new_required) if part.strip()]
        )

    new_optional = payload.get("new_optional_keywords", "")
    if isinstance(new_optional, str) and new_optional.strip():
        optional_keywords = normalize_keyword_list(
            optional_keywords
            + [part.strip() for part in re.split(r"[\n,]+", new_optional) if part.strip()]
        )

    return (
        min_responses_required,
        review_priority,
        required_keywords,
        optional_keywords,
        regenerate_required,
    )


def list_participants_for_assign(db):
    participants = db.scalars(
        select(Participant).order_by(Participant.display_name, Participant.wa_id)
    ).all()
    return [
        {
            "id": participant.id,
            "display_name": participant.display_name,
            "wa_id": hash_wa_id_for_display(participant.wa_id),
            "target_language": participant.target_language,
        }
        for participant in participants
    ]


def import_qa_items_from_json(db, *, json_text, skip_existing, import_defaults):
    if not (json_text or "").strip():
        raise QaItemsMutationError("JSON text or file is required")

    entries = parse_entries_from_json_text(json_text)
    result = import_qa_entries(
        db,
        entries,
        skip_existing=bool(skip_existing),
        import_defaults=import_defaults,
    )
    return result


def delete_qa_item(db, qa_item_id):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise QaItemsMutationError("QA item not found")
    db.delete(qa_item)
    return qa_item_id


def bulk_delete_qa_items(db, qa_item_ids):
    ordered = _load_ordered_qa_items(db, qa_item_ids)
    for qa_item in ordered:
        db.delete(qa_item)
    return len(ordered)


def bulk_assign_qa_items(db, qa_item_ids, participant_id):
    if not participant_id:
        raise QaItemsMutationError("Select a participant before assigning.")

    participant = db.get(Participant, participant_id)
    if not participant:
        raise QaItemsMutationError("Participant not found")

    ordered = _load_ordered_qa_items(db, qa_item_ids)
    participant_session = get_or_create_participant_session(db, participant)
    for qa_item in ordered:
        assign_qa_item_to_participant(db, participant, participant_session, qa_item)
    return len(ordered)


def assign_qa_item(db, qa_item_id, participant_id):
    if not participant_id:
        raise QaItemsMutationError("Select a participant to assign this question.")

    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise QaItemsMutationError("QA item not found")

    participant = db.get(Participant, participant_id)
    if not participant:
        raise QaItemsMutationError("Participant not found")

    participant_session = get_or_create_participant_session(db, participant)
    assign_qa_item_to_participant(db, participant, participant_session, qa_item)
    return qa_item_id


def update_qa_item_settings(db, qa_item_id, payload):
    (
        min_responses_required,
        review_priority,
        required_keywords,
        optional_keywords,
        regenerate_required,
    ) = parse_settings_payload(payload)

    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        raise QaItemsMutationError("QA item not found")

    qa_item.min_responses_required = min_responses_required
    qa_item.review_priority = review_priority
    if regenerate_required:
        if qa_item.original_required_keywords:
            qa_item.required_keywords = list(qa_item.original_required_keywords)
            qa_item.required_keyword_specs = list(qa_item.original_required_keyword_specs or [])
        else:
            raise QaItemsMutationError(
                "Cannot regenerate required keywords because this QA item "
                "does not have original required keywords from import."
            )
    else:
        qa_item.required_keywords = required_keywords
    qa_item.optional_keywords = optional_keywords
    return qa_item.id


def _load_ordered_qa_items(db, qa_item_ids):
    selected_ids = parse_selected_qa_item_ids(qa_item_ids)
    if not selected_ids:
        raise QaItemsMutationError("Select at least one QA item.")

    qa_items = db.scalars(select(QAItem).where(QAItem.id.in_(selected_ids))).all()
    qa_items_by_id = {item.id: item for item in qa_items}
    ordered = [qa_items_by_id[item_id] for item_id in selected_ids if item_id in qa_items_by_id]
    if not ordered:
        raise QaItemsMutationError("Selected QA items were not found.")
    return ordered
