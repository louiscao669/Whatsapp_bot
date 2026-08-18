import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.user_dashboard.service import expire_dashboard_question
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Base,
    Participant,
    ParticipantSession,
    QAItem,
    SessionState,
)


class DashboardQuestionTimerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def test_expiry_advances_to_next_question_without_recording_answer(self):
        with Session(self.engine) as db:
            participant = Participant(display_name="Timed participant")
            first_item = QAItem(
                passage_id="luke1",
                passage_reference="1:1",
                question_text="First?",
                expected_answer="First",
            )
            second_item = QAItem(
                passage_id="luke1",
                passage_reference="1:2",
                question_text="Second?",
                expected_answer="Second",
            )
            db.add_all([participant, first_item, second_item])
            db.flush()
            first = Assignment(
                participant_id=participant.id,
                qa_item_id=first_item.id,
                batch_id="batch",
            )
            second = Assignment(
                participant_id=participant.id,
                qa_item_id=second_item.id,
                batch_id="batch",
            )
            db.add_all([first, second])
            db.flush()
            first.next_assignment_id = second.id
            db.add(
                ParticipantSession(
                    participant_id=participant.id,
                    current_assignment_id=first.id,
                    current_batch_id="batch",
                    state=SessionState.AWAITING_RESPONSE.value,
                )
            )
            db.flush()

            payload = expire_dashboard_question(db, participant.id, first.id)

            self.assertEqual(first.status, AssignmentStatus.EXPIRED.value)
            self.assertEqual(payload["next_assignment_id"], second.id)
            self.assertEqual(payload["next_question"]["question"], "Second?")
            self.assertEqual(participant.session.current_assignment_id, second.id)


if __name__ == "__main__":
    unittest.main()
