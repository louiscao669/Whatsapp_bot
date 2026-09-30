import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.admin.services.qa_item_detail_service import get_qa_item_overview
from eten_shared.models import Base, ExperimentPassage, ExperimentPassageVerse, ExperimentWindow, QAItem


class QaItemPassageVariantsTests(unittest.TestCase):
    def test_overview_includes_clean_and_all_variants_without_qa_passage_text(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            question = QAItem(passage_id='source', question_text='Why?', expected_answer='Answer')
            db.add(question)
            for source, condition, language in [
                ('source', 'clean', 'zh'), ('source', 'omission30', 'zh'),
                ('source', 'grammar30', 'zh'), ('source', 'clean', 'en'),
                ('unrelated', 'clean', 'zh'),
            ]:
                db.add(ExperimentPassage(
                    source_passage_id=source, chapter=1, condition=condition,
                    language=language, passage_text=f'{language} {condition}',
                ))
            db.flush()
            overview = get_qa_item_overview(db, question.id)
            self.assertIsNone(overview['passage_text'])
            variants = overview['passage_variants']
            self.assertEqual(len(variants), 4)
            self.assertEqual([v['condition'] for v in variants if v['language'] == 'zh'],
                             ['clean', 'grammar30', 'omission30'])
            self.assertEqual(variants[-1]['defect_rate'], 0.3)
            self.assertTrue(all(v['passage_text'] and not v['is_window'] for v in variants))

    def test_window_uses_delivery_padding_and_keeps_full_passage(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            question = QAItem(passage_id='source', question_text='Why?', expected_answer='Answer')
            db.add(question)
            db.flush()
            db.add(ExperimentWindow(
                qa_item_id=question.id, source_passage_id='source', content_id='content',
                window_key='1-3', group_index=1, sequence_index=0,
                verse_numbers=['1', '2', '3'], window_ordinals=[1, 2, 3],
            ))
            for condition, numbers in [('clean', [1, 2, 3, 4]), ('omission30', [1, 3, 4])]:
                passage = ExperimentPassage(source_passage_id='source', chapter=1,
                    condition=condition, language='zh', passage_text=f'Full {condition}')
                db.add(passage)
                db.flush()
                for number in numbers:
                    db.add(ExperimentPassageVerse(experiment_passage_id=passage.id,
                        verse_number=str(number), position=number, text=f'Verse {number}'))
            db.flush()
            clean, omission = get_qa_item_overview(db, question.id)['passage_variants']
            self.assertEqual(clean['passage_text'], 'Verse 1 Verse 2 Verse 3')
            self.assertEqual(omission['passage_text'], 'Verse 1 Verse 3 Verse 4')
            self.assertEqual(omission['full_passage_text'], 'Full omission30')
            self.assertEqual(omission['verse_numbers'], ['1', '3', '4'])
            self.assertTrue(omission['is_window'])


if __name__ == '__main__':
    unittest.main()
