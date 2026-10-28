#!/usr/bin/env python3
"""Build a revision queue from the completed, repeated Gold/Hard QA review."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    args = parser.parse_args()
    root = args.run_root.resolve()
    entries = []
    manifests = {}
    for dataset in ("gold", "hard"):
        cases = {c["id"]: c for c in read(root / dataset / "cases.json")}
        results = read(root / dataset / "results.json")
        manifests[dataset] = read(root / dataset / "manifest.json")
        assert set(cases) == {r["id"] for r in results}
        for result in results:
            case = cases[result["id"]]
            reviews = result["reviews"]
            assert result["complete"], f"Incomplete review: {result['id']}"
            language_votes = [r["language_status"] for r in reviews]
            content_votes = [r["content_status"] for r in reviews]
            rewrite_count = language_votes.count("REWRITE")
            category = ("rewrite_both" if rewrite_count == len(reviews)
                        else "rewrite_one" if rewrite_count else "no_rewrite_flag")
            entries.append(dict(
                id=case["id"], dataset=dataset, content_id=case["id"].split(":", 1)[1].rsplit(":", 1)[0],
                form=case["form"], question=case["question"], options=case["options"],
                correct_option=case["correct_option"], expected_answer=case["expected_answer"],
                passage=case["passage"], decision=result["decision"], votes=result["votes"],
                language_votes=language_votes, content_votes=content_votes, rewrite_category=category,
                language_reviews=[dict(repeat=r["repeat"], failures=r["language_failures"],
                                       ratings={k: r["language_accessibility"][k] for k in
                                                ("naturalness", "processing", "context_economy")})
                                  for r in reviews],
                content_reviews=[dict(repeat=r["repeat"], status=r["content_status"],
                                      issues={k: r["content_validity"][k] for k in
                                              r["content_failures"] + r["content_uncertainties"] if k != "target"},
                                      target_basis=r["content_validity"]["target_basis"])
                                 for r in reviews]))

    summary = {}
    for dataset in ("gold", "hard"):
        rows = [e for e in entries if e["dataset"] == dataset]
        summary[dataset] = dict(forms=len(rows), questions=len({e["content_id"] for e in rows}),
                                overall=dict(Counter(e["decision"] for e in rows)),
                                wording=dict(Counter(e["rewrite_category"] for e in rows)),
                                by_form={form: dict(Counter(e["rewrite_category"] for e in rows if e["form"] == form))
                                         for form in ("open", "mcq")})
    data = dict(manifests=manifests, summary=summary, entries=entries)
    (root / "revision_queue.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    shortlist = ["# Questions flagged for rewriting", "",
                 "Completed review of English Gold72 and Chinese Hard66, with two passes per active form. "
                 "These are rewrite flags, not generated replacements. Original datasets are unchanged.", "",
                 "**Both passes** means the wording threshold was reached in each pass, even if content issues also require attention. "
                 "**One pass only** means adjudication is needed before treating the flag as stable. "
                 "For MCQs, the flag may concern the answer choices as well as the question stem.", ""]
    for category, title in (("rewrite_both", "Flagged in both passes"), ("rewrite_one", "Flagged in one pass only")):
        shortlist += ["## " + title, "", "| Set | Question ID | Form | Exact question | Flagged dimensions |",
                      "|---|---|---|---|---|"]
        for e in entries:
            if e["rewrite_category"] != category:
                continue
            dimensions = sorted({f for review in e["language_reviews"] for f in review["failures"]})
            shortlist.append("| " + " | ".join(map(cell, [e["dataset"].title(), e["content_id"],
                                                          e["form"], e["question"], ", ".join(dimensions)])) + " |")
        shortlist.append("")
    shortlist += ["[Full evidence, answer choices, content holds, and complete inventory](revision_queue.md).", ""]
    (root / "rewrite_shortlist.md").write_text("\n".join(shortlist), encoding="utf-8")

    lines = ["# Gold72 and Hard66: completed QA review", "",
             "These are questions flagged for rewriting. No replacement questions were generated, and no canonical questions were changed or removed.", "",
             "Gold: 71 English questions, each in open and multiple-choice form (142 forms). "
             "Hard: 65 active Chinese questions, 64 open and 65 multiple-choice forms (129 forms). "
             "Two excluded Hard forms and one inactive open form were not judged.", "",
             f"Model: {manifests['gold']['model']}; two independent repeat passes; three stages per pass: "
             "content validity, structural inspection, then wording burden. Actual campaign windows and hash-verified clean passages were used. "
             "Model screening is not measured human difficulty, and English Gold versus Chinese Hard is not a controlled quality comparison.", "",
             "A wording score of 2 or 3 in naturalness, processing, or context economy triggers a rewrite flag. "
             "A structural concern without a failed wording dimension goes to review. Content failures are held separately. "
             "A rewrite flag on both passes is reported even when content problems take priority in the overall decision.", "",
             "Technical response-validation fixes accepted verbatim joined option quotations and corrected inferred-target provenance labels from the input. "
             "Prompts, thresholds, and substantive judgments were not edited. Invalid responses were preserved and retried where needed; "
             "see [execution notes](execution_notes.json). Content holds caused by short passage windows need contextual adjudication.", "",
             "## Counts by form", "", "| Set and form | Reviewed | Rewrite both passes | Rewrite one pass only | No rewrite flag |",
             "|---|---:|---:|---:|---:|"]
    for dataset in ("gold", "hard"):
        for form in ("open", "mcq"):
            rows = [e for e in entries if e["dataset"] == dataset and e["form"] == form]
            counts = Counter(e["rewrite_category"] for e in rows)
            lines.append(f"| {dataset.title()} {form} | {len(rows)} | {counts['rewrite_both']} | {counts['rewrite_one']} | {counts['no_rewrite_flag']} |")
    lines += ["", "‘No rewrite flag’ does not imply acceptance: content or unresolved structure may still require review.", "",
              "| Set | KEEP both passes | Stable REWRITE decision | Stable content HOLD | REVIEW / disagreement |",
              "|---|---:|---:|---:|---:|"]
    for dataset in ("gold", "hard"):
        counts = summary[dataset]["overall"]
        lines.append(f"| {dataset.title()} | {counts.get('KEEP', 0)} | {counts.get('REWRITE', 0)} | {counts.get('HOLD_CONTENT', 0)} | {counts.get('REVIEW', 0)} |")

    def render(entries_to_show):
        if not entries_to_show:
            lines.extend(["None.", ""])
        for e in entries_to_show:
            lines.extend([f"### {e['id']}", "", e["question"], ""])
            if e["options"]:
                lines.extend(f"- {k}. {v}" for k, v in e["options"].items())
                lines.append("")
            lines.extend([f"Overall: **{e['decision']}** ({', '.join(e['votes'])}). "
                          f"Wording: {' / '.join(e['language_votes'])}. Content: {' / '.join(e['content_votes'])}.", ""])
            for review in e["language_reviews"]:
                scores = ", ".join(f"{k} {r['score']}/3" for k, r in review["ratings"].items())
                lines.append(f"- Pass {review['repeat']}: {scores}.")
                for failure in review["failures"]:
                    lines.append(f"  - {failure}: {review['ratings'][failure]['evidence']}")
            issues = [(r["repeat"], k, v) for r in e["content_reviews"] for k, v in r["issues"].items()]
            if issues:
                lines.extend(["", "Content issues:"])
                lines.extend(f"- Pass {rep}, {k} ({v['status']}): {v['evidence']}" for rep, k, v in issues)
            lines.append("")

    for category, title in (("rewrite_both", "Wording flagged for rewriting on both passes"),
                            ("rewrite_one", "Wording flagged on only one pass: adjudicate before rewriting")):
        lines.extend(["", "## " + title, ""])
        render([e for e in entries if e["rewrite_category"] == category])
    lines.extend(["", "## Additional content holds without a wording rewrite flag", ""])
    render([e for e in entries if e["rewrite_category"] == "no_rewrite_flag" and "HOLD" in e["content_votes"]])
    lines.extend(["", "## Complete inventory", "", "| ID | Question | Overall decision | Wording passes | Content passes |",
                  "|---|---|---|---|---|"])
    for e in entries:
        lines.append("| " + " | ".join(map(cell, [e["id"], e["question"], e["decision"],
                                                  " / ".join(e["language_votes"]), " / ".join(e["content_votes"])])) + " |")
    lines.extend(["", "Full evidence for every stage and both passes: [Gold](gold/report.md), [Hard](hard/report.md). "
                  "Exact windows and input hashes: [provenance](provenance.json). "
                  "Machine-readable queue: [revision_queue.json](revision_queue.json).", ""])
    (root / "revision_queue.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
