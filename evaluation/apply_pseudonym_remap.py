#!/usr/bin/env python3
"""Apply the per-chapter pseudonym remaps to the decanonicalized pilot files.

For every chapter it rewrites the CHINESE content -- replacing placeholder tokens
(and any leaked canonical name) with the readable pseudonyms, then collapsing
adjacent repeats (至高者 至高者 -> 至高者). English fields (open answers,
keywords) are left untouched -- they are the scoring rubric, not participant-facing.

Writes, next to each source (same 1.7b variant dir the importer reads):
  * passage_target_pseudonymized.txt   -- one per (chapter x condition), 56 total
  * qa_target_pseudonymized.json        -- one per chapter (Q + MCQ options rewritten)

Idempotent (overwrites). Runs a doubling/leak scan over every output.

Usage:
  python apply_pseudonym_remap.py --dry-run     # report only, no files written
  python apply_pseudonym_remap.py               # write the pseudonymized files
"""

import argparse
import json
import os
import re
import sys

from build_pseudonym_remap import collapse_repeats, collapsible_words

REMAP_DIR = "datasets/pseudonym_remap"
ANSWER_MODELS = ["1.7b", "1.5b", "llama 1b", "llama 3b"]
CHAPTERS = range(1, 9)
# (condition key, relative dir) -- the 7 pilot conditions, matching pilot_import.py
CONDITIONS = [
    ("clean", "omission/0%"), ("omission10", "omission/10%"),
    ("omission20", "omission/20%"), ("omission30", "omission/30%"),
    ("mistranslation20", "mistranslation/20%"), ("grammar30", "grammar/30%"),
    ("wbw", "google_word_by_word"),
]
SRC_PASSAGE = "passage_target_decanonicalized.txt"
OUT_PASSAGE = "passage_target_pseudonymized.txt"
SRC_QA = "qa_target_decanonicalized.json"
OUT_QA = "qa_target_pseudonymized.json"

# canonical spellings we deliberately do NOT touch (common/deity words), for the
# leak scan only -- these may legitimately survive (e.g. 神 as generic 'god').
LEAK_IGNORE = {"神", "主", "香", "灵"}


def variant_dir(ch, rel):
    for m in ANSWER_MODELS:
        d = os.path.join("outputs", f"luke{ch}", m, rel)
        if os.path.exists(d):
            return d
    return None


def remap_text(text, remap, words):
    for t in sorted(remap, key=len, reverse=True):
        text = text.replace(t, remap[t])
    return collapse_repeats(text, words)


_REF_RE = re.compile(r'(\d+\s*:\s*\d+(?:\s*\(#\d+\))?)')

def _clean_reference(ref):
    """'这记录 1:4' / 'Luke 1:4' / '路加福音 1:35 (#2)' -> '1:4' / '1:35 (#2)'."""
    if not ref:
        return ref
    m = _REF_RE.search(ref)
    return m.group(1).replace(" ", "") if m else ref


def remap_qa_record(rec, remap, words):
    rec = dict(rec)
    rec["Q"] = remap_text(rec["Q"], remap, words)
    if rec.get("passage_reference"):
        rec["passage_reference"] = _clean_reference(rec["passage_reference"])  # -> bare ch:verse
    if rec.get("q_type") != "open" and isinstance(rec.get("A"), dict):
        rec["A"] = {k: remap_text(v, remap, words) for k, v in rec["A"].items()}
    # open answer (English) + required/optional_keywords (English) left as-is
    return rec


def leak_scan(text, remap):
    """Return canonical proper-name spellings that survived in the output."""
    canon = [t for t in remap if not re.search(r'[甲乙丙丁戊己庚辛壬癸]|\d', t)]
    # 'canon' here = the canonical Chinese spellings we added to the remap; if any
    # still appears verbatim in the OUTPUT, it means a longer overlapping token ate
    # part of it -- worth flagging.
    return [c for c in canon if len(c) >= 2 and c in text and c not in LEAK_IGNORE]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(REMAP_DIR):
        sys.exit(f"remap dir not found: {REMAP_DIR} (run build_pseudonym_remap.py first)")

    n_pass = n_qa = 0
    problems = []
    for ch in CHAPTERS:
        rp = f"{REMAP_DIR}/luke{ch}_remap.json"
        if not os.path.exists(rp):
            problems.append(f"ch{ch}: no remap"); continue
        remap = json.load(open(rp, encoding="utf-8"))
        words = collapsible_words(remap)

        # For each condition dir: rewrite the passage, and the QA alongside it
        # (the QA is identical across conditions, but mirroring the source layout
        # -- which also keeps a qa_target_*.json in every dir -- avoids fallbacks).
        for cond, rel in CONDITIONS:
            d = variant_dir(ch, rel)
            if not d or not os.path.exists(os.path.join(d, SRC_PASSAGE)):
                problems.append(f"ch{ch} {cond}: missing passage"); continue

            txt = open(os.path.join(d, SRC_PASSAGE), encoding="utf-8").read()
            out = remap_text(txt, remap, words)
            compact = re.sub(r'\s+', '', out)
            for w in {v for v in remap.values() if len(v) >= 2}:
                if w + w in compact:
                    problems.append(f"ch{ch} {cond}: doubling '{w}'")
            for c in leak_scan(out, remap):
                problems.append(f"ch{ch} {cond}: leaked canonical '{c}'")
            if not args.dry_run:
                open(os.path.join(d, OUT_PASSAGE), "w", encoding="utf-8").write(out)
            n_pass += 1

            qp = os.path.join(d, SRC_QA)
            if os.path.exists(qp):
                out_qa = [remap_qa_record(r, remap, words) for r in json.load(open(qp, encoding="utf-8"))]
                blob = " ".join(r["Q"] + " " + (" ".join(r["A"].values()) if isinstance(r.get("A"), dict) else "")
                                for r in out_qa)
                for c in leak_scan(blob, remap):
                    problems.append(f"ch{ch} {cond} QA: leaked canonical '{c}'")
                if not args.dry_run:
                    json.dump(out_qa, open(os.path.join(d, OUT_QA), "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                n_qa += 1
            else:
                problems.append(f"ch{ch} {cond}: missing QA")

    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {n_pass} passages + {n_qa} QA files")
    print("scan:", "clean ✓" if not problems else "\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    main()
