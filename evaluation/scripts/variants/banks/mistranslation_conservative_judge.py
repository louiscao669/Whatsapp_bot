"""Experimental conservative judge contract; not enabled in production banks."""

from copy import deepcopy

from evaluation.scripts.variants.banks.mistranslation_validation import (
    JUDGE_SCHEMA, judgment_accepts, validate_schema,
)

CHANGE_BASES = (
    "explicit_value_change", "context_defined_distinction",
    "different_action_or_referent", "polarity_reversal",
    "vague_contrast", "equivalent_or_uncertain",
)
SCALAR_DIMENSIONS = {"quantity", "time", "frequency", "degree"}
CONSERVATIVE_SCHEMA = deepcopy(JUDGE_SCHEMA)
CONSERVATIVE_SCHEMA["properties"].update({
    "change_basis": {"type": "string", "enum": list(CHANGE_BASES)},
    "change_dimension": {"type": "string", "enum": [
        "quantity", "time", "frequency", "degree", "action", "referent",
        "relationship", "polarity", "attribute", "other",
    ]},
    "difference_evidence": {"type": "string"},
    "needs_repair": {"type": "string", "enum": ["yes", "no", "uncertain"]},
})
CONSERVATIVE_SCHEMA["required"] = list(CONSERVATIVE_SCHEMA["properties"])


def legacy_view(judgment):
    return {field: judgment[field] for field in JUDGE_SCHEMA["properties"]}


def conservative_rejection_reasons(judgment):
    """Apply explicit extra gates even if the five model criteria are all yes."""
    validate_schema(judgment, CONSERVATIVE_SCHEMA)
    reasons = []
    if not judgment_accepts(legacy_view(judgment)):
        reasons.append("legacy_criteria_or_claims_failed")
    if judgment["change_basis"] in {"vague_contrast", "equivalent_or_uncertain"}:
        reasons.append("insufficient_change_basis")
    if judgment["needs_repair"] != "no":
        reasons.append("edited_sentence_needs_repair_or_is_uncertain")
    if not judgment["difference_evidence"].strip():
        reasons.append("missing_difference_evidence")
    if (judgment["change_dimension"] in SCALAR_DIMENSIONS
            and judgment["change_basis"] == "different_action_or_referent"):
        reasons.append("scalar_change_cannot_use_action_or_referent_exception")
    return reasons


def conservative_judgment_accepts(judgment):
    return not conservative_rejection_reasons(judgment)
