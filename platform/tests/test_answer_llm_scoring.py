"""Judge parity tests.

The contract under test is that the live human judge matches the offline
benchmark judge (``evaluation/scripts/mcq/regen_mcq_tier01.py::judge_open``) on
scale, temperature and rubric. If these fail, the human pilot's open scores are
no longer comparable to the proxy benchmarks that H-T1 / H-T2 / H-T7 test
against -- so treat a failure here as a research-validity bug, not a unit-test
nit.
"""

import json
import unittest
from unittest.mock import patch

from eten_shared.answer_llm_scoring import (
    DEFAULT_MODEL,
    JUDGE_TEMPERATURE,
    VALID_SCORES,
    AnswerLLMScoringError,
    llm_answer_scoring_enabled,
    resolve_choice_letter,
    resolve_response_passage_text,
    score_open_answer,
)


class _Response:
    def __init__(self, payload):
        self.output_text = json.dumps(payload)


class _Responses:
    def __init__(self, payloads, calls):
        self.payloads = iter(payloads)
        self.calls = calls

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = next(self.payloads)
        if isinstance(payload, Exception):
            raise payload
        return _Response(payload)


class _Client:
    def __init__(self, payloads):
        self.calls = []
        self.responses = _Responses(payloads, self.calls)


def _judged(score, label, backtranslation="The angel came."):
    return [
        {"backtranslated_answer": backtranslation},
        {"score": score, "label": label, "rationale": "r"},
    ]


class ScoreScaleTests(unittest.TestCase):
    def test_returns_full_credit(self):
        result = score_open_answer(
            question="谁来了？",
            original_question="Who came?",
            participant_answer="天使来了",
            expected_answer="天使",
            original_expected_answer="The angel",
            language="zh",
            client=_Client(_judged(1, "correct")),
        )
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.label, "correct")
        self.assertEqual(result.backtranslated_answer, "The angel came.")

    def test_preserves_partial_credit(self):
        """The retired binary judge collapsed 0.5 to 0.0.

        judge_open emits 1 / 0.5 / 0, and the proxy benchmarks are means over
        that scale, so a partial must survive as 0.5.
        """
        result = score_open_answer(
            question="为什么？",
            participant_answer="因为害怕",
            expected_answer="因为不相信",
            original_expected_answer="Because he did not believe",
            client=_Client(_judged(0.5, "partial")),
        )
        self.assertEqual(result.score, 0.5)
        self.assertEqual(result.label, "partial")

    def test_returns_no_credit(self):
        result = score_open_answer(
            question="Q", participant_answer="A", expected_answer="E",
            original_expected_answer="E",
            client=_Client(_judged(0, "incorrect")),
        )
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.label, "incorrect")

    def test_blank_answer_scores_zero_without_calling_the_judge(self):
        client = _Client([])
        result = score_open_answer(
            question="Q", participant_answer="   ", expected_answer="E",
            original_expected_answer="E", client=client,
        )
        self.assertEqual(result.score, 0.0)
        self.assertEqual(client.calls, [])

    def test_score_is_read_from_free_text_like_judge_open(self):
        result = score_open_answer(
            question="Q", participant_answer="A", expected_answer="E",
            original_expected_answer="E",
            client=_Client(_judged("score: 0.5", "")),
        )
        self.assertEqual(result.score, 0.5)

    def test_unusable_score_raises_rather_than_defaulting_to_zero(self):
        """A malformed judgement must not be silently recorded as wrong."""
        with self.assertRaisesRegex(AnswerLLMScoringError, "unusable score"):
            score_open_answer(
                question="Q", participant_answer="A", expected_answer="E",
                original_expected_answer="E",
                client=_Client(_judged("banana", "???")),
            )

    def test_only_grid_scale_values_are_produced(self):
        for raw, expected in [(1, 1.0), ("1", 1.0), (0.5, 0.5), ("0.5", 0.5), (0, 0.0)]:
            result = score_open_answer(
                question="Q", participant_answer="A", expected_answer="E",
                original_expected_answer="E",
                client=_Client(_judged(raw, "")),
            )
            self.assertEqual(result.score, expected)
            self.assertIn(result.score, VALID_SCORES)


class JudgeParityTests(unittest.TestCase):
    def test_every_request_pins_temperature_zero(self):
        """Regression: this module was missed by the 2026-08-03 temperature sweep.

        It passed no temperature at all, so calls ran at the API default of 1.0
        -- on the pilot's primary human instrument.
        """
        client = _Client(_judged(1, "correct"))
        score_open_answer(
            question="Q", participant_answer="A", expected_answer="E",
            original_expected_answer="E", client=client,
        )
        self.assertEqual(len(client.calls), 2)  # backtranslate + judge
        for call in client.calls:
            self.assertEqual(call["temperature"], JUDGE_TEMPERATURE)
            self.assertEqual(call["temperature"], 0.0)

    def test_default_model_matches_the_grid_judge(self):
        self.assertEqual(DEFAULT_MODEL, "gpt-4o-mini")

    def test_passage_is_forwarded_to_the_judge(self):
        client = _Client(_judged(1, "correct"))
        score_open_answer(
            question="Q", participant_answer="A", expected_answer="E",
            original_expected_answer="E", passage="变体经文", client=client,
        )
        judge_payload = json.loads(client.calls[1]["input"][1]["content"])
        self.assertEqual(judge_payload["passage"], "变体经文")

    def test_absent_passage_is_omitted_not_blanked(self):
        """An empty string reads to the judge as 'the passage was blank'."""
        client = _Client(_judged(1, "correct"))
        score_open_answer(
            question="Q", participant_answer="A", expected_answer="E",
            original_expected_answer="E", passage="   ", client=client,
        )
        judge_payload = json.loads(client.calls[1]["input"][1]["content"])
        self.assertNotIn("passage", judge_payload)

    def test_judge_prompt_offers_all_three_scores(self):
        client = _Client(_judged(1, "correct"))
        score_open_answer(
            question="Q", participant_answer="A", expected_answer="E",
            original_expected_answer="E", client=client,
        )
        judge_payload = json.loads(client.calls[1]["input"][1]["content"])
        self.assertIn("0.5", judge_payload["task"])
        self.assertNotIn("never award partial credit", client.calls[1]["input"][0]["content"])


class _Passage:
    def __init__(self, text):
        self.passage_text = text


class _Cell:
    def __init__(self, passage):
        self.experiment_passage = passage


class _Assignment:
    def __init__(self, cell, cell_id="cell-1", passage_text=None):
        self.experiment_cell = cell
        self.experiment_cell_id = cell_id
        self.passage_text = passage_text


class _QAItem:
    def __init__(self, text):
        self.passage_text = text


class _StoredResponse:
    def __init__(self, assignment, qa_item):
        self.assignment = assignment
        self.qa_item = qa_item


class PassageResolutionTests(unittest.TestCase):
    """qa_item.passage_text is condition-INVARIANT; the variant is on the cell."""

    def test_prefers_the_variant_passage_over_the_shared_qa_text(self):
        response = _StoredResponse(
            _Assignment(_Cell(_Passage("degraded variant text"))),
            _QAItem("clean chapter text"),
        )
        self.assertEqual(
            resolve_response_passage_text(response), "degraded variant text"
        )

    def test_refuses_to_fall_back_when_the_cell_passage_is_null(self):
        """The ondelete=SET NULL footgun must not silently yield clean text.

        Judging a degraded-cell answer against the clean chapter would credit
        claims the respondent could not have read.
        """
        response = _StoredResponse(
            _Assignment(_Cell(None)), _QAItem("clean chapter text")
        )
        self.assertIsNone(resolve_response_passage_text(response))

    def test_non_experiment_response_falls_back_to_the_qa_item(self):
        response = _StoredResponse(None, _QAItem("chapter text"))
        self.assertEqual(resolve_response_passage_text(response), "chapter text")

    def test_prefers_the_delivered_snapshot_over_the_cell_passage(self):
        """The stamped snapshot is the exact text the respondent read.

        It is already sliced to the item's window/tile, whereas the cell's
        passage is the whole variant.
        """
        response = _StoredResponse(
            _Assignment(_Cell(_Passage("whole variant passage")),
                        passage_text="the three verses actually delivered"),
            _QAItem("clean chapter text"),
        )
        self.assertEqual(
            resolve_response_passage_text(response),
            "the three verses actually delivered",
        )

    def test_tier1_cell_with_no_single_passage_resolves_via_the_snapshot(self):
        """Regression: tier-1 cells are window GROUPS spanning two passages.

        They have no single experiment_passage_id, so the old FK-only lookup
        returned None for every tier-1 response and the outbox refused to judge
        them all.
        """
        response = _StoredResponse(
            _Assignment(_Cell(None), passage_text="tier-1 tile, omission30"),
            _QAItem("clean source text"),
        )
        self.assertEqual(
            resolve_response_passage_text(response), "tier-1 tile, omission30"
        )


_CHOICES = {"A": "The angel", "B": "The priest", "C": "The crowd", "D": "The king"}


class ChoiceResolutionTests(unittest.TestCase):
    """Fallback for MCQ replies that parse_mcq_response_letter returns None on.

    Motivation: choice_response_is_correct scores an unparseable reply FALSE,
    so a participant who writes "the second one" is recorded as WRONG. The
    proxy leg cannot produce that failure (answer models emit clean letters),
    so it is a bias living only in the human arm.
    """

    def test_resolves_a_paraphrased_reply_to_a_letter(self):
        result = resolve_choice_letter(
            question="Who came?",
            participant_answer="I think it was the second one",
            choices=_CHOICES,
            client=_Client([{"letter": "B", "rationale": "ordinal reference"}]),
        )
        self.assertEqual(result.letter, "B")
        self.assertTrue(result.resolved_by_llm)

    def test_returns_none_when_the_reply_selects_nothing(self):
        """Unresolvable must stay unresolvable -- callers treat None as
        unscorable, never as a wrong answer."""
        result = resolve_choice_letter(
            question="Who came?",
            participant_answer="I have no idea",
            choices=_CHOICES,
            client=_Client([{"letter": None, "rationale": "no selection"}]),
        )
        self.assertIsNone(result.letter)

    def test_rejects_a_letter_outside_the_offered_choices(self):
        result = resolve_choice_letter(
            question="Who came?", participant_answer="maybe E",
            choices={"A": "x", "B": "y"},
            client=_Client([{"letter": "D", "rationale": "hallucinated"}]),
        )
        self.assertIsNone(result.letter)

    def test_empty_reply_short_circuits_without_calling_the_llm(self):
        client = _Client([])
        result = resolve_choice_letter(
            question="Q", participant_answer="  ", choices=_CHOICES, client=client,
        )
        self.assertIsNone(result.letter)
        self.assertEqual(client.calls, [])

    def test_resolution_pins_temperature_zero(self):
        client = _Client([{"letter": "A", "rationale": "r"}])
        resolve_choice_letter(
            question="Q", participant_answer="the angel one",
            choices=_CHOICES, client=client,
        )
        self.assertEqual(client.calls[0]["temperature"], 0.0)

    def test_resolver_is_told_not_to_judge_correctness(self):
        """It maps reply -> choice. Correctness stays an exact letter-vs-key
        comparison, so MCQ parity with the grid is preserved."""
        client = _Client([{"letter": "A", "rationale": "r"}])
        resolve_choice_letter(
            question="Q", participant_answer="the angel one",
            choices=_CHOICES, client=client,
        )
        payload = json.loads(client.calls[0]["input"][1]["content"])
        self.assertIn("only which one was picked", payload["task"])
        self.assertEqual(payload["choices"], _CHOICES)

    def test_missing_choices_is_an_error_not_a_silent_none(self):
        with self.assertRaisesRegex(AnswerLLMScoringError, "Choices are required"):
            resolve_choice_letter(
                question="Q", participant_answer="something",
                choices={}, client=_Client([]),
            )


class MiscTests(unittest.TestCase):
    def test_translates_expected_answer_when_source_original_is_missing(self):
        result = score_open_answer(
            question="在哪里？",
            participant_answer="在城里",
            expected_answer="在城里",
            client=_Client([
                {"backtranslated_answer": "In the city",
                 "expected_answer_english": "In the city"},
                {"score": 1, "label": "correct"},
            ]),
        )
        self.assertEqual(result.expected_answer_english, "In the city")

    def test_wraps_provider_errors(self):
        with self.assertRaisesRegex(AnswerLLMScoringError, "request failed"):
            score_open_answer(
                question="Q", participant_answer="A", expected_answer="E",
                client=_Client([RuntimeError("offline")]),
            )

    def test_feature_flag_defaults_off(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(llm_answer_scoring_enabled())
        with patch.dict("os.environ", {"ENABLE_LLM_ANSWER_SCORING": "true"}):
            self.assertTrue(llm_answer_scoring_enabled())


if __name__ == "__main__":
    unittest.main()
