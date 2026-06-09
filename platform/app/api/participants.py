from flask import Blueprint, jsonify

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.participants_api_service import get_participant_detail, list_participants_dashboard

participants_blueprint = Blueprint("api_participants", __name__)


@participants_blueprint.route("", methods=["GET"])
@require_roles("admin")
def list_participants():
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = list_participants_dashboard(db)
    return jsonify(payload)


@participants_blueprint.route("/<participant_id>", methods=["GET"])
@require_roles("admin")
def get_participant(participant_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_participant_detail(db, participant_id)
    if not payload:
        return jsonify({"error": "not_found", "message": "Participant not found"}), 404
    return jsonify(payload)
