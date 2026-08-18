#!/usr/bin/env python3
"""Probe the RAW Ollama output (including <think>) for a campaign cell.

The pipeline strips <think>...</think> before saving (extract_json_text), and a
timed-out item saves nothing — so the raw reasoning never lands on disk. This
script rebuilds the *exact* answer prompt the mixed-defect campaign uses
(verse-window local passage + /no_think, same system message) and STREAMS the
model output token-by-token, so you can see whether qwen3:1.7b still emits a
<think> trace despite --ollama-no-think and whether it runs away (never closes
</think>). It reports tokens generated and wall time per question.

Run on the machine with Ollama (NOT in CI):
  python3 evaluation/scripts/mcq/probe_ollama_think.py \
    --artifact-root-template 'evaluation/outputs/luke{chapter}/1.7b/mixed/grammar20_omission' \
    --chapter 4 --level 10% \
    --answer-model qwen3:1.7b --answer-verse-window 2 --ollama-no-think

Add --num-predict 256 to see how it behaves with an output cap, or
--max-questions 3 to probe just the first few.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.agents.generate_chinese_answers import (  # noqa: E402
    apply_no_think,
    build_raw_answer_prompt,
    chapters_from_reference,
    index_passage_verses,
    load_passage,
    local_passage_for_question,
    public_questions,
)


def _system_message(expanded: bool) -> str:
    return (
        "Answer from the translated passage only. Do not include verse numbers, "
        "guess, or use outside knowledge. "
        "Do not repeat or echo the passage text in the answer. "
        "Do not echo the question. Do not output markdown or explanations. "
        + (
            "Return only valid JSON matching the requested schema."
            if expanded
            else "Return only the raw answer text."
        )
    )


def probe(base_url, model, passage_local, question, *, no_think, expanded, num_predict, timeout):
    prompt = build_raw_answer_prompt(passage_local, question, expanded_answer_format=expanded)
    if no_think:
        prompt = apply_no_think(prompt)
    options = {"temperature": 0, "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "8192"))}
    if num_predict:
        options["num_predict"] = int(num_predict)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_message(expanded)},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": options,
    }
    if no_think:
        payload["think"] = False   # structured switch; /no_think alone is ignored
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    content, thinking, eval_count, total_ns = [], [], None, None
    t0 = time.time()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for line in response:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            message = obj.get("message") or {}
            # Newer Ollama parses a Qwen3 reasoning trace OUT of content into a
            # structured `thinking` field. Reading only `content` therefore shows
            # a two-character answer while eval_count reports 168 tokens -- the
            # reasoning is real, just routed elsewhere.
            reasoning = message.get("thinking") or ""
            if reasoning:
                thinking.append(reasoning)
                sys.stdout.write(f"\033[2m{reasoning}\033[0m")
                sys.stdout.flush()
            chunk = message.get("content", "")
            if chunk:
                content.append(chunk)
                sys.stdout.write(chunk)
                sys.stdout.flush()
            if obj.get("done"):
                eval_count = obj.get("eval_count")
                total_ns = obj.get("total_duration")
    elapsed = time.time() - t0
    full = "".join(content)
    reasoned = "".join(thinking)
    return {
        "thinking_chars": len(reasoned),
        "answer_chars": len(full),
        "elapsed_s": elapsed,
        "eval_count": eval_count,
        "tok_per_s": (eval_count / (total_ns / 1e9)) if (eval_count and total_ns) else None,
        "has_think_open": "<think>" in full,
        "has_think_close": "</think>" in full,
        "chars": len(full),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact-root-template", required=True,
                   help="e.g. 'evaluation/outputs/luke{chapter}/1.7b/mixed/grammar20_omission'")
    p.add_argument("--chapter", type=int, required=True)
    p.add_argument("--level", required=True, help="method folder, e.g. 10%%")
    p.add_argument("--answer-model", default="qwen3:1.7b")
    p.add_argument("--answer-verse-window", type=int, default=2, help="-1 = full passage")
    p.add_argument("--ollama-no-think", action="store_true")
    p.add_argument("--expanded-answer-format", action="store_true")
    p.add_argument("--ollama-base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    p.add_argument("--num-predict", type=int, default=None, help="cap output tokens (default: uncapped)")
    p.add_argument("--timeout", type=float, default=float(os.getenv("OLLAMA_TIMEOUT", "300")))
    p.add_argument("--max-questions", type=int, default=None)
    args = p.parse_args()

    method_dir = Path(args.artifact_root_template.format(chapter=args.chapter)) / args.level
    passage = load_passage(method_dir / "passage_target_decanonicalized.txt")
    qa = json.loads((method_dir / "qa_target_decanonicalized.json").read_text(encoding="utf-8"))
    questions = public_questions(qa)
    if args.max_questions:
        questions = questions[: args.max_questions]

    verse_window = None if args.answer_verse_window < 0 else args.answer_verse_window
    passage_chapters = next(
        (
            chapters_from_reference(q.get("passage_reference"))
            for q in questions
            if chapters_from_reference(q.get("passage_reference"))
        ),
        [],
    )
    if verse_window is not None:
        verse_index, verse_order = index_passage_verses(passage, passage_chapters)
    else:
        verse_index, verse_order = {}, []

    print(f"# cell: {method_dir}  model={args.answer_model}  no_think={args.ollama_no_think}  "
          f"num_predict={args.num_predict or 'uncapped'}  questions={len(questions)}\n")

    summary = []
    for i, q in enumerate(questions, 1):
        local = q.get("local_passage") or (
            local_passage_for_question(passage, verse_index, q, verse_window, verse_order)
            if verse_window is not None else passage
        )
        print(f"\n===== Q{i} ({q.get('q_type','?')}) id={q.get('source_idx', q.get('id','?'))} =====")
        print(f"Q: {q.get('question','')}")
        print("---- raw model stream ----")
        try:
            stats = probe(
                args.ollama_base_url, args.answer_model, local, q,
                no_think=args.ollama_no_think, expanded=args.expanded_answer_format,
                num_predict=args.num_predict, timeout=args.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"\n[!] {type(exc).__name__}: {exc}")
            summary.append((i, q.get("q_type"), "ERROR", None, None, None))
            continue
        flag = ""
        if stats["has_think_open"]:
            flag = "  <-- THINK LEAKED despite /no_think" if not args.expanded_answer_format else "  <-- <think> present"
        if stats["has_think_open"] and not stats["has_think_close"]:
            flag = "  <-- RUNAWAY: <think> never closed (this is what times out)"
        if stats.get("thinking_chars"):
            flag = f"  <-- REASONING via message.thinking ({stats['thinking_chars']} chars) DESPITE /no_think"
        print(f"\n---- {stats['eval_count']} tokens in {stats['elapsed_s']:.1f}s "
              f"({(stats['tok_per_s'] or 0):.1f} tok/s), answer={stats.get('answer_chars')}ch "
              f"think_tag={stats['has_think_open']}{flag}")
        summary.append((i, q.get("q_type"), stats["eval_count"], stats["elapsed_s"],
                        stats["has_think_open"], stats["has_think_close"]))

    print("\n\n=== SUMMARY (Q, type, tokens, seconds, think_open, think_closed) ===")
    for row in summary:
        print("  ", row)
    slow = [r for r in summary if isinstance(r[2], int) and r[2] and r[2] > 1500]
    if slow:
        print(f"\n{len(slow)} question(s) generated >1500 tokens — those are the timeout risk.")
        print("Fixes: keep /no_think, and cap generation with OLLAMA_NUM_PREDICT (e.g. 256).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
