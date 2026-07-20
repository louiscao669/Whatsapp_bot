"""Passage translation list data for the admin interface."""

from sqlalchemy import select

from eten_shared.models import PassageTranslation, PassageVerse


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
