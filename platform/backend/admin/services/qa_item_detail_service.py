"""Read-only QA item detail payload for JSON API."""

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from eten_shared.mcq import choice_letters_for_item
from eten_shared.models import ExperimentPassage, ExperimentWindow, ParticipantResponse, QAItem, QAItemRecording
from eten_shared.domain.assignments import experiment_passage_assignment_kwargs
from eten_shared.pilot_trials import defect_for_condition
from backend.admin.services.qa_review_service import (
    format_qa_item_review_status_label,
    review_qa_tab_for_item,
)
from backend.admin.utils.admin_formatters import format_correctness_score
from backend.admin.utils.media_urls import qa_recording_media_url


def _iso_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _serialize_expected_answer(qa_item: QAItem):
    question_type = (qa_item.question_type or "open").strip().lower()
    if question_type not in {"mcq", "tf"}:
        return {
            "kind": "open",
            "text": qa_item.expected_answer or "",
        }

    choice_slots = len(choice_letters_for_item(qa_item))
    choices = list(qa_item.mcq_choices or [])
    correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
    return {
        "kind": question_type,
        "correct_choice": correct_letter or None,
        "choices": [
            {
                "letter": chr(ord("A") + index),
                "text": str(choices[index]).strip() if index < len(choices) else "",
                "is_correct": chr(ord("A") + index) == correct_letter,
            }
            for index in range(choice_slots)
        ],
    }


def _compute_metrics(qa_item: QAItem, responses):
    total_responses = len(responses)
    flagged_count = sum(
        1 for response in responses if response.is_correct in {"pending", "no (expert)"}
    )
    scored_responses = [
        response.correctness_score
        for response in responses
        if response.correctness_score is not None
    ]
    average_score = (
        format_correctness_score(sum(scored_responses) / len(scored_responses))
        if scored_responses
        else None
    )
    return {
        "total_responses": total_responses,
        "flagged_count": flagged_count,
        "flag_rate": round(flagged_count / total_responses, 3) if total_responses else None,
        "average_score": average_score,
        "scored_count": len(scored_responses),
        "meets_min_responses": total_responses >= qa_item.min_responses_required,
        "responses_needed": max(qa_item.min_responses_required - total_responses, 0),
    }


def _serialize_prompt_recording(recording: QAItemRecording | None):
    if not recording:
        return None
    return {
        "id": recording.id,
        "language": recording.language,
        "recording_type": recording.recording_type,
        "version": recording.version,
        "media_url": qa_recording_media_url(recording.id),
        "created_at": _iso_datetime(recording.created_at),
    }


def _latest_recordings_for_language(db, qa_item_id: str, language: str):
    if not language:
        return {}
    recordings = db.scalars(
        select(QAItemRecording).where(
            QAItemRecording.qa_item_id == qa_item_id,
            QAItemRecording.language == language,
        )
    ).all()
    latest = {}
    for recording in recordings:
        key = recording.recording_type
        current = latest.get(key)
        if not current or (recording.version, recording.created_at) > (
            current.version,
            current.created_at,
        ):
            latest[key] = recording
    return latest


def _question_passage_variants(db, qa_item):
    passages = db.scalars(
        select(ExperimentPassage)
        .where(ExperimentPassage.source_passage_id == qa_item.passage_id)
        .order_by(ExperimentPassage.language, ExperimentPassage.condition)
    ).all()
    window = db.scalar(select(ExperimentWindow).where(ExperimentWindow.qa_item_id == qa_item.id))
    variants = []
    for passage in sorted(passages, key=lambda row: (row.language, row.condition != "clean", row.condition)):
        # Curated windows use the same omission-padding rules as delivery.
        # Legacy questions have randomized windows, so show their full source.
        selection = experiment_passage_assignment_kwargs(db, passage, qa_item) if window else {}
        defect_type, defect_rate = defect_for_condition(passage.condition)
        variants.append({
            "id": passage.id,
            "condition": passage.condition,
            "language": passage.language,
            "defect_type": None if passage.condition == "clean" else defect_type,
            "defect_rate": defect_rate,
            "passage_text": selection.get("passage_text") if window else passage.passage_text,
            "verse_numbers": selection.get("passage_verse_numbers", []),
            "is_window": window is not None,
            "full_passage_text": passage.passage_text,
        })
    return variants


def get_qa_item_overview(db, qa_item_id: str, *, language: str = ""):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        return None

    responses = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.qa_item_id == qa_item_id)
        .options(selectinload(ParticipantResponse.participant))
        .order_by(ParticipantResponse.received_at.desc())
    ).all()

    prompt_recordings = _latest_recordings_for_language(db, qa_item_id, language)
    review_tab = review_qa_tab_for_item(qa_item)

    return {
        "id": qa_item.id,
        "passage_id": qa_item.passage_id,
        "passage": qa_item.passage_reference or qa_item.passage_id,
        "passage_text": qa_item.passage_text,
        "passage_variants": _question_passage_variants(db, qa_item),
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "question_text": qa_item.question_text,
        "expected_answer": _serialize_expected_answer(qa_item),
        "review_status": format_qa_item_review_status_label(qa_item, include_timestamp=True),
        "review_tab": review_tab,
        "qa_reviewed_at": _iso_datetime(qa_item.qa_reviewed_at),
        "review_removed_at": _iso_datetime(qa_item.review_removed_at),
        "active": qa_item.active,
        "settings": {
            "min_responses_required": qa_item.min_responses_required,
            "review_priority": qa_item.review_priority,
            "required_keywords": list(qa_item.required_keywords or []),
            "optional_keywords": list(qa_item.optional_keywords or []),
            "keyword_source": qa_item.keyword_source,
        },
        "prompt_recordings": {
            "language": language or None,
            "question": _serialize_prompt_recording(prompt_recordings.get("question")),
            "answer": _serialize_prompt_recording(prompt_recordings.get("answer")),
        },
        "analytics": _compute_metrics(qa_item, responses),
        "created_at": _iso_datetime(qa_item.created_at),
        "updated_at": _iso_datetime(qa_item.updated_at),
    }
