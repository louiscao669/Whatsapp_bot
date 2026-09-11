"""System language registry and participant/response language helpers."""

from sqlalchemy import select

from eten_shared.models import Participant, QAItemRecording, SystemLanguage
from eten_shared.languages import LanguageError as QAImportError, normalize_language_code


def canonical_language_code(language_value):
    value = (language_value or "").strip()
    if not value:
        return ""
    try:
        return normalize_language_code(value).lower()
    except QAImportError:
        return value.lower()


def participant_language_for_qa(participant):
    return canonical_language_code(participant.target_language if participant else "")


def response_language_for_qa(response):
    return participant_language_for_qa(response.participant)


def ensure_system_languages_table(db):
    SystemLanguage.__table__.create(bind=db.get_bind(), checkfirst=True)


def upsert_system_language(db, language_code, source):
    normalized = canonical_language_code(language_code)
    if not normalized:
        return
    ensure_system_languages_table(db)
    entry = db.get(SystemLanguage, normalized)
    if entry is None:
        entry = SystemLanguage(code=normalized)
        db.add(entry)
        db.flush()
    if source == "participant":
        entry.seen_in_participants = True
    if source == "recording":
        entry.seen_in_recordings = True


def sync_system_languages_registry(db):
    ensure_system_languages_table(db)
    participant_languages = db.scalars(select(Participant.target_language)).all()
    for language in participant_languages:
        upsert_system_language(db, language, "participant")

    recording_languages = db.scalars(select(QAItemRecording.language)).all()
    for language in recording_languages:
        upsert_system_language(db, language, "recording")

    db.flush()


def get_registered_system_languages(db):
    ensure_system_languages_table(db)
    return db.scalars(select(SystemLanguage.code).order_by(SystemLanguage.code)).all()


def parse_selected_languages(raw_values, fallback_language=""):
    parsed = []
    seen = set()
    for raw_value in raw_values or []:
        normalized = canonical_language_code(raw_value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        parsed.append(normalized)

    if parsed:
        return parsed

    fallback = canonical_language_code(fallback_language)
    return [fallback] if fallback else []
