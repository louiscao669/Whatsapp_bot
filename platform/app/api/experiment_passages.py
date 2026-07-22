from flask import Blueprint, jsonify

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.experiment_passages_service import (
    get_experiment_passage,
    list_experiment_passages,
)

experiment_passages_blueprint = Blueprint("api_experiment_passages", __name__)


@experiment_passages_blueprint.route("", methods=["GET"])
@require_roles("admin")
def experiment_passages_endpoint():
    session_factory = get_session_factory()
    with session_factory() as db:
        items = list_experiment_passages(db)
    return jsonify({"items": items})


@experiment_passages_blueprint.route("/<passage_id>", methods=["GET"])
@require_roles("admin")
def experiment_passage_detail_endpoint(passage_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        detail = get_experiment_passage(db, passage_id)
    if detail is None:
        return jsonify({"error": "not_found", "message": "Experiment passage not found"}), 404
    return jsonify(detail)
