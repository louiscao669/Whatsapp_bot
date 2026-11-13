"""Verify and publish a local passage pack without changing participant assignments."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from evaluation.scripts.pipeline.compare_clean_passages import BASE, ROOT, RUN, PILOT, read, freeze, save
from evaluation.scripts.pipeline.prepare_clean_passage_conditions import FILES, grammar, mis, omission, validate_reviewed_bank
from eten_shared.verse_windows import pad_window_verses
from human_pilot.pilot_import import load_tier1_metadata, parse_tier1_verses

CONDITIONS = {"clean": "omission/0%", "omission15":"omission/15%", "omission30":"omission/30%",
              "mistranslation15":"mistranslation/15%", "mistranslation30":"mistranslation/30%",
              "grammar30":"grammar/30%", "wbw":"google_word_by_word"}
RELEASE_ID = "tier1_zh_sol_v1_2026-11-09"
DEST = ROOT / "evaluation/datasets/passages" / RELEASE_ID


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(text):
    return sha256(text.encode()).hexdigest()


def verify_passage(run, meta):
    pid = meta["id"]
    src = run/"release"/pid
    base = src/"_base/llm_prompt_high"
    clean = (base/FILES[0]).read_text()
    release = read(run/pid/"clean_release.json")
    inputs = read(run/pid/"inputs.json")
    english = inputs["english"]
    require(digest(clean.strip()) == release["sha256"], "Clean release hash mismatch")
    labels = list(release["verses"])
    data = {"id":pid, "reference":meta["reference"], "english_sha256":digest(english),
            "english_path":inputs["source_path"], "baseline_sha256":digest(inputs["baseline"]), "conditions":{}}
    selected = {}
    approved = {}
    mis_bank = None
    for condition, rel in CONDITIONS.items():
        cell = src/rel
        rendered = (cell/FILES[1]).read_text()
        package = read(cell/"passage_translation.json")
        require((cell/FILES[0]).read_text() == rendered and package["translations"][0].strip() == rendered.strip(),
                f"{pid}/{condition}: JSON and serving files disagree")
        require(package["source_texts"] == [english], f"{pid}/{condition}: changed English")
        pairs = parse_tier1_verses(rendered,meta)
        actual_labels = [k for k,v in pairs]
        require(len(actual_labels)==len(set(actual_labels)) and all(v.strip() for _,v in pairs),f"{pid}/{condition}: invalid verses")
        subset = [k for k in labels if k in actual_labels]
        require(actual_labels==(subset if condition.startswith("omission") else labels),f"{pid}/{condition}: invalid verse labels")
        entry = dict(text=rendered, text_sha256=digest(rendered), verses=dict(pairs))
        if condition=="clean":
            require(rendered==clean and dict(pairs)==release["verses"],f"{pid}: incorrect clean")
        elif condition=="wbw":
            require(rendered==(BASE/pid/rel/FILES[1]).read_text(),f"{pid}: word-by-word text changed")
        else:
            family = rel.split("/")[0]
            metadata = read(cell/(family+"_metadata.json"))
            details = metadata["files"]["passage_target"]
            rate = details["requested_rate"]
            require(abs(rate-float(rel.split("/")[1][:-1])/100)<1e-9,f"{pid}/{condition}: wrong requested dose")
            measured = details["actual_affected_rate"] if family=="grammar" else details["actual_rate"]
            require(abs(rate-measured)<=.020000001,f"{pid}/{condition}: coverage {measured:.3%}")
            entry.update(requested_rate=rate, actual_rate=measured)
            if family=="omission":
                indices = [x["unit_index"] for x in details["omitted_units"]]
                original, _ = omission.apply_omissions(clean,rate=rate,seed=details["seed"],selected_unit_indices=indices)
                selected[condition]=set(indices)
            elif family=="grammar":
                bank = read(src/"grammar/_grammar_bank"/f"bank_{details['bank_id']}.json")
                original, _ = grammar.apply_grammar_bank(clean,rate=rate,seed=details["seed"],bank=bank,
                                                         selected_bank_indices=details["selected_bank_indices"])
                require(details["protected_verified"] and not details["protected_losses"],f"{pid}: protected grammar terms")
                entry["bank_id"]=bank["bank_id"]
                entry["proposer"]=bank["spec"]["proposer"]["model"]
                entry["grammar_judge"]=bank["spec"]["judge"]["model"]
                entry["meaning_judge"]=bank["spec"]["meaning_judge"]["judge"]["model"]
            else:
                if not approved:
                    mis_bank = read(src/"_base/_shared/mistranslation_bank_coverage_zh.json")
                    validate_reviewed_bank(mis_bank, clean)
                    groups = mis.candidate_groups(mis.find_occurrences(clean,mis.normalized_replacements(mis_bank)))
                    approved.update({(g["bank_index"],tuple((o["start"],o["end"]) for o in g["occurrences"])):i
                                     for i,g in enumerate(groups)})
                indices = [approved[g["bank_index"],tuple((o["start"],o["end"]) for o in g["occurrences"])]
                           for g in details["substitution_groups"]]
                original, _ = mis.apply_mistranslations(clean,rate=rate,seed=details["seed"],bank=mis_bank,
                                                         selected_group_indices=indices)
                selected[condition]=set(indices)
                require(mis_bank["bank_id"]==metadata["bank_id"],f"{pid}: incorrect substitution bank")
                entry["bank_id"]=mis_bank["bank_id"]
                entry["proposer"]=mis_bank["generation"]["model"]
                entry["substitution_judge"]=mis_bank["validation"]["judge"]["model"]
            require(original==rendered, f"{pid}/{condition}: variant could not be reconstructed")
        data["conditions"][condition]=entry
    for family in ("omission","mistranslation"):
        require(selected[family+"15"] < selected[family+"30"], f"{pid}/{family}: non-nested doses")
    return data


def verify_windows(packs):
    root = ROOT/"evaluation/datasets/qa/reviewed122"
    eligible = {r["id"] for r in read(root/"pilot_review.json") if r["status"]=="eligible"}
    bank = [r for r in read(root/"zh.json") if r["id"] in eligible]
    require(len(bank)==len(eligible)==119,"Expected 119 previously eligible pilot items")
    counts=Counter()
    padded=Counter()
    for r in bank:
        labels = list(r["verses"])
        occupied = {v for other in bank if other["id"]!=r["id"] and other["source"]==r["source"]
                    and other["passage_id"]==r["passage_id"] for v in other["verses"]}
        for condition,record in packs[r["passage_id"]]["conditions"].items():
            verses = [SimpleNamespace(verse_number=k,text=v) for k,v in record["verses"].items()]
            found = [v for v in verses if v.verse_number in labels]
            if condition == "clean":
                require([v.verse_number for v in found]==labels, f"Lost clean window for {r['id']}")
            elif len(found)<3:
                found = pad_window_verses(labels,verses,occupied=occupied)
                padded[condition]+=1
            require(found and all(v.text.strip() for v in found),f"Empty {condition} window for {r['id']}")
            counts[condition]+=1
    return dict(items=len(bank),nonempty_by_condition=dict(counts),padded_by_condition=dict(padded))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir",type=Path,default=RUN)
    args=parser.parse_args()
    root=args.run_dir
    catalog=load_tier1_metadata(ROOT/"evaluation")
    packs={m["id"]:verify_passage(root,m) for m in catalog}
    require(len(packs)==10,"Expected ten passages")
    validation=verify_windows(packs)
    votes=Counter(r["preference"] for p in packs for r in read(root/p/"unblinded.json"))
    repairs={p:read(root/p/"clean_release.json")["corrected_verses"] for p in packs}
    passage_results = {}
    for pid in packs:
        rounds = read(root/pid/"unblinded.json")
        passage_results[pid] = {"preferences": [r["preference"] for r in rounds],
                                "material_issue_verses": {
                                    side: sorted({i["verse"] for r in rounds for i in r["issues"] if i["affected"] == side})
                                    for side in ("baseline", "candidate", "both")}}
        if repairs[pid]:
            checks = sorted((root/pid).glob("repair_review_*.response.json"))
            verified = {r["verse"] for f in checks for r in json.loads(read(f)["output"])["checks"] if r["faithful"]}
            require(verified >= set(repairs[pid]), f"{pid}: missing independent correction review")
    ranges={c:[min(p["conditions"][c]["actual_rate"] for p in packs.values()),
               max(p["conditions"][c]["actual_rate"] for p in packs.values())]
            for c in CONDITIONS if c not in ("clean","wbw")}
    summary=dict(release_id=RELEASE_ID,writer="gpt-6.1-sol",reviewer="gpt-6-astra",prior_model="gpt-4.1-mini",
                 pilot=list(PILOT),decision=read(root/"pilot_decision.json"),full_review_preferences=dict(votes),
                 repaired_verses={k:v for k,v in repairs.items() if v}, passages=len(packs),
                 passage_results=passage_results,
                 clean_verses=sum(len(p["conditions"]["clean"]["verses"]) for p in packs.values()),
                 condition_texts=len(packs)*len(CONDITIONS), coverage_ranges=ranges,window_validation=validation)
    compatibility = read(root/"pilot_mcq_check/comparison.json")
    summary["paired_question_check"] = {
        "reader": read(root/"pilot_mcq_check/blind_manifest.json")["model"],
        "counts": compatibility["counts"],
        "new_disagreements": [r["id"] for r in compatibility["items"] if r["old_match"] and not r["new_match"]],
        "new_matches": [r["id"] for r in compatibility["items"] if not r["old_match"] and r["new_match"]],
    }
    # Publish only after every cell has been replayed and the delivery windows verified.
    DEST.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=DEST.parent) as temp:
        stage=Path(temp)/RELEASE_ID
        for pid,data in packs.items():
            save(stage/f"{pid}.json",data)
        summary["files"]={p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(stage.glob("*.json"))}
        save(stage/"manifest.json",summary)
        if DEST.exists():
            require(all((DEST/p.name).read_bytes()==p.read_bytes() for p in stage.iterdir()),"Release ID already differs")
        else:
            stage.rename(DEST)
    save(root/"release_report.json",summary)
    print(json.dumps({k:summary[k] for k in ("release_id","clean_verses","condition_texts","coverage_ranges","window_validation")}))


if __name__ == "__main__":
    main()
