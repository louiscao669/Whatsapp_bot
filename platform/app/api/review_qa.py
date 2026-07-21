from flask import Blueprint, jsonify, request

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.review_qa_api_service import get_review_qa_dashboard, serialize_review_qa_item
from app.services.review_qa_mutation_service import (
    ReviewQaMutationError,
    bulk_review_qa_chapter,
    mark_reviewed,
    remove_review_qa_item,
    restore_review_qa_item,
    return_unreviewed,
    revert_review_qa_item,
    target_tab_for_item,
    update_review_qa_item,
)

review_qa_blueprint = Blueprint("api_review_qa", __name__)


def _json_body():
    return request.get_json(silent=True) or {}


def _mutation_error(exc, *, status=400):
    if isinstance(exc, ReviewQaMutationError):
        return jsonify({"error": "validation_error", "message": str(exc)}), status
    return jsonify({"error": "server_error", "message": str(exc)}), 500


@review_qa_blueprint.route("", methods=["GET"])
@require_roles("admin", "expert")
def list_review_qa():
    tab = (request.args.get("tab") or "unreviewed").strip().lower()
    session_factory = get_session_factory()
    with session_factory() as db:
        payload = get_review_qa_dashboard(db, tab)
    return jsonify(payload)


@review_qa_blueprint.route("/bulk", methods=["POST"])
@require_roles("admin", "expert")
def bulk_review_qa():
    body = _json_body()
    action = (body.get("action") or "").strip().lower()
    chapter = body.get("chapter", "")

    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            next_tab, message = bulk_review_qa_chapter(db, action, chapter)
            db.commit()
    except Exception as exc:
        return _mutation_error(exc)

    return jsonify({"ok": True, "tab": next_tab, "message": message})


@review_qa_blueprint.route("/<qa_item_id>", methods=["PATCH"])
@require_roles("admin", "expert")
def patch_review_qa_item(qa_item_id):
    body = _json_body()
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = update_review_qa_item(db, qa_item_id, body)
            db.commit()
            item = serialize_review_qa_item(qa_item, tab="reviewed")
    except Exception as exc:
        return _mutation_error(exc)

    return jsonify(
        {
            "ok": True,
            "message": "QA saved and marked reviewed.",
            "item": item,
            "tab": "reviewed",
        }
    )


@review_qa_blueprint.route("/<qa_item_id>/mark-reviewed", methods=["POST"])
@require_roles("admin", "expert")
def post_mark_reviewed(qa_item_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = mark_reviewed(db, qa_item_id)
            db.commit()
            tab = target_tab_for_item(qa_item)
    except Exception as exc:
        return _mutation_error(exc)

    return jsonify({"ok": True, "message": "QA marked as reviewed.", "tab": tab})


@review_qa_blueprint.route("/<qa_item_id>/return-unreviewed", methods=["POST"])
@require_roles("admin", "expert")
def post_return_unreviewed(qa_item_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            return_unreviewed(db, qa_item_id)
            db.commit()
    except Exception as exc:
        return _mutation_error(exc)

    return jsonify({"ok": True, "message": "QA returned to unreviewed.", "tab": "unreviewed"})


@review_qa_blueprint.route("/<qa_item_id>/revert", methods=["POST"])
@require_roles("admin", "expert")
def post_revert(qa_item_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            revert_review_qa_item(db, qa_item_id)
            db.commit()
    except Exception as exc:
        return _mutation_error(exc)

    return jsonify({"ok": True, "message": "Reverted to original text.", "tab": "unreviewed"})


@review_qa_blueprint.route("/<qa_item_id>/remove", methods=["POST"])
@require_roles("admin", "expert")
def post_remove(qa_item_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            remove_review_qa_item(db, qa_item_id)
            db.commit()
    except Exception as exc:
        return _mutation_error(exc)

    return jsonify({"ok": True, "message": "QA moved to Removed QAs.", "tab": "removed"})


@review_qa_blueprint.route("/<qa_item_id>/restore", methods=["POST"])
@require_roles("admin", "expert")
def post_restore(qa_item_id):
    session_factory = get_session_factory()
    try:
        with session_factory() as db:
            qa_item = restore_review_qa_item(db, qa_item_id)
            db.commit()
            tab = target_tab_for_item(qa_item)
    except Exception as exc:
        return _mutation_error(exc)

    return jsonify({"ok": True, "message": "QA restored.", "tab": tab})
