from flask import Blueprint, jsonify

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.analytics_api_service import get_analytics_dashboard

analytics_blueprint = Blueprint("api_analytics", __name__)


@analytics_blueprint.route("", methods=["GET"])
@require_roles("admin")
def get_analytics():
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_analytics_dashboard(db)
    return jsonify(payload)
