"""Blind the frozen Sol passage ladder and reviewed MCQs with one bilingual map."""
import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from evaluation.scripts.pipeline.compare_clean_passages import ROOT, numbered_verses, read, save
from evaluation.scripts.pipeline.verify_clean_passage_release import digest, require, verify_windows
from evaluation.scripts.pipeline.build_clean_passage_ladder import DEST as LADDER, replay
from evaluation.scripts.variants._common import content_len
from evaluation.scripts.variants.current import create_grammar_variants as grammar
from evaluation.scripts.variants.current import create_omission_variants as omission
from human_pilot.pilot_import import load_tier1_metadata

DATA = ROOT / "evaluation/datasets"
MAP = DATA / "pseudonym_remap/name_map_tier1_sol_reviewed122.json"
QA = DATA / "qa/reviewed122"
DEST = DATA / "blinded/tier1_sol_reviewed122_v1"

# Reviewed against the English corpus, including names occurring only at the
# beginning of distractors. This inventory is independent of the alias matcher.
ORDINARY_CAPITALS = set("""
A About After Alas All Along Also Altar An And Another Anyone Appoint Are Aren As Ask At Be Because Beside
Between Blessed Bring Broke Bury But By Captured Centurion Change Choose Cisterns Clothes Come Commander
Consecrate Consecrating Crushes Destroyed Did Do Don Draw Each Even Evil Excellency Farmers Fight Finally
First Flocks Following For Fortified Four From Gate Get Give Go Governor Grain Greetings Guard Guards Have
He Healed Hear Hearing Help Her His Horses How Hurriedly Hurry I If In Indeed Inside Intercede Is It Its
Keep King Lay Learning Leave Let Listen Live Long Look Many May Meanwhile More Multiplied Muster Nephew
Never Next Now O Oh On Once One Only Please Praetorium Prepare Provide Put Puts Putting Quick Rally
Reappointing Rebuilt Reign Remember Reserving Retrieve Return Rise Rocks Sabbath Saddle Seated Second
Seeing Seize Selling Serve Sets Seven Seventh Shadows She Should Shut Since Sixth So Soldiers Some
Stables Stand Station Stay Stilled Storehouses Strikes Suddenly Surely Take Tell Testimony That The
Their Then There Therefore These They This Three Thus To Today Towers Travelers Treason Trees Under Until
Wait Watching We What When Where Whether Which While Who Whom Whose Why You Your
""".split())

# Signed differences in name-mention counts across the frozen parallel choices.
# A positive count means English uses the name more times. Each exception is
# deliberately keyed to a single choice and the exact entity, not to a passage.
REVIEWED_DIFFERENCES = {
    **{("2chr_26_1-23/v3-5:1", label): ({"Uzziah": 1}, "Chinese uses a pronoun for Uzziah.")
       for label in "ABCD"},
    ("2kgs_11_1-21/v4-8:1", "B"): ({"the Lord": -1}, "Chinese names the deity of the temple."),
    ("acts_23_12-35/v31-35:1", "C"): ({"Paul": -1}, "Chinese identifies whose accusers they are."),
    ("judg_17_1-13/v9-13:1", "B"): ({"Micah": 1}, "Chinese uses a possessive pronoun for Micah."),
    ("judg_18_1-31/v22-23:1", "B"): ({"Danites": 1}, "Chinese refers to the group with a pronoun."),
    ("judg_9_1-57/v18-20:1", "D"): ({"Abimelek": -1}, "Chinese repeats the name for an English pronoun."),
    ("judg_9_1-57/v30-33:1", "A"): ({"Shechem": -1}, "Chinese gives the name of the governor's city."),
    ("t1_1kgs13:wmh3", "B"): ({"Man of God from Judah": -1}, "English refers to him as the man."),
    ("t1_2kgs11:uo39", "C"): ({"the Lord": 1}, "Chinese refers to the temple without naming its deity."),
    ("t1_acts19:xtb7", "D"): ({"the Lord": -1}, "Chinese gives the object of the believers' faith."),
}


class Names:
    """One pass over the original string keeps an emitted name from being remapped."""

    def __init__(self, table, language, pid):
        self.forms = {}
        for entity in table["entities"]:
            forms = entity.get("release_forms", {})
            if pid not in forms.get("scope", [pid]):
                continue
            aliases = {**forms.get(language, {}), **forms.get(f"scoped_{language}", {}).get(pid, {})}
            for alias, template in aliases.items():
                key = alias.casefold() if language == "en" else alias
                value = template.replace("@", entity[f"pseudonym_{language}"]), entity["canonical"]
                require(key not in self.forms or self.forms[key] == value, f"Ambiguous {pid}/{language} form {alias}")
                self.forms[key] = value
        for alias in table["release_exemptions"][language]:
            key = alias.casefold() if language == "en" else alias
            self.forms[key] = (None, None)
        words = "|".join(re.escape(s) for s in sorted(self.forms, key=lambda k: (-len(k), k)))
        self.pattern = (re.compile(rf"(?<![A-Za-z])(?:{words})(?![A-Za-z])", re.IGNORECASE)
                        if language == "en" else re.compile(words))
        self.language = language
        self.allowed_capitals = ORDINARY_CAPITALS | {
            word for e in table["entities"] for word in e["pseudonym_en"].split()
        }

    def apply(self, text, hits=None):
        def replace(match):
            original = match.group()
            key = original.casefold() if self.language == "en" else original
            value, entity = self.forms[key]
            if value is None:
                return original
            if hits is not None:
                hits[entity] += 1
            return value
        return self.pattern.sub(replace, text)

    def check(self, text, location):
        hits = Counter()
        self.apply(text, hits)
        require(not hits, f"Surviving canonical forms in {location}: {dict(hits)}")
        if self.language == "en":
            unknown = set(re.findall(r"\b[A-Z][a-zA-Z]*(?:-[A-Za-z]+)?\b", text)) - self.allowed_capitals
            require(not unknown, f"Unreviewed English capitalized words in {location}: {sorted(unknown)}")
        else:
            require(not re.search(r"[A-Za-z]", text), f"Unexpected Latin text in Chinese at {location}")


def blind_bank(family, source_bank, raw, clean, names):
    if family == "mistranslation":
        total = content_len(clean)
    elif family == "omission":
        total = sum(u["content_chars"] for u in omission.passage_units(clean) if u["omittable"])
    else:
        total = sum(u["content_chars"] for u in grammar.passage_units(clean) if u["affectable"])
    edits = {}
    for edit_id, original in source_bank["edits"].items():
        weight = original["content_chars"]
        spans = []
        for span in original["spans"]:
            pos = span["start"]
            require(raw.startswith(span["before"], pos), "Incorrect source edit position")
            start = len(names.apply(raw[:pos]))
            before, after = names.apply(span["before"]), names.apply(span["after"])
            require(clean.startswith(before, start) and before != after, f"Invalid blinded edit {family}/{edit_id}")
            weight += content_len(before) - content_len(span["before"])
            spans.append({"start": start, "before": before, "after": after})
        edits[edit_id] = {"content_chars": weight, "spans": spans}
    return {"selection": source_bank["selection"], "seed": source_bank["seed"],
            "source_bank_id": source_bank.get("bank_id"), "total_content_chars": total, "edits": edits}


def blind_passage(source, names):
    conditions = {}
    pid = source["id"]
    for key, cell in source["conditions"].items():
        text = names.apply(cell["text"])
        require(digest(cell["text"]) == cell["text_sha256"], f"Bad source hash for {pid}/{key}")
        names.check(text, f"{pid}/{key}")
        verses = {k: names.apply(v) for k, v in cell["verses"].items()}
        for label, value in verses.items():
            names.check(value, f"{pid}/{key}/{label}")
        conditions[key] = {"text": text, "verses": verses, "text_sha256": digest(text),
                           "source_text_sha256": cell["text_sha256"]}
    clean = conditions["clean"]["text"]
    raw = source["conditions"]["clean"]["text"]
    banks = {f: blind_bank(f, bank, raw, clean, names) for f, bank in source["families"].items()}
    for key, cell in source["conditions"].items():
        if "selected_edits" not in cell:
            continue
        output = conditions[key]
        family = key.rstrip("0123456789")
        bank = banks[family]
        edits = [bank["edits"][str(i)] for i in cell["selected_edits"]]
        require(replay(clean, [s for e in edits for s in e["spans"]]) == output["text"],
                f"Blinding altered the selected edits in {pid}/{key}")
        actual = sum(e["content_chars"] for e in edits) / bank["total_content_chars"]
        require(abs(actual - cell["requested_rate"]) <= .020000001, f"Blinded dose out of tolerance in {pid}/{key}")
        output.update(requested_rate=cell["requested_rate"], source_actual_rate=cell["actual_rate"],
                      actual_rate=actual, selected_edits=cell["selected_edits"])
    require(len(conditions) == len({c["text"] for c in conditions.values()}) == 20, f"Collapsed conditions in {pid}")
    return {"id": pid, "reference": source["reference"], "conditions": conditions, "families": banks}


def blind_questions(names, packs):
    banks = {lang: read(QA / f"{filename}.json") for lang, filename in (("en", "english"), ("zh", "zh"))}
    ids = [q["id"] for q in banks["en"]]
    require(len(ids) == len(set(ids)) == 122, "Unexpected English question set")
    by_id = {q["id"]: q for q in banks["zh"]}
    require(set(ids) == set(by_id) and len(banks["zh"]) == 122, "Different Chinese question set")
    output = {"en": [], "zh": []}
    audit = []
    for en in banks["en"]:
        zh = by_id[en["id"]]
        pid = en["passage_id"]
        require(all(en[k] == zh[k] for k in ("id", "source", "passage_id", "correct")), "Different item or key")
        require(list(en["verses"]) == list(zh["verses"]), f"Verse span changed for {en['id']}")
        trace = []
        mentions = {}
        for lang, item in (("en", en), ("zh", zh)):
            matcher = names[pid, lang]
            label = f"{item['id']}/{lang}"
            stem = matcher.apply(item["question"])
            matcher.check(stem, label)
            require(len(item["choices"]) == 4 and item["correct"] in ("A", "B", "C", "D"), label)
            choices = []
            for i, original in enumerate(item["choices"]):
                hits = Counter()
                choice = matcher.apply(original, hits)
                matcher.check(choice, f"{label}/{'ABCD'[i]}")
                choices.append(choice)
                mentions[lang, "ABCD"[i]] = hits
                trace.append({"language": lang, "label": "ABCD"[i], "sha256": digest(choice),
                              "identities": dict(hits), "known_name_leaks": 0})
            require(len(set(choices)) == 4, f"Answer choices collapsed for {label}")
            clean = (packs[pid]["english"] if lang == "en" else packs[pid]["conditions"]["clean"])["verses"]
            window = {v: clean[v] for v in item["verses"]}
            for v, text in window.items():
                matcher.check(text, f"{label}/{v}")
            output[lang].append(dict(item, question=stem, choices=choices, verses=window))
        reviewed = {}
        for option in "ABCD":
            delta = mentions["en", option].copy()
            delta.subtract(mentions["zh", option])
            actual = {name: n for name, n in delta.items() if n}
            expected, reason = REVIEWED_DIFFERENCES.get((en["id"], option), ({}, None))
            require(actual == expected, f"Unreviewed bilingual name discrepancy: {en['id']}/{option} {actual}")
            if reason:
                reviewed[option] = reason
        audit.append({"id": en["id"], "choices": trace, "reviewed_bilingual_differences": reviewed})
    return output, audit


def build(dest):
    table = read(MAP)
    parent = MAP.parent / table["parent"]["file"]
    require(sha256(parent.read_bytes()).hexdigest() == table["parent"]["sha256"], "Unexpected parent map")
    parent_names = {e["canonical"]: (e["pseudonym_en"], e["pseudonym_zh"]) for e in read(parent)["entities"]}
    assigned = {e["canonical"]: (e["pseudonym_en"], e["pseudonym_zh"]) for e in table["entities"]}
    require(len(assigned) == len(table["entities"]) and parent_names.items() <= assigned.items(),
            "Duplicate entity or changed historical pseudonym")
    for lang in ("en", "zh"):
        active = [e[f"pseudonym_{lang}"] for e in table["entities"] if e.get("release_forms")]
        require(len(active) == len(set(active)), f"Duplicate assigned name in {lang}")
    ladder = read(LADDER / "manifest.json")
    packs, names = {}, {}
    metadata = {p["id"]: p for p in load_tier1_metadata(ROOT / "evaluation")}
    for filename, file_hash in ladder["files"].items():
        file = LADDER / filename
        require(sha256(file.read_bytes()).hexdigest() == file_hash, f"Unexpected source passage {filename}")
        source = read(file)
        pid = source["id"]
        for lang in ("en", "zh"):
            names[pid, lang] = Names(table, lang, pid)
        packs[pid] = blind_passage(source, names[pid, "zh"])
        chinese_parent = read(DATA / "passages" / ladder["source_release"] / filename)
        raw_en = (ROOT / chinese_parent["english_path"]).read_text()
        require(digest(raw_en) == source["english_sha256"], f"English source mismatch for {pid}")
        blinded_en = names[pid, "en"].apply(raw_en)
        names[pid, "en"].check(blinded_en, f"{pid}/English source")
        verses = dict(numbered_verses(blinded_en, metadata[pid]))
        require(list(verses) == list(packs[pid]["conditions"]["clean"]["verses"]), f"English verses differ in {pid}")
        packs[pid]["english"] = {"text": blinded_en, "verses": verses, "text_sha256": digest(blinded_en)}
    questions, audit = blind_questions(names, packs)
    windows = verify_windows(packs)
    payload = {f"passages/{pid}.json": pack for pid, pack in packs.items()}
    payload.update({"qa/english.json": questions["en"], "qa/zh.json": questions["zh"],
                    "qa/pilot_review.json": read(QA / "pilot_review.json"), "audit/choices.json": audit})
    require(len(packs) == 10 and sum(len(r["choices"]) for r in audit) == 976, "Incomplete release")
    manifest = {"release_id": DEST.name, "source_ladder": ladder["release_id"], "map": MAP.name,
                "map_sha256": sha256(MAP.read_bytes()).hexdigest(),
                "source_qa_sha256": {file: sha256((QA / file).read_bytes()).hexdigest()
                                     for file in ("english.json", "zh.json", "pilot_review.json")},
                "map_entities": len(assigned), "new_entities": len(assigned) - len(parent_names),
                "defect_variants": 180, "clean_controls": 10, "word_by_word_controls": 10,
                "questions": 122, "choices_checked_per_language": 488, "known_name_leaks_in_choices": 0,
                "reviewed_parallel_choice_differences": sum(len(r["reviewed_bilingual_differences"]) for r in audit),
                "max_blinded_dose_deviation_pp": max(100 * abs(c["requested_rate"] - c["actual_rate"])
                    for p in packs.values() for c in p["conditions"].values() if "requested_rate" in c),
                "window_validation": windows, "files": {}}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp) / dest.name
        for filename, data in payload.items():
            path = stage / filename
            save(path, data)
            manifest["files"][filename] = sha256(path.read_bytes()).hexdigest()
        save(stage / "manifest.json", manifest)
        if dest.exists():
            existing = {p.relative_to(dest) for p in dest.rglob("*") if p.is_file()}
            expected = {p.relative_to(stage) for p in stage.rglob("*") if p.is_file()}
            require(existing == expected and all((dest / p).read_bytes() == (stage / p).read_bytes()
                                                for p in expected), "Existing blinded release differs")
        else:
            stage.rename(dest)
    print(f"Verified 200 Chinese passages and 488 choices in each language in {dest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEST)
    build(parser.parse_args().output_dir)
