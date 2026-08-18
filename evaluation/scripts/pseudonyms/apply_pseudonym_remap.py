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
  python scripts/pseudonyms/apply_pseudonym_remap.py --dry-run  # from evaluation/
  python scripts/pseudonyms/apply_pseudonym_remap.py            # from evaluation/
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
# Extra dose cells addressable via --conditions (2026-07-27 design revision:
# omission/mistranslation each at 15% + 30%). Not in the default set, so the
# committed 7-condition run is byte-identical when the flag is omitted.
EXTRA_CONDITIONS = [
    ("omission5", "omission/5%"), ("omission15", "omission/15%"),
    ("mistranslation5", "mistranslation/5%"), ("mistranslation10", "mistranslation/10%"),
    ("mistranslation15", "mistranslation/15%"), ("mistranslation30", "mistranslation/30%"),
]
ALL_CONDITIONS = dict(CONDITIONS + EXTRA_CONDITIONS)
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


# Decanonicalization placeholders: short Chinese stem + 天干 suffix or 2-digit index
# (人物甲, 至高者甲, 角色03). Stem length is ambiguous -- in "天使 角色06" a greedy
# 3-char stem reads "使角色06" -- so anchor on the SUFFIX and test every stem
# length, treating the token as resolved if ANY reading is in the remap.
PLACEHOLDER_SUFFIX_PATTERN = re.compile(r'(?:[甲乙丙丁戊己庚辛壬癸]|\d{2})(?![一-鿿])')
MAX_STEM_CHARS = 3
# Ordinary words the suffix scan can otherwise reach (己 is a 天干 character).
NON_PLACEHOLDER_WORDS = {"自己", "知己", "异己", "利己", "而已"}


def unmapped_token_scan(text, remap):
    """Return placeholder tokens that no remap entry covers.

    These are almost always minted by a defect bank (角色03 -> 角色04,
    至高者甲 -> 明主甲). The remap is built from the chapter's own entity mapping,
    so an invented token has no entry and passes straight through into the
    participant-facing text. leak_scan cannot see these -- it only looks for
    leaked *canonical* names -- which is why 186 occurrences across 22 files went
    unreported before 2026-07-28.
    """
    # Stems the decanonicalizer actually issues for this chapter (人物, 角色, 场所...),
    # used to report the right token: in "他的角色05" the readings are 色05, 角色05,
    # 的角色05 and only 角色05 is the real token.
    stems = set()
    for key in remap:
        m = re.fullmatch(r'([一-鿿]{1,3})(?:[甲乙丙丁戊己庚辛壬癸]|\d{2})', key)
        if m:
            stems.add(m.group(1))

    bad = set()
    for m in PLACEHOLDER_SUFFIX_PATTERN.finditer(text):
        readings = []
        for n in range(1, MAX_STEM_CHARS + 1):
            start = m.start() - n
            if start < 0:
                break
            stem = text[start:m.start()]
            if not all('一' <= c <= '鿿' for c in stem):
                break
            readings.append((stem, stem + m.group(0), start))
        if not readings:
            continue
        if any(tok in NON_PLACEHOLDER_WORDS for _, tok, _ in readings):
            continue
        if any(tok in remap for _, tok, _ in readings):
            continue
        # Report the reading whose stem this chapter actually uses; otherwise the
        # longest reading that starts at a word boundary (covers minted stems like
        # 明主甲); otherwise the longest.
        known = [tok for stem, tok, _ in readings if stem in stems]
        if known:
            bad.add(known[0])
            continue
        anchored = [tok for _, tok, start in readings
                    if start == 0 or not ('一' <= text[start - 1] <= '鿿')]
        bad.add(max(anchored or [t for _, t, _ in readings], key=len))
    return sorted(bad)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--conditions", nargs="+", metavar="KEY",
                    help="condition keys to (re)write; default = the 7 pilot conditions. "
                         "Available: " + ", ".join(ALL_CONDITIONS))
    args = ap.parse_args()

    conditions = CONDITIONS
    if args.conditions:
        unknown = [k for k in args.conditions if k not in ALL_CONDITIONS]
        if unknown:
            sys.exit(f"unknown condition key(s): {unknown}; available: {sorted(ALL_CONDITIONS)}")
        conditions = [(k, ALL_CONDITIONS[k]) for k in args.conditions]

    if not os.path.isdir(REMAP_DIR):
        sys.exit(
            f"remap dir not found: {REMAP_DIR} "
            f"(run evaluation/scripts/pseudonyms/build_pseudonym_remap.py first)"
        )

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
        for cond, rel in conditions:
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
            for t in unmapped_token_scan(out, remap):
                problems.append(
                    f"ch{ch} {cond}: unmapped placeholder '{t}' "
                    f"x{out.count(t)} (minted by a defect bank; add it to the remap)"
                )
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
                for t in unmapped_token_scan(blob, remap):
                    problems.append(f"ch{ch} {cond} QA: unmapped placeholder '{t}'")
                if not args.dry_run:
                    json.dump(out_qa, open(os.path.join(d, OUT_QA), "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                n_qa += 1
            else:
                problems.append(f"ch{ch} {cond}: missing QA")

    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {n_pass} passages + {n_qa} QA files")
    print("scan:", "clean ✓" if not problems else "\n  " + "\n  ".join(problems))
    if problems:
        # Fail loudly. These files are delivered to participants; a silent report
        # is how the unmapped-token leak survived undetected.
        sys.exit(f"\nFAILED: {len(problems)} problem(s). Files above are NOT safe to deliver.")


if __name__ == "__main__":
    main()
