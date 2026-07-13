"""Responses and assignments tables for QA item detail."""

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from eten_shared.models import Assignment, ParticipantResponse, QAItem
from eten_shared.mcq import is_choice_scored_item
from app.services.qa_item_stats_service import (
    format_choice_correctness_label,
    format_choice_response_answer_display,
    open_response_status_label,
)
from app.services.system_languages_service import (
    participant_language_for_qa,
    parse_selected_languages,
    response_language_for_qa,
)
from app.utils.admin_formatters import format_correctness_score, format_display_datetime
from app.utils.media_urls import participant_response_media_url


def _iso_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _format_keyword_list(keywords):
    if not keywords:
        return []
    return [str(keyword).strip() for keyword in keywords if str(keyword).strip()]


def _serialize_open_response(qa_item, response):
    answer_text = response.transcript_text or response.response_text or ""
    has_audio = bool((response.media_url or "").strip())
    return {
        "received_at": format_display_datetime(response.received_at),
        "participant": (response.participant.display_name or response.participant.id)
        if response.participant
        else "",
        "language": response_language_for_qa(response),
        "response_type": response.response_type,
        "answer": answer_text,
        "normalized_text": response.normalized_text or "",
        "correctness_score": format_correctness_score(response.correctness_score),
        "matched_keywords": _format_keyword_list(response.matched_keywords),
        "missing_keywords": _format_keyword_list(response.missing_keywords),
        "is_correct": response.is_correct,
        "correctness_label": open_response_status_label(response.is_correct),
        "flag_reason": response.flag_reason or "",
        "review_status": response.review_status,
        "audio_url": participant_response_media_url(response.id) if has_audio else None,
    }


def _serialize_choice_response(qa_item, response):
    has_audio = bool((response.media_url or "").strip())
    return {
        "received_at": format_display_datetime(response.received_at),
        "participant": (response.participant.display_name or response.participant.id)
        if response.participant
        else "",
        "language": response_language_for_qa(response),
        "response_type": response.response_type,
        "choice_answer": format_choice_response_answer_display(qa_item, response),
        "correctness": format_choice_correctness_label(response.is_correct),
        "audio_url": participant_response_media_url(response.id) if has_audio else None,
    }


def get_qa_item_responses_payload(db, qa_item_id: str, *, languages=None):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        return None

    selected_languages = parse_selected_languages(languages or [], "")
    responses = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.qa_item_id == qa_item_id)
        .options(selectinload(ParticipantResponse.participant))
        .order_by(ParticipantResponse.received_at.desc())
    ).all()

    if selected_languages:
        language_set = set(selected_languages)
        responses = [
            response
            for response in responses
            if response_language_for_qa(response) in language_set
        ]

    choice_scored = is_choice_scored_item(qa_item)
    rows = []
    for response in responses:
        if choice_scored:
            rows.append(_serialize_choice_response(qa_item, response))
        else:
            rows.append(_serialize_open_response(qa_item, response))

    return {
        "qa_item_id": qa_item_id,
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "choice_scored": choice_scored,
        "languages": selected_languages,
        "responses": rows,
    }


def get_qa_item_assignments_payload(db, qa_item_id: str, *, languages=None):
    qa_item = db.get(QAItem, qa_item_id)
    if not qa_item:
        return None

    selected_languages = parse_selected_languages(languages or [], "")
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.qa_item_id == qa_item_id)
        .options(selectinload(Assignment.participant))
        .order_by(Assignment.assigned_at.desc())
    ).all()

    if selected_languages:
        language_set = set(selected_languages)
        assignments = [
            assignment
            for assignment in assignments
            if participant_language_for_qa(assignment.participant) in language_set
        ]

    rows = []
    for assignment in assignments:
        participant = assignment.participant
        rows.append(
            {
                "participant": (participant.display_name or participant.id) if participant else "",
                "participant_id": participant.id if participant else "",
                "language": participant_language_for_qa(participant),
                "status": assignment.status,
                "assigned_at": format_display_datetime(assignment.assigned_at),
                "completed_at": format_display_datetime(assignment.completed_at),
                "batch_id": assignment.batch_id or "",
            }
        )

    return {
        "qa_item_id": qa_item_id,
        "languages": selected_languages,
        "assignments": rows,
    }
