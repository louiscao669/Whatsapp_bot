#!/usr/bin/env python3
"""Audit and repair an LLM-generated pseudonym name map before it is applied.

``build_passage_name_map.py`` uses an LLM to *propose* entities. On the Tier 1
set that proposal contained four classes of defect, two of which silently
corrupt every passage rather than merely leaking a name:

  A. PRONOUN ALIASES -- "Paul" carried aliases ``he`` and ``him``. Applied, that
     rewrites every third-person pronoun in all ten passages to one pseudonym.
  B. BARE GENERIC ALIASES -- "Jeroboam" carried ``king`` and ``the king``. These
     passages contain Uzziah, Joash, Jehoram, Ben-Hadad and David; every generic
     "the king" would become Jeroboam.
  C. CLAUSE ALIASES -- ``God repaid the wickedness``, ``city used to be called
     Laish``, ``the third story``. Substituting these deletes narrative content
     the questions ask about.
  D. CROSS-ENTITY COLLISIONS -- ``man of God`` claimed by both Elisha and the
     Man of God from Judah; three separate deity entries competing for ``God``
     and ``the Lord`` with three different pseudonyms.

Detection is deliberately conservative and rule-based, and every edit is printed.
An alias survives only if it (1) is not a pronoun or bare common noun, (2) still
contains its entity's canonical name, and (3) has no finite verb and no "and".
Rule (2) is what separates a referring expression ("the citizens of Shechem")
from a description ("place west of Kiriath Jearim").

Policy decisions applied (see --help for how to change them):
  * generics stay in plain English -- pseudonym_en is reset to the canonical, so
    "lion" stays "lion". This restores build_passage_name_map's own documented
    "generic -> not substituted" policy, which the LLM overrode.
  * deity entries are merged to one, and Yahweh folded in, so the same deity has
    the same pseudonym everywhere.

Usage (from repo root):

    python evaluation/scripts/pseudonyms/audit_name_map.py \\
      --map evaluation/datasets/pseudonym_remap/name_map_tier1.json --report

    python evaluation/scripts/pseudonyms/audit_name_map.py \\
      --map evaluation/datasets/pseudonym_remap/name_map_tier1.json \\
      --out evaluation/datasets/pseudonym_remap/name_map_tier1_audited.json

    python evaluation/scripts/pseudonyms/audit_name_map.py --self-test
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

PRONOUNS = {"he", "him", "his", "she", "her", "hers", "they", "them", "their", "it", "its"}

# Bare common nouns that must never stand for a named entity.
BARE_GENERIC = {
    "king", "the king", "a king", "queen", "the queen",
    "priest", "the priest", "a priest", "prophet", "the prophet", "a prophet",
    "man", "the man", "woman", "a woman", "the woman", "men", "sons", "his sons",
    "son", "the son", "servant", "his servant", "prisoner", "the prisoner",
    "governor", "the governor", "commander", "the commander",
    "centurion", "the centurion", "elders", "the elders",
    "angel", "an angel", "lion", "donkey", "altar", "city", "his own city",
    "man of god", "the man of god",
}

# Finite verbs that mark a clause rather than a name.
CLAUSE_VERB = re.compile(
    r"\b(was|were|is|are|be|been|had|has|have|did|does|do|may|might|will|would|"
    r"could|should|gave|give|repaid|stirred|listen|used|called|dropped|brought|"
    r"lived|went|came|said|made|took|set|struck)\b",
    re.IGNORECASE,
)

# Entities whose canonical is a common noun: keep them in plain English.
# Gentilics (-ite) and register terms derived from a blinded place are NOT here,
# because leaving "Bethlehemite" or "Gittite" would leak Bethlehem and Gath.
GENERIC_CANONICALS = {
    "a woman", "altar", "angel", "armor-bearer", "centurion", "chief priests",
    "commander", "donkey", "elders", "lamp of Israel", "lion", "oak tree",
    "priests of the high places", "sons of the old prophet", "the priest",
}

# Deity entries to collapse into one, and the identity they collapse to.
DEITY_MERGE = {"God", "Lord", "the Lord"}
DEITY_CANONICAL = "the Lord"
DEITY_EXTRA_ALIASES = ["Yahweh", "the LORD", "LORD", "Lord God", "the Lord your God", "God"]


class AuditError(Exception):
    pass


def head_tokens(canonical: str) -> list[str]:
    """Tokens that a genuine alias of this entity should still contain."""
    words = re.findall(r"[A-Za-z][\w'’-]*", canonical)
    skip = {"of", "the", "son", "from", "in", "a", "an", "where", "who", "lived"}
    kept = [w for w in words if w.lower() not in skip]
    return kept or words


def alias_defect(alias: str, canonical: str) -> str | None:
    lowered = alias.strip().lower()
    if lowered in PRONOUNS:
        return "pronoun"
    if lowered in BARE_GENERIC and canonical.lower() not in BARE_GENERIC:
        return "bare generic"
    if " and " in lowered:
        return "conjunction"
    if CLAUSE_VERB.search(alias):
        return "clause"
    tokens = [token.lower() for token in head_tokens(canonical)]
    if any(token in lowered for token in tokens):
        return None
    # Morphological variants share a stem rather than a substring: "Sidon" is a
    # real alias of "Sidonians", "Eloth" of "Elath". Require a 4-character common
    # prefix, which admits those without admitting unrelated names.
    alias_tokens = re.findall(r"[A-Za-z][\w'’-]*", lowered)
    for token in tokens:
        for word in alias_tokens:
            shared = 0
            for a, b in zip(token, word):
                if a != b:
                    break
                shared += 1
            if shared >= 4:
                return None
    return "description (no canonical token)"


def audit(
    data: dict,
    keep_generics_blind: bool,
    same_entity: dict[str, list[str]] | None = None,
) -> tuple[dict, list[str]]:
    entities = [dict(entity) for entity in data["entities"]]
    log: list[str] = []

    def fold_same_entities() -> None:
        """Fold entities the extraction split apart.

        The LLM sees one participant under two descriptions and emits two
        entities with two different pseudonyms. Judges 18:30 is the clean case:
        "the Levite" of chapters 17-18 IS "Jonathan son of Gershom son of
        Moses", named only at the very end. Split, the expected answer for that
        item names someone the passage never introduced, and it is unscoreable.

        This runs AFTER alias hygiene on purpose. The folded aliases belong to
        the other entity's canonical, so the "alias must contain its canonical"
        rule would delete every one of them on the way in.
        """
        nonlocal entities
        for primary, others in (same_entity or {}).items():
            by_canonical = {entity["canonical"]: entity for entity in entities}
            if primary not in by_canonical:
                raise AuditError(
                    f"--same-entity {primary!r}: not a canonical name in the map."
                )
            target = by_canonical[primary]
            for other in others:
                if other not in by_canonical:
                    raise AuditError(
                        f"--same-entity {primary}={other}: {other!r} is not a "
                        "canonical name in the map."
                    )
                merged = by_canonical[other]
                target["aliases"] = sorted(
                    set(target.get("aliases") or [])
                    | set(merged.get("aliases") or [])
                    | {merged["canonical"]},
                    key=len,
                    reverse=True,
                )
                target["passages"] = sorted(
                    set(target.get("passages") or []) | set(merged.get("passages") or [])
                )
                entities = [e for e in entities if e["canonical"] != other]
                log.append(
                    f"  same  {other!r} folded into {primary!r} "
                    f"(-> {target['pseudonym_en']} / {target['pseudonym_zh']}, "
                    f"{len(target['aliases'])} aliases)"
                )

    # --- A/B/C: alias hygiene -------------------------------------------------
    for entity in entities:
        canonical = entity["canonical"]
        kept, seen = [], set()
        for alias in entity.get("aliases") or [canonical]:
            defect = alias_defect(alias, canonical)
            if defect:
                log.append(f"  drop  {canonical:32s} {alias!r:46s} [{defect}]")
                continue
            if alias.lower() in seen:
                log.append(f"  dedup {canonical:32s} {alias!r}")
                continue
            seen.add(alias.lower())
            kept.append(alias)
        if not kept:
            kept = [canonical]
            log.append(f"  keep  {canonical:32s} (all aliases dropped; canonical retained)")
        entity["aliases"] = kept

    fold_same_entities()

    # --- D1: merge the deity entries -----------------------------------------
    deities = [e for e in entities if e["canonical"] in DEITY_MERGE]
    if deities:
        primary = next((e for e in deities if e["canonical"] == DEITY_CANONICAL), deities[0])
        merged_aliases = set(DEITY_EXTRA_ALIASES)
        for entity in deities:
            merged_aliases.update(entity.get("aliases") or [])
        # Prefer the Luke-consistent rendering if one of the merged entries has it.
        pseudonym_en = next(
            (e["pseudonym_en"] for e in deities if e["pseudonym_en"].startswith("the ")),
            primary["pseudonym_en"],
        )
        pseudonym_zh = next(
            (e["pseudonym_zh"] for e in deities if e["pseudonym_zh"] in ("至高者", "主宰", "主上")),
            primary["pseudonym_zh"],
        )
        log.append(
            f"  merge deity {sorted(e['canonical'] for e in deities)} -> "
            f"{DEITY_CANONICAL!r} = {pseudonym_en} / {pseudonym_zh} (+Yahweh)"
        )
        primary = {
            **primary,
            "canonical": DEITY_CANONICAL,
            "type": "deity",
            "aliases": sorted(merged_aliases, key=len, reverse=True),
            "pseudonym_en": pseudonym_en,
            "pseudonym_zh": pseudonym_zh,
        }
        entities = [e for e in entities if e["canonical"] not in DEITY_MERGE] + [primary]

    # --- D2: remaining cross-entity alias collisions --------------------------
    owner = collections.defaultdict(list)
    for entity in entities:
        for alias in entity["aliases"]:
            owner[alias.lower()].append(entity)
    for alias, claimants in sorted(owner.items()):
        if len(claimants) < 2:
            continue
        # Claimants that never appear in the same passage are not in conflict:
        # there are two men named Jonathan in the Tier 1 set, one in Judges 17-18
        # and one in 2 Samuel 21, and each should keep the bare alias for its own
        # passage. Stripping it from one of them, as an earlier version did, gave
        # Judges 18:30 the 2 Samuel pseudonym and corrupted the expected answer.
        # Application is passage-scoped (pseudonymize_english_source.py
        # --passage-id), so disjoint claimants can safely coexist.
        passages = [set(e.get("passages") or []) for e in claimants]
        shared = any(
            passages[i] & passages[j]
            for i in range(len(passages))
            for j in range(i + 1, len(passages))
        )
        if not shared:
            log.append(
                f"  ok    {alias!r} shared by {[e['canonical'] for e in claimants]} "
                "but passages are disjoint; kept on both"
            )
            continue
        winner = min(claimants, key=lambda e: (len(e["canonical"]), e["canonical"]))
        for entity in claimants:
            if entity is winner:
                continue
            entity["aliases"] = [a for a in entity["aliases"] if a.lower() != alias]
            if not entity["aliases"]:
                entity["aliases"] = [entity["canonical"]]
            log.append(
                f"  collide {alias!r} -> kept by {winner['canonical']!r}, "
                f"removed from {entity['canonical']!r}"
            )

    # --- generics policy ------------------------------------------------------
    if not keep_generics_blind:
        for entity in entities:
            if entity["canonical"] in GENERIC_CANONICALS:
                log.append(
                    f"  generic {entity['canonical']:28s} "
                    f"en {entity['pseudonym_en']} -> (unchanged)"
                )
                entity["pseudonym_en"] = entity["canonical"]

    entities.sort(key=lambda e: e["canonical"].lower())
    return {**data, "entities": entities, "audited": True}, log


def verify(data: dict) -> list[str]:
    problems = []
    owner = collections.defaultdict(list)
    for entity in data["entities"]:
        canonical = entity["canonical"]
        for alias in entity["aliases"]:
            if alias.strip().lower() in PRONOUNS:
                problems.append(f"pronoun alias survives: {canonical} <- {alias!r}")
            if alias.strip().lower() in BARE_GENERIC and canonical.lower() not in BARE_GENERIC:
                problems.append(f"bare generic survives: {canonical} <- {alias!r}")
            owner[alias.lower()].append(canonical)
    scope = {e["canonical"]: set(e.get("passages") or []) for e in data["entities"]}
    for alias, owners in owner.items():
        names = sorted(set(owners))
        if len(names) < 2:
            continue
        if any(
            scope[a] & scope[b]
            for i, a in enumerate(names)
            for b in names[i + 1:]
        ):
            problems.append(f"alias shared within a passage: {alias!r} by {names}")
    return problems


def self_test() -> int:
    data = {
        "entities": [
            {"canonical": "Paul", "type": "person", "pseudonym_en": "Tilir",
             "pseudonym_zh": "卡姆", "aliases": ["Paul", "he", "him", "the prisoner"]},
            {"canonical": "Jeroboam", "type": "person", "pseudonym_en": "Vuvur",
             "pseudonym_zh": "诺恒", "aliases": ["King Jeroboam", "Jeroboam", "the king", "king"]},
            {"canonical": "Troas", "type": "place", "pseudonym_en": "Lamar",
             "pseudonym_zh": "兰恒地", "aliases": ["Troas", "the third story"]},
            {"canonical": "lion", "type": "role", "pseudonym_en": "Mases",
             "pseudonym_zh": "兰恩", "aliases": ["lion"]},
            {"canonical": "God", "type": "deity", "pseudonym_en": "the Sovereign",
             "pseudonym_zh": "至高者", "aliases": ["God", "God repaid the wickedness"]},
            {"canonical": "the Lord", "type": "deity", "pseudonym_en": "Lavum",
             "pseudonym_zh": "迦温", "aliases": ["the Lord", "God"]},
        ]
    }
    out, _ = audit(json.loads(json.dumps(data)), keep_generics_blind=False)
    by = {e["canonical"]: e for e in out["entities"]}

    checks = [
        ("pronouns dropped", "he" not in by["Paul"]["aliases"] and "him" not in by["Paul"]["aliases"]),
        ("bare 'king' dropped", "king" not in by["Jeroboam"]["aliases"]),
        ("'King Jeroboam' kept", "King Jeroboam" in by["Jeroboam"]["aliases"]),
        ("clause alias dropped", "the third story" not in by["Troas"]["aliases"]),
        ("lion left in English", by["lion"]["pseudonym_en"] == "lion"),
        ("deities merged", "God" not in by and "the Lord" in by),
        ("Yahweh folded in", "Yahweh" in by["the Lord"]["aliases"]),
        ("no residual problems", not verify(out)),
    ]
    failed = 0
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed += not ok
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--report", action="store_true", help="Print every edit.")
    parser.add_argument("--keep-generics-blind", action="store_true",
                        help="Keep invented English names for lion/donkey/altar/etc.")
    parser.add_argument("--same-entity", action="append", default=[],
                        metavar="PRIMARY=OTHER",
                        help="Two canonicals that are one participant; OTHER is "
                             "folded into PRIMARY. Repeatable.")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if not args.map:
        print("error: --map is required (or use --self-test)", file=sys.stderr)
        return 2

    try:
        data = json.loads(args.map.read_text(encoding="utf-8"))
        if not data.get("entities"):
            raise AuditError(f"{args.map} contains no entities.")
        before = len(data["entities"])
        alias_before = sum(len(e.get("aliases") or []) for e in data["entities"])
        same_entity: dict[str, list[str]] = {}
        for spec in args.same_entity:
            if "=" not in spec:
                raise AuditError(f"--same-entity expects PRIMARY=OTHER, got {spec!r}")
            primary, other = spec.split("=", 1)
            same_entity.setdefault(primary.strip(), []).append(other.strip())
        data, log = audit(data, args.keep_generics_blind, same_entity)
    except (AuditError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.report:
        print("\n".join(log) or "  (no edits)")
        print()

    after = len(data["entities"])
    alias_after = sum(len(e["aliases"]) for e in data["entities"])
    print(f"entities {before} -> {after}   aliases {alias_before} -> {alias_after}   "
          f"({len(log)} edit(s))")

    problems = verify(data)
    if problems:
        print(f"\n{len(problems)} problem(s) remain:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print("verify: no pronoun aliases, no bare generics, no shared aliases")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
