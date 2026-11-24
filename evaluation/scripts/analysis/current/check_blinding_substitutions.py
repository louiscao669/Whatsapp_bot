"""Compare Chinese substitution candidates with the frozen v1 materials on changed items."""
from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy

import requests

from evaluation.scripts.pipeline.blind_reviewed122 import MAP, Names, blind_passage
from evaluation.scripts.analysis.current import check_blinding_comprehension as paired

ROOT = paired.ROOT
REPORT = ROOT / "evaluation/reports/blinding_substitutions_2026-11-09"
RUN = ROOT / "evaluation/runs/blinding_substitutions_2026-11-09"
MODEL = "gemma3:4b"


def prepare(proposal_file=REPORT / "candidates.json"):
    read, require = paired.read, paired.require
    table = read(MAP)
    proposals = read(proposal_file)
    by_name = {entry["canonical"]: entry for entry in table["entities"]}
    pristine = deepcopy(table)
    for changes in proposals.values():
        for name, forms in changes.items():
            original = by_name[name]["release_forms"]["zh"]
            require(set(forms) <= original.keys(), f"Unrecognized spelling for {name}")
            original.update(forms)
    published = {q["id"]: q for q in read(paired.BLIND / "qa/zh.json")}
    packs = {}
    changed_cells = Counter()
    renderers = {}
    group_for = {}
    for path in sorted(paired.SOURCE.glob("t1_*.json")):
        source = read(path)
        pid = source["id"]
        renderer = Names(table, "zh", pid)
        renderers[pid] = renderer
        candidate = blind_passage(source, renderer)
        packs[pid] = candidate
        current = read(paired.BLIND / "passages" / path.name)
        for condition, cell in candidate["conditions"].items():
            if cell["text"] != current["conditions"][condition]["text"]:
                changed_cells[pid] += 1
        # Disjoint passages permit evaluating the role and place suggestions separately.
        if changed_cells[pid]:
            reference = source["conditions"]["clean"]["text"]
            hits = Counter()
            Names(pristine, "zh", pid).apply(reference, hits)
            groups = [key for key, changes in proposals.items() if set(changes) & hits.keys()]
            require(len(groups) == 1, f"Mixed proposal sets in {pid}")
            group_for[pid] = groups[0]
    candidate_items = []
    old_items = {q["id"]: q for q in paired.load_items()}
    for q in read(paired.DATA / "qa/reviewed122/zh.json"):
        pid = q["passage_id"]
        renderer = renderers[pid]
        old = old_items[q["id"]]
        choices = {label: renderer.apply(s) for label, s in zip("ABCD", q["choices"], strict=True)}
        require(len(set(choices.values())) == 4, f"Collapsed choices for {q['id']}")
        trial = dict(id=old["index"], question=renderer.apply(q["question"]), choices=choices,
                     window={k: packs[pid]["conditions"]["clean"]["verses"][k] for k in q["verses"]})
        for text in [trial["question"], *choices.values(), *trial["window"].values()]:
            renderer.check(text, q["id"])
        require(q["correct"] == published[q["id"]]["correct"], "Different answer keys")
        if trial != old["blinded"]:
            candidate_items.append(dict(id=q["id"], group=group_for[pid], correct=q["correct"],
                                        eligibility=old["eligibility"], old=old["blinded"], new=trial))
    return candidate_items, dict(changed_cells)


def check_local_reader(session, model, manifest):
    tags = session.get(paired.LOCAL + "/api/tags", timeout=10, allow_redirects=False)
    tags.raise_for_status()
    version = session.get(paired.LOCAL + "/api/version", timeout=10, allow_redirects=False)
    version.raise_for_status()
    paired.require(version.json()["version"] == manifest["ollama"] and
                   any(m["name"] == model and m["digest"] == manifest["digest"] for m in tags.json()["models"]),
                   "Reader version or model weights changed")


def run(offline, profile):
    proposal_file = REPORT / f"{profile}.json"
    folder = RUN if profile == "candidates" else RUN / profile
    items, changed_cells = prepare(proposal_file)
    directory = paired.RUN / "gemma3_4b"
    manifest = paired.read(directory / "manifest.json")
    baseline = {r["id"]: r for r in paired.read(directory / "results.json")}
    paired.require(manifest["model"] == MODEL and manifest["batch_size"] == 1 and
                   manifest["prompt"] == paired.SHORT_PROMPT and manifest["schema"] == paired.SHORT_SCHEMA and
                   manifest["blinded_qa_sha256"] == paired.checksum(paired.BLIND / "qa/zh.json"), "Changed baseline")
    paired.freeze(folder / "manifest.json", {"reader": manifest, "candidate_sha256": paired.checksum(proposal_file),
                                         "map_sha256": paired.checksum(MAP), "affected_ids": [r["id"] for r in items]})
    with requests.Session() as session:
        session.trust_env = False
        if not offline:
            check_local_reader(session, MODEL, manifest)
        output = []
        for i, item in enumerate(items, 1):
            result = baseline[item["id"]]
            # Match the archived prompt's original field order before constructing the new one.
            existing = item["old"]
            trial = {k: item["new"][k] for k in existing}
            args = (manifest["options"], directory / "cache", True)
            verdict = paired.call(None, MODEL, [existing], *args)[0]
            paired.require(verdict == result["blinded"], "Baseline response does not match the request receipt")
            verdict_new = paired.call(None if offline else session, MODEL, [trial], manifest["options"], folder / "cache", True)[0]
            output.append({"id": item["id"], "group": item["group"], "eligible": item["eligibility"] == "eligible",
                           "key": item["correct"], "current": verdict["supported"], "candidate": verdict_new["supported"],
                           "current_question": existing["question"], "candidate_question": trial["question"],
                           "current_choices": existing["choices"], "candidate_choices": trial["choices"]})
            print(i, "/", len(items), flush=True)
    totals = {}
    for group in [*paired.read(proposal_file), "all"]:
        rows = [r for r in output if r["eligible"] and (group == "all" or r["group"] == group)]
        pairs = [(r["current"] == [r["key"]], r["candidate"] == [r["key"]]) for r in rows]
        totals[group] = dict(n=len(rows), current=sum(a for a,b in pairs), candidate=sum(b for a,b in pairs),
                             gained=pairs.count((False,True)), lost=pairs.count((True,False)))
    output_file = REPORT / ("reader_check.json" if profile == "candidates" else f"{profile}_check.json")
    paired.save(output_file, {"model": MODEL, "scores_eligible": totals, "changed_condition_texts": changed_cells,
                                               "answers": output})
    print(totals)


def confirm_shortlist(offline):
    model = paired.MODEL
    proposed, cells = prepare(REPORT / "recommended.json")
    by_id = {r["id"]: r for r in proposed}
    before = paired.RUN / model.replace(":", "_")
    after = RUN / "confirmation"
    manifest = paired.read(before / "manifest.json")
    baseline = {r["id"]: r for r in paired.read(before / "results.json")}
    paired.require(manifest["prompt"] == paired.PROMPT and manifest["schema"] == paired.SCHEMA
                   and manifest["batch_size"] == 4 and manifest["think"] is False, "Changed Qwen settings")
    paired.freeze(after / "manifest.json", {"reader": manifest, "proposal": paired.checksum(REPORT / "recommended.json"),
                                           "affected_ids": list(by_id)})
    all_items = paired.load_items()
    output = []
    singles = set()
    for path in (before / "cache").glob("*.json"):
        receipt = paired.read(path)
        if len(receipt) == 1:
            singles.add(receipt[0]["id"])
    with requests.Session() as session:
        session.trust_env = False
        if not offline:
            check_local_reader(session, model, manifest)
        for start in range(0, len(all_items), 4):
            batch = all_items[start:start + 4]
            changed = [r for r in batch if r["id"] in by_id]
            if not changed:
                continue
            old = [r["blinded"] for r in batch]
            new = [{k: by_id[r["id"]]["new"][k] for k in r["blinded"]}
                   if r["id"] in by_id else r["blinded"] for r in batch]
            reference = paired.call(None, model, old, manifest["options"], before / "cache", False)
            # If the original batch needed single-item retries, keep the same context.
            requests_to_run = [[q] for q in new] if all(q["id"] in singles for q in old) else [new]
            answers = {}
            for tasks in requests_to_run:
                answers.update((v["id"], v) for v in paired.call(None if offline else session, model, tasks,
                               manifest["options"], after / "cache", False))
            verified = {v["id"]: v for v in reference}
            for r in changed:
                key = [r["correct"]]
                current = verified[r["index"]]
                paired.require(current == baseline[r["id"]]["blinded"], "Qwen baseline request differs")
                candidate = answers[r["index"]]
                output.append(dict(id=r["id"], group=by_id[r["id"]]["group"], eligible=r["eligibility"]=="eligible",
                                   key=key[0], current=current["supported"], candidate=candidate["supported"]))
            print(len(output), "/", len(proposed), flush=True)
    rows = [r for r in output if r["eligible"]]
    paired.save(REPORT / "confirmation.json", {"model": model, "eligible": len(rows),
                "current": sum(r["current"] == [r["key"]] for r in rows),
                "candidate": sum(r["candidate"] == [r["key"]] for r in rows),
                "validated_changed_conditions": cells, "answers": output})


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--profile", choices=("candidates", "distinct_names", "role_wording"), default="candidates")
    parser.add_argument("--confirm-shortlist", action="store_true")
    args = parser.parse_args()
    if args.confirm_shortlist:
        confirm_shortlist(args.offline)
    else:
        run(args.offline, args.profile)
