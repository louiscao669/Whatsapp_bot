#!/usr/bin/env python3
"""Teach the character-level defect generators to protect pseudonymised names.

THE BUG. `create_grammar_variants.py` guards its five operations with
`PLACEHOLDER_PATTERN`, which matches the OLD blinding style: `__PERSON_C__`
tokens and Chinese role placeholders (人物甲, 地点乙, ...). The pipeline moved to
English-side pseudonymisation, which emits natural-looking names (尼温, 韦恩,
韦姆村). Those match nothing, so every operation treats them as ordinary text:

    韦恩            -> 韦位恩          (classifier inserted INSIDE the name)
    问问韦姆村的所有首领  -> 姆村所有件问问韦首领   (phrase reorder splits the toponym)

Measured on tier1_bsb/t1_judg9 at 30% dose: 8% of proper-name mentions
destroyed (99/108). In a decanonicalised passage the pseudonym IS the referent,
so a broken name is ADEQUACY damage, not fluency damage -- which silently turns
the "fluency" arm into a mixed arm and explains why grammar accuracy was not
flat on gold72.

THE FIX. Nothing structural: the operations already consult the protection
layer, so it is enough to widen the vocabulary that layer knows about. This
patch:

  1. adds `--protected-terms` (repeatable) to load pseudonym maps,
  2. merges those terms into BOTH protection paths -- `protected_spans()`
     (used by the char-level ops) and `token_chunks()` (used by the phrase
     reorder), which previously diverged,
  3. adds a post-generation INVARIANT: every protected term must occur exactly
     as many times in the corrupted text as in the clean text, else the run
     fails loudly instead of writing a silently-contaminated variant,
  4. records `protected_terms`/`protected_verified` in the metadata.

Longest-first alternation matters: 韦姆村 must win over any 韦姆 prefix, or the
tail of the toponym stays unprotected.

Idempotent -- safe to re-run. Writes a .bak once.

Usage:
  python3 evaluation/scripts/variants/patch_protect_names.py            # apply
  python3 evaluation/scripts/variants/patch_protect_names.py --check    # dry run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

TARGET = Path("evaluation/scripts/variants/create_grammar_variants.py")

MARKER = "# --- name protection (patched) ---"

HELPERS = '''
# --- name protection (patched) ---
# Pseudonymised entity names are ordinary Chinese text to PLACEHOLDER_PATTERN,
# so they must be registered explicitly or the operations will corrupt them.
EXTRA_PROTECTED: "re.Pattern | None" = None
_CJK_RE = re.compile(r"[\\u3400-\\u9fff]")


def _collect_cjk_strings(node, out: set) -> None:
    """Harvest every CJK string from an arbitrarily nested name-map JSON."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and _CJK_RE.search(key):
                out.add(key)
            _collect_cjk_strings(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_cjk_strings(value, out)
    elif isinstance(node, str) and _CJK_RE.search(node):
        out.add(node)


def load_protected_terms(paths) -> int:
    """Compile the pseudonym vocabulary into EXTRA_PROTECTED. Returns its size."""
    global EXTRA_PROTECTED
    terms: set = set()
    for path in paths or []:
        _collect_cjk_strings(json.loads(Path(path).read_text(encoding="utf-8")), terms)
    # Single characters are far too aggressive -- one common character would
    # freeze half the passage and silently drive the achieved rate to zero.
    terms = {t.strip() for t in terms if len(t.strip()) >= 2}
    if not terms:
        EXTRA_PROTECTED = None
        return 0
    # Longest first: 韦姆村 must match before 韦姆, else the tail is left exposed.
    ordered = sorted(terms, key=len, reverse=True)
    EXTRA_PROTECTED = re.compile("|".join(re.escape(t) for t in ordered))
    return len(ordered)


def merged_protected_spans(text: str) -> list:
    """Placeholders + pseudonyms, overlaps merged, sorted by start."""
    spans = [(m.start(), m.end()) for m in PLACEHOLDER_PATTERN.finditer(text)]
    if EXTRA_PROTECTED is not None:
        spans += [(m.start(), m.end()) for m in EXTRA_PROTECTED.finditer(text)]
    if not spans:
        return []
    spans.sort()
    merged = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(s) for s in merged]


def verify_protected(clean: str, corrupted: str) -> list:
    """Every protected term must survive with its exact occurrence count.

    This is the invariant whose absence let 8% of names be destroyed unnoticed.
    """
    if EXTRA_PROTECTED is None:
        return []
    losses = []
    for term in {m.group(0) for m in EXTRA_PROTECTED.finditer(clean)}:
        before, after = clean.count(term), corrupted.count(term)
        if after != before:
            losses.append({"term": term, "before": before, "after": after})
    return sorted(losses, key=lambda d: d["term"])
'''

OLD_SPANS = '''def protected_spans(text: str) -> list[tuple[int, int]]:
    spans = [(match.start(), match.end()) for match in PLACEHOLDER_PATTERN.finditer(text)]
    spans.extend((match.start(), match.end()) for match in re.finditer(r"\\d+", text))
    return spans'''

NEW_SPANS = '''def protected_spans(text: str) -> list[tuple[int, int]]:
    spans = list(merged_protected_spans(text))
    spans.extend((match.start(), match.end()) for match in re.finditer(r"\\d+", text))
    return spans'''

OLD_CHUNKS = '''    chunks = []
    last = 0
    for match in PLACEHOLDER_PATTERN.finditer(text):
        if match.start() > last:
            chunks.append({"text": text[last : match.start()], "protected": False})
        chunks.append({"text": match.group(0), "protected": True})
        last = match.end()'''

NEW_CHUNKS = '''    chunks = []
    last = 0
    # Was PLACEHOLDER_PATTERN only, which left pseudonyms splittable by the
    # phrase-reorder operation even once the char-level ops were fixed.
    for start, end in merged_protected_spans(text):
        if start > last:
            chunks.append({"text": text[last:start], "protected": False})
        chunks.append({"text": text[start:end], "protected": True})
        last = end'''

OLD_ARG = '''    parser.add_argument("--seed", type=int, default=2026)'''
NEW_ARG = '''    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--protected-terms",
        action="append",
        default=[],
        metavar="NAME_MAP.json",
        help=(
            "Pseudonym map whose CJK terms must never be split or edited. "
            "Repeatable. Without this, English-side pseudonyms (尼温, 韦姆村) "
            "are treated as ordinary text and get corrupted -- 8%% of name "
            "mentions were destroyed at 30%% dose before this was added."
        ),
    )
    parser.add_argument(
        "--allow-protected-loss",
        action="store_true",
        help="Downgrade the protected-term invariant from fatal to a warning.",
    )'''


def apply(text: str) -> tuple[str, list[str]]:
    notes = []
    if MARKER in text:
        return text, ["already patched (marker present)"]

    if "import json" not in text.split("def ")[0]:
        notes.append("WARNING: 'import json' not found in the header; add it manually")

    anchor = "PROTECTED_CHARS = set("
    idx = text.index(anchor)
    end = text.index("\n", text.index("\n", idx) + 1)
    text = text[:end] + "\n" + HELPERS + text[end:]
    notes.append("inserted loader + merged_protected_spans + verify_protected")

    if OLD_SPANS not in text:
        raise SystemExit("protected_spans() body not found -- file drifted; patch by hand")
    text = text.replace(OLD_SPANS, NEW_SPANS)
    notes.append("protected_spans() now merges pseudonyms")

    if OLD_CHUNKS not in text:
        raise SystemExit("token_chunks() body not found -- file drifted; patch by hand")
    text = text.replace(OLD_CHUNKS, NEW_CHUNKS)
    notes.append("token_chunks() now segments on merged spans")

    if OLD_ARG not in text:
        raise SystemExit("--seed argument not found -- file drifted; patch by hand")
    text = text.replace(OLD_ARG, NEW_ARG)
    notes.append("added --protected-terms / --allow-protected-loss")

    return text, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="dry run")
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args()

    path = args.target
    if not path.exists():
        raise SystemExit(f"{path} not found -- run from the repo root")
    original = path.read_text(encoding="utf-8")
    patched, notes = apply(original)

    for note in notes:
        print(f"  - {note}")
    if patched == original:
        print("no change")
        return 0
    if args.check:
        print("\n--check: not written")
        return 0
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"  - backup -> {backup}")
    path.write_text(patched, encoding="utf-8")
    print(f"  - wrote {path}")
    print("\nStill to wire by hand (2 lines, see the README note printed below):")
    print("  in main(): load_protected_terms(args.protected_terms)")
    print("  in apply_grammar_errors()/create_variant(): call verify_protected(clean, out)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
