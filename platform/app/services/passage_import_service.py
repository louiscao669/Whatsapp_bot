"""Import passage translations and split their text into numbered verses."""

import re
from dataclasses import dataclass

from sqlalchemy import select

from eten_shared.models import PassageTranslation, PassageVerse
from app.services.system_languages_service import canonical_language_code, upsert_system_language


class PassageImportError(Exception):
    pass


_VERSE_MARKER = re.compile(
    r"(?:^|(?<=[\s，。！？；：、,.!?;:])"
    r"|(?<=[，。！？；：、,.!?;:][”’」』》）)\]\"']))"
    r"(?:\\v\s+|\[)?(?P<number>\d{1,3}[a-z]?)(?:\]|[.):])?[ \t]+",
    re.IGNORECASE,
)
_PUNCTUATION = frozenset("，。！？；：、,.!?;:")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedVerse:
    number: str
    text: str


def _normalize_verse_spacing(text: str) -> str:
    """Remove inter-word whitespace while retaining one space after punctuation."""
    parts: list[str] = []
    cursor = 0
    for whitespace in _WHITESPACE.finditer(text):
        parts.append(text[cursor : whitespace.start()])
        if whitespace.start() > 0 and text[whitespace.start() - 1] in _PUNCTUATION:
            parts.append(" ")
        cursor = whitespace.end()
    parts.append(text[cursor:])
    return "".join(parts)


def parse_numbered_verses(
    source_text: str, *, allow_duplicate_numbers: bool = False
) -> list[ParsedVerse]:
    """Split numbered verses, including multiple verses on the same line."""
    if not (source_text or "").strip():
        raise PassageImportError("Translation text is required")

    verses: list[ParsedVerse] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("<header>"):
            continue
        markers = list(_VERSE_MARKER.finditer(line))
        if not markers:
            if verses:
                previous = verses[-1]
                verses[-1] = ParsedVerse(
                    number=previous.number,
                    text=f"{previous.text}\n{line}",
                )
            continue

        prefix = line[: markers[0].start()].strip()
        if prefix and verses:
            previous = verses[-1]
            verses[-1] = ParsedVerse(
                number=previous.number,
                text=f"{previous.text}\n{prefix}",
            )
        for index, marker in enumerate(markers):
            end = markers[index + 1].start() if index + 1 < len(markers) else len(line)
            verse_text = line[marker.end() : end].strip()
            number = marker.group("number").lower()
            if not verse_text:
                raise PassageImportError(f"Verse {number} has no text")
            verses.append(ParsedVerse(number=number, text=verse_text))

    if not verses:
        raise PassageImportError("No numbered verses were found")

    verses = [
        ParsedVerse(number=verse.number, text=_normalize_verse_spacing(verse.text))
        for verse in verses
    ]

    seen = set()
    occurrences: dict[str, int] = {}
    unique_verses = []
    for verse in verses:
        if verse.number in seen:
            if not allow_duplicate_numbers:
                raise PassageImportError(f"Verse number {verse.number} appears more than once")
            occurrences[verse.number] += 1
            unique_verses.append(
                ParsedVerse(
                    number=f"{verse.number}-{occurrences[verse.number]}",
                    text=verse.text,
                )
            )
            continue
        seen.add(verse.number)
        occurrences[verse.number] = 1
        unique_verses.append(verse)
    return unique_verses


def import_passage_translation(
    db,
    *,
    source_text: str,
    language: str,
    chapter_number,
    name=None,
    allow_duplicate_verse_numbers: bool = False,
):
    normalized_language = canonical_language_code(language)
    if not normalized_language:
        raise PassageImportError("Translation language is required")

    try:
        normalized_chapter_number = int(chapter_number)
    except (TypeError, ValueError) as exc:
        raise PassageImportError("Chapter number must be a positive integer") from exc
    if normalized_chapter_number < 1 or str(chapter_number).strip() != str(
        normalized_chapter_number
    ):
        raise PassageImportError("Chapter number must be a positive integer")

    normalized_name = str(name).strip() if name is not None else None
    normalized_name = normalized_name or None
    if normalized_name and len(normalized_name) > 255:
        raise PassageImportError("Translation name must be 255 characters or fewer")

    verses = parse_numbered_verses(
        source_text, allow_duplicate_numbers=allow_duplicate_verse_numbers
    )
    name_filter = (
        PassageTranslation.name == normalized_name
        if normalized_name is not None
        else PassageTranslation.name.is_(None)
    )
    translation = db.scalar(
        select(PassageTranslation)
        .join(PassageVerse)
        .where(
            PassageTranslation.language == normalized_language,
            name_filter,
            PassageVerse.chapter_number == normalized_chapter_number,
        )
        .order_by(PassageTranslation.created_at)
        .limit(1)
    )

    if translation is None:
        translation = PassageTranslation(language=normalized_language, name=normalized_name)
        db.add(translation)
        db.flush()
        existing_verses = []
    else:
        existing_verses = list(
            db.scalars(
                select(PassageVerse).where(
                    PassageVerse.translation_id == translation.id,
                    PassageVerse.chapter_number == normalized_chapter_number,
                ).order_by(PassageVerse.position)
            ).all()
        )

    by_number = {verse.verse_number: verse for verse in existing_verses}
    for parsed in verses:
        stored = by_number.get(parsed.number)
        if stored is None:
            stored = PassageVerse(
                translation_id=translation.id,
                chapter_number=normalized_chapter_number,
                verse_number=parsed.number,
                position=0,
                text=parsed.text,
            )
            db.add(stored)
            by_number[parsed.number] = stored
        else:
            stored.text = parsed.text

    # Temporarily move existing positions out of the positive range so merged
    # verses can be reordered without violating the unique-position constraint.
    previous_positions = {stored.id: stored.position for stored in existing_verses}
    for offset, stored in enumerate(existing_verses, start=1):
        stored.position = -offset
    if existing_verses:
        db.flush()

    # Preserve the source order. Any verses omitted by a partial reimport remain
    # afterward in their previous order, matching the existing merge behavior.
    parsed_numbers = [verse.number for verse in verses]
    remaining = sorted(
        (stored for number, stored in by_number.items() if number not in parsed_numbers),
        key=lambda stored: previous_positions.get(stored.id, 10**9),
    )
    ordered = [by_number[number] for number in parsed_numbers] + remaining
    for position, stored in enumerate(ordered, start=1):
        stored.position = position

    upsert_system_language(db, normalized_language, source="manual")
    db.flush()
    return translation, verses
