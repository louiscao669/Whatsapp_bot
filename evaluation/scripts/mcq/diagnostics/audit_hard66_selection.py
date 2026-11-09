"""Blindly replay the source English questions from the historical 85-to-66 selection."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics.audit_hard66_answerability import atomic_write, read


def load_pool(archive: Path):
    parent = archive / "tier1_hard_v3"
    selection = archive / "tier1_strong66"
    exported = read(parent / "tier1_strong_candidates.json")
    published = read(REPO / "evaluation/outputs/strong66_render_source.json")
    export_index = {(r["source_passage"], r["content_id"]): r for r in exported}
    public_index = {(r["source_passage"], r["source_content_id"]): r for r in published}
    if len(export_index) != len(exported) or len(public_index) != len(published):
        raise ValueError("Duplicate historical item IDs")
    items, separate_questions, selected_ids = [], [], set()
    for file in sorted(selection.glob("*.json")):
        full = read(parent / file.name)
        kept = {r["content_id"]: r for r in read(file)}
        separate_questions.extend(r["question"] for r in read(archive / "tier1_hard_bsb" / file.name))
        for r in full:
            key = file.stem, r["content_id"]
            if r["audit"]["passed"] is not True:
                raise ValueError(f"Candidate had failed the historical generator's checks: {key}")
            kept_item = kept.get(r["content_id"])
            bank_id = None
            if kept_item is not None:
                published_item = public_index[key]
                if (r != kept_item or export_index[key] != dict(r, source_passage=file.stem)
                        or (published_item["question"], published_item["answer"]) != (r["question"], r["answer"])):
                    raise ValueError(f"Source, selection or publication mismatch for {key}")
                bank_id = published_item["content_id"]
                selected_ids.add(key)
            window = r["window_text"]
            if sorted(map(int, window)) != r["window_verses"] or not all(v.strip() for v in window.values()):
                raise ValueError(f"Invalid original verse window for {key}")
            items.append(dict(id="/".join(key), passage=file.stem, source_id=r["content_id"],
                              published_id=bank_id, historical="retained" if kept_item else "removed",
                              question=r["question"], answer=r["answer"], window=window,
                              original_rank=r["final_rank"]))
    if (len(items) != len({i["id"] for i in items}) or len(items) != 85 or len(selected_ids) != 66
            or selected_ids != export_index.keys() or selected_ids != public_index.keys()
            or len(separate_questions) != 95):
        raise ValueError("Source counts or memberships do not match the archived selection")
    def normalize(s):
        return " ".join(s.casefold().split())

    overlap = {normalize(i["question"]) for i in items if i["historical"] == "retained"} & {
        normalize(q) for q in separate_questions}
    return items, len(overlap)


def passage_reference(item):
    book, chapter, _ = item["passage"].split("_", 2)
    books = {"1kgs": "1 Kings", "2kgs": "2 Kings", "2chr": "2 Chronicles",
             "2sam": "2 Samuel", "acts": "Acts", "judg": "Judges"}
    verses = sorted(map(int, item["window"]))
    span = str(verses[0]) if len(verses) == 1 else f"{verses[0]}–{verses[-1]}"
    return f"{books[book]} {chapter}:{span}"


def review(report):
    rows = report["items"]
    lines = ["# Hard QA selection and clean-window answerability", "",
             "The historical English pool contains 85 questions across 12 source passages. "
             "Every one of the 66 selected records matches its parent record, the selection export, "
             "and the published source question and key. The 19 others were removed. "
             f"The separate 95-item BSB run shares {report['hard95_shared_questions']} exact normalized "
             "question texts with the 66. The selection files establish membership. They do not identify the curator or reasons for individual removals.", "",
             f"The {report['model']} reader received one original question and its original clean English "
             "window. A second call compared the supported readings to the original answer key. "
             "Historical decisions, scores, rankings, competing answers and the authors’ rationales "
             "were withheld from both calls. This is a report-only answerability check.", "",
             "| Historical selection | Model passed | Model flagged | Unchecked |",
             "|---|---:|---:|---:|"]
    groups = {g: Counter(i["finding"]["status"] for i in rows if i["historical"] == g)
              for g in ("retained", "removed")}
    for group, ct in groups.items():
        lines.append(f"| {group.title()} | {ct['passed']} | {ct['flagged']} | {ct['unchecked']} |")
    agree = groups["retained"]["passed"] + groups["removed"]["flagged"]
    checked = sum(c["passed"] + c["flagged"] for c in groups.values())
    if checked:
        lines += ["", f"Treating a model pass as a keep, the decisions agree on {agree}/{checked} "
                  f"checked questions ({agree/checked:.1%}). The comparison measures agreement with "
                  "the historical selection. A clear question can still be too easy or incidental for the study.", ""]
        for label, counts in groups.items():
            n = counts["passed"] + counts["flagged"]
            if n:
                lines.append(f"- The check flagged {counts['flagged']}/{n} checked {label} questions "
                             f"({counts['flagged']/n:.1%}).")
    archive = Path(report["source"])
    lines += ["", "The parent directory holds the 12 per-passage candidate files and the combined "
              "66-item selection export. The final per-passage files preserve the complete original "
              "records. The historical generator marked all 85 as passing its then-current checks, "
              "including the 19 later removed. "
              f"[Parent and selection export](<{archive}/tier1_hard_v3/tier1_strong_candidates.json>) · "
              f"[Separate 95-question run](<{archive}/tier1_hard_bsb>)"]
    for title, candidates in [
        ("All 19 historical removals", [r for r in rows if r["historical"] == "removed"]),
        ("Retained questions flagged or unchecked", [r for r in rows if r["historical"] == "retained"
                                                      and r["finding"]["status"] != "passed"]),
    ]:
        lines += ["", f"## {title}", "", "| Original item | Question and key | Model finding |",
                  "|---|---|---|"]
        for r in candidates:
            f = r["finding"]
            rationale = f["reason"]
            if f["status"] == "flagged":
                readings = " / ".join(a["answer"] for a in f.get("readings", []))
                if readings:
                    rationale = f"Blind answers: {readings}. {rationale}"
            cells = [passage_reference(r), f"{r['question']} → {r['answer']}",
                     f"**{f['verdict'].replace('_', ' ')}**. {rationale}"]
            lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    lines += ["", "The accompanying JSON contains every question, verse window, blind answer, "
              "supporting quotation and recorded verdict.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="Restored qa_generation/outputs directory")
    parser.add_argument("--generator-root", type=Path, required=True, help="Checkout containing the answerability check")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    sys.path.insert(0, str(args.generator_root.resolve()))
    from qa_generation.config import load_env
    load_env()
    from qa_generation.prompts.hard_qa import format_window
    from qa_generation.services import answerability

    items, overlap = load_pool(args.archive)
    judge = answerability.AnswerabilityCheck("report-only", args.model)
    signature = json.dumps([args.model, items, str(answerability.enumerate_readings_prompt),
                            inspect.getsource(answerability), inspect.getsource(format_window)],
                           ensure_ascii=False, sort_keys=True)
    fingerprint = sha256(signature.encode()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "answerability.json"
    previous = read(path) if path.exists() else {"fingerprint": fingerprint, "items": []}
    if previous["fingerprint"] != fingerprint:
        raise ValueError("Inputs or check changed. Use a new output directory.")
    findings = {r["id"]: r["finding"] for r in previous["items"] if r["finding"]["status"] != "unchecked"}

    def report():
        return dict(mode="report-only", model=args.model, fingerprint=fingerprint,
                    source=str(args.archive.resolve()), hard95_shared_questions=overlap,
                    items=[dict(r, finding=findings[r["id"]]) for r in items if r["id"] in findings])

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        pending = {}
        for r in items:
            if r["id"] in findings:
                continue
            window = format_window({int(k): v for k, v in r["window"].items()})
            future = pool.submit(judge.assess, window, r["question"], r["answer"])
            pending[future] = r["id"]
        for future in as_completed(pending):
            key = pending[future]
            findings[key] = future.result()
            atomic_write(path, json.dumps(report(), ensure_ascii=False, indent=2) + "\n")
            print(f"{len(findings)}/{len(items)} {key} {findings[key]['status']}", flush=True)
    atomic_write(args.output_dir / "review.md", review(report()))
    return int(any(f["status"] == "unchecked" for f in findings.values()))


if __name__ == "__main__":
    raise SystemExit(main())
