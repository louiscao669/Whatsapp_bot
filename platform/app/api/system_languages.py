from flask import Blueprint, jsonify, request

from eten_shared.database import get_session_factory
from eten_shared.models import SystemLanguage
from app.services.admin_session_service import require_roles
from app.services.system_languages_service import (
    canonical_language_code,
    get_registered_system_languages,
    sync_system_languages_registry,
    upsert_system_language,
)

system_languages_blueprint = Blueprint("api_system_languages", __name__)


def _json_body():
    return request.get_json(silent=True) or {}


@system_languages_blueprint.route("", methods=["GET"])
@require_roles("admin", "expert")
def list_system_languages():
    session_factory = get_session_factory()
    with session_factory() as db:
        sync_system_languages_registry(db)
        db.commit()
        languages = get_registered_system_languages(db)
    return jsonify({"languages": languages})


@system_languages_blueprint.route("", methods=["POST"])
@require_roles("admin", "expert")
def add_system_language():
    body = _json_body()
    code = canonical_language_code(body.get("code", ""))
    if not code:
        return jsonify({"error": "validation_error", "message": "code is required"}), 400

    session_factory = get_session_factory()
    with session_factory() as db:
        upsert_system_language(db, code, source="manual")
        db.commit()
        languages = get_registered_system_languages(db)

    return jsonify({"ok": True, "languages": languages})


@system_languages_blueprint.route("/<code>", methods=["DELETE"])
@require_roles("admin", "expert")
def remove_system_language(code):
    normalized = canonical_language_code(code)
    if not normalized:
        return jsonify({"error": "validation_error", "message": "code is required"}), 400

    session_factory = get_session_factory()
    with session_factory() as db:
        language_entry = db.get(SystemLanguage, normalized)
        if language_entry:
            db.delete(language_entry)
            db.commit()
        languages = get_registered_system_languages(db)

    return jsonify({"ok": True, "languages": languages})
