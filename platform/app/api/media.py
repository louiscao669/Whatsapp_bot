from flask import Blueprint, Response, jsonify, request, session

from app.services.admin_media_service import (
    expert_may_access_participant_response,
    load_participant_response_media,
    load_qa_keyword_recording_media,
    load_qa_recording_media,
    log_media_access,
)
from app.services.admin_session_service import require_roles

media_blueprint = Blueprint("api_media", __name__)


def _request_role():
    return session.get("admin_role")


def _media_stream_cache_headers():
    return {
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
    }


def _stream_response(content, content_type, *, filename: str, as_download: bool):
    headers = _media_stream_cache_headers()
    disposition = "attachment" if as_download else "inline"
    headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return Response(content, mimetype=content_type, headers=headers)


@media_blueprint.route("/participant-response/<response_id>", methods=["GET"])
@require_roles("admin", "expert")
def stream_participant_response_media(response_id):
    role = _request_role()
    response, content, content_type = load_participant_response_media(response_id)
    if not response:
        return jsonify({"error": "not_found", "message": "Response not found"}), 404

    if role == "expert" and not expert_may_access_participant_response(response):
        return jsonify({"error": "forbidden", "message": "Forbidden"}), 403

    if not content:
        return jsonify({"error": "not_found", "message": "Audio not available"}), 404

    log_media_access("participant_response", response_id, role, session.get("admin_email"))
    as_download = request.args.get("download") in {"1", "true", "yes"}
    return _stream_response(
        content,
        content_type,
        filename=f"response_{response_id}.ogg",
        as_download=as_download,
    )


@media_blueprint.route("/qa-recording/<recording_id>", methods=["GET"])
@require_roles("admin", "expert")
def stream_qa_recording_media(recording_id):
    role = _request_role()
    recording, content, content_type = load_qa_recording_media(recording_id)
    if not recording:
        return jsonify({"error": "not_found", "message": "Recording not found"}), 404

    if not content:
        return jsonify({"error": "not_found", "message": "Audio not available"}), 404

    log_media_access("qa_recording", recording_id, role, session.get("admin_email"))
    as_download = request.args.get("download") in {"1", "true", "yes"}
    suffix = recording.recording_type or "recording"
    return _stream_response(
        content,
        content_type,
        filename=f"{suffix}_{recording_id}.ogg",
        as_download=as_download,
    )


@media_blueprint.route("/qa-keyword-recording/<recording_id>", methods=["GET"])
@require_roles("admin", "expert")
def stream_qa_keyword_recording_media(recording_id):
    role = _request_role()
    recording, content, content_type = load_qa_keyword_recording_media(recording_id)
    if not recording:
        return jsonify({"error": "not_found", "message": "Recording not found"}), 404

    if not content:
        return jsonify({"error": "not_found", "message": "Audio not available"}), 404

    log_media_access("qa_keyword_recording", recording_id, role, session.get("admin_email"))
    as_download = request.args.get("download") in {"1", "true", "yes"}
    return _stream_response(
        content,
        content_type,
        filename=f"keyword_{recording_id}.ogg",
        as_download=as_download,
    )
