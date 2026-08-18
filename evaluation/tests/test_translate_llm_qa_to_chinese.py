import unittest

from evaluation.scripts.data_prep.translate_llm_qa_to_chinese import normalize_items


class NormalizeAllFormatsTests(unittest.TestCase):
    def test_mcq_uses_option_aligned_stem_instead_of_top_level_question(self):
        source = {
            "content_id": "t1_example:item",
            "question": "How did Sunor rescue Raygo?",
            "open": {
                "question_type": "open",
                "original_question": "How did Sunor rescue Raygo?",
                "original_answer": "He killed Doneth.",
            },
            "mcq": {
                "question_type": "multiple_choice",
                "mcq_stem": "Whom did Sunor kill to rescue Raygo?",
                "mcq_options": ["A giant", "Doneth", "Gudos", "Gevur"],
                "content": "<answer>B<answer>",
            },
        }

        open_item, mcq_item = normalize_items([source])

        self.assertEqual(open_item["Q"], "How did Sunor rescue Raygo?")
        self.assertEqual(mcq_item["Q"], "Whom did Sunor kill to rescue Raygo?")
        self.assertEqual(mcq_item["passage_id"], "uw-t1_example:item-mcq")
        self.assertEqual(mcq_item["correct"], "B")

    def test_compact_translated_q_still_has_highest_precedence(self):
        item = {
            "q_type": "mcq",
            "Q": "弗斯为了救芮谷，杀了谁？",
            "mcq_stem": "Whom did Sunor kill to rescue Raygo?",
            "question": "How did Sunor rescue Raygo?",
            "A": {"A": "甲", "B": "塞达", "C": "丙", "D": "丁"},
            "correct": "B",
        }

        [normalized] = normalize_items([item])

        self.assertEqual(normalized["Q"], "弗斯为了救芮谷，杀了谁？")


if __name__ == "__main__":
    unittest.main()
