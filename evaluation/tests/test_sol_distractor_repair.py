"""Exercise the routing, field scope, and two-round limit of the Chinese Sol pipeline."""
from copy import deepcopy
import json

import pytest

from evaluation.scripts.mcq.preparation import sol_distractors as pipeline


def held_item():
    row = dict(id="case", source="test", reference="1:1", passage_id="test",
               question="谁递交了信？", choices=["使者递交了信。", "守门人", "商人", "国王", "根据这段文字无法判断"],
               correct="A", verses={"1:1": "使者递交了信。"})
    last = dict(fixed_findings=["Fixed key stands out by length: too long"], findings=[], checks={})
    return dict(id="case", index=1, status="held", before=row, after=deepcopy(row), source_flags=[],
                attempts=[last])


@pytest.mark.parametrize(("question", "choices", "key", "echo", "avoidable", "screen"), [
    ("上帝帮助乌西雅对抗哪些敌人作战？",
     ["非利士人、住在姑珥巴力的阿拉伯人和亚扪人。", "非利士人、埃及人和米乌尼人。",
      "亚扪人、住在姑珥巴力的阿拉伯人和埃及人。", "上帝帮助乌西雅对抗非利士人、住在姑珥巴力的阿拉伯人和米乌尼人。"],
     "D", "上帝帮助乌西雅对抗", "上帝帮助乌西雅对抗", True),
    ("信由谁送来？", ["信是使者送来的。", "站岗的守门人。", "经常来往的外国商人。", "宫中的官员。"],
     "A", "信是", "", False),
    ("哪些城同时遭围？", ["城甲、城乙和城丙。", "城丁。", "城戊。", "城己。"], "A", "", "", True),
    ("谁送来了信？", ["使者", "守门人", "商人", "国王"], "A", "", "", False),
])
def test_key_cues_screen_the_final_menu_and_preserve_necessary_details(
        tmp_path, monkeypatch, question, choices, key, echo, avoidable, screen):
    def assess(client, model, prompt, data, schema):
        assert schema is pipeline.KeyCueReview
        assert data["length_screen"] is screen and set(data["options"]) == set("ABCD")
        assert data["lengths"] == dict(zip("ABCD", (sum(c.isalnum() for c in t) for t in choices)))
        return dict(redundant_stem_excerpt=echo, avoidable_length_excerpt=avoidable, reason="Reviewed.")
    monkeypatch.setattr(pipeline, "model_review", assess)
    row = dict(question=question, verses={"1:1": "经文。"}, choices=choices + ["无法根据这段经文判断。"], correct=key)
    cue, findings = pipeline.key_cue_review(None, row, tmp_path)
    assert cue["length_screen"] is screen
    assert len(findings) == bool(echo) + bool(avoidable)
    assert pipeline.fields_for_review(dict(checks={}, fixed_findings=findings, findings=[]), key) == (
        {key} if echo or avoidable else set())


def test_focused_audit_second_round_cannot_rewrite_a_distractor(tmp_path):
    item = dict(held_item(), key_only=True)
    item["repair"] = dict(review=dict(checks={}, fixed_findings=[], findings=["C (wording): long"]),
                          findings=["C (wording): long"], fidelity=dict(clear_question=True,
                          faithful_answer=True, same_target=True))
    result = pipeline.repair_once(item, item["before"], None, tmp_path, stage="second_repair")
    assert result["status"] == "held" and result["after"] == item["after"]
    assert result["second_repair"]["editable_fields"] == []
    assert "proposal" not in result["second_repair"]


def test_translation_review_routes_difficult_fields_independently_of_length(tmp_path, monkeypatch):
    item = held_item()
    row = item["after"]
    def assess(client, model, instructions, payload, schema):
        assert schema is pipeline.TranslationReview
        assert set(payload["fields"]) == set("QABCD") and "correct_letter" not in payload
        return {"findings": [{"field": field, "excerpt": payload["fields"][field], "reason": "Embedded report."}
                             for field in ("Q", "A", "B")]}
    monkeypatch.setattr(pipeline, "model_review", assess)
    last = pipeline.translation_review(None, row, tmp_path)
    assert pipeline.fields_for_review(last, "A") == {"Q", "A", "B"}
    assert len(last["fixed_findings"]) == 2 and len(last["findings"]) == 1
    monkeypatch.setattr(pipeline, "model_review", lambda *args: {"findings": []})
    assert pipeline.translation_review(None, row, tmp_path) == last
    assert not pipeline.fields_for_review(pipeline.translation_review(None, row, tmp_path/"plain"), "A")


def test_all_choices_drop_identical_reporting_clause_only_with_current_evidence():
    prefix = "军官告诉以利沙说："
    row = dict(question="军官对以利沙说了什么？", correct="B", choices=[
        prefix+"‘请派人守住城门。’", prefix+"‘看哪，这事真能发生吗？’",
        prefix+"‘耶和华必定会供应粮食。’", prefix+"‘明天会有粮食。’", "根据这段文字无法判断"])
    new = pipeline.apply_edits(row, ["B"], dict(edits=[dict(field="B", text="这事真能发生吗？")]))
    assert pipeline.dropped_shared_quote_frame(row, new)
    assert not pipeline.dropped_shared_quote_frame(row, row)
    cue = dict(redundant_stem_excerpt=prefix)
    corrected, edits = pipeline.remove_shared_stem_prefix(row, new, cue)
    assert list(edits) == ["A", "C", "D"]
    assert corrected["choices"] == ["请派人守住城门。", "这事真能发生吗？", "耶和华必定会供应粮食。",
                                    "明天会有粮食。", "根据这段文字无法判断"]
    assert pipeline.remove_shared_stem_prefix(row, row, cue) == (row, {})
    assert pipeline.remove_shared_stem_prefix(row, new, {}) == (new, {})
    mixed = dict(row, choices=["城门需要人看守。", *row["choices"][1:]])
    assert not pipeline.dropped_shared_quote_frame(mixed, new)
    assert pipeline.remove_shared_stem_prefix(mixed, new, cue) == (new, {})


def test_routes_only_current_findings_and_applicable_earlier_notes():
    held = held_item()
    held["attempts"][-1]["findings"] = ["C (wording): incidental title"]
    held["source_flags"] = [
        dict(field="Q", after=held["after"]["question"], kind="risk", note="unclear construction"),
        dict(field="D", after="obsolete", kind="risk", note="earlier text"),
    ]
    fields, findings = pipeline.repair_feedback(held)
    assert fields == ["Q", "A", "C"]
    assert findings == [*held["attempts"][-1]["fixed_findings"], "C (wording): incidental title",
                        "unclear construction"]
    held["source_flags"] = []
    held["attempts"][-1] = dict(fixed_findings=["Fixed question: unclear"], findings=[],
                               checks={"stem_issue": "ambiguous"})
    assert pipeline.repair_feedback(held)[0] == ["Q"]
    held["attempts"][-1] = dict(fixed_findings=[], findings=["D (wording): long"], checks={})
    assert pipeline.repair_feedback(held)[0] == ["D"]


@pytest.mark.parametrize(("supported", "status"), [(True, "passed"), (False, "held")])
def test_one_repair_checks_candidate_and_preserves_scope(tmp_path, monkeypatch, supported, status):
    item = held_item()
    calls = []
    def assess(client, model, prompt, data, schema):
        calls.append(schema.__name__)
        if schema is pipeline.Proposal:
            return dict(repairable=True, edits=[dict(field="A", text="使者")], reason="Remove repetition.")
        return dict(same_target=True, clear_question=True, faithful_answer=supported,
                    evidence="使者递交了信", reason="Fidelity verdict.")
    def review(client, candidate, folder, full_review):
        assert full_review and candidate["choices"] == ["使者", *item["after"]["choices"][1:]]
        return dict(fixed_findings=[], findings=[], checks={})
    monkeypatch.setattr(pipeline, "model_review", assess)
    monkeypatch.setattr(pipeline, "review_choices", review)
    result = pipeline.repair_once(item, item["before"], None, tmp_path)
    assert result["status"] == status
    assert result["repair"]["before"] == item["after"]
    if not supported:
        assert pipeline.repair_feedback(result, result["repair"]) == (["A"], ["Fidelity: Fidelity verdict."])
    assert pipeline.repair_once(result, item["before"], None, tmp_path) == result
    assert pipeline.repair_once(item, item["before"], None, tmp_path) == result
    assert calls == ["Proposal", "Fidelity"]


def test_unauthorized_edit_keeps_original_wording_and_scope_for_retry(tmp_path, monkeypatch):
    item = held_item()
    monkeypatch.setattr(pipeline, "model_review", lambda *args:
                        dict(repairable=True, edits=[dict(field="C", text="士兵")], reason="Change a distractor."))
    result = pipeline.repair_once(item, item["before"], None, tmp_path)
    assert result["status"] == "held" and result["after"] == item["after"]
    assert "out-of-scope" in result["repair"]["findings"][0]
    fields, findings = pipeline.repair_feedback(result, result["repair"])
    assert fields == ["A"]
    assert findings == result["repair"]["original_findings"] + result["repair"]["findings"]


@pytest.mark.parametrize("second_passes", [True, False])
def test_normal_batch_and_legacy_replay_route_only_remaining_findings(tmp_path, monkeypatch, second_passes):
    from_file = tmp_path / "inputs.json"
    bank = tmp_path / "bank"
    bank.mkdir()
    held = held_item()
    row = held["after"]
    for path, data in [(from_file, [dict(index=1, row=row)]), (bank/"zh.json", [row]),
                       (bank/"pilot_review.json", [dict(id=row["id"], status="eligible")])]:
        path.write_text(json.dumps(data))
    monkeypatch.setattr(pipeline, "OpenAI", lambda **kwargs: None)
    proposals = []
    def assess(client, model, prompt, data, schema):
        if schema is pipeline.AnswerMeaning:
            return dict(verdict="faithful", verse="1:1", quote="使者递交了信",
                        reader_meaning="The messenger.", reason="Directly supported.")
        if schema is pipeline.Proposal:
            proposals.append(data["editable_fields"])
            if data["editable_fields"] == ["A"]:
                return dict(repairable=True, edits=[dict(field="A", text="使者")], reason="Shorter key.")
            assert data["editable_fields"] == ["C"] and data["options"]["A"] == "使者"
            assert data["findings"] == ["C (wording): needs revision"]
            return dict(repairable=True, edits=[dict(field="C", text="商贩")], reason="Revise C.")
        return dict(same_target=True, clear_question=True, faithful_answer=True,
                    evidence="使者递交了信", reason="Supported.")
    def review(client, candidate, folder, full_review):
        assert full_review and candidate["choices"][0] == "使者"
        passed = second_passes and candidate["choices"][2] == "商贩"
        return dict(fixed_findings=[], findings=[] if passed else ["C (wording): needs revision"], checks={})
    monkeypatch.setattr(pipeline, "model_review", assess)
    monkeypatch.setattr(pipeline, "review_choices", review)
    monkeypatch.setattr(pipeline, "run_item", lambda *args: held)
    command = ["--inputs", str(from_file), "--bank", str(bank), "--output", str(tmp_path/"out")]
    pipeline.main(command)
    pipeline.main(command)
    final, = pipeline.read(tmp_path/"out/results.json")
    assert final["repair"]["status"] == "held"
    assert final["status"] == final["second_repair"]["status"] == ("passed" if second_passes else "held")
    assert final["after"]["choices"] == ["使者", "守门人", "商贩", "国王", "根据这段文字无法判断"]
    assert proposals == [["A"], ["C"]]
    # Even a second hold is terminal across separate replay runs.
    pipeline.main(["--repair-held-from", str(tmp_path/"out/results.json"), "--bank", str(bank),
                   "--output", str(tmp_path/"exhausted")])
    assert not (tmp_path/"exhausted").exists()
    # Earlier one-repair runs contain just the first record and the then-current candidate.
    legacy = dict(final, status="held", after=final["second_repair"]["before"])
    del legacy["second_repair"]
    pipeline.write(tmp_path/"legacy.json", [legacy, dict(legacy, id="already_passed", status="passed")])
    pipeline.main(["--repair-held-from", str(tmp_path/"legacy.json"), "--bank", str(bank),
                   "--output", str(tmp_path/"second")])
    assert proposals == [["A"], ["C"], ["C"]]
    assert pipeline.read(tmp_path/"second/results.json") == [final]


def test_contextual_drift_triggers_repair_even_when_key_is_the_best_option(tmp_path, monkeypatch):
    row = dict(id="door", source="test", reference="2 Kings 6:32", passage_id="elisha",
               question="以利沙告诉长老们做什么？", correct="A",
               choices=["关上门并留住他。", "给使者开门。", "请王进来。", "出门见王。", "根据这段文字无法判断"],
               verses={"6:32":"关上门，把他挡在外面。"})
    src = dict(row, question="What did Elisha tell the elders to do?",
               choices=["Shut and hold the door.", "Open it.", "Invite the king.", "Leave.", "Cannot tell."],
               verses={"6:32":"Shut the door to keep him out."})
    bank = tmp_path / "bank"
    bank.mkdir()
    for file, data in [("english", [src]), ("zh", [row]), ("pilot_review", [dict(id="door", status="eligible")])]:
        pipeline.write(bank / (file+".json"), data)
    pipeline.write(bank / "choice_release.json", {"zh_sha256":pipeline.sha256((bank/"zh.json").read_bytes()).hexdigest()})
    flags = [dict(field="A", after=row["choices"][0], kind="risk", note="Changed the object."),
             dict(field="A", after="已经删除的文字", kind="risk", note="Stale warning.")]
    pipeline.write(tmp_path/"prior.json",[dict(id="door",before=row,source_flags=flags)])
    corrected = "关上门，不让使者进来。"
    def assess(client, model, instructions, data, schema):
        if schema is pipeline.MenuDesignReview:
            return dict(findings=[])
        if schema is pipeline.AnswerMeaning:
            original = data["answer"] == row["choices"][0]
            assert data["source_answer"] == src["choices"][0]
            assert data["prior_risks"] == (["Changed the object."] if original else [])
            return dict(verdict="repair" if original else "faithful", verse="6:32",quote="把他挡在外面",
                        reader_meaning="Detain him." if original else "Keep him outside.",
                        reason="Check the object of the action.")
        if schema is pipeline.Proposal:
            assert data["editable_fields"]==["A"] and data["reference_answer"]==src["choices"][0]
            return dict(repairable=True, edits=[dict(field="A", text=corrected)], reason="Restore direction.")
        if schema in (pipeline.PremiseReview, pipeline.UsageReview):
            return dict(findings=[])
        if schema is pipeline.MenuWithCues:
            assert "correct_letter" not in data
            return dict(cues=[], choices=[dict(letter=l, verdict="supported" if l=="A" else "wrong",
                                      circular=False, reason="Checked.") for l in "ABCD"])
        assert schema is pipeline.Fidelity
        return dict(same_target=True, clear_question=True, faithful_answer=True,
                    evidence="把他挡在外面", reason="Preserves the instruction.")
    monkeypatch.setattr(pipeline,"model_review",assess)
    monkeypatch.setattr(pipeline,"OpenAI",lambda **kwargs:None)
    pipeline.main(["--bank",str(bank),"--audit-answer-meaning","--source-flags-from",str(tmp_path/"prior.json"),
                   "--output",str(tmp_path/"run")])
    result, = pipeline.read(tmp_path/"run/results.json")
    assert result["initial_status"]=="held" and result["status"]=="passed"
    assert result["after"]==dict(row,choices=[corrected,*row["choices"][1:]])
    assert result["repair"]["review"]["checks"]["answer_meaning"]["verdict"]=="faithful"


def test_normal_distractor_draft_cannot_pass_with_changed_key_meaning(tmp_path, monkeypatch):
    row = held_item()["before"]
    row["question"] = "以利沙吩咐长老做什么？"
    row["choices"][0] = "关门并留住使者。"
    row["verses"] = {"1:1": "关上门，把他挡在外面。"}
    source = dict(row, choices=["Keep the messenger out.", *row["choices"][1:]])
    draft = dict(zip("ABCD", row["choices"][:4]), correct="A")
    monkeypatch.setattr(pipeline.writer, "rewrite_distractors", lambda *args, **kw: draft)
    monkeypatch.setattr(pipeline, "review_choices", lambda *args: dict(checks={}, fixed_findings=[], findings=[]))
    monkeypatch.setattr(pipeline, "model_review", lambda *args: dict(
        verdict="repair", verse="1:1", quote="把他挡在外面", reader_meaning="Detain the messenger.",
        reason="Keeping someone there is different from keeping them outside."))
    result = pipeline.run_item(dict(index=1, row=row, meaning_source=source), None, tmp_path)
    assert result["status"] == "held" and len(result["attempts"]) == 1
    assert pipeline.repair_feedback(result)[0] == ["A"]


def test_supported_repair_with_a_giveaway_can_move_shared_actor_into_question(tmp_path, monkeypatch):
    row = dict(question="以利沙对疑问作出了什么宣告？", correct="C",
               choices=["他会先吃到细面", "他会付双倍的粮价", "那位军官会亲眼看见，却一点粮食也吃不到",
                        "他会在城门口分粮", "根据这段文字无法判断"], verses={"7:2":"你必亲眼看见，却一点也吃不到。"})
    cue = dict(letter="C", kind="shared_context", excerpt="那位军官", reason="All four choices concern him.")
    def assess(client, model, instructions, data, schema):
        assert schema is pipeline.MenuWithCues and "correct_letter" not in data
        return dict(cues=[cue], choices=[dict(letter=l, verdict="supported" if l=="C" else "wrong",
                                              reason="Reviewed.", circular=False) for l in "ABCD"])
    monkeypatch.setattr(pipeline, "model_review", assess)
    menu, findings = pipeline.check_repaired_menu(None, row, tmp_path)
    checks = dict(option_cues=menu["cues"])
    assert pipeline.fields_for_review(dict(checks=checks, fixed_findings=findings, findings=[]), "C")=={"Q","C"}
    assert not pipeline.key_shares_context(checks,"A")
    only_detail = dict(cue,kind="avoidable_detail",excerpt="亲眼")
    assert not pipeline.key_shares_context(dict(option_cues=[only_detail]),"C")


def test_distractor_refresh_respects_a_pinned_wrong_choice_during_review(tmp_path, monkeypatch):
    row = held_item()["before"]
    entry = dict(index=1, row=row, meaning_source=row, pinned_distractors=["C"], distractors_only=True)
    def rewrite(client, model, task, question, window, **kw):
        assert row["choices"][2] in kw["feedback"]
        return dict(A=row["choices"][0], B="官员", C="拟替换的选项", D="渔夫", correct="A")
    def review(client, candidate, folder):
        assert candidate["choices"][2]==row["choices"][2] and candidate["question"]==row["question"]
        return dict(checks={}, fixed_findings=[], findings=[])
    monkeypatch.setattr(pipeline.writer,"rewrite_distractors",rewrite)
    monkeypatch.setattr(pipeline,"review_choices",review)
    monkeypatch.setattr(pipeline,"meaning_review",lambda *args:dict(checks={},fixed_findings=[],findings=[]))
    result=pipeline.run_item(entry,None,tmp_path)
    assert result["status"]=="passed" and result["after"]["choices"]==[
        row["choices"][0],"官员",row["choices"][2],"渔夫",row["choices"][4]]


def test_unsupported_name_routes_to_stem_repair_and_role_passes(tmp_path, monkeypatch):
    verses = {"23:33": "骑兵把信交给总督，并把保罗带到他面前。"}
    actor = dict(name="斐利克斯", verdict="unsupported", verse="23:33", quote="把信交给总督",
                 suggested_description="总督", reason="The governor is unnamed.")
    paul = dict(name="保罗", verdict="grounded", verse="23:33", quote="把保罗带到他面前",
                suggested_description="", reason="The passage identifies the prisoner.")

    def assess(client, model, instructions, data, schema):
        assert set(data) == {"verses", "question"} and schema is pipeline.StemIdentityReview
        return {"names": [actor, paul] if "斐利克斯" in data["question"] else [paul]}

    monkeypatch.setattr(pipeline, "model_review", assess)
    before = dict(question="斐利克斯何时会审理保罗的案件？", verses=verses)
    finding = pipeline.stem_identity_review(None, before, tmp_path / "before")
    assert pipeline.fields_for_review(finding, "A") == {"Q"}
    assert "总督" in finding["fixed_findings"][0]
    after = dict(before, question="总督何时会审理保罗的案件？")
    passed = pipeline.stem_identity_review(None, after, tmp_path / "after")
    assert passed["fixed_findings"] == [] and passed["findings"] == []


def test_identity_check_rejects_a_quote_from_outside_the_window(tmp_path, monkeypatch):
    invented = dict(name="斐利克斯", verdict="grounded", verse="23:33", quote="斐利克斯总督",
                    suggested_description="", reason="Named in the text.")
    monkeypatch.setattr(pipeline, "model_review", lambda *args: {"names": [invented]})
    with pytest.raises(ValueError, match="passage evidence"):
        pipeline.stem_identity_review(None, {"question": "斐利克斯何时审理案件？",
                                             "verses": {"23:33": "骑兵把信交给总督。"}}, tmp_path)


@pytest.mark.parametrize("kind,key,expected", [
    ("unrelated_distractors", "B", set("QABCD")),
    ("name_matching", "A", set("QABCD")),
    ("menu_wordiness", "B", set("QABCD")),
    ("semantic_outlier", "C", set("ABD")),
])
def test_menu_design_repair_scope(kind, key, expected):
    letter = key if kind == "name_matching" else "D"
    issue = dict(kind=kind, letter=letter, excerpt="文字", reason="Test finding.")
    review = dict(checks=dict(menu_design=dict(findings=[issue])), findings=[], fixed_findings=[])
    assert pipeline.fields_for_review(review, key) == expected


@pytest.mark.parametrize("choices,pattern,confirmed", [
    (["饥荒临到，使居民灭亡。", "两方互相毁灭。", "他们赶走他，使他流亡。", "外军攻城，将首领掳走。"],
     "All three wrong choices", True),
    (["祭司砸碎了神像。", "但人拿走神像，带走祭司。", "但人抢走牲畜。", "但人索取贡品。"],
     "Only the key", True),
    (["他们交还神像，留下祭司。", "他们拿走神像，带走祭司。", "他们打碎神像。", "他们带走牲畜。"], "", False),
    (["他们说话。", "听完以后，他也说话。", "他们问话。", "他们回答。"], "Only the key", False),
    (["他们只问路。", "他们拿走神像又带走祭司。", "他们只借宿。", "他们只问安。"], "", True),
])
def test_clause_structure_review_routes_to_distractors(tmp_path, monkeypatch, choices, pattern, confirmed):
    row = dict(question="发生了什么事？", correct="B", verses={"1": "他们带走了祭司。"},
               choices=[*choices, "根据这段文字无法判断"])
    def assess(client, model, prompt, payload, schema):
        assert schema is pipeline.MenuDesignReview and "two-and-two" in prompt
        if pattern:
            assert payload["clause_screen"].startswith(pattern)
        else:
            assert "clause_screen" not in payload
        assert set(payload["options"]) == set("ABCD")
        return dict(findings=[dict(kind="clause_structure_cue", letter="B", excerpt=choices[1],
                                   reason="The key is the only choice with this construction.")] if confirmed else [])
    monkeypatch.setattr(pipeline, "model_review", assess)
    result = pipeline.menu_design_review(None, row, tmp_path)
    assert not result["fixed_findings"] and bool(result["findings"]) == confirmed
    assert pipeline.fields_for_review(result, "B") == (set("ACD") if confirmed else set())


@pytest.mark.parametrize("verdict,retire", [("hold", False), ("unsupported_target", True), ("unfair_menu", True)])
def test_exhausted_reviews_apply_only_to_verified_published_menu(tmp_path, monkeypatch, verdict, retire):
    result = held_item()
    row = result["before"]
    result["repair"] = dict(status="held", findings=["The first repair failed."])
    stages = pipeline.REPAIR_STAGES
    with pytest.raises(ValueError, match="completed failed repairs"):
        pipeline.final_mcq_review(None, row, row, result, stages, tmp_path)
    result["second_repair"] = dict(status="held", findings=["The second repair failed."])
    result["after"] = dict(row, question="未发表的改写？")
    def assess(client, model, prompt, task, schema):
        assert schema is pipeline.FinalMCQReview
        assert task["question"] == row["question"] and task["choices"]["A"] == row["choices"][0]
        return dict(verdict=verdict, target_support="unsupported" if verdict=="unsupported_target" else "supported",
                    repair_possible="yes" if verdict=="hold" else "no", verse="1:1", quote="使者递交了信",
                    missing_link="No stated motive.", menu_shortcut="Only one matching name.",
                    alternatives_considered="No other named people.", reason="Reviewed the published identity and choices.")
    monkeypatch.setattr(pipeline, "model_review", assess)
    result["final_mcq_review"] = pipeline.final_mcq_review(None, row, row, result, stages, tmp_path)
    bank = tmp_path / "bank"
    pipeline.write(bank/"zh.json",[row])
    release = dict(zh_sha256=pipeline.sha256((bank/"zh.json").read_bytes()).hexdigest())
    pipeline.write(bank/"choice_release.json",release)
    pipeline.write(bank/"pilot_review.json",[dict(id=row["id"], status="eligible")])
    pipeline.apply_final_retirements(bank,[result],release)
    saved = (bank/"pilot_review.json").read_bytes()
    assert pipeline.read(bank/"pilot_review.json")[0]["status"] == ("withheld" if retire else "eligible")
    pipeline.apply_final_retirements(bank,[result],release)
    assert saved == (bank/"pilot_review.json").read_bytes()
    stale = dict(row, choices=[*reversed(row["choices"][:4]), row["choices"][4]])
    with pytest.raises(ValueError, match="evidence"):
        pipeline.validate_final_review(stale,result["final_mcq_review"])


def test_later_repair_can_replace_a_rejected_clause_peer(tmp_path, monkeypatch):
    result = held_item()
    result["attempts"][0]["checks"] = {"menu_design": {"findings": [{"kind": "clause_structure_cue"}]}}
    result["repair"] = dict(review=dict(checks={}, findings=["C (wording): padded clause"], fixed_findings=[]),
                            fidelity=dict(same_target=True, faithful_answer=True, clear_question=True),
                            findings=["C (wording): padded clause"])
    result["pinned_distractors"] = ["B"]
    def proposal(client, model, instructions, task, schema):
        assert schema is pipeline.Proposal
        assert task["editable_fields"] == ["C", "D"]
        assert "Keep a structural peer" in task["clause_structure_guidance"]
        return dict(repairable=False, reason="No plausible alternative.", edits=[])
    monkeypatch.setattr(pipeline, "model_review", proposal)
    pipeline.repair_once(result, result["before"], None, tmp_path, stage="second_repair")


@pytest.mark.parametrize("peer", [False, True])
def test_shared_ending_does_not_mask_a_key_only_stem_prefix(tmp_path, monkeypatch, peer):
    opening = "他们被说成是"
    row = dict(question="在迦勒第一次宣称之后，他们被说成是什么？", correct="D", verses={"9:36":"你把山的影子看成人了。"},
               choices=[("他们被说成是" if peer else "")+"山脊上的石头，不是人。", "山上的羊群，不是人。",
                        "山坡上的树木，不是人。", opening+"山上的影子，不是人。", "根据这段文字无法判断"])
    def assess(client, model, prompt, task, schema):
        assert schema is pipeline.MenuDesignReview
        assert task.get("unique_stem_opening") == (None if peer else opening)
        return dict(findings=[] if peer else [dict(kind="asymmetric_frame", letter="D", excerpt=opening,
                                                   reason="Only the key repeats the reporting frame.")])
    monkeypatch.setattr(pipeline, "model_review", assess)
    review = pipeline.menu_design_review(None, row, tmp_path)
    assert bool(review["fixed_findings"]) != peer
    assert ("D" in pipeline.fields_for_review(review, "D")) != peer


def test_long_shared_scene_gets_a_separate_compression_judgment(tmp_path, monkeypatch):
    row = dict(question="有什么愿望？", correct="B", verses={"1":"甲地和乙地的首领。"},
               choices=["愿甲地和乙地的首领避开危险，全城的人都平安。",
                        "愿甲地和乙地的首领举起火把，两方的火都烧向对方。",
                        "愿甲地和乙地的首领离开那座城，进入山里。",
                        "愿甲地和乙地的首领欢喜快乐，所有的人都回来。", "根据这段文字无法判断"])
    def assess(client, model, prompt, data, schema):
        if schema is pipeline.MenuDesignReview:
            return dict(findings=[])
        assert schema is pipeline.SharedContextReview and "甲地和乙地的首领" in data["shared_span"]
        return dict(move_to_stem=True, reason="Name the shared leaders once.")
    monkeypatch.setattr(pipeline, "model_review", assess)
    outcome = pipeline.menu_design_review(None, row, tmp_path)
    assert outcome["checks"]["menu_design"]["findings"][0]["kind"] == "menu_wordiness"
    assert pipeline.fields_for_review(outcome, "B") == set("QABCD")


def test_list_modes_reconstruct_only_an_unbalanced_key():
    options = ["非利士人、阿拉伯人和埃及人。", "非利士人、亚扪人和米乌尼人。",
               "亚扪人、阿拉伯人和米乌尼人。", "非利士人、阿拉伯人和米乌尼人。"]
    assert pipeline.position_cue(options, "D") == ["非利士人", "阿拉伯人", "米乌尼人"]
    assert not pipeline.position_cue(options, "A")
    balanced = ["亚扪人、米乌尼人、阿拉伯人。", "阿拉伯人、非利士人、亚扪人。",
                "米乌尼人、亚扪人、非利士人。", "非利士人、阿拉伯人、米乌尼人。"]
    assert not pipeline.position_cue(balanced, "D")
    assert not pipeline.shared_distractor_members(balanced, "D")


def test_shared_distractor_ending_can_disclose_key_despite_passing_modes():
    choices = ["非利士人、阿拉伯人和亚扪人。", "非利士人、米乌尼人和亚扪人。",
               "阿拉伯人、米乌尼人和亚扪人。", "非利士人、阿拉伯人和米乌尼人。"]
    assert not pipeline.position_cue(choices, "D")
    assert pipeline.shared_distractor_members(choices, "D") == [(3, "亚扪人")]
    choices[-1] = "亚扪人、阿拉伯人和米乌尼人。"
    assert not pipeline.shared_distractor_members(choices, "D")


def test_partial_list_clue_keeps_both_surviving_answers():
    choices = ["耶何耶大、王和百姓", "耶和华、王和祭司", "耶何耶大、祭司和百姓", "耶和华、王和百姓"]
    assert pipeline.modal_shortlist(choices, "D") == ["A", "D"]
    assert not pipeline.position_cue(choices, "D")
    assert not pipeline.modal_shortlist(choices, "C")
    assert not pipeline.modal_shortlist(["甲、乙和丙", "乙、丙和丁", "丙、丁和甲", "丁、甲和乙"], "A")
    review = dict(checks={"list_shortlist": ["A", "D"]}, fixed_findings=["Partial clue"], findings=[])
    assert pipeline.fields_for_review(review, "D") == set("ABCD")


def test_readiness_import_uses_published_row_and_exact_held_roster():
    row = held_item()["before"]
    decision = dict(id="case", disposition="Further review", local_question=row["question"],
                    local_choices=row["choices"], clean_verses=row["verses"], key="A",
                    question="另一道题？", set="Prepared", finding=dict(reason="Repeated frame.", next_step="Shorten."))
    release = dict(held_for_review=["case"])
    bank = {"case":row}
    entry, = pipeline.readiness_repair_inputs([decision], bank, release)
    assert entry["before"] == row == entry["after"]
    assert entry["editorial_concern"] == "Repeated frame."
    with pytest.raises(ValueError, match="exactly once"):
        pipeline.readiness_repair_inputs([decision, decision], bank, release)
    with pytest.raises(ValueError, match="Stale"):
        pipeline.readiness_repair_inputs([dict(decision, local_question="旧版本？")], bank, release)


def test_fourth_round_uses_latest_review_and_preserves_manual_lineage(tmp_path, monkeypatch):
    item = held_item()
    row = item["before"]
    result = dict(item)
    calls = []
    def assess(client, model, instructions, task, schema):
        if schema is pipeline.Proposal:
            calls.append(task["editable_fields"])
            if len(calls) == 3:
                return dict(repairable=False, edits=[], reason="First approach unavailable.")
            field, text = {1:("A", "使者"), 2:("C", "商贩"), 4:("C", "卫兵")}[len(calls)]
            return dict(repairable=True, edits=[dict(field=field, text=text)], reason="Revise field.")
        assert schema is pipeline.Fidelity
        return dict(same_target=True, clear_question=True, faithful_answer=True,
                    evidence="使者", reason="Supported.")
    def review(client, candidate, folder, *, full_review):
        return dict(checks={}, fixed_findings=[],
                    findings=[] if candidate["choices"][2] == "卫兵" else ["C (wording): unclear role"])
    monkeypatch.setattr(pipeline, "model_review", assess)
    monkeypatch.setattr(pipeline, "review_choices", review)
    for stage in pipeline.EXTENDED_REPAIR_STAGES:
        result = pipeline.repair_once(result, row, None, tmp_path / stage, stage=stage)
    assert result["status"] == "passed" and calls == [["A"], ["C"], ["C"], ["C"]]
    assert pipeline.retained_manual_fields(result, row, ["Q","A","B","C"]) == ["Q","B"]


def test_regular_batch_repairs_remaining_wrong_choice_only_findings(tmp_path, monkeypatch):
    item = held_item()
    row = item["after"]
    item["attempts"] = [dict(checks={}, fixed_findings=[], findings=["C (wording): Distant distractor."])]
    bank = tmp_path / "bank"
    pipeline.write(bank / "zh.json", [row])
    pipeline.write(bank / "pilot_review.json", [dict(id=row["id"], status="eligible")])
    pipeline.write(tmp_path / "input.json", [dict(index=1, row=row)])
    monkeypatch.setattr(pipeline, "OpenAI", lambda **kw: None)
    monkeypatch.setattr(pipeline, "run_item", lambda *args: item)
    def repair(result, reference, client, folder, *, stage, meaning_source):
        assert stage == "repair" and pipeline.repair_feedback(result)[0] == ["C"]
        candidate = dict(row, choices=[*row["choices"][:2], "祭司", *row["choices"][3:]])
        return dict(result, status="passed", after=candidate, repair=dict(before=row))
    monkeypatch.setattr(pipeline, "repair_once", repair)
    pipeline.main(["--inputs", str(tmp_path / "input.json"), "--bank", str(bank), "--output", str(tmp_path / "run")])
    result, = pipeline.read(tmp_path / "run/results.json")
    assert result["status"] == "passed" and result["after"]["choices"][2] == "祭司"


def test_editorial_repair_uses_reviewed_draft_and_rejects_stale_bank(tmp_path):
    local = held_item()["before"]
    draft = dict(local, question="是谁？")
    item = dict(index=1, id=local["id"], local=local, row=draft, checks={},
                issues=[], source="Repair draft")
    decision = dict(index=1, id=item["id"], category="Additional editorial review", reason="Unclear referent.")
    pipeline.write(tmp_path / "results.json", [item])
    pipeline.write(tmp_path / "dispositions.json", dict(items=[decision]))
    entry, = pipeline.editorial_repair_inputs(tmp_path, {local["id"]: local})
    assert entry["before"] == draft and entry["editorial_concern"] == decision["reason"]
    assert pipeline.repair_feedback(entry)[0] == list("QABCD")
    with pytest.raises(ValueError, match="Stale"):
        pipeline.editorial_repair_inputs(tmp_path, {local["id"]: draft})
    decision["category"] = "No material issue identified"
    pipeline.write(tmp_path / "dispositions.json", dict(items=[decision]))
    assert pipeline.editorial_repair_inputs(tmp_path, {local["id"]: local}) == []


def test_editorial_concern_must_be_resolved_after_repair(tmp_path, monkeypatch):
    item = held_item()
    item["editorial_concern"] = "The key stands out."
    def assess(client, model, prompt, data, schema):
        if schema is pipeline.Proposal:
            return dict(repairable=True, edits=[dict(field="A", text="使者")], reason="Shorter.")
        if schema is pipeline.EditorialVerdict:
            assert data["concern"] == item["editorial_concern"] and data["choices"]["A"] == "使者"
            return dict(resolved=False, fields=["B", "C", "D"], reason="The alternative roles still give away A.")
        assert schema is pipeline.Fidelity
        return dict(same_target=True, clear_question=True, faithful_answer=True, evidence="使者", reason="Supported.")
    monkeypatch.setattr(pipeline, "model_review", assess)
    monkeypatch.setattr(pipeline, "review_choices", lambda *a, **kw: dict(checks={}, fixed_findings=[], findings=[]))
    item = pipeline.repair_once(item, item["before"], None, tmp_path)
    assert item["status"] == "held"
    assert pipeline.repair_feedback(item, item["repair"])[0] == ["B", "C", "D"]


def test_wrong_target_allows_restoring_identity_choices():
    result = held_item()
    previous = dict(review=dict(checks={}, findings=[], fixed_findings=[]), findings=["Target changed."],
                    fidelity=dict(clear_question=True, same_target=False, faithful_answer=True))
    assert pipeline.repair_feedback(result, previous)[0] == list("QABCD")


def replacement_case():
    prior = held_item()
    row = prior["after"]
    spec = dict(replaces=row["id"], replacement_id="case@object", held_sha256=pipeline.digest(row),
                correct="A", question="使者递交了什么？", choices=["信", "书", "钱", "钥匙"],
                target=dict(question="What did the messenger deliver?", answer="A letter."),
                verse="1:1", quote="递交了信", concern="Only one delivered object is supported.")
    return prior, spec


def test_replacement_requires_distinct_identity_and_matching_held_wording():
    prior, spec = replacement_case()
    bank = {prior["id"]: prior["after"]}
    for invalid in (dict(spec, replacement_id=prior["id"]), dict(spec, held_sha256="stale"),
                    dict(spec, quote="经文之外"), dict(spec, correct="B")):
        with pytest.raises(ValueError):
            pipeline.replacement_inputs([invalid], [prior], bank)
    with pytest.raises(ValueError, match="matching held wording"):
        pipeline.replacement_inputs([spec], [dict(prior, status="passed")], bank)


@pytest.mark.parametrize("outcome", ["pass", "repair", "reject", "service_error"])
def test_approved_replacement_uses_new_target_and_excludes_failed_items(tmp_path, monkeypatch, outcome):
    prior, spec = replacement_case()
    spec["manually_written_fields"] = list("QABCD")
    chinese = prior["after"]
    english = dict(chinese, question="Who delivered the letter?", choices=["The messenger", "A guard", "A merchant", "The king", "Unknown"])
    bank = tmp_path / "bank"
    pipeline.write(bank / "zh.json", [chinese])
    pipeline.write(bank / "english.json", [english])
    pipeline.write(bank / "pilot_review.json", [dict(id=prior["id"], status="eligible")])
    pipeline.write(bank / "choice_release.json", dict(zh_sha256=pipeline.sha256((bank / "zh.json").read_bytes()).hexdigest()))
    pipeline.write(tmp_path / "held.json", [prior])
    pipeline.write(tmp_path / "approved.json", [spec])
    monkeypatch.setattr(pipeline, "OpenAI", lambda **kw: None)
    calls = []
    def blind(client, row, directory, *, full_review):
        assert full_review and row["id"] == spec["replacement_id"] and row["choices"][4] == chinese["choices"][4]
        if outcome == "service_error":
            raise RuntimeError("Reviewer unavailable")
        issue = [] if outcome == "pass" or row["choices"][1] == "包裹" else ["B (wording): ambiguous alternative"]
        return dict(checks={}, fixed_findings=[], findings=issue)
    def assess(client, model, prompt, data, schema):
        if schema is pipeline.TargetSupport:
            assert data["target"] == spec["target"] and data["clean_verses"] == chinese["verses"]
            return dict(verdict="supported", passage_claim="The messenger delivered a letter.",
                        target_claim="A letter was delivered.", missing_link="", verse="1:1", quote="递交了信")
        if schema is pipeline.AnswerMeaning:
            assert data["source_question"] == spec["target"]["question"] and data["source_answer"] == "A letter."
            return dict(verdict="faithful", target_changed=False, reader_meaning="A letter", verse="1:1",
                        quote="递交了信", reason="Supported.")
        if schema is pipeline.Fidelity:
            assert data["reference_question"] == spec["target"]["question"]
            return dict(same_target=True, clear_question=True, faithful_answer=True, evidence="递交了信", reason="Supported.")
        if schema is pipeline.EditorialVerdict:
            return dict(resolved=True, fields=[], reason="The requested fact is supported.")
        assert schema is pipeline.Proposal and data["reference_answer"] == "A letter."
        calls.append(data["editable_fields"])
        if outcome == "reject":
            return dict(repairable=False, edits=[], reason="No defensible alternative for B.")
        return dict(repairable=True, edits=[dict(field="B", text="包裹")], reason="Ambiguity removed.")
    monkeypatch.setattr(pipeline, "review_choices", blind)
    monkeypatch.setattr(pipeline, "model_review", assess)
    out = tmp_path / "out"
    argv = ["--review-replacements", str(tmp_path / "approved.json"), "--held-results", str(tmp_path / "held.json"),
            "--output", str(out), "--bank", str(bank)]
    if outcome == "service_error":
        with pytest.raises(SystemExit):
            pipeline.main(argv)
        assert pipeline.read(out / "errors.json") and not (out / "selection.json").exists()
        return
    pipeline.main(argv)
    pipeline.main(argv)  # Completed runs reuse their decisions.
    result, = pipeline.read(out / "results.json")
    selection = pipeline.read(out / "selection.json")
    assert selection["excluded_originals"] == [prior["id"]] and result["old_target"]["question"] == english["question"]
    if outcome == "reject":
        assert result["status"] == "rejected" and calls == [["B"], ["B"]]
        assert selection["candidates"] == [] and selection["rejected"][0]["reasons"]
    else:
        assert result["status"] == "passed" and calls == ([["B"]] if outcome == "repair" else [])
        assert selection["candidates"][0]["row"] == result["after"]
        expected_fields = list("QACD" if outcome == "repair" else "QABCD")
        assert selection["candidates"][0]["manually_written_fields"] == result["manually_written_fields"] == expected_fields
        assert selection["candidates"][0]["row"]["id"] != prior["id"] and selection["rejected"] == []


def test_unsupported_target_cannot_pass_by_matching_its_own_key(tmp_path, monkeypatch):
    row = dict(held_item()["after"], verses={"18:7": "那地一无所缺。"})
    spec = dict(replaces=row["id"], replacement_id="case@observation",
                target=dict(question="What did the men observe?", answer="Residents had everything they needed."),
                verse="18:7", quote="那地一无所缺", concern="An observation in Laish.")
    def judge(client, model, prompt, data, schema):
        assert schema is pipeline.TargetSupport
        assert set(data) == {"target", "clean_verses", "cited_verse", "cited_phrase"}
        return dict(verdict="unsupported", passage_claim="The land lacked nothing.",
                    target_claim="The residents had everything they needed.", verse="18:7", quote="那地一无所缺",
                    missing_link="The passage does not say that the people obtained everything they needed.")
    monkeypatch.setattr(pipeline, "model_review", judge)
    monkeypatch.setattr(pipeline, "review_choices", lambda *a, **kw: pytest.fail("Unsupported target reached menu review"))
    result = pipeline.review_replacement(dict(row=row, approval=spec, index=1), row, None, tmp_path)
    assert result["status"] == "rejected" and "repair" not in result
    assert "obtained" in result["rejection_reasons"][0] and not pipeline.replacement_selection([result])["candidates"]


def test_unsupported_speaker_suggestion_is_not_sent_to_writer(tmp_path, monkeypatch):
    item = held_item()
    row = item["after"]
    row.update(question="发言者认为，立亚比米勒为王的人应当报答谁？",
               verses={"9:16": "你们立亚比米勒为王，若是善待耶路巴力和他的家，若是照他应得的报答他。"})
    issue = dict(field="Q", kind="unclear_reference", excerpt="发言者认为",
                 verse="9:16", quote="照他应得的报答他", reason="Replace the unnamed speaker with 约坦.")
    finding = "Fixed question (unclear_reference): “发言者认为”. " + issue["reason"]
    item["attempts"] = [dict(checks={"chinese_usage": {"findings": [issue]}},
                             fixed_findings=[finding], findings=[])]
    def writer(client, model, prompt, task, schema):
        assert schema is pipeline.Proposal and task["editable_fields"] == ["Q"]
        assert "约坦" not in json.dumps(task, ensure_ascii=False)
        assert "照他应得的报答他" in task["findings"][0]
        assert "speaker" in task["stem_guidance"]
        return dict(repairable=False, edits=[], reason="Test proposal.")
    monkeypatch.setattr(pipeline, "model_review", writer)
    result = pipeline.repair_once(item, row, None, tmp_path)
    assert result["repair"]["original_findings"] == [finding]


def test_draft_audit_checks_original_unknown_and_preserves_recorded_concern(tmp_path, monkeypatch):
    row = held_item()["after"]
    source = dict(row, question="Who delivered the letter?", choices=["The messenger.", *row["choices"][1:]])
    draft = dict(row, question="使者对这封信而言扮演了什么角色？",
                 choices=["递交信的人", "读信的人", "写信的人", "收信的人", row["choices"][4]])
    for filename, contents in [("zh.json", [row]), ("english.json", [source]),
                               ("pilot_review.json", [dict(id=row["id"], status="eligible")])]:
        pipeline.write(tmp_path / "bank" / filename, contents)
    bank = tmp_path / "bank"
    pipeline.write(bank / "choice_release.json", {"zh_sha256":pipeline.sha256((bank / "zh.json").read_bytes()).hexdigest()})
    inputs = tmp_path / "input.json"
    pipeline.write(inputs,[dict(index=1, row=draft, editorial_concern="Preserve the identity question.")])
    monkeypatch.setattr(pipeline,"OpenAI",lambda **kw:None)
    def blind(client, actual, folder, *, full_review):
        assert full_review and actual == draft
        return dict(checks={}, fixed_findings=[], findings=[])
    monkeypatch.setattr(pipeline,"review_choices",blind)
    def assess(client, model, prompt, task, schema):
        if schema is pipeline.AnswerMeaning:
            assert task["source_question"] == source["question"] and task["question"] == draft["question"]
            return dict(verdict="repair", target_changed=True, verse="1:1", quote="使者递交了信",
                        reader_meaning="The messenger delivered it.", reason="The stem gives away who.")
        assert schema is pipeline.EditorialVerdict and task["concern"] == "Preserve the identity question."
        return dict(resolved=False, fields=list("QABCD"), reason="Role replaces identity.")
    monkeypatch.setattr(pipeline,"model_review",assess)
    pipeline.main(["--audit-draft-wording",str(inputs),"--bank",str(bank),
                   "--output",str(tmp_path/"out"),"--inspect-only"])
    item, = pipeline.read(tmp_path/"out"/"results.json")
    assert item["status"] == "held" and item["before"] == item["after"] == draft
    assert item["attempts"][0]["checks"]["answer_meaning"]["target_changed"]
    assert item["editorial_concern"] == "Preserve the identity question."


def test_window_review_checks_assumed_roles_and_routes_the_precise_fields(tmp_path, monkeypatch):
    row = dict(question="神人为什么拒绝王的提议？", choices=["军长", "祭司长", "长老", "使者", "无法判断"],
               correct="A", verses={"1": "神人却回答。", "2": "向千夫长提出请求。"})
    def assess(client, model, prompt, payload, schema):
        assert "correct" not in payload
        if schema is pipeline.PremiseReview:
            assert set(payload) == {"question", "verses"}
            return dict(findings=[dict(excerpt="王的提议", verse="1", quote="神人却回答",
                                       reason="The reply does not identify the addressee.")])
        assert schema is pipeline.UsageReview
        return dict(findings=[dict(field="A", kind="terminology", excerpt="军长", verse="2",
                                   quote="向千夫长提出请求", reason="Different military rank.")])
    monkeypatch.setattr(pipeline, "model_review", assess)
    review = pipeline.window_wording_review(None, row, tmp_path)
    assert pipeline.fields_for_review(review, "A") == {"Q", "A"}
    assert len(review["fixed_findings"]) == 2
    row["verses"] = {"1": "对方答话。", "2": "向千夫长提出请求。"}
    with pytest.raises(ValueError, match="passage evidence"):
        pipeline.window_wording_review(None, row, tmp_path / "new_window")


def test_stem_uses_the_displayed_council_label_and_accepts_a_local_short_form():
    row = dict(question="谁要去公会？", verses={"1": "向公议会提出请求。"})
    finding, = pipeline.local_title_findings(row, [])
    assert (finding["field"], finding["quote"]) == ("Q", "公议会")
    assert pipeline.local_title_findings(row, [finding]) == [finding]
    assert not pipeline.local_title_findings(dict(row, question="谁要去公议会？"), [])
    assert not pipeline.local_title_findings(dict(row, verses={"1": "他在公会，也就是公议会发言。"}), [])


def test_key_only_second_repair_can_fix_a_stem_rejected_by_fidelity(tmp_path, monkeypatch):
    item = dict(held_item(), key_only=True, meaning_only=True)
    item["repair"] = dict(review=dict(checks={}, fixed_findings=[], findings=[]),
                          findings=["The speaker and pronoun are unclear."],
                          fidelity=dict(clear_question=False, same_target=True, faithful_answer=True))
    def writer(client, model, prompt, task, schema):
        assert schema is pipeline.Proposal
        assert task["editable_fields"] == ["Q"]
        assert "speaker" in task["stem_guidance"]
        return dict(repairable=False, edits=[], reason="No faithful rewording here.")
    monkeypatch.setattr(pipeline, "model_review", writer)
    result = pipeline.repair_once(item, item["before"], None, tmp_path, stage="second_repair")
    assert result["second_repair"]["editable_fields"] == ["Q"]


def test_only_a_confirmed_parallel_trailing_clause_is_removed(tmp_path, monkeypatch):
    row = dict(correct="D", question="他们被说成是什么？", verses={"9:36":"你把山的影子看成人了。"},
               choices=["石头，不是人。", "羊群，不是人。", "树木，不是人。",
                                     "山的影子，不是人。", "根据这段文字无法判断"])
    candidate = dict(row, question="西布勒说迦勒把什么看成了人？",
                     choices=[*row["choices"][:3], "山的影子。", row["choices"][4]])
    after, edits = pipeline.remove_shared_stem_suffix(row, candidate, {"redundant_stem_excerpt": "不是人。"})
    assert after["choices"] == ["石头。", "羊群。", "树木。", "山的影子。", row["choices"][4]]
    assert set(edits) == set("ABC")
    assert pipeline.remove_shared_stem_suffix(row, candidate, {}) == (candidate, {})
    def approve(client, model, prompt, task, schema):
        assert task["before"][-1] == task["after"][-1] == "山的影子。"
        assert set(task["changed_letters"]) == set("ABC")
        return dict(redundant=True, reason="The stem already supplies the contrast.")
    monkeypatch.setattr(pipeline, "model_review", approve)
    assert pipeline.review_dropped_suffix(None, row, candidate, tmp_path) == (after, edits)
