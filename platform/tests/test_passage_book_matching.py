"""Regular passage translations are matched to QA items by book, not only chapter:verse."""

import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.admin.services.participant_assignment_service import (
    ParticipantAssignmentError,
    assign_questions_with_passages,
    get_assignment_options,
)
from backend.admin.services.passage_import_service import (
    PassageImportError,
    import_passage_translation,
)
from eten_shared.domain.assignments import automatic_passage_assignment_kwargs
from eten_shared.domain.bible_books import normalize_book, qa_item_book
from eten_shared.models import Base, Participant, PassageTranslation, PassageVerse, QAItem


class BookNormalisationTests(unittest.TestCase):
    def test_reference_and_passage_id_forms(self):
        cases = [
            ("Luke 2:4", "x", "luke"),
            ("Judges 9:1-57", "uw-t1_judg9:w5fv-mcq", "judges"),
            ("2 Kings 6:24-7:20", "t1_2kgs6_7", "2 kings"),
            ("2:4", "luke-2-4", "luke"),
            (None, "hard66/t1_acts19", "acts"),
            ("2:4", "opaque123", None),
        ]
        for reference, passage_id, expected in cases:
            with self.subTest(reference=reference, passage_id=passage_id):
                qa = QAItem(passage_reference=reference, passage_id=passage_id, question_text="?")
                self.assertEqual(qa_item_book(qa), expected)

    def test_aliases(self):
        self.assertEqual(normalize_book("JDG"), "judges")
        self.assertEqual(normalize_book("II Kings"), "2 kings")
        self.assertEqual(normalize_book("1 Sam."), "1 samuel")
        self.assertIsNone(normalize_book("Hezekiah"))


class BookMatchingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(
            self.engine, "connect",
            lambda connection, _record: connection.execute("PRAGMA foreign_keys=ON"),
        )
        Base.metadata.create_all(self.engine)

    def _translation(self, db, name, book, chapter=9):
        translation = PassageTranslation(language="zh", name=name, book=book)
        db.add(translation)
        db.flush()
        db.add_all(
            PassageVerse(translation_id=translation.id, chapter_number=chapter,
                         verse_number=str(n), position=n, text=f"{name} {n}")
            for n in range(1, 8)
        )
        db.flush()
        return translation

    def test_judges_question_is_not_offered_luke_passage(self):
        with Session(self.engine) as db:
            participant = Participant(target_language="zh")
            judges_qa = QAItem(passage_id="uw-t1_judg9:abcd-mcq",
                               passage_reference="Judges 9:4", question_text="J?", expected_answer="a")
            luke_qa = QAItem(passage_id="luke9", passage_reference="Luke 9:4", question_text="L?", expected_answer="a")
            db.add_all([participant, judges_qa, luke_qa])
            db.flush()
            legacy_luke = self._translation(db, "Legacy Luke", None)
            judges = self._translation(db, "Judges zh", "judges")

            options = {q["id"]: [t["id"] for t in q["translations"]]
                       for q in get_assignment_options(db, participant.id)["questions"]}
            self.assertEqual(options[judges_qa.id], [judges.id])
            self.assertEqual(options[luke_qa.id], [legacy_luke.id])

            with self.assertRaisesRegex(ParticipantAssignmentError, "Luke"):
                assign_questions_with_passages(
                    db, participant.id,
                    [{"qa_item_id": judges_qa.id, "translation_id": legacy_luke.id}],
                )

            kwargs = automatic_passage_assignment_kwargs(db, participant, judges_qa)
            self.assertEqual(kwargs["passage_translation_id"], judges.id)

    def test_no_book_reference_keeps_chapter_verse_matching(self):
        with Session(self.engine) as db:
            participant = Participant(target_language="zh")
            qa = QAItem(passage_id="opaque", passage_reference="9:4", question_text="?", expected_answer="a")
            db.add_all([participant, qa])
            db.flush()
            self._translation(db, "A", None)
            self._translation(db, "B", "judges")
            [question] = get_assignment_options(db, participant.id)["questions"]
            self.assertEqual(len(question["translations"]), 2)

    def test_import_stores_book_and_keeps_books_apart(self):
        with Session(self.engine) as db:
            luke, _ = import_passage_translation(
                db, source_text="1 路加", language="zh", chapter_number=9, name="M")
            judges, _ = import_passage_translation(
                db, source_text="1 士师", language="zh", chapter_number=9, name="M2",
                book="Judges")
            self.assertEqual(luke.book, "luke")
            self.assertEqual(judges.book, "judges")
            with self.assertRaisesRegex(PassageImportError, "Unknown book"):
                import_passage_translation(
                    db, source_text="1 x", language="zh", chapter_number=9, book="Narnia")


if __name__ == "__main__":
    unittest.main()
