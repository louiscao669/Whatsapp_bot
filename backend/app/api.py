"""JSON API for the React admin frontend (expanded in later migration phases)."""

from flask import Blueprint, jsonify

api_blueprint = Blueprint("api", __name__, url_prefix="/api/v1")


@api_blueprint.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})
