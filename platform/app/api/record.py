import logging

from flask import Blueprint, jsonify, request, session

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.record_api_service import get_record_dashboard, serialize_recording
from app.services.record_mutation_service import RecordMutationError, delete_recording, upload_recording

record_blueprint = Blueprint("api_record", __name__)


def _mutation_error(exc, *, status=400):
    if isinstance(exc, RecordMutationError):
        return jsonify({"error": "validation_error", "message": str(exc)}), status
    return jsonify({"error": "server_error", "message": str(exc)}), 500


def _uploader_label():
    return session.get("admin_email") or session.get("admin_display_name") or session.get("admin_role")


@record_blueprint.route("", methods=["GET"])
@require_roles("expert")
def list_record_dashboard():
    language = (request.args.get("language") or "").strip()
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_record_dashboard(db, language=language)
        db.commit()
    return jsonify(payload)


@record_blueprint.route("/upload", methods=["POST"])
@require_roles("expert")
def upload_record_audio():
    qa_item_id = (request.form.get("qa_item_id") or "").strip()
    recording_type = (request.form.get("recording_type") or "").strip().lower()
    language = (request.form.get("language") or "").strip()
    mode = (request.form.get("mode") or "new").strip().lower()
    recording_id = (request.form.get("recording_id") or "").strip()
    version_raw = (request.form.get("version") or "").strip()
    choice_letter = (request.form.get("choice_letter") or "").strip().upper()
    file = request.files.get("audio")

    if not file:
        return jsonify({"error": "validation_error", "message": "audio file is required"}), 400

    content = file.read()
    content_type = file.mimetype or "audio/webm"

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            record = upload_recording(
                db,
                qa_item_id=qa_item_id,
                recording_type=recording_type,
                language=language,
                content=content,
                content_type=content_type,
                mode=mode,
                recording_id=recording_id,
                version_raw=version_raw,
                choice_letter=choice_letter,
                uploader=_uploader_label(),
            )
            db.commit()
    except Exception as exc:
        logging.exception("Failed to upload QA recording")
        return _mutation_error(exc)

    label_prefix = "Question" if record.recording_type == "question" else "Answer"
    return jsonify(
        {
            "ok": True,
            "message": "Recording saved",
            "recording_id": record.id,
            "recording": serialize_recording(record, label_prefix=label_prefix),
        }
    )


@record_blueprint.route("/recordings/<recording_id>", methods=["DELETE"])
@require_roles("expert")
def delete_record_audio(recording_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            delete_recording(db, recording_id)
    except RecordMutationError as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except Exception as exc:
        logging.exception("Failed to delete QA recording")
        return _mutation_error(exc)

    return jsonify({"ok": True, "message": "Recording removed"})
