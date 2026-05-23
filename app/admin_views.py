import csv
import hmac
import io
import json
from functools import wraps

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_session_factory
from app.models import ParticipantResponse


admin_blueprint = Blueprint("admin", __name__, url_prefix="/admin")


EXPORT_COLUMNS = [
    "response_id",
    "received_at",
    "participant_id",
    "participant_wa_id",
    "participant_display_name",
    "qa_item_id",
    "passage_id",
    "passage_reference",
    "language",
    "question_text",
    "expected_answer",
    "required_keywords",
    "assignment_id",
    "batch_id",
    "response_type",
    "response_text",
    "media_id",
    "media_url",
    "transcript_text",
    "normalized_text",
    "correctness_score",
    "matched_keywords",
    "missing_keywords",
    "is_flagged",
    "flag_reason",
    "review_status",
]


def admin_token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        expected_token = current_app.config.get("ADMIN_API_TOKEN")
        if not expected_token:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "ADMIN_API_TOKEN is not configured",
                    }
                ),
                503,
            )

        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()

        if not hmac.compare_digest(token, expected_token):
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        return f(*args, **kwargs)

    return decorated_function


def serialize_datetime(value):
    return value.isoformat() if value else ""


def serialize_json(value):
    return json.dumps(value or [], ensure_ascii=False)


def response_to_row(response):
    participant = response.participant
    qa_item = response.qa_item
    assignment = response.assignment

    return {
        "response_id": response.id,
        "received_at": serialize_datetime(response.received_at),
        "participant_id": participant.id if participant else "",
        "participant_wa_id": participant.wa_id if participant else "",
        "participant_display_name": participant.display_name if participant else "",
        "qa_item_id": qa_item.id if qa_item else "",
        "passage_id": qa_item.passage_id if qa_item else "",
        "passage_reference": qa_item.passage_reference if qa_item else "",
        "language": qa_item.language if qa_item else "",
        "question_text": qa_item.question_text if qa_item else "",
        "expected_answer": qa_item.expected_answer if qa_item else "",
        "required_keywords": serialize_json(qa_item.required_keywords if qa_item else []),
        "assignment_id": assignment.id if assignment else "",
        "batch_id": assignment.batch_id if assignment else "",
        "response_type": response.response_type,
        "response_text": response.response_text or "",
        "media_id": response.media_id or "",
        "media_url": response.media_url or "",
        "transcript_text": response.transcript_text or "",
        "normalized_text": response.normalized_text or "",
        "correctness_score": (
            "" if response.correctness_score is None else response.correctness_score
        ),
        "matched_keywords": serialize_json(response.matched_keywords),
        "missing_keywords": serialize_json(response.missing_keywords),
        "is_flagged": response.is_flagged,
        "flag_reason": response.flag_reason or "",
        "review_status": response.review_status,
    }


def get_responses(flagged_only=False):
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
        statement = statement.where(ParticipantResponse.is_flagged.is_(True))

    session_factory = get_session_factory()
    with session_factory() as db:
        return db.scalars(statement).all()


def build_csv_response(responses, filename):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for response in responses:
        writer.writerow(response_to_row(response))

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@admin_blueprint.route("/export/responses.csv", methods=["GET"])
@admin_token_required
def export_responses_csv():
    return build_csv_response(get_responses(flagged_only=False), "responses.csv")


@admin_blueprint.route("/export/flagged.csv", methods=["GET"])
@admin_token_required
def export_flagged_csv():
    return build_csv_response(get_responses(flagged_only=True), "flagged.csv")
