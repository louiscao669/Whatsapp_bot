import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.engagement.outbox as outbox
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Base,
    OutboxNotification,
    OutboxStatus,
    Participant,
    ParticipantSession,
    QAItem,
)


class OutboxNewAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _seed(self, db, *, with_open_assignment=True):
        participant = Participant(target_language="cmn", display_name="Tester")
        db.add(participant)
        db.flush()
        assignment_id = None
        if with_open_assignment:
            qa_item = QAItem(
                passage_id="luke-2-4",
                passage_reference="Luke 2:4",
                question_text="Question?",
                expected_answer="Answer",
            )
            db.add(qa_item)
            db.flush()
            assignment = Assignment(
                participant_id=participant.id,
                qa_item_id=qa_item.id,
                status=AssignmentStatus.ASSIGNED.value,
            )
            db.add(assignment)
            db.flush()
            assignment_id = assignment.id
        db.add(
            ParticipantSession(
                participant_id=participant.id,
                current_assignment_id=assignment_id,
            )
        )
        db.add(
            OutboxNotification(
                participant_id=participant.id,
                notification_type=outbox.NEW_ASSIGNMENT_ASSIGNED_TYPE,
                payload={"assigned_count": 1, "assignment_id": assignment_id},
                status=OutboxStatus.PENDING.value,
            )
        )
        db.commit()
        return participant.id, assignment_id

    def test_delivers_new_assignment_prompt(self):
        with self.Session() as db:
            participant_id, assignment_id = self._seed(db, with_open_assignment=True)

        sent_texts = []
        sent_prompts = []
        with patch.object(outbox, "get_session_factory", return_value=self.Session), \
            patch.object(outbox, "provider_name_for_participant", return_value="telegram"), \
            patch.object(outbox, "build_assignment_prompt", return_value="PROMPT"), \
            patch.object(
                outbox, "send_text_message",
                side_effect=lambda db, p, text: sent_texts.append(text),
            ), \
            patch.object(
                outbox, "send_provider_assignment_prompt",
                side_effect=lambda db, p, prompt: sent_prompts.append(prompt),
            ):
            processed = outbox.process_pending_outbox()

        self.assertEqual(processed, 1)
        self.assertEqual(sent_texts, ["You have a new question to answer:"])
        self.assertEqual(sent_prompts, ["PROMPT"])
        with self.Session() as db:
            notification = db.scalar(select(OutboxNotification))
            self.assertEqual(notification.status, OutboxStatus.SENT.value)
            assignment = db.get(Assignment, assignment_id)
            self.assertIsNotNone(assignment.started_at)

    def test_cancels_when_no_open_assignment(self):
        with self.Session() as db:
            self._seed(db, with_open_assignment=False)

        sent_texts = []
        with patch.object(outbox, "get_session_factory", return_value=self.Session), \
            patch.object(outbox, "provider_name_for_participant", return_value="telegram"), \
            patch.object(
                outbox, "send_text_message",
                side_effect=lambda db, p, text: sent_texts.append(text),
            ), \
            patch.object(outbox, "send_provider_assignment_prompt") as send_prompt:
            processed = outbox.process_pending_outbox()

        self.assertEqual(processed, 0)
        self.assertEqual(sent_texts, [])
        send_prompt.assert_not_called()
        with self.Session() as db:
            notification = db.scalar(select(OutboxNotification))
            self.assertEqual(notification.status, OutboxStatus.CANCELLED.value)


if __name__ == "__main__":
    unittest.main()
