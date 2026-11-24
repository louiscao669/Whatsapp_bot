"""Versioned, QA-blind comparison of the pilot's clean Chinese passage translations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import re
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

from dotenv import load_dotenv
from openai import OpenAI

from evaluation.scripts.scoring.current.translation_quality import llm_translation_messages

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "human_pilot"))
from pilot_import import load_tier1_metadata, parse_tier1_verses

BASE = ROOT / "evaluation/outputs/tier1_bsb_unblinded_5opt_think"
RUN = ROOT / "evaluation/runs/clean_passage_sol_astra_2026-11-09"
PILOT = ("t1_judg9", "t1_2kgs6_7", "t1_acts20")
WRITER = "gpt-6.1-sol"
JUDGE = "gpt-6-astra"
TARGETS = {"t1_judg9": "9:25", "t1_2kgs6_7": "7:11"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    Path(f.name).replace(path)


def freeze(path, data):
    if path.exists():
        if read(path) != data:
            raise ValueError(f"Different inputs or settings in {path}; choose a fresh run directory")
    else:
        save(path, data)


def api_call(client, directory, name, model, messages, schema=None):
    kwargs = dict(model=model, input=messages, store=False, reasoning={"effort": "medium"})
    if schema is not None:
        kwargs["text"] = {"format": {"type": "json_schema", "name": "review", "strict": True, "schema": schema}}
    freeze(directory / f"{name}.request.json", kwargs)
    receipt = directory / f"{name}.response.json"
    if not receipt.exists():
        result = client.responses.create(**kwargs)
        if result.status != "completed" or not result.output_text.strip():
            raise RuntimeError(f"{name} returned {result.status}")
        save(receipt, dict(request_id=result.id, returned_model=result.model,
                           usage=result.usage.model_dump() if result.usage else {}, output=result.output_text))
    return read(receipt)["output"]


def freeze_source(run, meta):
    pid = meta["id"]
    base = BASE / pid / "_base/llm_prompt_high"
    data = read(base / "passage_translation.json")
    source, = data["source_texts"]
    baseline, = data["translations"]
    if data["method"] != "llm_prompt_high" or data["target_language"] != "Simplified Chinese":
        raise ValueError(f"Wrong baseline for {pid}")
    serving = BASE / pid / "omission/0%/passage_target_decanonicalized.txt"
    if baseline.strip() != serving.read_text().strip():
        raise ValueError(f"{pid} clean serving file differs from the saved baseline")
    source_path = read(base / "decanonicalized_metadata.json")["source"]["passage_file"]
    if source.strip() != (ROOT / source_path).read_text().strip():
        raise ValueError(f"{pid} source differs from the English passage file")
    snapshot = dict(reference=meta["reference"], english=source, baseline=serving.read_text().strip(),
                    source_path=source_path, baseline_path=str(serving.relative_to(ROOT)))
    freeze(run / pid / "inputs.json", snapshot)
    return snapshot


def translate(client, run, meta):
    pid = meta["id"]
    snapshot = freeze_source(run, meta)
    messages = llm_translation_messages(snapshot["english"], "Simplified Chinese", "high")
    value = api_call(client, run / pid, "writer", WRITER, messages)
    (run / pid / "candidate.txt").write_text(value.strip()+"\n", encoding="utf-8")
    print("Translated", meta["reference"], flush=True)


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def array_schema(item):
    return {"type": "array", "items": item}


TEXT = {"type": "string"}
ISSUE = object_schema({
    "verse": TEXT, "affected": {"type": "string", "enum": ["A", "B", "both"]},
    "source_quote": TEXT, "target_anchor": TEXT, "explanation": TEXT,
})
REVIEW_SCHEMA = object_schema({
    "assessed_verses": array_schema(TEXT), "material_issues": array_schema(ISSUE),
    "focus_verses": array_schema(object_schema({"verse": TEXT, "A_literal_English": TEXT, "B_literal_English": TEXT})),
    "preference": {"type": "string", "enum": ["A", "B", "tie"]}, "reason": TEXT,
})
REVIEW_PROMPT = """Compare two anonymous Simplified Chinese translations with the numbered English source.
Read every verse including its surrounding context. Treat the supplied English as authoritative.
Inspect agency, speaker/addressee, action, objects, target or beneficiary, time, causal and discourse
relations, quantities, negation, ambiguity, names and references. Flag any material loss, addition
or change that could give an attentive reader a different understanding of what happened or why.
Record material errors even in the better overall translation; advantages elsewhere do not cancel
them. Mark 'both' for the same defect in both. Natural Chinese paraphrases, recognized equivalent
names, register, and style differences are fine. Do not flag a defensible reading solely for
differing from your favored Bible interpretation. List each verse label exactly once in assessed_verses.
For each issue give the decisive exact source words, a short exact Chinese anchor in the affected
version (in A if both), and explain the concrete difference. Use one verse label for its primary
location. For focus_verses, provide a literal English rendering of each Chinese version at the
requested verse, based only on its Chinese wording. Leave the list empty when none are requested.
Give an overall preference on faithfulness with a short explanation. You do not know the origin
or models of A and B. Do not infer their identities."""


def numbered_verses(text, meta):
    # Embedded comma-grouped quantities such as 307,500 are not verse markers.
    escaped = re.sub(r"(?<=\d),(?=\d{3}\b)", "__THOUSANDS__", text)
    return [(k, v.replace("__THOUSANDS__", ",")) for k, v in parse_tier1_verses(escaped, meta)]


def review(client, run, meta):
    pid = meta["id"]
    directory = run / pid
    source = freeze_source(run, meta)
    versions = {"source": source["english"], "baseline": source["baseline"],
                "candidate": (directory / "candidate.txt").read_text()}
    verses = {}
    for name, text in versions.items():
        parts = numbered_verses(text, meta)
        verse_map = dict(parts)
        if len(verse_map) != len(parts) or ("source" in verses and list(verse_map) != list(verses["source"])):
            raise ValueError(f"{pid}: {name} verse markers differ from the English source")
        verses[name] = verse_map
    freeze(directory / "aligned.json", verses)
    focus = [TARGETS[pid]] if pid in TARGETS else []
    # Counterbalance the first position across passages, then swap it independently.
    first = ["baseline", "candidate"]
    if int(sha256(pid.encode()).hexdigest(), 16) % 2:
        first.reverse()
    rounds = []
    for order in (first, first[::-1]):
        labels = dict(zip("AB", order))
        tasks = {"English": verses["source"], "A": verses[labels["A"]], "B": verses[labels["B"]],
                 "focus_verses": focus}
        messages = [{"role": "system", "content": REVIEW_PROMPT},
                    {"role": "user", "content": json.dumps(tasks, ensure_ascii=False)}]
        name = "blind_" + str(len(rounds) + 1)
        raw = api_call(client, directory, name, JUDGE, messages, REVIEW_SCHEMA)
        result = json.loads(raw)
        if (sorted(result["assessed_verses"]) != sorted(verses["source"])
                or [r["verse"] for r in result["focus_verses"]] != focus):
            raise ValueError(f"{pid} {name}: incomplete verse review")
        findings = []
        for issue in result["material_issues"]:
            side = issue["affected"]
            affected = labels[side] if side in labels else "both"
            label = issue["verse"]
            anchor_version = labels["A"] if affected == "both" else affected
            # Preserve questionable quotation matches for explicit adjudication.
            findings.append(dict(issue, affected=affected,
                                 exact_source=issue["source_quote"] in verses["source"].get(label, ""),
                                 exact_anchor=issue["target_anchor"] in verses[anchor_version].get(label, "")))
        rounds.append({"order": labels, "preference": labels.get(result["preference"], "tie"),
                       "reason": result["reason"], "issues": findings,
                       "focus": [{version: f[letter+"_literal_English"] for letter, version in labels.items()}
                                 for f in result["focus_verses"]]})
    save(directory / "unblinded.json", rounds)
    print("Reviewed both orders:", meta["reference"], flush=True)


EDITS = object_schema({"edits": array_schema(object_schema({"verse": TEXT, "chinese": TEXT, "reason": TEXT}))})
VALIDATION = object_schema({"checks": array_schema(object_schema({
    "verse": TEXT, "faithful": {"type": "boolean"}, "reason": TEXT,
}))})


def finalize_clean(client, run, meta):
    pid = meta["id"]
    directory = run / pid
    aligned = read(directory / "aligned.json")
    concerns = {}
    for order in read(directory / "unblinded.json"):
        for issue in order["issues"]:
            if issue["affected"] != "baseline":
                concerns.setdefault(issue["verse"], []).append(issue["explanation"])
    current = aligned["candidate"].copy()
    pending = dict(concerns)
    for attempt in range(1, 4):
        if not pending:
            break
        edited_labels = list(pending)
        prompt = ("Revise only the specified verse texts of this Simplified Chinese translation. "
                  "Use the provided English as the sole authority. Make the smallest change that "
                  "fixes a genuine meaning error; retain the current Chinese if a criticism is "
                  "unsupported. Do not add interpretation, numbering or commentary to the translation. "
                  "Return each specified label once, with its complete replacement verse and a reason.")
        payload = {"english_context": aligned["source"], "chinese_context": current, "findings": pending}
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload,ensure_ascii=False)}]
        edits = json.loads(api_call(client, directory, f"repair_{attempt}", WRITER, messages, EDITS))["edits"]
        if sorted(e["verse"] for e in edits) != sorted(edited_labels):
            raise ValueError(f"Incomplete correction for {pid}")
        for e in edits:
            text = e["chinese"].strip()
            if not text or not re.search(r"[\u3400-\u9fff]", text):
                raise ValueError("Empty or non-Chinese repair")
            current[e["verse"]] = text
        prompt = ("Independently assess the specified Chinese verses against the English passage. "
                  "Check all meaning, agency, scope, numbers, and surrounding context. Verify any "
                  "previously flagged issue is resolved without introducing a new material error. "
                  "Accept faithful paraphrases. Return faithful true or false and concrete evidence for each label.")
        data = {"english": aligned["source"], "chinese": current, "verses_to_check": pending}
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(data,ensure_ascii=False)}]
        checks = json.loads(api_call(client, directory, f"repair_review_{attempt}", JUDGE, messages, VALIDATION))["checks"]
        if sorted(c["verse"] for c in checks) != sorted(edited_labels):
            raise ValueError(f"Incomplete repair verification for {pid}")
        pending = {c["verse"]: [c["reason"]] for c in checks if not c["faithful"]}
    if pending:
        raise ValueError(f"{pid} has unresolved corrections: {pending}")
    original = (directory / "candidate.txt").read_text().strip()
    for label in concerns:
        before = aligned["candidate"][label]
        if before != current[label]:
            if original.count(before) != 1:
                raise ValueError(f"{pid} {label} cannot be uniquely patched")
            original = original.replace(before, current[label], 1)
    exported = dict(parse_tier1_verses(original, meta))
    if exported != current or list(exported) != list(aligned["source"]):
        raise ValueError(f"{pid} release text differs from the adjudicated verse map")
    out = run / "release" / pid / "_base/llm_prompt_high"
    out.mkdir(parents=True, exist_ok=True)
    for filename in ("passage_target.txt", "passage_target_decanonicalized.txt"):
        (out / filename).write_text(original + "\n", encoding="utf-8")
    (out / "passage_source_decanonicalized.txt").write_text(read(directory/"inputs.json")["english"].strip()+"\n")
    package = read(BASE / pid / "_base/llm_prompt_high/passage_translation.json")
    package.update(translations=[original], model=WRITER, verifier=JUDGE)
    save(out / "passage_translation.json", package)
    save(directory / "clean_release.json", {"sha256": sha256(original.encode()).hexdigest(), "verses":current,
                                           "corrected_verses":[k for k in concerns if current[k]!=aligned["candidate"][k]]})
    print("Finalized", meta["reference"], "checked repair labels", list(concerns), flush=True)


def decide_pilot(run, ambush_evidence, shouting_evidence):
    """Record the inspected Chinese evidence and block expansion on new review findings."""
    diagnostics = {}
    for pid, evidence in zip(TARGETS, (ambush_evidence, shouting_evidence)):
        label = TARGETS[pid]
        verses = read(run / pid / "aligned.json")
        if not evidence or evidence not in verses["candidate"][label]:
            raise ValueError(f"Supply an exact Chinese quotation confirming the diagnostic at {label}")
        diagnostics[pid] = dict(verse=label, source=verses["source"][label], old=verses["baseline"][label],
                                new=verses["candidate"][label], restored=True)
    counts = {}
    candidate_only = 0
    for pid in PILOT:
        rounds = read(run / pid / "unblinded.json")
        if len(rounds) != 2 or rounds[0]["order"]["A"] == rounds[1]["order"]["A"]:
            raise ValueError("Two counterbalanced reviews are required")
        counts[pid] = [len(r["issues"]) for r in rounds]
        candidate_only += sum(i["affected"] == "candidate" for r in rounds for i in r["issues"])
    freeze(run / "pilot_decision.json", dict(expand=candidate_only == 0, diagnostics=diagnostics,
           material_findings_per_order=counts, candidate_only_material_findings=candidate_only,
           review_hashes={p: sha256((run/p/"unblinded.json").read_bytes()).hexdigest() for p in PILOT}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "translate", "review", "decide", "finalize"])
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true", help="Use all ten after the pilot passes; cached calls are reused.")
    scope.add_argument("--remaining", action="store_true", help="Run the other seven after the pilot decision passes.")
    parser.add_argument("--run-dir", type=Path, default=RUN)
    parser.add_argument("--ambush-evidence", help="Verified quotation naming the ambush target.")
    parser.add_argument("--shouting-evidence", help="Verified quotation retaining the shouted announcement.")
    args = parser.parse_args()
    catalog = {m["id"]: m for m in load_tier1_metadata(ROOT / "evaluation")}
    freeze(args.run_dir / "plan.json", {
        "pilot": list(PILOT), "control": "t1_acts20", "writer": WRITER, "reviewer": JUDGE,
        "diagnostics": {"t1_judg9/9:25": "The ambush explicitly targets Abimelech.",
                        "t1_2kgs6_7/7:11": "The gatekeepers explicitly raise their voices to pass on the news."},
        "gate": "Both missing details restored; no substantiated new material error in any pilot passage.",
        "review": "Two anonymous comparisons per passage in reversed order; answer keys excluded.",
    })
    selected = list(PILOT)
    if args.remaining or args.all:
        decision = read(args.run_dir / "pilot_decision.json")
        if not decision["expand"] or decision["review_hashes"] != {
            pid: sha256((args.run_dir/pid/"unblinded.json").read_bytes()).hexdigest() for pid in PILOT
        }:
            raise ValueError("A passing decision for these pilot reviews is required")
        selected = list(catalog) if args.all else [pid for pid in catalog if pid not in PILOT]
    for pid in selected:
        freeze_source(args.run_dir, catalog[pid])
    if args.action == "decide":
        return decide_pilot(args.run_dir,args.ambush_evidence,args.shouting_evidence)
    if args.action == "prepare":
        return
    load_dotenv(ROOT / ".env")
    client = OpenAI(base_url="https://api.openai.com/v1", timeout=240, max_retries=2)
    with ThreadPoolExecutor(max_workers=3) as pool:
        operation = {"translate": translate, "review": review, "finalize": finalize_clean}[args.action]
        list(pool.map(lambda pid: operation(client, args.run_dir, catalog[pid]), selected))


if __name__ == "__main__":
    main()
