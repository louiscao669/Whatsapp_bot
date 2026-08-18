#!/usr/bin/env python3
"""Tier 0-1 driver: re-answer open + NEW MCQ items across the grid, re-score, QC.

Runs, in one command:
  0a. rebuild datasets/mcq/mcq_rewrites.json (via build_rewrites_v2.py) + promote
      it into EVERY condition dir (all 56 qa_target_pseudonymized.json).
  0b. excluded items are skipped automatically: only ids present in mcq_rewrites.json are
      scored (the 2 excluded ones are absent, so they never enter the grid).
  1.  answer each open and MCQ item using the same deterministic randomized three-verse
      window delivered in the human pilot and production.
  2.  score MCQs by letter and open answers with a semantic 0/0.5/1 judge.
  3.  write a combined scores_target_window3_v2.json plus the backwards-compatible
      scores_target_mcq_v2.json.

Then emits evaluation/outputs/reports/mcq_regen_qc/ :
  * qc_report.json / per_item_clean.csv / dose_response.csv
  * PER-ITEM CLEAN ACCURACY (mean over models on omission/0%)  -> broken/mis-key flags (<0.5)
  * DOSE-RESPONSE per model: omission 0/10/20/30 (Spearman), mistranslation 20 vs clean,
    grammar 30 vs clean (should be ~flat), wbw vs clean.
  * BROKEN-ITEM FLAGS: clean acc < threshold, or a defect condition RAISES accuracy (inverted).

The four known off-by-one references are constrained so the next verse containing the
answer remains inside the three-verse passage. Excluded MCQs also exclude their matching
open variants.

  python evaluation/scripts/mcq/regen_mcq_tier01.py --provider ollama
  python evaluation/scripts/mcq/regen_mcq_tier01.py --provider ollama --skip-promote --models "1.5b=qwen2.5:1.5b"
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LETTER = re.compile(r"[A-Da-d]")
THINK = re.compile(r"<think>.*?</think>", re.DOTALL)   # qwen3 reasoning block
HEADER = re.compile(r"<header>.*?</header>", re.DOTALL)
FOOTNOTE = re.compile(r"\[[a-z]\]")
VERSE = re.compile(r"(?<!\d)(\d{1,3})\s")              # a verse-number marker
MODEL_MAP = {"1.7b": "qwen3:1.7b", "1.5b": "qwen2.5:1.5b", "llama 1b": "llama3.2:1b"}
CONDITIONS = ["omission/0%", "omission/10%", "omission/20%", "omission/30%",
              "mistranslation/20%", "grammar/30%", "google_word_by_word"]
DEFAULT_CONDITIONS = list(CONDITIONS)
CLEAN = "omission/0%"
DOMAIN = "你正在回答关于一段宗教经文（圣经）的阅读理解选择题。"
ANSWER_VERSE_OFFSET_STEMS = {
    "uw-174342": 1,
    "uw-174343": 1,
    "uw-174344": 1,
    "uw-174404": 1,
}

# Open items retired but whose MCQ form is kept. 174382: the question ("what did the devil
# want?") is unscoped, and the randomized 3-verse window can straddle two temptations
# (worship v7 + jump v9) -> genuinely two answers for the free-response form. The MCQ form is
# fine (options pin the answer), so we drop only the open form by stem.
EXCLUDED_OPEN_STEMS = {"uw-174382"}


def build_client(provider):
    from openai import OpenAI
    if provider == "ollama":
        return OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), api_key="ollama")
    return OpenAI()


def _create(client, **kwargs):
    """chat.completions.create, but for OLLAMA-served models disable chain-of-thought
    (qwen3) via both the native `think` flag and the template kwarg, so there is no <think>
    block to truncate. Ignored by non-thinking models; NEVER sent to the OpenAI API (so the
    gpt-4o-mini judge is unaffected). The max_tokens+<think>-strip logic stays as a fallback."""
    try:
        is_ollama = "11434" in str(client.base_url) or "ollama" in str(client.base_url).lower()
    except Exception:
        is_ollama = False
    if is_ollama:
        # CONFIRMED working switch: append Qwen3's /no_think token to the last user message
        # (model-level, honored even though this ollama build drops the extra_body params).
        # Harmless literal text to qwen2.5 / llama, which don't reason.
        msgs = kwargs.get("messages") or []
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "user" and isinstance(msgs[i].get("content"), str):
                if "/no_think" not in msgs[i]["content"]:
                    new = dict(msgs[i], content=msgs[i]["content"].rstrip() + " /no_think")
                    kwargs["messages"] = msgs[:i] + [new] + msgs[i + 1:]
                break
        eb = kwargs.setdefault("extra_body", {})       # kept as a belt-and-suspenders no-op
        eb["think"] = False
        eb.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
    return client.chat.completions.create(**kwargs)


def ask_letter(client, model, question, opts, passage):
    # Robust to thinking models (qwen3): give enough tokens for the reasoning to FINISH and
    # emit an answer, then DROP the <think>...</think> block and read the letter after it.
    # (The old bug: max_tokens=256 truncated qwen3 mid-reasoning -> no letter -> "?", 24% of
    # the time. qwen3 reasons in Chinese, so there was no stray A-D to fall back on.)
    prompt = (f"文章：\n{passage}\n\n这是一道单项选择题，请只根据上面的文章作答。\n\n"
              f"问题：{question}\n选项：\n" +
              "\n".join(f"{L}. {opts[L]}" for L in "ABCD" if opts.get(L)) +
              "\n\n请直接给出答案，只输出一个字母：A、B、C 或 D。")
    for _ in range(2):                                 # one retry if we still can't parse
        r = _create(client, model=model, temperature=0.0, max_tokens=1024,
            messages=[{"role": "system", "content": DOMAIN}, {"role": "user", "content": prompt}])
        text = THINK.sub("", r.choices[0].message.content or "")   # strip reasoning
        ms = LETTER.findall(text.strip())
        if ms:
            return ms[-1].upper()
    return "?"


def ask_open(client, model, question, passage):
    prompt = (f"文章：\n{passage}\n\n请只根据上面的文章简短回答问题。"
              f"不要解释，只输出答案。\n\n问题：{question}")
    for _ in range(2):
        response = _create(
            client,
            model=model,
            temperature=0.0,
            max_tokens=1024,   # was 256: truncated qwen3's <think> so nothing followed -> empty
            messages=[{"role": "system", "content": DOMAIN},
                      {"role": "user", "content": prompt}],
        )
        answer = THINK.sub("", response.choices[0].message.content or "").strip()
        if answer:
            return answer
    return ""


def judge_open(client, model, question, expected, generated, passage):
    if not (generated or "").strip():   # a blank answer is never correct -- don't ask the judge
        return 0.0
    prompt = f"""Judge whether a generated answer contains the core claim required by the expected answer.
The passage and question are Chinese; the expected answer is English. Accept equivalent
Chinese wording, paraphrases, anonymized names, and rough grammar. Do not accept merely
related passage context.

Passage:
{passage}

Question: {question}
Expected answer: {expected}
Generated answer: {generated}

Output only one score: 1, 0.5, or 0.
1 = correct core claim; 0.5 = partially correct; 0 = incorrect or missing.
"""
    for _ in range(2):
        response = _create(
            client,
            model=model,
            temperature=0.0,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = THINK.sub("", response.choices[0].message.content or "").strip()
        match = re.search(r"(?<!\d)(0\.5|1(?:\.0)?|0(?:\.0)?)(?!\d)", text)
        if match:
            return float(match.group(1))
    return 0.0


def pick(d, *names):
    for n in names:
        if (d / n).exists():
            return d / n
    return None


def parse_verses(passage):
    """Split a passage into {verse_number: text}. Verse markers = Arabic ints in increasing
    order (Chinese text spells its own numbers, so stray digits are rare). Tolerates gaps so
    omission variants (which delete verses) still parse."""
    text = FOOTNOTE.sub("", HEADER.sub("", passage))
    marks, last = [], 0
    for m in VERSE.finditer(text):
        n = int(m.group(1))
        if n > last and n <= last + 25:               # strictly increasing, no absurd jump
            marks.append((n, m.end(), m.start()))
            last = n
    verses = {}
    for i, (n, tstart, _mstart) in enumerate(marks):
        tend = marks[i + 1][2] if i + 1 < len(marks) else len(text)
        verses[n] = text[tstart:tend].strip()
    return verses


def item_stem(item_id):
    return str(item_id or "").rsplit("-", 1)[0]


def cell_dir_name(chapter, pattern="luke{cell}"):
    """Directory name for one cell.

    [2026-08-17] Was hardcoded ``f"luke{ch}"``, which cannot address the tier-1
    grid (``tier1/t1_judg9``) -- passing ``--chapters t1_judg9`` produced
    ``luket1_judg9``. Parameterised so the same script serves both layouts;
    ``--cell-pattern 'tier1/{cell}'`` reaches tier-1.
    """
    return pattern.format(cell=chapter)


def parse_only_items(raw):
    """Comma list of content_ids, or ``@path`` to a JSON file of them.

    Accepts the artifacts this pipeline already emits -- a bare list, or an
    object with an ``items`` array of records carrying ``content_id`` (e.g.
    ``tier1_gold_72_missing.json``) -- so the targeted set never has to be
    retyped by hand.

    Ids are normalised to stems: the grid writes ``<content_id>-open`` /
    ``-mcq``, and a caller passing either form must select the same item. The
    content_id schemes in this project have already diverged three ways
    (``uw-`` prefixes, ``#2`` occurrence suffixes, re-issued ``b`` ids), so this
    matches on the stem rather than requiring an exact string.
    """
    if not raw:
        return None
    if raw.startswith("@"):
        payload = json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("items", payload.get("content_ids", []))
        ids = [
            (entry.get("content_id") if isinstance(entry, dict) else entry)
            for entry in payload
        ]
    else:
        ids = raw.split(",")
    out = {item_stem(str(i).strip()) for i in ids if str(i or "").strip()}
    if not out:
        raise SystemExit(f"--only-items resolved to an empty set: {raw!r}")
    return out


def randomized_three_verse_window(passage, record):
    """Mirror deployment's stable QA-ID-based three-verse placement."""
    try:
        target = int(
            re.sub(r".*:", "", str(record.get("passage_reference")))
            .split("(")[0]
            .strip()
        )
    except Exception:
        return passage
    verses = parse_verses(passage)
    if len(verses) < 2:                               # parser failed -> don't blank the model
        return passage

    available_min, available_max = min(verses), max(verses)
    answer = target + ANSWER_VERSE_OFFSET_STEMS.get(item_stem(record.get("passage_id")), 0)
    valid_starts = [
        start
        for start in range(available_min, available_max - 1)
        if start <= target <= start + 2 and start <= answer <= start + 2
    ]
    if not valid_starts:
        return ""
    stable_key = str(record.get("passage_id") or record.get("passage_reference") or "")
    random_value = int.from_bytes(
        hashlib.sha256(stable_key.encode("utf-8")).digest()[:8], "big"
    )
    if answer != target:
        start = valid_starts[random_value % len(valid_starts)]
    else:
        desired_start = target - (random_value % 3)
        start = min(valid_starts, key=lambda candidate: (abs(candidate - desired_start), candidate))
    # Missing text remains missing in degraded conditions, while window boundaries
    # stay identical to the clean passage.
    return "\n".join(verses[number] for number in range(start, start + 3) if number in verses)


def promote(root):
    here = Path(__file__).resolve().parents[2]           # evaluation/
    repo = here.parent
    print(">> rebuilding datasets/mcq/mcq_rewrites.json (scripts/mcq/build_rewrites_v2.py) ...")
    subprocess.run(
        [sys.executable, str(here / "scripts" / "mcq" / "build_rewrites_v2.py")],
        cwd=repo,
        check=True,
    )
    print(">> promoting to ALL condition dirs ...")
    subprocess.run([sys.executable, str(repo / "scripts" / "promote_mcq_rewrites.py")], cwd=repo, check=True)


def write_mcq_scores(cell_dir, new_by_id):
    """Write a clean, self-contained MCQ score file for this (model, condition) cell.

    We do NOT edit the legacy scores_target_llama.json: for 1.5b / llama-1b those were scored
    on the older *decanonicalized* text, whereas we are now scoring the pilot's *pseudonymized*
    items. Mixing schemes in one file would corrupt it. Downstream tools read this via
    --score-file scores_target_mcq_v2.json instead.
    """
    cell_dir.mkdir(parents=True, exist_ok=True)
    items = [{"id": iid, "q_type": "mcq", "correct_choice": v["correct"],
              "selected_choice": v["selected"], "direct_correct": v["correct"] == v["selected"]}
             for iid, v in new_by_id.items()]
    out = {"summary": {"mcq_count": len(items),
                       "mcq_correct": sum(i["direct_correct"] for i in items)},
           "items": items}
    (cell_dir / "scores_target_mcq_v2.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def write_combined_scores(cell_dir, mcq_by_id, open_by_id):
    items = [
        {
            "id": item_id,
            "q_type": "mcq",
            "correct_choice": value["correct"],
            "selected_choice": value["selected"],
            "direct_correct": value["correct"] == value["selected"],
        }
        for item_id, value in mcq_by_id.items()
    ] + [
        {
            "id": item_id,
            "q_type": "open",
            "generated_answer": value["generated"],
            "expected_answer": value["expected"],
            "llm_score": value["score"],
        }
        for item_id, value in open_by_id.items()
    ]
    mcq_items = [item for item in items if item["q_type"] == "mcq"]
    open_items = [item for item in items if item["q_type"] == "open"]
    output = {
        "summary": {
            "mcq_count": len(mcq_items),
            "mcq_correct": sum(item["direct_correct"] for item in mcq_items),
            "open_count": len(open_items),
            "open_llm_score_mean": (
                sum(item["llm_score"] for item in open_items) / len(open_items)
                if open_items else None
            ),
        },
        "items": items,
    }
    (cell_dir / "scores_target_window3_v2.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def run(args):
    global CONDITIONS
    if args.conditions:
        CONDITIONS = [c.strip() for c in args.conditions.split(",") if c.strip()]
        print(f">> conditions ({len(CONDITIONS)}): {CONDITIONS}")
    root = Path(args.root)
    if not args.skip_promote and not args.rejudge_open and not args.report_only:
        promote(root)
    active = set(json.loads(
        (Path(args.root).parent / "datasets" / "mcq" / "mcq_rewrites.json").read_text(encoding="utf-8")
    ))
    active_stems = {item_stem(item_id) for item_id in active}
    only_items = parse_only_items(args.only_items)
    if only_items is not None:
        print(f">> --only-items: restricting to {len(only_items)} item(s)")
        unknown = only_items - active_stems
        if unknown:
            # Loud, not silent: an id that is not in mcq_rewrites.json would be
            # filtered out by active_stems anyway, so the run would quietly
            # answer fewer items than asked for.
            print(f"   [warn] {len(unknown)} requested id(s) are not in "
                  f"mcq_rewrites.json and will be skipped: {sorted(unknown)[:5]}")
    models = dict(p.split("=", 1) for p in args.models.split(",")) if args.models else MODEL_MAP
    client = None if args.report_only else build_client(args.provider)
    judge_client = None if args.report_only else build_client(args.open_judge_provider)

    # results[model_dir][condition][item_id] = correct(bool)
    # CLEAN is always keyed (even when --conditions excludes it) so the clean-referenced
    # QC blocks degrade to "no data" instead of raising.
    slots = list(dict.fromkeys(list(CONDITIONS) + [CLEAN]))
    results = {m: {c: {} for c in slots} for m in models}
    open_results = {m: {c: {} for c in slots} for m in models}

    def answer_cell(model_dir, ollama, ch, cond):
        # QA + passage are model-independent and live ONLY under the pseudonymized (qa) model dir.
        src = root / cell_dir_name(ch, args.cell_pattern) / args.qa_model_dir / cond
        qf = pick(src, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
        pf = pick(src, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt")
        if not qf or not pf:
            return cond, {}, {}
        passage = pf.read_text(encoding="utf-8")
        recs = [
            record
            for record in json.loads(qf.read_text(encoding="utf-8"))
            if item_stem(record.get("passage_id")) in active_stems
            and (only_items is None
                 or item_stem(record.get("passage_id")) in only_items)
            and record.get("q_type") in args.formats
            and not (record.get("q_type") == "open"
                     and item_stem(record.get("passage_id")) in EXCLUDED_OPEN_STEMS)
        ]
        new_by_id, open_by_id = {}, {}
        for record in recs:
            ctx = (
                passage
                if args.whole_passage
                else randomized_three_verse_window(passage, record)
            )
            if record.get("q_type") == "mcq":
                selected = ask_letter(client, ollama, record["Q"], record["A"], ctx)
                new_by_id[record["passage_id"]] = {
                    "correct": record["correct"],
                    "selected": selected,
                }
            else:
                generated = ask_open(client, ollama, record["Q"], ctx)
                score = judge_open(
                    judge_client,
                    args.open_judge_model,
                    record["Q"],
                    str(record.get("A") or ""),
                    generated,
                    ctx,
                )
                open_by_id[record["passage_id"]] = {
                    "expected": str(record.get("A") or ""),
                    "generated": generated,
                    "score": score,
                }
        if args.update_scores:
            cell_dir = root / cell_dir_name(ch, args.cell_pattern) / model_dir / cond
            write_mcq_scores(cell_dir, new_by_id)
            write_combined_scores(cell_dir, new_by_id, open_by_id)
        return (
            cond,
            {iid: value["correct"] == value["selected"] for iid, value in new_by_id.items()},
            {iid: value["score"] for iid, value in open_by_id.items()},
        )

    def rejudge_cell(model_dir, _ollama, ch, cond):
        # Re-score EXISTING open answers only. Reuses the stored generated_answer; reconstructs
        # the question + expected + the same 3-verse window and re-judges with judge_client.
        src = root / cell_dir_name(ch, args.cell_pattern) / args.qa_model_dir / cond
        qf = pick(src, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
        pf = pick(src, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt")
        scores_path = root / cell_dir_name(ch, args.cell_pattern) / model_dir / cond / "scores_target_window3_v2.json"
        if not (qf and pf and scores_path.exists()):
            return cond, {}, {}
        passage = pf.read_text(encoding="utf-8")
        recs = {r["passage_id"]: r for r in json.loads(qf.read_text(encoding="utf-8"))
                if item_stem(r.get("passage_id")) in active_stems
                and (only_items is None
                     or item_stem(r.get("passage_id")) in only_items)}
        data = json.loads(scores_path.read_text(encoding="utf-8"))
        mcq_res, open_res = {}, {}
        for it in data.get("items", []):
            if it.get("q_type") == "mcq":
                mcq_res[it["id"]] = bool(it.get("direct_correct"))
                continue
            if item_stem(it["id"]) in EXCLUDED_OPEN_STEMS:
                continue
            rec = recs.get(it["id"])
            if not rec:
                continue
            ctx = passage if args.whole_passage else randomized_three_verse_window(passage, rec)
            it["llm_score"] = judge_open(judge_client, args.open_judge_model, rec["Q"],
                                         str(rec.get("A") or ""), it.get("generated_answer", ""), ctx)
            open_res[it["id"]] = it["llm_score"]
        opens = [i for i in data.get("items", []) if i.get("q_type") != "mcq"]
        data.setdefault("summary", {})["open_llm_score_mean"] = (
            sum(i["llm_score"] for i in opens) / len(opens) if opens else 0.0)
        scores_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return cond, mcq_res, open_res

    def report_cell(model_dir, _ollama, ch, cond):
        # No model calls: just read the existing scores from disk to rebuild the reports.
        sp = root / cell_dir_name(ch, args.cell_pattern) / model_dir / cond / "scores_target_window3_v2.json"
        if not sp.exists():
            return cond, {}, {}
        data = json.loads(sp.read_text(encoding="utf-8"))
        mcq_res, open_res = {}, {}
        for it in data.get("items", []):
            if it.get("q_type") == "mcq":
                mcq_res[it["id"]] = bool(it.get("direct_correct"))
            elif item_stem(it["id"]) not in EXCLUDED_OPEN_STEMS:
                open_res[it["id"]] = it.get("llm_score")
        return cond, mcq_res, open_res

    cell_fn = (report_cell if args.report_only
               else rejudge_cell if args.rejudge_open else answer_cell)
    verb = ("reading scores (report-only)" if args.report_only
            else "re-judging open" if args.rejudge_open else "answering")
    for model_dir, ollama in models.items():
        print(f"\n== {verb}: {model_dir} ({ollama}) ==")
        jobs = [(ch, c) for ch in args.chapters for c in CONDITIONS]
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(cell_fn, model_dir, ollama, ch, c): (ch, c) for ch, c in jobs}
            for i, f in enumerate(as_completed(futs), 1):
                cond, res, open_res = f.result()
                results[model_dir][cond].update(res)
                open_results[model_dir][cond].update(open_res)
                if i % 10 == 0:
                    print(f"   ...{i}/{len(jobs)} cells")

    # ---------------- QC ----------------
    out = root / "reports" / "mcq_regen_qc"; out.mkdir(parents=True, exist_ok=True)
    all_ids = sorted(active)

    # per-item clean accuracy across models
    per_item = []
    for iid in all_ids:
        vals = [results[m][CLEAN].get(iid) for m in models if iid in results[m][CLEAN]]
        acc = sum(vals) / len(vals) if vals else None
        per_item.append({"id": iid, "clean_acc": acc, "n_models": len(vals)})
    with (out / "per_item_clean.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["id", "clean_acc", "n_models"])
        for r in sorted(per_item, key=lambda x: (x["clean_acc"] is None, x["clean_acc"] or 0)):
            w.writerow([r["id"], "" if r["clean_acc"] is None else f'{r["clean_acc"]:.2f}', r["n_models"]])

    open_ids = sorted({item_id for model in models for item_id in open_results[model][CLEAN]})
    open_per_item = []
    for item_id in open_ids:
        values = [
            open_results[model][CLEAN][item_id]
            for model in models
            if item_id in open_results[model][CLEAN]
        ]
        open_per_item.append({
            "id": item_id,
            "clean_score": sum(values) / len(values) if values else None,
            "n_models": len(values),
        })
    with (out / "per_item_open_clean.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "clean_score", "n_models"])
        for row in sorted(open_per_item, key=lambda value: value["clean_score"] or 0):
            writer.writerow([
                row["id"],
                "" if row["clean_score"] is None else f'{row["clean_score"]:.2f}',
                row["n_models"],
            ])

    def cond_acc(m, c):
        v = list(results[m][c].values())
        return sum(v) / len(v) if v else None

    def open_cond_score(model, condition):
        values = list(open_results[model][condition].values())
        return sum(values) / len(values) if values else None

    def spearman(xs, ys):
        def rank(a):
            order = sorted(range(len(a)), key=lambda i: a[i]); r = [0]*len(a)
            for pos, i in enumerate(order): r[i] = pos
            return r
        rx, ry = rank(xs), rank(ys); n = len(xs)
        d2 = sum((rx[i]-ry[i])**2 for i in range(n))
        return 1 - 6*d2/(n*(n*n-1)) if n > 1 else None

    dose = {}
    with (out / "dose_response.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["model"] + CONDITIONS)
        for m in models:
            row = [m] + [f'{cond_acc(m,c):.3f}' if cond_acc(m,c) is not None else "" for c in CONDITIONS]
            w.writerow(row)
            # Dose ladders are derived from the conditions actually selected, so a
            # {0,15,30} design reports as readily as the legacy {0,10,20,30} one.
            entry = {}
            for family in ("omission", "mistranslation"):
                levels = sorted(
                    int(c.split("/")[1].rstrip("%")) for c in CONDITIONS
                    if c.startswith(family + "/") and c.split("/")[1].endswith("%"))
                # the clean anchor is omission/0%; it doubles as the 0-dose for every family
                if 0 not in levels and CLEAN in CONDITIONS:
                    levels = [0] + levels
                acc = [cond_acc(m, CLEAN) if p == 0 else cond_acc(m, f"{family}/{p}%")
                       for p in levels]
                if not any(a is not None for a in acc):
                    continue
                entry[f"{family}_levels"] = levels
                entry[f"{family}_acc"] = [round(x, 3) if x is not None else None for x in acc]
                if len(levels) > 1:
                    entry[f"{family}_spearman_dose_vs_acc"] = round(
                        spearman(levels, [x or 0 for x in acc]), 3)
                base = cond_acc(m, CLEAN)
                if base is not None:
                    entry[f"{family}_drop_vs_clean"] = {
                        f"{p}%": round(base - (cond_acc(m, f'{family}/{p}%') or 0), 3)
                        for p in levels if p != 0
                        and cond_acc(m, f"{family}/{p}%") is not None}
            for label, cond in (("grammar30", "grammar/30%"), ("wbw", "google_word_by_word")):
                if cond in CONDITIONS and cond_acc(m, cond) is not None:
                    entry[f"{label}_drop_vs_clean"] = round(
                        (cond_acc(m, CLEAN) or 0) - cond_acc(m, cond), 3)
            dose[m] = entry

    with (out / "dose_response_by_type.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["model", "q_type"] + CONDITIONS)
        for model in models:
            for q_type, getter in (("mcq", cond_acc), ("open", open_cond_score)):
                values = [getter(model, condition) for condition in CONDITIONS]
                writer.writerow([
                    model,
                    q_type,
                    *["" if value is None else f"{value:.3f}" for value in values],
                ])

    broken = {
        "low_clean_acc(<%.2f)" % args.broken_threshold:
            [r["id"] for r in per_item if r["clean_acc"] is not None and r["clean_acc"] < args.broken_threshold],
        "inverted(any defect > clean by >=0.34 for a model)": sorted({
            iid for m in models for c in CONDITIONS if c != CLEAN
            for iid in results[m][c]
            if results[m][c].get(iid) and not results[m][CLEAN].get(iid, True)
            and (cond_acc(m, c) or 0) - (cond_acc(m, CLEAN) or 0) >= 0.34}),
    }
    open_clean_values = [
        row["clean_score"] for row in open_per_item if row["clean_score"] is not None
    ]
    summary = {"models": models, "conditions": CONDITIONS, "n_active_items_per_type": len(active),
               "window": "deterministic_randomized_three_verse",
               "formats": sorted(args.formats),
               "dose_response": dose, "broken_flags": broken,
               "clean_accuracy_mean": round(sum(r["clean_acc"] for r in per_item if r["clean_acc"] is not None)
                                            / max(1, sum(1 for r in per_item if r["clean_acc"] is not None)), 3),
               "open_clean_score_mean": round(sum(open_clean_values) / len(open_clean_values), 3)
                                        if open_clean_values else None}
    (out / "qc_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== QC SUMMARY ==="); print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nwrote {out}/qc_report.json and MCQ/open QC CSVs")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="evaluation/outputs")
    ap.add_argument("--chapters", nargs="+", default=list(range(1, 9)),
                    help="cell ids: Luke chapter numbers, or tier-1 passage ids "
                         "like t1_judg9 (use with --cell-pattern)")
    ap.add_argument("--cell-pattern", default="luke{cell}",
                    help="directory name per cell under --root. Default 'luke{cell}'; "
                         "use 'tier1/{cell}' for the tier-1 grid")
    ap.add_argument("--only-items",
                    help="restrict answering/judging to these content_ids: a comma "
                         "list, or @path.json (accepts tier1_gold_72_missing.json). "
                         "Matched on the stem, so -open/-mcq suffixes are fine")
    ap.add_argument("--models", help='comma list "dir=ollama_model"; default the 3-tier ladder')
    ap.add_argument("--qa-model-dir", default="1.7b",
                    help="dir holding the pseudonymized qa_target/passage (shared by all models)")
    ap.add_argument("--formats", choices=("both", "open", "mcq"), default="both",
                    help="question formats to evaluate; default: both")
    ap.add_argument("--whole-passage", action="store_true",
                    help="use the whole passage instead of deployment's randomized "
                         "three-verse window")
    # [CHANGED 2026-07-27] Default judge is now gpt-4o-mini over the OpenAI API. Open answers
    # are the pilot's PRIMARY channel (HUMAN_PILOT_DESIGN_2026-07-27 §5), so the judge must be
    # independent of the answer tiers rather than qwen3:1.7b, which also sits in the answer
    # ladder. Requires OPENAI_API_KEY. Pass --open-judge-provider ollama --open-judge-model
    # qwen3:1.7b to reproduce pre-07-27 runs exactly.
    ap.add_argument("--open-judge-model", default="gpt-4o-mini",
                    help="fixed model used to judge open answers so scores are comparable "
                         "across answer tiers; default: gpt-4o-mini (OpenAI)")
    ap.add_argument("--open-judge-provider", default="openai", choices=["ollama", "openai"],
                    help="backend for the open-answer judge; default openai (needs "
                         "OPENAI_API_KEY). Use --open-judge-provider ollama "
                         "--open-judge-model qwen3:1.7b for the pre-2026-07-27 local judge")
    ap.add_argument("--rejudge-open", action="store_true",
                    help="re-judge EXISTING open answers only: no promote, no re-answering. "
                         "Reads each scores_target_window3_v2.json, re-scores its open items "
                         "with the judge, rewrites the file, and regenerates the QC reports.")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild the QC reports from existing scores on disk: no promote, no "
                         "answering, no judging, no model calls. Reads all --models' "
                         "scores_target_window3_v2.json (e.g. re-run 1.7b alone, then this to "
                         "refresh the full 3-model report without touching 1.5b/1b).")
    ap.add_argument("--conditions",
                    help="comma list of condition dirs to run, overriding the default 7 "
                         "(e.g. 'omission/15%%,mistranslation/15%%,mistranslation/30%%'). "
                         "Omit for the committed default set. Cells outside the list are "
                         "neither answered nor read, so their scores are untouched.")
    ap.add_argument("--provider", default="ollama", choices=["ollama", "openai"])
    ap.add_argument("--skip-promote", action="store_true", help="assume rewrites already promoted")
    ap.add_argument("--update-scores", action="store_true", default=True)
    ap.add_argument("--no-update-scores", dest="update_scores", action="store_false")
    ap.add_argument("--broken-threshold", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    args.formats = {"open", "mcq"} if args.formats == "both" else {args.formats}
    return args


if __name__ == "__main__":
    run(parse_args())
