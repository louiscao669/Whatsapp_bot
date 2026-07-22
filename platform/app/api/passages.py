from flask import Blueprint, jsonify, request
from sqlalchemy import select

from eten_shared.database import get_session_factory
from app.services.admin_session_service import require_roles
from app.services.passage_import_service import PassageImportError, import_passage_translation
from app.services.passage_list_service import get_passage_detail, list_passage_items
from app.services.system_languages_service import canonical_language_code
from eten_shared.models import PassageTranslation


passages_blueprint = Blueprint("api_passages", __name__)


@passages_blueprint.route("", methods=["GET"])
@require_roles("admin")
def passage_items_endpoint():
    session_factory = get_session_factory()
    with session_factory() as db:
        items = list_passage_items(db)
    return jsonify({"items": items})


@passages_blueprint.route("/<translation_id>/<int:chapter_number>", methods=["GET"])
@require_roles("admin")
def passage_detail_endpoint(translation_id, chapter_number):
    session_factory = get_session_factory()
    with session_factory() as db:
        detail = get_passage_detail(db, translation_id, chapter_number)
    if detail is None:
        return jsonify({"error": "not_found", "message": "Passage not found"}), 404
    return jsonify(detail)


@passages_blueprint.route("/translation-names", methods=["GET"])
@require_roles("admin")
def passage_translation_names_endpoint():
    language = canonical_language_code(request.args.get("language"))
    statement = select(PassageTranslation.name).where(PassageTranslation.name.is_not(None))
    if language:
        statement = statement.where(PassageTranslation.language == language)
    statement = statement.distinct().order_by(PassageTranslation.name)

    session_factory = get_session_factory()
    with session_factory() as db:
        names = [name for name in db.scalars(statement).all() if name]
    return jsonify({"names": names})


def _import_fields():
    if request.content_type and "multipart/form-data" in request.content_type:
        uploaded = request.files.get("translation_file")
        if uploaded and uploaded.filename:
            try:
                source_text = uploaded.read().decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise PassageImportError("Translation file must be UTF-8 text") from exc
        else:
            source_text = request.form.get("translation_text") or ""
        return (
            source_text,
            request.form.get("language"),
            request.form.get("chapter_number"),
            request.form.get("name"),
        )

    body = request.get_json(silent=True) or {}
    return (
        body.get("translation_text") or "",
        body.get("language"),
        body.get("chapter_number"),
        body.get("name"),
    )


@passages_blueprint.route("/import", methods=["POST"])
@require_roles("admin")
def import_passage_endpoint():
    try:
        source_text, language, chapter_number, name = _import_fields()
        session_factory = get_session_factory()
        with session_factory() as db:
            translation, verses = import_passage_translation(
                db,
                source_text=source_text,
                language=language,
                chapter_number=chapter_number,
                name=name,
            )
            db.commit()
            result = {
                "id": translation.id,
                "language": translation.language,
                "name": translation.name,
                "chapter_number": int(chapter_number),
                "verse_count": len(verses),
            }
    except PassageImportError as exc:
        return jsonify({"error": "validation_error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": "server_error", "message": str(exc)}), 500

    return jsonify(
        {
            "ok": True,
            "translation": result,
            "message": f"Imported {len(verses)} verse(s)",
        }
    ), 201
