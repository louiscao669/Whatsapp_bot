"""Replay the clean Hard66 windows through the generator's report-only check."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

REPO = Path(__file__).resolve().parents[4]
RUN = REPO / "evaluation/runs/hard66_small_models_variants_2026-10-28"
CANONICAL = REPO / "evaluation/datasets/qa/tier1_hard66_canonical"
sys.path.insert(0, str(REPO))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_items():
    from evaluation.agents.generate_chinese_answers import chapters_from_reference, index_passage_verses
    from evaluation.scripts.campaigns.current.run_hard66_full_ladder import item_window

    manifest = read(RUN / "manifest.json")
    items = {}
    for item in manifest["items"]:
        identifier = item["id"]
        if identifier in items or item["expected"] != item["choices"][item["correct"]]:
            raise ValueError(f"duplicate ID or inconsistent key: {identifier}")
        items[identifier] = dict(id=identifier, reference=item["reference"], verses=item["curated_window"],
                                 question=item["question"], answer=item["expected"], cohort="active",
                                 window=item["private_clean_passage"], clean_mcq={})
    for path in sorted((RUN / "scores").glob("*_clean/*.json")):
        model = path.parent.name.removesuffix("_clean")
        response = read(RUN / "answers" / path.parent.name / path.name)
        outcomes = items[response["id"]]["clean_mcq"]
        if model in outcomes:
            raise ValueError(f"duplicate clean response: {response['id']} / {model}")
        outcomes[model] = read(path)["label"]
    if any(len(item["clean_mcq"]) != 3 for item in items.values()):
        raise ValueError("incomplete clean MCQ comparison")

    # Recover the source window for the one question excluded before data collection.
    originals = [row for path in sorted(CANONICAL.glob("*.json"))
                 for row in read(path) if row["q_type"] == "mcq"]
    for row in originals:
        if row["status"] != "exclude":
            continue
        pid = row["passage_id"].removeprefix("uw-").split(":")[0]
        source = next(i for i in manifest["items"] if i["pid"] == pid)
        passage = Path(source["passage_source"]).read_text(encoding="utf-8")
        index, order = index_passage_verses(passage, chapters_from_reference(row["passage_reference"]))
        keys = item_window(row, order)
        identifier = row["passage_id"]
        if identifier in items:
            raise ValueError(f"excluded item also present in active manifest: {identifier}")
        items[identifier] = dict(id=identifier, reference=row["passage_reference"],
                                 verses=[f"{c}:{v}" for c, v in keys], question=row["Q"],
                                 answer=row["A"][row["correct"]], cohort="previously excluded",
                                 window="\n".join(index[k] for k in keys), clean_mcq={})
    if len(items) != 66 or set(items) != {row["passage_id"] for row in originals}:
        raise ValueError("Hard66 audit must cover the 66 distinct canonical IDs")
    return list(items.values())


def atomic_write(path, content):
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        temp.write(content)
    Path(temp.name).replace(path)


def markdown(report):
    rows = report["items"]
    lines = ["# Hard66 clean-passage answerability", "",
             f"Report-only run with {report['model']}. The blind reader saw one Chinese question and its clean Chinese verse window. The second call compared the readings with the Chinese keyed answer. Choices, prior review and historical scores were withheld from the reader.", "",
             "| Set | Passed | Flagged | Unchecked |", "|---|---:|---:|---:|"]
    for cohort in ("active", "previously excluded"):
        counts = Counter(r["finding"]["status"] for r in rows if r["cohort"] == cohort)
        lines.append(f"| {cohort.capitalize()} | {counts['passed']} | {counts['flagged']} | {counts['unchecked']} |")
    lines += ["", "## Comparison with earlier clean MCQ results", "",
              "Each active question has one response each from Gemma 3 4B, Phi-4 Mini 3.8B and Qwen 2.5 3B. Percentages measure model agreement with the MCQ key. Human accuracy was not measured.", ""]
    for status in ("flagged", "passed"):
        outcomes = [v for row in rows if row["cohort"] == "active" and row["finding"]["status"] == status
                    for v in row["clean_mcq"].values()]
        if outcomes:
            correct = outcomes.count("correct")
            lines.append(f"- {status.capitalize()} questions had {correct}/{len(outcomes)} correct responses ({correct/len(outcomes):.1%}).")
    misses = [r for r in rows if r["clean_mcq"] and "correct" not in r["clean_mcq"].values()]
    if misses:
        lines += ["", "### Questions missed by all three models on clean text", ""]
        for row in misses:
            lines += [f"- **{row['id']}** ({', '.join(row['verses'])}) — {row['question']} "
                      f"Key: {row['answer']}. Answerability: {row['finding']['verdict']}. "
                      f"{row['finding']['reason']}"]
    for cohort in ("active", "previously excluded"):
        lines += ["", f"## {cohort.capitalize()} questions for review", ""]
        if not any(r["cohort"] == cohort and r["finding"]["status"] != "passed" for r in rows):
            lines.append("The check flagged no questions in this set.")
        for row in rows:
            finding = row["finding"]
            if row["cohort"] != cohort or (finding["status"] == "passed" and cohort == "active"):
                continue
            lines += [f"### {row['id']} · {', '.join(row['verses'])}", "",
                      f"**{row['question']}**", "", f"Key — {row['answer']}", "",
                      f"**{finding['verdict'].replace('_', ' ').capitalize()}** — {finding['reason']}", ""]
            assessments = {v["number"]: v for v in finding.get("assessments", [])}
            for i, reading in enumerate(finding.get("readings", []), 1):
                note = assessments.get(i, {}).get("reason", "")
                lines.append(f"- {reading['answer']} — “{reading['support']}” {note}")
            lines += ["", *[f"> {line}" for line in row["window"].splitlines()], ""]
    return "\n".join(lines).rstrip()+"\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator-root", type=Path, help="v3/combo checkout if qa_generation is not installed")
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--regrade-from", type=Path, help="Reuse earlier blind answers with matching reader, ID, question and window")
    args = parser.parse_args()
    if args.generator_root:
        sys.path.insert(0, str(args.generator_root.resolve()))
    from qa_generation.config import load_env
    load_env()
    from qa_generation.services.answerability import AnswerabilityCheck, decision_prompt, enumerate_readings_prompt

    items = load_items()
    judge = AnswerabilityCheck("report-only", args.model)
    source = Path(sys.modules[AnswerabilityCheck.__module__].__file__).read_bytes()
    reader_signature = str(enumerate_readings_prompt) + inspect.getsource(AnswerabilityCheck.read) + args.model
    reader_digest = sha256(reader_signature.encode()).hexdigest()
    digest = sha256(source + str(enumerate_readings_prompt).encode() + str(decision_prompt).encode()
                    + json.dumps([args.model, items], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "answerability.json"
    saved = read(path) if path.exists() else {"fingerprint": digest, "items": []}
    prior = {}
    if args.regrade_from:
        previous = read(args.regrade_from)
        if previous.get("reader_fingerprint") != reader_digest:
            raise ValueError("reader signature differs; cannot reuse blind answers")
        prior = {r["id"]: r for r in previous["items"]}
    if saved["fingerprint"] != digest and not args.regrade_from:
        raise ValueError("inputs, judge or prompts changed; choose a fresh output directory")
    findings = {r["id"]: r["finding"] for r in saved["items"]
                if saved["fingerprint"] == digest and r["finding"]["status"] != "unchecked"}

    def assess(row):
        prior_row = prior.get(row["id"], {})
        readings = None
        if (prior_row.get("question"), prior_row.get("window")) == (row["question"], row["window"]):
            readings = prior_row["finding"].get("readings")
        return judge.assess(row["window"], row["question"], row["answer"], readings=readings)

    def snapshot():
        return dict(mode="report-only", model=args.model, fingerprint=digest, reader_fingerprint=reader_digest,
                    manifest=str(RUN / "manifest.json"),
                    items=[dict(row, finding=findings[row["id"]]) for row in items if row["id"] in findings])

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        pending = {pool.submit(assess, r): r["id"]
                   for r in items if r["id"] not in findings}
        for future in as_completed(pending):
            identifier = pending[future]
            findings[identifier] = future.result()
            atomic_write(path, json.dumps(snapshot(), indent=2, ensure_ascii=False)+"\n")
            print(f"{len(findings)}/{len(items)} {identifier} {findings[identifier]['status']}", flush=True)
    report = snapshot()
    atomic_write(args.output_dir / "review.md", markdown(report))
    return 1 if any(f["status"] == "unchecked" for f in findings.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
