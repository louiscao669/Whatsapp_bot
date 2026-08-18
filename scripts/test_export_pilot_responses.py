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
from export_pilot_responses import assemble, fetch_records, CONDITION_TO_EVAL

fails = []


def test_slate_consistency():
    """[NEW 2026-07-27b] The condition slate is declared in three places that must agree:
    build_experiment_plan.SLOTS (what gets assigned), pilot_import.CONDITIONS (what gets
    imported as passages) and export_pilot_responses.CONDITION_TO_EVAL (where responses land).
    A re-slate that misses one of them silently drops or misroutes a whole condition, so pin
    it here. pilot_import is read via AST -- importing it needs Flask/platform."""
    import ast
    from build_experiment_plan import SLOTS

    src = ast.parse((REPO_ROOT / "scripts" / "pilot_import.py").read_text(encoding="utf-8"))
    import_conds = None
    for node in src.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "CONDITIONS" for t in node.targets):
            import_conds = [e.elts[0].value for e in node.value.elts]
    slots = set(SLOTS)
    check("pilot_import.CONDITIONS parsed", import_conds is not None)
    check("SLOTS == pilot_import.CONDITIONS (assignment vs import agree)",
          slots == set(import_conds or []))
    check("SLOTS subset of CONDITION_TO_EVAL (every assigned condition can export)",
          slots <= set(CONDITION_TO_EVAL))


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
        # [NEW 2026-07-27b] the re-slated conditions: omission{15,30} + mistranslation{15,30}
        *[dict(chapter=ch, condition=cond, participant_slug="P03",
               qa_item_id=f"q{i}", passage_id=f"luke{ch}", passage_reference=f"Luke {ch}",
               question_type="open", question_text=f"Q{i}", expected_answer="y",
               response_id=f"r{i}", response_type="text", response_text="y",
               transcript_text=None, normalized_text=None, correctness_score=1.0,
               is_correct="correct", review_status="auto", matched_keywords=["y"],
               missing_keywords=[], media_id=None, mcq_correct=None)
          for i, (ch, cond) in enumerate(
              [(4, "omission15"), (5, "omission30"),
               (6, "mistranslation15"), (7, "mistranslation30")], start=5)],
    ]

    out = assemble(recs, split_by="condition", subdir="human", include_audio_ref=False)
    paths = set(out)
    check("omission20 -> luke3/human/omission/20%/",
          "outputs/luke3/human/omission/20%/scores_target_human.json" in paths)
    check("wbw -> luke1/human/google_word_by_word/ (no level)",
          "outputs/luke1/human/google_word_by_word/scores_target_human.json" in paths)
    check("clean -> luke1/human/omission/0%/",
          "outputs/luke1/human/omission/0%/scores_target_human.json" in paths)
    # [NEW 2026-07-27b] every re-slated condition must route to its eval-layout cell, and the
    # clean anchor must serve as the 0% dose for the mistranslation ladder too (there is no
    # mistranslation/0% cell) -- checked above via clean -> omission/0%.
    for ch, cond, cell in [(4, "omission15", "omission/15%"), (5, "omission30", "omission/30%"),
                           (6, "mistranslation15", "mistranslation/15%"),
                           (7, "mistranslation30", "mistranslation/30%")]:
        check(f"{cond} -> luke{ch}/human/{cell}/",
              f"outputs/luke{ch}/human/{cell}/scores_target_human.json" in paths)
    check("routes to 7 distinct cells (4 re-slated + retired omission20 + wbw + clean)",
          len(paths) == 7)

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


def test_unresolved_mcq_is_unscored_not_wrong():
    """[2026-08-12] An MCQ reply that never resolved to a letter is missing
    data, not an error.

    Before the LLM fallback, choice_response_is_correct returned False for an
    unparseable reply, so a participant who wrote "I think the second one" was
    indistinguishable in the export from one who picked the wrong choice. That
    biases human MCQ accuracy downward relative to the proxy benchmark, where
    answer models always emit clean letters.
    """
    base = dict(chapter=3, condition="clean", participant_slug="P01",
                passage_id="luke3", passage_reference="Luke 3",
                question_type="mcq", question_text="Q", expected_answer="B",
                response_type="text", transcript_text=None, normalized_text=None,
                correctness_score=None, review_status="auto", media_id=None)
    recs = [
        # cleanly parsed, correct
        dict(base, qa_item_id="q1", response_id="r1", response_text="B",
             is_correct="yes (auto)", mcq_correct=True, scoring_metadata=None),
        # cleanly parsed, wrong -- a real error, must still count
        dict(base, qa_item_id="q2", response_id="r2", response_text="A",
             is_correct="no (auto)", mcq_correct=False, scoring_metadata=None),
        # reply selected nothing -- must NOT count as wrong
        dict(base, qa_item_id="q3", response_id="r3", response_text="no idea",
             is_correct="pending", review_status="pending", mcq_correct=False,
             scoring_metadata={"method": "llm_choice_resolution",
                               "status": "unresolved"}),
        # still queued -- must NOT count either
        dict(base, qa_item_id="q4", response_id="r4", response_text="the second one",
             is_correct="pending", review_status="pending", mcq_correct=False,
             scoring_metadata={"method": "llm_choice_resolution", "status": "queued"}),
        # rescued by the LLM fallback, resolved to the correct letter
        dict(base, qa_item_id="q5", response_id="r5", response_text="B",
             is_correct="yes (auto)", mcq_correct=True,
             scoring_metadata={"method": "llm_choice_resolution",
                               "status": "complete", "resolved_letter": "B"}),
    ]
    out = assemble(recs, "condition", "human", False)
    payload = next(iter(out.values()))
    summary = payload["summary"]

    check("unresolved + queued excluded from mcq_scored_count",
          summary["mcq_scored_count"] == 3)
    check("both unscorable rows counted as mcq_unscored",
          summary["mcq_unscored"] == 2)
    check("mcq_correct counts only genuinely correct answers",
          summary["mcq_correct"] == 2)
    check("accuracy denominator excludes unscored (2/3, not 2/5)",
          abs(summary["mcq_accuracy"] - 2 / 3) < 1e-9)
    check("llm-rescued replies are counted",
          summary["mcq_llm_resolved"] == 3)

    by_item = {it["id"]: it for it in payload["items"]}
    check("unresolved row exports llm_score None (not 0.0)",
          by_item["q3"]["llm_score"] is None)
    check("unresolved row exports direct_correct None (not False)",
          by_item["q3"]["direct_correct"] is None)
    check("cleanly-wrong row still exports 0.0",
          by_item["q2"]["llm_score"] == 0.0)
    check("rescued row carries its resolved letter",
          by_item["q5"]["resolved_letter"] == "B")
    check("cleanly-parsed row is labelled exact_letter",
          by_item["q1"]["scoring_method"] == "exact_letter")


def test_tier1_path():
    rec = dict(
        chapter=2, condition="omission15", participant_slug="P01",
        qa_item_id="t1q", passage_id="t1_judg17_18",
        passage_reference="Judges 17:1-18:31", question_type="open",
        question_text="Q", expected_answer="A", response_id="r-t1",
        response_type="text", response_text="A", transcript_text=None,
        normalized_text=None, correctness_score=1.0, is_correct="correct",
        review_status="auto", media_id=None, mcq_correct=None,
        scoring_metadata={"method": "backtranslation_llm_judge", "scale": "0/0.5/1"},
    )
    out = assemble([rec], "condition", "human", False)
    check("tier-1 export routes by source passage, not window-group/chapter field",
          "outputs/tier1/t1_judg17_18/human/omission/15%/scores_target_human.json" in out)


def main():
    print("assemble():")
    test_assemble()
    print("unresolved MCQ handling:")
    test_unresolved_mcq_is_unscored_not_wrong()
    print("tier-1 output routing:")
    test_tier1_path()
    print("fetch_records() [sqlite]:")
    test_fetch_records_sqlite()
    print("slate consistency across the three declaration sites:")
    test_slate_consistency()
    print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
