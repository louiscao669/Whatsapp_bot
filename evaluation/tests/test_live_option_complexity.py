"""Regression for a fixed key that stood out after the other choices were shortened."""
from evaluation.scripts.mcq.diagnostics import audit_live_option_complexity as reviewer


def test_judges_key_is_flagged_even_when_the_wording_reviewer_passes_it(tmp_path, monkeypatch):
    def pass_options(client, model, stem, window, options, *, correct_answer):
        return {"version": reviewer.complexity_version(), "model": model, "choices": {
            label: {"text": text, "verdict": "pass", "excerpt": "", "reason": ""}
            for label, text in options.items()}}

    monkeypatch.setattr(reviewer, "review_complexity", pass_options)
    item = {
        "id": "t1_judg9:iw06", "question": "约坦发出了怎样的咒诅？", "correct": "B",
        "verses": {"9:20": "愿火从亚比米勒那里出来，烧灭示剑和伯米罗的首领；也愿火从示剑和伯米罗的首领那里出来，烧灭亚比米勒。"},
        "choices": ["饥荒会摧毁示剑的田地。",
                    "愿火从亚比米勒那里出来，烧灭示剑和米罗的首领，也愿火从那些首领那里出来，烧灭亚比米勒。",
                    "亚比米勒会奴役示剑的首领，而他们又会奴役他。", "外邦军队会征服示剑和伯米罗。", "根据这段文字无法判断"],
    }
    # The key's individual pass is cached before the distractors are shortened.
    old_choices = list(item["choices"])
    old_choices[0] = "愿饥荒毁掉示剑和米罗的田地，瘟疫临到亚比米勒和他全家，使他的后代一个也不能存活。"
    assert reviewer.audit(tmp_path, "judge", None, dict(item, choices=old_choices))["B"]["verdict"] == "pass"

    result = reviewer.audit(tmp_path, "judge", None, item)
    assert [letter for letter, finding in result.items() if finding["verdict"] == "flag"] == ["B"]
    assert result["B"]["excerpt"] == item["choices"][1]
    assert "A=10, B=39, C=20, D=13" in result["B"]["reason"]
    assert "E" not in result

    item["choices"][1] = "愿亚比米勒和示剑、伯米罗的首领都被对方的火烧灭。"
    assert reviewer.audit(tmp_path, "judge", None, item)["B"]["verdict"] == "pass"
