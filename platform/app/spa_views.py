"""Serve the React admin SPA and redirect legacy /admin routes."""

from flask import Blueprint, redirect, request, send_from_directory, session

from eten_shared.repo_paths import REPO_ROOT

spa_blueprint = Blueprint("spa", __name__)

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def _spa_index():
    return send_from_directory(FRONTEND_DIST, "index.html")


def _role_home_path():
    role = session.get("admin_role")
    if role == "expert":
        return "/review-response"
    if role == "admin":
        return "/analytics"
    return "/login"


def _append_query(target: str) -> str:
    if request.query_string:
        return f"{target}?{request.query_string.decode()}"
    return target


@spa_blueprint.route("/admin/media/participant-response/<response_id>", methods=["GET"])
def redirect_participant_media(response_id):
    return redirect(_append_query(f"/api/v1/media/participant-response/{response_id}"), code=307)


@spa_blueprint.route("/admin/media/qa-recording/<recording_id>", methods=["GET"])
def redirect_qa_recording_media(recording_id):
    return redirect(_append_query(f"/api/v1/media/qa-recording/{recording_id}"), code=307)


@spa_blueprint.route("/admin/media/qa-keyword-recording/<recording_id>", methods=["GET"])
def redirect_keyword_recording_media(recording_id):
    return redirect(_append_query(f"/api/v1/media/qa-keyword-recording/{recording_id}"), code=307)


@spa_blueprint.route("/admin/logout", methods=["GET", "POST"])
def redirect_admin_logout():
    return redirect("/login", code=302)


@spa_blueprint.route("/admin/qa-items/<qa_item_id>", methods=["GET"])
def redirect_qa_item_detail(qa_item_id):
    return redirect(_append_query(f"/qa-items/{qa_item_id}"), code=302)


@spa_blueprint.route("/admin/participants/<participant_id>", methods=["GET"])
def redirect_participant_detail(participant_id):
    return redirect(f"/participants/{participant_id}", code=302)


@spa_blueprint.route("/admin/export/responses.csv", methods=["GET"])
def redirect_responses_csv():
    return redirect("/api/v1/export/responses.csv", code=302)


@spa_blueprint.route("/admin/export/flagged.csv", methods=["GET"])
def redirect_flagged_csv():
    return redirect("/api/v1/export/flagged.csv", code=302)


@spa_blueprint.route("/admin", methods=["GET", "POST"])
@spa_blueprint.route("/admin/", methods=["GET", "POST"])
def redirect_admin_root():
    if session.get("admin_role"):
        return redirect(_role_home_path(), code=302)
    return redirect("/login", code=302)


@spa_blueprint.route("/admin/<path:page>", methods=["GET", "POST"])
def redirect_legacy_admin_page(page):
    mapping = {
        "login": "/login",
        "analytics": "/analytics",
        "qa-items": "/qa-items",
        "review": "/review-response",
        "review-qa": "/review-qa",
        "record": "/record",
        "participants": "/participants",
        "system-languages": "/system-languages",
        "export/audio": "/export/audio",
    }
    target = mapping.get(page)
    if target:
        return redirect(_append_query(target), code=302)
    return redirect("/login", code=302)


@spa_blueprint.route("/assets/<path:filename>")
def spa_assets(filename):
    return send_from_directory(FRONTEND_DIST / "assets", filename)


@spa_blueprint.route("/", defaults={"path": ""})
@spa_blueprint.route("/<path:path>")
def spa_catch_all(path):
    if path.startswith(("api/", "webhook")):
        return {"error": "not_found"}, 404

    if FRONTEND_DIST.exists():
        candidate = FRONTEND_DIST / path
        if path and candidate.is_file():
            return send_from_directory(FRONTEND_DIST, path)
        return _spa_index()

    return (
        "<p>Frontend build not found. Run <code>cd frontend && npm run build</code>.</p>",
        503,
        {"Content-Type": "text/html"},
    )
