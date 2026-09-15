import unittest

from evaluation.scripts.pipeline.translate_qa import (
    invented_tokens,
    normalize_items,
    protected_tokens,
)


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


class ProtectedTokenGuardTests(unittest.TestCase):
    """The canonical arm carries no placeholders, so any token is an invention.

    The real failure this guards: the translation prompt named __MOST_HIGH_A__
    as an example of a token to preserve, and the model preserved one that was
    never in the source -- "Impossible even if Yahweh helped" came back as
    即使__MOST_HIGH_A__帮助也不可能 and was shown to every answering model.
    """

    def test_finds_tokens_nested_in_mcq_choices(self):
        item = {"q_type": "mcq", "Q": "\u4ec0\u4e48\uff1f",
                "A": {"A": "\u7532", "B": "\u5373\u4f7f__MOST_HIGH_A__\u5e2e\u52a9\u4e5f\u4e0d\u53ef\u80fd"}}
        self.assertEqual(protected_tokens(item), {"__MOST_HIGH_A__"})

    def test_token_absent_from_source_is_invented(self):
        source = {"q_type": "mcq", "Q": "What did the captain say?",
                  "A": {"B": "Impossible even if Yahweh helped"}}
        bad = {"q_type": "mcq", "Q": "\u961f\u957f\u8bf4\u4ec0\u4e48\uff1f",
               "A": {"B": "\u5373\u4f7f__MOST_HIGH_A__\u5e2e\u52a9\u4e5f\u4e0d\u53ef\u80fd"}}
        self.assertEqual(invented_tokens(source, bad), {"__MOST_HIGH_A__"})

    def test_token_carried_through_from_source_is_not_invented(self):
        source = {"q_type": "open", "Q": "Why does __MOST_HIGH_A__ help?"}
        good = {"q_type": "open", "Q": "__MOST_HIGH_A__\u4e3a\u4f55\u5e2e\u52a9\uff1f"}
        self.assertEqual(invented_tokens(source, good), set())

    def test_dropping_a_source_token_is_not_flagged_here(self):
        # Losing a token is a different defect (decanonicalize would leave a
        # bare name); this guard is only about tokens appearing from nowhere.
        source = {"q_type": "open", "Q": "Why does __MOST_HIGH_A__ help?"}
        lossy = {"q_type": "open", "Q": "\u4ed6\u4e3a\u4f55\u5e2e\u52a9\uff1f"}
        self.assertEqual(invented_tokens(source, lossy), set())

    def test_lowercase_and_partial_markers_are_not_tokens(self):
        self.assertEqual(protected_tokens("__person_a__ and _PERSON_A_ and __A"), set())


if __name__ == "__main__":
    unittest.main()
