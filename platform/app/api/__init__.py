"""JSON API for the React admin frontend, split by domain."""

from flask import Blueprint, jsonify

from app.api.analytics import analytics_blueprint
from app.api.auth import auth_blueprint
from app.api.exports import exports_blueprint
from app.api.media import media_blueprint
from app.api.participants import participants_blueprint
from app.api.qa_items import qa_items_blueprint
from app.api.record import record_blueprint
from app.api.review_qa import review_qa_blueprint
from app.api.review_response import review_response_blueprint
from app.api.system_languages import system_languages_blueprint

api_blueprint = Blueprint("api", __name__, url_prefix="/api/v1")

api_blueprint.register_blueprint(auth_blueprint, url_prefix="/auth")
api_blueprint.register_blueprint(media_blueprint, url_prefix="/media")
api_blueprint.register_blueprint(qa_items_blueprint, url_prefix="/qa-items")
api_blueprint.register_blueprint(review_qa_blueprint, url_prefix="/review-qa")
api_blueprint.register_blueprint(review_response_blueprint, url_prefix="/review-response")
api_blueprint.register_blueprint(record_blueprint, url_prefix="/record")
api_blueprint.register_blueprint(analytics_blueprint, url_prefix="/analytics")
api_blueprint.register_blueprint(participants_blueprint, url_prefix="/participants")
api_blueprint.register_blueprint(system_languages_blueprint, url_prefix="/system-languages")
api_blueprint.register_blueprint(exports_blueprint, url_prefix="/export")


@api_blueprint.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@api_blueprint.route("/courses", methods=["GET"])
def list_courses():
    """Compatibility response for stale/dev clients that probe for course data."""
    return jsonify({"courses": [], "items": [], "total": 0})
