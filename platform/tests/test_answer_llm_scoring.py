import json
import unittest
from unittest.mock import patch

from eten_shared.answer_llm_scoring import (
    AnswerLLMScoringError,
    llm_answer_scoring_enabled,
    score_open_answer_binary,
)


class _Response:
    def __init__(self, payload):
        self.output_text = json.dumps(payload)


class _Responses:
    def __init__(self, payloads):
        self.payloads = iter(payloads)

    def create(self, **_kwargs):
        payload = next(self.payloads)
        if isinstance(payload, Exception):
            raise payload
        return _Response(payload)


class _Client:
    def __init__(self, payloads):
        self.responses = _Responses(payloads)


class BinaryAnswerLLMScoringTests(unittest.TestCase):
    def test_backtranslates_then_returns_binary_correct_score(self):
        result = score_open_answer_binary(
            question="谁来了？",
            original_question="Who came?",
            participant_answer="天使来了",
            expected_answer="天使",
            original_expected_answer="The angel",
            language="zh",
            client=_Client([
                {"backtranslated_answer": "The angel came."},
                {
                    "score": 1,
                    "label": "correct",
                    "core_claim_expected": "the angel",
                    "core_claim_found": True,
                    "rationale": "Same person.",
                },
            ]),
        )

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.backtranslated_answer, "The angel came.")
        self.assertEqual(result.expected_answer_english, "The angel")

    def test_never_accepts_partial_credit(self):
        result = score_open_answer_binary(
            question="为什么？",
            participant_answer="因为害怕",
            expected_answer="因为不相信",
            original_expected_answer="Because he did not believe",
            client=_Client([
                {"backtranslated_answer": "Because he was afraid."},
                {"score": 0.5, "label": "partial", "rationale": "Wrong reason."},
            ]),
        )

        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.label, "incorrect")

    def test_translates_expected_answer_when_source_original_is_missing(self):
        result = score_open_answer_binary(
            question="在哪里？",
            participant_answer="在城里",
            expected_answer="在城里",
            client=_Client([
                {
                    "backtranslated_answer": "In the city",
                    "expected_answer_english": "In the city",
                },
                {"score": 1, "label": "correct"},
            ]),
        )
        self.assertEqual(result.expected_answer_english, "In the city")

    def test_wraps_provider_errors(self):
        with self.assertRaisesRegex(AnswerLLMScoringError, "request failed"):
            score_open_answer_binary(
                question="Q",
                participant_answer="A",
                expected_answer="E",
                client=_Client([RuntimeError("offline")]),
            )

    def test_feature_flag_defaults_off(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(llm_answer_scoring_enabled())
        with patch.dict("os.environ", {"ENABLE_LLM_ANSWER_SCORING": "true"}):
            self.assertTrue(llm_answer_scoring_enabled())


if __name__ == "__main__":
    unittest.main()
