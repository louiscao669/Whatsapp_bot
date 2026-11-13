"""Combine the reproducible translation checks into a per-item review queue."""
import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import re

from eten_shared.wh_type import classify_wh_type
from evaluation.scripts.pipeline.verify_reviewed122_zh import BANK, load_translations, read, write
from qa_generation.services.mcq_complexity import key_length_finding


def stem_change(english, chinese):
    """Catch two high-confidence changes in what the question asks the reader to supply."""
    target = classify_wh_type(chinese)
    if re.match(r"^(who|whom|whose)\b", english, re.I) and target == "how" and "谁" not in chinese:
        return "The source asks for a person; the translation asks how."
    if (re.match(r"^why\b", english, re.I) and target == "what"
            and not re.search(r"原因|理由|缘故|目的|为的是什么", chinese)):
        return "The source asks why; the translation asks what."
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True, help="Directory containing both review audits.")
    args = parser.parse_args()
    translated = load_translations(args.translations)
    bank_hash = sha256(args.translations.read_bytes()).hexdigest()
    source = {r["id"]: r for r in read(BANK / "english.json")}
    dispositions = {r["id"]: r for r in read(BANK / "pilot_review.json")}
    checks = {}
    for kind in ("blind", "fidelity"):
        manifest = read(args.run_dir / f"{kind}_manifest.json")
        if manifest["bank_sha256"] != bank_hash:
            raise ValueError(f"{kind} review is for a different translation.")
        results = read(args.run_dir / f"{kind}_audit.json")
        checks[kind] = {r["id"]: r for r in results}
        if len(results) != len(source) or set(checks[kind]) != set(source):
            raise ValueError(f"Incomplete {kind} review.")

    flagged = []
    counts = Counter()
    for _, row in translated:
        item_id = row["id"]
        findings = {}
        if not checks["blind"][item_id]["matched"]:
            findings["blind_key_disagreement"] = checks["blind"][item_id]["review"]
        if issues := checks["fidelity"][item_id]["issues"]:
            findings["model_fidelity"] = issues
        if issue := stem_change(source[item_id]["question"], row["question"]):
            findings["question_type"] = issue
        if issue := key_length_finding(dict(zip("ABCD", row["choices"][:4], strict=True)), row["correct"]):
            findings["key_length"] = {"letter": row["correct"], **issue}
        if dispositions[item_id]["status"] == "withheld":
            findings["previous_source_hold"] = dispositions[item_id]["reason"]
        if findings:
            counts.update(findings.keys())
            flagged.append({"id": item_id, "english": source[item_id]["question"],
                            "chinese": row["question"], "findings": findings})
    summary = {"bank_sha256": bank_hash, "total": len(translated), "flagged": len(flagged),
               "unflagged": len(translated) - len(flagged), "counts_by_check": dict(counts)}
    write(args.run_dir / "translation_report.json", {**summary, "items_to_check": flagged})
    print(summary)


if __name__ == "__main__":
    main()
