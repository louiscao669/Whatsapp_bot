"""Language code normalization used across bot and platform."""


class LanguageError(Exception):
    pass


def normalize_language_code(language):
    if language is None:
        raise LanguageError("Language is required")

    value = str(language).strip()
    if not value:
        raise LanguageError("Language is required")
    if len(value) > 64:
        raise LanguageError("Language must be 64 characters or fewer")

    lowered = value.lower()
    if lowered in {"english", "en", "eng"}:
        return "eng"
    return value


def canonical_language_code(language_value):
    value = (language_value or "").strip()
    if not value:
        return ""
    try:
        return normalize_language_code(value).lower()
    except LanguageError:
        return value.lower()
