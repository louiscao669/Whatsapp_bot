"""HTTP surface for the ``/pilot`` participant interface.

Caching contract (enforced in ``add_pilot_cache_headers``): PostgreSQL is the
source of truth, so every participant / session / question / submission /
checkpoint / result response is ``no-store``. A browser must never be able to
serve a cached question, a cached answer, a cached score or a cached completion
state. Only the versioned static assets under ``/pilot/static/`` are cacheable,
and those are content-versioned by query string.
"""

from flask import Blueprint, jsonify, redirect, request, send_from_directory

from eten_shared.dashboard_links import DashboardLinkError, verify_dashboard_token
from eten_shared.database import get_session_factory
from eten_shared.repo_paths import REPO_ROOT

from app.pilot.service import (
    PilotError,
    PilotNotFoundError,
    get_consent_state,
    record_consent,
    get_pilot_results,
    get_pilot_state,
    mark_pilot_question_viewed,
    record_pilot_activity_checkpoint,
    submit_pilot_answer,
)
from app.services.admin_session_service import require_roles

PILOT_DIR = REPO_ROOT / "platform" / "pilot"

pilot_blueprint = Blueprint("pilot", __name__)


@pilot_blueprint.after_request
def add_pilot_cache_headers(response):
    if request.path.startswith("/pilot/static/"):
        # Versioned assets only (?v=... in the page). Safe to cache hard, and
        # set outright because send_from_directory defaults these to no-cache.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


def _error(exc):
    status = 404 if isinstance(exc, PilotNotFoundError) else 400
    return jsonify({"error": "pilot_error", "message": str(exc)}), status


def _body():
    """Request body, tolerating ``sendBeacon`` payloads.

    ``navigator.sendBeacon`` may deliver a Blob whose Content-Type the browser
    rewrites, so the checkpoint endpoint cannot rely on a strict JSON header.
    """

    return request.get_json(silent=True, force=True) or {}


@pilot_blueprint.route("/pilot/api/<participant_id>/consent", methods=["GET"])
def pilot_consent_state(participant_id):
    """Whether the consent screen is due, and the approved text to display."""

    try:
        with get_session_factory()() as db:
            payload = get_consent_state(db, participant_id)
    except PilotError as exc:
        return _error(exc)
    return jsonify(payload)


@pilot_blueprint.route("/pilot/api/<participant_id>/consent", methods=["POST"])
def pilot_consent_record(participant_id):
    """Record the participant's decision. ``agreed`` must be sent explicitly.

    There is no default: a missing flag is a client bug, and defaulting either
    way would either fabricate consent or silently discard it.
    """

    body = _body()
    if "agreed" not in body or not isinstance(body["agreed"], bool):
        return (
            jsonify(
                {
                    "error": "pilot_error",
                    "message": "consent requires an explicit boolean 'agreed'",
                }
            ),
            400,
        )
    try:
        with get_session_factory()() as db:
            payload = record_consent(
                db, participant_id, body["agreed"], body.get("consent_version")
            )
            db.commit()
    except PilotError as exc:
        return _error(exc)
    return jsonify(payload)


@pilot_blueprint.route("/pilot/api/<participant_id>/question", methods=["GET"])
def pilot_question(participant_id):
    """The current question, or the completion state. Never the next one."""

    try:
        with get_session_factory()() as db:
            payload = get_pilot_state(db, participant_id)
            db.commit()
    except PilotError as exc:
        return _error(exc)
    return jsonify(payload)


@pilot_blueprint.route("/pilot/api/<participant_id>/session", methods=["POST"])
def pilot_session(participant_id):
    body = _body()
    try:
        with get_session_factory()() as db:
            payload = get_pilot_state(db, participant_id, body.get("consent_version"))
            db.commit()
    except PilotError as exc:
        return _error(exc)
    return jsonify(payload)


@pilot_blueprint.route("/pilot/api/<participant_id>/question/viewed", methods=["POST"])
def pilot_question_viewed(participant_id):
    body = _body()
    try:
        with get_session_factory()() as db:
            payload = mark_pilot_question_viewed(
                db,
                participant_id,
                body.get("assignment_id"),
                client_event_at=body.get("client_event_at"),
                reload_count=body.get("reload_count"),
            )
            db.commit()
    except PilotError as exc:
        return _error(exc)
    return jsonify({"ok": True, **payload})


@pilot_blueprint.route("/pilot/api/<participant_id>/question/checkpoint", methods=["POST"])
def pilot_question_checkpoint(participant_id):
    body = _body()
    try:
        with get_session_factory()() as db:
            payload = record_pilot_activity_checkpoint(
                db,
                participant_id,
                body.get("assignment_id"),
                event_type=body.get("event_type"),
                active_time_ms=body.get("active_time_ms"),
                focused_time_ms=body.get("focused_time_ms"),
                passage_onscreen_ms=body.get("passage_onscreen_ms"),
                visibility_change_count=body.get("visibility_change_count"),
                focus_change_count=body.get("focus_change_count"),
                reload_count=body.get("reload_count"),
                client_event_at=body.get("client_event_at"),
            )
            db.commit()
    except PilotError as exc:
        return _error(exc)
    return jsonify({"ok": True, **payload})


@pilot_blueprint.route("/pilot/api/<participant_id>/answers", methods=["POST"])
def pilot_answers(participant_id):
    body = _body()
    try:
        with get_session_factory()() as db:
            payload = submit_pilot_answer(
                db,
                participant_id,
                body.get("assignment_id"),
                submission_id=body.get("submission_id"),
                answer=body.get("answer"),
                active_time_ms=body.get("active_time_ms"),
                focused_time_ms=body.get("focused_time_ms"),
                passage_onscreen_ms=body.get("passage_onscreen_ms"),
                visibility_change_count=body.get("visibility_change_count"),
                focus_change_count=body.get("focus_change_count"),
                reload_count=body.get("reload_count"),
                client_event_at=body.get("client_event_at"),
            )
            # The receipt is committed here, before the client is told to
            # advance. Nothing about the next question is returned: the client
            # must ask for it, so it can neither be preloaded nor pre-timed.
            db.commit()
    except PilotError as exc:
        return _error(exc)
    return jsonify({"ok": True, **payload})


@pilot_blueprint.route("/pilot/api/results", methods=["GET"])
@require_roles("admin", "expert")
def pilot_results():
    participant_ids = [
        value.strip()
        for value in (request.args.get("participant_ids") or "").split(",")
        if value.strip()
    ]
    include_trials = request.args.get("include_trials", "false").lower() == "true"
    with get_session_factory()() as db:
        payload = get_pilot_results(db, participant_ids or None)
    if not include_trials:
        payload = {key: value for key, value in payload.items() if key != "trials"}
    return jsonify(payload)


# ----------------------------------------------------------------- static UI
@pilot_blueprint.route("/pilot", methods=["GET"])
@pilot_blueprint.route("/pilot/", methods=["GET"])
@pilot_blueprint.route("/pilot/<participant_id>", methods=["GET"])
def pilot_index(participant_id=None):
    return send_from_directory(PILOT_DIR, "index.html")


@pilot_blueprint.route("/pilot/t/<token>", methods=["GET"])
def pilot_deep_link(token):
    """Signed participant link, same convention as the user dashboard."""

    try:
        resolved_participant_id = verify_dashboard_token(token)
    except DashboardLinkError:
        return redirect("/pilot?notice=link_expired")
    return redirect(f"/pilot/{resolved_participant_id}")


@pilot_blueprint.route("/pilot/static/<path:filename>", methods=["GET"])
def pilot_static(filename):
    return send_from_directory(PILOT_DIR, filename)
