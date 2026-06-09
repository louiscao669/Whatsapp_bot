import os
import re
from typing import Iterable, List

from rapidfuzz import fuzz

# Longest suffixes first so "ing" is not stripped before "ring" incorrectly.
_STEM_SUFFIXES = (
    "iness",
    "ment",
    "ness",
    "ing",
    "ed",
    "es",
    "er",
    "est",
    "ly",
    "s",
)


def normalize_response_text(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return " ".join(normalized.split())


def stem_word(word: str) -> str:
    token = (word or "").strip().lower()
    if not token:
        return ""

    for suffix in _STEM_SUFFIXES:
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]

    return token


def get_fuzzy_match_threshold() -> int:
    raw = os.getenv("KEYWORD_FUZZY_MATCH_THRESHOLD", "85")
    try:
        threshold = int(raw)
    except ValueError:
        threshold = 85
    return max(50, min(threshold, 100))


def _tokens_match(keyword_token: str, response_token: str, threshold: int) -> bool:
    keyword_token = keyword_token.strip().lower()
    response_token = response_token.strip().lower()
    if not keyword_token or not response_token:
        return False

    if keyword_token == response_token:
        return True

    keyword_stem = stem_word(keyword_token)
    response_stem = stem_word(response_token)
    if keyword_stem and keyword_stem == response_stem:
        return True

    # Substring helps for compounds: "witness" in "eyewitnesses".
    shorter, longer = (
        (keyword_stem, response_stem)
        if len(keyword_stem) <= len(response_stem)
        else (response_stem, keyword_stem)
    )
    if len(shorter) >= 3 and shorter in longer:
        return True

    return fuzz.ratio(keyword_stem, response_stem) >= threshold


def _phrase_matches(phrase: str, response_tokens: List[str], threshold: int) -> bool:
    parts = normalize_response_text(phrase).split()
    if not parts:
        return False

    return all(
        any(_tokens_match(part, token, threshold) for token in response_tokens)
        for part in parts
    )


def keyword_variants(keyword: str, keyword_specs: Iterable[dict]) -> List[str]:
    variants = []
    seen = set()
    normalized_keyword = normalize_response_text(keyword)

    def add_variant(value: str):
        cleaned = (value or "").strip()
        if not cleaned:
            return
        key = normalize_response_text(cleaned)
        if key in seen:
            return
        seen.add(key)
        variants.append(cleaned)

    add_variant(keyword)

    for spec in keyword_specs or []:
        if not isinstance(spec, dict):
            continue
        spec_text = (spec.get("text") or "").strip()
        if normalize_response_text(spec_text) != normalized_keyword and spec_text != keyword:
            continue
        add_variant(spec_text)
        for synonym in spec.get("synonyms") or []:
            add_variant(str(synonym))
        break

    return variants


def keyword_matches_in_response(
    keyword: str,
    response_text: str,
    keyword_specs: Iterable[dict] | None = None,
    threshold: int | None = None,
) -> bool:
    if threshold is None:
        threshold = get_fuzzy_match_threshold()

    normalized_response = normalize_response_text(response_text)
    if not normalized_response:
        return False

    # Fast path: exact phrase present after normalization.
    for variant in keyword_variants(keyword, keyword_specs or []):
        normalized_variant = normalize_response_text(variant)
        if normalized_variant and normalized_variant in normalized_response:
            return True

    response_tokens = normalized_response.split()
    for variant in keyword_variants(keyword, keyword_specs or []):
        if _phrase_matches(variant, response_tokens, threshold):
            return True

    return False
