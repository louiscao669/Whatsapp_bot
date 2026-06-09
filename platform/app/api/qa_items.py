from flask import Blueprint, jsonify, request

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.workflow_bridge import AssignmentAssignError
from app.services.qa_item_detail_service import get_qa_item_overview
from app.services.qa_item_responses_service import (
    get_qa_item_assignments_payload,
    get_qa_item_responses_payload,
)
from app.services.qa_item_stats_service import get_qa_item_stats
from app.services.qa_items_list_service import list_qa_items_with_stats
from app.services.qa_items_mutation_service import (
    QA_JSON_INPUT_HINT,
    QaItemsMutationError,
    assign_qa_item,
    bulk_assign_qa_items,
    bulk_delete_qa_items,
    delete_qa_item,
    get_uw_json_import_example,
    import_qa_items_from_json,
    list_participants_for_assign,
    parse_import_defaults,
    parse_selected_qa_item_ids,
    update_qa_item_settings,
)
from eten_shared.languages import LanguageError as QAImportError

qa_items_blueprint = Blueprint("api_qa_items", __name__)


def _json_body():
    return request.get_json(silent=True) or {}


def _mutation_error_response(exc, *, status=400):
    if isinstance(exc, (QaItemsMutationError, QAImportError, ValueError)):
        return jsonify({"error": "validation_error", "message": str(exc)}), status
    if isinstance(exc, AssignmentAssignError):
        return jsonify({"error": "assignment_error", "message": str(exc)}), 400
    return jsonify({"error": "server_error", "message": str(exc)}), 500


@qa_items_blueprint.route("/participants", methods=["GET"])
@require_roles("admin")
def list_assign_participants():
    session_factory = get_session_factory()
    with session_factory() as db:
        participants = list_participants_for_assign(db)
    return jsonify({"participants": participants})


@qa_items_blueprint.route("/import-template", methods=["GET"])
@require_roles("admin")
def get_import_template():
    return jsonify(
        {
            "template": get_uw_json_import_example(),
            "hint": QA_JSON_INPUT_HINT,
        }
    )


@qa_items_blueprint.route("/import", methods=["POST"])
@require_roles("admin")
def import_qa_items_endpoint():
    json_text = ""
    skip_existing = True
    defaults_payload = {}

    if request.content_type and "multipart/form-data" in request.content_type:
        uploaded = request.files.get("json_file")
        if uploaded and uploaded.filename:
            json_text = uploaded.read().decode("utf-8")
        else:
            json_text = (request.form.get("json_text") or "").strip()
        skip_existing = request.form.get("skip_existing", "1") in {"1", "true", "yes", "on"}
        defaults_payload = {
            "min_responses_required": request.form.get("import_min_responses_required", "3"),
            "review_priority": request.form.get("import_review_priority", "0"),
            "active": request.form.get("import_active", "1") in {"1", "true", "yes", "on"},
        }
    else:
        body = _json_body()
        json_text = (body.get("json_text") or "").strip()
        skip_existing = bool(body.get("skip_existing", True))
        defaults_payload = body.get("defaults") or {}

    try:
        import_defaults = parse_import_defaults(defaults_payload)
        session_factory = get_session_factory()
        with session_factory() as db:
            result = import_qa_items_from_json(
                db,
                json_text=json_text,
                skip_existing=skip_existing,
                import_defaults=import_defaults,
            )
            db.commit()
    except Exception as exc:
        return _mutation_error_response(exc)

    response = {
        "ok": True,
        "created": result["created"],
        "skipped": result["skipped"],
        "errors": result["errors"],
    }
    if result["errors"]:
        response["message"] = (
            f"Imported {result['created']} with {len(result['errors'])} error(s)"
        )
    else:
        response["message"] = f"Imported {result['created']} question(s)"
        if result["skipped"]:
            response["message"] += f"; skipped {result['skipped']} duplicate(s)"
    return jsonify(response)


@qa_items_blueprint.route("/bulk", methods=["POST"])
@require_roles("admin")
def bulk_qa_items_action():
    body = _json_body()
    action = (body.get("action") or "").strip().lower()
    qa_item_ids = parse_selected_qa_item_ids(body.get("qa_item_ids") or [])

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            if action == "delete":
                count = bulk_delete_qa_items(db, qa_item_ids)
                db.commit()
                return jsonify({"ok": True, "action": action, "count": count, "message": f"Deleted {count} question(s)"})

            if action == "assign":
                count = bulk_assign_qa_items(db, qa_item_ids, body.get("participant_id"))
                db.commit()
                return jsonify(
                    {
                        "ok": True,
                        "action": action,
                        "count": count,
                        "message": f"Assigned {count} question(s) to participant",
                    }
                )

            raise QaItemsMutationError("Unknown bulk action.")
    except Exception as exc:
        return _mutation_error_response(exc)


@qa_items_blueprint.route("", methods=["GET"])
@require_roles("admin")
def list_qa_items():
    session_factory = get_session_factory()
    with session_factory() as db:
        items = list_qa_items_with_stats(db)
    return jsonify({"items": items})


def _parse_language_args():
    languages = [value.strip() for value in request.args.getlist("languages") if value.strip()]
    if languages:
        return languages
    single = (request.args.get("language") or "").strip()
    return [single] if single else []


@qa_items_blueprint.route("/<qa_item_id>/responses", methods=["GET"])
@require_roles("admin")
def get_qa_item_responses_endpoint(qa_item_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_qa_item_responses_payload(db, qa_item_id, languages=_parse_language_args())
    if not payload:
        return jsonify({"error": "not_found", "message": "QA item not found"}), 404
    return jsonify(payload)


@qa_items_blueprint.route("/<qa_item_id>/assignments", methods=["GET"])
@require_roles("admin")
def get_qa_item_assignments_endpoint(qa_item_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_qa_item_assignments_payload(db, qa_item_id, languages=_parse_language_args())
    if not payload:
        return jsonify({"error": "not_found", "message": "QA item not found"}), 404
    return jsonify(payload)


@qa_items_blueprint.route("/<qa_item_id>/stats", methods=["GET"])
@require_roles("admin")
def get_qa_item_stats_endpoint(qa_item_id):
    session_factory = get_session_factory()
    with session_factory() as db:
        stats = get_qa_item_stats(db, qa_item_id, language_filter=_parse_language_args())
    if not stats:
        return jsonify({"error": "not_found", "message": "QA item not found"}), 404
    return jsonify({"stats": stats})


@qa_items_blueprint.route("/<qa_item_id>/settings", methods=["PATCH"])
@require_roles("admin")
def patch_qa_item_settings(qa_item_id):
    body = _json_body()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            update_qa_item_settings(db, qa_item_id, body)
            db.commit()
            item = get_qa_item_overview(db, qa_item_id)
    except Exception as exc:
        return _mutation_error_response(exc)

    return jsonify({"ok": True, "message": "Question settings updated", "item": item})


@qa_items_blueprint.route("/<qa_item_id>/assign", methods=["POST"])
@require_roles("admin")
def post_qa_item_assign(qa_item_id):
    body = _json_body()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            assign_qa_item(db, qa_item_id, body.get("participant_id"))
            db.commit()
    except Exception as exc:
        return _mutation_error_response(exc)

    return jsonify({"ok": True, "message": "Question assigned to participant"})


@qa_items_blueprint.route("/<qa_item_id>", methods=["DELETE"])
@require_roles("admin")
def delete_qa_item_endpoint(qa_item_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            delete_qa_item(db, qa_item_id)
            db.commit()
    except QaItemsMutationError as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except Exception as exc:
        return _mutation_error_response(exc)

    return jsonify({"ok": True, "message": "Question deleted"})


@qa_items_blueprint.route("/<qa_item_id>", methods=["GET"])
@require_roles("admin")
def get_qa_item(qa_item_id):
    language = (request.args.get("language") or "").strip()
    session_factory = get_session_factory()
    with session_factory() as db:
        item = get_qa_item_overview(db, qa_item_id, language=language)
    if not item:
        return jsonify({"error": "not_found", "message": "QA item not found"}), 404
    return jsonify({"item": item})
