from flask import Blueprint, Response, jsonify, request, send_from_directory
from sqlalchemy import select

from eten_shared.database import get_session_factory
from eten_shared.models import Assignment, AssignmentStatus, Participant, ParticipantResponse, QAItemRecording
from eten_shared.repo_paths import REPO_ROOT
from app.services.admin_media_service import (
    load_participant_response_media,
    load_qa_recording_media,
)
from app.user_dashboard.service import (
    ChestRewardError,
    CosmeticUpdateError,
    DashboardAnswerError,
    ProfilePhotoUploadError,
    ProfilePhotoNotFoundError,
    StorePurchaseError,
    StreakPauseUpdateError,
    get_user_dashboard_payload,
    claim_batch_chest_reward,
    load_profile_photo,
    purchase_store_item,
    set_cosmetic_equipped,
    set_user_streak_pause,
    start_dashboard_new_batch,
    submit_dashboard_answer,
    update_profile_photo,
)


USER_DASHBOARD_DIR = REPO_ROOT / "platform" / "user_dashboard"

user_dashboard_blueprint = Blueprint("user_dashboard", __name__)


def _cors_response(response):
    origin = request.headers.get("Origin")
    if origin in {"http://127.0.0.1:5500", "http://localhost:5500"}:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


@user_dashboard_blueprint.after_request
def add_cors_headers(response):
    return _cors_response(response)


@user_dashboard_blueprint.route("/user-dashboard/api/<wa_id>", methods=["GET", "OPTIONS"])
@user_dashboard_blueprint.route("/api/v1/user-dashboard/<wa_id>", methods=["GET", "OPTIONS"])
def get_user_dashboard(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_user_dashboard_payload(db, wa_id)
        if payload:
            db.commit()

    if not payload:
        return jsonify({"error": "not_found", "message": "Participant not found"}), 404

    return jsonify(payload)


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/purchases",
    methods=["POST", "OPTIONS"],
)
def purchase_user_dashboard_item(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = purchase_store_item(db, wa_id, body.get("item_id"))
            db.commit()
    except StorePurchaseError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "purchase_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/cosmetics",
    methods=["POST", "OPTIONS"],
)
def update_user_dashboard_cosmetic(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = set_cosmetic_equipped(
                db,
                wa_id,
                body.get("item_id"),
                body.get("equipped") is True,
            )
            db.commit()
    except CosmeticUpdateError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "cosmetic_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/streak-pause",
    methods=["POST", "OPTIONS"],
)
def update_user_dashboard_streak_pause(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = set_user_streak_pause(db, wa_id, body.get("paused") is True)
            db.commit()
    except StreakPauseUpdateError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "streak_pause_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/batch-rewards",
    methods=["POST", "OPTIONS"],
)
def claim_user_dashboard_batch_reward(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = claim_batch_chest_reward(db, wa_id, body.get("batch_id"))
            db.commit()
    except ChestRewardError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "chest_reward_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/answers",
    methods=["POST", "OPTIONS"],
)
def submit_user_dashboard_answer(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = submit_dashboard_answer(
                db,
                wa_id,
                body.get("assignment_id"),
                body.get("response_text"),
            )
            db.commit()
    except DashboardAnswerError as exc:
        message = str(exc)
        status = 404 if message in {"Participant not found", "Assignment not found"} else 400
        return jsonify({"error": "answer_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/start-batch",
    methods=["POST", "OPTIONS"],
)
def start_user_dashboard_batch(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = start_dashboard_new_batch(db, wa_id)
            db.commit()
    except DashboardAnswerError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "start_batch_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/profile-photo",
    methods=["GET", "POST", "OPTIONS"],
)
def user_dashboard_profile_photo(wa_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))
    if request.method == "GET":
        session_factory = get_session_factory()
        try:
            with session_factory() as db:
                photo = load_profile_photo(db, wa_id)
        except ProfilePhotoNotFoundError as exc:
            return jsonify({"error": "profile_photo_error", "message": str(exc)}), 404

        if request.headers.get("If-None-Match") == photo["etag"]:
            response = Response(status=304)
        else:
            response = Response(photo["content"], mimetype=photo["content_type"])
        response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
        response.headers["ETag"] = photo["etag"]
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    photo = request.files.get("photo")
    if not photo:
        return (
            jsonify(
                {
                    "error": "profile_photo_error",
                    "message": "Profile photo file is required",
                }
            ),
            400,
        )

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = update_profile_photo(
                db,
                wa_id,
                photo.read(),
                photo.mimetype,
            )
            db.commit()
    except ProfilePhotoUploadError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "profile_photo_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/participant-response/<response_id>/audio",
    methods=["GET"],
)
def user_dashboard_participant_response_audio(wa_id, response_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        participant = db.scalars(
            select(Participant).where(Participant.wa_id == wa_id)
        ).first()
        response_row = db.get(ParticipantResponse, response_id)
        if (
            not participant
            or not response_row
            or response_row.participant_id != participant.id
        ):
            return jsonify({"error": "not_found", "message": "Audio not found"}), 404

    _, content, content_type = load_participant_response_media(response_id)
    if not content:
        return jsonify({"error": "not_found", "message": "Audio not available"}), 404
    return Response(content, mimetype=content_type or "application/octet-stream")


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/qa-question-recording/<recording_id>/audio",
    methods=["GET"],
)
def user_dashboard_qa_question_recording_audio(wa_id, recording_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        participant = db.scalars(
            select(Participant).where(Participant.wa_id == wa_id)
        ).first()
        recording = db.get(QAItemRecording, recording_id)
        if (
            not participant
            or not recording
            or (recording.recording_type or "").strip().lower() != "question"
        ):
            return jsonify({"error": "not_found", "message": "Audio not found"}), 404
        assigned = db.scalars(
            select(Assignment).where(
                Assignment.participant_id == participant.id,
                Assignment.qa_item_id == recording.qa_item_id,
            )
        ).first()
        if not assigned:
            return jsonify({"error": "not_found", "message": "Audio not found"}), 404

    _, content, content_type = load_qa_recording_media(recording_id)
    if not content:
        return jsonify({"error": "not_found", "message": "Audio not available"}), 404
    return Response(content, mimetype=content_type or "application/octet-stream")


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<wa_id>/qa-answer-recording/<recording_id>/audio",
    methods=["GET"],
)
def user_dashboard_qa_answer_recording_audio(wa_id, recording_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        participant = db.scalars(
            select(Participant).where(Participant.wa_id == wa_id)
        ).first()
        recording = db.get(QAItemRecording, recording_id)
        if (
            not participant
            or not recording
            or (recording.recording_type or "").strip().lower() != "answer"
        ):
            return jsonify({"error": "not_found", "message": "Audio not found"}), 404
        completed_assignment = db.scalars(
            select(Assignment).where(
                Assignment.participant_id == participant.id,
                Assignment.qa_item_id == recording.qa_item_id,
                Assignment.status == AssignmentStatus.COMPLETED.value,
            )
        ).first()
        if not completed_assignment:
            return jsonify({"error": "not_found", "message": "Audio not found"}), 404

    _, content, content_type = load_qa_recording_media(recording_id)
    if not content:
        return jsonify({"error": "not_found", "message": "Audio not available"}), 404
    return Response(content, mimetype=content_type or "application/octet-stream")


@user_dashboard_blueprint.route("/user_dashboard/", methods=["GET"])
@user_dashboard_blueprint.route("/user_dashboard/index.html", methods=["GET"])
@user_dashboard_blueprint.route("/user_dashboard/index.html/<wa_id>", methods=["GET"])
def user_dashboard_index(wa_id=None):
    return send_from_directory(USER_DASHBOARD_DIR, "index.html")


@user_dashboard_blueprint.route("/user_dashboard/<path:filename>", methods=["GET"])
def user_dashboard_static(filename):
    return send_from_directory(USER_DASHBOARD_DIR, filename)
