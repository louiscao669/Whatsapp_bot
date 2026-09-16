"""Five-option MCQs: A-D content options plus one "cannot tell" meta-option on E."""

import unittest
from types import SimpleNamespace

from eten_shared.mcq import (
    choice_letters_for_item,
    choice_response_is_correct,
    choice_response_letter,
    infer_question_type_from_choice_count,
    normalize_labeled_choices,
    parse_choice_lines_from_text,
    validate_question_fields,
)

FOUR = ["bought land", "hired men", "gave alms", "built a temple"]
FIVE = FOUR + ["cannot tell"]


def item(choices, correct="B"):
    return SimpleNamespace(question_type="mcq", mcq_choices=choices, mcq_correct_choice=correct)


class FiveChoiceMcqTests(unittest.TestCase):
    def test_four_and_five_choices_validate_but_three_and_six_do_not(self):
        self.assertEqual(normalize_labeled_choices(FOUR, "mcq"), FOUR)
        self.assertEqual(normalize_labeled_choices(FIVE, "mcq"), FIVE)
        for bad in (FOUR[:3], FIVE + ["extra"]):
            with self.assertRaises(ValueError):
                normalize_labeled_choices(bad, "mcq")

    def test_letters_offered_follow_the_item(self):
        self.assertEqual(choice_letters_for_item(item(FOUR)), ("A", "B", "C", "D"))
        self.assertEqual(choice_letters_for_item(item(FIVE)), ("A", "B", "C", "D", "E"))
        tf = SimpleNamespace(question_type="tf", mcq_choices=["yes", "no"])
        self.assertEqual(choice_letters_for_item(tf), ("A", "B"))

    def test_e_is_a_valid_reply_only_on_a_five_option_item(self):
        self.assertEqual(choice_response_letter(item(FIVE), "E"), "E")
        self.assertIsNone(choice_response_letter(item(FOUR), "E"))
        self.assertEqual(choice_response_letter(item(FIVE), "mcq_4"), "E")
        self.assertIsNone(choice_response_letter(item(FOUR), "mcq_4"))

    def test_choosing_the_meta_option_scores_incorrect(self):
        self.assertFalse(choice_response_is_correct(item(FIVE, "B"), "E"))
        self.assertTrue(choice_response_is_correct(item(FIVE, "B"), "B"))

    def test_correct_choice_e_and_text_parsing(self):
        _type, choices, letter, answer = validate_question_fields("mcq", FIVE, "E")
        self.assertEqual((letter, answer), ("E", "cannot tell"))
        with self.assertRaises(ValueError):
            validate_question_fields("mcq", FOUR, "E")
        parsed, stem = parse_choice_lines_from_text(
            "Q?\n" + "\n".join(f"{l}. {t}" for l, t in zip("ABCDE", FIVE))
        )
        self.assertEqual((parsed, stem), (FIVE, "Q?"))
        self.assertEqual(infer_question_type_from_choice_count(5), "mcq")


if __name__ == "__main__":
    unittest.main()
