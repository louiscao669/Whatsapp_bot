"""Build or verify the Sol pilot's name-preserving Google word-by-word condition offline.

Run python -m evaluation.scripts.pipeline.build_sol_wbw_names [--write].
The November 9 release and its SLM inputs remain reproducible from their original files.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

from evaluation.scripts.scoring.current.translation_quality import protect_wbw_names, review_wbw_source_names, wbw_join, wbw_name_override

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "evaluation/datasets"
BASE = DATA / "passages/tier1_zh_sol_v1_defect_ladder_2026-11-09"
OUTPUT = DATA / "passages/sol_wbw_names_v1.json"
REPORT = ROOT / "evaluation/reports/sol_wbw_names_v1.md"
sys.path.insert(0, str(ROOT / "human_pilot"))
from pilot_import import load_tier1_metadata, parse_tier1_verses


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(text):
    return sha256(text.encode()).hexdigest()


def correct_passage(english, record, clean, meta, config, legacy, cache):
    """Replay the old token stream, then replace only source-aligned named spans."""
    labels = list(clean)
    markers = [paragraph.split(" ", 1)[0] for paragraph in english.strip().split("\n\n")]
    expected_markers = [chapter if verse == "1" else verse for chapter, verse in
                        (label.split(":") for label in labels)]
    if markers != expected_markers:
        raise ValueError(f"{meta['id']}: English and clean verse labels differ")
    if dict(parse_tier1_verses(record["text"], meta)) != record["verses"]:
        raise ValueError(f"{meta['id']}: old served verse map differs")

    pairs = []
    for word in english.split(" "):
        target = wbw_name_override(word, legacy)
        if target is None:
            target = cache[word.lower()] if word else ""
        pairs.append((word, target))
    if wbw_join(pairs).strip() != record["text"].strip() or digest(record["text"]) != record["text_sha256"]:
        raise ValueError(f"{meta['id']}: cached Google output does not reproduce the original")

    names = {**config["components"], **config["names"]}
    review_wbw_source_names(english, names, set(config["reviewed_non_names"]), list(clean.items()))
    output, occurrences = protect_wbw_names(pairs, names)
    checks = [(labels[english.count("\n\n", 0, position)], name, old, expected)
              for position, name, old, expected in occurrences]
    old_text = record["text"]
    corrected = old_text.replace(old_text.strip(), wbw_join(output).strip(), 1)
    verses = dict(parse_tier1_verses(corrected, meta))
    if list(verses) != labels:
        raise ValueError(f"{meta['id']}: name correction changed verse boundaries")
    return dict(text=corrected, text_sha256=digest(corrected), verses=verses), checks


def sol_condition(english, original_text, clean, meta):
    """Build a fresh Sol release from its clean verses and saved English/Google pair."""
    record = {"text": original_text, "text_sha256": digest(original_text),
              "verses": dict(parse_tier1_verses(original_text, meta))}
    return correct_passage(english, record, clean, meta, read(DATA / "perturbations/sol_wbw_names.json"),
                           read(DATA / "perturbations/wbw_name_overrides.json"),
                           read(DATA / "perturbations/.wbw_cache_en_zh-CN.json"))[0]


def build():
    config = read(DATA / "perturbations/sol_wbw_names.json")
    legacy = read(DATA / "perturbations/wbw_name_overrides.json")
    cache = read(DATA / "perturbations/.wbw_cache_en_zh-CN.json")
    manifest = read(BASE / "manifest.json")
    overlay = {"parent_release": BASE.name, "passages": {}}
    edits = defaultdict(list)
    counts = Counter()
    covered = set()
    for meta in load_tier1_metadata(ROOT / "evaluation"):
        pid = meta["id"]
        file = BASE / f"{pid}.json"
        if sha256(file.read_bytes()).hexdigest() != manifest["files"][file.name]:
            raise ValueError(f"{pid}: parent passage hash mismatch")
        pack = read(file)
        english = (DATA / "passages/tier1_bsb" / config["source_files"][pid]).read_text()
        if digest(english) != pack["english_sha256"]:
            raise ValueError(f"{pid}: wrong English source")
        old = pack["conditions"]["wbw"]
        new, checks = correct_passage(english, old, pack["conditions"]["clean"]["verses"], meta,
                                      config, legacy, cache)
        overlay["passages"][pid] = dict(parent_text_sha256=old["text_sha256"], **new)
        counts["verses"] += len(new["verses"])
        counts["occurrences"] += len(checks)
        covered.update(name for _, name, _, _ in checks)
        changed = set()
        for label, name, before, after in checks:
            if before != after:
                edits[(meta["reference"], name, before, after)].append(label)
                changed.add(label)
                counts["changes"] += 1
        if changed != {v for v in new["verses"] if old["verses"][v] != new["verses"][v]}:
            raise ValueError(f"{pid}: unexplained verse changes")
        counts["changed_verses"] += len(changed)
    if set(config["names"]) != covered or set(overlay["passages"]) != set(config["source_files"]):
        raise ValueError("Name or passage inventory differs from this release")
    report = ["# Sol pilot Google word-by-word name audit", "",
              f"Checked {len(overlay['passages'])} passages, {counts['verses']} verses and {counts['occurrences']} "
              f"occurrences of {len(covered)} protected English names or named expressions. "
              f"{counts['changes']} occurrences changed in {counts['changed_verses']} verses.", "",
              "Each row gives the wording from the original participant passage, the spelling in the clean Sol "
              "verse, and every location changed. Repeated verse numbers indicate two occurrences.", "",
              "| Passage | English | Previous | Corrected | Verses |", "|---|---|---|---|---|"]
    for (ref, name, old, new), labels in sorted(edits.items()):
        report.append(f"| {ref} | {name} | {old} | {new} | {', '.join(labels)} |")
    return overlay, "\n".join(report) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the pilot release and name audit")
    args = parser.parse_args()
    overlay, report = build()
    for path, content in [(OUTPUT, json.dumps(overlay, ensure_ascii=False, indent=2) + "\n"), (REPORT, report)]:
        if args.write:
            path.write_text(content, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Rebuild differs from {path}")
    print(report.splitlines()[2])


if __name__ == "__main__":
    main()
