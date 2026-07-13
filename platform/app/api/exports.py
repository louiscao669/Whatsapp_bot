import logging

from flask import Blueprint, Response, jsonify, request

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.audio_export_service import (
    build_zip_archive,
    fetch_response_audio_bytes,
    get_audio_export_chapters,
    zip_download_filename,
)
from app.services.responses_export_service import build_responses_csv

exports_blueprint = Blueprint("api_exports", __name__)


def _json_body():
    return request.get_json(silent=True) or {}


def _serialize_audio_chapters(chapters):
    return [
        {
            "chapter_label": chapter.chapter_label,
            "chapter_key": chapter.chapter_key,
            "qa_groups": [
                {
                    "qa_item_id": group.qa_item_id,
                    "question_label": group.question_label,
                    "items": [
                        {
                            "response_id": item.response_id,
                            "participant_id": item.participant_id,
                            "participant_label": item.participant_label,
                            "export_filename": item.export_filename,
                            "received_at": item.received_at.isoformat() if item.received_at else None,
                            "has_storage": item.has_storage,
                        }
                        for item in group.items
                    ],
                }
                for group in chapter.qa_groups
            ],
        }
        for chapter in chapters
    ]


@exports_blueprint.route("/audio", methods=["GET"])
@require_roles("admin")
def list_audio_export():
    chapters = get_audio_export_chapters()
    return jsonify({"chapters": _serialize_audio_chapters(chapters)})


@exports_blueprint.route("/audio/<response_id>", methods=["GET"])
@require_roles("admin")
def download_audio_file(response_id):
    try:
        content, content_type, filename = fetch_response_audio_bytes(response_id)
    except Exception as exc:
        logging.exception("Audio export file failed")
        return jsonify({"error": "server_error", "message": str(exc)}), 500

    if not content:
        return jsonify({"error": "not_found", "message": "Audio file not available"}), 404

    return Response(
        content,
        mimetype=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@exports_blueprint.route("/audio/download", methods=["POST"])
@require_roles("admin")
def download_audio_zip():
    body = _json_body()
    response_ids = body.get("response_ids") or []
    if not isinstance(response_ids, list) or not response_ids:
        return jsonify({"error": "validation_error", "message": "response_ids is required"}), 400

    try:
        archive_bytes, included, errors = build_zip_archive(response_ids)
    except ValueError as exc:
        return jsonify({"error": "validation_error", "message": str(exc)}), 400
    except Exception as exc:
        logging.exception("Audio ZIP export failed")
        return jsonify({"error": "server_error", "message": str(exc)}), 500

    if errors:
        logging.warning("Audio export completed with %s errors", len(errors))

    filename = zip_download_filename()
    return Response(
        archive_bytes,
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@exports_blueprint.route("/responses.csv", methods=["GET"])
@require_roles("admin")
def export_responses_csv():
    session_factory = get_session_factory()
    with session_factory() as db:
        csv_text = build_responses_csv(db, flagged_only=False)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="responses.csv"'},
    )


@exports_blueprint.route("/flagged.csv", methods=["GET"])
@require_roles("admin")
def export_flagged_csv():
    session_factory = get_session_factory()
    with session_factory() as db:
        csv_text = build_responses_csv(db, flagged_only=True)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="flagged.csv"'},
    )
