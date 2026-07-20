import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.passage_list_service import list_passage_items
from eten_shared.models import PassageTranslation, PassageVerse


class PassageListServiceTests(unittest.TestCase):
    def test_lists_each_translation_chapter_with_available_verses(self):
        engine = create_engine("sqlite://")
        PassageTranslation.__table__.create(engine)
        PassageVerse.__table__.create(engine)

        with Session(engine) as db:
            translation = PassageTranslation(language="cmn", name="Method X")
            db.add(translation)
            db.flush()
            db.add_all(
                [
                    PassageVerse(
                        translation_id=translation.id,
                        chapter_number=2,
                        verse_number="1",
                        position=1,
                        text="第一节",
                    ),
                    PassageVerse(
                        translation_id=translation.id,
                        chapter_number=2,
                        verse_number="3",
                        position=2,
                        text="第三节",
                    ),
                ]
            )
            db.flush()

            self.assertEqual(
                list_passage_items(db),
                [
                    {
                        "id": translation.id,
                        "language": "cmn",
                        "translation_name": "Method X",
                        "chapter_number": 2,
                        "verse_count": 2,
                        "verses": "1, 3",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
