"""Write and automatically review English source distractors for Gold72 and Hard66."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from itertools import repeat
from pathlib import Path
from tempfile import TemporaryDirectory

from evaluation.agents.generate_chinese_answers import (
    chapters_from_reference, curated_window_for_item, index_passage_verses, load_verse_windows,
)
from evaluation.scripts.analysis.current.check_full_conditions_5opt import PASSAGES
from evaluation.scripts.campaigns.current.run_hard66_full_ladder import item_window

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "evaluation/datasets"
WINDOWS = REPO / "QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json"


@dataclass
class Item:
    dataset: str
    file: str
    identifier: str
    row: dict
    question: str
    answer: str
    key: str | None
    extras: list[str]
    window: str
    verses: list[str]


def load_items(dataset, *, source_json=None, windows_path=WINDOWS, passage_dir=None):
    gold = dataset == "gold72"
    source = DATA / ("qa/tier1_gold72_canonical_5opt" if gold else "pseudonymized/qa/tier1_strong")
    passage_dir = passage_dir or DATA / ("passages/tier1_bsb" if gold else "pseudonymized/passages/tier1_bsb")
    windows = load_verse_windows(windows_path) if gold else {}
    paths = [source_json] if source_json else [source / f"{pid}_all_formats.json" for pid in PASSAGES]
    passages = {}
    for path in paths:
        for row in json.loads(path.read_text(encoding="utf-8")):
            if (row.get("status") == "exclude" or row.get("force_form") == "open"
                    or (row.get("audit") or {}).get("passed") is False):
                continue
            cid = row["content_id"]
            mcq = row.get("mcq")
            key, extras = None, []
            if mcq is not None:
                match = re.search(r"<answer>([A-D])<answer>", mcq["content"])
                if not match or mcq.get("correct", match[1]) != match[1]:
                    raise ValueError(f"{cid}: missing or inconsistent A–D key")
                key, options = match[1], mcq["mcq_options"]
                if not 4 <= len(options) <= 6 or not all(isinstance(v, str) and v.strip() for v in options):
                    raise ValueError(f"{cid}: invalid choice list")
                question, answer, extras = mcq["mcq_stem"], options["ABCD".index(key)], options[4:]
            elif source_json and row.get("window_text"):
                question, answer = row["question"], row["answer"]
            else:
                raise ValueError(f"{cid}: missing English MCQ")

            if row.get("window_text"):
                verse_map = {int(v): t for v, t in row["window_text"].items()}
                verse_ids = [int(v) for v in row.get("window_verses", sorted(verse_map))]
                if not verse_ids or any(not verse_map[v].strip() for v in verse_ids):
                    raise ValueError(f"{cid}: empty verse in the source window")
                window = "\n".join(f"{v}  {verse_map[v]}" for v in verse_ids)
                labels = [str(v) for v in verse_ids]
            else:
                pid = row.get("passage_id") or cid.partition(":")[0]
                if pid not in passages:
                    passage = (passage_dir / PASSAGES[pid]).read_text(encoding="utf-8")
                    passages[pid] = index_passage_verses(passage, chapters_from_reference(row["passage_reference"]))
                index, order = passages[pid]
                keys = curated_window_for_item(windows, row) if gold else item_window(row, order)
                if not keys or any(k not in index for k in keys):
                    raise ValueError(f"{cid}: incomplete clean English window")
                window = "\n".join(index[k] for k in keys)
                labels = [f"{c}:{v}" for c, v in keys]
            yield Item(dataset, path.name, cid, row, question, answer, key, extras, window, labels)


def rewrite_item(item, writer):
    from qa_generation.services.window_mcq import MCQReviewError
    audit = {"dataset": item.dataset, "id": item.identifier, "window_verses": item.verses}
    previous = item.row.get("answerability") or {}
    saved_ambiguity = (item.row.get("stage") == "source answerability"
                       and previous.get("status") == "flagged" and previous.get("verdict") == "multiple_answers"
                       and previous.get("question") == item.question and item.row.get("answer") == item.answer)
    options_for_writer = {"fixed_key": item.key}
    if saved_ambiguity:
        options_for_writer["answerability"] = previous
    try:
        block = writer.generate(item.question, item.answer, item.window, item.identifier, **options_for_writer)
    except MCQReviewError as exc:
        if exc.repair:
            audit["question_repair"] = exc.repair
        return None, dict(audit, status="withheld", stage=exc.stage, reason=str(exc))
    key = block["correct"]
    options = block["mcq_options"] + item.extras
    if (item.key and key != item.key) or options["ABCD".index(key)] != item.answer:
        raise ValueError(f"{item.identifier}: key drift")
    body = "\n".join(f"{letter}. {v}" for letter, v in zip("ABCDEF", options))
    updated = deepcopy(item.row)
    if saved_ambiguity:
        updated.pop("stage")
        updated.pop("reason", None)
        updated["answerability"] = block["review"]["answerability"]
    stem = block["mcq_stem"]
    if "question_repair" in block["review"]:
        audit["question_repair"] = block["review"]["question_repair"]
        if (updated.get("question"), updated.get("answer")) == (item.question, item.answer):
            updated["question"] = stem
            if "answerability" in (updated.get("audit") or {}):
                updated["audit"]["answerability"] = block["review"]["answerability"]
        open_block = updated.get("open")
        if open_block and open_block.get("content") == f"<question>{item.question}\n<question><answer>{item.answer}<answer>":
            open_block["content"] = f"<question>{stem}\n<question><answer>{item.answer}<answer>"
    mcq = updated.setdefault("mcq", {})
    # In the prepared format original_question/original_answer can describe the open form.
    for field in ("question_type", "original_question", "original_answer"):
        mcq.setdefault(field, block[field])
    mcq.update(mcq_stem=stem, mcq_options=options, correct=key, review=block["review"],
               content=f"<question>{stem}\n\n{body}\n<question><answer>{key}<answer>")
    return updated, dict(audit, status="accepted", attempts=block["review"]["attempts"])


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    from qa_generation.config import load_env
    from qa_generation.services.window_mcq import WindowMCQWriter, add_mcq_model_arguments
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["both", "gold72", "hard66"], default="both")
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory for accepted English QA and audit.json.")
    parser.add_argument("--source-json", type=Path, help="Use a newly generated English source array for a single set.")
    parser.add_argument("--windows", type=Path, default=WINDOWS, help="Gold window map for prepared rows.")
    parser.add_argument("--passage-dir", type=Path, help="English passage files matching a custom source.")
    add_mcq_model_arguments(parser)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--item", action="append", help="Limit to this content ID; repeat for several.")
    args = parser.parse_args(argv)
    if args.output_dir.exists() or args.workers < 1:
        parser.error("Use a new output directory and at least one worker.")
    if args.dataset == "both" and (args.source_json or args.passage_dir):
        parser.error("Pick one dataset when supplying a custom source or passage directory.")
    datasets = ["gold72", "hard66"] if args.dataset == "both" else [args.dataset]
    requested = set(args.item or [])
    items = [i for dataset in datasets for i in load_items(dataset, source_json=args.source_json,
             windows_path=args.windows, passage_dir=args.passage_dir) if not requested or i.identifier in requested]
    if not items or requested - {i.identifier for i in items}:
        parser.error("No matching items or an unknown item ID.")
    if len({(i.dataset, i.identifier) for i in items}) != len(items):
        parser.error("Duplicate source IDs; run each passage separately for passage-local IDs.")
    writer = WindowMCQWriter(args.mcq_writer_model, args.mcq_judge_model)
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output_dir.parent) as temp:
        batch = Path(temp) / "batch"
        files = {}
        checks = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for item, (row, check) in zip(items, pool.map(rewrite_item, items, repeat(writer))):
                checks.append(check)
                rows = files.setdefault(batch / item.dataset / item.file, [])
                if row is not None:
                    rows.append(row)
                print(f"{item.dataset} {item.identifier}: {check['status']}", flush=True)
        for path, rows in files.items():
            write_json(path, rows)
        totals = Counter(check["status"] for check in checks)
        write_json(batch / "audit.json", {"language": "English", "writer": writer.model, "judge": writer.judge_model,
                                         "counts": totals, "items": checks})
        batch.rename(args.output_dir)
    print(f"{totals['accepted']} accepted, {totals['withheld']} withheld. Output: {args.output_dir}")
    return 0 if totals["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
