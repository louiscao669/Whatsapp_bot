#!/usr/bin/env python3
"""End-to-end check that option rotation removes a letter prior on REAL tier-1 QA.

No model and no network: the "answerer" is a stub that always returns the same letter,
which is the pathological case the real answerers approximate (llama3.2:1b picks B 33% of
the time, qwen3:1.7b picks D 33%, and each is deterministic per item at temperature 0).

What must hold:
  * rotation off      -> the biased stub scores exactly the share of items keyed to its
                         favourite letter. That is the bug: the score measures the key
                         distribution, not the model.
  * rotations 0..3    -> every item is correct in exactly one rotation, so the mean is
                         0.25 for every item regardless of where its key sits. The prior
                         cancels exactly, not on average.
  * one offset        -> position is identical for every cell in a run, so a paired dose
                         contrast carries no position change.
  * always            -> abstention / none-of-the-above never move, and the text under
                         the mapped-back letter still matches what was shown.
"""
import json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate_chinese_answers as g          # noqa: E402
import mcq_option_order as order              # noqa: E402

QA = Path(os.path.expanduser(
    "~/mnt/eten-research-outputs/evaluation/outputs/tier1_bsb"))
SRC = sorted(QA.glob("t1_*/llama321b/omission/0%/qa_target.json"))
assert SRC, "no tier-1 qa_target.json found"

items, keys = [], {}
for p in SRC:
    d = json.load(open(p))
    for it in (d if isinstance(d, list) else d.get("items", [])):
        if it.get("q_type") == "mcq" and isinstance(it.get("A"), dict) and it.get("correct"):
            items.append(it)
questions = g.public_questions(items)
mcq = [q for q in questions if q["q_type"] == "mcq"]
for q, it in zip(mcq, [i for i in items if i.get("q_type") == "mcq"]):
    keys[q["item_index"]] = it["correct"]
print(f"loaded {len(mcq)} real MCQ items from {len(SRC)} passages")

import collections
kd = collections.Counter(keys.values())
print("  key letters:", {L: f"{kd[L]}({kd[L]/len(keys):.0%})" for L in "ABCD"})


def run(rotate, always):
    """Stub answerer that always says `always`; returns per-item correctness."""
    qs = json.loads(json.dumps(questions))        # fresh copy each run
    plan = g.apply_option_order(qs, rotate=rotate)
    answers = [{"item_index": q["item_index"], "selected_choice": always,
                "selected_choice_text": q["choices"].get(always)}
               for q in qs if q["q_type"] == "mcq"]
    g.restore_canonical_order(answers, qs, plan, rotate=rotate)
    return {a["item_index"]: a["selected_choice"] == keys[a["item_index"]]
            for a in answers}, answers, qs


ok = []
# --- rotation OFF: the score is just the key distribution -------------------------
for fav in "ABCD":
    res, _, _ = run(None, fav)
    acc = sum(res.values()) / len(res)
    ok.append((f"unrotated, a stub that always says {fav} scores {acc:.3f} "
               f"= share of keys on {fav} ({kd[fav]/len(keys):.3f})",
               abs(acc - kd[fav] / len(keys)) < 1e-9))

# --- rotations 0..3: the prior cancels exactly, per item ---------------------------
for fav in "ABCD":
    per_item = collections.Counter()
    for k in range(4):
        res, _, _ = run(k, fav)
        for idx, good in res.items():
            per_item[idx] += good
    ok.append((f"always-{fav} is correct in exactly 1 of 4 rotations on every item",
               set(per_item.values()) == {1}))
    mean = sum(per_item.values()) / (4 * len(per_item))
    ok.append((f"always-{fav} averages {mean:.3f} over the ladder (chance, not key share)",
               abs(mean - 0.25) < 1e-9))

# --- one offset is constant across a run, so paired contrasts are clean -----------
_, _, qs1 = run(2, "A")
_, _, qs2 = run(2, "A")
ok.append(("the same offset gives the same presentation every time",
           [q.get("choices") for q in qs1] == [q.get("choices") for q in qs2]))

# --- text integrity and meta-options ----------------------------------------------
_, answers, qs = run(1, "B")
byi = {q["item_index"]: q for q in qs}
good_text = all(
    a["selected_choice_text"] == byi[a["item_index"]]["choices"]["B"] for a in answers)
ok.append(("the recorded text is what was actually shown", good_text))
src = {q["item_index"]: q for q in questions}
moved = sum(1 for a in answers
            if byi[a["item_index"]]["choices"] != src[a["item_index"]]["choices"])
ok.append((f"rotation actually changed the presentation ({moved}/{len(answers)} items)",
           moved == len(answers)))
ok.append(("presented order and rotation are recorded for later analysis",
           all(a.get("presented_order") and a.get("mcq_option_order") == "rotate:1"
               and a.get("presented_choice") == "B" for a in answers)))

# meta-options: build a 6-option question and confirm E/F are untouched
q6 = {"item_index": 1, "id": "x", "q_type": "mcq",
      "question": "q", "choices": {"A": "a", "B": "b", "C": "c", "D": "d",
                                   "E": "I can't tell", "F": "None of the above"}}
plan = g.apply_option_order([q6], rotate=3)
ok.append(("abstention and none-of-the-above keep their letters and text",
           q6["choices"]["E"] == "I can't tell"
           and q6["choices"]["F"] == "None of the above"))
ok.append(("only the content options moved", {q6["choices"][L] for L in "ABCD"} ==
           {"a", "b", "c", "d"} and q6["choices"]["A"] != "a"))

# --- off by default: nothing changes ----------------------------------------------
qs0 = json.loads(json.dumps(questions))
plan0 = g.apply_option_order(qs0, rotate=None, seed=None)
ok.append(("with no rotation requested, nothing is touched at all",
           plan0 == {} and qs0 == questions))

bad = 0
for name, cond in ok:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    bad += not cond
print(f"\n{len(ok) - bad}/{len(ok)} checks passed (no model calls)")
raise SystemExit(1 if bad else 0)
