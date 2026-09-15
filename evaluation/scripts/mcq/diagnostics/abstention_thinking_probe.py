#!/usr/bin/env python3
"""Does a thinking model ABSTAIN when its own reasoning says the answer is not there?

The question this answers is narrow and important. If the trace says "the passage does not
mention this" and the model then picks a content option anyway, the failure is in the
prompt or the output format, not in the model's reading -- and no amount of extra data
fixes it. If the trace is confidently wrong instead, that is a capability limit and the
remedy is different.

DESIGN -- a positive control, not a survey.

  full      the item's ordinary 3-verse window. The answer IS present; abstention should
            be rare, and any abstention here is a false alarm.
  redacted  the SAME window with the keyed verse removed. The answer is provably absent,
            so E ("根据这段文字无法判断") is the only defensible choice. Abstention should
            be near 1.0, and every failure is measurable.

Two conditions on the same items and the same model isolate the behaviour: nothing changes
except whether the answer-bearing verse is in the context.

Reuses the already-translated, already-pinned Chinese 5-option QA from a previous run, so
this costs NOTHING in API spend -- the only work is local Ollama inference. It calls
Ollama directly with think=true and keeps the trace, which the normal pipeline discards
(clean_raw_answer strips the <think> block, and only thinking_chars survives; set
MCQ_KEEP_THINKING=1 to retain it in a full campaign).

  python3 .../abstention_thinking_probe.py --limit 20          # ~9 min, a first look
  python3 .../abstention_thinking_probe.py                     # all items, ~30 min
  python3 .../abstention_thinking_probe.py --self-test
"""
from __future__ import annotations

import argparse, json, math, os, random, re, sys, time, urllib.error, urllib.request
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "evaluation" / "agents"))

DEFAULT_RUN = "evaluation/outputs/tier1_bsb_unblinded_5opt"
DEFAULT_WINDOWS = "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"

# Heuristic cues that the reasoning has concluded the passage does not answer the question.
# qwen3 thinks in either language, so both are needed. This is a screen, not a verdict --
# every flagged trace is written out for reading.
# Pinned meta-option strings, identical to pin_meta_options.py's PINNED table. The
# translated QA in a completed run carries only E, because no 6-option set has ever been
# translated. F is a FIXED string, so it can be appended here deterministically -- no LLM,
# no cost -- which is exactly what pin_meta_options.py --add-missing exists for.
CONTENT_LETTERS = "ABCD"   # the content options; meta-options are appended after them


def CJK(ch: str) -> bool:
    """True for a CJK ideograph. Used to reject punctuation and Latin text from the
    spans this script locates and replaces."""
    return "\u4e00" <= ch <= "\u9fff"


# The meta-option LABELS, keyed by ROLE rather than by letter, so the two roles can be
# assigned to either letter (--abstain F --nota E puts the none-of-the-above option first).
#
# "current" is what every run so far has shown. Its trouble is that the abstain label is a
# claim about the READER -- 根据这段文字无法判断, "cannot be determined from this passage" --
# and in the corrupted condition that sentence is TRUE: the passage says 王坐在宝座上, no
# option says that, so the model really cannot determine which option is right, says so, and
# takes the abstain option. The instruction 200 tokens earlier says abstain means the passage
# is silent, but the label sitting inline beside A-D says otherwise, and the label wins.
# 20 of the 21 abstentions in the corrupted arm were read individually: in every one the
# passage did state an answer, so the abstain condition was false and the label was not.
#
# "explicit" moves both labels onto the passage, which is where the divide actually lies:
# abstain = the passage does not mention the answer; nota = the passage gives one, but not
# among the options. Both are appended at run time from this table, so switching label sets
# costs nothing -- no retranslation, no dataset regeneration.
META_LABELS = {
    "current": {"abstain": "根据这段文字无法判断",
                "nota": "以上都不是"},
    "explicit": {"abstain": "这段经文没有提到答案",
                 "nota": "经文给出了答案，但不在以上选项中"},
    # The configuration adopted on 2026-09-14: ONE hatch, asserting only that no
    # content option is supported. Run it with --nota "" and --labels ABCDE; the
    # "nota" text here is what a 6-option run would show and exists only so the
    # table stays well-formed.
    "unified": {"abstain": "经文不支持以上任何一个选项",
                "nota": "经文给出了答案，但不在以上选项中"},
}
KNOWN_META_TEXTS = {t for pair in META_LABELS.values() for t in pair.values()}

# Letter-keyed view of the default set, for pin_meta_options.py and the on-disk 5-option QA.
PINNED = {"E": META_LABELS["current"]["abstain"],
          "F": META_LABELS["current"]["nota"]}

ABSENCE_CUES_ZH = ("没有提到", "未提及", "没有提及", "文中没有", "没有说明", "没有提供",
                   "无法判断", "没有明确", "不清楚", "没有直接", "并未提到", "看不出")
ABSENCE_CUES_EN = ("not mentioned", "does not mention", "doesn't mention", "not stated",
                   "does not say", "doesn't say", "not in the passage", "no information",
                   "cannot tell", "can't tell", "not specified", "isn't mentioned",
                   "does not provide", "no mention")


def trace_signals_absence(trace: str) -> bool:
    t = (trace or "").lower()
    return (any(c in trace for c in ABSENCE_CUES_ZH)
            or any(c in t for c in ABSENCE_CUES_EN))


def content_id_of(item: dict) -> str:
    """'<pid>:<item>' for an answered cell's QA.

    The per-cell qa_target.json carries no content_id -- the identifier survives only in
    passage_id / id, wrapped as 'uw-<pid>:<item>-mcq'. The verse-window file is indexed by
    the bare content_id, so it has to be unwrapped or every window lookup misses and the
    probe silently finds zero items.
    """
    raw = str(item.get("content_id") or item.get("passage_id") or item.get("id") or "")
    raw = raw.strip()
    if raw.startswith("uw-"):
        raw = raw[3:]
    for suffix in ("-mcq", "-open"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
    return raw.split("#")[0]


def verse_number(ref: str) -> str:
    """'26:11' -> '11'; a bare '11' stays '11'. Windows store either shape."""
    return str(ref).strip().split(":")[-1]


def redact(window_text: str, keyed_ref: str) -> str:
    """Drop the keyed verse from a rendered window, keeping the other verses verbatim.

    The window is rendered one verse per line, each starting with its number. Removing
    that line makes the answer provably absent while every other word of context stays --
    so the only thing that differs between conditions is the answer itself.
    """
    want = verse_number(keyed_ref)
    kept = [ln for ln in window_text.splitlines()
            if not re.match(rf"^\s*{re.escape(want)}\s", ln)]
    return "\n".join(kept).strip()


def ollama_chat(prompt: str, model: str, base_url: str, think: bool, timeout: int = 300):
    payload = {"model": model, "stream": False,
               "messages": [{"role": "user", "content": prompt}],
               "options": {"temperature": 0.0}}
    # ALWAYS send the switch, in both directions. Omitting it when think=False does not
    # disable reasoning -- qwen3:1.7b ignores the advisory "/no_think" prompt token and
    # keeps thinking, which generate_chinese_answers.py documents from a 2026-08-06 probe.
    # The first overnight run proved it again: the "thinking OFF" arm returned a reasoning
    # trace on 138 of 138 answers (median 426 chars), so both arms were the same condition
    # and the contrast measured nothing.
    payload["think"] = bool(think)
    req = urllib.request.Request(f"{base_url.rstrip('/')}/api/chat",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Ollama builds predating the `think` field reject it; same fallback the pipeline
        # uses. Retrying without it can only mean "thinking left at default".
        if exc.code not in (400, 404, 422):
            raise
        payload.pop("think", None)
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/chat",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    msg = data.get("message") or {}
    content = msg.get("content") or ""
    thinking = msg.get("thinking") or ""
    if not thinking:
        m = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
        if m:
            thinking = m.group(1)
            content = content[:m.start()] + content[m.end():]
    return content.strip(), thinking.strip(), data


def parse_letter(text: str, labels: str) -> str | None:
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    try:
        obj = json.loads(re.search(r"\{.*\}", t, re.DOTALL).group(0))
        v = str(obj.get("selected_choice") or "").strip().upper()
        if v[:1] in labels:
            return v[:1]
    except Exception:
        pass
    m = re.search(rf"\b([{labels}])\b", t.upper())
    return m.group(1) if m else None


def parse_verses(text: str, stem: str) -> dict:
    """(chapter, verse) -> verse text, for a translated passage file.

    The first block is numbered with the CHAPTER, not with verse 1: 1 Kings 13:1 renders as
    "13 <text>" and the following verses as 2, 3, 4... Reading that first number as a verse
    silently produced an empty verse 1 and a window with a blank line in it. Numbering
    restarts at 1 when the count jumps backwards, which is how the passages that span a
    chapter boundary are handled. Same rule as rewrite_distractors_gold72_en.parse_passage,
    applied to the Chinese text instead of the English source.
    """
    m = re.match(r"^[0-9]?[a-z]+_(\d+)_(\d+)-(?:(\d+)_)?(\d+)$", stem)
    if not m:
        return {}
    c0, v0 = int(m.group(1)), int(m.group(2))
    c1 = int(m.group(3)) if m.group(3) else c0
    # Two things have to be told apart, and each one broke the other when handled alone:
    #
    #   chapter markers  the corpus prints the CHAPTER NUMBER in place of verse 1, which is
    #                    why the first block of 1 Kings 13 reads "13". t1_judg17_18 does it
    #                    again at the 17->18 boundary.
    #   gaps             a dosed passage really is missing verses -- omission at 30% deletes
    #                    10 of t1_1kgs13's 34 -- so a jump is not a new chapter.
    #
    # Reading a jump as a chapter change renumbered everything after the first deletion;
    # reading every jump as a literal verse turned Judges 18 into "chapter 2". The stem
    # names the chapters the passage actually spans, so the marker is identifiable and
    # everything else is literal.
    idx, cur_ch, prev, cur_key = {}, c0, None, None
    for line in text.splitlines():
        mm = re.match(r"^\s*(\d+)\s+(.*)$", line)
        if mm:
            n = int(mm.group(1))
            if prev is None:
                v = v0                                  # first block: the chapter marker
            elif cur_ch == c0 and c1 != c0 and n == c1:
                cur_ch, v = c1, 1                       # marker for the next chapter
            elif n > prev:
                v = n                                   # literal verse; gaps are real
            else:
                cur_ch, v = cur_ch + 1, 1               # numbering went backwards
            cur_key = (cur_ch, v)
            idx[cur_key] = mm.group(2).strip()
            prev = v
        elif cur_key and line.strip():
            idx[cur_key] = (idx[cur_key] + " " + line.strip()).strip()
    return idx


def parse_ref_span(ref: str, default_chapter: int):
    """'26:11' -> [(26,11)];  '26:4-5' -> [(26,4),(26,5)];  '' -> [].

    A third of gold72's keys are verse RANGES -- the answer spans two verses. Redacting only
    the first would leave the answer in the window and turn the unanswerable condition into
    a merely harder answerable one, which is the exact opposite of what this control needs.
    """
    ref = str(ref or "").strip()
    if not ref:
        return []
    ch, _, rest = ref.rpartition(":")
    try:
        chapter = int(ch) if ch else default_chapter
    except ValueError:
        return []
    lo, _, hi = rest.partition("-")
    try:
        a = int(lo)
        b = int(hi) if hi else a
    except ValueError:
        return []
    if b < a or b - a > 10:
        return []
    return [(chapter, v) for v in range(a, b + 1)]


def load_items(run_root, windows_path, limit=0, passage_map=None):
    from evaluation.scripts.mcq.preparation.rewrite_distractors_gold72_en import PASSAGE_FILE
    passage_map = passage_map or PASSAGE_FILE
    W = json.load(open(windows_path, encoding="utf-8"))
    wins = {str(w.get("content_id") or "").strip(): w for w in W["windows"]}
    out, skipped = [], Counter()
    root = Path(run_root)
    for pdir in sorted(root.glob("t1_*")):
        stem = passage_map.get(pdir.name)
        if not stem:
            skipped["no passage stem"] += 1
            continue
        cells = sorted(pdir.glob("*/omission/0%/qa_target.json"))
        if not cells:
            skipped["no answered cell"] += 1
            continue
        qa_path = cells[0]
        passage = qa_path.parent / "passage_target.txt"
        if not passage.exists():
            skipped["no passage_target.txt"] += 1
            continue
        verses = parse_verses(passage.read_text(encoding="utf-8"), stem)
        base_ch = int(re.match(r"^[0-9]?[a-z]+_(\d+)_", stem).group(1))
        for it in json.load(open(qa_path, encoding="utf-8")):
            if it.get("q_type") != "mcq" or not isinstance(it.get("A"), dict):
                continue
            cid = content_id_of(it)
            w = wins.get(cid) or wins.get(cid.split("#")[0])
            if not w:
                skipped["no window"] += 1
                continue
            keyed = parse_ref_span(it.get("reference"), base_ch)
            refs = [r for v in w["window"] for r in parse_ref_span(v, base_ch)]
            if not keyed or not refs:
                skipped["unparseable reference or window"] += 1
                continue
            if not set(keyed) <= set(refs):
                skipped["keyed verse(s) outside their own window"] += 1
                continue
            if len(refs) - len(set(keyed) & set(refs)) < 1:
                skipped["redaction would empty the window"] += 1
                continue
            # Every verse must render non-empty, or the FULL condition is already missing
            # text and the comparison measures the wrong thing.
            if any(not verses.get(r) for r in refs):
                skipped["a window verse is missing from the passage"] += 1
                continue
            full = "\n".join(f"{v} {verses[(c, v)]}" for c, v in refs)
            red = "\n".join(f"{v} {verses[(c, v)]}" for c, v in refs
                            if (c, v) not in set(keyed))
            if len(red.splitlines()) != len(full.splitlines()) - len(set(keyed) & set(refs)):
                skipped["redaction removed the wrong number of verses"] += 1
                continue
            out.append({"cid": cid, "pid": pdir.name, "ref": it.get("reference"),
                        "Q": it.get("Q"), "choices": it["A"], "correct": it.get("correct"),
                        "keyed_verses": len(set(keyed) & set(refs)),
                        "window_verses": len(refs),
                        "windows": {"full": full, "redacted": red}})
            if limit and len(out) >= limit:
                return out, skipped
    return out, skipped


def load_dose_items(run_root, windows_path, doses, limit=0, defect="omission",
                    passage_map=None):
    """The SAME items read under real defect variants instead of surgical redaction.

    Redaction answers "will it say 'I can't tell' when the answer is provably gone".
    This answers the deployment question: does abstention track DOSE on text that was
    degraded the way a real bad translation is degraded. Omission at 30% both truncates
    verses and deletes some outright, so a window can lose part or all of its evidence --
    which is exactly the gradient the experiment is built on.

    Costs nothing: the dosed Chinese passages and the translated QA already exist in the
    completed run, so this is local inference only.
    """
    from evaluation.scripts.mcq.preparation.rewrite_distractors_gold72_en import PASSAGE_FILE
    passage_map = passage_map or PASSAGE_FILE
    W = json.load(open(windows_path, encoding="utf-8"))
    wins = {str(w.get("content_id") or "").strip(): w for w in W["windows"]}
    out, skipped = [], Counter()
    root = Path(run_root)
    for pdir in sorted(root.glob("t1_*")):
        stem = passage_map.get(pdir.name)
        # Two layouts exist in a run root. The answering pipeline writes a cell PER MODEL,
        # <pid>/<model>/<defect>/<dose>/, and that is what every earlier arm read. The
        # variant builder writes the shared, model-independent cell one level up,
        # <pid>/<defect>/<dose>/ -- which is all that exists for a defect family that was
        # built but never answered. Globbing only the model level silently skipped the
        # whole mistranslation arm: 10 passages, "no baseline cell", and the run carried on.
        # The QA is identical either way (variant scripts perturb the Chinese and copy the
        # QA across unchanged), and model_dir below derives correctly from both shapes.
        cells = sorted(pdir.glob(f"*/{defect}/{doses[0]}/qa_target.json"))
        if not cells:
            cells = sorted(pdir.glob(f"{defect}/{doses[0]}/qa_target.json"))
        if not stem or not cells:
            skipped["no baseline cell"] += 1
            continue
        model_dir = cells[0].parent.parent.parent
        texts = {}
        for d in doses:
            p = model_dir / defect / d / "passage_target.txt"
            if not p.exists():
                break
            texts[d] = parse_verses(p.read_text(encoding="utf-8"), stem)
        if len(texts) != len(doses):
            skipped["a dose cell is missing"] += 1
            continue
        base_ch = int(re.match(r"^[0-9]?[a-z]+_(\d+)_", stem).group(1))
        for it in json.load(open(cells[0], encoding="utf-8")):
            if it.get("q_type") != "mcq" or not isinstance(it.get("A"), dict):
                continue
            cid = content_id_of(it)
            w = wins.get(cid) or wins.get(cid.split("#")[0])
            if not w:
                skipped["no window"] += 1
                continue
            refs = [r for v in w["window"] for r in parse_ref_span(v, base_ch)]
            if not refs or any(not texts[doses[0]].get(r) for r in refs):
                skipped["baseline window incomplete"] += 1
                continue
            wnd, present = {}, {}
            for d in doses:
                kept = [(c, v) for c, v in refs if texts[d].get((c, v))]
                wnd[f"dose_{d}"] = "\n".join(f"{v} {texts[d][(c, v)]}" for c, v in kept)
                present[f"dose_{d}"] = len(kept)
            out.append({"cid": cid, "pid": pdir.name, "ref": it.get("reference"),
                        "Q": it.get("Q"), "choices": it["A"], "correct": it.get("correct"),
                        "window_verses": len(refs), "verses_present": present,
                        "windows": wnd})
            if limit and len(out) >= limit:
                return out, skipped
    return out, skipped


def stratified_sample(items, n, seed=0):
    """Take n items SPREAD ACROSS PASSAGES rather than the first n.

    --limit truncates inside the loader, so it returns the first N items in sort order --
    and those all come from one passage. The 2026-09-14 rehearsal used --limit 8, drew all
    eight from t1_1kgs13, and appeared to show abstention collapsing 81.2% -> 12.5%. It had
    not: on those same eight items the baseline itself scored 2/8. A screening run whose
    numbers are meant to be read at all has to sample, not truncate.

    Round-robin over passages, shuffled within each, deterministic given a seed -- so every
    cell of a factorial design answers the SAME items and the contrasts stay paired.
    """
    if not n or n >= len(items):
        return items
    by = {}
    for it in items:
        by.setdefault(it["pid"], []).append(it)
    rng = random.Random(seed)
    for group in by.values():
        rng.shuffle(group)
    order = sorted(by)
    out = []
    while len(out) < n:
        progressed = False
        for pid in order:
            if by[pid]:
                out.append(by[pid].pop())
                progressed = True
                if len(out) >= n:
                    break
        if not progressed:
            break
    return sorted(out, key=lambda it: it["cid"])


def add_meta_options(choices: dict, labels: str, abstain: str, nota: str,
                    label_set: str = "current") -> dict:
    """Ensure every requested meta-option is present, pinned to its fixed Chinese string.

    Text is chosen by ROLE, so --abstain F --nota E swaps which letter carries which
    meaning and therefore which one elimination reasoning reaches first.

    Asserts rather than guesses: a meta-option must never collide with a content option,
    or the item would have two ways to be right. A letter already holding a meta string
    from ANY label set is overwritten -- that is a relabelling, not a collision -- but a
    letter holding real content is refused.
    """
    texts = META_LABELS[label_set]
    out = dict(choices)
    for lab, role in ((abstain, "abstain"), (nota, "nota")):
        if lab and lab in labels:
            text = texts[role]
            if (lab in out and out[lab].strip() != text
                    and out[lab].strip() not in KNOWN_META_TEXTS):
                raise ValueError(f"{lab} already holds {out[lab]!r}, not a meta-option")
            out[lab] = text
    content = [L for L in labels if L not in (abstain, nota)]
    texts = [out[L] for L in content if L in out]
    for lab in (abstain, nota):
        if lab and lab in out and out[lab] in texts:
            raise ValueError(f"meta-option {lab} duplicates a content option")
    return out


# The deployed pipeline's raw Ollama prompt pushes TOWARD the content options before it
# ever mentions the escape hatch: "For multiple choice, choose the option best supported by
# explicit passage evidence." The first version of this probe had no equivalent and went
# straight from "choose a letter" to the two meta-options -- and it drew 15% E where the
# pipeline drew 0% from the same model on the same items, plus 25% F without thinking.
# Same sentence, same position (before the letter instruction), in Chinese.
EVIDENCE_NUDGE = "请选择经文中有明确证据支持的选项。"

# --- how the two meta-options are explained -----------------------------------------
# "current" is the wording inherited from _meta_hint(). Its E clause is
# 没有提供足够的信息来回答 -- "does not provide enough information TO ANSWER" -- which reads
# naturally as "enough information to pick one of these options", and that is true whenever
# the answer is absent from the option set. So E's stated condition already covers F's case,
# and E is listed first. The traces show exactly this: on t1_1kgs13:mjwk the model reasoned
# "the answer is the Judah elder... 选项中没有这个选项" -- there is no such option -- and then
# chose E. On kcyl it said twice "或许 F 是正确的，因为没有选项符合经文" and still chose E.
#
# "disjoint" makes E a claim about the PASSAGE rather than about answering, and states the
# exclusivity outright, so neither clause can absorb the other.
META_WORDING = {
    "current": {
        "abstain": "如果这段经文没有提供足够的信息来回答，选 {E}。",
        "nota": "如果这段经文确实回答了这个问题，但答案不是 {content}，选 {F}。",
        "note": "",
    },
    "disjoint": {
        "abstain": "如果这段经文完全没有提到这个问题的答案，选 {E}。",
        "nota": "如果这段经文给出了答案，但这个答案不在 {content} 之中，选 {F}。",
        "note": "这两个选项互不重叠：{E} 表示经文没有说，{F} 表示经文说了但选项里没有。",
    },
    # "disjoint" states the divide but still leaves it as one six-way choice, and the traces
    # show the model stating the nota condition aloud -- 经文没有提到这些选项中的任何内容 --
    # and then taking the abstain option anyway. "sequential" makes the divide an ORDER OF
    # OPERATIONS instead of a description: one binary question about the passage, then a
    # second about the option set. The closing sentence is the one that does the work --
    # it makes abstaining conditional on the passage being silent, not on the reader being
    # unsure.
    # With one hatch there is no divide to explain: the instruction is the evidence
    # rule and its own negation, nothing to arbitrate between.
    "unified": {
        "abstain": "如果经文不支持 {content} 中的任何一个，选 {E}。",
        "nota": "",
        "note": "",
    },
    "sequential": {
        "abstain": "请按顺序判断。第一步：这段经文有没有回答这个问题？如果经文根本没有提到答案，选 {E}。",
        "nota": "第二步：如果经文回答了这个问题，再看这个答案是不是 {content} 中的一个；如果都不是，选 {F}。",
        "note": "只要经文说出了答案，就不能选 {E}，即使这个答案不在选项里——那种情况选 {F}。",
    },
}


def load_swap_items(run_root, windows_path, limit=0, defect="omission", dose="0%",
                   passage_map=None, nota_label="F"):
    """A positive control for F, the mirror image of redaction's control for E.

    Redaction makes E correct by removing the answer from the PASSAGE. F needs the opposite
    situation: the passage still answers the question, but the answer is not among A-D. That
    state cannot arise under omission -- omission deletes evidence, which is E's case -- and
    it never arises in the item bank either, because every item is built with its key among
    the options. So F was wrong by construction in every condition measured so far, which is
    why its only observed use was as a dumping ground when reasoning was off.

    Here it is made correct by construction, without touching the passage: the KEY's text is
    replaced by a distractor borrowed from another item of the same passage. The passage
    still says what it said; none of A-D now states it; E is wrong because the passage does
    answer; F is the only defensible choice.

    Borrowing from a sibling item rather than inventing text keeps the replacement in the
    same register and vocabulary, so the swapped option cannot be spotted as alien.
    """
    items, skipped = load_items(run_root, windows_path, 0, passage_map)
    by_passage = {}
    for it in items:
        by_passage.setdefault(it["pid"], []).append(it)
    out = []
    rng = random.Random("fswap")
    for pid, group in sorted(by_passage.items()):
        for it in group:
            key = it["correct"]
            if key not in CONTENT_LETTERS:
                skipped["no key letter"] += 1
                continue
            here = {v.strip() for v in it["choices"].values() if v}
            pool = [v.strip() for other in group if other is not it
                    for L, v in other["choices"].items()
                    if L in CONTENT_LETTERS and L != other["correct"] and v and v.strip() not in here]
            # de-duplicate while keeping order, then pick deterministically
            seen, cand = set(), []
            for v in pool:
                if v not in seen:
                    seen.add(v); cand.append(v)
            if not cand:
                skipped["no borrowable distractor in this passage"] += 1
                continue
            # Prefer a borrow of similar LENGTH to the text it replaces. Length is a crude
            # proxy for type in Chinese, but a good one here: a 2-character noun swapped in
            # for a 6-character manner phrase is visibly the wrong KIND of answer, and the
            # model may then choose E because the option set looks broken rather than
            # because the answer is genuinely missing from it. Ties broken deterministically.
            tgt = len(it["choices"][key])
            cand.sort(key=lambda v: (abs(len(v) - tgt), v))
            near = [v for v in cand if abs(len(v) - tgt) <= max(2, tgt // 3)] or cand[:3]
            borrowed = near[rng.randrange(len(near))]
            swapped = dict(it["choices"])
            swapped[key] = borrowed          # the key LETTER stays put; only its text changes
            assert borrowed not in {v for L, v in it["choices"].items() if L != key}, it["cid"]
            out.append({**it,
                        "windows": {"key_in": it["windows"]["full"],
                                    "key_out": it["windows"]["full"]},
                        "choices_by_cond": {"key_in": dict(it["choices"]),
                                            "key_out": swapped},
                        "expected": {"key_in": key, "key_out": nota_label},
                        "borrowed_text": borrowed, "replaced_text": it["choices"][key]})
            if limit and len(out) >= limit:
                return out, skipped
    return out, skipped


def load_corrupt_items(run_root, windows_path, corrupted_file, limit=0, passage_map=None,
                       nota_label="F"):
    """Items paired with an LLM-rewritten window that asserts a DIFFERENT fact -- F correct.

    The rewriting is NOT done here. build_corrupted_windows.py generates and verifies the
    corrupted windows once, paying the API cost, and writes them to disk; this reads that
    file so the measurement stays local, free and repeatable.

    An earlier version spliced the replacement in by string substitution. It produced word
    salad -- 王的手 became 为我的国祷告, "pray for my kingdom then recovered" -- and broken
    syntax reads as DAMAGE, which invites E. F needs fluent-but-wrong, which needs a model.

    Only verified corruptions appear in the file: each was checked to still answer the
    question, to support none of A-D, and to read as natural Chinese.
    """
    items, skipped = load_items(run_root, windows_path, 0, passage_map)
    if not os.path.exists(corrupted_file):
        raise SystemExit(
            f"no corrupted windows at {corrupted_file}. Generate them first:\n"
            f"  python3 evaluation/scripts/mcq/preparation/build_corrupted_windows.py")
    C = json.load(open(corrupted_file, encoding="utf-8"))
    out = []
    for it in items:
        c = C.get(it["cid"])
        if not c:
            skipped["no verified corruption for this item"] += 1
            continue
        if c.get("key_letter") and c["key_letter"] != it["correct"]:
            skipped["corruption was generated for a different key"] += 1
            continue
        out.append({**it,
                    "windows": {"intact": it["windows"]["full"],
                                "corrupted": c["corrupted"]},
                    "expected": {"intact": it["correct"], "corrupted": nota_label},
                    "answer_span": c.get("span_before"),
                    "replacement": c.get("span_after"),
                    "new_answer": c.get("new_answer")})
        if limit and len(out) >= limit:
            break
    return out, skipped


def build_prompt(item, window, labels, abstain_label, nota_label="", evidence_nudge=True,
                 meta_wording="current"):
    body = "\n".join(f"{L}. {item['choices'][L]}" for L in labels if L in item["choices"])
    content = [L for L in labels if L not in (abstain_label, nota_label)]
    # The two meta-options make DIFFERENT claims and the instruction has to say so, or the
    # model treats them as ordinary distractors. Wording mirrors _meta_hint() in
    # generate_chinese_answers.py: E is a claim about the PASSAGE, F about the OPTION SET.
    w = META_WORDING[meta_wording]
    joined = "、".join(content[:-1]) + " 或 " + content[-1]
    fmt = {"E": abstain_label, "F": nota_label, "content": joined}
    hint = ""
    if abstain_label:
        hint += w["abstain"].format(**fmt)
    if nota_label:
        hint += w["nota"].format(**fmt)
    if abstain_label and nota_label and w["note"]:
        hint += w["note"].format(**fmt)
    lead = (EVIDENCE_NUDGE + "\n") if evidence_nudge else ""
    return (
        "只根据下面这段经文回答问题。不要依赖你已有的圣经知识；"
        "这段经文是唯一的依据。\n\n"
        f"经文：\n{window}\n\n"
        f"问题：{item['Q']}\n"
        f"选项：\n{body}\n\n"
        f"{lead}"
        f"必须从 {', '.join(labels[:-1])} 或 {labels[-1]} 中选择一个字母。{hint}\n"
        '只输出 JSON：{"selected_choice":"X"}'
    )


def run(args):
    if args.mode == "corrupt":
        items, skipped = load_corrupt_items(args.run_root, args.windows,
                                            args.corrupted_windows, args.limit,
                                            nota_label=args.nota or args.abstain or "F")
    elif args.mode == "swap":
        items, skipped = load_swap_items(args.run_root, args.windows, args.limit,
                                         args.defect, args.doses[0],
                                         nota_label=args.nota or args.abstain or "F")
    elif args.mode == "dose":
        items, skipped = load_dose_items(args.run_root, args.windows, args.doses,
                                         args.limit, args.defect)
    else:
        items, skipped = load_items(args.run_root, args.windows, args.limit)
    for reason, n in sorted(skipped.items()):
        print(f"  [skip] {n} item(s)/passage(s): {reason}", file=sys.stderr)
    if not items:
        print(f"no usable items under {args.run_root}", file=sys.stderr)
        return 1
    if args.sample:
        before = len(items)
        items = stratified_sample(items, args.sample, args.sample_seed)
        pids = len({it["pid"] for it in items})
        print(f"stratified sample: {len(items)} of {before} item(s) across {pids} passage(s)"
              f" (seed {args.sample_seed})")
    labels = args.labels
    ab = args.abstain
    print(f"{len(items)} item(s); model={args.model} think={not args.no_think}; "
          f"options={labels} abstain={ab}"
          + (f" nota={args.nota}" if args.nota else " nota=off")
          + f"; {sum(len(i['windows']) for i in items)} calls\n")
    for it in items:
        if it.get("choices_by_cond"):
            it["choices_by_cond"] = {
                c: add_meta_options(v, labels, ab, args.nota, args.meta_labels)
                for c, v in it["choices_by_cond"].items()}
            it["choices"] = it["choices_by_cond"][sorted(it["choices_by_cond"])[0]]
        else:
            it["choices"] = add_meta_options(it["choices"], labels, ab, args.nota,
                                             args.meta_labels)

    # Resume. Results used to be written only after the whole arm finished, so the run that
    # was killed at 01:57 lost 100% of its work and left no way to tell how far it had got.
    # Partial results are now flushed as they arrive and reloaded on restart.
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, done_keys = [], set()
    if args.resume and out.exists():
        try:
            rows = json.load(open(out, encoding="utf-8"))
            done_keys = {(r["cid"], r["condition"]) for r in rows}
            print(f"resuming: {len(rows)} result(s) already recorded, skipping those")
        except Exception as exc:
            print(f"  [warn] could not read {out} to resume ({exc}); starting fresh",
                  file=sys.stderr)
            rows, done_keys = [], set()

    def flush():
        tmp = out.with_suffix(out.suffix + ".tmp")
        json.dump(rows, open(tmp, "w"), ensure_ascii=False, indent=1)
        os.replace(tmp, out)        # atomic: a kill mid-write cannot truncate the results

    t0, since_flush = time.time(), 0
    for i, it in enumerate(items, 1):
        for cond in it["windows"]:
            if (it["cid"], cond) in done_keys:
                continue
            try:
                content, trace, raw = ollama_chat(
                    build_prompt({**it, "choices": (it.get("choices_by_cond") or {}).get(
                        cond, it["choices"])}, it["windows"][cond], labels, ab, args.nota,
                        evidence_nudge=args.evidence_nudge,
                        meta_wording=args.meta_wording),
                    args.model, args.base_url, not args.no_think)
            except Exception as exc:
                print(f"  [err] {it['cid']}/{cond}: {exc}", file=sys.stderr)
                continue
            since_flush += 1
            letter = parse_letter(content, labels)
            rows.append({
                "cid": it["cid"], "pid": it["pid"], "ref": it["ref"], "condition": cond,
                "question": it["Q"], "key": it["correct"], "choice": letter,
                "abstained": letter == ab,
                "nota": bool(args.nota) and letter == args.nota,
                "evidence_nudge": bool(args.evidence_nudge),
                "meta_wording": args.meta_wording,
                "meta_labels": args.meta_labels,
                "abstain_letter": ab, "nota_letter": args.nota or None,
                # Which defect family the dose conditions came from. "dose_30%" alone does
                # not say 30% OF WHAT, and omission and mistranslation damage a passage in
                # opposite ways -- one removes the answer, the other replaces it.
                "defect": (args.defect if args.mode == "dose" else None),
                "expected": (it.get("expected") or {}).get(cond),
                "borrowed_text": it.get("borrowed_text"),
                "replaced_text": it.get("replaced_text"),
                "answer_span": it.get("answer_span"),
                "replacement": it.get("replacement"),
                "verses_present": (it.get("verses_present") or {}).get(cond),
                "window_verses": it.get("window_verses"),
                "trace_says_absent": trace_signals_absence(trace),
                "thinking_chars": len(trace), "thinking": trace, "raw": content,
            })
        if since_flush >= args.checkpoint_every:
            flush()
            since_flush = 0
        if i % 5 == 0 or i == len(items):
            el = time.time() - t0
            made = max(1, len(rows) - len(done_keys))
            left = sum(len(x["windows"]) for x in items[i:])
            # A HEARTBEAT, not just progress: without a timestamped line there is no way to
            # tell a hung run from a slow one, which is what cost 7 hours.
            print(f"  [{time.strftime('%H:%M:%S')}] {i}/{len(items)} items, "
                  f"{made} call(s) this session, {el/made:.1f}s/call, "
                  f"~{left*el/made/60:.0f} min left", flush=True)
    flush()
    report(rows, ab)
    print(f"\nfull traces: {out}")
    return 0


def report(rows, ab):
    print("\n" + "=" * 72)
    for cond in sorted({x["condition"] for x in rows}):
        r = [x for x in rows if x["condition"] == cond]
        if not r:
            continue
        n = len(r)
        absd = sum(x["abstained"] for x in r)
        notad = sum(x.get("nota") for x in r)
        says = sum(x["trace_says_absent"] for x in r)
        print(f"\n{cond.upper():9} n={n}")
        print(f"  chose E (abstained)          {absd:4d}  {absd/n:6.1%}")
        print(f"  chose F (none of the above)  {notad:4d}  {notad/n:6.1%}"
              + ("   <-- F is never correct here; these are false alarms"
                 if notad else ""))
        print(f"  any meta-option              {absd+notad:4d}  {(absd+notad)/n:6.1%}")
        print(f"  trace says 'not in passage'  {says:4d}  {says/n:6.1%}")
        both = sum(x["abstained"] and x["trace_says_absent"] for x in r)
        said_not_chose = sum(x["trace_says_absent"] and not x["abstained"] for x in r)
        chose_not_said = sum(x["abstained"] and not x["trace_says_absent"] for x in r)
        print(f"  trace says absent AND chose E      {both:4d}")
        print(f"  trace says absent BUT chose content{said_not_chose:4d}"
              + ("   <-- knows but will not say it" if said_not_chose else ""))
        print(f"  chose E with no such trace          {chose_not_said:4d}")
        if says:
            print(f"  P(chose E | trace says absent) = {both/says:.1%}")
    hardest = "redacted" if any(x["condition"] == "redacted" for x in rows) else max(
        {x["condition"] for x in rows}, default="")
    red = [x for x in rows if x["condition"] == hardest]
    leak = [x for x in red if not x["abstained"] and not x["trace_says_absent"]]
    if red:
        took = sum(x["abstained"] for x in red)
        if hardest == "redacted":
            print(f"\nIn REDACTED the answer is provably absent, so E is the only "
                  f"defensible choice.\n  {took}/{len(red)} took it.")
            if leak:
                print(f"  {len(leak)} answered confidently from a window that does not "
                      f"contain the answer -- check those for memorised scripture rather "
                      f"than reading.")
        else:
            # Under a real dose the evidence degrades by degrees: some windows keep the
            # answer, some lose part of it, some lose it entirely. So a content answer is
            # not automatically wrong here and must not be reported as if it were.
            lost = [x for x in red if x.get("verses_present") is not None
                    and x.get("window_verses") and x["verses_present"] < x["window_verses"]]
            gone = [x for x in lost if x["verses_present"] == 0]
            print(f"\nIn {hardest.upper()} the window is degraded, not emptied: "
                  f"{len(lost)}/{len(red)} lost at least one verse and {len(gone)} lost all "
                  f"of them.\n  {took}/{len(red)} abstained.")
            if gone:
                g = sum(x["abstained"] for x in gone)
                print(f"  of the {len(gone)} with NO window left, {g} abstained"
                      + ("" if g == len(gone)
                         else f" -- the other {len(gone)-g} answered from nothing"))
    bad = [x for x in red if x["trace_says_absent"] and not x["abstained"]][:3]
    for x in bad:
        print(f"\n  --- trace said absent, chose {x['choice']} ({x['cid']})")
        print("      " + (x["thinking"][:300].replace("\n", " ") or "(empty)"))


def mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar p. The arms answer the SAME items, so the comparison is
    paired and only the discordant pairs carry information; an unpaired chi-square on
    69 items would be both wrong and optimistic."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def compare(path_a, path_b, ab):
    """Thinking off vs on, paired by (item, condition)."""
    A = {(r["cid"], r["condition"]): r for r in json.load(open(path_a, encoding="utf-8"))}
    B = {(r["cid"], r["condition"]): r for r in json.load(open(path_b, encoding="utf-8"))}
    keys = sorted(set(A) & set(B))
    print("=" * 74)
    print(f"THINKING OFF  {path_a}")
    print(f"THINKING ON   {path_b}")
    print(f"paired on {len(keys)} (item, condition) pair(s)\n")
    for cond in sorted({k[1] for k in keys}):
        ks = [k for k in keys if k[1] == cond]
        if not ks:
            continue
        a = sum(A[k]["abstained"] for k in ks)
        b_ = sum(B[k]["abstained"] for k in ks)
        n = len(ks)
        only_on = sum(1 for k in ks if B[k]["abstained"] and not A[k]["abstained"])
        only_off = sum(1 for k in ks if A[k]["abstained"] and not B[k]["abstained"])
        p = mcnemar(only_on, only_off)
        print(f"{cond.upper():9} n={n}")
        print(f"  abstained (E), thinking OFF   {a:4d}  {a/n:6.1%}")
        print(f"  abstained (E), thinking ON    {b_:4d}  {b_/n:6.1%}")
        fa = sum(A[k].get("nota") for k in ks)
        fb = sum(B[k].get("nota") for k in ks)
        if fa or fb:
            print(f"  none-of-the-above (F) OFF/ON  {fa:4d} / {fb:<4d}"
                  f"  {fa/n:5.1%} / {fb/n:5.1%}"
                  "   <-- F is never correct in either condition")
        print(f"  changed: off->on {only_on}, on->off {only_off}   "
              f"McNemar exact p = {p:.4f}")
        if cond == "redacted":
            print("  (E is the correct answer here; higher is better)")
    target = "redacted" if any(k[1] == "redacted" for k in keys) else max(
        {k[1] for k in keys}, default="")
    on_only = [k for k in keys if k[1] == target]
    if on_only:
        says = sum(B[k]["trace_says_absent"] for k in on_only)
        both = sum(B[k]["trace_says_absent"] and B[k]["abstained"] for k in on_only)
        gap = sum(B[k]["trace_says_absent"] and not B[k]["abstained"] for k in on_only)
        print(f"\nthinking arm, {target.upper()}: trace said absent on {says}/{len(on_only)}; "
              f"of those {both} chose E and {gap} did not")
        if says:
            print(f"  P(chose E | trace says absent) = {both/says:.1%}"
                  + ("   <-- the model knows and will not say it"
                     if both / says < 0.5 else ""))
    return 0


def self_test():
    ok = []
    w = "11 第十一节。\n12 第十二节。\n13 第十三节。"
    vb = parse_verses("13 alpha\n\n2 bravo\n\n3 charlie", "1kgs_13_1-34")
    vl = parse_verses("13 alpha\n2 bravo\n3 charlie", "1kgs_13_1-34")
    ok.append(("blank-line and one-per-line passages parse identically",
               vb == vl == {(13, 1): "alpha", (13, 2): "bravo", (13, 3): "charlie"}))
    ok.append(("the first block's number is the CHAPTER, not verse 1",
               (13, 1) in vb and (13, 13) not in vb))
    ok.append(("a wrapped continuation line joins the verse it belongs to",
               parse_verses("13 alpha\n  still alpha\n2 bravo", "1kgs_13_1-34")
               == {(13, 1): "alpha still alpha", (13, 2): "bravo"}))
    ok.append(("numbering restarts at a chapter boundary",
               parse_verses("6 a\n25 b\n7 c\n2 d", "2kgs_6_24-7_20")
               == {(6, 24): "a", (6, 25): "b", (7, 1): "c", (7, 2): "d"}))
    ok.append(("the chapter marker at a boundary starts verse 1 of the NEXT chapter",
               parse_verses("17 a\n2 b\n13 c\n18 d\n2 e", "judg_17_1-18_31")
               == {(17, 1): "a", (17, 2): "b", (17, 13): "c",
                   (18, 1): "d", (18, 2): "e"}))
    ok.append(("a GAP is a deleted verse, not a new chapter",
               parse_verses("13 a\n2 b\n5 c\n6 d", "1kgs_13_1-34")
               == {(13, 1): "a", (13, 2): "b", (13, 5): "c", (13, 6): "d"}))
    ok.append(("redaction removes the keyed verse only",
               redact(w, "26:12") == "11 第十一节。\n13 第十三节。"))
    ok.append(("redaction accepts a bare verse number", redact(w, "12") == redact(w, "26:12")))
    ok.append(("redaction does not match a number inside another verse's text",
               redact("1 abc\n11 def", "26:1") == "11 def"))
    ok.append(("redaction of an absent verse is a no-op", redact(w, "26:99") == w))
    ok.append(("content_id is unwrapped from the answered cell's passage_id",
               content_id_of({"passage_id": "uw-t1_2kgs11:fn7d-mcq"}) == "t1_2kgs11:fn7d"))
    ok.append(("a bare content_id passes through",
               content_id_of({"content_id": "t1_judg9:o93q"}) == "t1_judg9:o93q"))
    ok.append(("occurrence suffixes are dropped",
               content_id_of({"content_id": "t1_judg9:o93q#1"}) == "t1_judg9:o93q"))
    ok.append(("a single reference is one verse",
               parse_ref_span("26:11", 26) == [(26, 11)]))
    ok.append(("a RANGE reference expands to every verse it covers",
               parse_ref_span("26:4-5", 26) == [(26, 4), (26, 5)]))
    ok.append(("a bare verse uses the passage's chapter",
               parse_ref_span("11", 26) == [(26, 11)]))
    ok.append(("an empty or missing reference yields nothing rather than crashing",
               parse_ref_span("", 1) == [] and parse_ref_span(None, 1) == []
               and parse_ref_span("x:y", 1) == []))
    ok.append(("a bare range uses the passage's chapter",
               parse_ref_span("17-18", 13) == [(13, 17), (13, 18)]))
    ok.append(("an absurd span is rejected", parse_ref_span("1:1-999", 1) == []))
    ok.append(("verse_number handles both shapes",
               verse_number("26:11") == "11" and verse_number("11") == "11"))
    ok.append(("Chinese absence cue is caught",
               trace_signals_absence("这段经文没有提到他的名字")))
    ok.append(("English absence cue is caught",
               trace_signals_absence("The passage does not mention who was sent.")))
    ok.append(("case is ignored for English", trace_signals_absence("NOT IN THE PASSAGE")))
    ok.append(("a confident trace is not flagged",
               not trace_signals_absence("经文说天使向撒迦利亚显现，所以选 B")))
    ok.append(("empty trace is not flagged", not trace_signals_absence("")))
    ok.append(("letter parsed from JSON", parse_letter('{"selected_choice":"E"}', "ABCDE") == "E"))
    ok.append(("letter parsed from bare text", parse_letter("答案是 C", "ABCDE") == "C"))
    ok.append(("thinking block ignored when parsing",
               parse_letter("<think>maybe A</think> {\"selected_choice\":\"D\"}", "ABCDE") == "D"))
    ok.append(("unparseable gives None", parse_letter("不知道", "ABCDE") is None))
    five = {"A": "甲", "B": "乙", "C": "丙", "D": "丁", "E": PINNED["E"]}
    p = build_prompt({"Q": "谁？", "choices": five}, "11 经文", "ABCDE", "E")
    ok.append(("5-option prompt offers A-E and names the abstention",
               "A, B, C, D 或 E" in p and "选 E" in p and "以上都不是" not in p))
    ok.append(("prompt forbids prior knowledge", "不要依赖你已有的圣经知识" in p))

    # ---- six options ----
    six = add_meta_options(five, "ABCDEF", "E", "F")
    ok.append(("F is appended with the pinned string, E untouched",
               six["F"] == PINNED["F"] and six["E"] == PINNED["E"]
               and [six[L] for L in "ABCD"] == ["甲", "乙", "丙", "丁"]))
    ok.append(("adding meta-options is idempotent",
               add_meta_options(six, "ABCDEF", "E", "F") == six))
    p6 = build_prompt({"Q": "谁？", "choices": six}, "11 经文", "ABCDEF", "E", "F")
    ok.append(("6-option prompt offers A-F", "A, B, C, D, E 或 F" in p6))
    ok.append(("the evidence nudge is present by default", EVIDENCE_NUDGE in p6))
    p6n = build_prompt({"Q": "谁？", "choices": six}, "11 经文", "ABCDEF", "E", "F",
                       evidence_nudge=False)
    ok.append(("--no-evidence-nudge removes it and nothing else",
               EVIDENCE_NUDGE not in p6n
               and p6n.replace("", "") == p6.replace(EVIDENCE_NUDGE + "\n", "")))
    ok.append(("the nudge comes BEFORE the letter instruction, as in the pipeline",
               p6.index(EVIDENCE_NUDGE) < p6.index("必须从")))
    ok.append(("the nudge comes AFTER the options, so it is read against them",
               p6.index("选项：") < p6.index(EVIDENCE_NUDGE)))
    ok.append(("the two meta-options are given DIFFERENT conditions",
               "没有提供足够的信息" in p6 and "确实回答了这个问题，但答案不是" in p6))
    pd = build_prompt({"Q": "谁？", "choices": six}, "11 经文", "ABCDEF", "E", "F",
                      meta_wording="disjoint")
    ok.append(("disjoint E is a claim about the PASSAGE, not about answering",
               "完全没有提到这个问题的答案" in pd
               and "没有提供足够的信息来回答" not in pd))
    ok.append(("disjoint F says the answer exists but is unlisted",
               "给出了答案，但这个答案不在" in pd))
    ok.append(("disjoint states the two do not overlap",
               "互不重叠" in pd and "E 表示经文没有说" in pd
               and "F 表示经文说了但选项里没有" in pd))
    ok.append(("the exclusivity note appears only when BOTH options are offered",
               "互不重叠" not in build_prompt({"Q": "q", "choices": five}, "w", "ABCDE", "E",
                                              meta_wording="disjoint")))
    ok.append(("both wordings name the same letters and content options",
               all(x in pd for x in ("A, B, C, D, E 或 F", "A、B、C 或 D"))))
    ok.append(("the none-of-the-above condition lists only content letters",
               "A、B、C 或 D" in p6))
    ok.append(("both pinned strings appear as options",
               PINNED["E"] in p6 and PINNED["F"] in p6))
    clash = False
    try:
        add_meta_options({"A": "甲", "B": "乙", "C": "丙", "D": PINNED["F"]},
                         "ABCDEF", "E", "F")
    except ValueError:
        clash = True
    ok.append(("a content option that duplicates F is refused, not shipped", clash))

    # ---- role-keyed labels and the swapped assignment ----
    exp = add_meta_options({"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                           "ABCDEF", "E", "F", "explicit")
    ok.append(("explicit labels state both conditions about the PASSAGE",
               exp["E"] == META_LABELS["explicit"]["abstain"]
               and exp["F"] == META_LABELS["explicit"]["nota"]
               and "无法判断" not in exp["E"]))
    swapped = add_meta_options({"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                               "ABCDEF", "F", "E", "explicit")
    ok.append(("--abstain F --nota E puts none-of-the-above FIRST, at E",
               swapped["E"] == META_LABELS["explicit"]["nota"]
               and swapped["F"] == META_LABELS["explicit"]["abstain"]))
    relabel = add_meta_options({"A": "甲", "B": "乙", "C": "丙", "D": "丁",
                                "E": PINNED["E"]}, "ABCDEF", "F", "E", "explicit")
    ok.append(("a letter holding the OLD meta string is relabelled, not refused",
               relabel["E"] == META_LABELS["explicit"]["nota"]))
    refused = False
    try:
        add_meta_options({"A": "甲", "B": "乙", "C": "丙", "E": "王坐在宝座上"},
                         "ABCDEF", "E", "F", "explicit")
    except ValueError:
        refused = True
    ok.append(("a letter holding real CONTENT is still refused", refused))

    # ---- the sequential wording ----
    seq = build_prompt({"Q": "谁？", "choices": exp}, "11 经文", "ABCDEF", "E", "F",
                       meta_wording="sequential")
    ok.append(("sequential wording gives an order of operations, not a description",
               "第一步" in seq and "第二步" in seq))
    ok.append(("sequential wording forbids abstaining when the passage DID answer",
               "就不能选 E" in seq))
    seq_swapped = build_prompt({"Q": "谁？", "choices": swapped}, "11 经文", "ABCDEF",
                               "F", "E", meta_wording="sequential")
    ok.append(("the wording follows the ROLE, not the letter",
               "如果经文根本没有提到答案，选 F" in seq_swapped
               and "如果都不是，选 E" in seq_swapped))
    # ---- stratified sampling ----
    pool = [{"cid": f"t1_p{p}:i{i}", "pid": f"t1_p{p}"} for p in range(5) for i in range(10)]
    samp = stratified_sample(pool, 10, seed=1)
    ok.append(("a sample of 10 from 5 passages takes 2 from each",
               len(samp) == 10 and sorted(Counter(x["pid"] for x in samp).values()) == [2]*5))
    ok.append(("--limit's first-N would have taken all 10 from ONE passage",
               len({x["pid"] for x in pool[:10]}) == 1))
    ok.append(("sampling is deterministic given the seed",
               [x["cid"] for x in stratified_sample(pool, 7, seed=3)]
               == [x["cid"] for x in stratified_sample(pool, 7, seed=3)]))
    ok.append(("a different seed draws a different sample",
               [x["cid"] for x in stratified_sample(pool, 7, seed=3)]
               != [x["cid"] for x in stratified_sample(pool, 7, seed=4)]))
    ok.append(("asking for more than exists returns everything, unshuffled",
               stratified_sample(pool, 999) is pool and stratified_sample(pool, 0) is pool))
    uneven = ([{"cid": f"a:{i}", "pid": "a"} for i in range(8)]
              + [{"cid": "b:0", "pid": "b"}])
    ok.append(("a passage with too few items does not stall the round-robin",
               len(stratified_sample(uneven, 6, seed=0)) == 6))

    ok.append(("every label set keeps the two meta-options distinct",
               all(v["abstain"] != v["nota"] for v in META_LABELS.values())))
    wrong = False
    try:
        add_meta_options(dict(five, F="以上皆非"), "ABCDEF", "E", "F")
    except ValueError:
        wrong = True
    ok.append(("an F that is not the pinned string is refused", wrong))
    # the bug that voided arm 1 of the first overnight run
    import urllib.request as _u
    seen = {}
    class _R:
        def __init__(self, b): self.b = b
        def read(self): return self.b
        def __enter__(self): return self
        def __exit__(self, *a): return False
    def _fake(req, timeout=0):
        seen["payload"] = json.loads(req.data.decode())
        return _R(json.dumps({"message": {"content": '{"selected_choice":"B"}'}}).encode())
    _real, _u.urlopen = _u.urlopen, _fake
    try:
        ollama_chat("p", "m", "http://x", think=False)
        off = seen["payload"]
        ollama_chat("p", "m", "http://x", think=True)
        on = seen["payload"]
    finally:
        _u.urlopen = _real
    ok.append(("think=False SENDS think:false rather than omitting the field",
               off.get("think") is False))
    ok.append(("think=True sends think:true", on.get("think") is True))
    ok.append(("mcnemar is symmetric", mcnemar(3, 9) == mcnemar(9, 3)))
    ok.append(("no discordant pairs means p=1", mcnemar(0, 0) == 1.0))
    ok.append(("a lopsided split is significant, an even one is not",
               mcnemar(0, 12) < 0.01 < mcnemar(6, 6)))
    ok.append(("p never exceeds 1", all(mcnemar(i, j) <= 1.0
                                        for i in range(4) for j in range(4))))
    bad = 0
    for name, cond in ok:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        bad += not cond
    print(f"\n{len(ok)-bad}/{len(ok)} self-tests passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-root", default=DEFAULT_RUN,
                    help="run whose translated Chinese QA is reused (no API cost)")
    ap.add_argument("--windows", default=DEFAULT_WINDOWS)
    ap.add_argument("--model", default="qwen3:1.7b")
    ap.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL",
                                                    "http://localhost:11434"))
    ap.add_argument("--no-think", action="store_true",
                    help="disable reasoning, to contrast with the thinking arm")
    ap.add_argument("--labels", default="ABCDE")
    ap.add_argument("--abstain", default="E")
    ap.add_argument("--evidence-nudge", dest="evidence_nudge", action="store_true",
                    default=True,
                    help="include the pipeline's push toward content options before the "
                         "meta-option instructions (default: on, matching deployment)")
    ap.add_argument("--no-evidence-nudge", dest="evidence_nudge", action="store_false")
    ap.add_argument("--meta-labels", choices=sorted(META_LABELS), default="current",
                    help="which text the two meta-options carry. 'current' is what every "
                         "run so far has shown; 'explicit' states both as claims about the "
                         "PASSAGE. Appended at run time, so switching costs nothing.")
    ap.add_argument("--meta-wording", choices=sorted(META_WORDING), default="current",
                    help="how E and F are explained. 'current' mirrors the deployed "
                         "_meta_hint(); 'disjoint' makes E a claim about the passage and "
                         "states that E and F do not overlap, because the traces show the "
                         "current E clause absorbing F's case.")
    ap.add_argument("--nota", default="",
                    help="none-of-the-above label, e.g. F. The translated QA in a finished "
                         "run is 5-option; F is a fixed string so it is appended here at no "
                         "cost. F is never the correct answer in either condition, so its "
                         "rate is a false-alarm measure -- and tells you whether offering it "
                         "cannibalises E.")
    ap.add_argument("--mode", choices=["redact", "dose", "swap", "corrupt"],
                    default="redact",
                    help="redact: surgical control, the keyed verse removed. "
                         "dose: the real defect variants at each --doses level. "
                         "swap: the key's TEXT is replaced by a borrowed distractor so the "
                         "passage still answers but no content option does -- the positive "
                         "control for F, as redact is for E. "
                         "corrupt: the answer span in the PASSAGE is replaced so the text "
                         "asserts something no option states -- the same situation "
                         "mistranslation creates, with F correct by construction.")
    ap.add_argument("--doses", nargs="+", default=["0%", "30%"])
    ap.add_argument("--defect", default="omission")
    ap.add_argument("--corrupted-windows",
                    default="evaluation/datasets/mcq/corrupted_windows.json",
                    help="verified LLM-rewritten windows from build_corrupted_windows.py")
    ap.add_argument("--checkpoint-every", type=int, default=10,
                    help="flush partial results every N generations (atomic replace)")
    ap.add_argument("--resume", dest="resume", action="store_true", default=True,
                    help="reuse results already in --out and skip those items (default: on)")
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.add_argument("--limit", type=int, default=0,
                    help="truncate to the first N items. This is a PLUMBING rehearsal knob: "
                         "the first N all come from one passage, so its percentages are not "
                         "a sample. Use --sample for a small run you intend to read.")
    ap.add_argument("--sample", type=int, default=0,
                    help="take N items spread evenly across passages (deterministic given "
                         "--sample-seed), so a short run is a sample rather than one "
                         "passage. Applied after loading, so every cell of a factorial "
                         "design gets the same items and contrasts stay paired.")
    ap.add_argument("--sample-seed", type=int, default=0)
    ap.add_argument("--out", default="evaluation/outputs/reports/abstention_thinking_probe.json")
    ap.add_argument("--compare", nargs=2, metavar=("OFF_JSON", "ON_JSON"),
                    help="compare a thinking-off run against a thinking-on run, paired")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.compare:
        return compare(a.compare[0], a.compare[1], a.abstain)
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
