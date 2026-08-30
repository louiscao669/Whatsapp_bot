#!/usr/bin/env python3
"""Recover and compare qwen3:1.7b reasoning traces across a defect ladder.

WHY THIS EXISTS. `ollama_effort()` records `thinking_chars` -- a LENGTH -- but
not the reasoning text, and `clean_raw_answer` strips the <think> block before
anything is written. So the mistranslation result (effort beta = +0.744,
t = +4.57) tells us the model reasons ~25% longer at 30% dose without telling
us WHAT the extra tokens are doing. That distinction matters: "re-reads the
passage hunting for a referent" and "enumerates MCQ options more verbosely"
are very different mechanisms, and only one of them is a quality signal.

Answer generation is deterministic (`options["temperature"] = 0`), so re-running
an item reproduces the original generation exactly. Nothing is re-scored and
nothing is written to the run outputs -- this reads inputs and writes one report.

HOW IT STAYS FAITHFUL. It calls the pipeline's own `generate_answers()` with the
same verse-window handling and prompt construction the run used, and monkeypatches
`ollama_effort` to stash the raw Ollama payload (which carries `message.thinking`)
instead of rebuilding a prompt by hand. A hand-rolled prompt would silently differ
and the traces would not be the ones that produced the numbers.

PAIRING. For each sampled item it runs the SAME item at dose 0% (clean) and at
--dose, so the comparison is within-item. Cross-item trace comparison is useless
here: per-item reasoning length has a log sd of ~0.8, which swamps the ~25% dose
effect.

Usage:
  python3 evaluation/scripts/analysis/inspect_thinking_traces.py \
      --passage t1_judg9 --dose 30% --n 10 --q-type mcq
  python3 evaluation/scripts/analysis/inspect_thinking_traces.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

def _find_repo(start: Path) -> Path:
    """Walk up to the repo root instead of assuming a fixed depth.

    parents[3] breaks the moment the file is run from anywhere but
    evaluation/scripts/analysis/ -- including a scratch copy -- and the
    IndexError it raises says nothing useful.
    """
    for cand in [start, *start.parents]:
        if (cand / "evaluation" / "agents").is_dir():
            return cand
    return Path.cwd()


REPO = _find_repo(Path(__file__).resolve().parent)
sys.path.insert(0, str(REPO))

OUT_ROOT = REPO / "evaluation" / "outputs" / "tier1_bsb"
WINDOWS = REPO / "QA_algorithm" / "inputs" / "tier1_qa_verse_windows.json"
CLEAN_CELL = "grammar/0%"          # byte-identical to mistranslation/0%, verified


def cell_dir(passage: str, cell: str) -> Path:
    return OUT_ROOT / passage / "qwen317b_think" / cell


def load_items(path: Path) -> list[dict]:
    """Normalise QA the way the pipeline does before answering.

    The on-disk qa_target_decanonicalized.json uses `Q`/`A` and carries no
    `item_index`; `public_questions()` is what maps those to the shape
    generate_answers() expects and assigns the index. Reading the raw JSON and
    passing it straight in fails inside failed_answer_output with
    KeyError: 'item_index' -- and it fails on the ERROR path, so the real cause
    is hidden. Indices are assigned over the FULL list (and mcq/open are
    expanded from one record), so filter AFTER this call or the indices will
    not line up with the run outputs.
    """
    import evaluation.agents.generate_chinese_answers as gen
    return gen.public_questions(gen.load_qa_items(path))


def segment(trace: str) -> dict[str, int]:
    """Rough functional breakdown of a reasoning trace.

    Deliberately crude -- these are keyword heuristics on Chinese/English mixed
    text, meant to point at where the extra tokens went, not to be a taxonomy.
    Read the traces themselves before trusting any of these counts.
    """
    sents = [s for s in re.split(r"[。！？\n.!?]+", trace) if s.strip()]
    buckets = {
        "quotes_passage": ("passage says", "根据", "文中", "原文", "提到"),
        "weighs_options": ("option", "选项", "A ", "B ", "C ", "D ", "或者"),
        "expresses_doubt": ("but", "however", "但是", "不过", "可是", "不确定",
                            "wait", "hmm", "seems", "似乎", "好像", "矛盾"),
        "restates_question": ("question", "问题", "asks", "问的是"),
    }
    out = {k: 0 for k in buckets}
    out["sentences"] = len(sents)
    for s in sents:
        low = s.lower()
        for k, keys in buckets.items():
            if any(t.lower() in low for t in keys):
                out[k] += 1
    return out


def run_cell(passage: str, cell: str, items: list[dict], args) -> list[dict]:
    """Answer `items` against one cell's passage, capturing raw payloads."""
    import evaluation.agents.generate_chinese_answers as gen

    captured: list[dict] = []
    original = gen.ollama_effort

    def spy(data, content=""):
        captured.append({
            "thinking": ((data.get("message") or {}).get("thinking") or ""),
            "content": content,
        })
        return original(data, content)

    # Positional zip() is WRONG here. ollama_effort only fires on a SUCCESSFUL
    # generation, so any failed item leaves no capture and shifts every later
    # trace up by one -- silently, because zip truncates. Observed on the wbw
    # MCQ run: item 1 failed (0 tokens) and items 1-9 were each paired with the
    # NEXT item's reasoning. Pair on the answer's own effort payload instead.

    gen.ollama_effort = spy
    try:
        d = cell_dir(passage, cell)
        passage_text = (d / "passage_target_decanonicalized.txt").read_text(encoding="utf-8")
        vw = gen.load_verse_windows(WINDOWS) if WINDOWS.exists() else None
        answers = gen.generate_answers(
            passage_text, items,
            provider="ollama", model=args.model,
            ollama_base_url=args.ollama_base_url,
            batch_size=1, verse_window=2, retries=0, dry_run=False,
            allow_partial_answers=True, ollama_no_think=False,
            expanded_answer_format=False,
            mcq_choice_mapper="rules", mcq_choice_model="",
            verse_windows=vw,
        )
    finally:
        gen.ollama_effort = original

    # Match each answer to its capture by the effort payload identity that
    # ollama_effort returned for it; fall back to leaving the trace EMPTY
    # rather than guessing, so a gap is visible instead of silently wrong.
    by_answer_chars: dict = {}
    for c in captured:
        cleaned = re.sub(r"<think>.*?</think>", "", c["content"] or "",
                         flags=re.S).strip()
        by_answer_chars.setdefault(len(cleaned), []).append(c)
    misaligned = 0
    for a in answers:
        eff = a.get("answer_effort") or {}
        key = eff.get("answer_chars")
        bucket = by_answer_chars.get(key) or []
        if bucket:
            c = bucket.pop(0)
            a["_thinking"] = c["thinking"] or "".join(
                re.findall(r"<think>(.*?)</think>", c["content"], re.S))
        else:
            a["_thinking"] = ""
            misaligned += 1
    if misaligned:
        print(f"  [warn] {misaligned}/{len(answers)} item(s) have no matched "
              f"trace (generation failed or answer_chars collision); their "
              f"traces are EMPTY, not shifted.", file=sys.stderr)
    return answers


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--passage", default="t1_judg9")
    p.add_argument("--dose", default="30%")
    p.add_argument("--family", default="mistranslation")
    p.add_argument("--dirty-cell",
                   help="Explicit cell path under qwen317b_think/ (e.g. "
                        "google_word_by_word). Overrides --family/--dose for "
                        "conditions that are not a dose ladder.")
    p.add_argument("--max-latin", type=float, default=5.0,
                   help="Refuse a dosed passage whose Latin share exceeds this "
                        "%%. Guards against the wbw cells where the token "
                        "fallback left 21-93%% untranslated English -- those "
                        "look like valid translations on disk but are not.")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--q-type", choices=("mcq", "open", "both"), default="mcq")
    p.add_argument("--model", default="qwen3:1.7b")
    p.add_argument("--ollama-base-url", default="http://localhost:11434")
    p.add_argument("--out", type=Path,
                   default=REPO / "evaluation/outputs/reports/thinking_traces.json")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)

    if args.self_test:
        t = ("The passage says Tadul went. But option B seems wrong. "
             "The question asks who. 原文提到尼温。不过选项A矛盾。")
        s = segment(t)
        assert s["sentences"] >= 4 and s["quotes_passage"] >= 1 and s["expresses_doubt"] >= 1
        print("segment():", s)
        print("SELF-TEST PASSED")
        return 0

    dirty_cell = args.dirty_cell or f"{args.family}/{args.dose}"
    dirty = cell_dir(args.passage, dirty_cell)
    clean = cell_dir(args.passage, CLEAN_CELL)
    for d in (dirty, clean):
        if not (d / "passage_target_decanonicalized.txt").exists():
            print(f"[fatal] missing {d}", file=sys.stderr)
            return 2

    # Guard: a passage that was never really translated is not the condition
    # you think it is. Measured on the 2026-08-26 wbw batch: Google refused
    # ~88% of requests, the per-token fallback kept the English source, and the
    # cells landed on disk indistinguishable from good ones.
    dtxt = (dirty / "passage_target_decanonicalized.txt").read_text(encoding="utf-8")
    lat = len(re.findall(r"[A-Za-z]", dtxt))
    cjk = len(re.findall(r"[\u3400-\u9fff]", dtxt))
    share = 100 * lat / max(lat + cjk, 1)
    print(f"dosed passage: {share:.1f}% Latin / {cjk} CJK chars")
    if share > args.max_latin:
        print(f"[fatal] {share:.1f}% Latin exceeds --max-latin {args.max_latin}. "
              f"This cell is largely UNTRANSLATED, not degraded-translation. "
              f"Pass --max-latin to override only if you know why.", file=sys.stderr)
        return 2

    qa = load_items(dirty / "qa_target_decanonicalized.json")
    if args.q_type != "both":
        qa = [q for q in qa if q.get("q_type") == args.q_type]
    qa = qa[: args.n]
    print("item_index sample:", [q.get("item_index") for q in qa[:6]])
    if not qa:
        print("[fatal] no items matched", file=sys.stderr)
        return 2
    print(f"{len(qa)} item(s), {args.passage}, clean vs {dirty_cell}\n")

    a_clean = run_cell(args.passage, CLEAN_CELL, qa, args)
    a_dirty = run_cell(args.passage, dirty_cell, qa, args)

    rows = []
    print("%-4s %-9s %-9s %-8s %-9s %-9s %s" % (
        "#", "tok 0%", "tok dose", "delta", "think 0%", "think dose", "answer 0%->dose"))
    for q, c, dd in zip(qa, a_clean, a_dirty):
        ec = c.get("answer_effort") or {}
        ed = dd.get("answer_effort") or {}
        tc, td = ec.get("output_tokens") or 0, ed.get("output_tokens") or 0
        rows.append({
            "id": q.get("passage_id") or q.get("id"), "q_type": q.get("q_type"),
            "question": q.get("question") or q.get("Q"),
            "clean": {"tokens": tc, "thinking_chars": ec.get("thinking_chars"),
                      "answer": c.get("generated_answer"),
                      "choice": c.get("selected_choice"),
                      "trace": c.get("_thinking", ""),
                      "segments": segment(c.get("_thinking", ""))},
            "dosed": {"tokens": td, "thinking_chars": ed.get("thinking_chars"),
                      "answer": dd.get("generated_answer"),
                      "choice": dd.get("selected_choice"),
                      "trace": dd.get("_thinking", ""),
                      "segments": segment(dd.get("_thinking", ""))},
        })
        print("%-4d %-9d %-9d %-8s %-9s %-9s %s -> %s" % (
            len(rows), tc, td, "%+.0f%%" % (100 * (td / tc - 1)) if tc else "n/a",
            ec.get("thinking_chars"), ed.get("thinking_chars"),
            c.get("selected_choice") or str(c.get("generated_answer"))[:10],
            dd.get("selected_choice") or str(dd.get("generated_answer"))[:10]))

    print("\nWHERE THE EXTRA REASONING GOES (mean sentences per trace)")
    print("%-20s %-10s %-10s %s" % ("segment", "clean", "dosed", "change"))
    keys = ["sentences", "quotes_passage", "weighs_options",
            "expresses_doubt", "restates_question"]
    for k in keys:
        a = sum(r["clean"]["segments"][k] for r in rows) / len(rows)
        b = sum(r["dosed"]["segments"][k] for r in rows) / len(rows)
        print("%-20s %-10.1f %-10.1f %+.1f" % (k, a, b, b - a))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nfull traces -> {args.out}")
    print("Read the traces. The segment counts are keyword heuristics, not a taxonomy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
