"""Build the six-dose Chinese defect ladder from the frozen pilot and its reviewed banks."""
import argparse
from functools import partial
from hashlib import sha256
from itertools import accumulate, combinations
from pathlib import Path
import random
import re
from tempfile import TemporaryDirectory

from evaluation.scripts.analysis.current.check_full_conditions_5opt import FAMILIES, RATES
from evaluation.scripts.pipeline.compare_clean_passages import ROOT, RUN, read, save
from evaluation.scripts.pipeline.prepare_clean_passage_conditions import grammar, mis, omission
from evaluation.scripts.pipeline.verify_clean_passage_release import DEST as PILOT, digest, require, verify_windows
from human_pilot.pilot_import import clean_tier1_verse_text, load_tier1_metadata, parse_tier1_verses

DEST = PILOT.with_name(PILOT.name.replace("_v1_", "_v1_defect_ladder_"))
DOSES = [percent / 100 for percent in RATES]
TOLERANCE_PP = 2


def nested_plan(weights, total, fixed):
    """Use the historical planner on eligible edits, preserving the highest fixed dose."""
    ids = [i for i in weights if .30 not in fixed or i in fixed[.30]]
    index = {edit: position for position, edit in enumerate(ids)}
    anchors = {rate: [index[i] for i in selected] for rate, selected in fixed.items()}
    bank = {"entries": [{"content_chars": weights[i]} for i in ids], "total_content_chars": total, "max_rate": .30}
    plan = grammar.plan_nested_selections(bank, DOSES, tolerance_pp=TOLERANCE_PP, fixed_selections=anchors)
    return {rate: [ids[i] for i in chosen] for rate, chosen in plan.items()}


def omission_plan(weights, total, anchors):
    # A short passage may lack enough clauses inside the fixed pilot edits for six
    # increasing doses. Prefer both pilot texts, then an individual anchor.
    for levels in ((.15, .30), (.30,), (.15,)):
        try:
            return nested_plan(weights, total, {rate: anchors[rate] for rate in levels})
        except grammar.GrammarError:
            continue
    return nested_plan(weights, total, {})


def acts20_grammar_plan(weights, total, parent):
    # The historical Acts 20 exception uses subsets of its five fixed 30% edits.
    subsets = [c for n in range(1, len(parent) + 1) for c in combinations(sorted(parent), n)]
    def distance(choice, rate):
        return abs(sum(weights[i] for i in choice) / total - rate), choice
    return {rate: list(min(subsets, key=lambda c: distance(c, rate))) if rate < .30 else parent
            for rate in DOSES}


def edit_span(start, before, after):
    return {"start": start, "before": before, "after": after}


def replay(clean, edits):
    pieces = []
    end = 0
    for edit in sorted(edits, key=lambda e: e["start"]):
        start, before = edit["start"], edit["before"]
        require(start >= end and clean.startswith(before, start), "Edits overlap or use a different source")
        pieces.extend((clean[end:start], edit["after"]))
        end = start + len(before)
    return "".join(pieces) + clean[end:]


def omission_verses(clean, clean_verses, edits):
    # The historical renderer can delete the printed number with the opening
    # clause. Keep the surviving words attached to their original verse.
    markers = list(re.finditer(r"(?m)^\d+[ \t]+", clean))
    require(len(markers) == len(clean_verses), "Ambiguous source verse boundaries")
    retained = list(clean)
    for edit in edits:
        start, size = edit["start"], len(edit["before"])
        retained[start:start + size] = [""] * size
    output = {}
    for i, (label, expected) in enumerate(clean_verses.items()):
        start = markers[i].end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(clean)
        require(clean_tier1_verse_text(clean[start:end].strip()) == expected, f"Incorrect source boundary for {label}")
        body = clean_tier1_verse_text("".join(retained[start:end]).strip())
        if body:
            output[label] = body
    return output


def group_key(group):
    return group["bank_index"], tuple((o["start"], o["end"]) for o in group["occurrences"])


def build_family(passage_dir, meta, pack, family):
    clean_record = pack["conditions"]["clean"]
    clean = clean_record["text"]
    levels = (.30,) if family == "grammar" else (.15, .30)
    pilot = {rate: read(passage_dir / family / f"{rate:.0%}" / f"{family}_metadata.json")["files"]["passage_target"]
             for rate in levels}
    top = pilot[.30]
    seed, total = top["seed"], top["total_content_chars"]
    info = {"seed": seed, "total_content_chars": total, "selection": "strictly_nested"}
    if family == "mistranslation":
        bank = read(passage_dir / "_base/_shared/mistranslation_bank_coverage_zh.json")
        mis.validate_reviewed_bank(bank, clean)
        groups = mis.candidate_groups(mis.find_occurrences(clean, mis.normalized_replacements(bank)))
        ids = {group_key(g): i for i, g in enumerate(groups)}
        fixed = {r: [ids[group_key(g)] for g in d["substitution_groups"]] for r, d in pilot.items()}
        weights = {i: g["changed_chars"] for i, g in enumerate(groups)}
        plan = nested_plan(weights, total, fixed)
        render = partial(mis.apply_mistranslations, clean, seed=seed, bank=bank)
        selector = "selected_group_indices"
        spans = {i: [edit_span(o["start"], o["source"], o["target"]) for o in g["occurrences"]]
                 for i, g in enumerate(groups)}
        info["bank_id"] = bank["bank_id"]
    else:
        if family == "omission":
            units = omission.passage_units(clean)
            ids = [i for i, u in enumerate(units) if u["omittable"] and u["content_chars"]]
            random.Random(seed).shuffle(ids)
            weights = {i: units[i]["content_chars"] for i in ids}
            fixed = {r: [u["unit_index"] for u in d["omitted_units"]] for r, d in pilot.items()}
            plan = omission_plan(weights, total, fixed)
            render = partial(omission.apply_omissions, clean, seed=seed)
            selector = "selected_unit_indices"
        else:
            bank = read(passage_dir / "grammar/_grammar_bank" / f"bank_{top['bank_id']}.json")
            grammar.validate_grammar_bank(clean, bank)
            units = grammar.passage_units(clean, unit_mode=bank["spec"].get("unit_mode", "clause"))
            weights = {i: e["content_chars"] for i, e in enumerate(bank["entries"])}
            parent = top["selected_bank_indices"]
            if meta["id"] == "t1_acts20" and len(parent) < len(DOSES):
                plan = acts20_grammar_plan(weights, total, parent)
                info["selection"] = "subsets_of_fixed_30pct_v1"
            else:
                plan = nested_plan(weights, total, {.30: parent})
            render = partial(grammar.apply_grammar_bank, clean, seed=seed, bank=bank)
            selector = "selected_bank_indices"
            info["bank_id"] = bank["bank_id"]
        require("".join(u["text"] for u in units) == clean, "Unit boundaries differ from the frozen clean text")
        starts = list(accumulate((len(u["text"]) for u in units), initial=0))
        if family == "omission":
            spans = {i: [edit_span(starts[i], units[i]["text"], "")] for i in weights}
        else:
            spans = {i: [edit_span(starts[e["unit_index"]], e["original_text"], e["corrupted_text"])]
                     for i, e in enumerate(bank["entries"])}

    edits_used = sorted({i for chosen in plan.values() for i in chosen})
    info["edits"] = {str(i): {"content_chars": weights[i], "spans": spans[i]} for i in edits_used}
    previous, previous_rate, seen = set(), 0, {clean}
    conditions = {}
    for rate, chosen in plan.items():
        name = family + str(round(rate * 100))
        text, details = render(rate=rate, **{selector: chosen})
        actual = details["actual_affected_rate"] if family == "grammar" else details["actual_rate"]
        require(previous_rate < actual and abs(actual - rate) <= TOLERANCE_PP / 100 + 1e-9, f"{name}: contents outside dose")
        require(abs(sum(weights[i] for i in chosen) / total - actual) < 1e-9, f"{name}: edit weights disagree")
        require(set(chosen) <= set(plan[.30]), f"{name}: edit outside the highest dose")
        if info["selection"] == "strictly_nested":
            require(previous < set(chosen), f"{name}: adjacent levels are not nested")
        edits = [span for i in chosen for span in spans[i]]
        require(text == replay(clean, edits) and text not in seen, f"{name}: repeated text or failed edit replay")
        if family == "omission":
            verses = omission_verses(clean, clean_record["verses"], edits)
        else:
            verses = dict(parse_tier1_verses(text, meta))
            require(list(verses) == list(clean_record["verses"]), f"{name}: altered verse markers")
        entry = {"requested_rate": rate, "actual_rate": actual, "selected_edits": sorted(chosen),
                 "text_sha256": digest(text), "text": text, "verses": verses}
        if rate in levels:
            pilot_record = pack["conditions"][name]
            require(pilot_record.get("bank_id") == info.get("bank_id"), f"{name}: wrong pilot bank")
            entry["matches_pilot_text"] = text == pilot_record["text"]
            if family != "omission":
                require(entry["matches_pilot_text"], f"{name}: changed fixed pilot text")
        conditions[name] = entry
        previous, previous_rate = set(chosen), actual
        seen.add(text)
    return conditions, info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=RUN)
    parser.add_argument("--output-dir", type=Path, default=DEST)
    args = parser.parse_args()
    pilot_manifest = read(PILOT / "manifest.json")
    packs = {}
    for meta in load_tier1_metadata(ROOT / "evaluation"):
        pid = meta["id"]
        file = PILOT / f"{pid}.json"
        require(sha256(file.read_bytes()).hexdigest() == pilot_manifest["files"][file.name], f"{pid}: altered pilot pack")
        pilot = read(file)
        passage_dir = args.run_dir / "release" / pid
        clean = pilot["conditions"]["clean"]["text"]
        require((passage_dir / "_base/llm_prompt_high/passage_target.txt").read_text() == clean, f"{pid}: altered clean")
        conditions = {name: pilot["conditions"][name] for name in ("clean", "wbw")}
        pack = {"id": pid, "reference": pilot["reference"], "english_sha256": pilot["english_sha256"],
                "conditions": conditions, "families": {}}
        for family in FAMILIES:
            variants, info = build_family(passage_dir, meta, pilot, family)
            conditions.update(variants)
            pack["families"][family] = info
        packs[pid] = pack

    require(len(packs) == 10 and all(len(p["conditions"]) == 20 for p in packs.values()), "Incomplete passage grid")
    windows = verify_windows(packs)
    differences = {pid: [n for n, c in p["conditions"].items() if c.get("matches_pilot_text") is False]
                   for pid, p in packs.items()}
    policies = {pid: {f: i["selection"] for f, i in p["families"].items() if i["selection"] != "strictly_nested"}
                for pid, p in packs.items()}
    manifest = {"release_id": DEST.name, "source_release": PILOT.name, "families": list(FAMILIES),
                "target_percentages": list(RATES), "coverage_tolerance_pp": TOLERANCE_PP,
                "passages": len(packs), "defect_variants": 180, "control_texts": 20,
                "selection_exceptions": {k: v for k, v in policies.items() if v},
                "different_from_pilot_text": {k: v for k, v in differences.items() if v},
                "window_validation": windows, "files": {}}
    dest = args.output_dir
    dest.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dest.parent) as temp:
        stage = Path(temp) / dest.name
        for pid, pack in packs.items():
            file = stage / f"{pid}.json"
            save(file, pack)
            manifest["files"][file.name] = sha256(file.read_bytes()).hexdigest()
        save(stage / "manifest.json", manifest)
        if dest.exists():
            require({p.name for p in dest.iterdir()} == {p.name for p in stage.iterdir()} and
                    all((dest / p.name).read_bytes() == p.read_bytes() for p in stage.iterdir()),
                    f"Different release already exists at {dest}")
        else:
            stage.rename(dest)
    print(f"{dest}: verified 180 variants across {len(packs)} passages")


if __name__ == "__main__":
    main()
