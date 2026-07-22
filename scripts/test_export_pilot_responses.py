#!/usr/bin/env python3
"""Tests for export_pilot_responses: assemble() path/scoring + fetch_records via SQLite."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "eten-shared"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eten_shared.models import (
    Assignment, Base, ExperimentPlanCell, Participant, ParticipantResponse, QAItem,
)
from export_pilot_responses import assemble, fetch_records

fails = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def test_assemble():
    recs = [
        dict(chapter=3, condition="omission20", participant_slug="P01",
             qa_item_id="q1", passage_id="luke3", passage_reference="Luke 3",
             question_type="mcq", question_text="Q1", expected_answer="B",
             response_id="r1", response_type="text", response_text="B",
             transcript_text=None, normalized_text=None, correctness_score=None,
             is_correct="correct", review_status="auto", matched_keywords=[],
             missing_keywords=[], media_id=None, mcq_correct=True),
        dict(chapter=3, condition="omission20", participant_slug="P01",
             qa_item_id="q2", passage_id="luke3", passage_reference="Luke 3",
             question_type="open", question_text="Q2", expected_answer="grace",
             response_id="r2", response_type="audio", response_text=None,
             transcript_text="grace and truth", normalized_text=None,
             correctness_score=0.5, is_correct="pending", review_status="pending",
             matched_keywords=["grace"], missing_keywords=["truth"],
             media_id="m2", mcq_correct=None),
        dict(chapter=1, condition="wbw", participant_slug="P02",
             qa_item_id="q3", passage_id="luke1", passage_reference="Luke 1",
             question_type="mcq", question_text="Q3", expected_answer="A",
             response_id="r3", response_type="text", response_text="A",
             transcript_text=None, normalized_text=None, correctness_score=None,
             is_correct="incorrect", review_status="auto", matched_keywords=[],
             missing_keywords=[], media_id=None, mcq_correct=False),
        dict(chapter=1, condition="clean", participant_slug="P02",
             qa_item_id="q4", passage_id="luke1", passage_reference="Luke 1",
             question_type="open", question_text="Q4", expected_answer="x",
             response_id="r4", response_type="text", response_text="x",
             transcript_text=None, normalized_text=None, correctness_score=1.0,
             is_correct="correct", review_status="reviewed", matched_keywords=["x"],
             missing_keywords=[], media_id=None, mcq_correct=None),
    ]

    out = assemble(recs, split_by="condition", subdir="human", include_audio_ref=False)
    paths = set(out)
    check("omission20 -> luke3/human/omission/20%/",
          "outputs/luke3/human/omission/20%/scores_target_human.json" in paths)
    check("wbw -> luke1/human/google_word_by_word/ (no level)",
          "outputs/luke1/human/google_word_by_word/scores_target_human.json" in paths)
    check("clean -> luke1/human/omission/0%/",
          "outputs/luke1/human/omission/0%/scores_target_human.json" in paths)

    cell = out["outputs/luke3/human/omission/20%/scores_target_human.json"]
    s = cell["summary"]
    check("summary counts (2 items, 1 mcq, 1 open, mcq_correct=1)",
          s["total"] == 2 and s["mcq_count"] == 1 and s["open_count"] == 1 and s["mcq_correct"] == 1)
    check("open_llm_score_mean = correctness_score (0.5)", s["open_llm_score_mean"] == 0.5)
    mcq_item = next(it for it in cell["items"] if it["q_type"] == "mcq")
    open_item = next(it for it in cell["items"] if it["q_type"] != "mcq")
    check("mcq item direct_correct True + llm_score 1.0",
          mcq_item["direct_correct"] is True and mcq_item["llm_score"] == 1.0)
    check("open item llm_score 0.5, answer=transcript, modality audio",
          open_item["llm_score"] == 0.5 and open_item["generated_answer"] == "grace and truth"
          and open_item["response_modality"] == "audio")

    # audio ref gating
    check("audio_ref ABSENT by default", "audio_ref" not in open_item)
    out_ar = assemble(recs, split_by="condition", subdir="human", include_audio_ref=True)
    oi = next(it for it in out_ar["outputs/luke3/human/omission/20%/scores_target_human.json"]["items"]
              if it["q_type"] != "mcq")
    check("audio_ref present with flag (media_id + auth proxy path, no media_url)",
          oi.get("audio_ref") == "m2"
          and oi.get("audio_proxy_path") == "/api/v1/media/participant-response/r2"
          and "media_url" not in oi)

    # participant split -> subdir is the participant slug
    outp = assemble(recs, split_by="participant", subdir="human", include_audio_ref=False)
    check("participant split -> luke3/P01/omission/20%/",
          "outputs/luke3/P01/omission/20%/scores_target_human.json" in outp)


def test_fetch_records_sqlite():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Participant(id="p0", display_name="Part 0", consented=True, target_language="zh"))
        db.add(QAItem(id="qm", passage_id="luke3", question_text="Q", question_type="mcq",
                      expected_answer="B", mcq_choices=["a", "b", "c", "d"], mcq_correct_choice="B",
                      required_keywords=[], optional_keywords=[], active=True))
        cell = ExperimentPlanCell(id="c0", participant_id="p0", chapter=3,
                                  condition="omission20", sequence_index=0, status="done")
        db.add(cell)
        db.add(Assignment(id="a0", participant_id="p0", qa_item_id="qm",
                          status="completed", experiment_cell_id="c0"))
        db.add(ParticipantResponse(participant_id="p0", qa_item_id="qm", assignment_id="a0",
                                   response_type="text", response_text="B", correctness_score=None,
                                   is_correct="correct", review_status="auto",
                                   matched_keywords=[], missing_keywords=[]))
        db.commit()

        recs = fetch_records(db, require_reviewed=False)
        check("fetch_records returns the 1 completed experiment response", len(recs) == 1)
        check("MCQ scored correct via choice_response_is_correct (B==B)",
              recs and recs[0]["mcq_correct"] is True)
        out = assemble(recs, "condition", "human", False)
        check("fetched record assembles to the expected cell path",
              "outputs/luke3/human/omission/20%/scores_target_human.json" in out)

        # require-reviewed excludes a pending response
        db.add(ParticipantResponse(participant_id="p0", qa_item_id="qm", assignment_id="a0",
                                   response_type="text", response_text="B", is_correct="pending",
                                   review_status="pending", matched_keywords=[], missing_keywords=[]))
        db.commit()
        # latest response is now the pending one -> excluded under require_reviewed
        check("require_reviewed excludes pending latest response",
              len(fetch_records(db, require_reviewed=True)) == 0)


def main():
    print("assemble():")
    test_assemble()
    print("fetch_records() [sqlite]:")
    test_fetch_records_sqlite()
    print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
