#!/usr/bin/env python3
"""Rewrite gold72 distractors on the ENGLISH SOURCE, before translation.

Why English source rather than the Chinese cells: the fix then survives
re-translation, propagates to every model and both naming arms through the normal
translate step, and carries into the human pilot. Rewriting the Chinese in output
cells would have to be redone per arm and (before SHARE_QA) per model.

Measured problem this addresses (gold72, ~159 observations/item):
    distractors never selected by ANY model in ANY cell : 86/216 (40%)
    mean EFFECTIVE options per item                     : 2.81 (design assumes 4)
    omission dz, items with 0 dead distractors          : 0.492
    omission dz, items with 2-3 dead distractors        : 0.233
Dead distractors cost 2.1x the dose sensitivity the experiment exists to measure.

Reuses the prompt design, relevance framing, length matching and deterministic
shuffle from rewrite_distractors.py (16/16 self-tests) and supplies English inputs:
  - QA        evaluation/datasets/qa/tier1_gold72_canonical_5opt
  - windows   QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json
  - passages  evaluation/datasets/passages/tier1_bsb

Option E (the abstention) is held out of the rewrite AND out of the shuffle, then
re-appended last, so it never becomes the keyed answer and never moves position.

TWO GATES audit every item against its own verse window before it is written. They are
complements, they run in ONE loop, and a single regeneration round has to satisfy both:

  --relevance-check   is each distractor a possible ANSWER to the question? One that is not
                      is a free elimination -- discardable without reading the passage. This
                      is the dead-distractor mechanism (gold72: 86/216 distractors never
                      selected by any model, 2.81 effective options against a design
                      assumption of 4).
  --falseness-check   is each distractor a WRONG answer given the window? One the window
                      SUPPORTS -- including one that merely paraphrases the key -- leaves the
                      item with two defensible answers. Added 2026-09-13, after nothing
                      audited this and the rewrite shipped distractor/window word overlap
                      0.145 -> 0.511 and open-book 0.958 -> 0.831.

Silence is not a defect: a distractor the window neither supports nor refutes is exactly what
a good distractor looks like. Both gates default to AUTO -- on precisely when the LLM rewriter
runs, off for --verify-only and curated pass-through so neither starts spending by surprise.
Pass a flag explicitly to audit the EXISTING items without rewriting them.

Usage:
  set -a; source .env; set +a
  python3 evaluation/scripts/mcq/preparation/rewrite_distractors_gold72_en.py --self-test
  python3 evaluation/scripts/mcq/preparation/rewrite_distractors_gold72_en.py \
      --model gpt-5.6-terra --relevance-model gpt-5.6-sol \
      --answer-provider ollama --answer-model qwen2.5:1.5b
  # audit the existing items without rewriting anything:
  python3 evaluation/scripts/mcq/preparation/rewrite_distractors_gold72_en.py \
      --verify-only --no-verify --relevance-check --falseness-check
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))
# relevance_chain / audit_verdicts are imported by bare name (rewrite_distractors does the
# same from run()), so the preparation dir has to be importable, not just the repo root.
if str(HERE) not in sys.path: sys.path.insert(0, str(HERE))
import evaluation.scripts.mcq.preparation.rewrite_distractors as rd   # noqa: E402

LETTERS = "ABCD"
LABELS = "ABCDEF"
# Must match add_meta_options.py exactly; they are matched by TEXT, not by position.
ABSTAIN_EN = "I can't tell from this passage"      # E -- a claim about the READER
NOTA_EN = "None of the above"                      # F -- a claim about the OPTION SET
META_EN = (ABSTAIN_EN, NOTA_EN)


def split_meta(options):
    """Peel the trailing meta-options off an option list. Returns (content, meta).

    add_meta_options.py APPENDS these after any shuffle so their letters never move, and
    neither is ever the keyed answer. So this driver must hold them out of the rewrite and
    out of the shuffle, then put them back in their original order -- which makes it work
    unchanged on the 4-, 5- and 6-option variants of the same items. They are identified by
    text rather than by counting back from the end, so a 4-option set whose last distractor
    happens to sit in the tail position is never mistaken for a meta-option.
    """
    content, meta = [str(o) for o in options], []
    while content and content[-1].strip() in META_EN:
        meta.insert(0, content.pop())
    return content, meta
PASSAGE_FILE = {
    "t1_1kgs13":"1kgs_13_1-34","t1_2chr26":"2chr_26_1-23","t1_2kgs11":"2kgs_11_1-21",
    "t1_2kgs6_7":"2kgs_6_24-7_20","t1_2sam21":"2sam_21_15-22","t1_acts19":"acts_19_11-20",
    "t1_acts20":"acts_20_7-12","t1_acts23":"acts_23_12-35","t1_judg17_18":"judg_17_1-18_31",
    "t1_judg9":"judg_9_1-57",
}

# ---- English mode: swap the two Chinese-specific pieces of the shared module ----
def en_len(s): return len(str(s or "").split())          # words, not CJK characters
def install_english_mode():
    rd.cjk_len = en_len
    rd.REWRITE_SYSTEM_TEMPLATE = rd.REWRITE_SYSTEM_TEMPLATE.replace(
        "Chinese reading-comprehension MCQ", "English reading-comprehension MCQ")

def key_separable_by_length(options, correct, tolerance):
    """True if the KEY can be picked out by length alone, without reading anything.

    Both gates judge the distractors and are explicitly told not to judge the correct
    option, so neither can see this. On 2026-09-13 that let t1_2sam21/kjsg ship with a
    2-word key against 8/8/11-word distractors -- a giveaway far worse than the defect
    the rewrite was called in to fix.
    """
    dl = [rd.cjk_len(options[L]) for L in LETTERS if L != correct]
    kl = rd.cjk_len(options[correct])
    return bool(dl) and (kl < min(dl) - tolerance or kl > max(dl) + tolerance)


def norm_q(q): return re.sub(r"\s+", " ", (q or "").strip().lower())
def item_question(it):
    return str((it.get("open") or {}).get("original_question") or it.get("question") or "").strip()
def win_key(pid, q, occ=0):
    return f"{pid}:{hashlib.sha1(norm_q(q).encode()).hexdigest()[:10]}#{occ}"

def parse_passage(stem, pdir):
    m = re.match(r"^[0-9]?[a-z]+_(\d+)_(\d+)-(?:(\d+)_)?(\d+)$", stem)
    c0, v0 = int(m.group(1)), int(m.group(2))
    idx, ch, prev = {}, int(m.group(1)), None
    for b in [x.strip() for x in (Path(pdir)/f"{stem}.txt").read_text(encoding="utf-8").split("\n\n") if x.strip()]:
        mm = re.match(r"^(\d+)\s+(.*)$", b, re.S); n = int(mm.group(1))
        if prev is None: v = v0
        elif n == prev + 1: v = n
        else: ch = n; v = 1
        idx[(ch, v)] = mm.group(2).strip(); prev = v
    return idx

def ask_letter_en(client, model, question, opts, context, temperature, effort=None):
    head = f"Passage:\n{context}\n\n" if context else ""
    instr = ("Answer using ONLY the passage above." if context
             else "No passage is provided. Guess the most likely answer from prior knowledge.")
    body = "\n".join(f"{L}. {opts[L]}" for L in LETTERS)
    prompt = (f"{head}This is a multiple-choice question. {instr}\n\n"
              f"Question: {question}\nOptions:\n{body}\n\nReply with one letter only: A, B, C, or D.")
    out = rd.chat(client, model, [{"role":"user","content":prompt}], temperature, 8, effort)
    m = re.search(r"[A-Da-d]", out or "")
    return m.group(0).upper() if m else "?"

def gate_on(flag, need_llm):
    """Resolve --falseness-check. None = auto: on exactly when the LLM rewriter runs, so a
    --verify-only or curated pass-through run never starts spending API money by surprise."""
    return bool(need_llm) if flag is None else bool(flag)


def self_test():
    ok = []
    install_english_mode()
    ok.append(("English length is word-based", en_len("the man of God") == 4))
    ok.append(("prompt says English not Chinese",
               "English reading-comprehension MCQ" in rd.REWRITE_SYSTEM_TEMPLATE
               and "Chinese reading-comprehension MCQ" not in rd.REWRITE_SYSTEM_TEMPLATE))
    it = {"A":"w","B":"x","C":"y","D":"z","correct":"C"}
    sh = rd.randomize_choices(dict(it), "seed-1")
    ok.append(("shuffle preserves the keyed text", sh[sh["correct"]] == "y"))
    ok.append(("shuffle is deterministic", rd.randomize_choices(dict(it), "seed-1") == sh))
    ok.append(("shuffle touches only 4 options", set(sh) == set("ABCD") | {"correct"}))
    idx = {("9",1):"x"}
    ok.append(("window key is content-addressed",
               win_key("p","Who ran?") == win_key("p"," who  RAN? ")))
    ok.append(("abstention never enters the shuffle", ABSTAIN_EN not in sh.values()))
    # ---- meta-options: the same driver must serve the 4-, 5- and 6-option variants ----
    core = ["w", "x", "y", "z"]
    ok.append(("4-option set has no meta tail", split_meta(core) == (core, [])))
    ok.append(("5-option set peels the abstention",
               split_meta(core + [ABSTAIN_EN]) == (core, [ABSTAIN_EN])))
    ok.append(("6-option set peels both, in order",
               split_meta(core + [ABSTAIN_EN, NOTA_EN]) == (core, [ABSTAIN_EN, NOTA_EN])))
    ok.append(("peeling is by text, so a 4th distractor is never mistaken for meta",
               split_meta(["w", "x", "y", "None of the above but different"])[1] == []))
    ok.append(("meta text matches add_meta_options.py",
               ABSTAIN_EN == "I can't tell from this passage"
               and NOTA_EN == "None of the above"))
    _sh = rd.randomize_choices({"A": "w", "B": "x", "C": "y", "D": "z", "correct": "B"}, "s")
    _final = [_sh[L] for L in LETTERS] + [ABSTAIN_EN, NOTA_EN]
    ok.append(("meta-options re-append last and keep E/F",
               _final[4] == ABSTAIN_EN and _final[5] == NOTA_EN
               and LABELS[:len(_final)] == "ABCDEF"))
    ok.append(("the key is always a content option, never meta",
               _final[LABELS.index(_sh["correct"])] not in META_EN))
    # The loop skips when ki >= len(content options). Exercise that condition directly
    # rather than grepping the source -- a source grep finds its own assertion line.
    # ---- guard: the key must not be pickable by length alone ----
    install_english_mode()
    _kj = {"A": "By driving Ishbi Benob away without killing him.",
           "B": "By taking David away from the battlefield before the attack.",
           "C": "Ishbi Benob", "D": "By confronting the Philistine but sparing him."}
    ok.append(("the kjsg failure is caught: 2-word key against 8-word distractors",
               key_separable_by_length(_kj, "C", 3)))
    _ok4 = {"A": "As one undivided force.", "B": "By assigned divisions.",
            "C": "Without organized divisions.", "D": "As an untrained militia."}
    ok.append(("a parallel option set is not flagged",
               not key_separable_by_length(_ok4, "B", 3)))
    ok.append(("a key that is uniquely LONG is flagged too",
               key_separable_by_length({"A": "one two three four five six seven eight",
                                        "B": "a", "C": "b", "D": "c"}, "A", 3)))
    ok.append(("tolerance is honoured, not ignored",
               not key_separable_by_length({"A": "a b c d e", "B": "a b", "C": "a b",
                                            "D": "a b"}, "A", 3)))
    _content5 = split_meta(core + [ABSTAIN_EN])[0]
    _content6 = split_meta(core + [ABSTAIN_EN, NOTA_EN])[0]
    ok.append(("a content key is in range for every variant",
               all(LABELS.index(L) < len(c) for L in "ABCD"
                   for c in (core, _content5, _content6))))
    ok.append(("a meta key is out of range, so the item is skipped not re-keyed to A",
               LABELS.index("E") >= len(_content5)
               and LABELS.index("F") >= len(_content6)
               and LABELS.index("E") >= len(_content6)))
    ok.append(("all 10 passages mapped", len(PASSAGE_FILE) == 10))
    # ---- falseness gate ----
    ok.append(("gate auto-on when the rewriter runs", gate_on(None, True) is True))
    ok.append(("gate auto-off for verify-only / curated pass-through",
               gate_on(None, False) is False))
    ok.append(("--falseness-check forces it on without the rewriter",
               gate_on(True, False) is True))
    ok.append(("--no-falseness-check wins over auto", gate_on(False, True) is False))
    from audit_verdicts import (falseness_failing_letters as _ffl,
                                falseness_feedback as _ffb,
                                falseness_status_counts as _fsc)

    class _V:
        def __init__(self, st, why="r", q=None, fix=None):
            self.answer_status, self.reason, self.quote, self.suggested_fix = st, why, q, fix

    _a = {"B": _V("supported", "v13 says exactly this", "13 ..."), "C": _V("unsupported"),
          "D": _V("contradicted")}
    ok.append(("only 'supported' fails the gate", _ffl(_a) == ["B"]))
    ok.append(("silence is not a defect", _ffl({"C": _V("unsupported")}) == []))
    ok.append(("auditor error fails OPEN (item kept, reported unaudited)", _ffl({}) == []))
    ok.append(("feedback quotes the supporting span",
               "the context says: 13 ..." in _ffb(_a) and "- C" not in _ffb(_a)))
    ok.append(("status counts tally", _fsc(_a) == {"supported": 1, "contradicted": 1,
                                                   "unsupported": 1}))
    ok.append(("falseness rule reached the shared rewrite prompt",
               "EVERY DISTRACTOR MUST BE FALSE FOR THIS PASSAGE" in rd.REWRITE_SYSTEM_TEMPLATE))
    for name, cond in ok: print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    n = sum(1 for _, c in ok if c)
    print(f"\n{n}/{len(ok)} self-tests passed")
    return 0 if n == len(ok) else 1

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qa-dir", default="evaluation/datasets/qa/tier1_gold72_canonical_5opt")
    ap.add_argument("--out-dir", default="evaluation/datasets/qa/tier1_gold72_canonical_5opt_rw")
    ap.add_argument("--passage-dir", default="evaluation/datasets/passages/tier1_bsb")
    ap.add_argument("--windows", default="QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json")
    ap.add_argument("--provider", default="openai"); ap.add_argument("--model", default="gpt-5.6-terra")
    ap.add_argument("--rewrite-temperature", type=float, default=0.4)
    ap.add_argument("--rewrite-effort", default="medium")
    # Relevance gate: is each distractor a possible ANSWER to the question, or can it be
    # discarded on relevance alone without reading the passage? Same window, same loop and
    # same auto-default as the falseness gate; these flags existed and were DEAD until
    # 2026-09-13 -- accepted on the command line, shown in the usage example above, read by
    # nothing.
    ap.add_argument("--relevance-check", dest="relevance_check", action="store_true",
                    default=None,
                    help="audit that each distractor is a possible ANSWER (default: auto -- "
                         "on exactly when the rewriter runs). Pass it with --verify-only to "
                         "measure how many of the EXISTING distractors are free "
                         "eliminations: that, not truth, is the dead-distractor mechanism.")
    ap.add_argument("--no-relevance-check", dest="relevance_check", action="store_false")
    ap.add_argument("--relevance-provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--relevance-model", default="gpt-5.6-sol")
    ap.add_argument("--relevance-effort", default="medium",
                    choices=["none", "low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--relevance-retries", type=int, default=1)
    ap.add_argument("--length-tolerance", type=int, default=3)
    ap.add_argument("--shuffle-seed", default="mcq-key")
    ap.add_argument("--verify", dest="verify", action="store_true", default=True)
    ap.add_argument("--no-verify", dest="verify", action="store_false")
    ap.add_argument("--answer-provider", default="ollama")
    ap.add_argument("--answer-model", default="qwen2.5:1.5b")
    ap.add_argument("--report", default="evaluation/outputs/reports/rewrite_gold72_en.json")
    ap.add_argument("--limit", type=int, default=0, help="only N items, for a cheap smoke test")
    ap.add_argument("--curated", default="",
                    help="JSON of hand-drafted replacements {id: {distractors:[3]}}. Applies them "
                         "deterministically INSTEAD of calling the rewriter. The LLM rewrite was "
                         "measured worse on every axis (closed-book unchanged 0.394, open-book "
                         "0.958->0.831, 9 items made unanswerable) because it produced near-correct "
                         "options; curated mode keeps the generation out and reuses the verifier.")
    ap.add_argument("--rewrite-rest", action="store_true",
                    help="with --curated, ALSO send the non-curated items to the LLM rewriter. "
                         "Off by default: a curated run leaves everything else untouched. The "
                         "rewriter is measured harmful (open-book 0.958 -> 0.831), so this is "
                         "opt-in only.")
    ap.add_argument("--only", default="",
                    help="comma-separated item ids to process; others are passed through untouched")
    ap.add_argument("--verify-only", action="store_true",
                    help="measure closed/open book on the INPUT QA without rewriting, to get a "
                         "before-baseline. Applies the SAME deterministic shuffle as the rewrite "
                         "path, so the comparison isolates distractor quality rather than the "
                         "key's position (a mis-aligned key can explain a closed-book number "
                         "on its own).")
    ap.add_argument("--falseness-check", dest="falseness_check", action="store_true",
                    default=None,
                    help="audit that each distractor is a WRONG answer given its window. "
                         "Default: auto -- on exactly when the LLM rewriter runs, off for "
                         "--verify-only and curated pass-through (those spend no API money "
                         "by default). Pass this flag to force it on, e.g. to find which of "
                         "the EXISTING items already carry a supported distractor.")
    ap.add_argument("--no-falseness-check", dest="falseness_check", action="store_false")
    ap.add_argument("--falseness-provider", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--falseness-model", default="gpt-5.6-sol",
                    help="judge for the falseness gate. Must differ from --model: the model "
                         "that lifted a true statement out of the window is the worst judge "
                         "of whether it is true.")
    ap.add_argument("--falseness-effort", default="medium",
                    choices=["none", "low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--falseness-retries", type=int, default=1,
                    help="regeneration rounds when the gate rejects a distractor. Applies to "
                         "LLM-rewritten items only -- curated replacements are reported, "
                         "never silently regenerated.")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return self_test()

    install_english_mode()

    # Hand-drafted replacements, applied INSTEAD of calling the rewriter. The LLM
    # rewrite was measured worse on every axis: closed-book unchanged (0.394),
    # open-book 0.958 -> 0.831, 9 items made unanswerable. Cause: its prompt ranks
    # "must be a possible answer" and "prefer window material" above a single
    # sentence requiring the distractor be FALSE, and inside 3 verses those three
    # constraints are often unsatisfiable together -- measured, the rewrite raised
    # distractor/window word overlap from 0.145 to 0.511. Nothing audits falseness.
    curated = {}
    if a.curated:
        curated = {k: v for k, v in json.load(open(a.curated)).items() if not k.startswith("_")}
        print(f"curated replacements loaded: {len(curated)} item(s)")
        flagged = [k for k, v in curated.items() if v.get("flag")]
        if flagged:
            print(f"  FLAGGED, review before trusting: {flagged}")
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    if only:
        print(f"restricted to {len(only)} item id(s)")
    # Index by content_id, matching generate_chinese_answers.load_verse_windows.
    # The "key"/"span_key" fields are build-time annotation artifacts and are NOT
    # what the pipeline looks windows up by; content_id is shared across the
    # canonical and pseudonymized arms, so one windows file serves both.
    W = json.load(open(a.windows))
    wins = {str(w.get("content_id") or "").strip(): w for w in W["windows"] if w.get("content_id")}
    _need_llm = not a.verify_only and (a.rewrite_rest or not curated)
    client = rd.build_client(a.provider) if _need_llm else None
    if curated and not a.rewrite_rest:
        print('curated mode: non-curated items pass through untouched, no LLM calls')
    # Auto: on exactly when the rewriter runs. --verify-only and curated pass-through get
    # it only if asked, so neither path can quietly start spending API money -- but forcing
    # it on for --verify-only is the cheapest way to find which EXISTING items already have
    # a distractor the window supports.
    a.falseness_check = gate_on(a.falseness_check, _need_llm)
    a.relevance_check = gate_on(a.relevance_check, _need_llm)
    rel_chain = fal_chain = None
    if a.relevance_check:
        from relevance_chain import (build_relevance_chain, audit_distractors,  # noqa: F401
                                     failing_letters, audit_feedback)
        rel_chain = build_relevance_chain(a.relevance_model, a.relevance_provider,
                                          reasoning_effort=a.relevance_effort)
        print(f"relevance gate: {a.relevance_provider}:{a.relevance_model} "
              f"(effort={a.relevance_effort})")
        if a.relevance_model == a.model and a.relevance_provider == a.provider:
            print("[warn] the relevance judge and the rewriter are the SAME model -- "
                  "self-review. Use a different --relevance-model.", file=sys.stderr)
    if a.falseness_check:
        from relevance_chain import build_falseness_chain, audit_falseness    # noqa: F401
        from audit_verdicts import (falseness_failing_letters, falseness_feedback,
                                    falseness_status_counts)
        fal_chain = build_falseness_chain(a.falseness_model, a.falseness_provider,
                                          reasoning_effort=a.falseness_effort)
        print(f"falseness gate: {a.falseness_provider}:{a.falseness_model} "
              f"(effort={a.falseness_effort})")
        if a.falseness_model == a.model and a.falseness_provider == a.provider:
            print("[warn] the falseness judge and the rewriter are the SAME model -- "
                  "self-review, and it will under-report. Use a different "
                  "--falseness-model.", file=sys.stderr)
    if rel_chain is not None or fal_chain is not None:
        print(f"  audit retries: {max(a.relevance_retries, a.falseness_retries)} "
              f"(LLM-rewritten items only)")
    ans_client = rd.build_client(a.answer_provider) if a.verify else None
    if not a.verify_only: os.makedirs(a.out_dir, exist_ok=True)
    report, done = [], 0

    for fn in sorted(os.listdir(a.qa_dir)):
        if not fn.endswith(".json"): continue
        items = json.load(open(os.path.join(a.qa_dir, fn)))
        pid = next((x.get("passage_id") or str(x.get("content_id","")).split(":")[0])
                   for x in items if isinstance(x, dict)
                   and (x.get("passage_id") or x.get("content_id")))
        idx = parse_passage(PASSAGE_FILE[pid], a.passage_dir)
        occ = {}
        for it in items:
            mcq = it.get("mcq")
            if not mcq: continue
            cid0 = str(it.get("content_id") or "")
            if not it.get("id") and ":" in cid0: it["id"] = cid0.split(":",1)[1].split("#")[0]
            if not it.get("passage_id") and ":" in cid0: it["passage_id"] = cid0.split(":",1)[0]
            if not it.get("id") or not it.get("passage_id"):
                print(f"[skip] malformed record (no id/content_id): {sorted(it)[:6]}", file=sys.stderr)
                continue
            opts = list(mcq.get("mcq_options") or [])
            opts, meta_opts = split_meta(opts)
            if len(opts) != 4:
                print(f"[skip] {pid}/{it['id']}: expected 4 content options (+meta), got "
                      f"{len(opts)}+{len(meta_opts)}", file=sys.stderr); continue
            if a.limit and done >= a.limit: break
            keyed = re.search(r"<answer>([A-F])<answer>", mcq.get("content", ""))
            if not keyed: print(f"[skip] {pid}/{it['id']}: no key", file=sys.stderr); continue
            ki = LABELS.index(keyed.group(1))
            if ki >= len(opts):
                # Was silently re-keyed to A before 2026-09-13. A meta-keyed item is a
                # data error upstream, not something to paper over: abstention and
                # none-of-the-above are never the answer.
                print(f"[skip] {pid}/{it['id']}: key {keyed.group(1)} is a META-option "
                      f"(abstention/NOTA is never the answer)", file=sys.stderr); continue
            q = item_question(it)
            cid = str(it.get("content_id") or f"{pid}:{it['id']}").strip()
            w = wins.get(cid) or wins.get(cid.split("#")[0])
            if not w: print(f"[skip] {pid}/{it['id']}: no window", file=sys.stderr); continue
            ch = int(str(it.get("reference", "0:0")).split(":")[0])
            window = "\n".join(f"{v} {idx.get((ch, int(str(v).split(':')[-1])), '')}"
                               for v in [int(str(x).split(':')[-1]) for x in w["window"]])
            base = {LETTERS[i]: opts[i] for i in range(4)}
            base["correct"] = LETTERS[ki]
            if only and it["id"] not in only:
                continue
            if it["id"] in curated:
                repl = list(curated[it["id"]]["distractors"])
                new = {"correct": base["correct"]}
                slots = [L for L in LETTERS if L != base["correct"]]
                new[base["correct"]] = base[base["correct"]]       # key text never changes
                for L, txt in zip(slots, repl): new[L] = txt
                src = "curated"
                print(f"[cur ] {pid}/{it['id']} {curated[it['id']].get('fault','')}")
            elif a.verify_only or (curated and not a.rewrite_rest):
                new = dict(base)          # pass through untouched
                src = "passthrough"
            else:
                src = "llm"
                try:
                    new = rd.rewrite_distractors(client, a.model, base, q, window,
                                                 temperature=a.rewrite_temperature, effort=a.rewrite_effort)
                except Exception as exc:
                    print(f"[err ] {pid}/{it['id']}: {exc}", file=sys.stderr); new = base
            new["correct"] = base["correct"]

            # ---- falseness gate ------------------------------------------------------
            # Is each distractor a WRONG answer given THIS window? Only "supported" fails:
            # an option the window is silent about is what a good distractor looks like, and
            # treating silence as a defect is how the hand-drafted set went the other way
            # (implausible options, closed-book 0.154 -> 0.462 on the curated items).
            # Regeneration is offered to LLM items only -- a curated replacement is the
            # user's text, so a failure there is reported and left alone.
            # ONE loop, both gates. They are complements and they pull against each other:
            # relevance wants an option that could be the answer, falseness wants one that
            # is not. Auditing in series would double the rewrite calls and let each gate
            # reintroduce the other's failure. Auditing together means one regeneration
            # round sees both objections and has to satisfy both at once.
            ra, rfail, fa, ffail, rounds, rfail_all3 = {}, [], {}, [], 0, False
            if rel_chain is not None or fal_chain is not None:
                retries = (max(a.relevance_retries, a.falseness_retries)
                           if src == "llm" else 0)
                for rounds in range(1, retries + 2):
                    notes = []
                    if rel_chain is not None:
                        ra = audit_distractors(rel_chain, q, new, new["correct"], window)
                        rfail = failing_letters(ra)
                        if len(rfail) >= 3:
                            # Three simultaneously-irrelevant distractors is not three bad
                            # distractors: it means the judge and the item disagree about
                            # what the question asks, which is a question/key problem. On
                            # kjsg ("Whom does Abishai kill...") the judge read the stem as
                            # "how", rejected all three names, and the rewriter replaced
                            # them with manner phrases that no longer answer "whom" --
                            # leaving the key the only name, and the only short option.
                            # Rewriting here makes the item worse every time. Stop.
                            rfail_all3 = True
                            break
                        if rfail:
                            notes.append(audit_feedback(ra))
                    if fal_chain is not None:
                        fa = audit_falseness(fal_chain, q, new, new["correct"], window)
                        ffail = falseness_failing_letters(fa)
                        if ffail:
                            notes.append(falseness_feedback(fa))
                    if not notes or rounds > retries:
                        break
                    try:
                        new = rd.rewrite_distractors(
                            client, a.model, new, q, window,
                            temperature=a.rewrite_temperature, effort=a.rewrite_effort,
                            feedback="\n".join(notes))
                        new["correct"] = base["correct"]
                    except Exception as exc:
                        print(f"[err ] {pid}/{it['id']}: audit regen failed: {exc}",
                              file=sys.stderr)
                        break
            if rfail_all3:
                print(f"[REVIEW] {pid}/{it['id']} the relevance gate rejected ALL THREE "
                      f"distractors. That is a question/key mismatch, not three bad "
                      f"distractors -- the item is left EXACTLY as it was. Fix the stem or "
                      f"the key by hand, then re-run.", file=sys.stderr)
                report.append({"pid": pid, "id": it["id"], "source": src,
                               "action": "skipped-for-review",
                               "review": "relevance gate rejected all 3 distractors",
                               "stem": mcq.get("mcq_stem") or q,
                               "key": LETTERS[ki], "options": opts,
                               "relevance_reasons": {L: ra[L].reason for L in rfail
                                                     if L in ra}})
                done += 1
                continue
            sh = rd.randomize_choices(new, f"{a.shuffle_seed}:{it['id']}")
            final = [sh[L] for L in LETTERS] + meta_opts
            # The gate audited the PRE-shuffle options, so its letters are not the letters
            # that ship. Remap by text before anything is reported: without this the warning
            # names an innocent option, and the first audit of gold72 did exactly that
            # ("A. They turned into snakes" when the supported option was "They disappeared").
            _ship = {}
            for _L in LETTERS:
                _ship.setdefault(sh[_L], _L)
            def _shipped(L):
                return _ship.get(new.get(L, ""), "?")
            ffail_pre, ffail = list(ffail), [_shipped(L) for L in ffail]
            ffail_text = [new.get(L, "") for L in ffail_pre]
            fa = {_shipped(L): v for L, v in fa.items()}
            rfail_pre, rfail = list(rfail), [_shipped(L) for L in rfail]
            rfail_text = [new.get(L, "") for L in rfail_pre]
            ra = {_shipped(L): v for L, v in ra.items()}
            if rfail_pre:
                print(f"[RELEV] {pid}/{it['id']} shipped option(s) {','.join(rfail)} are not "
                      f"possible ANSWERS -- free eliminations"
                      + ("" if src == "llm" else f" [{src}, not regenerated]")
                      + " -- " + "; ".join(f"{L} ({t!r}): {ra[L].reason}"
                                           for L, t in zip(rfail, rfail_text) if L in ra),
                      file=sys.stderr)
            if ffail_pre:
                detail = "; ".join(
                    f"{ship} ({txt!r}): {fa[ship].reason}"
                    for ship, txt in zip(ffail, ffail_text) if ship in fa)
                print(f"[FALSE] {pid}/{it['id']} shipped option(s) {','.join(ffail)} are "
                      f"SUPPORTED by the window -- two defensible answers"
                      + ("" if src == "llm" else f" [{src}, not regenerated]")
                      + (f" -- {detail}" if detail else ""), file=sys.stderr)
            mcq["mcq_options"] = final
            labels = LABELS[:len(final)]
            stem = mcq.get("mcq_stem") or q
            mcq["content"] = ("<question>" + stem + "\n\n"
                              + "\n".join(f"{L}. {final[i]}" for i, L in enumerate(labels))
                              + f"\n<question><answer>{sh['correct']}<answer>")
            # Re-stamp from the rebuilt list rather than asserting E/F: a 4-option input
            # gets no meta fields at all, and the letters follow the actual tail.
            for _txt, _field in ((ABSTAIN_EN, "abstention_option"), (NOTA_EN, "nota_option")):
                if _txt in final:
                    mcq[_field] = labels[final.index(_txt)]
            if meta_opts:
                mcq["meta_option_count"] = len(meta_opts)
            assert final[LABELS.index(sh["correct"])] not in META_EN, \
                f"{pid}/{it['id']}: a meta-option became the key"
            mcq["distractors_rewritten"] = True
            key_long = key_separable_by_length(sh, sh["correct"], a.length_tolerance)
            if key_long:
                print(f"[LENGTH] {pid}/{it['id']} the key is "
                      f"{rd.cjk_len(sh[sh['correct']])} units against distractors "
                      f"{sorted(rd.cjk_len(sh[L]) for L in LETTERS if L != sh['correct'])} "
                      f"-- separable by length alone, without reading the passage",
                      file=sys.stderr)
            row = {"pid": pid, "id": it["id"], "key": sh["correct"], "source": src,
                   "key_separable_by_length": key_long,
                   "key_len": rd.cjk_len(sh[sh["correct"]]),
                   "distractor_lens": sorted(rd.cjk_len(sh[L]) for L in LETTERS
                                             if L != sh["correct"]),
                   "n_meta_options": len(meta_opts),
                   "before": opts, "after": [sh[L] for L in LETTERS]}
            if fal_chain is not None:
                row["falseness"] = {
                    "audited": bool(fa), "rounds": rounds,
                    # letters as SHIPPED (index into row["after"]); the pre-shuffle letters
                    # the auditor used are kept only for tracing back to its raw verdicts.
                    "failed": ffail, "failed_text": ffail_text,
                    "failed_pre_shuffle": ffail_pre,
                    "counts": falseness_status_counts(fa) if fa else {},
                    "verdicts": {L: {"answer_status": v.answer_status, "reason": v.reason,
                                     "quote": v.quote} for L, v in fa.items()},
                }
            if rel_chain is not None:
                # "failed" = options a respondent can discard WITHOUT reading the passage.
                # This is the dead-distractor mechanism; the falseness gate cannot see it.
                row["relevance"] = {
                    "audited": bool(ra), "rounds": rounds,
                    "failed": rfail, "failed_text": rfail_text,
                    "failed_pre_shuffle": rfail_pre,
                    "n_effective_distractors": (3 - len(rfail)) if ra else None,
                    "verdicts": {L: {"is_possible_answer": v.is_possible_answer,
                                     "reason": v.reason} for L, v in ra.items()},
                }
            if a.verify and ans_client:
                try:
                    cb = ask_letter_en(ans_client, a.answer_model, q, sh, "", 0.0)
                    ob = ask_letter_en(ans_client, a.answer_model, q, sh, window, 0.0)
                    row["closed_book_correct"] = int(cb == sh["correct"])
                    row["open_book_correct"] = int(ob == sh["correct"])
                except Exception as exc:
                    print(f"[warn] verify failed {pid}/{it['id']}: {exc}", file=sys.stderr)
            report.append(row); done += 1
            print(f"[ok  ] {pid}/{it['id']} key={sh['correct']}"
                  + (f" closed={row.get('closed_book_correct')} open={row.get('open_book_correct')}"
                     if a.verify else ""))
        if not a.verify_only:
            json.dump(items, open(os.path.join(a.out_dir, fn), "w"), ensure_ascii=False, indent=2)

    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    json.dump(report, open(a.report, "w"), ensure_ascii=False, indent=2)
    cb = [r["closed_book_correct"] for r in report if "closed_book_correct" in r]
    ob = [r["open_book_correct"] for r in report if "open_book_correct" in r]
    print(f"\n{'measured' if a.verify_only else 'rewrote'} {done} items"
          + ("" if a.verify_only else f" -> {a.out_dir}"))
    if cb:
        print(f"  closed-book accuracy : {sum(cb)/len(cb):.3f}   (want near 0.25 -- distractors work)")
        print(f"  open-book accuracy   : {sum(ob)/len(ob):.3f}   (want high -- item still answerable)")
        print(f"  discrimination       : {sum(ob)/len(ob) - sum(cb)/len(cb):+.3f}")
    rv = [r for r in report if r.get("action") == "skipped-for-review"]
    if rv:
        print(f"  needs HUMAN review     : {len(rv)} item(s) left untouched "
              f"({', '.join(r['id'] for r in rv)}) -- the relevance gate rejected all three "
              f"distractors, which points at the stem or the key, not the options")
    kl = [r for r in report if r.get("key_separable_by_length")]
    if kl:
        print(f"  key separable by length: {len(kl)} item(s) "
              f"({', '.join(r['id'] for r in kl)}) -- the key can be picked without reading; "
              f"neither gate looks at the key, so fix these by hand")
    rl = [r for r in report if "relevance" in r]
    if rl:
        unaud = [r for r in rl if not r["relevance"]["audited"]]
        aud = [r for r in rl if r["relevance"]["audited"]]
        if not aud:
            print(f"  relevance gate       : NO VERDICTS -- all {len(rl)} item(s) failed to "
                  f"audit (auditor unreachable?). Nothing was measured.")
        else:
            bad = [r for r in aud if r["relevance"]["failed"]]
            eff = [r["relevance"]["n_effective_distractors"] for r in aud
                   if r["relevance"]["n_effective_distractors"] is not None]
            dead = sum(len(r["relevance"]["failed"]) for r in aud)
            print(f"  relevance gate       : {len(bad)}/{len(aud)} audited item(s) carry a "
                  f"distractor discardable WITHOUT reading the passage")
            print(f"    dead distractors   : {dead}/{3 * len(aud)} "
                  f"({dead / max(1, 3 * len(aud)):.1%})")
            if eff:
                print(f"    effective options  : {1 + sum(eff) / len(eff):.2f} of 4 "
                      f"(chance floor {1 / (1 + sum(eff) / len(eff)):.3f} vs 0.250 by design)")
        if unaud:
            print(f"    NOT AUDITED        : {len(unaud)} item(s) got no relevance verdict. "
                  f"An empty audit is 'no opinion', NOT a pass -- these are unmeasured.")
            print(f"    [warn] unaudited for relevance: "
                  f"{', '.join(r['id'] for r in unaud[:12])}", file=sys.stderr)
    fl = [r for r in report if "falseness" in r]
    if fl:
        bad_items = []          # stays empty when nothing could be audited
        unaud = [r for r in fl if not r["falseness"]["audited"]]
        aud = [r for r in fl if r["falseness"]["audited"]]
        if not aud:
            print(f"  falseness gate       : NO VERDICTS -- all {len(fl)} item(s) failed to "
                  f"audit (auditor unreachable?). Nothing was measured.")
        else:
            bad_items = [r for r in aud if r["falseness"]["failed"]]
            tot = {k: sum(r["falseness"]["counts"].get(k, 0) for r in aud)
                   for k in ("supported", "contradicted", "unsupported")}
            print(f"  falseness gate       : {len(bad_items)}/{len(aud)} audited item(s) "
                  f"still carry a distractor the window SUPPORTS")
            print(f"    distractor verdicts: supported {tot['supported']}, "
                  f"contradicted {tot['contradicted']}, unsupported {tot['unsupported']}")
        if unaud:
            print(f"    NOT AUDITED        : {len(unaud)} item(s) got no falseness verdict. "
                  f"An empty audit is 'no opinion', NOT a pass -- these are unmeasured.")
            print(f"    [warn] unaudited for falseness: "
                  f"{', '.join(r['id'] for r in unaud[:12])}", file=sys.stderr)
        if bad_items:
            print(f"    [warn] two defensible answers on: "
                  f"{', '.join(r['id'] for r in bad_items[:12])}"
                  + (" ..." if len(bad_items) > 12 else ""), file=sys.stderr)
            print("    open-book accuracy UNDERSTATES these items; it does not excuse them.",
                  file=sys.stderr)
    print(f"  report: {a.report}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
