from flask import Blueprint, jsonify, request

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.participants_api_service import (
    ParticipantMutationError,
    get_participant_detail,
    list_participants_dashboard,
    update_participant_language,
)
from app.services.participant_assignment_service import (
    ParticipantAssignmentError,
    assign_questions_with_passages,
    get_assignment_options,
)

participants_blueprint = Blueprint("api_participants", __name__)


def _json_body():
    return request.get_json(silent=True) or {}


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


@participants_blueprint.route("/<participant_id>/language", methods=["PATCH"])
@require_roles("admin")
def patch_participant_language(participant_id):
    body = _json_body()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            update_participant_language(db, participant_id, body.get("language"))
            db.commit()
            payload = get_participant_detail(db, participant_id)
    except ParticipantMutationError as exc:
        message = str(exc)
        status = 404 if message == "Participant not found" else 400
        return jsonify({"error": "validation_error", "message": message}), status

    return jsonify({"ok": True, "message": "Participant language updated", **payload})


@participants_blueprint.route("/<participant_id>/assignment-options", methods=["GET"])
@require_roles("admin")
def participant_assignment_options(participant_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            payload = get_assignment_options(db, participant_id)
    except ParticipantAssignmentError as exc:
        status = 404 if str(exc) == "Participant not found" else 400
        return jsonify({"error": "validation_error", "message": str(exc)}), status
    return jsonify(payload)


@participants_blueprint.route("/<participant_id>/assignments", methods=["POST"])
@require_roles("admin")
def create_participant_assignments(participant_id):
    body = _json_body()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            assignments = assign_questions_with_passages(
                db, participant_id, body.get("selections")
            )
            db.commit()
    except ParticipantAssignmentError as exc:
        status = 404 if str(exc) == "Participant not found" else 400
        return jsonify({"error": "validation_error", "message": str(exc)}), status
    return jsonify(
        {
            "ok": True,
            "assigned_count": len(assignments),
            "message": f"Assigned {len(assignments)} question(s)",
        }
    ), 201
