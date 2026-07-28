from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.messaging.workflow import (
    process_pending_answer_receipts,
    record_telegram_answer_receipt,
)
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
                external_user_id="123",
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
