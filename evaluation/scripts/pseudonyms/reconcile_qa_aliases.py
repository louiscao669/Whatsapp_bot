#!/usr/bin/env python3
"""Reconcile QA-set name spellings against a passage-derived pseudonym map.

Why this exists
---------------
``build_passage_name_map.py`` extracts entities from the *passage*, so its
aliases carry the passage translation's spelling. The Door43/uW QA sets use a
different tradition. For Judges 9 (NIV passage, uW QA) the divergence is total:

    passage: Abimelek     Jerub-Baal
    QA     : Abimelech    Jerubbaal      (+ "Gideon", absent from the passage)

Every alias rule therefore misses, the QA keeps its canonical names, and the
expected answers end up in a different namespace from the passage the model
reads. That is exactly the failure that made the first Tier 1 run unscoreable.

This script closes the gap deterministically -- no LLM. It scans the QA files
for proper-noun candidates, fuzzy-matches each unmatched one against the map's
canonicals and aliases, and writes an alias-augmented map. Candidates it cannot
match are reported and treated as a hard error, because an unmatched proper noun
in a QA set is a blinding leak, not a nuisance.

Cross-name identities (Jerub-Baal == Gideon) are below any safe fuzzy threshold
and must be supplied explicitly:

    --alias Jerub-Baal=Gideon

Usage (from repo root):

    python evaluation/scripts/pseudonyms/reconcile_qa_aliases.py \\
      --map evaluation/datasets/pseudonym_remap/name_map_tier1.json \\
      --qa-dir evaluation/datasets/qa/tier1_QAs_easy \\
      --out evaluation/datasets/pseudonym_remap/name_map_tier1_reconciled.json \\
      --alias Jerub-Baal=Gideon \\
      --report

    python evaluation/scripts/pseudonyms/reconcile_qa_aliases.py --self-test
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

# Kept in sync with pseudonymize_english_source.py -- the fields that actually
# reach a model or the scoring rubric.
QA_TEXT_FIELDS = {
    "content",
    "question",
    "Q",
    "A",
    "answer",
    "expected_answer",
    "mcq_stem",
    "mcq_options",
    "original_question",
    "original_answer",
}

# Capitalized words that are not names: sentence starters, interrogatives, and
# the handful of title-case function words that survive the scan. Deliberately
# conservative -- a false candidate costs one --ignore flag, a missed one costs
# a leak.
STOPWORDS = {
    "A", "After", "All", "An", "And", "As", "At", "Because", "Before", "But",
    "By", "During", "Each", "For", "From", "He", "Her", "His", "How", "However",
    "If", "In", "Into", "It", "Its", "Not", "Of", "On", "One", "Or", "Other",
    "She", "So", "Some", "텍스트", "That", "The", "Their", "Then", "There",
    "These", "They", "This", "Those", "To", "Two", "Under", "Until", "Was",
    "What", "When", "Where", "Which", "While", "Who", "Whom", "Whose", "Why",
    "With", "Yes", "No", "Both", "Three", "Seventy", "Thousand",
}

# A proper-noun candidate: one or more Capitalized tokens, hyphens allowed
# inside a token ("El-Berith", "Jerub-Baal", "Beth Millo", "Mount Zalmon").
CANDIDATE_RE = re.compile(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)*(?:\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)*)*\b")

DEFAULT_THRESHOLD = 0.82


class ReconcileError(Exception):
    pass


def load_map(path: Path) -> dict:
    if not path.exists():
        raise ReconcileError(f"{path} not found. Run build_passage_name_map.py first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("entities"):
        raise ReconcileError(f"{path} contains no entities.")
    return data


def collect_text(value: Any, key: str | None, out: list[str]) -> None:
    if isinstance(value, str):
        if key in QA_TEXT_FIELDS:
            out.append(value)
    elif isinstance(value, list):
        for item in value:
            collect_text(item, key, out)
    elif isinstance(value, dict):
        for inner_key, inner in value.items():
            collect_text(inner, inner_key, out)


# Characters after which a capital is just sentence case, not a name. The tag
# forms come from the *_all_formats "content" field (<question>...<answer>).
_SENTENCE_END = re.compile(r"(?:^|[.!?:;>\n\"'(\[]|\bA\.|\bB\.|\bC\.|\bD\.)\s*$")


def candidates(texts: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Return (name candidates, rejected sentence-initial-only candidates).

    Capitalization alone cannot separate "Abimelech" from an MCQ option that
    happens to start with "Fight". The discriminator is position: a real proper
    noun shows up mid-sentence at least once, whereas an option-initial verb
    never does. Candidates seen only in initial position are rejected, and
    returned separately so --report can surface a name that genuinely never
    appears mid-sentence.
    """
    total: dict[str, int] = {}
    medial: dict[str, int] = {}
    for text in texts:
        for match in CANDIDATE_RE.finditer(text):
            phrase = match.group(0).strip()
            initial = bool(_SENTENCE_END.search(text[: match.start()]))

            # "When Abimelech" -> drop the leading sentence word, keep the name.
            tokens = phrase.split()
            while tokens and tokens[0] in STOPWORDS:
                tokens.pop(0)
                initial = False
            if not tokens:
                continue

            # Score the whole phrase and each capitalized token: uW writes both
            # "Beth Millo" and a bare "Millo".
            forms = {" ".join(tokens)}
            if len(tokens) > 1:
                forms.update(tokens)

            whole = " ".join(tokens)
            for form in sorted(forms):
                if form in STOPWORDS or len(form) < 3:
                    continue
                total[form] = total.get(form, 0) + 1
                # The phrase and its first token both sit in initial position;
                # only interior tokens escape it. Without this, "Fight Abimelech"
                # would look medial on the strength of its own second word.
                if not initial or form not in (tokens[0], whole):
                    medial[form] = medial.get(form, 0) + 1

    keep = {form: hits for form, hits in total.items() if medial.get(form)}
    rejected = {form: hits for form, hits in total.items() if not medial.get(form)}
    return (
        dict(sorted(keep.items(), key=lambda item: (-item[1], item[0]))),
        dict(sorted(rejected.items(), key=lambda item: (-item[1], item[0]))),
    )


def known_forms(entities: list[dict]) -> dict[str, str]:
    """alias/canonical (lowercased) -> canonical."""
    forms: dict[str, str] = {}
    for entity in entities:
        canonical = entity["canonical"]
        for alias in [canonical] + list(entity.get("aliases") or []):
            forms[alias.lower()] = canonical
            forms[alias.lower().replace("-", "")] = canonical
            forms[alias.lower().replace("-", " ")] = canonical
    return forms


def best_match(candidate: str, forms: dict[str, str], threshold: float) -> tuple[str | None, float]:
    lowered = candidate.lower()
    if lowered in forms:
        return forms[lowered], 1.0
    best: tuple[str | None, float] = (None, 0.0)
    for form, canonical in forms.items():
        ratio = difflib.SequenceMatcher(None, lowered, form).ratio()
        if ratio > best[1]:
            best = (canonical, ratio)
    return best if best[1] >= threshold else (None, best[1])


def reconcile(
    data: dict,
    qa_paths: list[Path],
    threshold: float,
    manual: dict[str, list[str]],
    ignore: set[str],
) -> tuple[dict, list[tuple[str, str, float, int]], list[tuple[str, int, float]], dict[str, int]]:
    entities = data["entities"]
    by_canonical = {entity["canonical"]: entity for entity in entities}

    for canonical, extras in manual.items():
        if canonical not in by_canonical:
            raise ReconcileError(
                f"--alias {canonical}={extras[0]}: {canonical!r} is not a canonical "
                f"name in the map. Known: {', '.join(sorted(by_canonical))}"
            )

    texts: list[str] = []
    for path in qa_paths:
        collect_text(json.loads(path.read_text(encoding="utf-8")), None, texts)

    counts, rejected = candidates(texts)
    forms = known_forms(entities)

    added: list[tuple[str, str, float, int]] = []
    unmatched: list[tuple[str, int, float]] = []

    for candidate, hits in counts.items():
        if candidate in ignore:
            continue
        target = next(
            (
                canonical
                for canonical, extras in manual.items()
                if any(extra.lower() == candidate.lower() for extra in extras)
            ),
            None,
        )
        ratio = 1.0
        if target is None:
            target, ratio = best_match(candidate, forms, threshold)
        if target is None:
            unmatched.append((candidate, hits, ratio))
            continue
        entity = by_canonical[target]
        aliases = entity.setdefault("aliases", [])
        if candidate not in aliases:
            aliases.append(candidate)
            added.append((candidate, target, ratio, hits))

    for entity in entities:
        # Longest-first is applied downstream, but keep the file tidy/stable.
        entity["aliases"] = sorted(set(entity.get("aliases") or []))

    data = {**data, "entities": entities}
    data["qa_reconciled_from"] = [str(path) for path in qa_paths]
    return data, added, unmatched, rejected


def self_test() -> int:
    data = {
        "schema_version": 1,
        "entities": [
            {"canonical": "Abimelek", "type": "person", "aliases": ["Abimelek"],
             "pseudonym_en": "Tarel", "pseudonym_zh": "塔瑞"},
            {"canonical": "Jerub-Baal", "type": "person", "aliases": ["Jerub-Baal"],
             "pseudonym_en": "Voren", "pseudonym_zh": "沃仁"},
            {"canonical": "Shechem", "type": "place", "aliases": ["Shechem"],
             "pseudonym_en": "Kadresh", "pseudonym_zh": "卡德城"},
        ],
    }
    texts = [
        "Who was Abimelech's father?",
        "Abimelech's father was Gideon who was also called Jerubbaal.",
        "The leaders of Shechem hoped to ambush Abimelech.",
    ]
    texts += [
        "Fight Abimelech",          # MCQ option: title-cased verb phrase
        "Hires reckless scoundrels",
    ]
    counts, rejected = candidates(texts)
    checks = []
    checks.append(("Abimelech found", "Abimelech" in counts, sorted(counts)))
    checks.append(("Who filtered", "Who" not in counts, sorted(counts)))
    checks.append(("The filtered", "The" not in counts, sorted(counts)))
    checks.append(("option-initial verb rejected",
                   "Fight" not in counts and "Hires" not in counts, sorted(counts)))
    checks.append(("'Fight Abimelech' not kept as a phrase",
                   "Fight Abimelech" not in counts, sorted(counts)))
    checks.append(("rejects are reported", "Hires" in rejected, sorted(rejected)))

    forms = known_forms(data["entities"])
    target, ratio = best_match("Abimelech", forms, DEFAULT_THRESHOLD)
    checks.append((f"Abimelech->Abimelek ({ratio:.2f})", target == "Abimelek", target))
    target, ratio = best_match("Jerubbaal", forms, DEFAULT_THRESHOLD)
    checks.append((f"Jerubbaal->Jerub-Baal ({ratio:.2f})", target == "Jerub-Baal", target))
    target, ratio = best_match("Gideon", forms, DEFAULT_THRESHOLD)
    checks.append((f"Gideon unmatched ({ratio:.2f})", target is None, target))

    failed = 0
    for label, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"   got {detail!r}"))
        failed += not ok
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", type=Path, help="Name map from build_passage_name_map.py")
    parser.add_argument("--merge", type=Path, action="append", default=[],
                        metavar="FILE",
                        help="Extra entities to fold in, same schema as --map. For "
                             "names the passage-side extraction missed entirely "
                             "(a QA set may mention people the passage never names).")
    parser.add_argument("--qa", type=Path, action="append", default=[])
    parser.add_argument("--qa-dir", type=Path)
    parser.add_argument("--glob", default="*_all_formats.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Fuzzy match cutoff. Default: {DEFAULT_THRESHOLD}")
    parser.add_argument("--alias", action="append", default=[], metavar="CANONICAL=FORM",
                        help="Force a QA spelling onto an entity (Jerub-Baal=Gideon).")
    parser.add_argument("--ignore", action="append", default=[], metavar="WORD",
                        help="Candidate that is not a name; skip it.")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--allow-unmatched", action="store_true",
                        help="Exit 0 even with unmatched candidates. Leaks the unmatched names.")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if not args.map:
        print("error: --map is required (or use --self-test)", file=sys.stderr)
        return 2

    qa_paths = list(args.qa)
    if args.qa_dir:
        qa_paths += sorted(args.qa_dir.glob(args.glob))
    if not qa_paths:
        print("error: no QA files; pass --qa or --qa-dir", file=sys.stderr)
        return 2

    manual: dict[str, list[str]] = {}
    for spec in args.alias:
        if "=" not in spec:
            print(f"error: --alias expects CANONICAL=FORM, got {spec!r}", file=sys.stderr)
            return 2
        canonical, form = spec.split("=", 1)
        # Repeatable per canonical: "Beth Millo" needs both "Beth" and "Millo".
        manual.setdefault(canonical.strip(), []).append(form.strip())

    try:
        data = load_map(args.map)
        for extra_path in args.merge:
            extra = load_map(extra_path)
            known = {entity["canonical"] for entity in data["entities"]}
            new = [e for e in extra["entities"] if e["canonical"] not in known]
            data["entities"].extend(new)
            print(f"merged {len(new)} entity/entities from {extra_path}: "
                  + ", ".join(e["canonical"] for e in new))
        data, added, unmatched, rejected = reconcile(
            data, qa_paths, args.threshold, manual, set(args.ignore)
        )
    except (ReconcileError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.report or added:
        print(f"{len(added)} alias/aliases added from {len(qa_paths)} QA file(s):")
        for candidate, canonical, ratio, hits in added:
            note = "exact" if ratio == 1.0 else f"{ratio:.2f}"
            print(f"  {candidate:22s} -> {canonical:18s} ({note}, {hits} hit(s))")

    if args.report and rejected:
        print(
            f"\n{len(rejected)} candidate(s) rejected as sentence-initial only "
            "(title-cased MCQ options, not names):"
        )
        print("  " + ", ".join(list(rejected)[:25]) + ("" if len(rejected) <= 25 else ", ..."))
        print("  If a real name is in this list, add it with --alias CANONICAL=FORM.")

    if unmatched:
        print(f"\n{len(unmatched)} unmatched proper-noun candidate(s):", file=sys.stderr)
        for candidate, hits, ratio in unmatched:
            print(f"  {candidate:22s} {hits:3d} hit(s)  best ratio {ratio:.2f}", file=sys.stderr)
        print(
            "\nEach of these will survive into the blinded QA. Resolve with "
            "--alias CANONICAL=FORM (a different name for a known entity), "
            "--ignore WORD (not a name), or by adding the entity to the map.",
            file=sys.stderr,
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
        print(f"\nwrote {args.out}")

    return 0 if (not unmatched or args.allow_unmatched) else 1


if __name__ == "__main__":
    raise SystemExit(main())
