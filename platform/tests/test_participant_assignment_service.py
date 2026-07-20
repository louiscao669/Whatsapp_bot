import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.services.participant_assignment_service import (
    assign_questions_with_passages,
    get_assignment_options,
    parse_qa_chapter_verse,
    qa_reference_sort_key,
)
from eten_shared.models import (
    Assignment,
    Base,
    Participant,
    ParticipantSession,
    PassageTranslation,
    PassageVerse,
    QAItem,
)
from eten_shared.domain.assignments import automatic_assignment_enabled


class ParticipantAssignmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def test_parses_qa_reference(self):
        self.assertEqual(parse_qa_chapter_verse("Luke 2:4"), (2, 4))
        self.assertIsNone(parse_qa_chapter_verse("Unknown passage"))

    def test_sorts_qa_references_by_numeric_chapter_and_verse(self):
        items = [
            QAItem(id="68", passage_id="luke-1-68", passage_reference="Luke 1:68"),
            QAItem(id="7", passage_id="luke-1-7", passage_reference="Luke 1:7"),
            QAItem(id="2", passage_id="luke-2-1", passage_reference="Luke 2:1"),
        ]

        ordered = sorted(items, key=qa_reference_sort_key)

        self.assertEqual([item.passage_reference for item in ordered], [
            "Luke 1:7",
            "Luke 1:68",
            "Luke 2:1",
        ])

    def test_automatic_assignment_is_disabled_by_default_and_can_be_enabled(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(automatic_assignment_enabled())
        with patch.dict("os.environ", {"ENABLE_AUTOMATIC_ASSIGNMENT": "true"}):
            self.assertTrue(automatic_assignment_enabled())

    def test_assigns_selected_translation_and_five_verse_window(self):
        with Session(self.engine) as db:
            participant = Participant(target_language="cmn", display_name="Tester")
            qa_item = QAItem(
                passage_id="luke-2-4",
                passage_reference="Luke 2:4",
                question_text="Question?",
                expected_answer="Answer",
            )
            translation = PassageTranslation(language="cmn", name="Method X")
            db.add_all([participant, qa_item, translation])
            db.flush()
            db.add_all(
                PassageVerse(
                    translation_id=translation.id,
                    chapter_number=2,
                    verse_number=str(number),
                    position=number,
                    text=f"Verse {number}",
                )
                for number in range(1, 8)
            )
            db.flush()

            options = get_assignment_options(db, participant.id)
            self.assertEqual(options["questions"][0]["translations"][0]["name"], "Method X")

            assignments = assign_questions_with_passages(
                db,
                participant.id,
                [{"qa_item_id": qa_item.id, "translation_id": translation.id}],
            )
            assignment = assignments[0]
            self.assertEqual(assignment.passage_translation_id, translation.id)
            self.assertEqual(assignment.passage_chapter_number, 2)
            self.assertEqual(assignment.passage_verse_numbers, ["2", "3", "4", "5", "6"])
            self.assertIn("4 Verse 4", assignment.passage_text)

            queued_qa_items = [
                QAItem(
                    passage_id=f"luke-2-{number}",
                    passage_reference=f"Luke 2:{number}",
                    question_text=f"Question {number}?",
                    expected_answer=f"Answer {number}",
                )
                for number in (5, 6, 2, 3)
            ]
            db.add_all(queued_qa_items)
            db.flush()
            filled_current_batch = assign_questions_with_passages(
                db,
                participant.id,
                [
                    {"qa_item_id": qa.id, "translation_id": translation.id}
                    for qa in queued_qa_items[:2]
                ],
            )
            self.assertEqual(
                [queued.batch_id for queued in filled_current_batch],
                [assignment.batch_id, assignment.batch_id],
            )

            next_batch = assign_questions_with_passages(
                db,
                participant.id,
                [
                    {"qa_item_id": qa.id, "translation_id": translation.id}
                    for qa in queued_qa_items[2:]
                ],
            )
            self.assertNotEqual(next_batch[0].batch_id, assignment.batch_id)
            self.assertEqual(next_batch[0].batch_id, next_batch[1].batch_id)

            participant_session = db.scalar(
                select(ParticipantSession).where(
                    ParticipantSession.participant_id == participant.id
                )
            )
            self.assertEqual(participant_session.current_assignment_id, assignment.id)
            self.assertEqual(participant_session.current_batch_id, assignment.batch_id)

            stored = db.scalar(select(Assignment).where(Assignment.id == assignment.id))
            self.assertIsNotNone(stored)


if __name__ == "__main__":
    unittest.main()
