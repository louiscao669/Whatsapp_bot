#!/usr/bin/env python3
"""Audit each gold72 item's option-aligned MCQ stem against its canonical question.

WHERE THE DEFECTS ACTUALLY ARE. An all-formats record carries a canonical ``question``
plus, inside its ``mcq`` block, an option-aligned ``mcq_stem``. translate_qa.normalize_item
prefers ``mcq_stem`` for the MCQ form -- deliberately, and its comment says why: options
written to answer "whom did X kill" would be incoherent under "how did X rescue Y".

The cost is that the option-aligned stem is free to narrow the question, and some of them
narrow it by saying part of the answer out loud:

  kjsg  canonical  How did Abishai rescue David when he was weary?
        mcq_stem   Whom does Abishai kill to rescue David?      <- a how became a who,
                                                                   and it concedes the kill
  i7yf  canonical  What pact concerning Paul did some Jewish men make?
        mcq_stem   What do 40 Jewish men vow not to do until they kill Paul?

The Chinese for these is FAITHFUL. Both defects are in the English mcq_stem, so this audit
runs on the dataset files alone -- no translation, no database, no API.

  python3 evaluation/scripts/analysis/current/audit_mcq_stems.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "packages" / "eten-shared"))
from eten_shared.wh_type import classify_wh_type  # noqa: E402

DEFAULT_DIRS = ("evaluation/datasets/qa/tier1_gold72_canonical_5opt",)
NUMBER_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|\d+)\b", re.I)
WORD = re.compile(r"[a-z']+")
STOP = set("""a an the and or but if of to in on at by with from as that this these those for
he she it they we you i his her its their our your my him them us me who whom whose which
what when where why how was were is are be been being am had has have do does did done not
no nor all any some each every both few more most other another such only own same so than
too very can will just should now then there here about after before while because since
until would could may might must shall into over under again further once during out up down
off above below between through said say says tell told ask asked make made made give gave
go went come came take took get got did what's it's""".split())


def stem_from_content(content) -> str | None:
    match = re.search(r"<question>\s*(.*?)\s*<question>", str(content or ""), re.DOTALL)
    if not match:
        return None
    return re.sub(r"\n\s*[A-F]\.\s+.*$", "", match.group(1).strip(), flags=re.DOTALL).strip()


def _stem_word(word: str) -> str:
    """Crude suffix strip, so kill/killed and anger/angry compare equal.

    Without it the audit missed i7yf (stem says "kill", the answer says "killed") and
    falsely flagged eo5e (canonical "anger kindled" vs stem "become angry").
    """
    for suffix in ("ies", "ing", "ed", "es", "ly", "ry", "er", "s", "y"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def content_words(text: str) -> set:
    return {_stem_word(w) for w in WORD.findall((text or "").lower())
            if len(w) > 2 and w not in STOP}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="*", default=list(DEFAULT_DIRS))
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    findings, total = [], 0
    for folder in args.dirs:
        for path in sorted((REPO / folder).glob("t1_*_all_formats.json")):
            for record in json.loads(path.read_text(encoding="utf-8")):
                mcq = record.get("mcq") or {}
                stem = mcq.get("mcq_stem") or stem_from_content(mcq.get("content"))
                canonical = (record.get("question") or "").strip()
                answer = (record.get("answer") or "").strip()
                if not (stem and canonical):
                    continue
                total += 1
                problems = []
                canon_wh, stem_wh = classify_wh_type(canonical), classify_wh_type(stem)
                if canon_wh != stem_wh:
                    problems.append(f"question type changed: canonical {canon_wh} -> stem {stem_wh}")
                # a word the stem introduces that the ANSWER supplies is a concession
                leaked = sorted((content_words(stem) - content_words(canonical))
                                & content_words(answer))
                if leaked:
                    problems.append("stem states part of the answer: " + ", ".join(leaked))
                canon_nums = set(m.group(0).lower() for m in NUMBER_WORDS.finditer(canonical))
                if canon_nums and not NUMBER_WORDS.search(stem):
                    problems.append(f"quantity dropped: {sorted(canon_nums)}")
                if problems:
                    findings.append({"passage": record.get("passage_id"),
                                     "id": record.get("id"), "canonical": canonical,
                                     "stem": stem, "answer": answer, "problems": problems})

    print(f"{total} MCQ stems checked, {len(findings)} flagged\n")
    for f in sorted(findings, key=lambda f: (str(f["passage"]), str(f["id"]))):
        print(f"  {f['passage']} / {f['id']}")
        print(f"    canonical  {f['canonical']}")
        print(f"    mcq_stem   {f['stem']}")
        for problem in f["problems"]:
            print(f"    ->  {problem}")
        print()
    if args.json:
        args.json.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
