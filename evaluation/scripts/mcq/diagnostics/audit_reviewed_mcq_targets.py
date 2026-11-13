"""Review the original English wording and options of every released MCQ by source ID."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv
from openai import OpenAI
from qa_generation.services.mcq_target import review_target, target_version


ROOT = Path(__file__).resolve().parents[4]


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    Path(f.name).replace(path)


def input_signature(row, model):
    return sha256(json.dumps([model, target_version(), row], sort_keys=True).encode()).hexdigest()


def verse_window(row):
    return "\n".join(f"[{n}] {v}" for n, v in row["verses"].items())


def repair_from_audit(args, rows):
    from qa_generation.services.window_mcq import WindowMCQWriter, MCQReviewError, check_saved_mcq
    flags = json.loads(args.repair_flagged.read_text())["questions"]
    by_id = {r["id"]: r for r in rows}
    if len(by_id) != len(rows) or len({f["id"] for f in flags}) != len(flags):
        raise ValueError("Duplicate IDs in bank or audit report.")
    for flag in flags:
        row = by_id[flag["id"]]
        if (flag["input_signature"] != input_signature(row, args.model) or flag["model"] != args.model
                or flag["version"] != target_version()
                or flag["verdict"] not in ("compound_stem", "both", "off_target_choices", "ungrounded_event", "review_grounding")):
            raise ValueError(f"Invalid or stale target finding for {row['id']}. Rerun the audit.")
    writer = WindowMCQWriter(args.writer, args.model)

    def rewrite(flag):
        row = by_id[flag["id"]]
        if flag["verdict"] in ("ungrounded_event", "review_grounding"):
            return {"id": row["id"], "status": "retired" if flag["verdict"] == "ungrounded_event" else "withheld",
                    "stage": "stem grounding", "source_signature": flag["input_signature"], "reason": flag["reason"]}
        key = row["correct"]
        answer = row["choices"]["ABCD".index(key)]
        inputs = (row["question"], answer, verse_window(row), row["id"])
        finding = {k: flag[k] for k in ("target", "verdict", "reason", "model", "version")}
        try:
            if finding["verdict"] == "off_target_choices":
                block = writer.generate(*inputs, fixed_key=key)
            else:
                block = writer.repair_flagged_target(*inputs, finding, fixed_key=key)
        except MCQReviewError as exc:
            return {"id": row["id"], "status": "withheld", "stage": exc.stage, "reason": str(exc),
                    "repair": exc.repair, "answerability": exc.answerability}
        if block["correct"] != key:
            raise ValueError(f"Answer position changed for {row['id']}")
        revised = {**row, "question": block["mcq_stem"], "choices": block["mcq_options"] + row["choices"][4:]}
        target_repair = block["review"].get("target_repair")
        intended_answer = target_repair["proposal"]["answer"].strip() if target_repair else answer
        problems = check_saved_mcq(dict(question=revised["question"], answer=intended_answer, mcq=block))
        if problems:
            raise ValueError(f"{row['id']}: {problems}")
        return {"id": row["id"], "status": "accepted", "source_signature": flag["input_signature"],
                "original_question": row["question"], "original_answer": answer,
                "candidate": revised, "review": block["review"]}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(rewrite, flags))
    save(args.output / "repairs.json", results)
    for result in results:
        print(result["id"], result["status"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=ROOT / "evaluation/datasets/qa/reviewed122")
    parser.add_argument("--output", required=True, type=Path, help="Run directory for resumable review evidence.")
    parser.add_argument("--report", type=Path, help="Destination for the flagged-question report.")
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--repair-flagged", type=Path, help="Rewrite flagged items from a saved audit into the run directory.")
    parser.add_argument("--writer", default="gpt-6.1-sol", help="Writer for --repair-flagged.")
    parser.add_argument("--workers", default=8, type=int)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    rows = json.loads((args.bank / "english.json").read_text())
    if args.repair_flagged:
        repair_from_audit(args, rows)
        return
    client = OpenAI(timeout=120, max_retries=3)
    dispositions = {r["id"]: r["status"] for r in json.loads((args.bank / "pilot_review.json").read_text())}
    if len(rows) != len(dispositions) or {r["id"] for r in rows} != dispositions.keys():
        raise ValueError("Question roster and pilot dispositions differ")

    def check(r):
        signature = input_signature(r, args.model)
        path = args.output / "checks" / (signature + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            options = dict(zip("ABCD", r["choices"][:4], strict=True))
            window = verse_window(r)
            result = review_target(client, args.model, r["question"], window, options)
            save(path, result)
        return {"id": r["id"], "source": r["source"], "reference": r["reference"],
                "pilot_status": dispositions[r["id"]], "question": r["question"],
                "choices": r["choices"], "correct": r["correct"], "input_signature": signature, **result}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(check, rows))
    save(args.output / "audit.json", results)
    chinese = {r["id"]: r for r in json.loads((args.bank / "zh.json").read_text())}
    flags = [{**r, "published_chinese_question": chinese[r["id"]]["question"]}
             for r in results if r["verdict"] != "pass"]
    save(args.report or args.output / "flagged.json", {
        "model": args.model, "review_language": "English", "checked": len(results),
        "checked_by_pilot_status": dict(Counter(r["pilot_status"] for r in results)),
        "flagged": len(flags), "questions": flags,
    })
    counts = Counter((r["pilot_status"], r["source"], r["verdict"]) for r in results)
    for group, n in sorted(counts.items()):
        print(*group, n)


if __name__ == "__main__":
    main()
