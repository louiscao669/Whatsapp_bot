"""Participants list and detail payloads."""

from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from eten_shared.models import Assignment, Participant, ParticipantResponse, ParticipantSession
from eten_shared.mcq import is_choice_scored_item
from app.services.qa_item_stats_service import (
    format_choice_correctness_label,
    format_choice_response_answer_display,
    open_response_status_label,
)
from app.services.system_languages_service import canonical_language_code, upsert_system_language
from app.utils.admin_formatters import format_display_datetime


CORRECT_IS_CORRECT_VALUES = frozenset({"yes (auto)", "yes (expert)"})
INCORRECT_IS_CORRECT_VALUES = frozenset({"no (expert)"})
UNDER_REVIEW_IS_CORRECT_VALUES = frozenset({"pending"})


class ParticipantMutationError(Exception):
    pass


def _truncate_text(value, max_length=240):
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def _format_assignment_label(assignment):
    qa_item = assignment.qa_item
    if not qa_item:
        return assignment.qa_item_id
    passage = qa_item.passage_reference or qa_item.passage_id
    return passage or "—"


def _participant_response_stats(db, participant_ids):
    if not participant_ids:
        return {}

    stats = {
        participant_id: {"total": 0, "correct": 0, "incorrect": 0, "under_review": 0}
        for participant_id in participant_ids
    }
    rows = db.execute(
        select(
            ParticipantResponse.participant_id,
            ParticipantResponse.is_correct,
            func.count(),
        )
        .where(ParticipantResponse.participant_id.in_(participant_ids))
        .group_by(ParticipantResponse.participant_id, ParticipantResponse.is_correct)
    )
    for participant_id, is_correct, count in rows:
        bucket = stats.get(participant_id)
        if not bucket:
            continue
        count = int(count or 0)
        bucket["total"] += count
        value = (is_correct or "").strip()
        if value in CORRECT_IS_CORRECT_VALUES:
            bucket["correct"] += count
        elif value in INCORRECT_IS_CORRECT_VALUES:
            bucket["incorrect"] += count
        elif value in UNDER_REVIEW_IS_CORRECT_VALUES:
            bucket["under_review"] += count
        else:
            bucket["under_review"] += count
    return stats


def _build_assigned_questions_summary(assignments):
    if not assignments:
        return ""
    labels = [
        f"{_format_assignment_label(assignment)} ({assignment.status})"
        for assignment in assignments
    ]
    return _truncate_text("; ".join(labels))


def _build_current_work_summary(participant_session):
    if not participant_session:
        return "", ""
    current_assignment = participant_session.current_assignment
    if not current_assignment:
        return participant_session.state, ""
    return participant_session.state, _format_assignment_label(current_assignment)


def _mcq_choice_text_for_letter(qa_item, letter):
    if not letter or letter == "—":
        return "—"
    choices = list(qa_item.mcq_choices or [])
    valid_letters = [chr(ord("A") + index) for index in range(len(choices))]
    if letter not in valid_letters:
        return "—"
    index = valid_letters.index(letter)
    text = str(choices[index]).strip()
    return text or "—"


def _format_expected_answer(qa_item):
    if is_choice_scored_item(qa_item):
        letter = (qa_item.mcq_correct_choice or "").strip().upper()
        return _mcq_choice_text_for_letter(qa_item, letter)
    return (qa_item.expected_answer or "").strip() or "—"


def _format_user_answer(qa_item, response):
    if is_choice_scored_item(qa_item):
        letter = format_choice_response_answer_display(qa_item, response)
        return _mcq_choice_text_for_letter(qa_item, letter)
    text = (response.transcript_text or response.response_text or "").strip()
    return _truncate_text(text, 200) if text else "—"


def _format_correctness_status(qa_item, response):
    if is_choice_scored_item(qa_item):
        return format_choice_correctness_label(response.is_correct)
    return open_response_status_label(response.is_correct)


def _iso_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def list_participants_dashboard(db):
    participants = db.scalars(select(Participant).order_by(Participant.created_at.desc())).all()
    participant_ids = [participant.id for participant in participants]
    response_stats = _participant_response_stats(db, participant_ids)

    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.participant_id.in_(participant_ids))
        .options(selectinload(Assignment.qa_item))
        .order_by(Assignment.assigned_at.desc())
    ).all()
    sessions = db.scalars(
        select(ParticipantSession)
        .where(ParticipantSession.participant_id.in_(participant_ids))
        .options(
            selectinload(ParticipantSession.current_assignment).selectinload(Assignment.qa_item)
        )
    ).all()

    assignments_by_participant = {participant_id: [] for participant_id in participant_ids}
    for assignment in assignments:
        assignments_by_participant.setdefault(assignment.participant_id, []).append(assignment)

    sessions_by_participant = {
        participant_session.participant_id: participant_session
        for participant_session in sessions
    }

    rows = []
    for participant in participants:
        participant_session = sessions_by_participant.get(participant.id)
        session_state, current_question = _build_current_work_summary(participant_session)
        stats = response_stats.get(
            participant.id,
            {"total": 0, "correct": 0, "incorrect": 0, "under_review": 0},
        )
        rows.append(
            {
                "id": participant.id,
                "participant_id": participant.id,
                "display_name": participant.display_name or "",
                "language": participant.target_language or "",
                "session_state": session_state,
                "current_question": current_question,
                "assigned_questions": _build_assigned_questions_summary(
                    assignments_by_participant.get(participant.id, [])
                ),
                "questions_completed": stats["total"],
                "correct": stats["correct"],
                "incorrect": stats["incorrect"],
                "under_review": stats["under_review"],
                "batch_size": participant.preferred_batch_size,
                "last_seen": format_display_datetime(participant.last_seen_at),
                "consented": participant.consented,
            }
        )

    return {"participants": rows}


def get_participant_detail(db, participant_id: str):
    participant = db.scalar(
        select(Participant)
        .where(Participant.id == participant_id)
        .options(
            selectinload(Participant.session)
            .selectinload(ParticipantSession.current_assignment)
            .selectinload(Assignment.qa_item)
        )
    )
    if not participant:
        return None

    responses = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.participant_id == participant_id)
        .options(selectinload(ParticipantResponse.qa_item))
        .order_by(ParticipantResponse.received_at.desc())
    ).all()
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.participant_id == participant_id)
        .options(
            selectinload(Assignment.qa_item),
            selectinload(Assignment.passage_translation),
        )
        .order_by(Assignment.assigned_at.desc())
    ).all()
    stats = _participant_response_stats(db, [participant_id]).get(
        participant_id,
        {"total": 0, "correct": 0, "incorrect": 0, "under_review": 0},
    )
    session_state, current_question = _build_current_work_summary(participant.session)

    history = []
    for response in responses:
        qa_item = response.qa_item
        if not qa_item:
            continue
        history.append(
            {
                "qa_item_id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id or "",
                "question": _truncate_text(qa_item.question_text, 100),
                "question_type": (qa_item.question_type or "open").strip().lower(),
                "expected_answer": _format_expected_answer(qa_item),
                "user_answer": _format_user_answer(qa_item, response),
                "correctness_status": _format_correctness_status(qa_item, response),
            }
        )

    assigned_questions = []
    for assignment in assignments:
        qa_item = assignment.qa_item
        if not qa_item:
            continue
        translation = assignment.passage_translation
        assigned_questions.append(
            {
                "assignment_id": assignment.id,
                "qa_item_id": qa_item.id,
                "passage": qa_item.passage_reference or qa_item.passage_id or "",
                "question": _truncate_text(qa_item.question_text, 100),
                "translation_name": translation.name if translation else None,
                "passage_verse_numbers": list(assignment.passage_verse_numbers or []),
                "batch_id": assignment.batch_id,
                "status": assignment.status,
                "assigned_at": _iso_datetime(assignment.assigned_at),
            }
        )

    return {
        "participant": {
            "id": participant.id,
            "participant_id": participant.id,
            "display_name": participant.display_name or "",
            "language": participant.target_language or "",
            "session_state": session_state,
            "current_question": current_question or None,
            "assigned_questions": _build_assigned_questions_summary(assignments) or None,
            "questions_completed": stats["total"],
            "correct": stats["correct"],
            "incorrect": stats["incorrect"],
            "under_review": stats["under_review"],
            "batch_size": participant.preferred_batch_size,
            "last_seen": format_display_datetime(participant.last_seen_at),
            "consented": participant.consented,
            "created_at": _iso_datetime(participant.created_at),
        },
        "assigned_questions": assigned_questions,
        "history": history,
    }


def update_participant_language(db, participant_id: str, language_value):
    participant = db.get(Participant, participant_id)
    if not participant:
        raise ParticipantMutationError("Participant not found")

    language = canonical_language_code(language_value)
    if not language:
        raise ParticipantMutationError("Language is required")

    participant.target_language = language
    upsert_system_language(db, language, source="participant")
    db.flush()
    return participant
