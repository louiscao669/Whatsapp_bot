"""Question-bank separation and saved-version selection for the admin list."""

from datetime import datetime, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.admin.services.qa_items_list_service import list_qa_items_with_stats, question_bank
from eten_shared.models import Base, ExperimentWindow, QAItem


class QaItemsListTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def item(self, passage, *, day=1, form="mcq", group="same-question", **fields):
        item = QAItem(
            passage_id=passage, passage_reference="2 Kings 6:33–7:2",
            question_text="谁？", expected_answer="Old answer",
            question_type=form, form_group_id=group,
            created_at=datetime(2026, 11, day, tzinfo=timezone.utc), **fields,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def test_same_source_question_in_different_banks_is_current_in_each_bank(self):
        original = self.item("reviewed122/Prepared60/t1_2kgs6_7")
        old = self.item("reviewed122_sol/Prepared60/t1_2kgs6_7")
        current = self.item(old.passage_id, day=2)
        scratch = self.item("reviewed122_sol/Hard77/t1_2kgs6_7")
        rows = {row["id"]: row for row in list_qa_items_with_stats(self.db)}
        self.assertEqual(len({rows[q.id]["bank_id"] for q in (original, current, scratch)}), 3)
        self.assertTrue(all(rows[q.id]["is_current"] for q in (original, current, scratch)))
        self.assertFalse(rows[old.id]["is_current"])
        self.assertEqual(len(rows), 4)  # Retain history instead of deleting records.

    def test_delivery_window_wins_over_newer_unused_revision_and_active_flag(self):
        linked = self.item("reviewed122_sol/Prepared60/t1_2kgs6_7", active=False)
        draft = self.item(linked.passage_id, day=2, active=True)
        self.db.add(ExperimentWindow(
            qa_item_id=linked.id, source_passage_id=linked.passage_id,
            content_id=linked.form_group_id, window_key="6:33|7:1|7:2",
            group_index=301, sequence_index=1, verse_numbers=[], window_ordinals=[],
        ))
        self.db.flush()
        rows = {row["id"]: row for row in list_qa_items_with_stats(self.db)}
        self.assertTrue(rows[linked.id]["is_current"])
        self.assertFalse(rows[draft.id]["is_current"])

    def test_distinct_forms_and_ungrouped_questions_are_not_hidden_as_revisions(self):
        mcq = self.item("t1_2kgs6_7")
        opened = self.item(mcq.passage_id, form="open", day=2)
        ungrouped = [self.item(mcq.passage_id, group=None, day=day) for day in (3, 4)]
        rows = list_qa_items_with_stats(self.db)
        self.assertEqual({row["id"] for row in rows if row["is_current"]},
                         {mcq.id, opened.id, *(q.id for q in ungrouped)})

    def test_search_payload_uses_keyed_option_and_keeps_other_options(self):
        mcq = self.item("t1_2kgs6_7", mcq_choices=["母亲", "撒迦利亚", "国王"],
                        mcq_correct_choice="B")
        opened = self.item(mcq.passage_id, form="open")
        rows = {row["id"]: row for row in list_qa_items_with_stats(self.db)}
        self.assertEqual(rows[mcq.id]["answer"], "撒迦利亚")
        self.assertEqual(rows[mcq.id]["mcq_choices"], ["母亲", "撒迦利亚", "国王"])
        self.assertEqual(rows[opened.id]["answer"], "Old answer")
        self.assertEqual(mcq.expected_answer, "Old answer")
        self.assertFalse(self.db.dirty)

    def test_known_and_unrecognized_banks_keep_distinct_labels(self):
        self.assertEqual(question_bank("hard66/t1_judg9"), ("hard66", "Strong-66"))
        self.assertEqual(question_bank("t1_judg9"), ("gold72", "Gold-72 · prepared"))
        self.assertNotEqual(question_bank("custom-one/ch1")[0], question_bank("custom-two/ch1")[0])


if __name__ == "__main__":
    unittest.main()
