#!/usr/bin/env python3
"""Group a QA set by the interrogative its stems ask with, and optionally annotate it.

    python3 group_by_wh_type.py                       # report gold72 and hard66
    python3 group_by_wh_type.py --annotate            # also write wh_type into the JSON
    python3 group_by_wh_type.py --self-test

WHY COMPOSITION MATTERS. An entity-retrieval item ("who did X") is answerable by locating
a proper noun, and a proper noun is the most transfer-robust element in a translation: it
survives grammar corruption, awkward phrasing, added filler and style drift, and is touched
only by deletion or a name swap. A set weighted toward `who` is therefore insensitive to
four of the six defect families before any defect is applied -- which is consistent with
the 2026-09-16 grid, where only omission and mistranslation moved accuracy at all.
See EXPERIMENT_QUESTION_TYPE_COMPOSITION_2026-09-26.md.

The classifier is eten_shared.wh_type, the same one the live assignment selector uses.
qa_generation keeps a second copy beside QAPairSimple.wh_type because the two repos are
not on one import path; if you change a cue, change it there too.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages" / "eten-shared"))
from eten_shared.wh_type import (  # noqa: E402
    UNKNOWN, WH_TYPES, classify_wh_type,
)

SETS = {
    "gold72": "evaluation/datasets/qa/tier1_gold72_canonical_5opt/*_all_formats.json",
    "hard66": "evaluation/datasets/qa/tier1_hard66_canonical/*.json",
}


def read_items(path):
    """[(item_dict, stem, options)] for every MCQ item in one file, either layout.

    gold72 nests the MCQ under an "mcq" key alongside "open"; hard66 stores one row per
    form with q_type and a choices dict. Both appear in evaluation/datasets/qa.
    """
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for it in (data if isinstance(data, list) else []):
        if not isinstance(it, dict):
            continue
        m = it.get("mcq")
        if isinstance(m, dict):
            out.append((m, m.get("mcq_stem") or it.get("question"), m.get("mcq_options") or []))
        elif it.get("q_type") == "mcq":
            out.append((it, it.get("Q"), list((it.get("A") or {}).values())))
    return out


def report(name, pattern, annotate=False):
    files = sorted(glob.glob(pattern))
    rows, touched = [], 0
    for f in files:
        items = read_items(f)
        changed = False
        for holder, stem, opts in items:
            t = classify_wh_type(stem)
            rows.append((t, stem, opts))
            if annotate and holder.get("wh_type") != t:
                holder["wh_type"] = t
                changed = True
        if annotate and changed:
            data = json.load(open(f, encoding="utf-8"))
            # re-apply on a fresh parse so we write exactly what we classified
            for it in data:
                m = it.get("mcq") if isinstance(it, dict) else None
                if isinstance(m, dict):
                    m["wh_type"] = classify_wh_type(m.get("mcq_stem") or it.get("question"))
                elif isinstance(it, dict) and it.get("q_type") == "mcq":
                    it["wh_type"] = classify_wh_type(it.get("Q"))
            json.dump(data, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            touched += 1
    n = len(rows)
    if not n:
        print(f"{name}: no MCQ items found at {pattern}")
        return
    print(f"\n{name}   n={n}   ({len(files)} file(s))")
    counts = {t: 0 for t in WH_TYPES}
    counts[UNKNOWN] = 0
    for t, _s, _o in rows:
        counts[t] += 1
    for t in list(WH_TYPES) + [UNKNOWN]:
        if counts[t]:
            bar = "#" * round(40 * counts[t] / n)
            print(f"  {t:7}{counts[t]:4d} {counts[t]/n:6.1%}  {bar}")
    # entity-retrieval proxy: most content options are short enough to be bare names
    short = sum(1 for _t, _s, o in rows
                if o and sum(1 for x in o if len(str(x)) <= 6) >= 3)
    print(f"  {'name-like options':21}{short:4d} {short/n:6.1%}")
    if annotate:
        print(f"  annotated wh_type into {touched} file(s)")


def self_test():
    cases = [("Why does God allow it?", "why"), ("Whose body is it?", "who"),
             ("Which city?", "what"), ("为什么但人寻找地盘？", "why"),
             ("这件事什么时候发生？", "when"), ("米该偷了什么？", "what"),
             ("亚比米勒的父亲是谁？", "who"), ("百姓如何反应？", "how"),
             ("神人从哪里来？", "where"), ("", UNKNOWN), (None, UNKNOWN)]
    bad = [(s, w, classify_wh_type(s)) for s, w in cases if classify_wh_type(s) != w]
    for s, w, g in bad:
        print(f"  [FAIL] {s!r}: wanted {w}, got {g}")
    print(f"{len(cases)-len(bad)}/{len(cases)} self-tests passed")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--annotate", action="store_true",
                    help="write a wh_type field into each MCQ item (rewrites the JSON)")
    ap.add_argument("--set", choices=sorted(SETS), action="append",
                    help="limit to one set (default: all)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    for name in (a.set or sorted(SETS)):
        report(name, SETS[name], annotate=a.annotate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
