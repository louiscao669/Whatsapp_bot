"""Researcher labels for the exact Chinese question and options reviewed."""
import json
from functools import lru_cache

from eten_shared.repo_paths import REPO_ROOT


@lru_cache(maxsize=1)
def _records():
    path = REPO_ROOT / "evaluation/datasets/qa/reviewed122_sol/manual_wording.json"
    return json.loads(path.read_text(encoding="utf-8"))["banks"]


def manual_fields(bank, item_id, question, choices, correct):
    if bank not in {"reviewed122_sol", "reviewed122"} or not item_id:
        return []
    # Drafts can share a source ID with the release while carrying different authorship.
    for version in _records()[bank].get(item_id, []):
        if (version["question"] == question and version["choices"] == choices[:4]
                and version["correct"] == correct):
            return list(version["manually_written_fields"])
    return []
