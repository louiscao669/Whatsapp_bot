"""Dashboard serialization services."""

from ._common import *  # noqa: F401,F403

def _iso_datetime(value):
    return value.isoformat() if value else None


def _luke_chapter_from_reference(passage_reference):
    # Admin-authored QA commonly uses "Luke 1:11" while the evaluation/pilot
    # importer uses "1:11" (and occasionally "1:35(#2)"). Both identify the
    # same dashboard chapter and must be visible to regular participants.
    match = re.match(
        r"^(?:luke\s+)?(?P<chapter>\d+):\d+(?:\(#\d+\))?",
        str(passage_reference or "").strip(),
        re.IGNORECASE,
    )
    return int(match.group("chapter")) if match else None


def _choice_text_for_letter(qa_item, letter):
    normalized = (letter or "").strip().upper()
    choices = list(qa_item.mcq_choices or [])
    if not normalized or len(normalized) != 1:
        return ""
    index = ord(normalized) - ord("A")
    if index < 0 or index >= len(choices):
        return ""
    return str(choices[index] or "").strip()


def _format_choice_answer(qa_item, letter):
    normalized = (letter or "").strip().upper()
    text = _choice_text_for_letter(qa_item, normalized)
    if normalized and text:
        return f"{normalized}. {text}"
    return normalized or "No answer recorded"


def _latest_answer_recording(db, qa_item, participant):
    language = participant_language_code(participant)
    statement = select(QAItemRecording).where(
        QAItemRecording.qa_item_id == qa_item.id,
        QAItemRecording.recording_type == "answer",
        func.lower(QAItemRecording.language) == language.lower(),
    )
    if is_choice_scored_item(qa_item):
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        if correct_letter:
            statement = statement.where(
                QAItemRecording.version == ord(correct_letter) - ord("A") + 1
            )
    return db.scalars(
        statement.order_by(
            QAItemRecording.version.desc(),
            QAItemRecording.created_at.desc(),
        )
    ).first()


def _latest_question_audio_url(db, qa_item, participant):
    language = participant_language_code(participant)
    recording = get_latest_question_recording(db, qa_item.id, language)
    if recording:
        return f"/user-dashboard/api/{participant.id}/qa-question-recording/{recording.id}/audio"
    return qa_item.audio_url


def _serialize_dashboard_question(
    db,
    participant,
    assignment,
    qa_item,
    *,
    question_index=0,
):
    chapter_number = _luke_chapter_from_reference(qa_item.passage_reference)
    return {
        "assignment_id": assignment.id,
        "batch_id": assignment.batch_id,
        "question_index": max(int(question_index or 0), 0),
        "chapter": chapter_number,
        "chapter_label": f"Chapter {chapter_number}" if chapter_number else None,
        "passage_reference": qa_item.passage_reference,
        "passage_text": assignment_passage_snapshot(assignment)
        or surrounding_passage_text(db, assignment)
        or qa_item.passage_text,
        "question": qa_item.question_text,
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "mcq_choices": list(qa_item.mcq_choices or []),
        "audio_url": _latest_question_audio_url(db, qa_item, participant),
        "status": "current",
    }


def _serialize_completed_question_review(db, participant, assignment, qa_item):
    response = db.scalars(
        select(ParticipantResponse)
        .where(ParticipantResponse.assignment_id == assignment.id)
        .order_by(ParticipantResponse.received_at.desc(), ParticipantResponse.id.desc())
    ).first()
    if not response:
        return None

    choice_scored = is_choice_scored_item(qa_item)
    if choice_scored:
        user_letter = (response.response_text or "").strip().upper()
        correct_letter = (qa_item.mcq_correct_choice or "").strip().upper()
        participant_answer = _format_choice_answer(qa_item, user_letter)
        correct_answer = _format_choice_answer(qa_item, correct_letter)
        correctness = format_choice_correctness_label(response.is_correct)
    else:
        participant_answer = (
            response.transcript_text or response.response_text or ""
        ).strip() or "No answer recorded"
        correct_answer = (qa_item.expected_answer or "").strip() or "No answer recorded"
        correctness = open_response_status_label(response.is_correct)

    response_audio_url = (
        f"/user-dashboard/api/{participant.id}/participant-response/{response.id}/audio"
        if (response.media_url or "").strip()
        else None
    )
    correct_recording = _latest_answer_recording(db, qa_item, participant)
    return {
        "question": qa_item.question_text,
        "passage_reference": qa_item.passage_reference,
        "question_type": (qa_item.question_type or "open").strip().lower(),
        "participant_answer": participant_answer,
        "participant_audio_url": response_audio_url,
        "correct_answer": correct_answer,
        "correct_audio_url": (
            f"/user-dashboard/api/{participant.id}/qa-answer-recording/{correct_recording.id}/audio"
            if correct_recording
            else None
        ),
        "correctness": correctness,
        "submitted_at": _iso_datetime(response.received_at),
    }


