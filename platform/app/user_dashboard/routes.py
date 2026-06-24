from flask import Blueprint, Response, jsonify, request, send_from_directory

from eten_shared.database import get_session_factory
from eten_shared.repo_paths import REPO_ROOT
from app.user_dashboard.service import (
    CosmeticUpdateError,
    ProfilePhotoUploadError,
    ProfilePhotoNotFoundError,
    StorePurchaseError,
    StreakPauseUpdateError,
    get_user_dashboard_payload,
    load_profile_photo,
    purchase_store_item,
    set_cosmetic_equipped,
    set_user_streak_pause,
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


@user_dashboard_blueprint.route("/user_dashboard/", methods=["GET"])
@user_dashboard_blueprint.route("/user_dashboard/index.html", methods=["GET"])
@user_dashboard_blueprint.route("/user_dashboard/index.html/<wa_id>", methods=["GET"])
def user_dashboard_index(wa_id=None):
    return send_from_directory(USER_DASHBOARD_DIR, "index.html")


@user_dashboard_blueprint.route("/user_dashboard/<path:filename>", methods=["GET"])
def user_dashboard_static(filename):
    return send_from_directory(USER_DASHBOARD_DIR, filename)
