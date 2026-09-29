#!/usr/bin/env python3
"""Exercise the padding at its CALL SITE, against the real ORM.

Why this exists. test_pad_window_verses.py covers pad_window_verses itself, and every
case passed -- while experiment_passage_assignment_kwargs never imported the function.
The padding branch only runs when a curated window has lost verses to omission, so the
NameError sat there until the first damaged window reached delivery and answered a
participant with HTTP 500. A pure test of a helper cannot catch a missing import at the
place that calls it; this one drives the real function and would have.

Run: python3 platform/tests/test_experiment_window_padding_callsite.py   (no DB / env)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("REQUIRE_QUESTION_AUDIO", "false")
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eten_shared.models import (
    Base, ExperimentPassage, ExperimentPassageVerse, ExperimentWindow, QAItem,
)
from eten_shared.domain.assignments import (
    PASSAGE_DELIVERY_VERSE_COUNT, experiment_passage_assignment_kwargs,
)

fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def build(surviving, window_numbers, other_windows=()):
    """A passage holding only `surviving` verses, and a window asking for `window_numbers`."""
    db = Session(create_engine("sqlite:///:memory:"))
    Base.metadata.create_all(db.get_bind())
    passage = ExperimentPassage(chapter=9, condition="omission_30", language="zh",
                                name="t1", passage_text="whole passage",
                                source_passage_id="t1_judg9")
    db.add(passage)
    db.flush()
    for position, number in enumerate(surviving):
        db.add(ExperimentPassageVerse(experiment_passage_id=passage.id, position=position,
                                      verse_number=number, text=f"verse {number}"))
    item = QAItem(id="q1", passage_id="t1_judg9", question_text="为什么？",
                  question_type="mcq", expected_answer="a",
                  mcq_choices=["a", "b", "c", "d"], mcq_correct_choice="A",
                  required_keywords=[], optional_keywords=[], active=True)
    db.add(item)
    db.add(ExperimentWindow(qa_item_id="q1", source_passage_id="t1_judg9",
                            content_id="t1_judg9:q1", window_key="q1",
                            group_index=9, sequence_index=0,
                            verse_numbers=list(window_numbers)))
    for index, numbers in enumerate(other_windows):
        other = QAItem(id=f"q{index + 2}", passage_id="t1_judg9", question_text="什么？",
                       question_type="mcq", expected_answer="a",
                       mcq_choices=["a", "b", "c", "d"], mcq_correct_choice="A",
                       required_keywords=[], optional_keywords=[], active=True)
        db.add(other)
        db.add(ExperimentWindow(qa_item_id=other.id, source_passage_id="t1_judg9",
                                content_id=f"t1_judg9:{other.id}", window_key=other.id,
                                group_index=9, sequence_index=index + 1,
                                verse_numbers=list(numbers)))
    db.commit()
    return db, passage, item


# THE REGRESSION: a window cut down to one verse by omission. This is the exact shape
# that raised NameError: name 'pad_window_verses' is not defined.
db, passage, item = build(surviving=["1", "2", "3", "4", "5"], window_numbers=["3", "4", "5"])
db.execute(ExperimentPassageVerse.__table__.delete().where(
    ExperimentPassageVerse.verse_number.in_(["4", "5"])))
db.commit()
kwargs = experiment_passage_assignment_kwargs(db, passage, item)
check("a window cut to one verse is served, not an exception",
      isinstance(kwargs, dict) and kwargs.get("passage_verse_numbers"))
check(f"and it is padded back to {PASSAGE_DELIVERY_VERSE_COUNT} verses",
      len(kwargs["passage_verse_numbers"]) == PASSAGE_DELIVERY_VERSE_COUNT)
check("the padded text is non-empty", bool(kwargs["passage_text"].strip()))
check("padding never resurrects a deleted verse",
      not ({"4", "5"} & set(kwargs["passage_verse_numbers"])))
db.close()

# an intact window must be returned verbatim, padding untouched
db, passage, item = build(surviving=["1", "2", "3", "4"], window_numbers=["2", "3", "4"])
kwargs = experiment_passage_assignment_kwargs(db, passage, item)
check("an intact window is passed through unchanged",
      kwargs["passage_verse_numbers"] == ["2", "3", "4"])
db.close()

# a wholly deleted window has nothing to anchor: no verses, no crash
db, passage, item = build(surviving=["1", "2"], window_numbers=["7", "8", "9"])
kwargs = experiment_passage_assignment_kwargs(db, passage, item)
check("a wholly deleted window still returns padding rather than failing",
      isinstance(kwargs, dict))
db.close()

# `occupied` is advisory: a short window is never returned just to dodge an overlap
db, passage, item = build(surviving=["1", "2", "3"], window_numbers=["3"],
                          other_windows=(["1", "2"],))
kwargs = experiment_passage_assignment_kwargs(db, passage, item)
check("a claimed verse is taken rather than returning a short window",
      len(kwargs["passage_verse_numbers"]) == PASSAGE_DELIVERY_VERSE_COUNT)
db.close()

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
