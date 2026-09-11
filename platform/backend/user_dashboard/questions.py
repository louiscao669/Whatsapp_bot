"""Dashboard questions services."""

from ._common import *  # noqa: F401,F403

def submit_dashboard_answer(db, participant_id: str, assignment_id: str, response_text: str):
    from .profile import _participant_by_id
    from .rewards import _award_dashboard_currency
    from .engagement import _enqueue_outbox_notification
    from .store import _get_or_create_wallet
    from .scheduling import _schedule_dashboard_next_batch
    from .serialization import _serialize_dashboard_question
    from backend.shared.assignment_selection import select_next_participant_qa_item
    from backend.shared.assignment_selection import experiment_assignment_kwargs

    assignment_id = (assignment_id or "").strip()
    answer_text = (response_text or "").strip()
    if not assignment_id:
        raise DashboardAnswerError("Assignment is required")
    if not answer_text:
        raise DashboardAnswerError("Answer is required")

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")

    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.participant_id != participant.id:
        raise DashboardAnswerError("Assignment not found")
    if assignment.status == AssignmentStatus.COMPLETED.value:
        raise DashboardAnswerError("This question is already answered")

    qa_item = assignment.qa_item or db.get(QAItem, assignment.qa_item_id)
    if not qa_item:
        raise DashboardAnswerError("Question not found")

    # Race guard: atomically claim the assignment; the first surface
    # (dashboard or messenger) to complete it wins.
    if not try_complete_assignment(db, assignment):
        raise DashboardAnswerError("This question is already answered")

    participant_session = get_or_create_participant_session(db, participant)
    participant_session.current_assignment_id = assignment.id
    participant_session.current_batch_id = assignment.batch_id
    participant_session.state = SessionState.AWAITING_RESPONSE.value

    normalized_text = None
    correctness_score = None
    matched_keywords = []
    missing_keywords = []
    flag_reason = None
    needs_expert_review = False
    stored_response_text = answer_text
    backtranslated_text = None
    scoring_metadata = {}

    mcq_needs_llm_resolution = False
    if is_choice_scored_item(qa_item):
        # Dashboard replies are usually button taps, so the letter parses and
        # this is the exact-match path. Free-text entry still gets the same
        # fallback as the bot -- the two channels must score identically.
        parsed_letter = choice_response_letter(qa_item, answer_text)
        if parsed_letter is not None:
            stored_response_text = parsed_letter
            choice_correct = choice_response_is_correct(qa_item, answer_text)
            is_correct_label = "yes (auto)" if choice_correct else "no (auto)"
            review_status = ReviewStatus.AUTO.value
        elif llm_answer_scoring_enabled() and (answer_text or "").strip():
            mcq_needs_llm_resolution = True
            is_correct_label = "pending"
            review_status = ReviewStatus.PENDING.value
            flag_reason = "MCQ choice resolution queued."
            scoring_metadata = {"method": "llm_choice_resolution", "status": "queued"}
        else:
            is_correct_label = "pending"
            review_status = ReviewStatus.PENDING.value
            flag_reason = "Pending: MCQ reply did not resolve to a choice."
            scoring_metadata = {"method": "none", "status": "unusable_reply"}
    else:
        # [2026-08-12] Keyword scoring removed here too -- this is the dashboard
        # twin of the message-bot ingest path, and the two must agree or the
        # same answer scores differently depending on the channel it arrived on
        # (source_channel is a pilot covariate, so that would be a real
        # confound). Open answers are LLM-judged only; see workflow.py.
        normalized_text = normalize_response_text(answer_text)
        correctness_score = None
        needs_expert_review = True
        is_correct_label = "pending"
        review_status = ReviewStatus.PENDING.value
        if llm_answer_scoring_enabled():
            flag_reason = "LLM scoring queued."
            scoring_metadata = {
                "method": "backtranslation_llm_judge",
                "scale": "0/0.5/1",
                "status": "queued",
            }
        else:
            flag_reason = (
                "Pending expert review: LLM answer scoring is disabled "
                "(set ENABLE_LLM_ANSWER_SCORING)."
            )
            scoring_metadata = {"method": "none", "status": "scorer_disabled"}

    response = ParticipantResponse(
        participant_id=participant.id,
        qa_item_id=qa_item.id,
        assignment_id=assignment.id,
        response_type=ResponseType.TEXT.value,
        response_text=stored_response_text,
        normalized_text=normalized_text,
        backtranslated_text=backtranslated_text,
        scoring_metadata=scoring_metadata,
        correctness_score=correctness_score,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        is_correct=is_correct_label,
        flag_reason=flag_reason,
        review_status=review_status,
        source_channel=SourceChannel.USER_DASHBOARD.value,
        # Only a cleanly-parsed choice has a verdict at ingest; everything else
        # stays NULL until the outbox scorer writes one back.
        scored_at=utc_now() if review_status == ReviewStatus.AUTO.value else None,
    )
    db.add(response)
    db.flush()
    if not is_choice_scored_item(qa_item) and llm_answer_scoring_enabled():
        _enqueue_outbox_notification(
            db, participant, ANSWER_LLM_SCORE_REQUESTED_NOTIFICATION,
            {"response_id": response.id},
        )
    elif mcq_needs_llm_resolution:
        _enqueue_outbox_notification(
            db, participant, MCQ_CHOICE_RESOLUTION_REQUESTED_NOTIFICATION,
            {"response_id": response.id},
        )

    now = utc_now()
    # status/completed_at/attempt_count were set atomically by
    # try_complete_assignment above; keep the started_at backfill as a
    # fallback for assignments never marked viewed.
    assignment.started_at = assignment.started_at or assignment.completed_at or now
    participant.completed_count = (participant.completed_count or 0) + 1
    participant.last_seen_at = now
    participant_session.current_assignment_id = None
    participant_session.state = SessionState.IDLE.value

    record_participant_event(
        db,
        participant,
        "response_recorded",
        {
            "assignment_id": assignment.id,
            "qa_item_id": qa_item.id,
            "response_type": ResponseType.TEXT.value,
            "correctness_score": correctness_score,
            "is_correct": is_correct_label,
            "choice_scored": is_choice_scored_item(qa_item),
            "question_type": qa_item.question_type,
            "source_surface": "user_dashboard",
        },
        source="user_dashboard",
    )
    db.flush()

    response_amount = (
        FIRST_ANSWER_COMPLETED_DIAMONDS
        if (participant.completed_count or 0) == 1
        else ANSWER_COMPLETED_DIAMONDS
    )
    _award_dashboard_currency(
        db,
        participant,
        response_amount,
        "answer_completed",
        assignment_id=assignment.id,
        response_id=response.id,
        metadata={
            "qa_item_id": qa_item.id,
            "response_type": response.response_type,
            "first_answer_bonus": response_amount == FIRST_ANSWER_COMPLETED_DIAMONDS,
        },
    )
    update_streak_for_response(db, participant, response)

    batch_completed, completed_batch_size = complete_current_batch_if_needed(
        db,
        participant,
        participant_session,
    )
    next_assignment_id = None
    next_question = None
    if batch_completed:
        _schedule_dashboard_next_batch(db, participant)
        batch_event = db.scalars(
            select(ParticipantEvent)
            .where(
                ParticipantEvent.participant_id == participant.id,
                ParticipantEvent.event_type == "batch_completed",
            )
            .order_by(ParticipantEvent.created_at.desc(), ParticipantEvent.id.desc())
        ).first()
        _award_dashboard_currency(
            db,
            participant,
            BATCH_COMPLETED_BONUS_DIAMONDS,
            "batch_completed_bonus",
            source_event_id=batch_event.id if batch_event else assignment.batch_id,
            metadata={
                "batch_id": assignment.batch_id,
                "completed_batch_size": completed_batch_size,
            },
        )
    else:
        participant_session.current_batch_id = assignment.batch_id
        next_assignment = (
            db.get(Assignment, assignment.next_assignment_id)
            if assignment.next_assignment_id
            else None
        )
        if not (
            next_assignment
            and next_assignment.participant_id == participant.id
            and next_assignment.batch_id == participant_session.current_batch_id
            and next_assignment.status == AssignmentStatus.ASSIGNED.value
        ):
            next_assignment = db.scalar(
                select(Assignment)
                .where(
                    Assignment.participant_id == participant.id,
                    Assignment.batch_id == participant_session.current_batch_id,
                    Assignment.status == AssignmentStatus.ASSIGNED.value,
                )
                .order_by(Assignment.assigned_at, Assignment.id)
            )
        if next_assignment:
            next_qa_item = db.get(QAItem, next_assignment.qa_item_id)
            if next_qa_item:
                participant_session.current_assignment_id = next_assignment.id
                participant_session.state = SessionState.AWAITING_RESPONSE.value
                participant_session.last_prompt_sent_at = utc_now()
                next_assignment_id = next_assignment.id
                next_question = _serialize_dashboard_question(
                    db,
                    participant,
                    next_assignment,
                    next_qa_item,
                    question_index=completed_batch_size,
                )
        else:
            next_qa_item, next_cell = (
                select_next_participant_qa_item(db, participant)
                if (automatic_assignment_enabled() or experiment_assignment_enabled())
                else (None, None)
            )
        if not next_assignment and next_qa_item:
            next_prompt = create_assignment_for_qa_item(
                db,
                participant,
                participant_session,
                next_qa_item,
                completed_batch_size=completed_batch_size,
                assignment_source="user_dashboard",
                **experiment_assignment_kwargs(
                    db, participant_session, next_cell, next_qa_item
                ),
            )
            next_assignment_id = next_prompt.assignment_id if next_prompt else None
            if next_assignment_id:
                next_assignment = db.get(Assignment, next_assignment_id)
                next_question = _serialize_dashboard_question(
                    db,
                    participant,
                    next_assignment,
                    next_qa_item,
                    question_index=completed_batch_size,
                )
        elif not next_assignment:
            participant_session.state = SessionState.IDLE.value

    _enqueue_outbox_notification(
        db,
        participant,
        DASHBOARD_ANSWER_SYNCED_NOTIFICATION,
        {
            "response_id": response.id,
            "assignment_id": assignment.id,
            "qa_item_id": qa_item.id,
            "batch_id": assignment.batch_id,
            "batch_completed": batch_completed,
            "completed_batch_size": completed_batch_size,
            "next_assignment_id": next_assignment_id,
        },
    )

    db.flush()
    wallet = _get_or_create_wallet(db, participant)
    return {
        "answer_submission": {
            "assignment_id": assignment.id,
            "response_id": response.id,
            "batch_id": assignment.batch_id,
            "batch_completed": batch_completed,
            "completed_batch_size": completed_batch_size,
            "next_assignment_id": next_assignment_id,
            "is_correct": is_correct_label,
        },
        "next_question": next_question,
        "wallet": {
            "balance": wallet.balance,
        },
        "awards": {
            "answer": response_amount,
            "batch_completed": BATCH_COMPLETED_BONUS_DIAMONDS if batch_completed else 0,
        },
    }


def submit_dashboard_answer_receipt(
    db,
    participant_id: str,
    assignment_id: str,
    response_text: str,
    submission_id: str,
):
    """Fast dashboard intake: commit the immutable receipt, return cached next."""
    from .profile import _participant_by_id
    from .serialization import _serialize_dashboard_question


    assignment_id = (assignment_id or "").strip()
    answer_text = (response_text or "").strip()
    submission_id = (submission_id or "").strip()
    if not assignment_id:
        raise DashboardAnswerError("Assignment is required")
    if not answer_text:
        raise DashboardAnswerError("Answer is required")
    if not submission_id:
        raise DashboardAnswerError("Submission ID is required")
    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")
    assignment = db.get(Assignment, assignment_id)
    if not assignment or assignment.participant_id != participant.id:
        raise DashboardAnswerError("Assignment not found")
    qa_item = assignment.qa_item or db.get(QAItem, assignment.qa_item_id)
    if not qa_item:
        raise DashboardAnswerError("Question not found")
    if is_choice_scored_item(qa_item):
        valid_letters = choice_letters_for_type(question_type_value(qa_item))
        if answer_text.upper() not in valid_letters:
            letters = ", ".join(valid_letters[:-1]) + f", or {valid_letters[-1]}"
            raise DashboardAnswerError(f"Wrong answer format. Choose {letters}.")
    try:
        receipt, _created = create_answer_receipt(
            db,
            participant_id=participant.id,
            assignment=assignment,
            provider=SourceChannel.USER_DASHBOARD.value,
            provider_update_id=submission_id,
            response_type=ResponseType.TEXT.value,
            raw_answer=answer_text,
        )
    except ValueError as exc:
        raise DashboardAnswerError(str(exc)) from exc

    next_assignment = db.get(Assignment, assignment.next_assignment_id) \
        if assignment.next_assignment_id else None
    next_question = None
    if next_assignment and next_assignment.status == AssignmentStatus.ASSIGNED.value:
        next_qa_item = next_assignment.qa_item or db.get(QAItem, next_assignment.qa_item_id)
        if next_qa_item:
            next_question = _serialize_dashboard_question(
                db, participant, next_assignment, next_qa_item, question_index=0
            )
    wallet = db.scalar(
        select(ParticipantWallet).where(ParticipantWallet.participant_id == participant.id)
    )
    return {
        "answer_submission": {
            "assignment_id": assignment.id,
            "response_id": None,
            "receipt_id": receipt.id,
            "batch_id": assignment.batch_id,
            "batch_completed": False,
            "completed_batch_size": 0,
            "next_assignment_id": next_assignment.id if next_assignment else None,
            "is_correct": "pending",
        },
        "next_question": next_question,
        "wallet": {"balance": wallet.balance if wallet else 0},
        "awards": {"answer": 0, "batch_completed": 0},
    }


def expire_dashboard_question(db, participant_id: str, assignment_id: str):
    """Expire an unanswered dashboard question and return its successor."""
    from .profile import _participant_by_id
    from .serialization import _serialize_dashboard_question

    from backend.admin.services.participant_assignment_service import skip_participant_assignment

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")
    assignment = db.get(Assignment, (assignment_id or "").strip())
    if not assignment or assignment.participant_id != participant.id:
        raise DashboardAnswerError("Assignment not found")
    if assignment.status == AssignmentStatus.COMPLETED.value:
        raise DashboardAnswerError("This question is already answered")
    if assignment.status == AssignmentStatus.EXPIRED.value:
        raise DashboardAnswerError("This question has already expired")

    skip_participant_assignment(db, participant.id, assignment.id)
    assignment.status = AssignmentStatus.EXPIRED.value
    participant_session = get_or_create_participant_session(db, participant)
    next_assignment = (
        db.get(Assignment, participant_session.current_assignment_id)
        if participant_session.current_assignment_id
        else None
    )
    next_question = None
    if next_assignment and next_assignment.status == AssignmentStatus.ASSIGNED.value:
        next_qa_item = next_assignment.qa_item or db.get(QAItem, next_assignment.qa_item_id)
        if next_qa_item:
            next_question = _serialize_dashboard_question(
                db, participant, next_assignment, next_qa_item, question_index=0
            )
    db.flush()
    return {
        "expired_assignment_id": assignment.id,
        "next_assignment_id": next_assignment.id if next_assignment else None,
        "next_question": next_question,
    }


def start_dashboard_new_batch(db, participant_id: str):
    from .profile import _participant_by_id
    from .scheduling import _assign_dashboard_next_batch
    from .payload import get_user_dashboard_payload

    participant = _participant_by_id(db, participant_id)
    if not participant:
        raise DashboardAnswerError("Participant not found")
    _assign_dashboard_next_batch(db, participant, source="manual")
    return get_user_dashboard_payload(db, participant_id)


