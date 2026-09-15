#!/usr/bin/env python3
"""Rewrite each item's window so it fluently asserts a DIFFERENT fact -- making F correct.

Why this exists. F means "the passage answers the question, but the answer is not A-D".
Under omission that state cannot arise: omission removes evidence, which is E's case, so F
was wrong by construction in every condition measured so far and its only observed use was
as a dumping ground when reasoning was off (25% of clean-text answers). Mistranslation is
where F becomes legitimately reachable, because the passage still asserts something -- just
not what the options list.

Why an LLM rather than string substitution. A deterministic splice produces word salad:
replacing 王的手 with 为我的国祷告 yields "pray for my kingdom then recovered". Broken syntax
reads as DAMAGE and invites E, which is the opposite of what this control needs. The whole
point is fluent-but-wrong: the text must look like a competent translation of a different
sentence. Only a model can do that.

Generation is separated from measurement on purpose. This script pays the API cost ONCE and
writes the corrupted windows to disk; abstention_thinking_probe.py then reads that file and
measures locally, free and repeatably, as many times as you like.

Every corruption is VERIFIED by a second model before it is kept:
  - the corrupted window must still answer the question (or E becomes correct, not F)
  - it must support NONE of A-D    (or that option becomes correct, not F)
  - it must read as fluent Chinese (or the model sees damage and picks E)
Rejections are reported and excluded rather than shipped, because an unverified corruption
silently turns the control into noise.

  python3 .../build_corrupted_windows.py --self-test
  set -a; source .env; set +a
  python3 .../build_corrupted_windows.py --limit 5      # cheap smoke test first
  python3 .../build_corrupted_windows.py
"""
from __future__ import annotations

import argparse, json, os, sys
from pathlib import Path
from typing import List, Literal, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
for p in (str(REPO), str(HERE), str(REPO / "evaluation/scripts/mcq/diagnostics")):
    if p not in sys.path:
        sys.path.insert(0, p)

CONTENT_LETTERS = "ABCD"


def build_chains(model, provider, effort):
    """Two chains: one that corrupts, one that checks. Separate models would be better
    still, but the check asks a different question than the rewrite, which is most of the
    independence that matters."""
    from pydantic import BaseModel, Field
    from langchain_core.prompts import ChatPromptTemplate

    class Corruption(BaseModel):
        corrupted_window: str = Field(
            description="The whole window, verse numbers intact, with ONLY the answer-"
                        "bearing clause rewritten. Every other verse character-identical.")
        span_before: str = Field(description="The exact original clause you replaced.")
        span_after: str = Field(description="Exactly what you replaced it with.")
        new_answer: str = Field(
            description="What the question's answer now is, according to the rewritten "
                        "window. Must not match any listed option.")

    class Check(BaseModel):
        answers_question: bool = Field(
            description="Does the rewritten window still answer the question with some "
                        "definite fact? False if it merely removed the information.")
        supported_options: List[str] = Field(
            description="Letters among A-D that the rewritten window now supports. Empty "
                        "is required: any entry means that option became correct.")
        fluent: bool = Field(
            description="Does the rewritten window read as natural, grammatical Chinese, "
                        "like a competent translation of a different sentence? False if it "
                        "is garbled or ungrammatical.")
        reason: str = Field(description="One short clause.")

    corrupt_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You rewrite ONE clause of a Chinese Bible passage so that it states a DIFFERENT "
         "fact. You are simulating a MISTRANSLATION, not damage.\n\n"
         "Requirements, in order of importance:\n"
         "1. The result must read as fluent, natural, grammatical Chinese in the same "
         "register as the original. A careful reader should see a passage that says "
         "something else -- never a garbled or broken sentence. This is the whole point: "
         "broken text reads as damage, and damage is a different condition.\n"
         "2. The rewritten window must still ANSWER the question, with a definite fact. Do "
         "not simply delete the information.\n"
         "3. That new fact must match NONE of the listed options. Check each one.\n"
         "4. SUBSTITUTE, NEVER ADD. Replace the words that carry the answer with different "
         "words. Do not append a clause, a sentence or a new participant, and do not "
         "reintroduce elsewhere anything you removed. The rewritten verse should be about "
         "the same length as the original -- a noticeably longer verse means you added "
         "rather than replaced, and the fixture is void.\n"
         "   WORKED EXAMPLE OF THE FAILURE. Original: 有一个神人奉耶和华的话从犹大来到伯特利. "
         "Asked to make the answer something other than 神人, a model returned "
         "有一个犹大长老奉耶和华的话从犹大来到伯特利，另有一个神人与他同行 -- it made the "
         "substitution and then ADDED the man of God back as a companion, to keep the scene "
         "coherent. That put the removed entity back in the passage and made the fixture "
         "ambiguous. The correct output replaces 神人 with 犹大长老 and stops there.\n"
         "5. Every verse other than the one containing the answer must come back "
         "character-for-character identical, verse numbers included.\n"
         "6. Stay inside the world of the passage: same people, same place, same period. "
         "An invented modern detail would be spotted as alien rather than as a translation "
         "error."),
        ("human",
         "QUESTION: {question}\n\nOPTIONS (the new fact must match none of these):\n"
         "{options}\n\nCURRENT ANSWER (this is what you must replace): {key}\n\n"
         "WINDOW:\n{window}"),
    ])
    check_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You check a rewritten passage window used as a test fixture. Answer three things "
         "about it, independently:\n"
         "  answers_question  -- does it state some definite answer to the question?\n"
         "  supported_options -- which of A-D, if any, does it now support? List letters.\n"
         "  fluent            -- does it read as natural grammatical Chinese?\n"
         "Judge only the rewritten window. Do not compare it to the original, and do not "
         "comment on whether the rewrite was a good idea."),
        ("human",
         "QUESTION: {question}\n\nOPTIONS:\n{options}\n\nREWRITTEN WINDOW:\n{window}"),
    ])

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        llm = ChatOllama(model=model, temperature=0.0)
    else:
        from langchain_openai import ChatOpenAI
        kw = {"model": model}
        if any(model.startswith(p) for p in ("gpt-5", "o1", "o3", "o4")):
            kw["reasoning_effort"] = effort
        else:
            kw["temperature"] = 0.0
        llm = ChatOpenAI(**kw)
    return (corrupt_prompt | llm.with_structured_output(Corruption),
            check_prompt | llm.with_structured_output(Check))


def options_block(choices, letters=CONTENT_LETTERS):
    return "\n".join(f"{L}. {choices[L]}" for L in letters if L in choices)


def structure_ok(intact: str, corrupted: str, max_growth=0.20, min_slack=4):
    """Deterministic backstop for rule 4: did the rewrite SUBSTITUTE, or did it ADD?

    The LLM check judges meaning and cannot see this -- on t1_1kgs13:mjwk it correctly
    reported that no option was supported, while the rewrite had quietly appended
    ，另有一个神人与他同行 and grown the verse from 38 to 51 characters. Length is the
    signal that catches it, and it costs nothing.

    Returns (ok, reason).
    """
    a = [l.rstrip() for l in intact.splitlines() if l.strip()]
    b = [l.rstrip() for l in corrupted.splitlines() if l.strip()]
    if len(a) != len(b):
        return False, f"verse count changed ({len(a)} -> {len(b)})"
    changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if not changed:
        return False, "nothing was changed"
    if len(changed) > 1:
        return False, f"{len(changed)} verses changed; only the answer-bearing one may move"
    i = changed[0]
    grew = len(b[i]) - len(a[i])
    allowed = max(min_slack, int(len(a[i]) * max_growth))
    if grew > allowed:
        return False, (f"verse grew {len(a[i])} -> {len(b[i])} (+{grew} > {allowed}); "
                       f"that is an addition, not a substitution")
    return True, "ok"


def verdict(check, expect_letters=CONTENT_LETTERS):
    """Accept only a corruption that answers, supports nothing, and reads naturally."""
    if check is None:
        return False, "no verdict"
    bad = [L for L in (check.supported_options or []) if L in expect_letters]
    if not check.answers_question:
        return False, "no longer answers the question -- that is E's case, not F's"
    if bad:
        return False, f"now supports {','.join(bad)} -- that option became correct"
    if not check.fluent:
        return False, "reads as damaged rather than as a different translation"
    return True, "ok"


def run(a):
    from abstention_thinking_probe import load_items
    items, skipped = load_items(a.run_root, a.windows, a.limit)
    print(f"{len(items)} item(s) to corrupt; skips={dict(skipped)}")
    corrupt, check = build_chains(a.model, a.provider, a.effort)
    out, rejected = {}, []
    if a.out and os.path.exists(a.out) and a.resume:
        out = json.load(open(a.out, encoding="utf-8"))
        print(f"resuming: {len(out)} already generated")
    for i, it in enumerate(items, 1):
        if it["cid"] in out:
            continue
        opts = options_block(it["choices"])
        try:
            c = corrupt.invoke({"question": it["Q"], "options": opts,
                                "key": it["choices"].get(it["correct"], ""),
                                "window": it["windows"]["full"]})
            k = check.invoke({"question": it["Q"], "options": opts,
                              "window": c.corrupted_window})
        except Exception as exc:
            print(f"  [err ] {it['cid']}: {exc}", file=sys.stderr)
            continue
        ok, why = structure_ok(it["windows"]["full"], c.corrupted_window,
                               a.max_growth, a.min_slack)
        if ok:
            ok, why = verdict(k)
        if not ok:
            rejected.append((it["cid"], why))
            print(f"  [rej ] {it['cid']}: {why}", file=sys.stderr)
            continue
        out[it["cid"]] = {"cid": it["cid"], "key_letter": it["correct"],
                          "intact": it["windows"]["full"],
                          "corrupted": c.corrupted_window,
                          "span_before": c.span_before, "span_after": c.span_after,
                          "new_answer": c.new_answer, "check_reason": k.reason}
        print(f"  [ok  ] {it['cid']}  {c.span_before[:22]!r} -> {c.span_after[:22]!r}")
        if i % 10 == 0:
            json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"\nkept {len(out)}, rejected {len(rejected)} -> {a.out}")
    for cid, why in rejected[:10]:
        print(f"  rejected {cid}: {why}")
    return 0


def self_test():
    ok = []
    ch = {"A": "甲", "B": "乙", "C": "丙", "D": "丁", "E": "根据这段文字无法判断"}
    ok.append(("options block lists only the content letters",
               options_block(ch) == "A. 甲\nB. 乙\nC. 丙\nD. 丁"))

    class K:
        def __init__(s, ans=True, sup=None, flu=True):
            s.answers_question, s.supported_options, s.fluent, s.reason = ans, sup or [], flu, ""
    ok.append(("a clean corruption is accepted", verdict(K())[0]))
    ok.append(("one that stopped answering is rejected (that is E's case)",
               not verdict(K(ans=False))[0]))
    ok.append(("one that made an option correct is rejected",
               not verdict(K(sup=["C"]))[0]))
    ok.append(("an ungrammatical one is rejected -- it reads as damage",
               not verdict(K(flu=False))[0]))
    ok.append(("a meta letter in supported_options does not reject",
               verdict(K(sup=["E"]))[0]))
    ok.append(("no verdict is a rejection, not a pass", not verdict(None)[0]))

    # the real mjwk rewrite, and the three that were fine
    mj_a = "1 突然，当耶罗波安站在坛旁烧香时，有一个神人奉耶和华的话从犹大来到伯特利。"
    mj_b = ("1 突然，当耶罗波安站在坛旁烧香时，有一个犹大长老奉耶和华的话从犹大来到伯特利，"
            "另有一个神人与他同行。")
    good, why = structure_ok(mj_a, mj_b)
    ok.append((f"the mjwk append is caught ({why[:44]})", not good))
    ok.append(("a same-length substitution passes",
               structure_ok("6 王的手便复原，像先前一样。", "6 王的手仍旧枯干，不能收回。")[0]))
    ok.append(("a +2 character substitution passes",
               structure_ok("7 请同我回家，歇息。", "7 请同我到城里去，歇息。")[0]))
    ok.append(("an unchanged window is rejected",
               not structure_ok("1 abc", "1 abc")[0]))
    ok.append(("changing two verses is rejected",
               not structure_ok("1 aaa\n2 bbb", "1 xxx\n2 yyy")[0]))
    ok.append(("dropping a verse is rejected",
               not structure_ok("1 aaa\n2 bbb", "1 aaa")[0]))
    ok.append(("shrinking is allowed -- deletion is not the failure mode here",
               structure_ok("1 aaaaaaaaaaaaaaaaaaaa", "1 aaa")[0]))
    bad = 0
    for n, c in ok:
        print(f"  [{'PASS' if c else 'FAIL'}] {n}")
        bad += not c
    print(f"\n{len(ok)-bad}/{len(ok)} self-tests passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-root", default="evaluation/outputs/tier1_bsb_unblinded_5opt")
    ap.add_argument("--windows",
                    default="QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json")
    ap.add_argument("--provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--model", default="gpt-5.6-sol")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.add_argument("--out", default="evaluation/datasets/mcq/corrupted_windows.json")
    ap.add_argument("--max-growth", type=float, default=0.20,
                    help="reject a rewrite whose changed verse grows by more than this "
                         "fraction -- growth means the model appended instead of replacing")
    ap.add_argument("--min-slack", type=int, default=4,
                    help="always allow this many extra characters, so a legitimate "
                         "substitution of slightly different length is not rejected")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    return self_test() if a.self_test else run(a)


if __name__ == "__main__":
    raise SystemExit(main())
