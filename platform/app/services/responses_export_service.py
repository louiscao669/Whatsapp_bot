"""CSV export for participant responses."""

import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from eten_shared.models import ParticipantResponse
from app.services.system_languages_service import canonical_language_code
from app.utils.admin_formatters import format_correctness_score, format_display_datetime

EXPORT_COLUMNS = [
    "response_id",
    "received_at",
    "participant_id",
    "participant_display_name",
    "qa_item_id",
    "passage_id",
    "passage_reference",
    "passage_text",
    "language",
    "question_text",
    "expected_answer",
    "required_keywords",
    "assignment_id",
    "batch_id",
    "question_type",
    "response_type",
    "response_text",
    "media_id",
    "media_url",
    "transcript_text",
    "normalized_text",
    "correctness_score",
    "matched_keywords",
    "missing_keywords",
    "is_correct",
    "flag_reason",
    "review_status",
]


def _serialize_json(value):
    return json.dumps(value or [], ensure_ascii=False)


def _response_to_row(response):
    participant = response.participant
    qa_item = response.qa_item
    assignment = response.assignment
    question_type = (qa_item.question_type if qa_item else "").strip().lower()
    choice_scored = question_type in {"mcq", "tf"}

    return {
        "response_id": response.id,
        "received_at": format_display_datetime(response.received_at),
        "participant_id": participant.id if participant else "",
        "participant_display_name": participant.display_name if participant else "",
        "qa_item_id": qa_item.id if qa_item else "",
        "passage_id": qa_item.passage_id if qa_item else "",
        "passage_reference": qa_item.passage_reference if qa_item else "",
        "passage_text": qa_item.passage_text if qa_item else "",
        "language": canonical_language_code(participant.target_language if participant else ""),
        "question_text": qa_item.question_text if qa_item else "",
        "expected_answer": qa_item.expected_answer if qa_item else "",
        "required_keywords": _serialize_json(qa_item.required_keywords if qa_item else []),
        "assignment_id": assignment.id if assignment else "",
        "batch_id": assignment.batch_id if assignment else "",
        "question_type": qa_item.question_type if qa_item else "",
        "response_type": response.response_type,
        "response_text": response.response_text or "",
        "media_id": "" if choice_scored else (response.media_id or ""),
        "media_url": "" if choice_scored else (response.media_url or ""),
        "transcript_text": "" if choice_scored else (response.transcript_text or ""),
        "normalized_text": "" if choice_scored else (response.normalized_text or ""),
        "correctness_score": (
            "" if choice_scored else format_correctness_score(response.correctness_score)
        ),
        "matched_keywords": (
            "" if choice_scored else _serialize_json(response.matched_keywords)
        ),
        "missing_keywords": (
            "" if choice_scored else _serialize_json(response.missing_keywords)
        ),
        "is_correct": response.is_correct,
        "flag_reason": response.flag_reason or "",
        "review_status": response.review_status,
    }


def _load_responses(db, *, flagged_only: bool):
    statement = (
        select(ParticipantResponse)
        .options(
            selectinload(ParticipantResponse.participant),
            selectinload(ParticipantResponse.qa_item),
            selectinload(ParticipantResponse.assignment),
        )
        .order_by(ParticipantResponse.received_at.desc())
    )
    if flagged_only:
        statement = statement.where(ParticipantResponse.is_correct == "pending")
    return db.scalars(statement).all()


def build_responses_csv(db, *, flagged_only: bool = False) -> str:
    responses = _load_responses(db, flagged_only=flagged_only)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for response in responses:
        writer.writerow(_response_to_row(response))
    return buffer.getvalue()
