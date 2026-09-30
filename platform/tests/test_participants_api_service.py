import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.admin.services.participants_api_service import (
    get_participant_detail,
    list_participants_dashboard,
)
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Base,
    ExperimentPassage,
    ExperimentPlanCell,
    Participant,
    ParticipantResponse,
    QAItem,
)


class ParticipantsApiServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def test_completed_question_leaves_assigned_list_and_enters_history(self):
        with Session(self.engine) as db:
            participant = Participant(display_name="Participant")
            open_question = QAItem(
                passage_id="luke1",
                passage_reference="1:1",
                question_text="Open question",
                expected_answer="Open answer",
            )
            completed_question = QAItem(
                passage_id="luke1",
                passage_reference="1:2",
                question_text="Completed question",
                expected_answer="Completed answer",
            )
            db.add_all([participant, open_question, completed_question])
            db.flush()

            open_assignment = Assignment(
                participant_id=participant.id,
                qa_item_id=open_question.id,
                status=AssignmentStatus.ASSIGNED.value,
            )
            completed_assignment = Assignment(
                participant_id=participant.id,
                qa_item_id=completed_question.id,
                status=AssignmentStatus.COMPLETED.value,
            )
            db.add_all([open_assignment, completed_assignment])
            db.flush()
            db.add(
                ParticipantResponse(
                    participant_id=participant.id,
                    qa_item_id=completed_question.id,
                    assignment_id=completed_assignment.id,
                    response_text="Participant answer",
                )
            )
            db.commit()

            payload = get_participant_detail(db, participant.id)

            self.assertEqual(
                [row["question"] for row in payload["assigned_questions"]],
                ["Open question"],
            )
            self.assertEqual(
                [row["question"] for row in payload["history"]],
                ["Completed question"],
            )

    def test_passage_metadata_preserves_snapshot_and_filters_reference_language(self):
        with Session(self.engine) as db:
            participant = Participant(display_name="Reader", target_language="en")
            question = QAItem(passage_id="source", question_text="Question", expected_answer="Answer", passage_text="Wrong fallback")
            db.add_all([participant, question])
            db.flush()
            cell = ExperimentPlanCell(
                participant_id=participant.id, chapter=1, sequence_index=0,
                condition="omission30",
            )
            db.add(cell)
            for condition, language, text in [
                ("clean", "en", "Clean reference"),
                ("omission30", "en", "Updated omission reference"),
                ("grammar30", "en", "Grammar reference"),
                ("clean", "zh", "Other language"),
            ]:
                db.add(ExperimentPassage(
                    source_passage_id="source", chapter=1, condition=condition,
                    language=language, passage_text=text,
                ))
            db.flush()
            assignment = Assignment(
                participant_id=participant.id, qa_item_id=question.id,
                experiment_cell_id=cell.id, passage_text="1 Original served text",
                passage_verse_numbers=["1"],
            )
            db.add(assignment)
            db.commit()
            metadata = get_participant_detail(db, participant.id)["assigned_questions"][0]["metadata"]
            self.assertEqual(metadata["served_passage"], "Original served text")
            self.assertEqual(metadata["clean_passage"], "Clean reference")
            self.assertEqual(metadata["defect_type"], "omission")
            self.assertEqual(metadata["defect_rate"], 0.30)
            self.assertEqual(
                {row["condition"] for row in metadata["passage_variants"]},
                {"omission30", "grammar30"},
            )
            assignment.status = AssignmentStatus.COMPLETED.value
            db.add(ParticipantResponse(
                participant_id=participant.id, qa_item_id=question.id,
                assignment_id=assignment.id, response_text="Answer",
            ))
            db.commit()
            self.assertEqual(get_participant_detail(db, participant.id)["history"][0]["metadata"], metadata)
            assignment.passage_text = None
            db.commit()
            self.assertIsNone(get_participant_detail(db, participant.id)["history"][0]["metadata"]["served_passage"])

    def test_score_buckets_count_auto_scored_and_partial_answers(self):
        labels = (
            ["yes (auto)", "yes (expert)"]
            + ["no (auto)", "No (Auto)", "no (expert)"]
            + ["partial (auto)", "partial (auto)"]
            + ["pending", None, "unexpected label"]
        )
        with Session(self.engine) as db:
            participant = Participant(display_name="Scored")
            db.add(participant)
            db.flush()
            for label in labels:
                db.add(
                    ParticipantResponse(
                        participant_id=participant.id,
                        qa_item_id="qa",
                        is_correct=label,
                    )
                )
            db.commit()

            expected = {
                "questions_completed": 10,
                "correct": 2,
                "incorrect": 3,
                "partial": 2,
                "under_review": 3,
            }
            detail = get_participant_detail(db, participant.id)["participant"]
            (row,) = list_participants_dashboard(db)["participants"]
            for key, value in expected.items():
                self.assertEqual(detail[key], value, key)
                self.assertEqual(row[key], value, key)


if __name__ == "__main__":
    unittest.main()
