import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any, List, Optional

from eten_shared.mcq import (
    ParsedLabeledContent,
    QUESTION_TYPE_OPEN,
    VALID_QUESTION_TYPES,
    infer_question_type_from_choice_count,
    parse_choice_lines_from_text,
    parse_mcq_correct_letter,
    validate_question_fields,
)


class QAImportError(Exception):
    pass


def clean_html_fragment(fragment: str) -> str:
    text = re.sub(r"</?strong>", "", fragment, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip().strip('"').strip()


def extract_tagged_text(content_html: str, tag_name: str) -> str:
    content_html = content_html or ""

    paired_match = re.search(
        rf"<{tag_name}>(.*?)</{tag_name}>",
        content_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if paired_match:
        return clean_html_fragment(paired_match.group(1))

    fallback_match = re.search(
        rf"<{tag_name}>(.*?)(?=<question>|<answer>|$)",
        content_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fallback_match:
        return clean_html_fragment(fallback_match.group(1))

    return ""


def parse_open_paragraph_content(content_html: str) -> tuple[str, str]:
    paragraphs = re.findall(r"<p>(.*?)</p>", content_html, flags=re.DOTALL | re.IGNORECASE)
    if not paragraphs:
        return "", ""

    question = clean_html_fragment(paragraphs[0])
    answer = clean_html_fragment(paragraphs[1]) if len(paragraphs) > 1 else ""
    return question, answer


def parse_uw_html_content(content_html: str, *, question_type: Optional[str] = None):
    """
    Parse UW content field.

    Labeled format example:
      <question>Stem\\n\\nA. ...\\nB. ...\\nC. ...\\nD. ...<question><answer>B<answer>
    """
    question_block = extract_tagged_text(content_html, "question")
    answer_block = extract_tagged_text(content_html, "answer")

    if question_block:
        choices, stem = parse_choice_lines_from_text(question_block)
        if choices:
            override = (question_type or "").strip().lower()
            if override and override in VALID_QUESTION_TYPES:
                resolved_type = override
            else:
                resolved_type = infer_question_type_from_choice_count(len(choices))

            correct_letter = parse_mcq_correct_letter(answer_block)
            normalized_type, normalized_choices, letter, expected_answer = validate_question_fields(
                resolved_type,
                choices,
                correct_letter,
            )
            if not stem:
                stem = question_block.strip()
            return ParsedLabeledContent(
                question_type=normalized_type,
                question_text=stem,
                mcq_choices=normalized_choices,
                mcq_correct_choice=letter,
                expected_answer=expected_answer,
            )

        if stem and answer_block:
            return ParsedLabeledContent(
                question_type=QUESTION_TYPE_OPEN,
                question_text=stem,
                mcq_choices=[],
                mcq_correct_choice=None,
                expected_answer=answer_block,
            )

    question_text, expected_answer = parse_open_paragraph_content(content_html)
    if question_text:
        return ParsedLabeledContent(
            question_type=QUESTION_TYPE_OPEN,
            question_text=question_text,
            mcq_choices=[],
            mcq_correct_choice=None,
            expected_answer=expected_answer,
        )

    return None


def passage_reference_from_entry(entry):
    title = (entry.get("title") or "").split(" (#")[0].strip()
    if title:
        return title

    passage = (entry.get("associations") or {}).get("passage") or []
    if passage and passage[0].get("start_ref_usfm"):
        return passage[0]["start_ref_usfm"]

    return entry.get("index_reference") or "Unknown passage"


def passage_text_from_entry(entry):
    value = entry.get("passage_text")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def keywords_from_answer(answer_text):
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", answer_text or "")


def keyword_specs_from_answer(answer_text):
    specs = []
    for word in keywords_from_answer(answer_text):
        spec = keyword_spec(word, word, [])
        if spec:
            specs.append(spec)
    return specs


def is_uw_entry(entry):
    return isinstance(entry, dict) and "content" in entry and (
        "content_id" in entry or "index_reference" in entry
    )


def is_native_qa_entry(entry):
    return isinstance(entry, dict) and "question_text" in entry and "expected_answer" in entry


def labeled_fields_from_entry(entry):
    question_type = (entry.get("question_type") or QUESTION_TYPE_OPEN).strip().lower()
    normalized_type, choices, correct_letter, expected_answer = validate_question_fields(
        question_type,
        entry.get("mcq_choices"),
        entry.get("mcq_correct_choice"),
        expected_answer=entry.get("expected_answer", ""),
    )
    required_parsed = parse_keywords_field(entry.get("required_keywords"))
    optional_parsed = parse_keywords_field(entry.get("optional_keywords"))
    return {
        "question_type": normalized_type,
        "mcq_choices": choices if normalized_type != QUESTION_TYPE_OPEN else [],
        "mcq_correct_choice": correct_letter if normalized_type != QUESTION_TYPE_OPEN else None,
        "expected_answer": expected_answer,
        **keyword_fields_from_parsed(required_parsed, optional_parsed),
    }


def keyword_fields_from_parsed(required_parsed: ParsedKeywords, optional_parsed: ParsedKeywords):
    required_keywords = required_parsed.texts
    required_keyword_specs = required_parsed.specs
    keyword_source = "json" if required_keywords else "none"
    return {
        "required_keywords": required_keywords,
        "optional_keywords": optional_parsed.texts,
        "required_keyword_specs": required_keyword_specs,
        "optional_keyword_specs": optional_parsed.specs,
        "original_required_keywords": list(required_keywords),
        "original_required_keyword_specs": list(required_keyword_specs),
        "keyword_source": keyword_source,
    }


def payload_from_parsed_content(parsed: ParsedLabeledContent, entry: dict):
    required_parsed = parse_keywords_field(entry.get("required_keywords"))
    optional_parsed = parse_keywords_field(entry.get("optional_keywords"))
    return {
        "question_text": parsed.question_text,
        "question_type": parsed.question_type,
        "mcq_choices": parsed.mcq_choices,
        "mcq_correct_choice": parsed.mcq_correct_choice,
        "expected_answer": parsed.expected_answer,
        "original_question_text": parsed.question_text,
        "original_expected_answer": parsed.expected_answer,
        "original_question_type": parsed.question_type,
        "original_mcq_choices": list(parsed.mcq_choices),
        "original_mcq_correct_choice": parsed.mcq_correct_choice,
        **keyword_fields_from_parsed(required_parsed, optional_parsed),
    }


def qa_item_payload_from_uw_entry(entry):
    parsed = parse_uw_html_content(
        entry.get("content", ""),
        question_type=entry.get("question_type"),
    )
    if not parsed or not parsed.question_text:
        raise QAImportError(
            f"UW entry {entry.get('content_id')} is missing a question in content HTML"
        )

    content_id = str(entry.get("content_id") or entry.get("index_reference") or "")
    if not content_id:
        raise QAImportError("UW entry is missing content_id and index_reference")

    return {
        "passage_id": f"uw-{content_id}",
        "passage_reference": passage_reference_from_entry(entry),
        "passage_text": passage_text_from_entry(entry),
        "audio_url": entry.get("audio_url"),
        **payload_from_parsed_content(parsed, entry),
        "min_responses_required": int(entry.get("min_responses_required", 3)),
        "active": bool(entry.get("active", True)),
        "review_priority": int(entry.get("review_priority", 0)),
    }


def qa_item_payload_from_native_entry(entry):
    passage_id = entry.get("passage_id")
    if not passage_id:
        raise QAImportError("Native QA JSON entry requires passage_id")

    content = entry.get("content")
    if content:
        parsed = parse_uw_html_content(content, question_type=entry.get("question_type"))
        if not parsed or not parsed.question_text:
            raise QAImportError("Native entry content is missing a parseable question")
        labeled = payload_from_parsed_content(parsed, entry)
    else:
        labeled = labeled_fields_from_entry(entry)
        labeled["original_question_text"] = entry["question_text"]
        labeled = {
            **labeled,
            "question_text": entry["question_text"],
        }

    return {
        "passage_id": str(passage_id),
        "passage_reference": entry.get("passage_reference") or str(passage_id),
        "passage_text": passage_text_from_entry(entry),
        "audio_url": entry.get("audio_url"),
        "language": entry.get("language") or "eng",
        **labeled,
        "min_responses_required": int(entry.get("min_responses_required", 3)),
        "active": bool(entry.get("active", True)),
        "review_priority": int(entry.get("review_priority", 0)),
    }


def qa_item_payload_from_entry(entry):
    if is_uw_entry(entry):
        return qa_item_payload_from_uw_entry(entry)
    if is_native_qa_entry(entry):
        return qa_item_payload_from_native_entry(entry)
    raise QAImportError(
        "Entry must be UW format (content + content_id) or native QA format "
        "(question_text + expected_answer + passage_id)"
    )


def parse_entries_from_json_text(json_text):
    if not json_text or not json_text.strip():
        raise QAImportError("JSON input is empty")

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise QAImportError(f"Invalid JSON: {exc}") from exc

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise QAImportError("JSON must be an object or an array of objects")


def normalize_language_code(language):
    if language is None:
        raise QAImportError("Language is required")

    value = str(language).strip()
    if not value:
        raise QAImportError("Language is required")
    if len(value) > 64:
        raise QAImportError("Language must be 64 characters or fewer")

    lowered = value.lower()
    if lowered in {"english", "en", "eng"}:
        return "eng"
    return value


def import_qa_entries(db, entries, skip_existing=True, import_defaults=None):
    from sqlalchemy import select

    from eten_shared.models import QAItem

    created = 0
    skipped = 0
    errors = []

    for index, entry in enumerate(entries, start=1):
        try:
            payload = qa_item_payload_from_entry(entry)
            if import_defaults:
                payload.update(import_defaults)
            payload.pop("language", None)
            existing = db.scalars(
                select(QAItem).where(QAItem.passage_id == payload["passage_id"])
            ).first()
            if existing:
                if skip_existing:
                    skipped += 1
                    continue
                for field, value in payload.items():
                    setattr(existing, field, value)
                skipped += 1
                continue

            db.add(QAItem(**payload))
            created += 1
        except (QAImportError, ValueError, TypeError) as exc:
            errors.append(f"Entry {index}: {exc}")

    if created:
        db.flush()

    return {"created": created, "skipped": skipped, "errors": errors}
