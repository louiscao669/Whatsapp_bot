"""Passage translation list + detail data for the admin interface."""

from sqlalchemy import select

from eten_shared.models import PassageTranslation, PassageVerse


def get_passage_detail(db, translation_id, chapter_number):
    """Full verse text + metadata for one (translation, chapter). None if absent."""
    translation = db.get(PassageTranslation, translation_id)
    if translation is None:
        return None
    try:
        chapter = int(chapter_number)
    except (TypeError, ValueError):
        return None

    verses = db.scalars(
        select(PassageVerse)
        .where(
            PassageVerse.translation_id == translation_id,
            PassageVerse.chapter_number == chapter,
        )
        .order_by(PassageVerse.position, PassageVerse.verse_number)
    ).all()
    if not verses:
        return None

    return {
        "id": translation.id,
        "language": translation.language,
        "translation_name": translation.name,
        "chapter_number": chapter,
        "created_at": translation.created_at.isoformat() if translation.created_at else None,
        "updated_at": translation.updated_at.isoformat() if translation.updated_at else None,
        "verse_count": len(verses),
        "verses": [
            {"verse_number": v.verse_number, "position": v.position, "text": v.text}
            for v in verses
        ],
    }


def list_passage_items(db):
    rows = db.execute(
        select(PassageTranslation, PassageVerse)
        .join(PassageVerse)
        .order_by(
            PassageTranslation.language,
            PassageTranslation.name,
            PassageVerse.chapter_number,
            PassageVerse.position,
        )
    ).all()

    items = {}
    for translation, verse in rows:
        key = (translation.id, verse.chapter_number)
        item = items.setdefault(
            key,
            {
                "id": translation.id,
                "language": translation.language,
                "translation_name": translation.name,
                "chapter_number": verse.chapter_number,
                "verse_numbers": [],
            },
        )
        item["verse_numbers"].append(verse.verse_number)

    result = []
    for item in items.values():
        verse_numbers = item.pop("verse_numbers")
        result.append(
            {
                **item,
                "verse_count": len(verse_numbers),
                "verses": ", ".join(verse_numbers),
            }
        )
    return result
