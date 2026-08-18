#!/usr/bin/env python3
"""Rewrite MCQ distractors against the answer context, then measure closed/open book.

Flow, one pass per question, exactly:

    Input: QA item (question + correct answer + 3 distractors)
      1. get the context window          -- the verses the respondent will actually see
      2. rewrite the 3 DISTRACTORS       -- LLM, given that window in its system prompt and
                                            told to prefer material from it (but free to go
                                            outside if the result is convincing), and to
                                            match the answer's type
      2b. audit relevance                -- a SECOND model (LangChain, structured output)
                                            checks each distractor is a possible ANSWER to
                                            the question, not just a true statement;
                                            rejections are regenerated with its feedback
      2c. length-match the answer        -- the correct option is rephrased toward the
                                            distractors' median length, and the rewrite is
                                            kept ONLY if a verifier agrees it asserts the
                                            same fact
      3. randomize the choices           -- deterministic shuffle, ours not the model's
      4. answer with a small model       -- closed book, then open book on the window
    Output: report

The correct option's FACT never changes. Step 2c may rephrase it for length, but only when an
equivalence check confirms the claim is identical; on any doubt or error the original text is
kept. There are no gates -- no item is discarded; this measures what the rewrite produces.

Usage:
  set -a; source .env; set +a
  python evaluation/scripts/mcq/rewrite_distractors.py \\
      --chapters 1 2 3 4 5 6 7 8 \\
      --provider openai --model gpt-5.6-terra \\
      --relevance-model gpt-5.6-sol \\
      --answer-provider ollama --answer-model qwen2.5:1.5b --k 1

  python evaluation/scripts/mcq/rewrite_distractors.py --self-test   # offline, no API
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

from regen_mcq_tier01 import randomized_three_verse_window

LETTER_RE = re.compile(r"[A-Da-d]")
LETTERS = "ABCD"


class DistractorGenerationError(Exception):
    """De-novo generation failed. Raised rather than emitting blank options."""


CJK_RE = re.compile(r"[一-鿿]")


def cjk_len(s):
    return len(CJK_RE.findall(s or ""))


def length_outliers(item, tolerance):
    """Distractors whose length differs from the correct option by more than ``tolerance``.

    The correct option is carried through verbatim from the original QA while the distractors
    are written fresh, so the two come from different registers and the answer ends up
    systematically shorter. Measured on the 2026-07-29 luke1 run: correct averaged 8.0 CJK
    chars vs 9.8 for distractors, the correct option was the shortest in 10/22 items, and
    "pick the shortest" scored 81.8% closed-book -- MORE than the answer model's 72.7%. The
    prompt already asked for parallel length and could not deliver it, because the model is
    only allowed to move three of the four options. So this is checked mechanically.
    """
    target = cjk_len(item[item["correct"]])
    return [L for L in LETTERS
            if L != item["correct"] and abs(cjk_len(item[L]) - target) > tolerance]


# --------------------------------------------------------------------- step 2: rewrite
REWRITE_SYSTEM_TEMPLATE = """You rewrite the three DISTRACTORS of a Chinese \
reading-comprehension MCQ.

ANSWER CONTEXT — the only verses the respondent will see when answering:
{window}
{menu}
Keep the correct option exactly as it is. Rewrite only the other three.

1. EVERY DISTRACTOR MUST BE A POSSIBLE ANSWER TO THE QUESTION. — most important
Not merely a true-sounding sentence: a genuine candidate answer to the exact thing asked. If
the question asks WHY someone was righteous, every option must be a reason someone could be
called righteous. If it asks WHO was sent, every option must be a person who could have been
sent. A statement that is fine in itself but does not address the question is worthless as a
distractor — a respondent rules it out on relevance alone, without reading the passage.

Test each distractor: "if I had not read the passage, could this be the answer?" If no,
rewrite it.

WORKED EXAMPLE — question: 珂温和哈丽为什么被认为是义人？
  Bad:  他们属于洛谷的祭司班次 / 他们是隆松的后裔 / 他们是索伦王兰维时代的人
        Each is drawn from the passage and each is true, but none is a REASON for being
        righteous — they are biographical facts, so all three are free eliminations.
  Good: 因为他们常在庙中献祭 / 因为他们终身祷告不倦 / 因为他们把家业分给穷人
        Each is a reason a person could be called righteous, so the respondent has to know
        which reason the passage actually gives.
Note what changed: the passage material was not dropped, it was RECAST as an answer to the
question. Do that.

2. PREFER MATERIAL FROM THE ANSWER CONTEXT.
Subject to rule 1, build distractors from something that really appears above — a person,
place, group, object, action or time — recast so it answers the question. These are the
strongest distractors, because a respondent cannot rule them out without actually
understanding the passage.

If a better distractor lies outside the context, use it — but then it must be CONVINCING:
consistent with the world, period and register of the passage, and something a careful reader
might plausibly believe until they check. Never produce an option a respondent can dismiss
because it feels invented or out of place; that is a free elimination and it costs the item
its discriminating power.

Whatever its source, every distractor must be FALSE for this passage.

3. MATCH THE ANSWER'S TYPE.
All four options must answer the same KIND of question as the correct one. If the answer is a
person, every option is a person; a reason, every option a reason; a place, every option a
place; a duration, every option a duration.

4. KEEP THE FOUR OPTIONS PARALLEL.
Parallel in grammar, length and specificity, so the correct one does not stand out. Do not let
it be either the only option echoing the context's wording or the only option avoiding it.

Output STRICT JSON only: {{"A":"...","B":"...","C":"...","D":"...","correct":"<letter>"}}
Keep "correct" exactly as given."""


DE_NOVO_TASK = """You WRITE the three DISTRACTORS of a Chinese \
reading-comprehension MCQ, given only the question and the correct answer."""

DE_NOVO_KEEP = ("Use the correct option exactly as given. Write the other three "
                "from scratch.")


def build_rewrite_system(window, menu="", de_novo=False):
    """Put the answer context INSIDE the system prompt, not alongside it in the user turn."""
    text = REWRITE_SYSTEM_TEMPLATE.format(window=window, menu=menu)
    if de_novo:
        # Only the framing changes. Rules 1-4 (possible answer / prefer context /
        # match type / keep parallel) are what make a distractor good and apply
        # identically whether it is being rewritten or written.
        text = text.replace(
            "You rewrite the three DISTRACTORS of a Chinese "
            "reading-comprehension MCQ.", DE_NOVO_TASK, 1)
        text = text.replace(
            "Keep the correct option exactly as it is. Rewrite only the other three.",
            DE_NOVO_KEEP, 1)
    return text


def rewrite_distractors(client, model, item, question, window, ents=None, temperature=0.4,
                        feedback=None, effort=None):
    """Rewrite the three distractors; return a new option dict. Correct option untouched.

    ``window`` is the answer context, not the chapter. Grounding in the whole chapter is the
    wrong scope: an option built from verse 60 and delivered in a window covering verses
    12-14 is indistinguishable from an invention to someone reading only those verses, which
    makes it MORE eliminable, not less.
    """
    correct = item["correct"]
    menu = ""
    if ents:
        by_cat = {}
        for name, cat in ents.items():
            if name and name in window:           # window-scoped on purpose
                by_cat.setdefault(cat, []).append(name)
        if by_cat:
            listing = "\n".join(f"- {cat}: {', '.join(sorted(set(v))[:20])}"
                                for cat, v in sorted(by_cat.items()) if v)
            menu = f"\nNamed entities present in the ANSWER CONTEXT, by type:\n{listing}\n"
    # De-novo: no prior distractors exist, only a correct answer. Rules 1-4 are
    # defined against the question, the correct option and the window -- none of
    # them consults the old distractors -- so the same prompt writes them from
    # nothing once the user turn stops presenting three strings to edit. Showing
    # empty slots instead would invite the model to "keep" them.
    de_novo = not all(str(item.get(L, "")).strip() for L in LETTERS if L != correct)
    fb = ""
    if feedback:
        fb = (f"\nAn independent reviewer REJECTED some of these options as not being possible "
              f"answers to the question:\n{feedback}\n"
              f"Fix exactly those, keep the others.\n")
    if de_novo:
        user = (f"QUESTION: {question}\n\n"
                f"CORRECT ANSWER (this is option {correct}, use it verbatim):\n"
                f"{item[correct]}\n{fb}\n"
                f"There are no existing distractors. WRITE the three others from scratch, "
                f"applying every rule above. Before answering, check each against rule 1: "
                f"is it a possible answer to this exact question, or merely a true "
                f"statement? JSON only.")
    else:
        body = "\n".join(
            f"{L}. {item[L]}" + ("   [correct — keep exactly as is]" if L == correct else "")
            for L in LETTERS)
        user = (f"QUESTION: {question}\n\n"
                f"CURRENT OPTIONS (correct = {correct}):\n{body}\n{fb}\n"
                f"Rewrite the three distractors. Before answering, check each one against rule 1: "
                f"is it a possible answer to this exact question, or merely a true statement? "
                f"JSON only.")
    out = chat(client, model,
               [{"role": "system", "content": build_rewrite_system(window, menu, de_novo)},
                {"role": "user", "content": user}], temperature, 400, effort)
    try:
        fixed = parse_json(out)
    except Exception:
        # Rewrite mode can fall back to the original options. De novo has no
        # original to fall back to, so returning the item would emit an MCQ with
        # blank choices that looks valid downstream. Signal failure instead.
        if de_novo:
            raise DistractorGenerationError(
                f"de-novo generation returned unparseable JSON for: {question[:60]}")
        return dict(item)                          # keep the original rather than lose the item
    if not all(str(fixed.get(L, "")).strip() for L in LETTERS):
        if de_novo:
            raise DistractorGenerationError(
                f"de-novo generation returned a blank option for: {question[:60]}")
        return dict(item)
    # The rewrite may not move the key or touch the fact under test.
    result = {L: str(fixed[L]).strip() for L in LETTERS}
    result[correct] = item[correct]
    result["correct"] = correct
    return result


# ----------------------------------------------------- step 2c: length-match the answer
CORRECT_REWRITE_SYSTEM = """You rephrase the CORRECT option of a Chinese \
reading-comprehension MCQ so it does not stand out from the other three by length or style.

The other three options were written together and are consistent with each other. The correct
option came from a different source and is the odd one out — usually conspicuously shorter,
which lets a respondent pick it without reading the passage.

ABSOLUTE CONSTRAINT: the fact must not change. Same entities, same relation, same polarity,
same numbers. You are rewording, not re-answering. If you cannot reach the target length
without adding, removing or softening information, stay closer to the original — a slightly
short option is far better than a wrong one. Do not pad with filler that adds no meaning, and
do not add detail the passage does not support.

Match the register and grammatical shape of the other options as well as their length.

Output STRICT JSON only: {"rewritten": "<the rephrased correct option>"}"""


def rewrite_correct_option(client, model, item, question, target_len, effort=None,
                           temperature=0.3):
    """Rephrase the correct option toward ``target_len`` characters. Returns text or None.

    Inverted from the earlier approach, which told the DISTRACTOR writer to match the correct
    option's length. That could not work: three of four options were being written to match a
    fourth the model was forbidden to touch. The three distractors are mutually consistent --
    same model, same call -- so the lone outlier is the answer, and the answer is what should
    move.
    """
    others = "\n".join(f"- {item[L]}  ({cjk_len(item[L])} chars)"
                       for L in LETTERS if L != item["correct"])
    user = (f"QUESTION: {question}\n\n"
            f"CORRECT OPTION (rephrase this): {item[item['correct']]}  "
            f"({cjk_len(item[item['correct']])} chars)\n\n"
            f"THE OTHER THREE OPTIONS, whose length and style to match:\n{others}\n\n"
            f"Target: about {target_len} Chinese characters. JSON only.")
    try:
        out = chat(client, model, [{"role": "system", "content": CORRECT_REWRITE_SYSTEM},
                                   {"role": "user", "content": user}],
                   temperature, 400, effort)
        text = str(parse_json(out).get("rewritten", "")).strip()
    except Exception:
        return None
    return text or None


# ------------------------------------------------------------------- step 3: randomize
def randomize_choices(item, seed):
    """Deterministic shuffle of the four options, key following its option.

    Never ask the model to randomise: a gpt-4.1-mini run put the answer at A in 92 of 100
    items. A respondent who always picks A would have scored 92%, and the closed-book number
    from that run (0.46) was fully explained by key/guess letter alignment (0.4477 expected,
    z=0.25) -- it measured position, not knowledge. Seeded by item id so it is reproducible,
    matching the deterministic source_idx shuffle the qa_generation MCQ converter uses.
    """
    values = [item[L] for L in LETTERS]
    correct_idx = LETTERS.index(item["correct"])
    order = list(range(4))
    random.Random(str(seed)).shuffle(order)
    out = {LETTERS[i]: values[order[i]] for i in range(4)}
    out["correct"] = LETTERS[order.index(correct_idx)]
    return out


# ---------------------------------------------------------------------- step 4: answer
def ask_letter(client, model, question, opts, context, temperature, system, effort=None):
    header = f"文章：\n{context}\n\n" if context else ""
    instr = "请只根据下面的文章作答。" if context else "没有提供文章。请凭已有知识猜最可能的答案。"
    body = "\n".join(f"{L}. {opts[L]}" for L in LETTERS)
    prompt = (f"{header}这是一道单项选择题。{instr}\n\n问题：{question}\n选项：\n{body}\n\n"
              f"只输出一个字母：A、B、C 或 D。")
    msgs = ([{"role": "system", "content": system}] if system else [])
    msgs.append({"role": "user", "content": prompt})
    m = LETTER_RE.search(chat(client, model, msgs, temperature, 8, effort))
    return m.group(0).upper() if m else "?"


# ------------------------------------------------------------------------------ helpers
def build_client(provider):
    from openai import OpenAI
    if provider == "ollama":
        return OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                      api_key="ollama")
    return OpenAI()


# GPT-5.x and the o-series are reasoning models and take a different call shape:
#   * 'max_tokens' is rejected -- it is 'max_completion_tokens'
#   * 'temperature' is rejected -- quality is controlled by 'reasoning_effort'
#   * reasoning tokens are charged against the completion budget, so a small cap (the 8 we
#     use for a single-letter answer) can be consumed entirely by reasoning and return an
#     empty string. Give reasoning models headroom regardless of the caller's cap.
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
REASONING_MIN_COMPLETION_TOKENS = 2000


def is_reasoning_model(model):
    return any(str(model).startswith(p) for p in REASONING_PREFIXES)


def chat(client, model, messages, temperature=0.0, max_tokens=400, effort=None):
    kwargs = {"model": model, "messages": messages}
    if is_reasoning_model(model):
        kwargs["max_completion_tokens"] = max(max_tokens, REASONING_MIN_COMPLETION_TOKENS)
        if effort:
            kwargs["reasoning_effort"] = effort
    else:
        kwargs["max_tokens"] = max_tokens
        kwargs["temperature"] = temperature
    r = client.chat.completions.create(**kwargs)
    return (r.choices[0].message.content or "").strip()


def parse_json(text):
    return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())


def pick(d, *names):
    for n in names:
        if (d / n).exists():
            return d / n
    return None


def load_entity_types(remap_dir, ch):
    """{pseudonym -> category} for one chapter, from the pseudonym remap master."""
    p = Path(remap_dir) / "_master.json"
    if not p.exists():
        return {}
    out = {}
    for row in json.loads(p.read_text(encoding="utf-8")):
        if len(row) >= 4 and row[0] == ch and row[3]:
            out.setdefault(row[3], row[2])
    return out


# --------------------------------------------------------------------------------- run
def run(args):
    client = build_client(args.provider)                        # rewriter (strong)
    aclient = build_client(args.answer_provider)                # answerer (small proxy)
    system = None if args.no_domain_hint else args.domain_hint
    root, report = Path(args.root), []

    rel_chain = eq_chain = None
    if args.rewrite_correct:
        from relevance_chain import build_equivalence_chain, check_equivalent  # noqa: F401
        globals()["check_equivalent"] = check_equivalent
        eq_chain = build_equivalence_chain(args.relevance_model, args.relevance_provider,
                                           reasoning_effort="low")
        print(f"answer length-match: on, verified by "
              f"{args.relevance_provider}:{args.relevance_model}")
    if args.relevance_check:
        from relevance_chain import (build_relevance_chain, audit_distractors,   # noqa: F401
                                     failing_letters, audit_feedback)
        globals().update(audit_distractors=audit_distractors,
                         failing_letters=failing_letters, audit_feedback=audit_feedback)
        rel_chain = build_relevance_chain(args.relevance_model, args.relevance_provider,
                                          reasoning_effort=args.relevance_effort)
        print(f"relevance audit: {args.relevance_provider}:{args.relevance_model} "
              f"(effort={args.relevance_effort}, retries={args.relevance_retries})")
        if args.relevance_model == args.model and args.relevance_provider == args.provider:
            print("[warn] the auditor and the rewriter are the SAME model -- this is "
                  "self-review and will under-report problems. Use a different "
                  "--relevance-model.", file=sys.stderr)

    de_novo_index = 0
    for ch in args.chapters:
        d = root / f"luke{ch}" / args.model_dir / "omission" / "0%"
        qf = pick(d, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
        pf = pick(d, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt")
        if not qf or not pf:
            print(f"[warn] missing files for luke{ch}", file=sys.stderr)
            continue
        passage = pf.read_text(encoding="utf-8")
        data = json.loads(qf.read_text(encoding="utf-8"))
        ents = load_entity_types(args.remap_dir, ch)

        for rec in data:
            iid = rec.get("passage_id")
            if args.de_novo:
                # Open items: a question and a correct answer, no options. The
                # correct letter cycles A,B,C,D across items so the de-novo set
                # does not inherit the position skew that build_rewrites_v2 had
                # to correct for (correct was B 35% of the time).
                answer = rec.get("A") if isinstance(rec.get("A"), str) else None
                if not answer or not str(answer).strip():
                    continue
                slot = LETTERS[de_novo_index % 4]
                de_novo_index += 1
                item = {L: "" for L in LETTERS}
                item[slot] = str(answer).strip()
                item["correct"] = slot
            else:
                if rec.get("q_type") != "mcq" or not isinstance(rec.get("A"), dict):
                    continue
                item = {L: rec["A"].get(L, "") for L in LETTERS}
                item["correct"] = rec.get("correct")
                if item["correct"] not in LETTERS or not all(item[L] for L in LETTERS):
                    print(f"[skip] luke{ch} {iid}: malformed options", file=sys.stderr)
                    continue

            # 1. context window
            window = randomized_three_verse_window(passage, rec)
            # This helper returns the WHOLE passage when the verse reference will not parse
            # or fewer than 2 verses are found. Those items are a different task, so flag
            # them instead of letting them blend into the open-book average.
            full_passage_fallback = window.strip() == passage.strip()

            # 2. rewrite the three distractors against that window
            try:
                rewritten = rewrite_distractors(client, args.model, item, rec["Q"], window,
                                                ents, args.rewrite_temperature,
                                                effort=args.rewrite_effort)
            except Exception as exc:
                print(f"[err ] luke{ch} {iid}: rewrite failed: {exc}", file=sys.stderr)
                continue

            # 2b. second model audits relevance, and we regenerate what it rejects.
            # A separate model on purpose: the model that wrote an option is the worst judge
            # of whether it is relevant.
            audit, audit_rounds = {}, 0
            for audit_rounds in range(1, args.relevance_retries + 2):
                notes = []
                if rel_chain is not None:
                    audit = audit_distractors(rel_chain, rec["Q"], rewritten,
                                              rewritten["correct"], window)
                    if failing_letters(audit):
                        notes.append(audit_feedback(audit))
                if not notes or audit_rounds > args.relevance_retries:
                    break
                rewritten = rewrite_distractors(
                    client, args.model, rewritten, rec["Q"], window, ents,
                    args.rewrite_temperature, feedback="\n".join(notes),
                    effort=args.rewrite_effort)

            # 2c. length-match the correct option to the three distractors, guarded so the
            # fact under test cannot drift.
            correct_before = rewritten[rewritten["correct"]]
            correct_rewritten = False
            if args.rewrite_correct:
                c = rewritten["correct"]
                dl = sorted(cjk_len(rewritten[L]) for L in LETTERS if L != c)
                target = dl[len(dl) // 2]                      # median of the three
                if abs(cjk_len(rewritten[c]) - target) > args.length_tolerance:
                    cand = rewrite_correct_option(client, args.model, rewritten, rec["Q"],
                                                  target, args.rewrite_effort)
                    # Guard fails CLOSED: without a verifier, or on any doubt, keep the
                    # original. A missed length match costs a little discriminating power;
                    # a drifted fact silently invalidates the item.
                    if cand and eq_chain is not None and check_equivalent(
                            eq_chain, rec["Q"], correct_before, cand):
                        rewritten[c] = cand
                        correct_rewritten = True

            # 3. randomize
            final = randomize_choices(rewritten, f"{args.shuffle_seed}:{iid}")
            opts = {L: final[L] for L in LETTERS}

            # 4. small model, closed book then open book
            try:
                closed = [ask_letter(aclient, args.answer_model, rec["Q"], opts, "",
                                     args.answer_temperature, system) for _ in range(args.k)]
                open_choice = ask_letter(aclient, args.answer_model, rec["Q"], opts, window,
                                         args.answer_temperature, system)
            except Exception as exc:
                print(f"[err ] luke{ch} {iid}: answering failed: {exc}", file=sys.stderr)
                continue

            closed_acc = sum(g == final["correct"] for g in closed) / max(1, args.k)
            report.append({
                "chapter": ch, "id": iid, "ref": rec.get("passage_reference"),
                "question": rec["Q"],
                "options": opts, "correct_letter": final["correct"],
                "original_options": {L: item[L] for L in LETTERS},
                "closed_book_guesses": closed, "closed_book_accuracy": closed_acc,
                "open_book_choice": open_choice,
                "open_book_correct": open_choice == final["correct"],
                "window": window, "window_is_full_passage": full_passage_fallback,
                "relevance_rounds": audit_rounds,
                "correct_rewritten": correct_rewritten,
                "correct_before": correct_before,
                "length_outliers": length_outliers(final, args.length_tolerance),
                "correct_len": cjk_len(final[final["correct"]]),
                "distractor_lens": [cjk_len(final[L]) for L in LETTERS
                                    if L != final["correct"]],
                "relevance_failed_after_retries": failing_letters(audit) if audit else [],
                "relevance_verdicts": {L: {"is_possible_answer": v.is_possible_answer,
                                           "reason": v.reason}
                                       for L, v in audit.items()},
            })
            rec["A"] = opts
            rec["correct"] = final["correct"]
            rec["_rewritten"] = True
            print(f"[ok  ] luke{ch} {iid} closed={closed_acc:.2f} "
                  f"open={'Y' if open_choice == final['correct'] else 'n'} "
                  f"key={final['correct']}"
                  + ("  [FULL-PASSAGE WINDOW]" if full_passage_fallback else ""))

        out_qf = qf if args.in_place else qf.with_suffix(".rewritten.json")
        out_qf.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  wrote {out_qf}")

    if args.save_mcq:
        save_mcq_bank(args, report)
    write_report(args, report)


def save_mcq_bank(args, report):
    """Persist the rewritten MCQs somewhere durable and versionable.

    The per-chapter ``*.rewritten.json`` files live under evaluation/outputs, which is a
    symlink into the separate research-outputs repo and gets overwritten on every rerun.
    This writes one consolidated, provenance-stamped bank into the main repo's datasets
    directory instead, so a set of items can be pointed at, diffed and re-imported later.
    """
    import datetime
    path = Path(args.save_mcq)
    path.parent.mkdir(parents=True, exist_ok=True)
    bank = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "rewrite_model": f"{args.provider}:{args.model}",
        "answer_model": f"{args.answer_provider}:{args.answer_model}",
        "shuffle_seed": args.shuffle_seed,
        "n_items": len(report),
        "items": [
            {
                "id": r["id"],
                "chapter": r["chapter"],
                "passage_reference": r["ref"],
                "question": r["question"],
                "options": r["options"],
                "correct": r["correct_letter"],
                "original_options": r["original_options"],
                "correct_rewritten": r.get("correct_rewritten", False),
                "correct_before": r.get("correct_before"),
                "answer_window": r["window"],
                "window_is_full_passage": r["window_is_full_passage"],
                "closed_book_accuracy": r["closed_book_accuracy"],
                "open_book_correct": r["open_book_correct"],
            }
            for r in report
        ],
    }
    if path.exists() and not args.overwrite_mcq:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
        print(f"[note] {args.save_mcq} exists; writing {path.name} instead "
              f"(use --overwrite-mcq to replace)")
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"mcq bank: {path}  ({len(report)} items)")


def write_report(args, report):
    outdir = Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "rewrite_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    n = len(report)
    key_dist = {L: sum(1 for r in report if r["correct_letter"] == L) for L in LETTERS}
    guess_dist = {L: sum(r["closed_book_guesses"].count(L) for r in report) for L in LETTERS}
    total_guesses = sum(len(r["closed_book_guesses"]) for r in report) or 1
    # What closed-book accuracy would be with ZERO knowledge, from key/guess letters lining
    # up alone. Compare against THIS, not against 0.25: with 100 items the realised key
    # distribution is not exactly uniform, and a letter-biased answerer shifts the null.
    expected = sum((key_dist[L] / max(1, n)) * (guess_dist[L] / total_guesses) for L in LETTERS)
    closed = sum(r["closed_book_accuracy"] for r in report) / max(1, n)
    open_acc = sum(r["open_book_correct"] for r in report) / max(1, n)

    summary = {
        "rewrite_model": args.model, "rewrite_provider": args.provider,
        "answer_model": args.answer_model, "answer_provider": args.answer_provider,
        "answer_temperature": args.answer_temperature, "k": args.k,
        "n_items": n, "chance": 0.25,
        "domain_hint": None if args.no_domain_hint else args.domain_hint,
        "closed_book_accuracy": round(closed, 4),
        "open_book_accuracy": round(open_acc, 4),
        # The number that matters: how much the passage adds over guessing.
        "dynamic_range": round(open_acc - closed, 4),
        "expected_accuracy_from_letter_alignment": round(expected, 4),
        "key_letter_distribution": key_dist,
        "guess_letter_distribution": guess_dist,
        "n_full_passage_window": sum(1 for r in report if r["window_is_full_passage"]),
        # If this approaches or beats closed_book_accuracy, the item set is being solved by
        # length rather than by knowledge -- exactly what happened on 2026-07-29 (81.8% vs
        # an observed 72.7%).
        # Ties are split, not credited: if the answer merely ties for shortest, a
        # length-guesser has to pick among the tied options. Counting ties as wins
        # overstated this at 0.778 when the fair value was 0.574.
        "shortest_option_heuristic_accuracy": (
            round(sum((1 / len(tied)) if r["correct_letter"] in tied else 0
                      for r in report
                      for tied in [[L for L in LETTERS
                                    if cjk_len(r["options"][L])
                                    == min(cjk_len(r["options"][x]) for x in LETTERS)]])
                  / max(1, n), 4)),
        "n_correct_uniquely_shortest": sum(
            1 for r in report
            if cjk_len(r["options"][r["correct_letter"]])
            < min(cjk_len(r["options"][x]) for x in LETTERS if x != r["correct_letter"])),
        "mean_len_correct": round(sum(r["correct_len"] for r in report) / max(1, n), 2),
        "mean_len_distractor": round(
            sum(sum(r["distractor_lens"]) for r in report) / max(1, 3 * n), 2),
        "n_length_outliers_remaining": sum(1 for r in report if r["length_outliers"]),
        "n_correct_rewritten": sum(1 for r in report if r.get("correct_rewritten")),
        "relevance_model": f"{args.relevance_provider}:{args.relevance_model}"
                           if args.relevance_check else None,
        "n_needed_relevance_rewrite": sum(1 for r in report if r.get("relevance_rounds", 0) > 1),
        "n_still_irrelevant_after_retries": sum(
            1 for r in report if r.get("relevance_failed_after_retries")),
    }
    # Needs enough items to distinguish skew from multinomial noise: at n=9 there is a 63%
    # chance some letter holds >=4 purely by chance, so the old threshold cried wolf.
    if n >= 40 and max(key_dist.values()) > 0.4 * n:
        summary["key_skew_warning"] = (f"key concentrated on one letter "
                                       f"({max(key_dist.values())}/{n})")
    if n and closed <= expected + 0.02:
        summary["note"] = ("closed-book accuracy is at or below what letter alignment alone "
                           "predicts -- no evidence of prior answerability")
    (outdir / "rewrite_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"report:  {outdir / 'rewrite_report.json'}")
    print(f"summary: {outdir / 'rewrite_summary.json'}")


# --------------------------------------------------------------------------- self-test
def self_test():
    import types
    cases = []
    src = {"A": "correct-opt", "B": "d1", "C": "d2", "D": "d3", "correct": "A"}
    keys, ok = [], True
    for i in range(4000):
        out = randomize_choices(src, f"seed:{i}")
        if out[out["correct"]] != "correct-opt" or {out[L] for L in LETTERS} != {src[L] for L in LETTERS}:
            ok = False
        keys.append(out["correct"])
    cases.append(("randomize keeps content and key together", ok))
    share = {L: keys.count(L) / len(keys) for L in LETTERS}
    cases.append((f"randomize spreads the key uniformly {share}",
                  all(0.22 <= s <= 0.28 for s in share.values())))
    cases.append(("randomize is deterministic",
                  randomize_choices(src, "x") == randomize_choices(src, "x")))

    seen = {}

    def stub(text):
        class S:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        seen["system"] = kw["messages"][0]["content"]
                        seen["user"] = kw["messages"][-1]["content"]
                        return types.SimpleNamespace(choices=[types.SimpleNamespace(
                            message=types.SimpleNamespace(content=text))])
        return S()

    window = "13 天使对他说：不要害怕，珂温，你的妻子哈丽要生一个儿子。14 他必带来喜乐。"
    ents = {"珂温": "person", "哈丽": "person", "米珥": "person"}     # 米珥 not in window
    item = {"A": "甲", "B": "正确答案", "C": "丙", "D": "丁", "correct": "B"}
    good = stub('{"A":"x1","B":"KEEP","C":"x3","D":"x4","correct":"C"}')
    out = rewrite_distractors(good, "m", item, "天使对谁说话？", window, ents)
    cases.append(("rewrite keeps the correct option and key",
                  out["correct"] == "B" and out["B"] == "正确答案"))
    cases.append(("rewrite replaces the distractors", out["A"] == "x1" and out["D"] == "x4"))
    cases.append(("answer context is inside the SYSTEM prompt",
                  window in seen["system"] and window not in seen["user"]))
    cases.append(("entity menu is window-scoped and in the system prompt",
                  "珂温" in seen["system"] and "米珥" not in seen["system"]))
    cases.append(("wording permits going outside the context, but demands conviction",
                  "lies outside the context" in seen["system"]
                  and "CONVINCING" in seen["system"]))
    cases.append(("relevance rule outranks grounding",
                  seen["system"].index("POSSIBLE ANSWER")
                  < seen["system"].index("PREFER MATERIAL")))
    cases.append(("worked example of the true-but-irrelevant failure is present",
                  "隆松的后裔" in seen["system"] and "RECAST" in seen["system"]))

    # ---- de-novo mode (after the `seen`-dependent cases: the stub shares one
    # `seen` dict, so calling it here would clobber the prompts they inspect) ----
    sys_rw = build_rewrite_system("W", "", de_novo=False)
    sys_dn = build_rewrite_system("W", "", de_novo=True)
    cases.append(("de-novo reframes task from rewrite to write",
                  "You WRITE the three DISTRACTORS" in sys_dn
                  and "You rewrite the three DISTRACTORS" not in sys_dn
                  and "You rewrite the three DISTRACTORS" in sys_rw))
    cases.append(("de-novo keeps all four content rules",
                  all(k in sys_dn for k in ("POSSIBLE ANSWER TO THE QUESTION",
                                            "PREFER MATERIAL FROM THE ANSWER CONTEXT",
                                            "MATCH THE ANSWER'S TYPE",
                                            "KEEP THE FOUR OPTIONS PARALLEL"))))
    cases.append(("de-novo drops the 'keep the other three' instruction",
                  "Rewrite only the other three" not in sys_dn))
    blank = {"A": "correct", "B": "", "C": "", "D": "", "correct": "A"}
    bad = stub("not json at all")
    try:
        rewrite_distractors(bad, "m", blank, "Q?", "W")
        raised = False
    except DistractorGenerationError:
        raised = True
    cases.append(("de-novo raises rather than emitting blank options", raised))
    full = {"A": "correct", "B": "d1", "C": "d2", "D": "d3", "correct": "A"}
    cases.append(("rewrite mode still falls back to the original on bad JSON",
                  rewrite_distractors(bad, "m", full, "Q?", "W")["B"] == "d1"))

    cases.append(("unparseable rewrite falls back to the original item",
                  rewrite_distractors(stub("not json"), "m", item, "q", window)["B"] == "正确答案"))

    bad = 0
    for name, passed in cases:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        bad += not passed
    print(f"\n{len(cases) - bad}/{len(cases)} self-tests passed")
    return 1 if bad else 0


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--chapters", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6, 7, 8])
    ap.add_argument("--model-dir", default="1.7b")
    ap.add_argument("--remap-dir", default="evaluation/datasets/pseudonym_remap")
    # rewriter
    ap.add_argument("--provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--model", default="gpt-5.6-terra",
                    help="rewriter. GPT-5.6: sol $5/$30, terra $2.50/$15, "
                         "luna $1/$6 per MTok")
    ap.add_argument("--rewrite-temperature", type=float, default=0.4,
                    help="ignored for reasoning models (gpt-5.x, o-series)")
    ap.add_argument("--rewrite-effort", default="medium",
                    choices=["none", "low", "medium", "high", "xhigh", "max"],
                    help="reasoning_effort for the rewriter; ignored for non-reasoning models")
    # answerer
    ap.add_argument("--answer-provider", default="ollama", choices=["openai", "ollama"])
    ap.add_argument("--answer-model", default="qwen2.5:1.5b")
    ap.add_argument("--answer-temperature", type=float, default=0.0)
    ap.add_argument("--k", type=int, default=1,
                    help="closed-book samples per item (1 = one pass per question)")
    ap.add_argument("--domain-hint", default="你正在回答关于一段宗教经文的阅读理解选择题。",
                    help="says 'a religious text', not 'the Bible': naming the Bible invites "
                         "the answerer to use canonical knowledge, the leak the "
                         "pseudonymisation exists to close")
    ap.add_argument("--no-domain-hint", action="store_true")
    # relevance audit (second model)
    ap.add_argument("--relevance-check", dest="relevance_check", action="store_true",
                    default=True, help="audit distractors with a second model (default: on)")
    ap.add_argument("--no-relevance-check", dest="relevance_check", action="store_false")
    ap.add_argument("--relevance-provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--relevance-model", default="gpt-5.6-sol",
                    help="second model that judges whether each distractor is a possible "
                         "ANSWER to the question. Use a DIFFERENT model from --model: the "
                         "model that wrote an option is the worst judge of it.")
    ap.add_argument("--relevance-effort", default="medium",
                    choices=["none", "low", "medium", "high", "xhigh", "max"],
                    help="reasoning_effort for GPT-5.x/o-series auditors; ignored otherwise")
    ap.add_argument("--relevance-retries", type=int, default=1,
                    help="regeneration rounds when the auditor rejects a distractor")
    ap.add_argument("--rewrite-correct", dest="rewrite_correct", action="store_true",
                    default=True,
                    help="rephrase the CORRECT option to match the distractors' length, "
                         "guarded by an equivalence check (default: on)")
    ap.add_argument("--no-rewrite-correct", dest="rewrite_correct", action="store_false")
    ap.add_argument("--length-tolerance", type=int, default=3,
                    help="how far the correct option may sit from the distractors' median "
                         "length before it is rephrased")
    ap.add_argument("--shuffle-seed", default="mcq-key")
    ap.add_argument("--in-place", action="store_true",
                    help="overwrite qa_target_pseudonymized.json (default: .rewritten.json)")
    ap.add_argument("--out-dir", default="evaluation/outputs/reports/rewrite_distractors")
    ap.add_argument("--save-mcq", default="evaluation/datasets/mcq/mcq_rewritten.json",
                    help="durable, provenance-stamped bank of the rewritten MCQs, written "
                         "into the main repo (the per-chapter .rewritten.json files live "
                         "under the outputs symlink and are overwritten each run). "
                         "Pass '' to skip.")
    ap.add_argument("--overwrite-mcq", action="store_true",
                    help="replace --save-mcq instead of writing a timestamped sibling")
    ap.add_argument(
        "--de-novo",
        action="store_true",
        help=("Write distractors from scratch for OPEN items (question + correct "
              "answer only). The correct letter cycles A,B,C,D across items to "
              "avoid position skew. Without this, items lacking four options are "
              "skipped as malformed."),
    )
    ap.add_argument("--self-test", action="store_true", help="offline checks, no API")
    return ap.parse_args()


if __name__ == "__main__":
    _a = parse_args()
    sys.exit(self_test() if _a.self_test else run(_a))
