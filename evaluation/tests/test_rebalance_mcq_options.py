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
    """generate -> fixed candidates; judge -> key text 'correct', listed verdicts, rest incorrect;
    factcheck -> listed fact verdicts, rest ok."""

    def __init__(self, candidates, key_text="请同我回家", verdicts=None, key_supported=True,
                 unnatural=(), facts=None, plaus=None, correct_texts=(), rewordings=(),
                 keycheck=None):
        self.candidates = candidates
        self.key_text = key_text
        self.verdicts = verdicts or {}
        self.key_supported = key_supported
        self.unnatural = set(unnatural)
        self.facts = facts or {}
        self.plaus = plaus or {}
        self.correct_texts = set(correct_texts)
        self.rewordings = list(rewordings)
        self.keycheck = keycheck or {}
        self.calls = []
        self.generate_payloads = []

    def __call__(self, role, system, user):
        self.calls.append(role)
        payload = json.loads(user)
        if role == "generate":
            self.generate_payloads.append(payload)
            if len(self.generate_payloads) > 1 and getattr(self, "candidates_after_first", None):
                self.candidates = self.candidates_after_first
            return {"answer_type": "action",
                    "candidates": [{"text": t, "kind": "span", "source": "v", "why_wrong": "w",
                                    "why_tempting": "t", "type": "action"}
                                   for t in self.candidates]}
        if role == "factcheck":
            return {"options": [{"letter": l, "verdict": self.facts.get(t, "ok")}
                                for l, t in payload["wrong_options"].items()]}
        if role == "keygen":
            return {"rewordings": [{"text": t, "why_same": "w"} for t in self.rewordings]}
        if role == "keycheck":
            fl = getattr(self, "fluency", {})
            return {"rewordings": [{"id": rid, "verdict": self.keycheck.get(t, "same"), "natural": True,
                                    "fluency": fl.get(t, 4)}
                                   for rid, t in payload["rewordings"].items()]}
        if role == "screen":
            self.screened = getattr(self, "screened", []) + list(payload["candidates"].values())
            return {"candidates": [
                {"id": cid, "label": ("correct" if t == self.key_text or t in self.correct_texts
                                      else self.verdicts.get(t, "incorrect")),
                 "natural": t not in self.unnatural, "plausibility": self.plaus.get(t, 4)}
                for cid, t in payload["candidates"].items()]}
        out = []
        for letter, text in payload["options"].items():
            if text == self.key_text or text in self.correct_texts:
                label = "correct" if self.key_supported else "incorrect"
            else:
                label = self.verdicts.get(text, "incorrect")
            out.append({"letter": letter, "label": label, "natural": text not in self.unnatural,
                        "plausibility": self.plaus.get(text, 4)})
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
        # audit = the screening prompt on the existing options; the set judge only confirms
        self.assertEqual(llm.calls, ["screen", "factcheck", "generate", "screen", "judge", "factcheck"])
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
        self.assertGreaterEqual(llm.calls.count("judge"), 1)   # at least one set confirmed

    def test_rejected_candidate_is_banned_and_replaced(self):
        bad = "在这地方吃饭喝水"
        llm = StubLLM([bad, "给我一半的家产", "照来时的路回去"], verdicts={bad: "ambiguous"})
        record = item({"A": "飞上天空", "B": "变成石头", "C": "请同我回家", "D": "下雨了"})
        result = rb.rebalance_item(record, ctx(), llm)
        judged = [c for c in llm.calls if c == "judge"]
        self.assertGreaterEqual(len(judged), 1)
        if result.new_options:
            self.assertNotIn(bad, result.new_options.values())

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

    def test_balanced_item_is_audited_only(self):
        llm = StubLLM([])
        balanced = {"A": "给我一半的家产", "B": "照来时的路回去", "C": "请同我回家", "D": "从别的路回去"}
        result = rb.rebalance_item(item(balanced), ctx(), llm)
        self.assertEqual(result.status, "ok")
        self.assertFalse(result.changed)
        self.assertEqual(llm.calls, ["screen", "factcheck"])

    def test_balanced_item_with_same_referent_distractor_is_replaced(self):
        alias = "从别的路回去"
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "不可吃饭喝水", "照来时的路回去"],
                      facts={alias: "same_referent"})
        balanced = {"A": "给我一半的家产", "B": "照来时的路回去", "C": "请同我回家", "D": alias}
        result = rb.rebalance_item(item(balanced), ctx(), llm)
        self.assertEqual(result.reason, "invalid_distractor")
        self.assertEqual(result.status, "replaced_invalid")
        self.assertNotIn(alias, result.new_options.values())
        self.assertEqual(result.new_options["A"], "给我一半的家产")   # untouched options stay
        self.assertIn(alias, llm.generate_payloads[0]["do_not_propose"])

    def test_unnatural_new_candidate_is_rejected(self):
        odd = "在这地方吃饭喝水"
        llm = StubLLM(["给我一半的家产", odd, "照来时的路回去", "从别的路回去"], unnatural={odd})
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm)
        self.assertIn(result.status, ("rebalanced", "partial"))
        self.assertNotIn(odd, result.new_options.values())

    def test_unnatural_existing_option_is_only_reported(self):
        llm = StubLLM([], unnatural={"照来时的路回去"})
        balanced = {"A": "给我一半的家产", "B": "照来时的路回去", "C": "请同我回家", "D": "从别的路回去"}
        result = rb.rebalance_item(item(balanced), ctx(), llm)
        self.assertEqual(result.status, "ok")
        self.assertFalse(result.natural["B"])

    def test_leftover_throwaway_is_flagged_and_replaced(self):
        # best AND second-best distractors match the key; the third is a throwaway
        lure = {"A": "给我一半的家产", "B": "照来时的路回去", "C": "请同我回家", "D": "变成石头"}
        record = item(lure)
        stats = rb.measure(rb.content_options(record), "C", ctx().window_for(record))
        self.assertLessEqual(abs(stats["gap"]), 0.15)
        self.assertEqual(rb.classify(stats, 0.15), "uneven")
        llm = StubLLM(["在这地方吃饭喝水", "从别的路回去"])
        result = rb.rebalance_item(record, ctx(), llm)
        self.assertEqual(result.status, "rebalanced")
        self.assertNotIn("变成石头", result.new_options.values())
        self.assertLessEqual(result.after["weakest_gap"], rb.WEAKEST_GAP_TOLERANCE)

    def test_low_plausibility_existing_option_is_replaced_during_rewrite(self):
        weak = "为我的国祷告"
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去", "从别的路回去"],
                      plaus={weak: 2})
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm)
        self.assertNotIn(weak, result.new_options.values())

    def test_low_plausibility_existing_option_fails_the_audit(self):
        weak = "照来时的路回去"
        llm = StubLLM(["在这地方吃饭喝水", "不可吃饭喝水", "神人回答说"], plaus={weak: 2})
        balanced = {"A": "给我一半的家产", "B": weak, "C": "请同我回家", "D": "从别的路回去"}
        result = rb.rebalance_item(item(balanced), ctx(), llm)
        self.assertEqual(result.reason, "invalid_distractor")
        self.assertTrue(result.changed)
        self.assertNotIn(weak, result.new_options.values())
        self.assertEqual(result.new_options["A"], "给我一半的家产")   # plausible ones are kept

    def test_without_the_gate_low_plausibility_is_only_reported(self):
        llm = StubLLM([], plaus={"照来时的路回去": 2})
        balanced = {"A": "给我一半的家产", "B": "照来时的路回去", "C": "请同我回家", "D": "从别的路回去"}
        c = ctx()
        c.plausibility_gate = False
        result = rb.rebalance_item(item(balanced), c, llm)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.plausibility["B"], 2)

    def test_proposal_rebuilds_throwaways_even_without_the_gate(self):
        reworded = "邀请神人到家中歇息"
        throwaways = {"A": "飞上天空", "B": "变成石头", "D": "下雨了"}
        llm = StubLLM(["火从天降", "海水分开"], plaus={**{t: 1 for t in throwaways.values()},
                                                  "火从天降": 1, "海水分开": 1,
                                                  "给我一半的家产": 4, "照来时的路回去": 4,
                                                  "在这地方吃饭喝水": 4},
                      rewordings=[reworded], correct_texts={reworded})
        llm.candidates_after_first = ["给我一半的家产", "照来时的路回去", "在这地方吃饭喝水"]
        c = ctx()
        c.plausibility_gate = False
        record = item({**throwaways, "C": "请同我回家"})
        result = rb.process_item(record, c, llm)
        self.assertIn(result.proposal["status"], ("proposed", "proposed_unbalanced"))
        for letter in "ABD":
            self.assertNotIn(result.proposal["options"][letter], throwaways.values())
        # verbatim distractors (1.00) against a reworded key (0.22) = reverse cue -> flagged
        self.assertEqual(result.proposal["status"], "proposed_unbalanced")

    def test_swaps_survive_the_similarity_filter(self):
        key = "赫人的诸王和埃及的诸王"
        raw = [{"text": "赫人的诸王和摩押的诸王", "kind": "swap", "why_tempting": "t"},
               {"text": "赫人的诸王和亚扪的诸王", "kind": "swap", "why_tempting": "t"},
               {"text": "赫人的诸王和埃及的诸王", "kind": "swap", "why_tempting": "t"},   # = key
               {"text": "赫人的诸王和埃及的诸王吧", "kind": "paraphrase", "why_tempting": "t"}]
        kept = rb.clean_candidates(raw, key, [])
        self.assertEqual([c.text for c in kept], ["赫人的诸王和摩押的诸王", "赫人的诸王和亚扪的诸王"])

    def test_implausible_new_candidate_is_rejected(self):
        absurd = "从别的路回去"
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去", absurd],
                      plaus={absurd: 1})
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm)
        self.assertIn(result.status, ("rebalanced", "partial"))
        self.assertNotIn(absurd, result.new_options.values())

    def test_selection_prefers_plausible_over_slightly_better_overlap(self):
        record = item(STANDS_OUT)
        window = ctx().window_for(record)
        verbatim = rb.Candidate("从别的路回去", "new")          # overlap 1.00
        tempting = rb.Candidate("从别的路回家", "new")          # overlap ~0.83
        others = [rb.Candidate("给我一半的家产", "new"), rb.Candidate("照来时的路回去", "new")]
        plaus = {rb.normalize("从别的路回去"): 2, rb.normalize("从别的路回家"): 5,
                 rb.normalize("给我一半的家产"): 5, rb.normalize("照来时的路回去"): 5}
        chosen = rb.choose_set(record, window, others + [verbatim, tempting], set(), plaus)
        texts = [c.text for c in chosen]
        self.assertIn("从别的路回家", texts)
        self.assertNotIn("从别的路回去", texts)

    def test_candidates_need_a_reason_and_the_key_type(self):
        raw = [{"text": "给我一半的家产", "type": "action", "why_tempting": "t"},
               {"text": "照来时的路回去", "type": "action"},                      # no reason
               {"text": "耶和华", "type": "person", "why_tempting": "t"}]      # wrong type
        kept = rb.clean_candidates(raw, "请同我回家", [], answer_type="action")
        self.assertEqual([c.text for c in kept], ["给我一半的家产"])

    def test_claimed_span_not_in_window_is_relabelled(self):
        record = item(STANDS_OUT)
        window = ctx().window_for(record)
        kept = rb.clean_candidates([{"text": "给我一半的家产", "kind": "span", "why_tempting": "t"},
                                    {"text": "飞上天空", "kind": "span", "why_tempting": "t"}],
                                   "请同我回家", [], window)
        self.assertEqual([c.kind for c in kept], ["span", "paraphrase"])

    def test_dominating_distractor_judged_correct_is_replaced(self):
        # B is verbatim and also a correct answer (an alias of the key, per the stub)
        opts = {"A": "建造祭坛", "B": "请同我回家，歇息", "C": "跟他到府上", "D": "祷告"}
        llm = StubLLM(["那神人", "别的路", "赏赐"], key_text="跟他到府上",
                      verdicts={"请同我回家，歇息": "correct"})
        result = rb.rebalance_item(item(opts), ctx(), llm)
        self.assertEqual(result.reason, "invalid_distractor")
        self.assertEqual(result.status, "replaced_invalid")
        self.assertNotIn("请同我回家，歇息", result.new_options.values())

    def test_dominating_distractor_validated_wrong_is_only_checked(self):
        opts = {"A": "建造祭坛", "B": "请同我回家，歇息", "C": "跟他到府上", "D": "祷告"}
        llm = StubLLM([], key_text="跟他到府上")
        result = rb.rebalance_item(item(opts), ctx(), llm)
        self.assertEqual(result.status, "ok")
        self.assertEqual(llm.calls, ["screen", "factcheck"])

    def test_stem_echo_is_avoided_when_alternatives_exist(self):
        q = "王对神人说了什么？"
        pool = [rb.Candidate("王对神人说", "new"), rb.Candidate("给我一半的家产", "new"),
                rb.Candidate("照来时的路回去", "new"), rb.Candidate("从别的路回去", "new")]
        record = item(STANDS_OUT, q=q)
        chosen = rb.choose_set(record, ctx().window_for(record), pool, set())
        self.assertNotIn("王对神人说", [c.text for c in chosen])

    def test_candidates_that_restate_the_key_are_dropped(self):
        kept = rb.clean_candidates([{"text": "请同我回家吧", "why_tempting": "t"},
                                    {"text": "给我一半的家产", "why_tempting": "t"}],
                                   "请同我回家", ["建造新的祭坛"])
        self.assertEqual([c.text for c in kept], ["给我一半的家产"])


class GateTests(unittest.TestCase):
    """5bba (2026-09-30 smoke run): fixing the best distractor while one lure + throwaways
    remain must NOT count as partial."""

    KEY = "赫人的诸王和埃及的诸王"
    PASSAGE = "\n".join([
        "5 黄昏时他们起来，往叙利亚营去。到了营外，却无人。",
        "6 因为耶和华使叙利亚人听见车马声和大军声，他们彼此说：“看哪，以色列王必是雇了赫人的诸王和埃及的诸王来攻击我们。”",
        "7 叙利亚人就起来，黄昏时逃跑，丢下帐棚、马匹和驴子，营地完好无损，逃命去了。",
    ])

    def _item(self):
        return {"q_type": "mcq", "Q": "叙利亚人以为谁要来攻击他们？",
                "A": {"A": self.KEY, "B": "摩押人", "C": "长大麻风的人", "D": "非利士人"},
                "correct": "A", "passage_id": "p", "passage_reference": "2 Kings 7:5-7",
                "reference": "7:6", "window_verses": [5, 6, 7]}

    def test_single_lure_replacement_is_left_for_review(self):
        c = rb.PassageContext(self.PASSAGE, "2 Kings 7:5-7")
        llm = StubLLM(["耶和华"], key_text=self.KEY)          # only one usable lure
        result = rb.rebalance_item(self._item(), c, llm, max_rounds=1)
        self.assertEqual(result.status, "needs_review")
        self.assertFalse(result.changed)

    def test_swaps_that_fix_both_gaps_are_accepted(self):
        c = rb.PassageContext(self.PASSAGE, "2 Kings 7:5-7")
        llm = StubLLM(["赫人的诸王和摩押的诸王", "埃及的诸王和以东的诸王", "雇了赫人的诸王"],
                      key_text=self.KEY)
        result = rb.rebalance_item(self._item(), c, llm)
        self.assertIn(result.status, ("rebalanced", "partial"))
        self.assertLess(rb.worst_gap(result.after), rb.worst_gap(result.before) - 0.15)


class ParallelTests(unittest.TestCase):
    def test_workers_preserve_order_and_results(self):
        records = [item(STANDS_OUT, pid=f"p{i}") for i in range(5)]
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去", "从别的路回去"])
        serial = rb.rebalance_records([dict(r, A=dict(r["A"])) for r in records], ctx(), llm, workers=1)
        parallel = rb.rebalance_records(records, ctx(), llm, workers=4)
        self.assertEqual([r.item_id for _, r in parallel], [f"p{i}" for i in range(5)])
        self.assertEqual([r.new_options for _, r in parallel], [r.new_options for _, r in serial])


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
        call("factcheck", "s", "u")
        self.assertEqual(seen[-1]["model"], "gpt-6-astra")
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


class ScreenTests(unittest.TestCase):
    def test_screen_rejects_before_selection_so_one_set_suffices(self):
        bad, odd, weak = "在这地方吃饭喝水", "照来时的路回去", "从别的路回去"
        llm = StubLLM(["给我一半的家产", bad, odd, weak, "不可吃饭喝水", "神人回答说", "王对神人说"],
                      verdicts={bad: "ambiguous"}, unnatural={odd}, plaus={weak: 2})
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm)
        self.assertTrue(result.changed, result.reason)
        for rejected in (bad, odd, weak):
            self.assertNotIn(rejected, result.new_options.values())
        # exactly ONE set judge (nothing rejected at the set stage); screens: audit + candidates
        self.assertEqual(llm.calls.count("judge"), 1)
        self.assertEqual(llm.calls.count("screen"), 2)

    def test_screen_scores_are_reported_not_rescored(self):
        llm = StubLLM(["给我一半的家产", "在这地方吃饭喝水", "照来时的路回去", "从别的路回去"],
                      plaus={"给我一半的家产": 5, "在这地方吃饭喝水": 4, "照来时的路回去": 3,
                             "从别的路回去": 3})
        result = rb.rebalance_item(item(STANDS_OUT), ctx(), llm)
        for letter, text in result.new_options.items():
            if letter != "C" and text != STANDS_OUT[letter]:
                self.assertEqual(result.plausibility[letter], llm.plaus[text])

    def test_unscreened_candidate_fails(self):
        out = rb.screen_candidates(lambda *a: {"candidates": []}, item(STANDS_OUT), "w",
                                   [rb.Candidate("x", "new")])
        self.assertFalse(rb.screen_passes(out["x"]))

    def test_default_round_limit_is_five(self):
        self.assertEqual(rb.DEFAULT_MAX_ROUNDS, 5)


class FormAndVarietyTests(unittest.TestCase):
    KEY = "赫人的诸王和埃及的诸王"
    PASSAGE = "\n".join([
        "5 黄昏时他们起来，往叙利亚营去。到了营外，却无人。",
        "6 因为耶和华使叙利亚人听见车马声和大军声，他们彼此说：“看哪，以色列王必是雇了赫人的诸王和埃及的诸王来攻击我们。”",
        "7 叙利亚人就起来，黄昏时逃跑，丢下帐棚、马匹和驴子，营地完好无损，逃命去了。",
    ])

    def test_quotes_and_speech_lead_are_removed(self):
        self.assertEqual(rb.tidy_option("百姓说：“他是麻风病人。”", False), "他是麻风病人")
        self.assertEqual(rb.tidy_option("“关门挡住他”", True), "关门挡住他。")
        self.assertEqual(rb.tidy_option("他被捡起时已死。", False), "他被捡起时已死")

    def test_key_parts(self):
        self.assertEqual(rb.key_parts(self.KEY), ["赫人的诸王", "埃及的诸王"])
        self.assertEqual(rb.key_parts("关门挡住他"), [])

    def test_swaps_mix_kept_parts(self):
        record = {"q_type": "mcq", "Q": "叙利亚人以为谁要来攻击他们？",
                  "A": {"A": self.KEY, "B": "摩押人", "C": "长大麻风的人", "D": "非利士人"},
                  "correct": "A", "passage_id": "p", "passage_reference": "2 Kings 7:5-7",
                  "reference": "7:6", "window_verses": [5, 6, 7]}
        c = rb.PassageContext(self.PASSAGE, "2 Kings 7:5-7")
        window = c.window_for(record)
        pool = [rb.Candidate(t, "new", kind="swap") for t in (
            "以东的诸王和埃及的诸王", "摩押的诸王和埃及的诸王", "亚扪的诸王和埃及的诸王",
            "赫人的诸王和摩押的诸王", "赫人的诸王和亚扪的诸王")]
        plaus = {rb.normalize(p.text): 3 for p in pool}
        chosen = [x.text for x in rb.choose_set(record, window, pool, set(), plaus)]
        kept_egypt = sum("埃及的诸王" in t for t in chosen)
        kept_hittite = sum("赫人的诸王" in t for t in chosen)
        self.assertTrue(kept_egypt >= 1 and kept_hittite >= 1, chosen)


class KeyRewordingTests(unittest.TestCase):
    """jxkk#2-type: verbatim key, window cannot supply matching distractors."""

    def _unbalanceable(self):
        # key verbatim (1.00); every generated candidate is a throwaway the screen rejects
        return item({"A": "飞上天空", "B": "变成石头", "C": "请同我回家", "D": "下雨了"})

    def test_eligibility(self):
        r = rb.ItemResult(item_id="x", status="needs_review", reason=rb.REWORDING_ELIGIBLE[0],
                          before={"key": 1.0}, old_options={})
        self.assertTrue(rb.needs_key_rewording(r))
        r.before = {"key": 0.5}
        self.assertFalse(rb.needs_key_rewording(r))
        r.before, r.reason = {"key": 1.0}, "validator does not support the key"
        self.assertFalse(rb.needs_key_rewording(r))

    def test_proposal_is_made_but_never_applied(self):
        reworded = "邀请神人到家中歇息"
        llm = StubLLM(["火从天降", "海水分开", "日头停住"], plaus={"火从天降": 1, "海水分开": 1, "日头停住": 1},
                      rewordings=["请同我回家", "请同我回家吧", reworded], correct_texts={reworded})
        record = self._unbalanceable()
        result = rb.process_item(record, ctx(), llm)
        self.assertEqual(result.status, "needs_review")
        self.assertIsNotNone(result.proposal)
        self.assertEqual(result.proposal["key"], reworded)              # verbatim ones dropped
        self.assertNotIn("请同我回家吧", result.proposal["candidates"])  # still copies the window
        self.assertFalse(result.changed)
        self.assertEqual(rb.apply_to_records([record], {result.item_id: result}, {}), 0)
        self.assertEqual(record["A"]["C"], "请同我回家")                 # key untouched
        row = rb.report_row("t", record, result)
        self.assertEqual(row["proposed_key"].split(" (")[0], reworded)
        self.assertIn(row["key_proposal_status"], ("proposed", "rebalance_failed"))

    def test_narrower_or_incorrect_rewordings_are_rejected(self):
        narrower, wrong = "请神人回家吃饭喝水", "叫神人立刻回犹大"
        llm = StubLLM(["火从天降"], plaus={"火从天降": 1}, rewordings=[narrower, wrong],
                      correct_texts={narrower}, keycheck={narrower: "narrower"})
        result = rb.process_item(self._unbalanceable(), ctx(), llm)
        self.assertEqual(result.proposal["status"], "no_valid_rewording")

    def test_flag_disables_it(self):
        llm = StubLLM(["火从天降"], plaus={"火从天降": 1}, rewordings=["邀请神人到家中歇息"])
        c = ctx()
        c.key_rewording = False
        result = rb.process_item(self._unbalanceable(), c, llm)
        self.assertIsNone(result.proposal)
        self.assertNotIn("keygen", llm.calls)


class RewordingChoiceTests(unittest.TestCase):
    def test_fluent_short_rewording_beats_stiff_or_long_one(self):
        window = rb.normalize("1 王对神人说：“请同我回家，歇息，我必给你赏赐。”")
        stiff = rb.rewording_cost("邀神人至舍下", window, 0.3, 5, fluency=2)
        long2 = rb.rewording_cost("邀请神人一起回到家中，好好休息一下", window, 0.3, 5, fluency=4)
        good = rb.rewording_cost("邀神人到家里", window, 0.3, 5, fluency=5)
        self.assertLess(good, stiff)
        self.assertLess(good, long2)

    def test_proposal_uses_fluency(self):
        stiff, fluent = "邀神人至舍下歇", "邀神人到家歇息"
        llm = StubLLM(["火从天降"], plaus={"火从天降": 1}, rewordings=[stiff, fluent],
                      correct_texts={stiff, fluent})
        llm.fluency = {stiff: 1, fluent: 5}
        result = rb.process_item(item({"A": "飞上天空", "B": "变成石头", "C": "请同我回家", "D": "下雨了"}),
                                 ctx(), llm)
        self.assertEqual(result.proposal["key"], fluent)
        self.assertEqual(result.proposal["key_fluency"], 5)
