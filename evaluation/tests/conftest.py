"""Opt-in model stubs for offline grammar pipeline tests."""

import copy

import pytest

from evaluation.scripts.variants.current import create_grammar_variants as grammar


@pytest.fixture
def fake_meaning_models(monkeypatch):
    # These responses test pipeline contracts, not linguistic correctness.
    calls = {"reading": [], "comparison": []}

    def read(self, request):
        calls["reading"].append(copy.deepcopy(request))
        return {
            "primary_reading": "Synthetic reading.", "participant_roles": "Synthetic roles.",
            "event_structure": "Synthetic event.", "modifier_scope": "Synthetic modifiers.",
            "interpretation_status": "clear", "alternative_readings": [],
        }

    def compare(self, request):
        calls["comparison"].append(copy.deepcopy(request))
        return {"explanation": "Synthetic comparison.", "risk_spans": [],
                **{field: "yes" for field in grammar.MEANING_FIELDS}}

    monkeypatch.setattr(grammar.GPTMeaningReader, "__call__", read)
    monkeypatch.setattr(grammar.GPTMeaningJudge, "__call__", compare)
    return calls
