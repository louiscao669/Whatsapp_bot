from flask import Blueprint, jsonify, request

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.review_response_service import (
    ReviewResponseError,
    apply_review_response_decision,
    get_review_response_dashboard,
)

review_response_blueprint = Blueprint("api_review_response", __name__)


def _json_body():
    return request.get_json(silent=True) or {}


@review_response_blueprint.route("", methods=["GET"])
@require_roles("admin", "expert")
def list_review_responses():
    language = (request.args.get("language") or "").strip()
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_review_response_dashboard(db, language=language)
        db.commit()
    return jsonify(payload)


@review_response_blueprint.route("/<response_id>/decision", methods=["POST"])
@require_roles("admin", "expert")
def post_review_response_decision(response_id):
    body = _json_body()
    decision = (body.get("decision") or "").strip().lower()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            apply_review_response_decision(db, response_id, decision)
            db.commit()
    except ReviewResponseError as exc:
        return jsonify({"error": "validation_error", "message": str(exc)}), 400

    return jsonify({"ok": True, "message": "Review decision saved"})
