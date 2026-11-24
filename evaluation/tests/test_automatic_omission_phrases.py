import pytest
from pydantic import ValidationError

from evaluation.scripts.pipeline import generate_omission_phrases as auto
from evaluation.scripts.pipeline.build_omission_phrase_bank import Passage, make_report


def decision(number, reason, flags=None, **overrides):
    checks = dict.fromkeys(auto.Checks.model_fields, "yes")
    checks.update(overrides)
    return auto.Decision(number=number, checks=auto.Checks(**checks), flags=flags or [], reason=reason)


def word_decision(number, reason, information_loss, category="person_or_group", key_check="yes", **overrides):
    value = decision(number, reason, **overrides).model_dump()
    value["checks"]["key_content_removed"] = key_check
    return auto.WordDecision(**value, information_loss=information_loss,
                             key_content_category=category, key_content_reason=reason)


def test_automatic_review_uses_real_deletions_and_holds_invalid_spans(monkeypatch, tmp_path):
    clean = {"1:1": "他在山上祷告。", "1:2": "那天天亮了。"}
    source = Passage("Test", {"1:1": "He prayed on the mountain.", "1:2": "It was day."}, clean, "test")
    proposed = [("on the mountain", "在山上"), ("on the mountain", "在山上"),
                ("He prayed", "祷告"), ("on the mountain", "在山下")]
    seen = []
    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        seen.append((stage, model))
        if stage == "propose":
            assert set(payload["1:1"]) == {"english", "chinese"}
            result = auto.Proposals(phrases=[
                auto.Phrase(verse="1:1", english=en, chinese=zh, english_occurrence=1, chinese_occurrence=1)
                for en, zh in proposed], no_proposals_reason="")
        else:
            assert [x["number"] for x in payload["candidates"]] == [1, 3]
            assert payload["candidates"][0]["edited_chinese_verse"] == "他祷告。"
            assert payload["window"]["1:2"]["chinese"] == clean["1:2"]
            result = auto.Decisions(decisions=[
                decision(3, "Removes the main action and leaves an unfinished sentence.",
                         valid_omission_unit="no", fluent="no"),
                decision(1, "Removes the location while keeping the prayer.")])
        validate(result)
        return result

    monkeypatch.setattr(auto, "ask", stub)
    window = dict(window_id="sample", passage_id="test")
    result = auto.process_window(None, tmp_path, window, clean, source, "writer", "reviewer")
    assert seen == [("propose", "writer"), ("review", "reviewer")]
    rows = result["candidates"]
    assert [r["status"] for r in rows] == ["accepted", "rejected", "rejected", "rejected"]
    assert [r["stage"] for r in rows] == ["model_review", "span_check", "model_review", "span_check"]
    assert rows[0]["affected_chars"] == 3 and "edit" not in rows[3]


def test_reviewer_must_cover_every_proposal_once():
    result = decision(1, "Removed the location.")
    with pytest.raises(ValueError, match="exactly one"):
        auto.validate_reviews(auto.Decisions(decisions=[result, result]), [1, 2])


def test_clause_boundary_recheck_can_hold_an_initial_pass(monkeypatch, tmp_path):
    clean = {"1:1": "住在城里的工人来了。"}
    source = Passage("Test", {"1:1": "The workers living in the city arrived."}, clean, "test")
    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        if stage == "propose":
            result = auto.Proposals(phrases=[auto.Phrase(verse="1:1", english="living in the city",
                chinese="住在城里的", english_occurrence=1, chinese_occurrence=1)], no_proposals_reason="")
        else:
            assert payload["candidates"][0]["edited_chinese_verse"] == "工人来了。"
            assert "reviews" not in payload["candidates"][0]
            unit_check = "no" if stage == "unit_review" else "yes"
            flags = ["ambiguous_reference", "other_meaning_changed"] if stage == "review" else []
            result = auto.Decisions(decisions=[decision(1, "Residence.", flags, valid_omission_unit=unit_check)])
        validate(result)
        return result

    monkeypatch.setattr(auto, "ask", stub)
    w = dict(window_id="test", passage_id="test")
    row, = auto.process_window(None, tmp_path, w, clean, source, "writer", "reviewer")["candidates"]
    assert row["status"] == "rejected" and row["issues"] == ["valid_omission_unit"]
    assert row["flags"] == ["ambiguous_reference", "other_meaning_changed"]
    assert [r["stage"] for r in row["reviews"]] == ["review", "unit_review"]


def test_fluency_rejects_and_prior_candidates_are_reviewed_blind(monkeypatch, tmp_path):
    clean = {"1:1": "他正坐在自己家中。", "1:2": "他向王宫报信。"}
    source = Passage("Test", {"1:1": "He sat in his house.", "1:2": "He reported to the palace."}, clean, "test")
    fresh = auto.Phrase(verse="1:1", english="in his house", chinese="在自己家中",
                        english_occurrence=1, chinese_occurrence=1)
    old = auto.Phrase(verse="1:2", english="to the palace", chinese="向王宫", english_occurrence=1, chinese_occurrence=1)
    prior = {"candidates": [dict(proposal=p.model_dump(), status="pass_with_flags", issues=[],
                                 flags=["fluency"]) for p in (fresh, old)]}
    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        if stage == "propose":
            assert set(payload) == set(clean)
            result = auto.Proposals(phrases=[fresh], no_proposals_reason="")
        else:
            assert len(payload["candidates"]) == 2
            assert all("previous_status" not in c and "proposed_this_run" not in c for c in payload["candidates"])
            result = auto.Decisions(decisions=[
                decision(1, "The location disappears; 正坐 sounds unfinished.", fluent="no"),
                decision(2, "The recipient disappears.")])
        validate(result)
        return result
    monkeypatch.setattr(auto, "ask", stub)
    w = auto.process_window(None, tmp_path, dict(window_id="test", passage_id="test"), clean, source, "writer", "reviewer", prior)
    assert w["fresh_count"] == 1
    assert [(c["status"], c["proposed_this_run"], c["previous_status"]) for c in w["candidates"]] == [
        ("rejected", True, "pass_with_flags"), ("accepted", False, "pass_with_flags")]
    assert w["candidates"][0]["checks"]["fluent"] == "no"
    assert w["candidates"][0]["issues"] == ["fluent"]


@pytest.mark.parametrize("check", list(auto.Checks.model_fields))
@pytest.mark.parametrize("answer", ["no", "uncertain"])
def test_every_failed_or_uncertain_check_rejects_in_normal_entry_point(monkeypatch, tmp_path, check, answer):
    clean = {"1:1": "他在山上祷告。"}
    source = Passage("Test", {"1:1": "He prayed on the mountain."}, clean, "test")

    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        if stage == "propose":
            result = auto.Proposals(phrases=[auto.Phrase(verse="1:1", english="on the mountain",
                chinese="在山上", english_occurrence=1, chinese_occurrence=1)], no_proposals_reason="")
        else:
            result = auto.Decisions(decisions=[decision(1, "Review explanation.",
                                                       ["other_meaning_changed"], **{check: answer})])
        validate(result)
        return result

    monkeypatch.setattr(auto, "ask", stub)
    w = dict(window_id="sample", passage_id="test")
    row, = auto.process_window(None, tmp_path, w, clean, source, "writer", "reviewer")["candidates"]
    assert row["status"] == "rejected"
    assert row["issues"] == [check]
    assert row["checks"][check] == answer
    assert row["flags"] == ["other_meaning_changed"]


def test_fluent_omission_can_be_accepted_with_context_flags_and_reported(monkeypatch, tmp_path):
    clean = {"1:1": "他在山上祷告。", "1:2": "他下山了。"}
    source = Passage("Test", {"1:1": "He prayed on the mountain.", "1:2": "He came down the mountain."}, clean, "test")

    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        if stage == "propose":
            result = auto.Proposals(phrases=[auto.Phrase(verse="1:1", english="on the mountain",
                chinese="在山上", english_occurrence=1, chinese_occurrence=1)], no_proposals_reason="")
        else:
            result = auto.Decisions(decisions=[decision(1, "Location omitted here and inferable from the descent.",
                                                       ["recoverable_from_context"])])
        validate(result)
        return result

    monkeypatch.setattr(auto, "ask", stub)
    w = auto.process_window(None, tmp_path, dict(window_id="sample", passage_id="test", reference="Test 1:1–2"),
                            clean, source, "writer", "reviewer")
    row, = w["candidates"]
    assert row["status"] == "accepted" and row["issues"] == []
    assert row["flags"] == ["recoverable_from_context"]
    bank = dict(mode="automatic", review_version=4, provenance="Test", windows=[w],
                required_checks=list(auto.Checks.model_fields), semantic_distortion_policy="flag")
    manifest = {"windows": [dict(id="sample", conditions={"clean": {"verses": clean}})]}
    report = make_report(bank, manifest, {"test": source})
    assert "1 accepted" in report and "0 rejected" in report
    assert "Accepted with flags: 1" in report and "Accepted without flags: 0" in report
    assert "fluent = yes" in report and "recoverable from context (1)" in report
    assert "all 5 checks" in report and "other meaning preserved" not in report
    assert "secondary mistranslation effects without causing rejection" in report
    assert "Pass with flags" not in report


@pytest.mark.parametrize("flag", ["other_meaning_changed", "possible_other_meaning_changed"])
@pytest.mark.parametrize("fluent", ["yes", "no", "uncertain"])
def test_deletion_with_changed_prohibition_is_flagged_but_fluency_required(monkeypatch, tmp_path, flag, fluent):
    clean = {"1:1": "你不可沿原路返回。"}
    source = Passage("Test", {"1:1": "You must not return by the same route."}, clean, "test")
    proposal = auto.Phrase(verse="1:1", english="by the same route", chinese="沿原路",
                          english_occurrence=1, chinese_occurrence=1)
    prior = {"candidates": [dict(proposal=proposal.model_dump(), status="rejected",
                                 issues=["other_meaning_preserved"], flags=[])]}

    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        if stage == "propose":
            result = auto.Proposals(phrases=[], no_proposals_reason="No additional proposals.")
        else:
            assert payload["candidates"][0]["edited_chinese_verse"] == "你不可返回。"
            result = auto.Decisions(decisions=[decision(1, "The prohibition has a broader reading.",
                                                       [flag], fluent=fluent)])
        validate(result)
        return result

    monkeypatch.setattr(auto, "ask", stub)
    w = dict(window_id="sample", passage_id="test")
    row, = auto.process_window(None, tmp_path, w, clean, source, "writer", "reviewer", prior)["candidates"]
    assert row["previous_status"] == "rejected" and not row["proposed_this_run"]
    assert row["checks"]["fluent"] == fluent
    assert row["flags"] == [flag]
    assert row["status"] == ("accepted" if fluent == "yes" else "rejected")
    assert row["issues"] == ([] if fluent == "yes" else ["fluent"])


def test_semantic_distortion_is_a_flag_and_fluency_is_required():
    result = decision(1, "Changed scope.", ["other_meaning_changed"])
    assert "other_meaning_preserved" not in result.checks.model_dump()
    assert len(result.checks.model_dump()) == 5
    checks = dict.fromkeys(auto.Checks.model_fields, "yes")
    del checks["fluent"]
    with pytest.raises(ValidationError, match="fluent"):
        auto.Checks(**checks)
    with pytest.raises(ValidationError, match="flags"):
        decision(1, "Unfinished sentence.", ["fluency"])


@pytest.mark.parametrize("unit,expected", [("word", "accepted"), ("phrase", "rejected")])
def test_single_word_reaches_word_reviewer_but_not_phrase_reviewer(monkeypatch, tmp_path, unit, expected):
    clean = {"1:1": "他的父亲大卫来了。"}
    source = Passage("Test", {"1:1": "His father David came."}, clean, "test")
    stages = []
    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        stages.append(stage)
        assert f"{unit}-level" in prompt and "{unit_rules}" not in prompt
        if stage == "propose":
            result = auto.Proposals(phrases=[auto.Phrase(verse="1:1", english="David", chinese="大卫",
                english_occurrence=1, chinese_occurrence=1)], no_proposals_reason="")
        else:
            assert unit == "word"
            assert payload["candidates"][0]["edited_chinese_verse"] == "他的父亲来了。"
            result = auto.WordDecisions(decisions=[word_decision(1, "Loses the father's identity.",
                information_loss=dict(kind="content_detail", source_information="His father David came.",
                                      edited_information="His father came.", lost_content="The father is David."))])
        validate(result)
        return result
    monkeypatch.setattr(auto, "ask", stub)
    w = auto.process_window(None, tmp_path, dict(window_id="sample", passage_id="test", reference="Test 1:1"),
                            clean, source, "writer", "reviewer", unit=unit)
    row, = w["candidates"]
    assert row["status"] == expected
    assert stages == (["propose", "review"] if unit == "word" else ["propose"])
    bank = dict(unit=unit, mode="automatic", review_version=4, provenance="Test", windows=[w])
    manifest = {"windows": [dict(id="sample", conditions={"clean": {"verses": clean}})]}
    report = make_report(bank, manifest, {"test": source})
    assert f"{unit.title()} omissions for the 1 Sol windows" in report


def test_word_mode_still_rejects_split_english_words():
    with pytest.raises(ValueError, match="splits a word"):
        auto.check_source_boundaries("He returned.", 3, "return", unit="word")
    with pytest.raises(ValueError, match="fewer than 1"):
        auto.check_source_boundaries("He returned.", 11, ".", unit="word")
    # Multi-token numbers are reviewed as a lexical unit, not rejected by token count.
    auto.check_source_boundaries("He had two hundred horses.", 7, "two hundred", unit="word")


@pytest.mark.parametrize("kind,expected", [("emphasis_only", "no"), ("meaning_preserved", "no"),
                                           ("unaligned", "no"), ("uncertain", "uncertain")])
def test_word_recheck_rejects_noncontent_even_if_reviewer_marks_information_yes(monkeypatch, tmp_path, kind, expected):
    clean = {"1:1": "诚然，他会回来。"}
    source = Passage("Test", {"1:1": "Surely he will return."}, clean, "test")
    old = auto.Phrase(verse="1:1", english="Surely", chinese="诚然，", english_occurrence=1, chinese_occurrence=1)
    prior = dict(candidates=[dict(proposal=old.model_dump(), status="accepted", issues=[])])
    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        assert stage == "review", "Re-review must not request new proposals"
        assert schema is auto.WordDecisions and "KEY PASSAGE INFORMATION" in prompt
        assert payload["candidates"][0]["edited_chinese_verse"] == "他会回来。"
        assert "previous_status" not in str(payload)
        result = auto.WordDecisions(decisions=[word_decision(1, "Same return prediction; certainty emphasis is removed.",
            information_loss=dict(kind=kind, source_information="The speaker predicts his return with emphasis.",
                                  edited_information="The speaker predicts his return.",
                                  lost_content="No concrete event detail beyond certainty emphasis."))])
        validate(result)
        return result
    monkeypatch.setattr(auto, "ask", stub)
    w = auto.process_window(None, tmp_path, dict(window_id="test", passage_id="test"), clean, source,
                            "writer", "reviewer", prior, unit="word", review_only=True)
    row, = w["candidates"]
    assert w["fresh_count"] == 0 and w["no_proposals_reason"] == ""
    assert row["proposal"] == old.model_dump() and row["previous_status"] == "accepted"
    assert row["status"] == "rejected" and row["issues"] == ["information_omitted"]
    assert row["checks"]["information_omitted"] == expected
    assert row["check_overrides"] == {"information_omitted": expected}
    assert row["reviews"][0]["checks"]["information_omitted"] == "yes"


def test_word_review_requires_concrete_evidence_and_recheck_preserves_history(tmp_path):
    review = auto.WordDecisions(decisions=[word_decision(1, "Detail lost.", information_loss=dict(kind="content_detail",
        source_information="The horse was white.", edited_information="A horse.", lost_content=""))])
    with pytest.raises(ValueError, match="Word review must explain"):
        auto.validate_reviews(review, [1])
    with pytest.raises(ValueError, match="requires --prior-bank"):
        auto.run_automatic(tmp_path/'manifest', tmp_path/'bank', tmp_path/'report', review_only=True)
    with pytest.raises(ValueError, match="separately"):
        auto.run_automatic(tmp_path/'manifest', tmp_path/'bank', tmp_path/'report', prior_bank_path=tmp_path/'bank')


def test_exact_word_deletion_is_verified_even_when_reviewer_misreads_the_original(monkeypatch, tmp_path):
    clean = {"1:1": "他的父亲大卫来了。"}
    source = Passage("Test", {"1:1": "His father David came."}, clean, "test")
    p = auto.Phrase(verse="1:1", english="David", chinese="大卫", english_occurrence=1, chinese_occurrence=1)
    prior = dict(candidates=[dict(proposal=p.model_dump(), status="accepted", issues=[])])
    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        assert stage == "review"
        c, = payload['candidates']
        assert c['original_chinese_verse'] == "他的父亲大卫来了。"
        assert c['edited_chinese_verse'] == "他的父亲来了。"
        assert c['exact_deletion'] == dict(verse="1:1", start=4, before="大卫", after="")
        result = auto.WordDecisions(decisions=[word_decision(
            1, "Mistakenly alleges extra punctuation was deleted.", deletion_only="no",
            information_loss=dict(kind="content_detail", source_information="His father David came.",
                                  edited_information="His father came.", lost_content="The father is David."))])
        validate(result)
        return result
    monkeypatch.setattr(auto, "ask", stub)
    w = auto.process_window(None, tmp_path, dict(window_id="test", passage_id="test"), clean, source,
                            "writer", "reviewer", prior, unit="word", review_only=True)
    c, = w['candidates']
    assert c['status'] == 'accepted' and c['checks']['deletion_only'] == 'yes'
    assert c['reviews'][0]['checks']['deletion_only'] == 'no'
    assert c['check_overrides'] == dict(deletion_only='yes')


@pytest.mark.parametrize("en,zh", [("Suddenly", "忽然，"), ("then", "就"), ("not", "不"), ("Therefore", "因此，")])
def test_excluded_markers_are_rejected_before_any_model_review(monkeypatch, tmp_path, en, zh):
    clean = {"1:1": f"他{zh}来了。"}
    source = Passage("Test", {"1:1": f"He {en} came."}, clean, "test")
    p = auto.Phrase(verse="1:1", english=en, chinese=zh, english_occurrence=1, chinese_occurrence=1)
    def unexpected(*args, **kwargs):
        pytest.fail("An excluded standalone marker must not reach the reviewer")
    monkeypatch.setattr(auto, "ask", unexpected)
    r = auto.process_window(None, tmp_path, dict(window_id="test", passage_id="test"), clean, source,
                            "writer", "reviewer", dict(candidates=[dict(proposal=p.model_dump(), status="accepted", issues=[])]),
                            unit="word", review_only=True)
    c, = r['candidates']
    assert c['status'] == 'rejected' and c['stage'] == 'eligibility_check'
    assert c['issues'] == ['key_content_removed'] and c['key_content_category'] == 'excluded_marker'
    assert c['resulting_verse'] == '他来了。'
    assert not auto.excluded_word_marker('不义')


@pytest.mark.parametrize("category,key_check,expected", [
    ("minor_detail", "yes", "no"), ("excluded_marker", "yes", "no"),
    ("not_key_content", "yes", "no"), ("uncertain", "yes", "uncertain"),
    ("significant_relationship", "no", "no"), ("significant_relationship", "uncertain", "uncertain"),
])
def test_meaning_loss_alone_cannot_bypass_key_content_gate(monkeypatch, tmp_path, category, key_check, expected):
    clean = {"1:1": "他买了新衣服。"}
    source = Passage("Test", {"1:1": "He bought new clothes."}, clean, "test")
    p = auto.Phrase(verse="1:1", english="new", chinese="新", english_occurrence=1, chinese_occurrence=1)
    def stub(client, folder, stage, model, prompt, payload, schema, validate):
        assert stage == 'review' and 'six required checks' in prompt
        d = word_decision(1, "Newness is an incidental attribute, not a key person, place or relationship.",
            dict(kind="content_detail", source_information="New clothes bought.",
                 edited_information="Clothes bought.", lost_content="Their newness."),
            category=category, key_check=key_check, flags=["other_meaning_changed"])
        result = auto.WordDecisions(decisions=[d]); validate(result); return result
    monkeypatch.setattr(auto, "ask", stub)
    r = auto.process_window(None, tmp_path, dict(window_id="test", passage_id="test"), clean, source,
                            "writer", "reviewer", dict(candidates=[dict(proposal=p.model_dump(), status="accepted", issues=[])]),
                            unit="word", review_only=True)
    c, = r['candidates']
    assert c['status'] == 'rejected' and c['issues'] == ['key_content_removed']
    assert c['checks']['information_omitted'] == 'yes' and c['checks']['key_content_removed'] == expected
    assert c['flags'] == ['other_meaning_changed']
