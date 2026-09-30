"""Per-participant question-FORM restriction (MCQ vs open).

Stored in ``participants.dashboard_preferences[PARTICIPANT_QUESTION_FORMS_KEY]`` as a
list such as ``["mcq"]`` -- the same JSON column the ``wh_types`` restriction and the
test flag use, so no schema change.

Resolution (``participant_question_forms``):
  * an explicit setting wins (``["mcq"]``, or ``["mcq", "open"]`` for both);
  * otherwise a TEST participant is MCQ-only -- test accounts are for checking the
    served multiple-choice items, and open answers from them are noise;
  * otherwise (real participants) unrestricted, i.e. behaviour is unchanged.

Applied by the experiment selector as a HARD filter, like the strict wh-type arm: a plan
cell holding no item of an allowed form is flipped to ``done`` and skipped. With MCQ-only
that drops the open-only items (gold72 17, hard66 16), never a whole cell in the current
sets, since every window group carries MCQ items.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from eten_shared.experiment_plan import is_test_participant

QUESTION_FORMS = ("mcq", "open")
PARTICIPANT_QUESTION_FORMS_KEY = "question_forms"
TEST_PARTICIPANT_DEFAULT_FORMS = frozenset({"mcq"})


def parse_question_forms(raw) -> frozenset:
    """"mcq" / "mcq,open" / ["mcq"] / "all" -> frozenset. Unknown names raise ValueError.

    Empty / None -> empty set (= caller's default). "all" -> every form.
    """
    if raw is None:
        return frozenset()
    if isinstance(raw, (list, tuple, set, frozenset)):
        parts = [str(p) for p in raw]
    else:
        parts = re.split(r"[,\s]+", str(raw))
    parts = [p.strip().lower() for p in parts if p and p.strip()]
    if "all" in parts:
        return frozenset(QUESTION_FORMS)
    unknown = sorted(set(parts) - set(QUESTION_FORMS))
    if unknown:
        raise ValueError(f"unknown question form(s): {', '.join(unknown)} "
                         f"(expected {', '.join(QUESTION_FORMS)} or all)")
    return frozenset(parts)


def stored_question_forms(participant) -> frozenset:
    """The explicit setting only (empty when none). Unknown names are dropped."""
    prefs = getattr(participant, "dashboard_preferences", None) or {}
    raw = prefs.get(PARTICIPANT_QUESTION_FORMS_KEY) or []
    if isinstance(raw, str):
        raw = re.split(r"[,\s]+", raw)
    return frozenset(str(f).strip().lower() for f in raw) & frozenset(QUESTION_FORMS)


def participant_question_forms(participant) -> frozenset:
    """Forms this participant may be served; empty = unrestricted (see module doc)."""
    own = stored_question_forms(participant)
    if own:
        return frozenset() if own == frozenset(QUESTION_FORMS) else own
    if is_test_participant(participant):
        return TEST_PARTICIPANT_DEFAULT_FORMS
    return frozenset()


def filter_candidates_by_form(items: Iterable, keep: Optional[frozenset]) -> list:
    """Items whose ``question_type`` is one of ``keep``. Empty ``keep`` -> unchanged."""
    items = list(items)
    if not keep:
        return items
    return [item for item in items if getattr(item, "question_type", None) in keep]
