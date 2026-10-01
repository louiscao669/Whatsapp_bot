"""rebalance_mcq_options: measurement, selection, validation gate, apply/sync. No API calls."""
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.scripts.pipeline import rebalance_mcq_options as rb

PASSAGE = "\n".join([
    "1 王对神人说：“请同我回家，歇息，我必给你赏赐。”",
    "2 神人回答说：“即使你给我一半的家产，我也不跟你去，也不在这地方吃饭喝水。",
    "3 因为我奉耶和华的话被吩咐说：‘你不可吃饭喝水，也不可照来时的路回去。’”",
    "4 于是神人从别的路回去，不从伯特利来的路回去。",
])
REF = "Test 1:1-4"


def item(options, key="C", q="王对神人说了什么？", pid="uw-t1_test:aaaa-mcq", window=(1, 2, 3)):
    return {"q_type": "mcq", "Q": q, "A": dict(options), "correct": key, "passage_id": pid,
            "passage_reference": REF, "reference": "1:1", "window_verses": list(window)}


STANDS_OUT = {"A": "建造新的祭坛", "B": "立刻离开伯特利", "C": "请同我回家", "D": "为我的国祷告",
              "E": "根据这段文字无法判断"}


class StubLLM:
    """generate -> fixed candidates; judge -> key text 'correct', listed texts as given, rest incorrect."""

    def __init__(self, candidates, key_text="请同我回家", verdicts=None, key_supported=True):
        self.candidates = candidates
        self.key_text = key_text
        self.verdicts = verdicts or {}
        self.key_supported = key_supported
        self.calls = []

    def __call__(self, role, system, user):
        self.calls.append(role)
        payload = json.loads(user)
        if role == "generate":
            return {"candidates": [{"text": t, "source": "v", "why_wrong": "w"} for t in self.candidates]}
        out = []
        for letter, text in payload["options"].items():
            if text == self.key_text:
                label = "correct" if self.key_supported else "incorrect"
            else:
                label = self.verdicts.get(text, "incorrect")
            out.append({"letter": letter, "label": label, "reason": ""})
        return {"options": out}


def ctx():
    return rb.PassageContext(PASSAGE, REF)


class MeasureTests(unittest.TestCase):
    def test_overlap_ratio_is_longest_contiguous_span(self):
        window = rb.normalize("王对神人说：请同我回家")
        self.assertEqual(rb.overlap_ratio("请同我回家", window), 1.0)
        self.assertAlmostEqual(rb.overlap_ratio("请你回家", window), 0.5)
        self.assertEqual(rb.overlap_ratio("", window), 0.0)

    def test_classify_flags_key_that_stands_out(self):
        record = item(STANDS_OUT)
        stats = rb.measure(rb.content_options(record), "C", ctx().window_for(record))
        self.assertEqual(rb.classify(stats, 0.15), "key_stands_out")
        self.assertNotIn("E", stats["ratios"])  # the meta-option is never measured

    def test_window_verses_use_the_item_reference_chapter(self):
        passage = "\n".join(["17 甲事。", "2 乙事。", "18 丙事。", "2 丁事。", "3 戊事。"])
        c = rb.PassageContext(passage, "Judges 17:1-18:3")
        record = {"window_verses": [2, 3], "reference": "18:2", "passage_reference": "Judges 17:1-18:3"}
        self.assertEqual(c.window_for(record), rb.normalize("2 丁事。3 戊事。"))


class RebalanceTests(unittest.TestCase):
    def test_rebalances_with_window_phrases_and_keeps_key_and_E(self):
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去", "从别的路回去"])
        record = item(STANDS_OUT)
        result = rb.rebalance_item(record, ctx(), llm)
        self.assertEqual(result.status, "rebalanced", result.reason)
        self.assertEqual(result.new_options["C"], "请同我回家")
        self.assertLessEqual(abs(result.after["gap"]), 0.15)
        self.assertEqual(llm.calls, ["generate", "judge"])
        rb.apply_to_records([record], {result.item_id: result}, {"date": "x"})
        self.assertEqual(record["A"]["E"], "根据这段文字无法判断")
        self.assertEqual(record["correct"], "C")
        self.assertIn("replaced", record["option_rebalance"])

    def test_validator_rejection_bans_candidate_and_reselects(self):
        bad = "在这地方吃饭喝水"
        llm = StubLLM(["给我一半的家产", bad, "照来时的路回去", "从别的路回去"],
                      verdicts={bad: "ambiguous"})
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm)
        self.assertIn(result.status, ("rebalanced", "partial"))
        self.assertNotIn(bad, result.new_options.values())
        self.assertEqual(llm.calls.count("judge"), 2)

    def test_unsupported_key_is_left_for_review(self):
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去"], key_supported=False)
        record = item(STANDS_OUT)
        result = rb.rebalance_item(record, ctx(), llm)
        self.assertEqual(result.status, "needs_review")
        self.assertFalse(result.changed)
        self.assertEqual(rb.apply_to_records([record], {result.item_id: result}, {}), 0)
        self.assertEqual(record["A"], STANDS_OUT)

    def test_all_candidates_rejected_is_needs_review(self):
        cands = ["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去"]
        llm = StubLLM(cands, verdicts={c: "correct" for c in cands})
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm, max_rounds=3)
        self.assertEqual(result.status, "needs_review")

    def test_balanced_item_makes_no_calls(self):
        llm = StubLLM([])
        balanced = {"A": "给我一半的家产", "B": "照来时的路回去", "C": "请同我回家", "D": "从别的路回去"}
        result = rb.rebalance_item(item(balanced), ctx(), llm)
        self.assertEqual(result.status, "balanced")
        self.assertEqual(llm.calls, [])

    def test_dominating_distractor_judged_correct_is_replaced(self):
        # B is verbatim and also a correct answer (an alias of the key, per the stub)
        opts = {"A": "建造祭坛", "B": "请同我回家，歇息", "C": "跟他到府上", "D": "祷告"}
        llm = StubLLM(["那神人", "别的路", "赏赐"], key_text="跟他到府上",
                      verdicts={"请同我回家，歇息": "correct"})
        result = rb.rebalance_item(item(opts), ctx(), llm)
        self.assertEqual(result.reason, "distractor_dominates")
        self.assertEqual(result.status, "replaced_second_correct")
        self.assertNotIn("请同我回家，歇息", result.new_options.values())

    def test_dominating_distractor_validated_wrong_is_only_checked(self):
        opts = {"A": "建造祭坛", "B": "请同我回家，歇息", "C": "跟他到府上", "D": "祷告"}
        llm = StubLLM([], key_text="跟他到府上")
        result = rb.rebalance_item(item(opts), ctx(), llm)
        self.assertEqual(result.status, "checked")
        self.assertEqual(llm.calls, ["judge"])

    def test_stem_echo_is_avoided_when_alternatives_exist(self):
        q = "王对神人说了什么？"
        pool = [rb.Candidate("王对神人说", "new"), rb.Candidate("给我一半的家产", "new"),
                rb.Candidate("照来时的路回去", "new"), rb.Candidate("从别的路回去", "new")]
        record = item(STANDS_OUT, q=q)
        chosen = rb.choose_set(record, ctx().window_for(record), pool, set())
        self.assertNotIn("王对神人说", [c.text for c in chosen])

    def test_candidates_that_restate_the_key_are_dropped(self):
        kept = rb.clean_candidates([{"text": "请同我回家吧"}, {"text": "给我一半的家产"}],
                                   "请同我回家", ["建造新的祭坛"])
        self.assertEqual([c.text for c in kept], ["给我一半的家产"])


class ApplyTests(unittest.TestCase):
    def test_apply_skips_copies_whose_options_were_already_edited(self):
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去", "从别的路回去"])
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm)
        edited = item({**STANDS_OUT, "A": "手改过的选项"})
        self.assertEqual(rb.apply_to_records([edited], {result.item_id: result}, {}), 0)
        self.assertEqual(edited["A"]["A"], "手改过的选项")

    def test_sync_copies_by_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = root / "t1_x" / "omission" / "0%"
            other = root / "t1_x" / "llama" / "grammar" / "30%"
            for d in (ref, other):
                d.mkdir(parents=True)
            new = item({**STANDS_OUT, "A": "新的"}, pid="p")
            old = item(STANDS_OUT, pid="p")
            for name in ("qa_target.json", "qa_target_decanonicalized.json"):
                (ref / name).write_text(json.dumps([new], ensure_ascii=False), encoding="utf-8")
                (other / name).write_text(json.dumps([old], ensure_ascii=False), encoding="utf-8")
            self.assertEqual(rb.sync_copies(root, "t1_x", "omission/0%"), 2)
            synced = json.loads((other / "qa_target.json").read_text(encoding="utf-8"))
            self.assertEqual(synced[0]["A"]["A"], "新的")
            self.assertTrue(list(other.glob("qa_target.json.bak_rebalance_*")))


class OpenAICallerTests(unittest.TestCase):
    def test_reasoning_effort_sent_and_falls_back_to_temperature(self):
        seen = []

        class Resp:
            output_text = '{"candidates": []}'

        class Responses:
            def create(self, **kwargs):
                seen.append(kwargs)
                if "reasoning" in kwargs and kwargs["model"] == "classic":
                    raise ValueError("Unsupported parameter: 'reasoning'")
                return Resp()

        class Client:
            responses = Responses()

        call = rb.openai_llm("classic", "gpt-6-astra", "high", retries=1, client=Client())
        self.assertEqual(call("generate", "s", "u"), {"candidates": []})
        self.assertEqual(seen[-1]["temperature"], 0)
        self.assertNotIn("reasoning", seen[-1])
        call("judge", "s", "u")
        self.assertEqual(seen[-1]["reasoning"], {"effort": "high"})
        self.assertEqual(seen[-1]["text"], {"format": {"type": "json_object"}})


if __name__ == "__main__":
    unittest.main()


class MainStageTests(unittest.TestCase):
    def _args(self, out):
        import argparse
        return argparse.Namespace(
            output_dir=out, stop_after=None, force=False, force_rebalance=False,
            force_passage_translate=False, rebalance_reference_method="llm_prompt_high",
            answer_verse_windows_json=None, answer_verse_window=2,
            rebalance_generator_model="g", rebalance_judge_model="j", rebalance_effort="high",
            rebalance_tolerance=0.15, retries=0,
        )

    def test_stage_runs_once_then_reuses_report(self):
        import os
        from unittest.mock import patch
        from evaluation import main as pipeline

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            method_dir = out / "llm_prompt_high"
            method_dir.mkdir()
            (method_dir / "passage_translation.json").write_text("{}", encoding="utf-8")
            (method_dir / "passage_target.txt").write_text(PASSAGE, encoding="utf-8")
            shared = {"translated_qa": out / "_shared" / "run_qa_zh.json"}
            shared["translated_qa"].parent.mkdir()
            shared["translated_qa"].write_text("[]", encoding="utf-8")
            args = self._args(out)

            def fake(qa, passage, report, **kw):
                Path(report).write_text("x", encoding="utf-8")
                self.assertEqual(Path(passage), method_dir / "passage_target.txt")
                self.assertEqual(kw["generator_model"], "g")
                return 3

            with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}), \
                    patch.object(pipeline, "rebalance_qa_file", side_effect=fake) as mocked:
                self.assertTrue(pipeline.run_mcq_rebalance_stage(args, shared, None, False))
                self.assertFalse(pipeline.run_mcq_rebalance_stage(args, shared, None, False))
                self.assertTrue(pipeline.run_mcq_rebalance_stage(args, shared, None, True))
                self.assertEqual(mocked.call_count, 2)
