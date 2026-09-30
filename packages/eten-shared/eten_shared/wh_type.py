"""Classify a question stem by its interrogative: who / what / when / where / why / how.

Why the pilot cares. An entity-retrieval item ("who did X") is answerable by locating a
proper noun, and a proper noun is the most transfer-robust element in a translation: it
survives grammar corruption, awkward phrasing, added filler and style drift, and is
touched only by deletion or a name swap. A question set weighted toward `who` is
therefore insensitive to four of the six defect families before any defect is applied.
Measured 2026-09-26: hard66 is 47.0% `who` against gold72's 12.7%, and 44% of hard66
items have name-like options against gold72's 3%. Under omission the why/how items lost
45.0pp against who's 11.1pp -- but under MISTRANSLATION the ordering reversed, `who`
falling hardest, because a swapped name is fatal to an entity lookup. So this is a
composition knob, not a quality ranking.
See EXPERIMENT_QUESTION_TYPE_COMPOSITION_2026-09-26.md.

This module is the canonical copy for the bot repo; qa_generation keeps its own beside
QAPairSimple.wh_type, because the two repos are not on one import path. If you change a
cue here, change it there too -- and note the Chinese ORDER is load-bearing (为什么 and
什么时候 both contain 什么), so getting it wrong silently reclassifies rather than fails.

Deliberately dependency-free: imported by the live assignment selector, and by scripts
that run where sqlalchemy is not installed.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

WH_TYPES = ("who", "what", "when", "where", "why", "how")
UNKNOWN = "other"

_CUES = (
    ("why",   (r"\bwhy\b",),                           ("为什么", "为何", "何故", "缘何")),
    ("when",  (r"\bwhen\b",),                          ("什么时候", "何时", "几时", "多久")),
    ("how",   (r"\bhow\b",),                           ("怎样", "怎么", "如何", "怎")),
    ("who",   (r"\bwho\b", r"\bwhom\b", r"\bwhose\b"), ("谁",)),
    ("where", (r"\bwhere\b",),                         ("哪里", "何处", "在哪", "往哪")),
    ("what",  (r"\bwhat\b", r"\bwhich\b"),             ("什么", "哪个", "哪些", "哪一")),
)


def classify_wh_type(stem: Optional[str]) -> str:
    """The interrogative a stem asks with, or "other" when none is recognisable.

    A sentence-initial wh-word wins over one appearing later, so "What does the man who
    fled do?" is a `what`: an embedded relative pronoun is not the question being asked.
    """
    if not stem:
        return UNKNOWN
    s = stem.strip()
    low = s.lower()
    for label, en, _zh in _CUES:
        if any(re.match(r"^\s*" + p, low) for p in en):
            return label
    for label, _en, zh in _CUES:
        if any(cue in s for cue in zh):
            return label
    for label, en, _zh in _CUES:
        if any(re.search(p, low) for p in en):
            return label
    return UNKNOWN


def parse_wh_types(raw: Optional[str]) -> frozenset:
    """Parse a comma/space separated list of stem types, rejecting unknown names.

    Raising rather than ignoring is deliberate: this reads an environment variable that
    gates what a live participant is served, and a typo that silently disabled the
    filter would look exactly like the filter working on a set with no matches.
    """
    if not raw or not raw.strip():
        return frozenset()
    keep = frozenset(t for t in re.split(r"[,\s]+", raw.strip().lower()) if t)
    unknown = keep - set(WH_TYPES)
    if unknown:
        raise ValueError(
            f"unknown stem type(s) {sorted(unknown)}; known: {', '.join(WH_TYPES)}"
        )
    return keep


# Per-participant stem filter, stored in ``participants.dashboard_preferences`` (JSON,
# no schema change) by the admin "Create test participant" action. When present it is a
# HARD filter for that participant only -- see experiment_selection.participant_wh_filter.
PARTICIPANT_WH_TYPES_KEY = "wh_types"


def participant_wh_types(participant) -> frozenset:
    """The stem types a participant is restricted to; empty = unrestricted.

    Reads ``dashboard_preferences[PARTICIPANT_WH_TYPES_KEY]`` (a list such as ["why"]).
    Unknown names are dropped rather than raised: this runs on every question served,
    and the value was already validated when the participant was created.
    """
    prefs = getattr(participant, "dashboard_preferences", None) or {}
    raw = prefs.get(PARTICIPANT_WH_TYPES_KEY) or []
    if isinstance(raw, str):
        raw = re.split(r"[,\s]+", raw)
    return frozenset(str(t).strip().lower() for t in raw) & frozenset(WH_TYPES)


def group_by_wh_type(stems: Iterable[Optional[str]]) -> dict:
    """{wh_type: count}, every known type present (possibly zero)."""
    out = {t: 0 for t in WH_TYPES}
    out[UNKNOWN] = 0
    for s in stems:
        out[classify_wh_type(s)] += 1
    return out
