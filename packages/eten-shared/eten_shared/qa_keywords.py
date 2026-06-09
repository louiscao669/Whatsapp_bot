"""Per-language keyword rubrics for QA items."""

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from eten_shared.models import QAItem, QAItemLanguageKeywords, utc_now
from eten_shared.keyword_parsing import (
    keyword_spec,
    parse_keywords_field,
    specs_to_texts,
)
from eten_shared.languages import normalize_language_code


@dataclass
class KeywordRubric:
    required_keywords: List[str]
    required_keyword_specs: List[dict]
    optional_keywords: List[str]
    optional_keyword_specs: List[dict]
    source: str = "qa_item"


def _language_code(language: Optional[str]) -> str:
    if not language:
        return "eng"
    return normalize_language_code(language).lower()


def rubric_from_qa_item(qa_item: QAItem) -> KeywordRubric:
    return KeywordRubric(
        required_keywords=list(qa_item.required_keywords or []),
        required_keyword_specs=list(qa_item.required_keyword_specs or []),
        optional_keywords=list(qa_item.optional_keywords or []),
        optional_keyword_specs=list(qa_item.optional_keyword_specs or []),
        source="qa_item",
    )


def get_language_keywords(
    db: Session,
    qa_item_id: str,
    language: Optional[str],
) -> KeywordRubric:
    """Load rubric for a target language; fall back to QAItem import keywords."""
    language_code = _language_code(language)
    row = db.get(QAItemLanguageKeywords, (qa_item_id, language_code))
    if row and (row.required_keyword_specs or row.required_keywords):
        return KeywordRubric(
            required_keywords=list(row.required_keywords or []),
            required_keyword_specs=list(row.required_keyword_specs or []),
            optional_keywords=list(row.optional_keywords or []),
            optional_keyword_specs=list(row.optional_keyword_specs or []),
            source="language",
        )

    qa_item = db.get(QAItem, qa_item_id)
    if qa_item:
        return rubric_from_qa_item(qa_item)

    return KeywordRubric([], [], [], [], source="empty")


def get_all_language_keywords_for_qa_items(
    db: Session,
    qa_item_ids: List[str],
) -> dict[tuple[str, str], QAItemLanguageKeywords]:
    if not qa_item_ids:
        return {}

    rows = db.scalars(
        select(QAItemLanguageKeywords).where(
            QAItemLanguageKeywords.qa_item_id.in_(qa_item_ids)
        )
    ).all()
    return {
        (row.qa_item_id, _language_code(row.language)): row for row in rows
    }


def get_keywords_for_qa_items(
    db: Session,
    qa_item_ids: List[str],
    language: Optional[str],
) -> dict[str, QAItemLanguageKeywords]:
    if not qa_item_ids:
        return {}

    language_code = _language_code(language)
    rows = db.scalars(
        select(QAItemLanguageKeywords).where(
            QAItemLanguageKeywords.qa_item_id.in_(qa_item_ids),
            QAItemLanguageKeywords.language == language_code,
        )
    ).all()
    return {row.qa_item_id: row for row in rows}


def parse_keyword_rows_from_form(keyword_texts: List[str], synonym_fields: List[str]):
    """Build keyword specs from parallel form lists (Record page)."""
    specs = []
    synonym_fields = synonym_fields or []
    for index, raw_text in enumerate(keyword_texts or []):
        text = (raw_text or "").strip()
        if not text:
            continue
        raw_synonyms = synonym_fields[index] if index < len(synonym_fields) else ""
        synonyms = []
        if raw_synonyms:
            synonyms = [
                part.strip()
                for part in str(raw_synonyms).split(",")
                if part.strip()
            ]
        spec = keyword_spec(f"keyword_{index + 1}", text, synonyms)
        if spec:
            specs.append(spec)
    return specs


def upsert_language_keywords(
    db: Session,
    qa_item_id: str,
    language: str,
    required_specs: List[dict],
    optional_specs: Optional[List[dict]] = None,
    updated_by: Optional[str] = None,
) -> QAItemLanguageKeywords:
    language_code = _language_code(language)
    required_keywords = specs_to_texts(required_specs)
    optional_specs = optional_specs or []
    optional_keywords = specs_to_texts(optional_specs)

    row = db.get(QAItemLanguageKeywords, (qa_item_id, language_code))
    now = utc_now()
    if row is None:
        row = QAItemLanguageKeywords(
            qa_item_id=qa_item_id,
            language=language_code,
            required_keywords=required_keywords,
            required_keyword_specs=required_specs,
            optional_keywords=optional_keywords,
            optional_keyword_specs=optional_specs,
            updated_by=updated_by,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.required_keywords = required_keywords
        row.required_keyword_specs = required_specs
        row.optional_keywords = optional_keywords
        row.optional_keyword_specs = optional_specs
        row.updated_by = updated_by
        row.updated_at = now

    return row


def copy_import_keywords_to_language(
    db: Session,
    qa_item: QAItem,
    language: str,
    updated_by: Optional[str] = None,
) -> QAItemLanguageKeywords:
    """Seed language rubric from UW/import fields on the QA item."""
    return upsert_language_keywords(
        db,
        qa_item.id,
        language,
        list(qa_item.required_keyword_specs or []),
        list(qa_item.optional_keyword_specs or []),
        updated_by=updated_by,
    )


def merge_specs_from_json_field(raw_value) -> List[dict]:
    return parse_keywords_field(raw_value).specs


def _specs_field_name(keyword_kind: str) -> str:
    if keyword_kind == "optional":
        return "optional_keyword_specs"
    return "required_keyword_specs"


def _keywords_field_name(keyword_kind: str) -> str:
    if keyword_kind == "optional":
        return "optional_keywords"
    return "required_keywords"


def _find_spec_index(specs: List[dict], keyword_text: str) -> Optional[int]:
    target = (keyword_text or "").strip()
    if not target:
        return None
    for index, spec in enumerate(specs or []):
        if not isinstance(spec, dict):
            continue
        if (spec.get("text") or "").strip() == target:
            return index
    return None


def get_keyword_translations(
    language_row: Optional[QAItemLanguageKeywords],
    keyword_kind: str,
    keyword_text: str,
) -> List[str]:
    if not language_row:
        return []
    field = _specs_field_name(keyword_kind)
    specs = list(getattr(language_row, field) or [])
    index = _find_spec_index(specs, keyword_text)
    if index is None:
        return []
    spec = specs[index]
    return [str(s).strip() for s in (spec.get("synonyms") or []) if str(s).strip()]


def ensure_language_keywords_row(
    db: Session,
    qa_item: QAItem,
    language: str,
    updated_by: Optional[str] = None,
) -> QAItemLanguageKeywords:
    language_code = _language_code(language)
    row = db.get(QAItemLanguageKeywords, (qa_item.id, language_code))
    if row:
        return row
    return copy_import_keywords_to_language(db, qa_item, language_code, updated_by=updated_by)


def _validate_keyword_on_item(qa_item: QAItem, keyword_kind: str, keyword_text: str) -> bool:
    allowed = (
        qa_item.required_keywords
        if keyword_kind == "required"
        else qa_item.optional_keywords
    ) or []
    return keyword_text in {str(keyword).strip() for keyword in allowed if str(keyword).strip()}


def add_keyword_translation(
    db: Session,
    qa_item: QAItem,
    language: str,
    keyword_kind: str,
    keyword_text: str,
    translation: str,
    updated_by: Optional[str] = None,
) -> QAItemLanguageKeywords:
    cleaned = (translation or "").strip()
    if not cleaned:
        raise ValueError("translation is required")
    if keyword_kind not in {"required", "optional"}:
        raise ValueError("keyword_kind must be required or optional")
    if not _validate_keyword_on_item(qa_item, keyword_kind, keyword_text):
        raise ValueError("keyword_text does not match this question")

    row = ensure_language_keywords_row(db, qa_item, language, updated_by=updated_by)
    specs_field = _specs_field_name(keyword_kind)
    specs = list(getattr(row, specs_field) or [])
    index = _find_spec_index(specs, keyword_text)
    if index is None:
        raise ValueError("keyword_text does not match this question")

    spec = dict(specs[index])
    synonyms = [str(s).strip() for s in (spec.get("synonyms") or []) if str(s).strip()]
    if cleaned not in synonyms:
        synonyms.append(cleaned)
    spec["synonyms"] = synonyms
    specs[index] = spec
    setattr(row, specs_field, specs)
    setattr(row, _keywords_field_name(keyword_kind), specs_to_texts(specs))
    row.updated_by = updated_by
    row.updated_at = utc_now()
    return row


def remove_keyword_translation(
    db: Session,
    qa_item: QAItem,
    language: str,
    keyword_kind: str,
    keyword_text: str,
    translation: str,
    updated_by: Optional[str] = None,
) -> Optional[QAItemLanguageKeywords]:
    cleaned = (translation or "").strip()
    if not cleaned:
        raise ValueError("translation is required")
    if keyword_kind not in {"required", "optional"}:
        raise ValueError("keyword_kind must be required or optional")
    if not _validate_keyword_on_item(qa_item, keyword_kind, keyword_text):
        raise ValueError("keyword_text does not match this question")

    language_code = _language_code(language)
    row = db.get(QAItemLanguageKeywords, (qa_item.id, language_code))
    if not row:
        return None

    specs_field = _specs_field_name(keyword_kind)
    specs = list(getattr(row, specs_field) or [])
    index = _find_spec_index(specs, keyword_text)
    if index is None:
        return row

    spec = dict(specs[index])
    synonyms = [
        str(s).strip()
        for s in (spec.get("synonyms") or [])
        if str(s).strip() and str(s).strip() != cleaned
    ]
    spec["synonyms"] = synonyms
    specs[index] = spec
    setattr(row, specs_field, specs)
    row.updated_by = updated_by
    row.updated_at = utc_now()
    return row
