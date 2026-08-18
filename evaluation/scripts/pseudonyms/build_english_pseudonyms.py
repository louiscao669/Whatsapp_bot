#!/usr/bin/env python3
"""Build the English-side pseudonym table used to blind passages before translation.

Rationale
---------
The pipeline currently blinds two different ways: LLM translation methods get
``__PERSON_C__`` protected tokens substituted into the English source, while the
neural MT methods (helsinki, mBART-50, NLLB, NLLB-dropout) get the untouched
English and rely on a post-translation LLM canonicalization pass to catch every
canonical name. That makes blinding *guaranteed* for one branch and *best-effort*
for the other, and confounds translation method with blinding strength.

Substituting natural-looking English pseudonyms *before* translation unifies both
branches: name-shaped strings survive MT models (they just get transliterated),
so every method can take the same protected source. It also defamiliarizes the
passage for the LLM translator, which otherwise pulls a recognizable text toward
the canonical Chinese wording it memorized -- the failure mode that most
threatens ``llm_prompt_low`` actually producing a low-quality translation.

Policy
------
person  -> invented given name, gender preserved (pronoun agreement matters)
place   -> invented toponym, no type suffix (English syntax already supplies
           "the town of X"); the Chinese side adds 地/城/村 downstream
people  -> invented ethnonym stem, with a generated -ite plural form
deity   -> non-canonical English title, not an invented name, so register is
           preserved for translation-quality judging
text    -> "this account"
generic -> NOT substituted. Common nouns (boat, shepherd, synagogue) carry
           meaning, not identity, and blanking them would damage adequacy.

Names are checked against three constraints: no collision with any canonical
name in the source, no collision between pseudonyms, and no pseudonym that is a
substring of another (so longest-first replacement stays unambiguous).

Usage (from evaluation/):
    python scripts/pseudonyms/build_english_pseudonyms.py
    python scripts/pseudonyms/build_english_pseudonyms.py --report

Writes datasets/pseudonym_remap/english_pseudonyms.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Resolved against evaluation/ so the script works from any working directory.
EVAL_DIR = Path(__file__).resolve().parents[2]
MASTER = EVAL_DIR / "datasets/pseudonym_remap/_master.json"
OUT = EVAL_DIR / "datasets/pseudonym_remap/english_pseudonyms.json"

SUBSTITUTED_TYPES = {"person", "place", "people", "deity", "text", "role"}

# Entities whose pseudonym is fixed by hand: the recurring cast, where a stable
# and deliberately chosen name matters more than generation convenience.
PINNED = {
    "Jesus": "Marun",
    "Mary": "Raymo",
    "Galilee": "Kaloh",
    "John": "Miran",
    "Zechariah": "Kowen",
    "Elizabeth": "Harlin",
    "Joseph": "Mihen",
    "Gabriel": "Vesar",
    "Abraham": "Kaonel",
    "Jacob": "Verlo",
    "David": "Raygo",
    "Nazareth": "Tarlo",
    "Jerusalem": "Verdon",
    "Judea": "Soren",
    "Herod": "Lanvi",
    "Elijah": "Garon",
    "Theophilus": "Kahen",
    "Luke": "Lonri",
    "Peter": "Nipan",
    "Aaron": "Lonsu",
    "Israel": "Serath",
}

# Deities take titles, not names. Each must be non-canonical, unambiguous, and
# distinct from any word already used in the source (note "Master" is excluded:
# Simon addresses Jesus as "Master" in Luke 5:5, which would collide).
DEITY_TITLES = {
    "God": "the Sovereign",
    "Lord": "the Supreme One",
    "Most High": "the Exalted One",
    "Holy Spirit": "the Sacred Spirit",
    "Messiah": "the Chosen One",
    "Son of Man": "the Son of Humanity",
    "devil": "the Adversary",
    "Satan": "the Adversary",
}

TEXT_TITLE = "this account"

# Proper nouns that appear in the Luke 1-8 source but are absent from
# _master.json, because the Chinese-side entity discovery missed them. Found by
# scanning pseudonymized output for surviving capitalized tokens.
EXTRA_ENTITIES = {
    "Moses": ("person", "Tavren"),
    "Jordan": ("place", "Kelvar"),
    "Asher": ("people", "Duran"),
    # "John the Baptist" keeps its epithet after substitution ("Miran the
    # Baptist"), which identifies him as surely as the name did. Same for
    # "Simon the Zealot".
    "Baptist": ("role", "Immerser"),
    "Zealot": ("role", "Partisan"),
    "Isaac": ("person", "Volem"),
    "Bartholomew": ("person", "Nedar"),
    "Thomas": ("person", "Selam"),
    "Matthew": ("person", "Doven"),
    "Judas": ("person", "Rethin"),
    "Tyre": ("place", "Munal"),
    "Nain": ("place", "Beltas"),
    # Adjectival form of Syria, which the base place rule does not cover.
    "Syrian": ("people", "Rodoran"),
}

# Female-coded entities, so generated pseudonyms preserve gender agreement.
FEMALE = {
    "Mary", "Elizabeth", "Anna", "Joanna", "Susanna", "Herodias",
    "Magdalene", "Martha",
}

# Syllable pools for generated names. Chosen to be phonotactically simple and
# stable under machine transliteration: MT models render "Doran" consistently,
# but waver on consonant clusters and unusual vowel sequences. Voiceless stops
# in coda position (-ek, -od, -ik) were removed because they produced names that
# read as noise rather than as names.
ONSET = ["D", "T", "K", "L", "M", "N", "R", "S", "V", "B", "G", "H"]
NUCLEUS = ["a", "e", "i", "o", "u"]
MEDIAL = ["r", "l", "n", "m", "v", "d", "s", "t"]
CODA_M = ["n", "r", "l", "m", "s", "th"]
CODA_F = ["a", "ia", "ela", "ina", "ora", "eva"]
PLACE_TAIL = ["dor", "mar", "nel", "tas", "ven", "rin", "sol", "kal", "pen", "lor"]

# Real words, brands, place names, and non-target religious names that the
# generator can plausibly land on. A pseudonym that reads as an existing thing
# reintroduces exactly the priors this table is meant to remove.
BLOCKLIST = {
    "kodak", "sedan", "salon", "melon", "talon", "ramen", "demon", "lemon",
    "vodka", "honda", "nissan", "roman", "satan", "sodom", "damon", "simon",
    "amen", "omen", "human", "nomad", "madam", "radar", "salad", "level",
    "model", "motel", "metal", "medal", "moral", "total", "vital", "canal",
    "minor", "major", "manor", "donor", "tumor", "rumor", "humor", "valor",
    "tenor", "terror", "mirror", "lunar", "solar", "molar", "dollar", "collar",
    "sonar", "altar", "cedar", "satin", "latin", "cabin", "robin", "resin",
    "basin", "ruin", "virus", "minus", "bonus", "venus", "sinus", "koran",
    "lorem", "tabor", "moses", "allah", "buddha", "vishnu", "odin", "thor",
    "loki", "titan", "siren", "raven", "haven", "heron", "baron", "bison",
    "melanin", "median", "median", "kelvin", "marina", "lima", "milan",
    "roma", "dakota", "havana", "sahara", "korea", "kenya", "malta", "malawi",
    "somalia", "bolivia", "tunisia", "nigeria", "liberia", "siberia",
    "hodor", "kotor", "notas", "datum", "velum", "serum", "torus", "novas",
    "gives", "gamer", "salim", "nives", "dadan", "dedan", "kaon", "bidon",
    "gomer", "hamor", "havil", "sinim", "lotan", "medan", "meson",
}


def load_master(path: Path) -> list[list]:
    if not path.exists():
        raise SystemExit(
            f"error: {path} not found. Run from evaluation/ after "
            "build_pseudonym_remap.py has produced _master.json."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def collect_entities(master: list[list]) -> dict[str, dict]:
    """Fold _master.json rows into one record per distinct English entity.

    Row shape: [chapter, placeholder, type, chinese_pseudonym, english, chinese].
    """
    entities: dict[str, dict] = {}
    for chapter, _placeholder, entity_type, zh_pseudonym, english, chinese in master:
        english = (english or "").strip()
        if not english or entity_type not in SUBSTITUTED_TYPES:
            continue
        record = entities.setdefault(
            english,
            {
                "canonical": english,
                "type": entity_type,
                "chapters": set(),
                "chinese_canonical": set(),
                "prior_chinese_pseudonyms": set(),
            },
        )
        record["chapters"].add(chapter)
        if chinese:
            record["chinese_canonical"].add(chinese)
        if zh_pseudonym:
            record["prior_chinese_pseudonyms"].add(zh_pseudonym)

    for english, (entity_type, pseudonym) in EXTRA_ENTITIES.items():
        record = entities.setdefault(
            english,
            {
                "canonical": english,
                "type": entity_type,
                "chapters": [],
                "chinese_canonical": set(),
                "prior_chinese_pseudonyms": set(),
                "source": "extra",
            },
        )
        record["chapters"] = set(record["chapters"])
        record.setdefault("source", "extra")
        PINNED.setdefault(english, pseudonym)
    return entities


def syllables(seed: int, entity_type: str, female: bool) -> str:
    """Deterministic name generation. Same canonical name always yields the same
    pseudonym, so reruns are stable and chapters stay consistent."""
    if entity_type == "place":
        head = ONSET[seed % len(ONSET)] + NUCLEUS[(seed // 7) % len(NUCLEUS)]
        return head + PLACE_TAIL[(seed // 13) % len(PLACE_TAIL)]
    head = ONSET[seed % len(ONSET)] + NUCLEUS[(seed // 5) % len(NUCLEUS)]
    medial = MEDIAL[(seed // 11) % len(MEDIAL)]
    if female:
        # Female forms take a vowel-final tail, so the medial vowel is dropped to
        # avoid three-vowel runs ("Dadeena").
        return head + medial + CODA_F[(seed // 23) % len(CODA_F)]
    mid = medial + NUCLEUS[(seed // 17) % len(NUCLEUS)]
    return head + mid + CODA_M[(seed // 23) % len(CODA_M)]


def stable_seed(text: str) -> int:
    value = 0
    for char in text:
        value = (value * 131 + ord(char)) % 1_000_003
    return value


def conflicts(candidate: str, taken: set[str], canonical: set[str]) -> bool:
    low = candidate.lower()
    if low in BLOCKLIST:
        return True
    if low in {name.lower() for name in canonical}:
        return True
    for existing in taken:
        existing_low = existing.lower()
        if low == existing_low or low in existing_low or existing_low in low:
            return True
    return False


def assign(entities: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    canonical_names = set(entities)
    # Canonical single words that appear inside multiword entities also count as
    # forbidden, so a pseudonym never accidentally reads as a real name.
    for name in list(canonical_names):
        canonical_names.update(name.split())

    taken: set[str] = set()
    warnings: list[str] = []

    for name, pseudonym in PINNED.items():
        if name in entities:
            if conflicts(pseudonym, taken, canonical_names):
                warnings.append(f"pinned pseudonym {pseudonym!r} for {name!r} conflicts")
            entities[name]["pseudonym"] = pseudonym
            entities[name]["pinned"] = True
            taken.add(pseudonym)

    for name, record in sorted(entities.items()):
        if "pseudonym" in record:
            continue
        if record["type"] == "deity":
            title = DEITY_TITLES.get(name)
            if title is None:
                title = f"the {syllables(stable_seed(name), 'person', False)} One"
                warnings.append(f"deity {name!r} had no pinned title; generated {title!r}")
            record["pseudonym"] = title
            record["pinned"] = False
            continue
        if record["type"] == "text":
            record["pseudonym"] = TEXT_TITLE
            record["pinned"] = False
            continue

        seed = stable_seed(name)
        female = name in FEMALE
        for attempt in range(400):
            candidate = syllables(seed + attempt * 9973, record["type"], female)
            if not conflicts(candidate, taken, canonical_names):
                break
        else:
            raise SystemExit(f"error: could not generate a pseudonym for {name!r}")
        record["pseudonym"] = candidate
        record["pinned"] = False
        taken.add(candidate)

    return entities, warnings


ALIAS_TOKEN_STOP = {"son", "of", "the", "daughter", "lake", "mount", "king"}


def build_aliases(name: str, record: dict, entity_names: set[str]) -> list[str]:
    """Surface forms to match. Possessives and curly apostrophes are handled by
    the apply script's regex, so they are not enumerated here."""
    aliases = {name}
    if record["type"] == "people":
        aliases.add(f"{name}ites")
        aliases.add(f"{name}ite")

    # Multiword names appear in the source in reduced forms: "Lake Gennesaret"
    # is written "the Lake of Gennesaret", "Judas Iscariot" becomes "Iscariot".
    # Add each distinctive token, but never one that is itself a separate entity
    # ("James son of Alphaeus" must not claim the bare "James").
    #
    # Deity titles are excluded: their tokens are ordinary words. Expanding
    # "Holy Spirit" to "Spirit" rewrote "an impure spirit" into a divine title.
    if " " in name and record["type"] != "deity":
        for token in name.split():
            clean = token.strip(",.")
            if (
                len(clean) >= 4
                and clean.lower() not in ALIAS_TOKEN_STOP
                and clean not in entity_names
            ):
                aliases.add(clean)

    return sorted(aliases, key=len, reverse=True)


def detect_ambiguity(entities: dict[str, dict]) -> list[dict]:
    """Flag entities that cannot be resolved by string substitution alone.

    These need a human decision; the script does not guess.
    """
    issues = []
    names = set(entities)

    for name, record in sorted(entities.items()):
        prior = record["prior_chinese_pseudonyms"]
        if len(prior) > 1:
            issues.append(
                {
                    "entity": name,
                    "kind": "inconsistent_prior_chinese_pseudonym",
                    "detail": sorted(prior),
                    "note": (
                        "The existing Chinese remap gave this entity different "
                        "pseudonyms in different chapters, despite claiming "
                        "cross-chapter consistency. An English-side table makes "
                        "this structurally impossible."
                    ),
                }
            )
        if len(record["chinese_canonical"]) > 1:
            issues.append(
                {
                    "entity": name,
                    "kind": "multiple_chinese_canonical_forms",
                    "detail": sorted(record["chinese_canonical"]),
                }
            )
        for other in names:
            if other != name and " " in other and name in other.split():
                issues.append(
                    {
                        "entity": name,
                        "kind": "substring_of_multiword_entity",
                        "detail": other,
                        "note": (
                            "Longest-alias-first matching resolves the string, "
                            "but confirm these are the same referent or not."
                        ),
                    }
                )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=MASTER)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--report", action="store_true", help="Print the full table.")
    args = parser.parse_args()

    entities = collect_entities(load_master(args.master))
    entities, warnings = assign(entities)
    ambiguity = detect_ambiguity(entities)

    payload = {
        "schema_version": 1,
        "policy": {
            "person": "invented given name, gender preserved",
            "place": "invented toponym, no type suffix",
            "people": "invented ethnonym with -ite plural",
            "deity": "non-canonical English title",
            "text": TEXT_TITLE,
            "generic": "not substituted",
        },
        "entities": [
            {
                "canonical": name,
                "type": record["type"],
                "pseudonym": record["pseudonym"],
                "pinned": record["pinned"],
                "aliases": build_aliases(name, record, set(entities)),
                "chapters": sorted(record["chapters"]),
                "chinese_canonical": sorted(record["chinese_canonical"]),
                "prior_chinese_pseudonyms": sorted(record["prior_chinese_pseudonyms"]),
            }
            for name, record in sorted(entities.items())
        ],
        "needs_review": ambiguity,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    by_type: dict[str, int] = {}
    for entry in payload["entities"]:
        by_type[entry["type"]] = by_type.get(entry["type"], 0) + 1
    print(f"wrote {len(payload['entities'])} entities to {args.out}")
    print("  " + ", ".join(f"{key}={value}" for key, value in sorted(by_type.items())))
    print(f"  {len(ambiguity)} entity/entities flagged for review")
    for warning in warnings:
        print(f"  warning: {warning}", file=sys.stderr)

    if args.report:
        for entry in payload["entities"]:
            pin = "*" if entry["pinned"] else " "
            print(f"{pin} {entry['type']:7s} {entry['canonical']:24s} -> {entry['pseudonym']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
