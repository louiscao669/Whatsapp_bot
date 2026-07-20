import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eten_shared.models import PassageTranslation, PassageVerse
from app.services.passage_import_service import (
    PassageImportError,
    import_passage_translation,
    parse_numbered_verses,
)


class ParseNumberedVersesTests(unittest.TestCase):
    def test_parses_supported_markers(self):
        verses = parse_numbered_verses(
            "1 First verse\n2. Second verse\n[3] Third verse\n\\v 4 Fourth verse"
        )

        self.assertEqual([verse.number for verse in verses], ["1", "2", "3", "4"])
        self.assertEqual(verses[0].text, "Firstverse")
        self.assertEqual(verses[3].text, "Fourthverse")

    def test_parses_inline_verses_and_appends_unnumbered_lines(self):
        verses = parse_numbered_verses(
            "引言\n1 第一节，含有角色02。2 第二节。3 第三节。\n另一个标题\n4 第四节。"
        )

        self.assertEqual([verse.number for verse in verses], ["1", "2", "3", "4"])
        self.assertEqual(verses[0].text, "第一节，含有角色02。")
        self.assertEqual(verses[1].text, "第二节。")
        self.assertEqual(verses[2].text, "第三节。 另一个标题")

    def test_appends_unnumbered_lines_to_preceding_verse(self):
        verses = parse_numbered_verses("1 First verse\ncontinued text\n2 Second verse")

        self.assertEqual(
            [verse.text for verse in verses],
            ["Firstversecontinuedtext", "Secondverse"],
        )

    def test_ignores_header_lines(self):
        verses = parse_numbered_verses(
            "<header>Opening\n1 First verse\n<header>Section title\n2 Second verse"
        )

        self.assertEqual([verse.text for verse in verses], ["Firstverse", "Secondverse"])

    def test_keeps_inline_verse_after_continuation_prefix(self):
        verses = parse_numbered_verses(
            "1 First verse\ncontinued text 2 Second verse"
        )

        self.assertEqual(
            [(verse.number, verse.text) for verse in verses],
            [("1", "Firstversecontinuedtext"), ("2", "Secondverse")],
        )

    def test_parses_inline_verse_after_punctuation_and_closing_quote(self):
        verses = parse_numbered_verses(
            "63 他写着：“他的名字是约翰。”64 随即他的口开通。65 邻居们都惊奇。"
        )

        self.assertEqual([verse.number for verse in verses], ["63", "64", "65"])
        self.assertEqual(verses[0].text, "他写着：“他的名字是约翰。”")
        self.assertEqual(verses[1].text, "随即他的口开通。")

    def test_removes_word_spaces_but_keeps_one_space_after_punctuation(self):
        verses = parse_numbered_verses(
            "1 一次 什么时候，   撒迦利亚 分配。 下一句"
        )

        self.assertEqual(verses[0].text, "一次什么时候， 撒迦利亚分配。 下一句")

    def test_rejects_duplicate_verse_numbers(self):
        with self.assertRaisesRegex(PassageImportError, "appears more than once"):
            parse_numbered_verses("1 First\n1 Duplicate")


class ImportPassageTranslationTests(unittest.TestCase):
    def test_requires_positive_integer_chapter_number(self):
        for chapter_number in (None, "", "0", "-1", "1.5"):
            with self.subTest(chapter_number=chapter_number):
                with self.assertRaisesRegex(PassageImportError, "positive integer"):
                    import_passage_translation(
                        None,
                        source_text="1 Verse",
                        language="eng",
                        chapter_number=chapter_number,
                    )

    def test_reimport_replaces_matching_verses_and_merges_new_ones(self):
        engine = create_engine("sqlite://")
        PassageTranslation.__table__.create(engine)
        PassageVerse.__table__.create(engine)

        with Session(engine) as db:
            first_translation, _ = import_passage_translation(
                db,
                source_text="1 Original one\n3 Original three",
                language="eng",
                chapter_number=4,
                name="Method X",
            )
            db.commit()

            second_translation, _ = import_passage_translation(
                db,
                source_text="1 Replacement one\n2 New two",
                language="eng",
                chapter_number=4,
                name="Method X",
            )
            db.commit()

            self.assertEqual(second_translation.id, first_translation.id)
            stored = db.scalars(
                select(PassageVerse)
                .where(PassageVerse.translation_id == first_translation.id)
                .order_by(PassageVerse.position)
            ).all()
            self.assertEqual(
                [(verse.verse_number, verse.text) for verse in stored],
                [("1", "Replacementone"), ("2", "Newtwo"), ("3", "Originalthree")],
            )


if __name__ == "__main__":
    unittest.main()
