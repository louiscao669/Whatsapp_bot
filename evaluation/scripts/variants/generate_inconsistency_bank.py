#!/usr/bin/env python3
"""Generate a per-chapter, identity-preserving inconsistency swap bank.

Problem this solves
-------------------
The old inconsistency swap bank was a single global, hardcoded dict keyed on a
handful of surface forms (人物甲, 约翰 ...). It (a) missed most entities, because
real passages are dominated by *per-chapter* numbered placeholders (人物01,
地点01, 角色01 ...) that were never in the bank, and (b) when it did fire it
replaced an entity with an unrelated invented name (人物甲 -> 诺兰甲), destroying
identity so the answer model could no longer resolve the referent.

What this generator produces
----------------------------
For each LOCAL entity placeholder that appears in a chapter, it emits recoverable
surface variants that a reader/model can still map back to the SAME entity:

    人物01  ->  ["人物一", "人物1"]      # numeral-format inconsistency, same number
    地点02  ->  ["地点二", "地点2"]

These are pure numeral-format variations (zero-padded arabic vs. hanzi vs.
unpadded) — no added content (not an Addition), and the entity's number is
preserved so identity is recoverable (not a Mistranslation-of-referent).

Collision guarantee (the key requirement)
-----------------------------------------
Every emitted variant is checked to NOT equal any term in:
  * the chapter's LOCAL decanonicalization mapping (entity sources, aliases,
    placeholders, protected tokens, english/chinese maps), and
  * the GLOBAL decanonicalization mapping (DEFAULT_MAPPING +
    DEFAULT_ENGLISH_TOKEN_MAPPING, keys and values).
So a variant can never collide with another entity's placeholder or a canonical
name — it cannot be mistaken for a different (local or global) entity. That is
what prevents identity destruction.

By design the bank only perturbs the per-chapter LOCAL numbered placeholders.
The global/doctrinal entities (God/Lord/Jesus/John/Holy Spirit -> 至高者甲/主人甲/
人物丙 ...) are left untouched, per the requirement to exclude all global-mapping
terms. Pass --include-global to also emit (collision-checked) variants for the
global-stem placeholders present in the chapter.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

# Local placeholder pattern: a Chinese type morpheme followed by ASCII digits,
# e.g. 人物01, 地点2, 角色03.  (Global placeholders use 甲/乙/丙 stems, not digits.)
LOCAL_PLACEHOLDER_RE = re.compile(r"^(?P<type>[㐀-鿿]+?)(?P<num>\d{1,3})$")

_HANZI_DIGITS = "零一二三四五六七八九"


def hanzi_number(n: int) -> str:
    """1 -> 一, 10 -> 十, 12 -> 十二, 20 -> 二十, 21 -> 二十一 (covers 0..99)."""
    if n < 0:
        return str(n)
    if n < 10:
        return _HANZI_DIGITS[n]
    if n < 20:
        return "十" + (_HANZI_DIGITS[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        return _HANZI_DIGITS[tens] + "十" + (_HANZI_DIGITS[ones] if ones else "")
    return str(n)


def load_global_reserved() -> set[str]:
    """All keys and values of the global decanonicalization mappings."""
    reserved: set[str] = set()
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from evaluation.scripts.data_prep.decanonicalize_chinese_dataset import (  # type: ignore
            DEFAULT_MAPPING,
            DEFAULT_ENGLISH_TOKEN_MAPPING,
        )
        for mapping in (DEFAULT_MAPPING, DEFAULT_ENGLISH_TOKEN_MAPPING):
            reserved.update(mapping.keys())
            reserved.update(mapping.values())
    except Exception as exc:  # pragma: no cover - import guard
        print(f"WARNING: could not import global mappings ({exc}); "
              "proceeding with local reserved terms only.", file=sys.stderr)
    return reserved


def load_inventory(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def local_reserved_terms(inv: dict[str, Any]) -> set[str]:
    """Every surface form tied to any entity in this chapter."""
    reserved: set[str] = set()
    for e in inv.get("entities", []):
        for k in ("source", "placeholder", "protected_token"):
            if e.get(k):
                reserved.add(str(e[k]))
        for lst in (e.get("aliases"), e.get("chinese_aliases")):
            for a in (lst or []):
                reserved.add(str(a))
    for mp in ("english_mapping", "chinese_mapping"):
        for k, v in (inv.get(mp) or {}).items():
            reserved.add(str(k))
            reserved.add(str(v))
    return reserved


def variant_candidates(placeholder: str) -> list[str]:
    """Recoverable, addition-free surface variants of a numbered placeholder.

    All keep the type morpheme AND the exact number, so identity is recoverable;
    they only vary how the number is written (or its position)."""
    m = LOCAL_PLACEHOLDER_RE.match(placeholder)
    if not m:
        return []
    typ, num = m.group("type"), int(m.group("num"))
    return [
        f"{typ}{hanzi_number(num)}",   # 人物01 -> 人物一   (hanzi numeral)
        f"{typ}{num}",                 # 人物01 -> 人物1    (unpadded arabic)
        f"{num}{typ}",                 # 人物01 -> 1人物    (reorder, fallback)
    ]


def build_bank(inv: dict[str, Any], global_reserved: set[str],
               include_global: bool) -> dict[str, Any]:
    reserved = set(global_reserved) | local_reserved_terms(inv)

    # entities to perturb: local numbered placeholders by default
    placeholders = []
    skipped_global = []
    for e in inv.get("entities", []):
        ph = str(e.get("placeholder") or "")
        if LOCAL_PLACEHOLDER_RE.match(ph):
            placeholders.append(ph)
        else:
            skipped_global.append(ph)
    placeholders = sorted(set(placeholders))

    used: set[str] = set(reserved)
    variants: dict[str, list[str]] = {}
    unresolved: list[str] = []
    for ph in placeholders:
        cands = [c for c in variant_candidates(ph)
                 if c != ph and c not in used]
        # de-dup while preserving order
        picked: list[str] = []
        for c in cands:
            if c not in picked:
                picked.append(c)
        if not picked:
            unresolved.append(ph)
            continue
        variants[ph] = picked
        used.update(picked)   # keep every emitted variant disjoint too

    bank = {
        "schema_version": 1,
        "type": "name",
        "scheme": "identity-preserving numeral-format variants "
                  "(type + same number, varied numeral surface)",
        "excludes": "all local + global decanonicalization terms",
        "variants": variants,
        "n_entities": len(variants),
        "unresolvable_placeholders": unresolved,
        "skipped_global_placeholders": sorted(set(skipped_global)),
    }
    if include_global:
        bank["note_global"] = ("--include-global was set but global-stem variant "
                               "generation is intentionally left to a reviewer; "
                               "doctrinal entities are sensitive.")
    return bank


def verify_disjoint(bank: dict[str, Any], global_reserved: set[str],
                    inv: dict[str, Any]) -> list[str]:
    """Return a list of any variant that collides with a reserved term."""
    reserved = set(global_reserved) | local_reserved_terms(inv)
    problems = []
    seen: dict[str, str] = {}
    for ph, vs in bank["variants"].items():
        for v in vs:
            if v in reserved:
                problems.append(f"{ph} -> {v} collides with a decanon term")
            if v in seen:
                problems.append(f"{ph} -> {v} collides with {seen[v]}'s variant")
            seen[v] = ph
    return problems


def default_inventory_path(root: Path, chapter: int, model_dir: str) -> Path:
    base = root / f"luke{chapter}" / model_dir / "_shared"
    hits = sorted(base.glob("*entity_inventory*.json"))
    if not hits:
        raise FileNotFoundError(f"No entity inventory under {base}")
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=REPO_ROOT / "evaluation" / "outputs")
    ap.add_argument("--model-dir", default="1.7b",
                    help="Answer-model tree to read the entity inventory from.")
    ap.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    ap.add_argument("--out-template",
                    default=str(REPO_ROOT / "evaluation" / "datasets"
                                / "chapter_local_inconsistency_banks"
                                / "inconsistency_bank_luke{chapter}.json"),
                    help="Where to write each chapter bank ({chapter} is filled).")
    ap.add_argument("--include-global", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print banks instead of writing them.")
    args = ap.parse_args()

    global_reserved = load_global_reserved()
    any_problem = False
    for ch in args.chapters:
        inv_path = default_inventory_path(args.root, ch, args.model_dir)
        inv = load_inventory(inv_path)
        bank = build_bank(inv, global_reserved, args.include_global)
        bank["chapter"] = ch
        bank["source_inventory"] = str(inv_path)

        problems = verify_disjoint(bank, global_reserved, inv)
        status = "OK" if not problems else f"{len(problems)} COLLISIONS"
        print(f"luke{ch}: {bank['n_entities']} entities -> variants  [{status}]"
              + (f"  unresolved={bank['unresolvable_placeholders']}"
                 if bank["unresolvable_placeholders"] else ""))
        for p in problems:
            any_problem = True
            print(f"    !! {p}", file=sys.stderr)

        if args.dry_run:
            print(json.dumps(bank, ensure_ascii=False, indent=2))
        else:
            out = Path(args.out_template.format(chapter=ch))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(bank, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            print(f"    wrote {out}")

    return 1 if any_problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
