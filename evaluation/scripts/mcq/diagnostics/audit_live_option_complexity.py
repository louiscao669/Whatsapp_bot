"""Read-only complexity audit of the live Sol pilot and its matching English sources."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import sys

from dotenv import load_dotenv
from openai import OpenAI
from qa_generation.services.mcq_complexity import complexity_version, key_length_finding, review_complexity
from evaluation.scripts.mcq.diagnostics.audit_reviewed_mcq_targets import ROOT, save, verse_window


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_live():
    sys.path.insert(0, str(ROOT / "human_pilot"))
    import pilot_import_reviewed122 as pilot
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session
    from eten_shared.models import QAItem, ExperimentWindow, ExperimentPassage, ExperimentPassageVerse
    from eten_shared.experiment_plan import qa_set_groups

    zh = {r["id"]: r for r in pilot.load_bank(pilot.SOL_SET)}
    en = {r["id"]: r for r in json.loads((pilot.SOL_BANK / "english.json").read_text())}
    groups = qa_set_groups(pilot.SOL_SET)
    with Session(create_engine(pilot.get_database_url())) as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        slots = db.execute(select(ExperimentWindow, QAItem).join(QAItem).where(
            ExperimentWindow.group_index.in_(groups)).order_by(ExperimentWindow.sequence_index)).all()
        passage_ids = {q.passage_id for _, q in slots}
        verses = db.execute(select(ExperimentPassage.source_passage_id, ExperimentPassageVerse.verse_number,
                                   ExperimentPassageVerse.text).join(ExperimentPassageVerse).where(
            ExperimentPassage.source_passage_id.in_(passage_ids), ExperimentPassage.condition == "clean",
            ExperimentPassage.language == "zh")).all()
        clean = {(pid, n): v for pid, n, v in verses}
        if len(slots) != len(zh) or {w.content_id for w, _ in slots} != set(zh):
            raise ValueError("Live slots and eligible release IDs differ.")
        for w, q in slots:
            r = zh[w.content_id]
            src = en[w.content_id]
            if (r["choices"][4:] != [pilot.CANNOT_TELL] or src["choices"][4:] != ["I can't tell from this passage"]
                    or any(r[k] != src[k] for k in ("correct", "source", "passage_id", "reference"))
                    or list(src["verses"]) != list(r["verses"])
                    or (q.form_group_id, q.question_text, q.mcq_choices, q.mcq_correct_choice, q.expected_answer)
                    != (r["id"], r["question"], r["choices"], r["correct"], r["choices"]["ABCD".index(r["correct"])])
                    or q.passage_id != f"{pilot.SOL_SET}/{r['source']}/{r['passage_id']}"
                    or w.verse_numbers != list(r["verses"])
                    or any(clean.get((q.passage_id, n)) != v for n, v in r["verses"].items())):
                raise ValueError(f"Live question, source or clean passage differs for {w.content_id}")
    return [{"zh": r, "en": en[cid]} for cid, r in zh.items()]


def audit(run, model, client, item):
    key = item["correct"]
    choices = dict(zip("ABCD", item["choices"][:4], strict=True))
    answer = choices[key]
    distractors = {letter: text for letter, text in choices.items() if letter != key}
    output = {}
    for stage, options, context in (("key", {"key": answer}, None), ("distractors", distractors, answer)):
        signature = digest([complexity_version(), model, item["id"], item["question"], item["verses"],
                            stage, options, context])
        path = run / "checks" / f"{signature}.json"
        if path.exists():
            record = json.loads(path.read_text())
        else:
            record = review_complexity(client, model, item["question"], verse_window(item), options,
                                       correct_answer=context)
            save(path, record)
        findings = record["choices"]
        if (record["version"] != complexity_version() or record["model"] != model or set(findings) != set(options)
                or any(v["text"] != options[k] or v["verdict"] not in ("pass", "flag")
                       or (v["verdict"] == "flag" and (not v["excerpt"] or v["excerpt"] not in v["text"] or not v["reason"]))
                       for k, v in findings.items())):
            raise ValueError(f"Invalid complexity checkpoint for {item['id']}")
        for label, finding in findings.items():
            output[key if label == "key" else label] = finding
    length_finding = key_length_finding(choices, key)
    if length_finding:
        if output[key]["verdict"] == "flag":
            output[key] = {**output[key], "reason": f"{output[key]['reason']} {length_finding['reason']}"}
        else:
            output[key] = length_finding
    return output


def write_reports(entries, report, model):
    flagged = []
    for entry in entries:
        pair = entry["item"]
        row = pair["zh"]
        flags = {lang: {k: v for k, v in sorted(entry[lang].items()) if v["verdict"] == "flag"}
                 for lang in ("zh", "en")}
        if any(flags.values()):
            flagged.append({"id": row["id"], "source": row["source"], "reference": row["reference"],
                            "question": row["question"], "english_question": pair["en"]["question"],
                            "key": row["correct"], **flags})
    def group(r):
        return 0 if r["key"] in r["zh"] else 1 if r["zh"] else 2
    flagged.sort(key=lambda r: (group(r), -len(r["zh"]), -len(r["en"]), r["id"]))
    counts = Counter(group(r) for r in flagged)
    summary = {"items_checked": len(entries), "model": model, "rubric": complexity_version(),
               "chinese_key_flagged": counts[0], "chinese_distractors_only": counts[1],
               "english_only": counts[2], "either_language": len(flagged)}
    save(report / "flags.json", {"summary": summary, "questions": flagged})
    lines = ["# Answer-option complexity in the live Sol pilot", "",
             f"{model} reviewed {len(entries)} live questions against their clean passages in Chinese and English. "
             "The correct answer and distractors were reviewed for wording, then the length of the "
             "key was checked against the final A–D choices. "
             "The fixed E response was excluded.", "",
             f"**{counts[0] + counts[1]} Chinese questions flagged** · {counts[0]} with a flagged correct answer "
             f"and {counts[1]} with flags only on distractors. {counts[2]} additional items were flagged only in English.", "",
             "Items with a flagged Chinese key appear first. Within each section, items with more flagged Chinese "
             "choices appear first. Each excerpt is copied from the reviewed option.", "",
             "| Question | Correct letter | Chinese flags | English flags |",
             "| --- | --- | --- | --- |"]
    for r in flagged:
        lines.append(f"| {r['question']} | {r['key']} | {', '.join(r['zh']) or '—'} | "
                     f"{', '.join(r['en']) or '—'} |")
    lines.append("")
    for index, title in enumerate(("Chinese correct answer flagged", "Chinese distractors only", "English source only")):
        lines.extend([f"## {title} ({counts[index]})", ""])
        for r in (r for r in flagged if group(r) == index):
            lines.extend([f"### {r['question']}", "",
                          f"{r['reference']} · {r['source']} · `{r['id']}` · correct answer {r['key']}", ""])
            for lang, name in (("zh", "Chinese"), ("en", "English")):
                for letter, f in r[lang].items():
                    role = "correct answer" if letter == r["key"] else "distractor"
                    lines.append(f"- **{name} {letter} ({role})** “{f['excerpt']}” — {f['reason']}")
            lines.append("")
    (report / "flagged.md").write_text("\n".join(lines), encoding="utf-8")
    print(summary, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    items = load_live()
    save(args.run / "snapshot.json", {"digest": digest(items), "items": items})
    print(f"Verified {len(items)} live items. Reviewing Chinese and English.", flush=True)
    results = [{"item": pair} for pair in items]
    client = OpenAI(timeout=150, max_retries=4)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(audit, args.run, args.model, client, pair[lang]): (i, lang)
                   for i, pair in enumerate(items) for lang in ("zh", "en")}
        for n, future in enumerate(as_completed(futures), 1):
            i, lang = futures[future]
            results[i][lang] = future.result()
            if n % 20 == 0 or n == len(futures):
                print(f"Reviewed {n}/{len(futures)} language versions.", flush=True)
    save(args.run / "audit.json", results)
    write_reports(results, args.report, args.model)


if __name__ == "__main__":
    main()
