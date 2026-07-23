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
from app.services.participant_assignment_service import (
    NEW_ASSIGNMENT_ASSIGNED_NOTIFICATION,
)
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Base,
    OutboxNotification,
    OutboxStatus,
    Participant,
    ParticipantSession,
    ExperimentPassage,
    ExperimentPassageVerse,
    PassageTranslation,
    PassageVerse,
    QAItem,
)
from eten_shared.domain.assignments import (
    automatic_assignment_enabled,
    experiment_passage_assignment_kwargs,
)


class ParticipantAssignmentServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def test_parses_qa_reference(self):
        self.assertEqual(parse_qa_chapter_verse("Luke 2:4"), (2, 4))
        self.assertEqual(parse_qa_chapter_verse("2:4"), (2, 4))
        self.assertEqual(parse_qa_chapter_verse("1:35(#2)"), (1, 35))
        self.assertIsNone(parse_qa_chapter_verse("Unknown passage"))

    def test_experiment_passage_links_qa_to_referenced_verse(self):
        with Session(self.engine) as db:
            passage = ExperimentPassage(
                chapter=2,
                condition="omission10",
                language="zh",
                passage_text="完整章节后备文本",
            )
            db.add(passage)
            db.flush()
            db.add_all(
                [
                    ExperimentPassageVerse(
                        experiment_passage_id=passage.id,
                        verse_number=str(number),
                        position=number,
                        text=f"第{number}节",
                    )
                    for number in range(2, 7)
                ]
            )
            db.flush()
            qa_item = QAItem(
                passage_id="luke2",
                passage_reference="Luke 2:4",
                question_text="问题",
            )

            result = experiment_passage_assignment_kwargs(db, passage, qa_item)

            self.assertEqual(result["passage_chapter_number"], 2)
            self.assertEqual(result["passage_verse_numbers"], ["4"])
            self.assertEqual(
                result["passage_text"], "第2节 第3节 第4节 第5节 第6节"
            )

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

    def _seed_one_translated_question(self, db, participant):
        qa_item = QAItem(
            passage_id="luke-2-4",
            passage_reference="Luke 2:4",
            question_text="Question?",
            expected_answer="Answer",
        )
        translation = PassageTranslation(language="cmn", name="Method X")
        db.add_all([qa_item, translation])
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
        return qa_item, translation

    def test_enqueues_outbox_push_when_new_batch_becomes_current(self):
        with Session(self.engine) as db:
            participant = Participant(target_language="cmn", display_name="Tester")
            db.add(participant)
            db.flush()
            qa_item, translation = self._seed_one_translated_question(db, participant)

            assignments = assign_questions_with_passages(
                db,
                participant.id,
                [{"qa_item_id": qa_item.id, "translation_id": translation.id}],
            )

            pending = db.scalars(
                select(OutboxNotification).where(
                    OutboxNotification.participant_id == participant.id,
                    OutboxNotification.status == OutboxStatus.PENDING.value,
                )
            ).all()
            self.assertEqual(len(pending), 1)
            self.assertEqual(
                pending[0].notification_type, NEW_ASSIGNMENT_ASSIGNED_NOTIFICATION
            )
            self.assertEqual(pending[0].payload["assignment_id"], assignments[0].id)
            self.assertEqual(pending[0].payload["assigned_count"], 1)

    def test_second_assignment_supersedes_stale_push(self):
        with Session(self.engine) as db:
            participant = Participant(target_language="cmn", display_name="Tester")
            db.add(participant)
            db.flush()
            qa_item, translation = self._seed_one_translated_question(db, participant)
            extra = QAItem(
                passage_id="luke-2-5",
                passage_reference="Luke 2:5",
                question_text="Question 2?",
                expected_answer="Answer 2",
            )
            db.add(extra)
            db.flush()

            first = assign_questions_with_passages(
                db,
                participant.id,
                [{"qa_item_id": qa_item.id, "translation_id": translation.id}],
            )
            # Complete the first so the next assignment becomes current again and
            # re-enqueues; the still-pending first push should be superseded so
            # only one pending row remains.
            first[0].status = AssignmentStatus.COMPLETED.value
            db.flush()
            assign_questions_with_passages(
                db,
                participant.id,
                [{"qa_item_id": extra.id, "translation_id": translation.id}],
            )

            rows = db.scalars(
                select(OutboxNotification).where(
                    OutboxNotification.participant_id == participant.id
                )
            ).all()
            pending = [r for r in rows if r.status == OutboxStatus.PENDING.value]
            superseded = [r for r in rows if r.status == OutboxStatus.SUPERSEDED.value]
            self.assertEqual(len(pending), 1)
            self.assertEqual(len(superseded), 1)

    def test_no_push_when_new_batch_is_queued_behind_open_assignment(self):
        with Session(self.engine) as db:
            participant = Participant(
                target_language="cmn", display_name="Tester", preferred_batch_size=1
            )
            db.add(participant)
            db.flush()
            qa_item, translation = self._seed_one_translated_question(db, participant)
            extra = QAItem(
                passage_id="luke-2-5",
                passage_reference="Luke 2:5",
                question_text="Question 2?",
                expected_answer="Answer 2",
            )
            db.add(extra)
            db.flush()

            # First assignment becomes current (1 push). It stays open (never
            # completed), so a second assignment queues behind it: no new push.
            assign_questions_with_passages(
                db,
                participant.id,
                [{"qa_item_id": qa_item.id, "translation_id": translation.id}],
            )
            assign_questions_with_passages(
                db,
                participant.id,
                [{"qa_item_id": extra.id, "translation_id": translation.id}],
            )

            pending = db.scalars(
                select(OutboxNotification).where(
                    OutboxNotification.participant_id == participant.id,
                    OutboxNotification.status == OutboxStatus.PENDING.value,
                )
            ).all()
            self.assertEqual(len(pending), 1)


if __name__ == "__main__":
    unittest.main()
