#!/usr/bin/env python3
"""Extract every proper name from arbitrary passages and assign pseudonyms.

Why this exists
---------------
``build_english_pseudonyms.py`` derives its entity list from
``datasets/pseudonym_remap/_master.json``, which only exists for Luke 1-8 --
it is a by-product of the Chinese-side canonicalization that was run on those
chapters. Any new passage (the Tier 1 obscure narratives in
``datasets/obscure_narrative_passages_tier1.csv``, or any other book) has no
such file, so entities have to be discovered from the passage text itself.

This script does that discovery with an LLM, validates the result, assigns a
pseudonym in **both** English and the target language, and freezes everything to
JSON. The LLM is used only to *propose* the entity list; nothing downstream calls
a model, so the map is stable and auditable once written.

Output shape (one record per entity):

    {"canonical": "Jesus", "type": "person", "gender": "m",
     "aliases": ["Jesus Christ", "Christ"],
     "pseudonym_en": "Marun", "pseudonym_zh": "玛伦",
     "source": "reused" | "generated", "passages": ["judg_9_1-57"]}

``pseudonym_en`` feeds ``pseudonymize_english_source.py`` (pre-translation
blinding). ``pseudonym_zh`` gives a target-side table for leak scanning and for
normalizing transliteration variants after translation.

Continuity: entities already present in ``_master.json`` or
``english_pseudonyms.json`` keep their committed pseudonyms, so Luke 1-8 output
does not churn and old and new material stay comparable. Only genuinely new
entities get freshly generated names.

Usage (from repo root):

    export OPENAI_API_KEY=...

    # one or more passages
    python evaluation/scripts/pseudonyms/build_passage_name_map.py \\
      --passage evaluation/datasets/passages/test_passage_luke5.txt \\
      --out evaluation/datasets/pseudonym_remap/name_map_luke5.json

    # a whole directory, merged into one map
    python evaluation/scripts/pseudonyms/build_passage_name_map.py \\
      --passage-dir evaluation/datasets/passages \\
      --out evaluation/datasets/pseudonym_remap/name_map_luke1-8.json --report

    # audit the candidate list without calling the API
    python evaluation/scripts/pseudonyms/build_passage_name_map.py \\
      --passage ... --dry-run

    # offline self-check of assignment and collision logic
    python evaluation/scripts/pseudonyms/build_passage_name_map.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVAL_DIR = Path(__file__).resolve().parents[2]
MASTER = EVAL_DIR / "datasets/pseudonym_remap/_master.json"
ENGLISH_TABLE = EVAL_DIR / "datasets/pseudonym_remap/english_pseudonyms.json"

SUBSTITUTED_TYPES = {"person", "place", "people", "deity", "role", "text"}

# Deity titles are fixed rather than generated: register matters for judging
# translation quality, and an invented name would lose it. "Master" is excluded
# because Simon addresses Jesus as "Master" in Luke 5:5.
DEITY_TITLES = {
    "God": ("the Sovereign", "至高者"),
    "Lord": ("the Supreme One", "主上"),
    "Most High": ("the Exalted One", "至尊"),
    "Holy Spirit": ("the Sacred Spirit", "圣灵"),
    "Messiah": ("the Chosen One", "救主"),
    "Son of Man": ("the Son of Humanity", "人子"),
    "devil": ("the Adversary", "魔君"),
    "Satan": ("the Adversary", "魔君"),
}

# English name generation. Voiceless-stop codas were removed after they produced
# strings that read as noise rather than names.
ONSET = ["D", "T", "K", "L", "M", "N", "R", "S", "V", "B", "G", "H"]
NUCLEUS = ["a", "e", "i", "o", "u"]
MEDIAL = ["r", "l", "n", "m", "v", "d", "s", "t"]
CODA_M = ["n", "r", "l", "m", "s", "th"]
CODA_F = ["a", "ia", "ela", "ina", "ora", "eva"]
PLACE_TAIL = ["dor", "mar", "nel", "tas", "ven", "rin", "sol", "kal", "pen", "lor"]

# Chinese transliteration syllables, matching the register of the committed
# pseudonyms in _master.json (玛伦, 芮茉, 迦洛地).
ZH_FIRST = "玛米诺维卡兰珂洛塞迦泰隆慕韦黛珈弗瓦尼利芮"
ZH_SECOND_M = "伦顿松恩德斯温磐昂图里罗谷姆恒朗达"
ZH_SECOND_F = "茉丽娜妮岚苔莎兰珊黛"
ZH_PLACE_SUFFIX = {"region": "地", "city": "城", "village": "村"}

BLOCKLIST = {
    "kodak", "sedan", "salon", "melon", "talon", "ramen", "demon", "lemon",
    "roman", "satan", "sodom", "simon", "amen", "omen", "human", "nomad",
    "radar", "level", "model", "moral", "total", "minor", "major", "manor",
    "donor", "tenor", "lunar", "solar", "sonar", "altar", "cedar", "satin",
    "latin", "cabin", "robin", "resin", "basin", "virus", "minus", "bonus",
    "venus", "koran", "lorem", "tabor", "moses", "allah", "titan", "siren",
    "raven", "haven", "heron", "baron", "bison", "gives", "gamer", "salim",
    "nives", "dadan", "dedan", "kaon", "bidon", "gomer", "hamor", "lotan",
    "hodor", "kotor", "notas", "datum", "serum", "torus",
}

FEMALE_HINTS = {
    "mary", "elizabeth", "anna", "joanna", "susanna", "herodias", "magdalene",
    "martha", "rachel", "leah", "sarah", "rebekah", "ruth", "naomi", "esther",
    "deborah", "hannah", "abigail", "bathsheba", "jezebel", "athaliah",
    "delilah", "miriam", "tamar", "dinah", "rahab", "priscilla", "lydia",
    "phoebe", "junia", "eunice", "lois", "salome", "candace", "damaris",
}


class NameMapError(Exception):
    pass


# --------------------------------------------------------------------------
# offline candidate scan (used for --dry-run and to sanity-check LLM recall)


SENTENCE_START = re.compile(r"(?:^|[.!?\"“”\n]\s*)$")
STOPWORDS = {
    "The", "But", "And", "Then", "For", "They", "You", "This", "That", "When",
    "While", "Now", "Who", "What", "Why", "How", "All", "Your", "His", "Her",
    "She", "He", "Him", "Them", "We", "Our", "Us", "My", "Me", "It", "Its",
    "There", "Here", "Some", "Many", "Every", "Everyone", "Those", "These",
    "After", "Before", "With", "Without", "Because", "Since", "If", "So",
    "Truly", "Blessed", "Woe", "Look", "Listen", "Come", "Go", "Do", "Did",
    "Let", "Take", "Give", "Rise", "Stand", "Immediately", "Meanwhile",
    "Suddenly", "Today", "Otherwise", "Therefore", "Someone", "Once", "Both",
    "Even", "Yet", "Also", "Still", "Again", "One", "Two", "Three", "Sir",
    "Lord", "Master", "Father", "Son", "Man", "Woman", "Boy", "Girl", "King",
    "Then", "Whoever", "Wherever", "Whatever", "Never", "Always", "Nothing",
}


def candidate_names(text: str) -> dict[str, int]:
    """Capitalized tokens that are not sentence-initial, with counts.

    Deliberately crude. Its job is to bound LLM recall, not to replace it: it
    misses sentence-initial names and cannot distinguish person from place.
    """
    stripped = re.sub(r"<header>.*?</header>", " ", text, flags=re.DOTALL)
    stripped = re.sub(r"\[[a-z]\]", " ", stripped)
    counts: dict[str, int] = {}
    for match in re.finditer(r"\b([A-Z][a-z]{2,})\b", stripped):
        word = match.group(1)
        if word in STOPWORDS:
            continue
        preceding = stripped[max(0, match.start() - 3) : match.start()]
        if SENTENCE_START.search(preceding):
            continue
        counts[word] = counts.get(word, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


# --------------------------------------------------------------------------
# LLM extraction


EXTRACTION_TASK = (
    "List every proper name in this Bible passage: people, places, peoples or "
    "tribes, divine titles, and identifying epithets. "
    "Rules: "
    "(1) Give each entity ONE canonical form plus every alias and epithet that "
    "appears, including possessive and multiword forms. "
    "(2) Treat an identifying epithet as its own entity when it identifies the "
    "bearer even without the name, for example 'the Baptist' or 'the Zealot'. "
    "(3) type must be one of: person, place, people, deity, role, text. "
    "(4) For person, set gender to m, f, or unknown. "
    "(5) Do NOT list common nouns (boat, shepherd, synagogue, priest) or "
    "religious category terms (Pharisees, Sabbath, Passover, Law, Temple). "
    "(6) Names that refer to the same individual must be ONE entity; names that "
    "refer to different individuals sharing a name must be SEPARATE entities, "
    "distinguished in canonical form."
)


def llm_extract_entities(
    passage_text: str, model: str, retries: int, temperature: float
) -> list[dict]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise NameMapError("Install the openai package, or use --dry-run.") from exc

    client = OpenAI()
    prompt = {
        "task": EXTRACTION_TASK,
        "passage": passage_text,
        "output_schema": {
            "entities": [
                {
                    "canonical": "string",
                    "type": "person|place|people|deity|role|text",
                    "gender": "m|f|unknown",
                    "aliases": ["string"],
                }
            ]
        },
    }

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.responses.create(
                model=model,
                temperature=temperature,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You extract named entities from Bible passages. "
                            "Return valid JSON only, no markdown."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            text = getattr(response, "output_text", "") or ""
            return validate_entities(json.loads(extract_json_object(text)))
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise NameMapError(f"entity extraction failed: {last_error}")


def extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise NameMapError("no JSON object in model response")
    return text[start : end + 1]


def validate_entities(raw: object) -> list[dict]:
    if not isinstance(raw, dict) or not isinstance(raw.get("entities"), list):
        raise NameMapError("response must be an object with an 'entities' array")

    out = []
    for item in raw["entities"]:
        if not isinstance(item, dict):
            continue
        canonical = str(item.get("canonical") or "").strip()
        entity_type = str(item.get("type") or "").strip().lower()
        if not canonical or entity_type not in SUBSTITUTED_TYPES:
            continue
        gender = str(item.get("gender") or "unknown").strip().lower()
        if gender not in {"m", "f", "unknown"}:
            gender = "unknown"
        aliases = [
            str(alias).strip()
            for alias in (item.get("aliases") or [])
            if str(alias).strip()
        ]
        out.append(
            {
                "canonical": canonical,
                "type": entity_type,
                "gender": gender,
                "aliases": sorted({canonical, *aliases}, key=len, reverse=True),
            }
        )
    if not out:
        raise NameMapError("no valid entities in response")
    return out


# --------------------------------------------------------------------------
# pseudonym assignment


def stable_seed(text: str) -> int:
    value = 0
    for char in text:
        value = (value * 131 + ord(char)) % 1_000_003
    return value


def generate_en(seed: int, entity_type: str, female: bool) -> str:
    if entity_type == "place":
        head = ONSET[seed % len(ONSET)] + NUCLEUS[(seed // 7) % len(NUCLEUS)]
        return head + PLACE_TAIL[(seed // 13) % len(PLACE_TAIL)]
    head = ONSET[seed % len(ONSET)] + NUCLEUS[(seed // 5) % len(NUCLEUS)]
    medial = MEDIAL[(seed // 11) % len(MEDIAL)]
    if female:
        return head + medial + CODA_F[(seed // 23) % len(CODA_F)]
    return head + medial + NUCLEUS[(seed // 17) % len(NUCLEUS)] + CODA_M[
        (seed // 23) % len(CODA_M)
    ]


def generate_zh(seed: int, entity_type: str, female: bool) -> str:
    first = ZH_FIRST[seed % len(ZH_FIRST)]
    pool = ZH_SECOND_F if female else ZH_SECOND_M
    second = pool[(seed // 7) % len(pool)]
    name = first + second
    if entity_type == "place":
        # Match the committed convention: 迦洛地 / 维珥顿城 / 泰洛村.
        suffix = list(ZH_PLACE_SUFFIX.values())[(seed // 11) % len(ZH_PLACE_SUFFIX)]
        return name + suffix
    return name


def conflicts(candidate: str, taken: set[str], forbidden: set[str]) -> bool:
    low = candidate.lower()
    if low in BLOCKLIST or low in {f.lower() for f in forbidden}:
        return True
    for existing in taken:
        existing_low = existing.lower()
        # Substring either way, so longest-first replacement stays unambiguous.
        if low == existing_low or low in existing_low or existing_low in low:
            return True
    return False


def load_reusable() -> tuple[dict[str, str], dict[str, str]]:
    """Committed pseudonyms, so existing entities keep their names."""
    en_map: dict[str, str] = {}
    zh_map: dict[str, str] = {}
    if ENGLISH_TABLE.exists():
        for entity in json.loads(ENGLISH_TABLE.read_text(encoding="utf-8"))["entities"]:
            en_map[entity["canonical"]] = entity["pseudonym"]
    if MASTER.exists():
        for _ch, _ph, _typ, zh, english, _zhc in json.loads(
            MASTER.read_text(encoding="utf-8")
        ):
            if english and zh:
                zh_map.setdefault(english, zh)
    return en_map, zh_map


def assign(entities: list[dict]) -> list[dict]:
    reuse_en, reuse_zh = load_reusable()

    # Collapse duplicate canonicals defensively. merge_entities() already does
    # this for the normal path, but assign() is also called directly (tests,
    # future callers) and two records for one entity would look like a
    # pseudonym collision downstream.
    deduped: dict[str, dict] = {}
    for entity in entities:
        existing = deduped.get(entity["canonical"])
        if existing is None:
            deduped[entity["canonical"]] = dict(entity)
            continue
        existing["aliases"] = sorted(
            set(existing["aliases"]) | set(entity["aliases"]), key=len, reverse=True
        )
        if existing.get("gender", "unknown") == "unknown":
            existing["gender"] = entity.get("gender", "unknown")
        existing["passages"] = sorted(
            set(existing.get("passages", [])) | set(entity.get("passages", []))
        )
    entities = list(deduped.values())

    forbidden = set()
    for entity in entities:
        forbidden.add(entity["canonical"])
        forbidden.update(entity["canonical"].split())
        forbidden.update(entity["aliases"])

    taken_en: set[str] = set()
    taken_zh: set[str] = set()
    records = []

    # Reused names are claimed first so generation cannot collide with them.
    for entity in entities:
        name = entity["canonical"]
        if name in reuse_en:
            taken_en.add(reuse_en[name])
        if name in reuse_zh:
            taken_zh.add(reuse_zh[name])

    for entity in sorted(entities, key=lambda e: e["canonical"]):
        name = entity["canonical"]
        entity_type = entity["type"]
        female = entity["gender"] == "f" or name.lower() in FEMALE_HINTS

        if entity_type == "deity" and name in DEITY_TITLES:
            pseudo_en, pseudo_zh = DEITY_TITLES[name]
            source = "deity_title"
        elif entity_type == "text":
            pseudo_en, pseudo_zh, source = "this account", "本记述", "text_title"
        else:
            pseudo_en = reuse_en.get(name)
            pseudo_zh = reuse_zh.get(name)
            source = "reused" if (pseudo_en or pseudo_zh) else "generated"

            seed = stable_seed(name)
            if not pseudo_en:
                for attempt in range(500):
                    candidate = generate_en(seed + attempt * 9973, entity_type, female)
                    if not conflicts(candidate, taken_en, forbidden):
                        pseudo_en = candidate
                        break
                else:
                    raise NameMapError(f"no English pseudonym available for {name!r}")
            if not pseudo_zh:
                for attempt in range(500):
                    candidate = generate_zh(seed + attempt * 7919, entity_type, female)
                    if not conflicts(candidate, taken_zh, forbidden):
                        pseudo_zh = candidate
                        break
                else:
                    raise NameMapError(f"no Chinese pseudonym available for {name!r}")

        taken_en.add(pseudo_en)
        taken_zh.add(pseudo_zh)
        records.append(
            {
                "canonical": name,
                "type": entity_type,
                "gender": entity["gender"],
                "aliases": entity["aliases"],
                "pseudonym_en": pseudo_en,
                "pseudonym_zh": pseudo_zh,
                "source": source,
                "passages": sorted(entity.get("passages", [])),
            }
        )
    return records


def merge_entities(batches: list[tuple[str, list[dict]]]) -> list[dict]:
    """Fold per-passage extractions into one entity list, unioning aliases."""
    merged: dict[str, dict] = {}
    for passage_id, entities in batches:
        for entity in entities:
            record = merged.setdefault(
                entity["canonical"],
                {
                    "canonical": entity["canonical"],
                    "type": entity["type"],
                    "gender": entity["gender"],
                    "aliases": set(),
                    "passages": set(),
                },
            )
            record["aliases"].update(entity["aliases"])
            record["passages"].add(passage_id)
            if record["gender"] == "unknown" and entity["gender"] != "unknown":
                record["gender"] = entity["gender"]
    out = []
    for record in merged.values():
        record["aliases"] = sorted(record["aliases"], key=len, reverse=True)
        record["passages"] = sorted(record["passages"])
        out.append(record)
    return out


# --------------------------------------------------------------------------


def self_test() -> int:
    checks = []

    ents = [
        {"canonical": "Jesus", "type": "person", "gender": "m", "aliases": ["Jesus"]},
        {"canonical": "Mary", "type": "person", "gender": "f", "aliases": ["Mary"]},
        {"canonical": "Galilee", "type": "place", "gender": "unknown", "aliases": ["Galilee"]},
        {"canonical": "Zebulunites", "type": "people", "gender": "unknown", "aliases": ["Zebulunites"]},
        {"canonical": "God", "type": "deity", "gender": "unknown", "aliases": ["God"]},
    ]
    records = assign(ents)
    by_name = {r["canonical"]: r for r in records}

    checks.append(
        ("committed Luke pseudonyms reused",
         by_name["Jesus"]["pseudonym_en"] == "Marun"
         and by_name["Jesus"]["pseudonym_zh"] == "玛伦",
         (by_name["Jesus"]["pseudonym_en"], by_name["Jesus"]["pseudonym_zh"])))
    checks.append(
        ("deity gets a title, not a name",
         by_name["God"]["pseudonym_en"] == "the Sovereign", by_name["God"]["pseudonym_en"]))
    checks.append(
        ("place gets a Chinese type suffix",
         by_name["Galilee"]["pseudonym_zh"][-1] in "地城村",
         by_name["Galilee"]["pseudonym_zh"]))
    checks.append(
        ("new entity is generated, not reused",
         by_name["Zebulunites"]["source"] == "generated",
         by_name["Zebulunites"]["source"]))

    en = [r["pseudonym_en"] for r in records]
    zh = [r["pseudonym_zh"] for r in records]
    checks.append(("no English collisions", len(en) == len(set(en)), en))
    checks.append(("no Chinese collisions", len(zh) == len(set(zh)), zh))

    # determinism
    again = assign(ents)
    checks.append(("assignment deterministic", again == records, None))

    # candidate scan must skip sentence-initial words but keep mid-sentence names
    cands = candidate_names("Jesus went to Capernaum. The crowd followed Jesus there.")
    checks.append(("candidate scan finds mid-sentence names",
                   "Capernaum" in cands and "Jesus" in cands, sorted(cands)))
    checks.append(("candidate scan drops sentence-initial stopword",
                   "The" not in cands, sorted(cands)))

    # validation rejects junk
    try:
        validate_entities({"entities": [{"canonical": "", "type": "person"}]})
        checks.append(("empty canonical rejected", False, "no error"))
    except NameMapError:
        checks.append(("empty canonical rejected", True, None))

    ok = 0
    for label, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}" + ("" if passed else f"  got={detail!r}"))
        ok += bool(passed)
    print(f"{ok}/{len(checks)} checks passed")
    return 0 if ok == len(checks) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passage", type=Path, action="append", default=[])
    parser.add_argument("--passage-dir", type=Path)
    parser.add_argument("--glob", default="*.txt")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print offline candidate names; no API calls.")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()

    paths = list(args.passage)
    if args.passage_dir:
        paths.extend(sorted(args.passage_dir.glob(args.glob)))
    if not paths:
        print("error: pass --passage and/or --passage-dir", file=sys.stderr)
        return 1

    try:
        if args.dry_run:
            for path in paths:
                counts = candidate_names(path.read_text(encoding="utf-8"))
                print(f"\n{path.name}: {len(counts)} candidate(s)")
                for word, hits in list(counts.items())[:40]:
                    print(f"  {hits:3d}  {word}")
            print(
                "\nCandidates are a crude capitalization scan: they miss "
                "sentence-initial names and cannot type entities. Run without "
                "--dry-run for the real extraction."
            )
            return 0

        batches = []
        for path in paths:
            print(f"extracting {path.name}")
            entities = llm_extract_entities(
                path.read_text(encoding="utf-8"),
                args.model,
                args.retries,
                args.temperature,
            )
            print(f"  {len(entities)} entity/entities")
            batches.append((path.stem, entities))

        records = assign(merge_entities(batches))

    except (NameMapError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    payload = {
        "schema_version": 1,
        "passages": [path.stem for path in paths],
        "policy": {
            "person": "invented given name, gender preserved",
            "place": "invented toponym; Chinese adds 地/城/村",
            "people": "invented ethnonym",
            "deity": "non-canonical title, not a name",
            "generic": "not substituted",
        },
        "entities": records,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")

    reused = sum(1 for r in records if r["source"] == "reused")
    by_type: dict[str, int] = {}
    for record in records:
        by_type[record["type"]] = by_type.get(record["type"], 0) + 1
    print(f"\n{len(records)} entity/entities  ({reused} reused, {len(records) - reused} new)")
    print("  " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))

    if args.report:
        print()
        for record in records:
            mark = "=" if record["source"] == "reused" else "+"
            print(
                f" {mark} {record['type']:7s} {record['canonical']:24s} "
                f"-> {record['pseudonym_en']:16s} {record['pseudonym_zh']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
