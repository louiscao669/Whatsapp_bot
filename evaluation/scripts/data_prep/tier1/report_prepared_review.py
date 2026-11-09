"""Compare a completed, blinded prepared-QA audit with the historical Gold72 schedule."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from rewindow_tier1_disjoint import assign_disjoint_ranked, candidate_starts, load_question_ranking, required_ordinals

ROOT = Path(__file__).resolve().parents[4]


def read(path):
    return Path(path).read_text(encoding="utf-8")


def load(path):
    return json.loads(read(path))


def write(path, content):
    with NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,delete=False) as f:
        f.write(content)
    Path(f.name).replace(path)


def save(path, data):
    write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def cell(value):
    return str(value).replace("|", "\\|").replace("\n"," ")


def table(headers, rows):
    return ["| "+" | ".join(headers)+" |","|"+"|".join("---" for _ in headers)+"|",
            *["| "+" | ".join(map(cell,row))+" |" for row in rows]]


def span(labels):
    return labels[0] + "–" + (labels[-1].split(":")[-1] if labels[0].split(":")[0]==labels[-1].split(":")[0] else labels[-1])


def compare(directory):
    audit = load(directory/"audit.json")
    if audit["mode"]!="report-only":
        raise ValueError("Expected a report-only audit")
    windows = load(ROOT/"QA_algorithm/inputs/tier1_qa_verse_windows.json")["windows"]
    baseline = load(ROOT/"evaluation/datasets/tier1_gold_72_selection.json")["passages"]
    gold = {r["content_id"]:r for r in load(ROOT/"evaluation/datasets/tier1_gold_72.json")["items"]}
    rank = load_question_ranking(ROOT/"evaluation/reports/tier1_question_ranking.json")
    items = {r["content_id"]:r for r in audit["items"]}
    if len(items)!=110 or set(items)!={w["content_id"] for w in windows} or not set(gold)<=set(items):
        raise ValueError("Prepared audit does not match the historical 110")
    group = defaultdict(list)
    for row in windows:
        group[row["passage_id"]].append((row["content_id"],required_ordinals(row)))
    for cid,r in gold.items():
        if (r["question"],r["answer"]) != (items[cid]["question"],items[cid]["answer"]):
            raise ValueError(f"Historical wording mismatch for {cid}")
    original = audit["as_written"]
    revisions = audit["accepted_revisions"]
    final = {cid:(audit["rechecks"][cid] if cid in revisions else original[cid]) for cid in items}

    def placement(checks, duplicate_round):
        eligible = {}
        for cid,item in items.items():
            individual = {r["start"] for r in checks[cid] if r["passed"]}
            decisions = audit[duplicate_round].get(item["passage_id"],{}).get("decisions",{})
            if individual and cid not in decisions:
                eligible[cid] = individual
        selected = {}
        extended = {}
        for pid,cohort in group.items():
            n = baseline[pid]["n_verses"]
            selected.update(assign_disjoint_ranked(cohort,n,rank,allowed_starts=eligible)[0])
            all_n = max((w["start"]+3) for cid,_ in cohort for w in items[cid]["windows"])
            extended.update(assign_disjoint_ranked(cohort,max(n,all_n),rank,allowed_starts=eligible)[0])
        return eligible, selected, extended

    for pid, cohort in group.items():
        n = baseline[pid]["n_verses"]
        old, _ = assign_disjoint_ranked(cohort,n,rank)
        if old!=baseline[pid]["assignment"]:
            raise ValueError(f"Historical scheduling replay failed for {pid}")
        for cid,ords in cohort:
            valid = set(candidate_starts(ords,n))
            audited = {w["start"] for w in items[cid]["windows"]}
            if valid-audited or audited!={r["start"] for r in original[cid]}:
                raise ValueError(f"Missing window check: {cid}")
            if cid in audit["rechecks"] and audited!={r["start"] for r in audit["rechecks"][cid]}:
                raise ValueError(f"Incomplete revision: {cid}")
    first_eligible, first_selected, _ = placement(original,"duplicates_as_written")
    eligible, selected, extended = placement(final,"duplicates_final")
    if {k for pid in baseline for k in baseline[pid]["assignment"]}!=gold.keys():
        raise ValueError("Gold manifest and selection disagree")
    details = []
    for cid,item in items.items():
        starts = {w["start"]:w for w in item["windows"]}
        good = [r for r in original[cid] if r["passed"]]
        failed = [r for r in original[cid] if not r["passed"]]
        before_dups = audit["duplicates_as_written"].get(item["passage_id"],{}).get("decisions",{})
        after_dups = audit["duplicates_final"].get(item["passage_id"],{}).get("decisions",{})
        hist = gold.get(cid)
        old_start = hist["window_ordinals"][0] if hist else None
        chosen = selected[cid][0] if cid in selected else None
        if chosen is not None and chosen not in eligible[cid]:
            raise ValueError("Selected an unverified question/window combination")
        defect = after_dups.get(cid)
        if cid in selected:
            outcome = "Selected after revision" if cid in revisions else "Selected as written"
        elif defect:
            outcome = "Held for duplicate review" if defect["action"]=="review" else "Confirmed duplicate"
        elif cid not in eligible:
            outcome = "No passing window"
        else:
            outcome = "Eligible, unplaced"
        orig_label = "No passing window" if not good else ("Some windows flagged" if failed else "Passes every window")
        proposal = audit["proposals"].get(cid)
        def audit_window(mark):
            return {"window":span(mark["verses"]),"start":mark["start"],"passed":mark["passed"],"reasons":mark["reasons"]}
        details.append(dict(id=cid,passage=item["passage_id"],ref=item["reference"],question=item["question"],key=item["answer"],
              original_status=orig_label,default_window=span(starts[item["default_start"]]["verses"]),
              original_windows=[audit_window(mark) for mark in original[cid]],
              revised_windows=[audit_window(mark) for mark in audit["rechecks"].get(cid,[])],
              duplicate_as_written=before_dups.get(cid), duplicate_final=defect, proposed=proposal,
              accepted_revision=cid in revisions,final_status=outcome,flagged=bool(failed or cid in before_dups or defect),
              gold_window=span(starts[old_start]["verses"]) if hist else None,
              gold_window_passed=any(m["start"]==old_start for m in good) if hist else None,
              projected_window=span(starts[chosen]["verses"]) if chosen is not None else None,
              final_question=revisions.get(cid,item)["question"],final_key=revisions.get(cid,item)["answer"]))
    old_ids,new_ids=set(gold),set(selected)
    flagged=[r for r in details if r["flagged"]]
    historical_fails=[r for r in details if r["gold_window_passed"] is False]
    flagged_windows=sum(not m["passed"] for checks in original.values() for m in checks)
    all_fail=sum(not any(m["passed"] for m in checks) for checks in original.values())
    stat = dict(candidates=len(items),windows=sum(map(len,original.values())),flagged_candidate_windows=flagged_windows,
                questions_flagged=len(flagged),all_windows_fail_initially=all_fail,
                mixed_windows_initially=sum(0<sum(m["passed"] for m in c)<len(c) for c in original.values()),
                all_windows_pass_initially=sum(all(m["passed"] for m in c) for c in original.values()),
                old_gold_windows_flagged=len(historical_fails),as_written_eligible=len(first_eligible),as_written_selected=len(first_selected),
                final_individually_eligible=sum(any(m["passed"] for m in c) for c in final.values()),
                revisions_accepted=len(revisions),revisions_selected=len(set(revisions)&new_ids),
                final_eligible=len(eligible),final_selected=len(selected),eligible_unplaced=len(eligible)-len(selected),
                overlap=len(old_ids&new_ids),added=len(new_ids-old_ids),dropped=len(old_ids-new_ids),
                extended_bounds_selected=len(extended),duplicate_holds=dict(Counter(r["final_status"] for r in details if r["duplicate_final"])))
    save(directory/"selection.json",{"summary":stat,"as_written_assignment":first_selected,"projected_assignment":selected,
         "extended_bounds_assignment":extended,"items":details})
    flags = ["# Flagged prepared questions","",
             f"{len(flagged)} of 110 questions triggered a flag on at least one candidate window or in duplicate review. "
             "A question with a passing alternative window can still be selected. Every question below has its original key, the affected windows and the projected outcome.",""]
    for pid in group:
        members = [r for r in flagged if r["passage"] == pid]
        if members:
            flags += [f"## {pid} ({len(members)})", ""] + table(
                ["ID", "Reference", "Original question", "Flag", "Projected outcome"],
                [[r["id"], r["ref"], r["question"],
                  r["original_status"] + ("; duplicate review" if r["duplicate_as_written"] or r["duplicate_final"] else ""),
                  r["final_status"]] for r in members]) + [""]
    flags += ["## Window findings and revisions", ""]
    for r in flagged:
        flags += [f"### {r['id']} · {r['question']}","",f"**Key** {r['key']}  ",
                  f"**Outcome** {r['final_status']}"+(f" · {r['projected_window']}" if r["projected_window"] else "") + "  ",
                  f"**Historical Gold72 window** {r['gold_window'] or 'Outside Gold72'}",""]
        for mark in r["original_windows"]:
            if not mark["passed"]:
                flags.append(f"- **{mark['window']}** "+" ".join(mark["reasons"]))
        if r["duplicate_as_written"] or r["duplicate_final"]:
            flags.append("- **Duplicate check** "+(r["duplicate_final"] or r["duplicate_as_written"])["reason"])
            phase = "duplicates_final" if r["duplicate_final"] else "duplicates_as_written"
            for n, order in enumerate(audit[phase][r["passage"]]["orders"], 1):
                for p in order:
                    if r["id"] in (p["preferred"], p["redundant"]):
                        flags.append(f"  - Order {n} preferred {p['preferred']} over {p['redundant']}. {p['reason']}")
        if r["proposed"]:
            p = r["proposed"]; flags+=["",p["reason"]]
            if p["repairable"]:
                flags += ["",f"**Proposed wording** {p['question']}  ",f"**Proposed key** {p['answer']}  ",
                          f"**Passing revised windows** {', '.join(m['window'] for m in r['revised_windows'] if m['passed']) or 'None'}"]
                for mark in r["revised_windows"]:
                    if not mark["passed"]:
                        flags.append(f"- **Recheck {mark['window']}** "+" ".join(mark["reasons"]))
        flags += [""]
    changes = ["# Projected selection compared with original Gold72",""]
    for title, subset in [("Added",[r for r in details if r["id"] in new_ids-old_ids]),
                           ("Dropped",[r for r in details if r["id"] in old_ids-new_ids]),
                           ("Retained with revised wording or key",[r for r in details if r["id"] in old_ids&new_ids and r["accepted_revision"]]),
                           ("Retained with a different window",[r for r in details if r["id"] in old_ids&new_ids and r["gold_window"]!=r["projected_window"]])]:
        changes += [f"## {title} ({len(subset)})",""] + table(["ID","Prepared question","Gold window","Projected window","Outcome"],
               [[r["id"],r["question"],r["gold_window"] or "—",r["projected_window"] or "—",r["final_status"]] for r in subset])+[""]
    changes+=["## All projected questions",""]+table(["ID","Window","Question","Key"],
             [[r["id"],r["projected_window"],r["final_question"],r["final_key"]] for r in details if r["id"] in new_ids])+[""]
    write(directory/"flagged_questions.md","\n".join(flags))
    write(directory/"selection_changes.md","\n".join(changes))
    summary=["# Report-only review of the 110 prepared Tier-1 questions","",
      f"**{len(selected)} questions fit the projected bank**, compared with the original 72. "
      f"{stat['overlap']} original questions remain, {stat['added']} enter, and {stat['dropped']} leave. "
      f"{len(eligible)} qualify before scheduling. Of those, {stat['eligible_unplaced']} lose a non-overlapping slot.","",
      "## From 110 questions to a projected bank",""]+table(["Step","Questions"],[
      ["Pass blind and both editorial checks in at least one window as written",len(items)-all_fail],
      ["Eligible as written after duplicate checks",len(first_eligible)],["Fit the schedule as written",len(first_selected)],
      ["Additional faithful revisions passing a complete recheck",len(revisions)],["Individually eligible after revisions",stat["final_individually_eligible"]],
      ["Eligible after final duplicate checks",len(eligible)],["Fit the final schedule",len(selected)]])+["",
      f"**{len(flagged)} questions flagged.** In the first pass, {flagged_windows} of {stat['windows']} candidate windows failed. "
      f"{all_fail} questions failed in every window and {stat['mixed_windows_initially']} passed in some windows only. "
      f"{stat['old_gold_windows_flagged']} of the original 72 failed on their actual historical window. "
      f"{stat['revisions_selected']} of the proposed bank's questions use a checked revision.","",
      "[Every flagged question, key, window and reason](flagged_questions.md) · [Added, dropped, revised and all projected questions](selection_changes.md) · [Machine-readable selection](selection.json) · [Full audit](audit.json)","",
      "## Method","",
      "The audit uses canonical English Berean Standard Bible verses and the frozen 110 questions and keys supplied to the historical selector. Nine of those pairs already differed from the earlier shortened export. GPT-5 read each question alone with the key hidden and then judged the supported readings against the key. Two GPT-5.6 Sol reviews assessed wording and support; simple factual questions qualified. An item needed all three checks to pass on the same window. For questions with no passing window, a bounded revision could be proposed against original source intent. The exact revised pair was checked in every candidate window. Eligible questions received two within-passage duplicate checks in opposite orders. Unresolved duplicate groups are held for review. Historical selection and ranking were withheld from all model requests.","",
      "The local selector maximized question count in disjoint three-verse windows, then used the historical ranking for ties. A control replay reproduced all 72 historical question IDs and assignments. The main comparison preserves the original selector’s passage bounds. "
      f"Allowing all checked windows through the actual end of each passage gives {len(extended)}. This is an English open-question projection. The original QA bank and delivery records were not changed.",""]
    still_flagged = [r for r in details if r["final_status"] in ("No passing window","Confirmed duplicate","Held for duplicate review")]
    summary += ["## Questions still held after review", ""] + table(
        ["ID","Original question","Gold72","Outcome"],
        [[r["id"],r["question"],"Yes" if r["gold_window"] else "No",r["final_status"]] for r in still_flagged]) + [""]
    write(directory/"review.md","\n".join(summary))
    return stat


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    print(json.dumps(compare(parser.parse_args().directory),indent=2))
