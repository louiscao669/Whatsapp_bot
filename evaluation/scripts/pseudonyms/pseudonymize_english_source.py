#!/usr/bin/env python3
"""Apply English pseudonyms to a source passage and its QA set before translation.

This replaces the ``__PERSON_C__`` protected-token step. Because the output is
still name-shaped natural English, every translation method can consume it --
including helsinki, mBART-50, and NLLB, which mangle underscore tokens and
therefore currently receive unblinded English.

The passage and the QA set must be pseudonymized together with the same table,
or the standard answers stop matching the passage.

Usage (from evaluation/):

    # passage
    python scripts/pseudonyms/pseudonymize_english_source.py \\
      --passage datasets/passages/test_passage_luke5.txt \\
      --out-passage outputs/_pseudo/test_passage_luke5.txt

    # QA set
    python scripts/pseudonyms/pseudonymize_english_source.py \\
      --qa datasets/qa/qa_output_luke_ch5_all_formats.json \\
      --out-qa outputs/_pseudo/qa_output_luke_ch5_all_formats.json

    # both, with a leak report
    python scripts/pseudonyms/pseudonymize_english_source.py \\
      --passage ... --qa ... --out-dir outputs/_pseudo --report

Verse numbers, footnote markers, ``<header>`` tags, and all JSON structure are
preserved. Text inside ``<header>`` is pseudonymized, since section headings name
entities too. The operation is idempotent: pseudonyms never collide with
canonical names, so a second run is a no-op.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Resolved against evaluation/ so the script works from any working directory.
EVAL_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TABLE = EVAL_DIR / "datasets/pseudonym_remap/english_pseudonyms.json"

# QA fields that are participant- or model-facing and must be pseudonymized.
# Everything else (ids, references, scores) is left byte-identical.
#
# The *_all_formats schema (Door43/uW imports, including the Tier 1 set) carries
# the same text several times over: agents/generate_chinese_answers.py reads
# mcq_stem / original_question / mcq_options, and scoring/score_generated_answers.py
# falls back to original_answer. Missing any one of them leaks a canonical name
# into either the prompt or the scoring rubric.
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
QA_KEYWORD_FIELDS = {
    "required_keywords",
    "optional_keywords",
    "validated_en",
    "concept_synonyms",
    "optional",
}
QA_NESTED_CONTAINERS = {"open", "mcq", "anchors"}

# Possessive suffixes, including the curly apostrophe that appears in the NIV
# text ("water's edge" uses U+2019).
POSSESSIVE = r"(?:'s|’s|s'|s’)?"
POSSESSIVE_S = r"(?:'s|’s|'|’)?"


class PseudonymError(Exception):
    pass


def load_table(path: Path) -> list[dict]:
    if not path.exists():
        raise PseudonymError(
            f"{path} not found. Run build_english_pseudonyms.py "
            "(Luke 1-8) or build_passage_name_map.py (any passage) first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    entities = data.get("entities")
    if not entities:
        raise PseudonymError(f"{path} contains no entities.")
    return [normalize_entity(entity, path) for entity in entities]


def scope_to_passage(entities: list[dict], passage_id: str | None) -> list[dict]:
    if not passage_id:
        return entities
    return [
        entity
        for entity in entities
        if not entity.get("passages") or passage_id in entity["passages"]
    ]


def normalize_entity(entity: dict, path: Path) -> dict:
    """Accept both table schemas.

    build_english_pseudonyms.py writes ``pseudonym``; build_passage_name_map.py
    writes ``pseudonym_en`` / ``pseudonym_zh``. The latter's docstring claims it
    feeds this script, but the key never matched, so the two halves were never
    actually connected. Normalize here rather than forking the callers.
    """
    if entity.get("pseudonym"):
        return entity
    english = entity.get("pseudonym_en")
    if not english:
        raise PseudonymError(
            f"{path}: entity {entity.get('canonical')!r} has neither "
            "'pseudonym' nor 'pseudonym_en'."
        )
    return {**entity, "pseudonym": english}


def build_rules(entities: list[dict]) -> list[tuple[re.Pattern, str, str]]:
    """One compiled rule per alias, longest alias first.

    Longest-first matters: "Simon the Zealot" and "James son of Alphaeus" must be
    consumed before the bare "Simon" and "James" rules can fire.
    """
    pairs: list[tuple[str, str, str]] = []
    for entity in entities:
        for alias in entity.get("aliases") or [entity["canonical"]]:
            pairs.append((alias, entity["pseudonym"], entity["canonical"]))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)

    rules = []
    for alias, pseudonym, canonical in pairs:
        # Names already ending in "s" take a bare apostrophe possessive
        # ("Jesus' parents"), which would otherwise leave a stray apostrophe.
        possessive = POSSESSIVE_S if alias.endswith(("s", "S")) else POSSESSIVE
        # \b fails against a leading apostrophe and against multiword aliases
        # with internal spaces, so anchor on explicit boundaries instead.
        # Case-insensitive because the keyword fields (required_keywords,
        # concept_synonyms) are stored lowercased for the RapidFuzz scorer:
        # a case-sensitive "Gideon" rule silently misses "gideon", leaving the
        # canonical name in the scoring rubric after the passage is blinded.
        pattern = re.compile(
            rf"(?<![A-Za-z]){re.escape(alias)}{possessive}(?![A-Za-z])",
            re.IGNORECASE,
        )
        rules.append((pattern, pseudonym, canonical))
    return rules


def apply_rules(
    text: str,
    rules: list[tuple[re.Pattern, str, str]],
    counts: dict[str, int],
    lowercase: bool = False,
) -> str:
    if not text:
        return text

    for pattern, pseudonym, canonical in rules:

        def substitute(match: re.Match) -> str:
            matched = match.group(0)
            replacement = pseudonym
            # A deity title carries its own article. After a possessive the
            # article is ungrammatical: "the Lord's Messiah" must become
            # "the Supreme One's Chosen One", not "... 's the Chosen One".
            preceding = match.string[: match.start()]
            if replacement.startswith("the ") and preceding.rstrip().endswith(
                ("'s", "’s", "s'", "s’")
            ):
                replacement = replacement[4:]
            possessive = matched.endswith(("'s", "’s", "s'", "s’", "'", "’"))
            if possessive and not matched.lower().startswith(pseudonym.lower()):
                replacement = f"{replacement}'s"
            if lowercase or matched.islower():
                replacement = replacement.lower()
            counts[canonical] = counts.get(canonical, 0) + 1
            return replacement

        text = pattern.sub(substitute, text)

    # Deity pseudonyms carry their own article, so "the God" and "the Lord"
    # would otherwise produce "the the Sovereign".
    text = re.sub(r"\bthe the\b", "the", text)
    text = re.sub(r"\bThe the\b", "The", text)

    # Two aliases of one person land on the same pseudonym, so an appositive
    # naming him twice collapses: "Jonathan, the son of Gershom" -> "Meses, the
    # Meses". Same effect as the doubling scan in apply_pseudonym_remap.py.
    for pseudonym in {rule[1] for rule in rules}:
        if not pseudonym:
            continue
        escaped = re.escape(pseudonym)
        text = re.sub(
            rf"(?<![A-Za-z]){escaped}(?:\s*,?\s+(?:the\s+)?{escaped})+(?![A-Za-z])",
            pseudonym,
            text,
        )
    return text


def pseudonymize_passage(
    text: str, rules: list[tuple[re.Pattern, str, str]], counts: dict[str, int]
) -> str:
    return apply_rules(text, rules, counts)


def pseudonymize_qa_value(
    value: Any,
    key: str | None,
    rules: list[tuple[re.Pattern, str, str]],
    counts: dict[str, int],
) -> Any:
    if isinstance(value, str):
        if key in QA_TEXT_FIELDS:
            return apply_rules(value, rules, counts)
        return value
    if isinstance(value, list):
        if key in QA_KEYWORD_FIELDS:
            # Keyword lists feed the RapidFuzz scorer and are lowercased there.
            return [
                apply_rules(item, rules, counts, lowercase=True)
                if isinstance(item, str)
                else item
                for item in value
            ]
        return [pseudonymize_qa_value(item, key, rules, counts) for item in value]
    if isinstance(value, dict):
        result = {}
        for inner_key, inner in value.items():
            if inner_key in QA_NESTED_CONTAINERS or isinstance(inner, (dict, list)):
                result[inner_key] = pseudonymize_qa_value(inner, inner_key, rules, counts)
            else:
                result[inner_key] = pseudonymize_qa_value(inner, inner_key, rules, counts)
        return result
    return value


def scan_leaks(text: str, entities: list[dict]) -> dict[str, int]:
    """Report canonical names that survived. Should be empty."""
    leaks: dict[str, int] = {}
    for entity in entities:
        # Generic entities ("woman", "armor-bearer") are deliberately left
        # alone by the map's generic policy -- pseudonym == canonical. Counting
        # them as leaks makes the report noisy enough to be ignored, which
        # defeats the one check standing between a leak and a scored run.
        if entity.get("pseudonym") == entity.get("canonical"):
            continue
        for alias in entity.get("aliases") or [entity["canonical"]]:
            hits = len(
                re.findall(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", text)
            )
            if hits:
                leaks[alias] = leaks.get(alias, 0) + hits
    return leaks


def collect_strings(value: Any, key: str | None, out: list[str]) -> None:
    if isinstance(value, str):
        if key in QA_TEXT_FIELDS or key in QA_KEYWORD_FIELDS:
            out.append(value)
    elif isinstance(value, list):
        for item in value:
            collect_strings(item, key, out)
    elif isinstance(value, dict):
        for inner_key, inner in value.items():
            collect_strings(inner, inner_key, out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument(
        "--passage-id",
        help=(
            "Restrict the table to entities scoped to this passage (the map's "
            "`passages` field, e.g. judg_17_1-18_31). Required whenever one map "
            "covers several passages that reuse a name: the Tier 1 set has two "
            "men called Jonathan, and without scoping one passage gets the "
            "other's pseudonym. Entities with no `passages` field always apply."
        ),
    )
    parser.add_argument("--passage", type=Path, help="English passage .txt")
    parser.add_argument("--qa", type=Path, help="English QA .json")
    parser.add_argument("--out-passage", type=Path)
    parser.add_argument("--out-qa", type=Path)
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Write outputs here using the input filenames.",
    )
    parser.add_argument("--report", action="store_true", help="Print per-entity counts.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not write; report only."
    )
    return parser.parse_args()


def resolve_output(
    explicit: Path | None, out_dir: Path | None, source: Path
) -> Path:
    if explicit:
        return explicit
    if out_dir:
        return out_dir / source.name
    raise PseudonymError(
        f"no output path for {source}; pass --out-dir or an explicit --out-* flag"
    )


def main() -> int:
    args = parse_args()
    if not args.passage and not args.qa:
        print("error: pass --passage and/or --qa", file=sys.stderr)
        return 1

    try:
        entities = scope_to_passage(load_table(args.table), args.passage_id)
        if args.passage_id and not entities:
            raise PseudonymError(
                f"no entities scoped to passage id {args.passage_id!r} in {args.table}"
            )
        rules = build_rules(entities)
        counts: dict[str, int] = {}
        leaks: dict[str, int] = {}

        if args.passage:
            source = args.passage.read_text(encoding="utf-8")
            result = pseudonymize_passage(source, rules, counts)
            for alias, hits in scan_leaks(result, entities).items():
                leaks[alias] = leaks.get(alias, 0) + hits
            if not args.dry_run:
                target = resolve_output(args.out_passage, args.out_dir, args.passage)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(result, encoding="utf-8")
                print(f"passage -> {target}")

        if args.qa:
            data = json.loads(args.qa.read_text(encoding="utf-8"))
            result_data = pseudonymize_qa_value(data, None, rules, counts)
            strings: list[str] = []
            collect_strings(result_data, None, strings)
            for alias, hits in scan_leaks("\n".join(strings), entities).items():
                leaks[alias] = leaks.get(alias, 0) + hits
            if not args.dry_run:
                target = resolve_output(args.out_qa, args.out_dir, args.qa)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps(result_data, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8",
                )
                print(f"qa      -> {target}")

    except (PseudonymError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    total = sum(counts.values())
    print(f"replaced {total} mention(s) across {len(counts)} entity/entities")
    if args.report:
        for name, hits in sorted(counts.items(), key=lambda item: -item[1]):
            print(f"  {hits:4d}  {name}")
    if leaks:
        print("LEAKS (canonical names surviving in output):", file=sys.stderr)
        for alias, hits in sorted(leaks.items(), key=lambda item: -item[1]):
            print(f"  {hits:4d}  {alias}", file=sys.stderr)
        return 2
    print("no canonical-name leaks detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
