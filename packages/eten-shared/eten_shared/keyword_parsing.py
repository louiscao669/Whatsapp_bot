"""Keyword field parsing shared by import and rubric services."""

import json
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class ParsedKeywords:
    texts: List[str]
    specs: List[dict]


def normalize_synonyms(raw_synonyms: Any) -> List[str]:
    if raw_synonyms is None:
        return []
    if isinstance(raw_synonyms, str):
        return [part.strip() for part in raw_synonyms.split(",") if part.strip()]
    if isinstance(raw_synonyms, list):
        synonyms = []
        for item in raw_synonyms:
            text = str(item).strip()
            if text and text not in synonyms:
                synonyms.append(text)
        return synonyms
    return []


def keyword_spec(keyword_id: str, text: str, synonyms: Optional[List[str]] = None) -> Optional[dict]:
    cleaned_text = (text or "").strip()
    if not cleaned_text:
        return None
    cleaned_id = (keyword_id or cleaned_text).strip() or cleaned_text
    return {
        "id": cleaned_id,
        "text": cleaned_text,
        "synonyms": normalize_synonyms(synonyms),
    }


def specs_to_texts(specs: List[dict]) -> List[str]:
    texts = []
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        text = (spec.get("text") or "").strip()
        if text:
            texts.append(text)
    return texts


def parse_keywords_field(raw_value: Any) -> ParsedKeywords:
    if raw_value is None:
        return ParsedKeywords(texts=[], specs=[])
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if not raw_value:
            return ParsedKeywords(texts=[], specs=[])
        try:
            raw_value = json.loads(raw_value)
        except json.JSONDecodeError:
            return ParsedKeywords(
                texts=[part.strip() for part in raw_value.split(",") if part.strip()],
                specs=[],
            )
    if isinstance(raw_value, list):
        if not raw_value:
            return ParsedKeywords(texts=[], specs=[])
        if all(isinstance(item, str) for item in raw_value):
            return ParsedKeywords(
                texts=[item.strip() for item in raw_value if item.strip()],
                specs=[],
            )
        specs = []
        for item in raw_value:
            if not isinstance(item, dict):
                continue
            spec = keyword_spec(
                item.get("id", ""),
                item.get("text", ""),
                item.get("synonyms"),
            )
            if spec:
                specs.append(spec)
        return ParsedKeywords(texts=specs_to_texts(specs), specs=specs)
    return ParsedKeywords(texts=[], specs=[])
