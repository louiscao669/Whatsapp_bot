import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import review_pilot_stems as pipeline
from eten_shared.models import Base, ExperimentPassage, ExperimentPassageVerse, ExperimentWindow, QAItem
from qa_generation.services.mcq_target import GroundingReview, review_stem_grounding


@pytest.mark.parametrize(("requested", "evidence", "expected"), [
    ("speech_time", "dated_content_only", "retire"),
    ("speech_time", "narrated_speech_time", "pass"),
    ("other", "dated_content_only", "pass"),
    ("speech_time", "unclear", "review"),
])
def test_only_the_mismatched_speech_target_retires(requested, evidence, expected):
    def parse(**call):
        assert set(json.loads(call["messages"][1]["content"])) == {"question", "excerpt"}
        result = GroundingReview(target="time", stem_quote="警告", requested_fact=requested, dated_event="撤退",
                                 quote="昨天撤退", timing_evidence=evidence, reason="Checked against the excerpt.")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=result))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    assert review_stem_grounding(client, "judge", "他何时警告众人？", "你们昨天撤退。")["verdict"] == expected


def test_model_decision_retires_existing_item_and_retries_without_manual_edits(tmp_path, monkeypatch):
    bank = tmp_path / "release"
    shutil.copytree(pipeline.pilot.SOL_BANK, bank)
    monkeypatch.setattr(pipeline.pilot, "SOL_BANK", bank)
    path = bank / "pilot_review.json"
    roster = json.loads(path.read_text())
    cid = "t1_judg9:m3kf"
    for row in roster:
        if row["id"] == cid:
            row.clear()
            row.update(id=cid, status="eligible")
    pipeline.save(path, roster)
    rows = pipeline.pilot.load_bank(pipeline.pilot.SOL_SET)
    item = next(r for r in rows if r["id"] == cid)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        pipeline.pilot.install(db, rows, qa_set=pipeline.pilot.SOL_SET, apply=True)
        before = pipeline.live_windows(db)
    finding = {"verdict": "retire", "requested_fact": "speech_time", "timing_evidence": "dated_content_only",
               "target": "date of the speech", "stem_quote": "向这些人说话", "dated_event": "the attack",
               "quote": "你们今天却起来攻击我父亲的家", "reason": "The passage dates the attack.",
               "model": "judge", "version": pipeline.grounding_version()}
    monkeypatch.setattr(pipeline, "review_stem_grounding", lambda *args: finding)
    results = pipeline.collect([item], None, "judge", tmp_path)
    with pytest.raises(ValueError, match="different released stem"):
        pipeline.publish(engine, {cid: dict(results[cid], stem_signature="stale")}, {cid})
    assert json.loads(path.read_text()) == roster
    for decisions in (results, {}):
        report = pipeline.publish(engine, decisions, {cid})
        assert report["retired"] == [cid]
        assert report["live_questions"] == len(before) - 1
    with Session(engine) as db:
        assert pipeline.live_windows(db) == {k: v for k, v in before.items() if k != cid}
    retired = next(r for r in json.loads(path.read_text()) if r["id"] == cid)
    assert retired["retired_from_pilot"] and retired["grounding_review"] == results[cid]


def test_related_copies_require_evidence_from_their_own_live_window(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        for index, (bank, verse) in enumerate([("old", "你们今日攻击我家。"), ("other", "他昨日向众人说话。")], 1):
            qa = QAItem(id=bank, passage_id=bank, question_text="他何时说话？", expected_answer="今日")
            passage = ExperimentPassage(source_passage_id=bank, chapter=index, language="zh",
                                        condition="clean", passage_text=verse)
            passage.verses = [ExperimentPassageVerse(verse_number="9:18", position=1, text=verse)]
            db.add_all([qa, passage, ExperimentWindow(qa_item_id=bank, source_passage_id=bank,
                       content_id="shared", group_index=index, sequence_index=index,
                       window_key="9:18", verse_numbers=["9:18"])])
    with Session(engine) as db:
        copies = pipeline.related_copies(db, {"shared"})
    def check(client, model, question, window):
        verdict = "retire" if "攻击" in window else "pass"
        return dict(verdict=verdict, quote=window, stem_quote="何时说话", requested_fact="speech_time",
                    timing_evidence="dated_content_only" if verdict == "retire" else "narrated_speech_time",
                    dated_event="攻击", model=model, version=pipeline.grounding_version(), reason="Checked timing.")
    monkeypatch.setattr(pipeline, "review_stem_grounding", check)
    findings = pipeline.collect(copies.values(), None, "judge", tmp_path)
    with pytest.raises(ValueError, match="evidence"):
        pipeline.publish_copy_reviews(engine, copies, {**findings, "old": dict(findings["old"], quote="别的经文")})
    for _ in range(2):
        assert pipeline.publish_copy_reviews(engine, copies, findings) == ["old"]
    with Session(engine) as db:
        assert list(pipeline.related_copies(db, {"shared"})) == ["other"]
        assert db.get(QAItem, "old").review_removed_at is not None
