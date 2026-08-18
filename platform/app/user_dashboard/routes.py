from flask import Blueprint, Response, jsonify, redirect, request, send_from_directory
from sqlalchemy import select

from eten_shared.dashboard_links import DashboardLinkError, verify_dashboard_token
from eten_shared.domain.identity import resolve_login
from eten_shared.database import get_session_factory
from eten_shared.models import Assignment, AssignmentStatus, Participant, ParticipantResponse, QAItemRecording
from eten_shared.repo_paths import REPO_ROOT
from app.services.admin_media_service import (
    load_participant_response_media,
    load_qa_recording_media,
)
from app.user_dashboard.service import (
    ChestRewardError,
    CommunityTeamError,
    CosmeticUpdateError,
    DashboardAnswerError,
    DashboardSettingsError,
    ProfilePhotoUploadError,
    ProfilePhotoNotFoundError,
    StorePurchaseError,
    StreakPauseUpdateError,
    get_user_dashboard_payload,
    claim_batch_chest_reward,
    create_community_team,
    expire_dashboard_question,
    join_community_team,
    leave_community_team,
    load_profile_photo,
    mark_dashboard_question_viewed,
    record_dashboard_heartbeat,
    rename_community_team,
    remove_community_team,
    purchase_store_item,
    set_cosmetic_equipped,
    set_user_streak_pause,
    start_dashboard_new_batch,
    submit_dashboard_answer_receipt,
    update_dashboard_settings,
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


@user_dashboard_blueprint.route("/user-dashboard/api/<participant_id>", methods=["GET", "OPTIONS"])
@user_dashboard_blueprint.route("/api/v1/user-dashboard/<participant_id>", methods=["GET", "OPTIONS"])
def get_user_dashboard(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_user_dashboard_payload(db, participant_id)
        if payload:
            db.commit()

    if not payload:
        return jsonify({"error": "not_found", "message": "Participant not found"}), 404

    return jsonify(payload)


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/teams", methods=["POST", "OPTIONS"]
)
def create_user_dashboard_team(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))
    body = request.get_json(silent=True) or {}
    try:
        with get_session_factory()() as db:
            payload = create_community_team(db, participant_id, body.get("name"))
            db.commit()
    except CommunityTeamError as exc:
        status = 404 if str(exc) == "Participant not found" else 400
        return jsonify({"error": "team_error", "message": str(exc)}), status
    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/teams/<team_id>/join", methods=["POST", "OPTIONS"]
)
def join_user_dashboard_team(participant_id, team_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))
    try:
        with get_session_factory()() as db:
            payload = join_community_team(db, participant_id, team_id)
            db.commit()
    except CommunityTeamError as exc:
        status = 404 if str(exc) in {"Participant not found", "Team not found"} else 400
        return jsonify({"error": "team_error", "message": str(exc)}), status
    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/teams/<team_id>/name", methods=["POST", "OPTIONS"]
)
def rename_user_dashboard_team(participant_id, team_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))
    body = request.get_json(silent=True) or {}
    try:
        with get_session_factory()() as db:
            payload = rename_community_team(db, participant_id, team_id, body.get("name"))
            db.commit()
    except CommunityTeamError as exc:
        status = 404 if str(exc) == "Team not found" else 400
        return jsonify({"error": "team_error", "message": str(exc)}), status
    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/teams/<team_id>/leave", methods=["POST", "OPTIONS"]
)
def leave_user_dashboard_team(participant_id, team_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))
    try:
        with get_session_factory()() as db:
            payload = leave_community_team(db, participant_id, team_id)
            db.commit()
    except CommunityTeamError as exc:
        return jsonify({"error": "team_error", "message": str(exc)}), 400
    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/teams/<team_id>/remove", methods=["POST", "OPTIONS"]
)
def remove_user_dashboard_team(participant_id, team_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))
    try:
        with get_session_factory()() as db:
            payload = remove_community_team(db, participant_id, team_id)
            db.commit()
    except CommunityTeamError as exc:
        status = 404 if str(exc) == "Team not found" else 400
        return jsonify({"error": "team_error", "message": str(exc)}), status
    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/purchases",
    methods=["POST", "OPTIONS"],
)
def purchase_user_dashboard_item(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = purchase_store_item(db, participant_id, body.get("item_id"))
            db.commit()
    except StorePurchaseError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "purchase_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/cosmetics",
    methods=["POST", "OPTIONS"],
)
def update_user_dashboard_cosmetic(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = set_cosmetic_equipped(
                db,
                participant_id,
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
    "/user-dashboard/api/<participant_id>/streak-pause",
    methods=["POST", "OPTIONS"],
)
def update_user_dashboard_streak_pause(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = set_user_streak_pause(db, participant_id, body.get("paused") is True)
            db.commit()
    except StreakPauseUpdateError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "streak_pause_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/batch-rewards",
    methods=["POST", "OPTIONS"],
)
def claim_user_dashboard_batch_reward(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = claim_batch_chest_reward(db, participant_id, body.get("batch_id"))
            db.commit()
    except ChestRewardError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "chest_reward_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/answers",
    methods=["POST", "OPTIONS"],
)
def submit_user_dashboard_answer(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = submit_dashboard_answer_receipt(
                db,
                participant_id,
                body.get("assignment_id"),
                body.get("response_text"),
                body.get("submission_id"),
            )
            db.commit()
    except DashboardAnswerError as exc:
        message = str(exc)
        status = 404 if message in {"Participant not found", "Assignment not found"} else 400
        return jsonify({"error": "answer_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/questions/expire",
    methods=["POST", "OPTIONS"],
)
def expire_user_dashboard_question(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = expire_dashboard_question(
                db, participant_id, body.get("assignment_id")
            )
            db.commit()
    except DashboardAnswerError as exc:
        message = str(exc)
        status = 404 if message in {"Participant not found", "Assignment not found"} else 400
        return jsonify({"error": "question_expiry_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/start-batch",
    methods=["POST", "OPTIONS"],
)
def start_user_dashboard_batch(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = start_dashboard_new_batch(db, participant_id)
            db.commit()
    except DashboardAnswerError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "start_batch_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/settings",
    methods=["POST", "OPTIONS"],
)
def update_user_dashboard_settings(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = update_dashboard_settings(
                db,
                participant_id,
                language=body.get("language"),
                batch_size=body.get("batch_size"),
            )
            db.commit()
    except DashboardSettingsError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "settings_error", "message": message}), status

    return jsonify({"ok": True, **(payload or {})})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/profile-photo",
    methods=["GET", "POST", "OPTIONS"],
)
def user_dashboard_profile_photo(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))
    if request.method == "GET":
        session_factory = get_session_factory()
        try:
            with session_factory() as db:
                photo = load_profile_photo(db, participant_id)
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
                participant_id,
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
    "/user-dashboard/api/<participant_id>/participant-response/<response_id>/audio",
    methods=["GET"],
)
def user_dashboard_participant_response_audio(participant_id, response_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        participant = db.scalars(
            select(Participant).where(Participant.id == participant_id)
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
    "/user-dashboard/api/<participant_id>/qa-question-recording/<recording_id>/audio",
    methods=["GET"],
)
def user_dashboard_qa_question_recording_audio(participant_id, recording_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        participant = db.scalars(
            select(Participant).where(Participant.id == participant_id)
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
    "/user-dashboard/api/<participant_id>/qa-answer-recording/<recording_id>/audio",
    methods=["GET"],
)
def user_dashboard_qa_answer_recording_audio(participant_id, recording_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        participant = db.scalars(
            select(Participant).where(Participant.id == participant_id)
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


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/question-viewed",
    methods=["POST", "OPTIONS"],
)
def user_dashboard_question_viewed(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = mark_dashboard_question_viewed(
                db,
                participant_id,
                body.get("assignment_id"),
            )
            db.commit()
    except DashboardAnswerError as exc:
        message = str(exc)
        status = 404 if message in {"Participant not found", "Assignment not found"} else 400
        return jsonify({"error": "question_viewed_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route(
    "/user-dashboard/api/<participant_id>/heartbeat",
    methods=["POST", "OPTIONS"],
)
def user_dashboard_heartbeat(participant_id):
    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = record_dashboard_heartbeat(
                db,
                participant_id,
                body.get("session_key"),
                active=bool(body.get("active", True)),
            )
            db.commit()
    except DashboardAnswerError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "heartbeat_error", "message": message}), status

    return jsonify({"ok": True, **payload})


@user_dashboard_blueprint.route("/user-dashboard/api/login", methods=["POST", "OPTIONS"])
@user_dashboard_blueprint.route("/api/v1/user-dashboard/login", methods=["POST", "OPTIONS"])
def user_dashboard_login():
    """Resolve a WhatsApp phone / Telegram chat id to a participant and hand
    back their dashboard link. Resolve-only: never creates or links accounts
    (linking is done at provisioning time)."""

    if request.method == "OPTIONS":
        return _cors_response(jsonify({"ok": True}))

    body = request.get_json(silent=True) or {}
    identifier = (body.get("identifier") or "").strip()
    provider = (body.get("provider") or "").strip() or None
    if not identifier:
        return (
            jsonify(
                {
                    "error": "missing_identifier",
                    "message": "Enter your WhatsApp number or Telegram chat id.",
                }
            ),
            400,
        )

    session_factory = get_session_factory()
    with session_factory() as db:
        participant = resolve_login(db, identifier, provider)
        if participant is None:
            return (
                jsonify(
                    {
                        "error": "not_found",
                        "message": (
                            "No participant found for that WhatsApp number or "
                            "Telegram chat id."
                        ),
                    }
                ),
                404,
            )
        return _cors_response(
            jsonify(
                {
                    "participant_id": participant.id,
                    "redirect": f"/user_dashboard/index.html/{participant.id}",
                }
            )
        )


@user_dashboard_blueprint.route("/user_dashboard/login", methods=["GET"])
def user_dashboard_login_page():
    return send_from_directory(USER_DASHBOARD_DIR, "login.html")


@user_dashboard_blueprint.route("/user_dashboard/t/<token>", methods=["GET"])
def user_dashboard_deep_link(token):
    """Signed deep link used in messenger nudges: lands the participant on
    their own dashboard page without typing a participant_id."""

    try:
        participant_id = verify_dashboard_token(token)
    except DashboardLinkError:
        # Stale/invalid link: fall back to the login page rather than an error
        # so the participant can still get in with their phone / chat id.
        return redirect("/user_dashboard/login?notice=link_expired")
    return redirect(f"/user_dashboard/index.html/{participant_id}")


@user_dashboard_blueprint.route("/user_dashboard/", methods=["GET"])
@user_dashboard_blueprint.route("/user_dashboard/index.html", methods=["GET"])
@user_dashboard_blueprint.route("/user_dashboard/index.html/<participant_id>", methods=["GET"])
def user_dashboard_index(participant_id=None):
    return send_from_directory(USER_DASHBOARD_DIR, "index.html")


@user_dashboard_blueprint.route("/user_dashboard/<path:filename>", methods=["GET"])
def user_dashboard_static(filename):
    return send_from_directory(USER_DASHBOARD_DIR, filename)
