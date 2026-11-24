"""Validate and materialize the frozen Chinese from-scratch window release."""
from collections import Counter, defaultdict
import re

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from eten_shared.experiment_plan import build_cells, SOL_SCRATCH_SET, SLOTS
from eten_shared.models import ExperimentPassage, ExperimentWindow, QAItem


DOSES = {"omission15": 15, "omission30": 30, "mistranslation15": 15,
         "mistranslation30": 30, "grammar30": 30}
CONTENT = re.compile(r"[\w\u3400-\u9fff]")


def validate_edits(clean, variant, condition):
    """Replay the stored spans against the clean text using the generator's content-character measure."""
    touched = set()
    edited = dict(clean)
    by_verse = defaultdict(list)
    for edit in variant["edits"]:
        by_verse[edit["verse"]].append(edit)
    for label, edits in by_verse.items():
        body = clean[label]
        pieces = []
        cursor = 0
        for edit in sorted(edits, key=lambda e: e["start"]):
            start, before, after = edit["start"], edit["before"], edit["after"]
            if start < cursor or before == after or not before or not body.startswith(before, start):
                raise ValueError(f"Invalid {condition} span in {label}")
            if condition.startswith("omission") and after:
                raise ValueError(f"Omission introduced text in {label}")
            if condition == "grammar30" and Counter(before) != Counter(after):
                raise ValueError(f"Grammar changed the character inventory in {label}")
            pieces.extend([body[cursor:start], after])
            touched.update((label, start + m.start()) for m in CONTENT.finditer(before))
            cursor = start + len(before)
        edited[label] = "".join(pieces) + body[cursor:]
    count = len(touched)
    total = sum(len(CONTENT.findall(body)) for body in clean.values())
    dose = DOSES[condition]
    if (edited != variant["verses"] or any(not CONTENT.search(v) for v in edited.values())
            or count != variant["affected_chars"] or variant["target_percent"] != dose
            or abs(100 * count - dose * total) > 2 * total):
        raise ValueError(f"Window text or measured dose differs for {condition}")
    return touched


def validate_release(manifest, rows, originals):
    roster = {row["id"]: row for row in rows if row["source"] == "Hard77"}
    windows = manifest["windows"]
    if (manifest["release"] != "sol-scratch66-windows-v1" or manifest["tolerance_pp"] != 2
            or manifest["condition_slots"] != SLOTS or len(windows) != 66
            or {w["id"] for w in windows} != set(roster) or len(roster) != 66):
        raise ValueError("Window release differs from the 66-question Latin-square roster")
    overrides = defaultdict(dict)
    for w in windows:
        row = roster[w["id"]]
        pid, labels, conditions = w["passage_id"], w["verses"], w["conditions"]
        clean = row["verses"]
        if (pid != row["passage_id"] or w["question"] != row["question"] or list(clean) != labels
                or set(conditions) != set(SLOTS)
                or w["clean_content_chars"] != sum(len(CONTENT.findall(t)) for t in clean.values())):
            raise ValueError(f"Different QA, verse window, or denominator for {w['id']}")
        spans = {}
        for key, v in conditions.items():
            if list(v["verses"]) != labels:
                raise ValueError(f"Different verse boundaries in {w['id']} / {key}")
            if key in DOSES:
                spans[key] = validate_edits(clean, v, key)
                entry = overrides[pid, key]
                if entry.keys() & v["verses"].keys():
                    raise ValueError(f"Overlapping windows in {pid} / {key}")
                entry.update(v["verses"])
            else:
                source = {n: t for n, _, t in originals[pid, key].verses}
                if {n: source[n] for n in labels} != v["verses"] or (key == "clean" and clean != v["verses"]):
                    raise ValueError(f"Control text differs for {w['id']} / {key}")
        for family in ("omission", "mistranslation"):
            if not spans[family + "15"] <= spans[family + "30"]:
                raise ValueError(f"Non-nested {family} doses in {w['id']}")
    return overrides


def overlay_verses(parent, clean, replacements):
    """Keep the parent variant outside study windows and restore any reintroduced verses in source order."""
    bodies = {n: t for n, _, t in parent.verses}
    bodies.update(replacements)
    return [(n, i, bodies[n]) for n, i, _ in clean.verses if n in bodies]


def verify_installed(db, manifest, rows, prefix, layout):
    """Compare persisted questions, choices, keys, groups and verse texts across all eight real rotations."""
    expected = {r["id"]: r for r in rows if r["source"] == "Hard77"}
    wrows = db.execute(select(ExperimentWindow, QAItem).join(QAItem, ExperimentWindow.qa_item_id == QAItem.id)
                       .where(ExperimentWindow.source_passage_id.startswith(prefix, autoescape=True))).all()
    saved = {w.content_id: (w, qa) for w, qa in wrows}
    held = set(manifest.get("held_for_review", []))
    if (len(saved) != len(wrows) or set(saved) - held != set(expected)
            or any(qa.review_removed_at is None for cid, (_, qa) in saved.items() if cid in held)
            or any(qa.review_removed_at is not None for cid, (_, qa) in saved.items() if cid not in held)):
        raise ValueError("The installed from-scratch question roster differs from the release")
    passages = db.scalars(select(ExperimentPassage).options(selectinload(ExperimentPassage.verses))
                          .where(ExperimentPassage.source_passage_id.startswith(prefix, autoescape=True),
                                 ExperimentPassage.language == "zh")).all()
    texts = {(p.source_passage_id, p.condition): {v.verse_number: v.text for v in p.verses} for p in passages}
    groups = {r["id"]: i * 8 // len(layout) + 1 for i, r in enumerate(layout)}
    plans = [dict((group, condition) for group, condition, _ in build_cells("verify-release", i, SOL_SCRATCH_SET))
             for i in range(8)]
    offset = min(plans[0]) - 1
    encounters = Counter()
    for w in manifest["windows"]:
        if w["id"] in held:
            continue
        item, qa = saved[w["id"]]
        row = expected[w["id"]]
        source = prefix + w["passage_id"]
        if (item.source_passage_id != source or qa.passage_id != source or qa.form_group_id != w["id"]
                or item.verse_numbers != w["verses"] or qa.question_text != row["question"]
                or qa.mcq_choices != row["choices"] or qa.mcq_correct_choice != row["correct"]
                or item.group_index != offset + groups[w["id"]]):
            raise ValueError(f"Different installed QA or group for {w['id']}")
        for plan in plans:
            key = plan[item.group_index]
            actual = texts[source, key]
            if {n: actual.get(n) for n in item.verse_numbers} != w["conditions"][key]["verses"]:
                raise ValueError(f"Installed window differs: {w['id']} / {key}")
            encounters[key] += 1
    if encounters != Counter({key: len(expected) * SLOTS.count(key) for key in set(SLOTS)}):
        raise ValueError("Unbalanced eight-rotation study")
    return dict(release=manifest["release"], verified_windows=len(expected), verified_dose_variants=len(expected)*len(DOSES),
                held=len(held), verified_rotations=len(plans), verified_question_presentations=sum(encounters.values()))
