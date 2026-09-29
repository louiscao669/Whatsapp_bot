#!/usr/bin/env python3
"""Audit the Chinese question stems the pilot serves against their English sources.

WHY. translate_qa.py's prompt says only "Translate questions ... preserve item order,
q_type, choice labels, metadata fields, and any correct letter". Nothing requires the
translation to keep asking the SAME question, and nothing checks afterwards. Two items
inspected by hand both failed, in different ways:

  cc0k  EN "What did the king think was the reason the Arameans left their camp?"
        ZH 王为什么认为叙利亚人离开了营地？
        -> a what-question became a why-question, and 为什么 placed before 认为 asks why
           the king BELIEVES it rather than what reason he attributes. The options still
           answer the English question, so stem and options no longer agree.

  dbzo  EN "Why was a donkey's head sold for eighty pieces of silver?"
        ZH 为什么在撒马利亚驴头卖银子？
        -> the quantity (eighty shekels) vanished, which IS the question; 卖到 lost its
           到 so 驴头 reads as the seller; and 撒马利亚 was imported from the ANSWER,
           which the model sees because Q and A travel together in one item.

Two of two is not a sample, it is a reason to look at all of them. This runs offline on
the files the importer itself reads -- no database, no API.

  python3 evaluation/scripts/analysis/current/audit_translated_stems.py
  python3 evaluation/scripts/analysis/current/audit_translated_stems.py --json out.json

Scope: gold72 only. tier1_hard66_canonical stores its stems already in Chinese, so those
items have no English stem to compare against.
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

EN_DIR = REPO / "evaluation/datasets/qa/tier1_gold72_canonical_5opt"
NAME_MAP = REPO / "evaluation/datasets/perturbations/wbw_name_overrides.json"
DEFAULT_ROOT = "tier1_bsb_unblinded_5opt_think"

CJK_DIGITS = "零一二三四五六七八九十百千万两半"
# "one" is excluded on purpose: "no one to rescue" and "one of his sons" are not
# quantities, and they were the audit's only false positives on this corpus.
NUMBER_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand)\b", re.I)
DIGITS = re.compile(r"\d")
QUOTED = re.compile(r"[\u201c\u2018\"\'][^\u201d\u2019\"\']*[\u201d\u2019\"\']")
LEADING_WH = re.compile(r"^\s*(why|when|how|who|whom|whose|where|what|which)\b", re.I)


def zh_qa_path(outputs: Path, passage_id: str) -> Path | None:
    """The clean-condition translated QA the importer reads (its own preference order)."""
    base = outputs / passage_id / "omission" / "0%"
    for name in ("qa_target_decanonicalized.json", "qa_target.json"):
        if (base / name).exists():
            return base / name
    return None


def base_id(passage_id: str) -> str:
    """'uw-t1_judg17_18:qysg-open' -> 'qysg'."""
    core = re.sub(r"-(open|mcq)$", "", str(passage_id or ""))
    return core.rsplit(":", 1)[-1]


def quantity_lost(en_stem: str, zh_stem: str) -> bool:
    """The English stem states a number and the Chinese stem holds no number at all.

    Deliberately blunt: comparing VALUES across 'eleven hundred' / 一千一百 invites false
    alarms, while a stem that names a quantity and a translation with no numeral anywhere
    is unambiguous -- and it is the failure that actually happened.
    """
    # A number inside quoted material belongs to the quote, not to the question: a stem
    # that refers to a quoted prophecy as 预言 has dropped nothing of its own.
    unquoted = QUOTED.sub(" ", en_stem)
    if not (DIGITS.search(unquoted) or NUMBER_WORDS.search(unquoted)):
        return False
    return not (DIGITS.search(zh_stem) or any(c in zh_stem for c in CJK_DIGITS))


def leaked_names(en_stem: str, en_answer: str, zh_stem: str, names: dict) -> list:
    """Names in the Chinese stem whose English form appears only in the ANSWER."""
    out = []
    low_stem, low_answer = en_stem.lower(), (en_answer or "").lower()
    for english, chinese in names.items():
        if len(chinese) < 2 or chinese not in zh_stem:
            continue
        if re.search(rf"\b{re.escape(english)}\b", low_stem):
            continue
        if re.search(rf"\b{re.escape(english)}\b", low_answer):
            out.append(f"{chinese} (en '{english}' is in the answer, not the question)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outputs", type=Path,
                    default=REPO / "evaluation" / "outputs" / DEFAULT_ROOT)
    ap.add_argument("--json", type=Path, help="also write the findings as JSON")
    args = ap.parse_args()

    names = json.loads(NAME_MAP.read_text(encoding="utf-8")) if NAME_MAP.exists() else {}
    findings, totals = [], {"items": 0, "wh_drift": 0, "quantity_lost": 0, "leak": 0,
                            "unmatched": 0}

    for en_path in sorted(EN_DIR.glob("t1_*_all_formats.json")):
        passage_id = en_path.name.replace("_all_formats.json", "")
        zh_path = zh_qa_path(args.outputs, passage_id)
        if zh_path is None:
            print(f"  ! {passage_id}: no translated QA under {args.outputs}", file=sys.stderr)
            continue
        english = {}
        for record in json.loads(en_path.read_text(encoding="utf-8")):
            english[str(record.get("id"))] = record
        for record in json.loads(zh_path.read_text(encoding="utf-8")):
            zh_stem = str(record.get("Q") or "").strip()
            source = english.get(base_id(record.get("passage_id")))
            if not zh_stem:
                continue
            if source is None:
                totals["unmatched"] += 1
                continue
            totals["items"] += 1
            en_stem = str(source.get("question") or "").strip()
            en_answer = str(source.get("answer") or "")
            problems = []
            en_wh, zh_wh = classify_wh_type(en_stem), classify_wh_type(zh_stem)
            if en_wh != zh_wh:
                # classify_wh_type prefers a sentence-initial wh-word, then falls back to
                # cue-list order. Neither rule is safe when the stem OPENS with a
                # subordinate clause ("When Joash sat..., how did the people respond?")
                # or embeds a relative pronoun ("what did many WHO practiced magic do?"),
                # so the EN label itself is shaky there. Flagged, not silently trusted.
                caveat = "" if LEADING_WH.match(en_stem) else \
                    "  [EN stem does not open with its wh-word -- label may be the classifier, not the translation]"
                problems.append(f"wh drift: EN asks {en_wh}, ZH asks {zh_wh}{caveat}")
                totals["wh_drift"] += 1
            if quantity_lost(en_stem, zh_stem):
                problems.append("quantity in the EN stem has no numeral in the ZH stem")
                totals["quantity_lost"] += 1
            leaks = leaked_names(en_stem, en_answer, zh_stem, names)
            if leaks:
                problems.append("answer leaked into the stem: " + "; ".join(leaks))
                totals["leak"] += 1
            if problems:
                findings.append({"passage": passage_id, "id": base_id(record.get("passage_id")),
                                 "form": record.get("q_type"), "en": en_stem, "zh": zh_stem,
                                 "problems": problems})

    by_item = {}
    for f in findings:
        by_item.setdefault((f["passage"], f["id"]), f)   # open/mcq share a stem
    print(f"{totals['items']} translated stems checked "
          f"({len(by_item)} distinct items flagged; {totals['unmatched']} unmatched)\n")
    for (passage, item_id), f in sorted(by_item.items()):
        print(f"  {passage} / {item_id}")
        print(f"    EN  {f['en']}")
        print(f"    ZH  {f['zh']}")
        for problem in f["problems"]:
            print(f"    ->  {problem}")
        print()
    print(f"wh drift: {totals['wh_drift']}   quantity lost: {totals['quantity_lost']}   "
          f"answer leak: {totals['leak']}   (counted per form, so ~2x per item)")
    if args.json:
        args.json.write_text(json.dumps(findings, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
