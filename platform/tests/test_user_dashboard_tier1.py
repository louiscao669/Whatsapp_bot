"""The participant dashboard shows tier-1 study questions, not only Luke.

Before 2026-10-28 the journey kept only references that parsed as Luke
("Luke 1:11" / "1:11"), so a participant holding tier-1 assignments (Judges,
Kings, Acts, ...) got an empty path, the frontend drew a placeholder, and
tapping it said "This question is not ready yet."

Also covers the IRB guard that comes with it: for study (non-Luke) items the
dashboard never reveals correctness or the answer key (protocol 26-08-10268:
accuracy is never shown), while the stored verdict is unchanged.
"""

import unittest
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.user_dashboard.journey import (
    get_luke_chapter_activity,
    get_luke_journey_chapters,
)
from backend.user_dashboard.questions import submit_dashboard_answer
from backend.user_dashboard.serialization import (
    answer_feedback_hidden,
    dashboard_book_chapter,
)
from eten_shared.models import (
    Assignment,
    AssignmentStatus,
    Base,
    Participant,
    ParticipantResponse,
    QAItem,
)


def _item(reference, passage_id):
    return SimpleNamespace(passage_reference=reference, passage_id=passage_id)


class BookChapterTests(unittest.TestCase):
    def test_tier1_references(self):
        self.assertEqual(
            dashboard_book_chapter(_item("Judges 9:1-57", "t1_judg9")),
            ("judges", 9, "Judges 9"),
        )
        self.assertEqual(
            dashboard_book_chapter(_item("1 Kings 13:1-34", "uw-t1_1kgs13:abcd-mcq")),
            ("1 kings", 13, "1 Kings 13"),
        )
        self.assertEqual(
            dashboard_book_chapter(_item("Acts 19:11-20", "hard66/t1_acts19")),
            ("acts", 19, "Acts 19"),
        )
        self.assertEqual(
            dashboard_book_chapter(_item("2 Chronicles 26:1-23", "t1_2chr26")),
            ("2 chronicles", 26, "2 Chronicles 26"),
        )

    def test_passage_spanning_two_chapters_is_labelled_as_a_range(self):
        self.assertEqual(
            dashboard_book_chapter(_item("Judges 17:1-18:31", "t1_judg17_18")),
            ("judges", 17, "Judges 17–18"),
        )
        self.assertEqual(
            dashboard_book_chapter(_item("2 Kings 6:24-7:20", "t1_2kgs6_7")),
            ("2 kings", 6, "2 Kings 6–7"),
        )

    def test_legacy_luke_references_unchanged(self):
        self.assertEqual(dashboard_book_chapter(_item("Luke 1:11", "luke1")), ("luke", 1, "Luke 1"))
        self.assertEqual(dashboard_book_chapter(_item("1:11", "luke1")), ("luke", 1, "Luke 1"))
        self.assertEqual(dashboard_book_chapter(_item("1:35(#2)", "opaque")), ("luke", 1, "Luke 1"))

    def test_bare_reference_takes_book_from_passage_id(self):
        # Judges 9 must not be filed under Luke 9.
        self.assertEqual(
            dashboard_book_chapter(_item("9:5", "hard66/t1_judg9")),
            ("judges", 9, "Judges 9"),
        )

    def test_unknown_reference(self):
        self.assertIsNone(dashboard_book_chapter(_item("Unknown passage", "opaque")))

    def test_feedback_hidden_only_for_study_books(self):
        self.assertTrue(answer_feedback_hidden(_item("Judges 9:1-57", "t1_judg9")))
        self.assertTrue(answer_feedback_hidden(_item("Acts 23:12-35", "t1_acts23")))
        self.assertFalse(answer_feedback_hidden(_item("Luke 1:11", "luke1")))
        self.assertFalse(answer_feedback_hidden(_item("1:11", "luke1")))
        self.assertFalse(answer_feedback_hidden(_item("Unknown passage", "opaque")))


class DashboardJourneyTier1Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.participant = Participant(display_name="Tier-1 participant")
        self.judges_mcq = QAItem(
            passage_id="t1_judg9",
            passage_reference="Judges 9:1-57",
            question_text="Who was made king at Shechem?",
            question_type="mcq",
            mcq_choices=["Abimelech", "Jotham", "Gaal", "Zebul"],
            mcq_correct_choice="A",
            expected_answer="Abimelech",
        )
        self.acts_open = QAItem(
            passage_id="t1_acts20",
            passage_reference="Acts 20:7-12",
            question_text="Who fell from the window?",
            question_type="open",
            expected_answer="Eutychus",
        )
        self.luke_mcq = QAItem(
            passage_id="luke1",
            passage_reference="Luke 1:11",
            question_text="Who appeared to Zechariah?",
            question_type="mcq",
            mcq_choices=["An angel", "Mary", "Elizabeth", "John"],
            mcq_correct_choice="A",
            expected_answer="An angel",
        )
        self.db.add_all([self.participant, self.judges_mcq, self.acts_open, self.luke_mcq])
        self.db.flush()

    def tearDown(self):
        self.db.close()

    def _assign(self, qa_item, batch_id="batch-1"):
        assignment = Assignment(
            participant_id=self.participant.id,
            qa_item_id=qa_item.id,
            batch_id=batch_id,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def _questions(self):
        chapters = get_luke_journey_chapters(self.db, self.participant.id)
        self.assertEqual(len(chapters), 1)
        return [
            question
            for batch in chapters[0]["batches"]
            for question in batch["questions"]
        ]

    def test_refresh_recovers_missing_successor_once(self):
        from unittest.mock import patch
        from backend.user_dashboard.scheduling import _resume_unfinished_dashboard_batch
        first = self._assign(self.judges_mcq)
        first.status = AssignmentStatus.COMPLETED.value
        self.db.flush()
        with patch("backend.user_dashboard.scheduling.automatic_assignment_enabled", return_value=True), patch(
            "backend.shared.assignment_selection.select_next_participant_qa_item",
            return_value=(self.acts_open, None),
        ):
            result = _resume_unfinished_dashboard_batch(self.db, self.participant)
            self.assertIsNotNone(result)
            self.assertEqual(self.db.get(Assignment, result.assignment_id).batch_id, first.batch_id)
            self.assertEqual(first.next_assignment_id, result.assignment_id)
            self.assertIsNone(_resume_unfinished_dashboard_batch(self.db, self.participant))

    def test_short_historical_batch_does_not_lock_next_batch(self):
        first = self._assign(self.judges_mcq, "old-batch")
        first.status = AssignmentStatus.COMPLETED.value
        second = self._assign(self.acts_open, "new-batch")
        self.db.flush()
        batches = get_luke_journey_chapters(self.db, self.participant.id)[0]["batches"]
        self.assertEqual(batches[0]["status"], "complete")
        self.assertEqual(batches[1]["status"], "active")
        self.assertEqual(batches[1]["questions"][0]["assignment_id"], second.id)
        self.assertEqual(batches[1]["questions"][0]["status"], "current")

    def test_answer_persists_successor_for_reload_and_retry(self):
        first = self._assign(self.judges_mcq)
        second = self._assign(self.acts_open)
        result = submit_dashboard_answer(self.db, self.participant.id, first.id, "A")
        self.assertEqual(result["next_question"]["assignment_id"], second.id)
        self.db.flush()
        self.db.expire_all()
        self.assertEqual(self.db.get(Assignment, first.id).next_assignment_id, second.id)

    def test_tier1_assignments_appear_on_the_path_and_can_be_opened(self):
        first = self._assign(self.judges_mcq)
        second = self._assign(self.acts_open)

        questions = self._questions()
        real = [q for q in questions if not q.get("placeholder")]

        self.assertEqual([q["assignment_id"] for q in real], [first.id, second.id])
        # The "current" node is a real assignment, so tapping it opens it.
        current = [q for q in questions if q["status"] == "current"]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["assignment_id"], first.id)
        self.assertEqual(real[0]["chapter_label"], "Judges 9")
        self.assertEqual(real[0]["book"], "Judges")
        self.assertEqual(real[1]["chapter_label"], "Acts 20")

    def test_no_assignments_still_returns_empty(self):
        self.assertEqual(get_luke_journey_chapters(self.db, self.participant.id), [])

    def test_tier1_submit_hides_verdict_but_stores_it(self):
        assignment = self._assign(self.judges_mcq)
        self._assign(self.acts_open)

        payload = submit_dashboard_answer(self.db, self.participant.id, assignment.id, "A")

        self.assertIsNone(payload["answer_submission"]["is_correct"])
        response = self.db.scalars(
            select(ParticipantResponse).where(ParticipantResponse.assignment_id == assignment.id)
        ).one()
        self.assertEqual(response.is_correct, "yes (auto)")
        self.assertEqual(assignment.status, AssignmentStatus.COMPLETED.value)

    def test_luke_submit_still_shows_verdict(self):
        assignment = self._assign(self.luke_mcq)
        payload = submit_dashboard_answer(self.db, self.participant.id, assignment.id, "A")
        self.assertEqual(payload["answer_submission"]["is_correct"], "yes (auto)")

    def test_tier1_completed_review_withholds_answer_key(self):
        assignment = self._assign(self.judges_mcq)
        self._assign(self.acts_open)
        submit_dashboard_answer(self.db, self.participant.id, assignment.id, "B")

        done = [q for q in self._questions() if q["status"] == "complete"]
        self.assertEqual(len(done), 1)
        review = done[0]["review"]
        self.assertTrue(review["feedback_hidden"])
        self.assertIsNone(review["correct_answer"])
        self.assertIsNone(review["correctness"])
        self.assertIsNone(review["correct_audio_url"])
        self.assertIn("Jotham", review["participant_answer"])

    def test_luke_completed_review_keeps_answer_key(self):
        assignment = self._assign(self.luke_mcq)
        submit_dashboard_answer(self.db, self.participant.id, assignment.id, "B")
        review = [q for q in self._questions() if q["status"] == "complete"][0]["review"]
        self.assertFalse(review["feedback_hidden"])
        self.assertIn("An angel", review["correct_answer"])

    def test_activity_grid_uses_study_books(self):
        assignment = self._assign(self.judges_mcq)
        self._assign(self.acts_open)
        submit_dashboard_answer(self.db, self.participant.id, assignment.id, "A")

        activity = get_luke_chapter_activity(self.db, self.participant.id)
        by_label = {cell["label"]: cell for cell in activity}
        self.assertEqual(set(by_label), {"Judges 9", "Acts 20"})
        self.assertEqual(by_label["Judges 9"]["answered_questions"], 1)
        self.assertEqual(by_label["Judges 9"]["book"], "Judges")
        self.assertEqual(by_label["Acts 20"]["answered_questions"], 0)

    def test_activity_grid_luke_only_participant_unchanged(self):
        self._assign(self.luke_mcq)
        activity = get_luke_chapter_activity(self.db, self.participant.id)
        self.assertEqual(len(activity), 24)
        self.assertEqual(activity[0]["label"], "Luke 1")
        self.assertEqual({cell["book"] for cell in activity}, {"Luke"})


if __name__ == "__main__":
    unittest.main()
