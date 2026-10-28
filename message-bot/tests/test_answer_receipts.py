from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.messaging.workflow import (
    mcq_answer_format_error,
    process_pending_answer_receipts,
    record_telegram_answer_receipt,
)
from eten_shared.participant_identity import blind_index
from eten_shared.models import (
    AnswerReceipt,
    Assignment,
    AssignmentStatus,
    Base,
    Participant,
    ParticipantProviderContact,
    ParticipantResponse,
    ParticipantSession,
    QAItem,
    SessionState,
    utc_now,
)


def test_receipt_is_minimal_deduplicated_and_projected():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as db:
        participant = Participant(display_name="Tester", target_language="eng")
        first_qa = QAItem(
            passage_id="p1", question_text="First?", expected_answer="First"
        )
        second_qa = QAItem(
            passage_id="p2", question_text="Second?", expected_answer="Second"
        )
        db.add_all([participant, first_qa, second_qa])
        db.flush()
        first = Assignment(
            participant_id=participant.id,
            qa_item_id=first_qa.id,
            batch_id="batch",
            passage_text="Passage one",
            delivered_at=utc_now(),
        )
        second = Assignment(
            participant_id=participant.id,
            qa_item_id=second_qa.id,
            batch_id="batch",
            passage_text="Passage two",
        )
        db.add_all([first, second])
        db.flush()
        first.next_assignment_id = second.id
        db.add_all([
            ParticipantProviderContact(
                participant_id=participant.id,
                provider="telegram",
                external_user_id=blind_index("telegram", "123"),
            ),
            ParticipantSession(
                participant_id=participant.id,
                current_assignment_id=first.id,
                current_batch_id="batch",
                state=SessionState.AWAITING_RESPONSE.value,
            ),
        ])
        db.commit()
        first_id, second_id, participant_id = first.id, second.id, participant.id

    with patch("app.messaging.workflow.get_session_factory", return_value=factory):
        result = record_telegram_answer_receipt(
            chat_id="123",
            display_name="Tester",
            update_id="update-1",
            assignment_id=first_id,
            raw_answer="my answer",
        )
        duplicate = record_telegram_answer_receipt(
            chat_id="123",
            display_name="Tester",
            update_id="update-1",
            assignment_id=first_id,
            raw_answer="my answer",
        )

        with Session(engine) as db:
            assert db.get(Assignment, first_id).status == AssignmentStatus.ASSIGNED.value
            assert len(db.scalars(select(AnswerReceipt)).all()) == 1
            assert len(db.scalars(select(ParticipantResponse)).all()) == 0
        assert result.prompt.assignment_id == second_id
        assert duplicate.status_message == "This question was already answered."

        assert process_pending_answer_receipts() == 1

    with Session(engine) as db:
        assert db.get(Assignment, first_id).status == AssignmentStatus.COMPLETED.value
        response = db.scalar(select(ParticipantResponse))
        assert response.assignment_id == first_id
        assert response.qa_item_id is not None
        assert response.response_text == "my answer"
        receipt = db.scalar(select(AnswerReceipt))
        assert receipt.status == "processed"
        assert receipt.response_id == response.id
        session = db.scalar(
            select(ParticipantSession).where(
                ParticipantSession.participant_id == participant_id
            )
        )
        assert session.current_assignment_id == second_id


def test_greeting_does_not_create_answer_receipt():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as db:
        participant = Participant(display_name="Tester", target_language="eng")
        question = QAItem(
            passage_id="p1", question_text="Question?", expected_answer="Answer"
        )
        db.add_all([participant, question])
        db.flush()
        assignment = Assignment(
            participant_id=participant.id,
            qa_item_id=question.id,
            batch_id="batch",
            passage_text="Passage",
        )
        db.add(assignment)
        db.flush()
        db.add_all([
            ParticipantProviderContact(
                participant_id=participant.id,
                provider="telegram",
                external_user_id=blind_index("telegram", "456"),
            ),
            ParticipantSession(
                participant_id=participant.id,
                current_assignment_id=assignment.id,
                current_batch_id="batch",
                state=SessionState.AWAITING_RESPONSE.value,
            ),
        ])
        db.commit()
        assignment_id = assignment.id

    with patch("app.messaging.workflow.get_session_factory", return_value=factory):
        premature = record_telegram_answer_receipt(
            chat_id="456",
            display_name="Tester",
            update_id="premature-1",
            assignment_id=assignment_id,
            raw_answer="an answer sent too early",
        )
        with Session(engine) as db:
            db.get(Assignment, assignment_id).delivered_at = utc_now()
            db.commit()
        result = record_telegram_answer_receipt(
            chat_id="456",
            display_name="Tester",
            update_id="greeting-1",
            assignment_id=assignment_id,
            raw_answer="Hi!",
        )

    assert premature.status_message.startswith("No question has been delivered")
    assert result.prompt.assignment_id == assignment_id
    with Session(engine) as db:
        assert db.scalar(select(AnswerReceipt)) is None
        assert db.get(Assignment, assignment_id).status == AssignmentStatus.ASSIGNED.value


def test_mcq_requires_a_strict_choice_letter_or_callback_value():
    question = QAItem(
        passage_id="mcq",
        question_text="Choose",
        question_type="mcq",
        mcq_choices=["One", "Two", "Three", "Four"],
        mcq_correct_choice="A",
        expected_answer="One",
    )
    assert mcq_answer_format_error(question, "A") is None
    assert mcq_answer_format_error(question, "d") is None
    assert mcq_answer_format_error(question, "mcq_2") is None
    assert mcq_answer_format_error(question, "One") is not None
    assert mcq_answer_format_error(question, "hello") is not None


def test_exact_mcq_letter_records_its_scoring_method():
    """Regression (2026-10-26 hard66 run): an MCQ scored by exact letter wrote no
    scoring metadata, so every pilot MCQ showed a blank scoring method."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as db:
        participant = Participant(display_name="Pilot", target_language="zh")
        items = [
            QAItem(
                passage_id=f"p{n}",
                question_text="Who?",
                expected_answer="Two",
                question_type="mcq",
                mcq_choices=["One", "Two", "Three", "Four", "Cannot tell"],
                mcq_correct_choice="B",
            )
            for n in (1, 2)
        ]
        db.add_all([participant, *items])
        db.flush()
        right = Assignment(participant_id=participant.id, qa_item_id=items[0].id,
                           batch_id="pilot", passage_text="P", delivered_at=utc_now())
        wrong = Assignment(participant_id=participant.id, qa_item_id=items[1].id,
                           batch_id="pilot", passage_text="P", delivered_at=utc_now())
        db.add_all([right, wrong, ParticipantSession(participant_id=participant.id,
                                                     state=SessionState.IDLE.value)])
        db.flush()
        for assignment, letter in ((right, "B"), (wrong, "E")):
            db.add(AnswerReceipt(
                participant_id=participant.id, assignment_id=assignment.id,
                qa_item_id=assignment.qa_item_id, provider="pilot",
                provider_update_id=f"sub-{letter}", response_type="text",
                raw_answer=letter,
            ))
        db.commit()
        right_id, wrong_id = right.id, wrong.id

    with patch("app.messaging.workflow.get_session_factory", return_value=factory):
        assert process_pending_answer_receipts() == 2

    with Session(engine) as db:
        by_assignment = {
            r.assignment_id: r for r in db.scalars(select(ParticipantResponse)).all()
        }
        for assignment_id, label, letter in (
            (right_id, "yes (auto)", "B"),
            (wrong_id, "no (auto)", "E"),
        ):
            response = by_assignment[assignment_id]
            assert response.is_correct == label
            assert response.scoring_metadata["method"] == "exact_letter"
            assert response.scoring_metadata["scale"] == "0/1"
            assert response.scoring_metadata["letter"] == letter


def test_designed_assignment_serves_next_question_after_answer():
    """Pilot assignment has no pre-built successor: the bot must fetch the next one."""
    from app.messaging.workflow import (
        TELEGRAM_PLAN_COMPLETE_MESSAGE,
        WorkflowResult,
        next_prompt_after_telegram_receipt,
    )

    accepted = WorkflowResult(participant_id="p", session_id="s", session_state="idle",
                              response_id="r1", prompt=None)
    follow = WorkflowResult(participant_id="p", session_id="s", session_state="idle")
    with patch("app.messaging.workflow.process_pending_answer_receipts") as drain, \
         patch("app.messaging.workflow.record_telegram_text_message", return_value=follow) as ask, \
         patch("app.messaging.workflow.experiment_assignment_enabled", return_value=True):
        result = next_prompt_after_telegram_receipt("123", None, accepted)
    drain.assert_called_once()
    assert ask.call_args.kwargs["record_response"] is False
    assert result.status_message == TELEGRAM_PLAN_COMPLETE_MESSAGE

    # A prepared successor, a duplicate tap, or no receipt: nothing extra to send.
    with_successor = WorkflowResult(participant_id="p", session_id="s", session_state="x",
                                    response_id="r1", prompt=object())
    duplicate = WorkflowResult(participant_id="p", session_id="s", session_state="x",
                               response_id="r1", status_message="This question was already answered.")
    for result in (with_successor, duplicate, None):
        assert next_prompt_after_telegram_receipt("123", None, result) is None
