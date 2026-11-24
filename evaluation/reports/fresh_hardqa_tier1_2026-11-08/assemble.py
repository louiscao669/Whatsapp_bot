"""Verify unit banks, check duplicates across chapter boundaries, and export all passages."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from dotenv import dotenv_values
from openai import OpenAI

from run_batch import GENERATOR, MANIFEST, REPO, ROOT, SCRIPTS

sys.path.insert(0, str(REPO))
from evaluation.scripts.mcq.diagnostics import check_hard85_rules as rules
from evaluation.scripts.mcq.diagnostics.curate_generated_chapter import signature
from evaluation.scripts.mcq.diagnostics.experiment_hard66_selectors import read, save, atomic_write

ORDER = ["t1_judg9", "t1_judg17_18", "t1_2kgs6_7", "t1_1kgs13", "t1_2kgs11",
         "t1_2chr26", "t1_2sam21", "t1_acts19", "t1_acts20", "t1_acts23"]


def check_across_chapters(passage, questions, client):
    batch = [dict(id=q["id"], question=q["question"], key=q["answer"], competitor=q["competitor"],
                  window="\n".join(f"[{q['chapter']}:{v}] {s}" for v, s in q["window_text"].items()))
             for q in questions]
    raw = []
    for order in (batch, list(reversed(batch))):
        name = "cross_" + signature([rules.MODEL, rules.DUP_PROMPT, order])
        result = rules.ask(client, name, rules.DUP_PROMPT, order, rules.Pairs, output_dir=ROOT)
        raw.append(result["pairs"])
    # Within-chapter pairs have already had a two-order check on this wording.
    chapters = {q["id"]:q["chapter"] for q in questions}
    cross = [[p for p in pairs if chapters[p["preferred"]] != chapters[p["redundant"]]] for pairs in raw]
    return dict(passage=passage, reads=raw, decisions=rules.duplicate_decisions(cross))


def verify_unit(unit, verify_only):
    original = Path(unit["run"])
    with TemporaryDirectory() as temp:
        directory = original
        if unit["carried"]:
            directory = Path(temp) / "carried"
            shutil.copytree(original, directory)
        args = [sys.executable, str(SCRIPTS / "curate_generated_chapter.py"), "--generator-root",
                str(GENERATOR), "--run-dir", str(directory)]
        if not verify_only and not unit["carried"] and (directory / "edits.json").exists():
            subprocess.run(args, check=True)
        subprocess.run(args + ["--verify"], check=True)
        if unit["carried"] and read(directory / "final_bank.json") != read(original / "final_bank.json"):
            raise ValueError("Carried bank failed offline verification")


def main(verify_only):
    os.environ.setdefault("OPENAI_API_KEY", dotenv_values(REPO / ".env").get("OPENAI_API_KEY") or "")
    client = None if verify_only else OpenAI(base_url="https://api.openai.com/v1", timeout=240, max_retries=2)
    (ROOT / "responses").mkdir(exist_ok=True)
    units = defaultdict(list)
    with ThreadPoolExecutor(max_workers=4) as workers:
        checks = [workers.submit(verify_unit, unit, verify_only) for unit in MANIFEST]
        for future in checks:
            future.result()
    for unit in MANIFEST:
        units[unit["passage"]].append(unit)
    if set(units) != set(ORDER):
        raise ValueError("Passage roster mismatch")
    all_kept = []
    all_omitted = []
    cross_checks = []
    table = []
    sections = []
    totals = [0] * 6
    for pid in ORDER:
        passage_units = units[pid]
        local = []
        counts = [0] * 6  # verses, windows, drafts, finalists, kept, kept after editing
        omitted = []
        for unit in passage_units:
            directory = Path(unit["run"])
            windows = read(directory / "windows.json")
            audit = read(directory / "editorial_audit.json")["items"]
            kept = read(directory / "final_bank.json")
            accepted = {r["id"]:r for r in audit if r["final_decision"] == "keep"}
            if set(accepted) != {r["id"] for r in kept} or len(accepted) != len(kept):
                raise ValueError("Editorial records do not match exported bank")
            counts[0] += unit["range"][1] - unit["range"][0] + 1
            counts[1] += len(windows)
            counts[2] += sum(w["generated"] for w in windows)
            counts[3] += len(audit)
            for r in kept:
                local.append(dict(r, id=unit["unit"] + ":" + r["id"], passage_id=pid,
                                  chapter=unit["chapter"], unit_id=r["id"], revised=bool(accepted[r["id"]]["edit"])))
            for r in audit:
                if r["final_decision"] != "keep":
                    why = [r["checks"][p]["reason"] for p in rules.PERSPECTIVES if rules.verdict(r["checks"][p]) != "keep"]
                    if r.get("duplicate_reason"):
                        why.append(r["duplicate_reason"])
                    omitted.append(dict(id=unit["unit"] + ":" + r["id"], passage_id=pid, reference=r["reference"],
                                        question=r["question"], decision=r["final_decision"], reasons=why))
        if len(passage_units) > 1 and len(local) >= 2:
            check = check_across_chapters(pid, local, client)
            cross_checks.append(check)
            decisions = check["decisions"]
            for q in local:
                if q["id"] in decisions:
                    decision, why = decisions[q["id"]]
                    omitted.append(dict(id=q["id"],passage_id=pid,reference=q["reference"],
                                        question=q["question"],decision=decision,reasons=[why]))
            local = [q for q in local if q["id"] not in decisions]
        counts[4] = len(local)
        counts[5] = sum(q["revised"] for q in local)
        totals = [a+b for a,b in zip(totals,counts)]
        first, last = passage_units[0], passage_units[-1]
        end = str(last["range"][1]) if first is last else last["chapter"].split()[-1] + ":" + str(last["range"][1])
        label = first["chapter"] + ":" + str(first["range"][0]) + "–" + end
        table.append("| " + label + " | " + " | ".join(map(str,counts)) + " |")
        sections += ["", "## "+label, "", "| Verses | Question | Answer key |", "|---|---|---|"]
        for q in local:
            sections.append("| " + " | ".join(q[f].replace("|","\\|") for f in ("reference","question","answer")) + " |")
        all_kept.extend(local)
        all_omitted.extend(omitted)
    if len({q["id"] for q in all_kept}) != len(all_kept) or totals[3] != len(all_kept) + len(all_omitted):
        raise ValueError("Bank totals do not reconcile")
    save(ROOT / "final_bank.json", all_kept)
    save(ROOT / "cross_chapter_review.json", cross_checks)
    save(ROOT / "omitted_finalists.json", all_omitted)
    intro = ["# Tier-1 English hard questions", "",
             f"**{totals[4]} questions met the selection rules across ten passages.**",
             "", "GPT-5 generated candidates from the English verse windows and checked whether a reader could answer with the key hidden. Two GPT-5.6 Sol assessments checked the key, wording and comprehension. The same model checked repeated questions twice in different orders. Edited questions were checked again. Each window could contribute one question. There was no target bank size.",
             "", "The 1 Kings 13 results come from the verified November 7 run. The other nine passages were generated from the same collection of English texts. The two passages spanning chapters also received a duplicate check across the chapter boundary.",
             "", "| Passage | Verses | Windows | Drafts | Finalists | Kept | Kept after editing |", "|---|---:|---:|---:|---:|---:|---:|"]
    lines = intro + table + ["| **Total** | " + " | ".join(map(str,totals))+" |"] + sections
    lines += ["", "[Bank with clean verse windows](final_bank.json) · [Omitted finalists and reasons](omitted_finalists.json) · [Cross-chapter duplicate checks](cross_chapter_review.json) · [Passage manifest](manifest.json)", ""]
    atomic_write(ROOT / "review.md", "\n".join(lines))
    print("Verified totals", totals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only",action="store_true")
    main(parser.parse_args().verify_only)

