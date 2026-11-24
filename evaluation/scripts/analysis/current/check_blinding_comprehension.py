"""Paired, passage-only local reader check on the Sol release before and after blinding."""
import argparse
import json
from collections import defaultdict
from hashlib import sha256
from math import comb
from pathlib import Path
from random import Random
from types import SimpleNamespace

import requests

from evaluation.scripts.pipeline.compare_clean_passages import ROOT, freeze, read, save
from evaluation.scripts.pipeline.verify_reviewed122_zh import MODEL, PROMPT, SCHEMA
from eten_shared.verse_windows import pad_window_verses

DATA = ROOT / "evaluation/datasets"
BLIND = DATA / "blinded/tier1_sol_reviewed122_v1"
SOURCE = DATA / "passages/tier1_zh_sol_v1_defect_ladder_2026-11-09"
ARCHIVE = ROOT / "evaluation/runs/clean_passage_sol_astra_2026-11-09/pilot_mcq_check"
RUN = ROOT / "evaluation/runs/blinded_comprehension_2026-11-09"
REPORT = ROOT / "evaluation/reports/blinded_comprehension_2026-11-09"
LOCAL = "http://127.0.0.1:11434"
MODELS = (MODEL, "gemma3:4b")
SHORT_PROMPT = ("请只根据每题提供的中文经文回答，选出经文支持而且确实回答所问的所有选项。"
                "若只有一个合理答案就选它；多个都合理则全选；证据不足则返回空数组。"
                "各题独立，勿用外部知识或其他题。仅按编号返回 id 和 supported。")
SHORT_SCHEMA = {"type":"object","required":["items"],"properties":{"items":{"type":"array",
                "items":{"type":"object","required":["id","supported"],"properties":{
                    "id":{"type":"integer"},"supported":{"type":"array","items":{"type":"string","enum":list("ABCD")}}}}}}}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(path):
    return sha256(path.read_bytes()).hexdigest()


def load_items():
    original = read(DATA / "qa/reviewed122/zh.json")
    blinded = read(BLIND / "qa/zh.json")
    eligibility = {v["id"]: v["status"] for v in read(BLIND / "qa/pilot_review.json")}
    packs = {p.stem: read(p) for p in SOURCE.glob("t1_*.json")}
    verified = read(ARCHIVE / "questions_with_candidate_windows.json")
    result = []
    for n, (old, new, archived) in enumerate(zip(original, blinded, verified, strict=True), 1):
        require(all(old[k] == new[k] for k in ("id", "correct", "source", "passage_id")), "Different questions or keys")
        require(list(old["verses"]) == list(new["verses"]), "Different verse ranges")
        verses = packs[old["passage_id"]]["conditions"]["clean"]["verses"]
        aligned = dict(old, verses={v: verses[v] for v in old["verses"]})
        require(aligned == archived, "Original inputs differ from the archived clean Sol run")
        row = {k: old[k] for k in ("id", "source", "passage_id", "correct")}
        row.update(index=n, eligibility=eligibility[old["id"]])
        for arm, entry in (("original", aligned), ("blinded", new)):
            row[arm] = dict(id=n, window=entry["verses"], question=entry["question"],
                            choices=dict(zip("ABCD", entry["choices"], strict=True)))
        result.append(row)
    require(len(result) == len(eligibility) == 122, "Incomplete question bank")
    return result


def variant_items(items):
    original = {p.stem: read(p) for p in SOURCE.glob("t1_*.json")}
    blinded = {p.stem: read(p) for p in (BLIND / "passages").glob("t1_*.json")}
    by_passage = defaultdict(list)
    for q in items:
        if q["eligibility"] == "eligible":
            by_passage[q["passage_id"]].append(q)
    for rows in by_passage.values():
        rows.sort(key=lambda q: sha256(("paired-blinding-v1/" + q["id"]).encode()).digest())
    cells = []
    conditions = [f + str(n) for n in (5, 10, 15, 20, 25, 30) for f in ("omission", "mistranslation", "grammar")]
    for level, condition in enumerate(conditions):
        for pid in sorted(by_passage):
            rows = by_passage[pid]
            q = rows[level % len(rows)]
            cell = {**q, "condition": condition, "index": len(cells) + 1}
            labels = list(q["original"]["window"])
            occupied = {v for other in rows if other["id"] != q["id"] and other["source"] == q["source"]
                        for v in other["original"]["window"]}
            for arm, packs in (("original", original), ("blinded", blinded)):
                texts = packs[pid]["conditions"][condition]["verses"]
                found = [SimpleNamespace(verse_number=v, text=t) for v, t in texts.items() if v in labels]
                if len(found) < 3:
                    available = [SimpleNamespace(verse_number=v, text=t) for v, t in texts.items()]
                    found = pad_window_verses(labels, available, occupied=occupied)
                cell[arm] = dict(q[arm], id=cell["index"], window={v.verse_number: v.text for v in found})
            require(list(cell["original"]["window"]) == list(cell["blinded"]["window"]), "Different delivered verses")
            cells.append(cell)
    require(len({(c["passage_id"], c["condition"]) for c in cells}) == len(cells) == 180, "Missing variant")
    return cells


def call(session, model, tasks, options, cache, short, constrain_id=False):
    schema = SHORT_SCHEMA if short else SCHEMA
    if constrain_id:
        schema = json.loads(json.dumps(schema))
        array = schema["properties"]["items"]
        array.update(minItems=1, maxItems=1)
        array["items"]["properties"]["id"] = {"type": "integer", "enum": [tasks[0]["id"]]}
    body = {"model": model, "stream": False, "think": False, "format": schema, "options": options,
            "messages": [{"role": "system", "content": SHORT_PROMPT if short else PROMPT},
                         {"role": "user", "content": json.dumps(tasks, ensure_ascii=False)}]}
    path = cache / (sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest() + ".json")
    if path.exists():
        return read(path)
    resp = session.post(LOCAL + "/api/chat", json=body, timeout=300, allow_redirects=False)
    resp.raise_for_status()
    raw = resp.json()
    try:
        require(raw.get("done") and raw.get("done_reason") != "length", "Truncated response")
        items = json.loads(raw["message"]["content"])["items"]
        require(sorted(v["id"] for v in items) == [v["id"] for v in tasks], "Missing/duplicate responses")
        for v in items:
            require((short or isinstance(v["reason"], str)) and isinstance(v["supported"], list)
                    and set(v["supported"]) <= set("ABCD") and len(v["supported"]) == len(set(v["supported"])),
                    "Invalid choice list")
    except (ValueError, TypeError, KeyError):
        if len(tasks) == 1:
            if constrain_id:
                raise
            items = call(session, model, tasks, options, cache, short, constrain_id=True)
        else:
            items = [call(session, model, [t], options, cache, short)[0] for t in tasks]
    save(path, items)
    return items


def run(model, variants):
    items = load_items()
    recipe = read(ARCHIVE / "blind_manifest.json")
    short = variants or model != MODEL
    options = dict(recipe["options"], seed=2026, num_predict=240) if short else recipe["options"]
    batch_size = 1 if model != MODEL else 4
    folder = RUN / model.replace(":", "_")
    if variants:
        items = variant_items(items)
        folder = folder / "variants"
        freeze(folder / "sample.json", [{k: row[k] for k in ("id","passage_id","condition","index")} for row in items])
    with requests.Session() as session:
        session.trust_env = False
        version = session.get(LOCAL + "/api/version", timeout=10, allow_redirects=False)
        version.raise_for_status()
        tags = session.get(LOCAL + "/api/tags", timeout=10, allow_redirects=False)
        tags.raise_for_status()
        identity = next(m["digest"] for m in tags.json()["models"] if m["name"] == model)
        freeze(folder / "manifest.json", dict(model=model, digest=identity, ollama=version.json()["version"],
               options=options, think=False, prompt=SHORT_PROMPT if short else PROMPT,
               schema=SHORT_SCHEMA if short else SCHEMA, batch_size=batch_size,
               blinded_qa_sha256=checksum(BLIND / "qa/zh.json"), archived_inputs_sha256=recipe["bank_sha256"]))
        cached_original = {}
        if model == MODEL and not variants:
            require(recipe["model_digest"] == identity and recipe["ollama_version"] == version.json()["version"]
                    and recipe["prompt"] == PROMPT and recipe["schema"] == SCHEMA and recipe["think"] is False
                    and checksum(ARCHIVE / "questions_with_candidate_windows.json") == recipe["bank_sha256"],
                    "Archived reader or input changed")
            archived = read(ARCHIVE / "blind_audit.json")
            for i in range(0, len(items), 4):
                batch = items[i:i+4]
                digest = sha256(json.dumps([recipe, [r["original"] for r in batch]], ensure_ascii=False).encode()).hexdigest()
                receipt = read(ARCHIVE / "blind_checks" / (digest + ".json"))
                cached_original.update({r["id"]: r for r in receipt})
            for q, v in zip(items, archived, strict=True):
                require(v["id"] == q["id"] and v["review"] == cached_original[q["index"]], "Archived receipt mismatch")
        result = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            arms = ("original", "blinded") if (i // batch_size) % 2 == 0 else ("blinded", "original")
            outputs = {}
            for arm in arms:
                if arm == "original" and cached_original:
                    outputs[arm] = cached_original
                else:
                    response = call(session, model, [r[arm] for r in batch], options, folder / "cache", short)
                    outputs[arm] = {r["id"]: r for r in response}
            for q in batch:
                row = {k: q[k] for k in ("id", "index", "eligibility", "source", "passage_id", "correct")}
                if variants:
                    row["condition"] = q["condition"]
                for arm in arms:
                    row[arm] = outputs[arm][q["index"]]
                    row[arm + "_match"] = row[arm]["supported"] == [q["correct"]]
                result.append(row)
            print(model, len(result), "/", len(items), flush=True)
    save(folder / "results.json", result)
    if variants:
        save(REPORT / "variants.json", {
            "model": model, "pairs": len(result), "unique_questions": len({q["id"] for q in result}),
            "original_keys": sum(q["original_match"] for q in result),
            "blinded_keys": sum(q["blinded_match"] for q in result),
            "by_family": {f: {k: v for k, v in counts([r for r in result if r["condition"].startswith(f)]).items()
                              if k != "two_sided_exact_mcnemar_p"} for f in ("omission","mistranslation","grammar")},
            "same_supported_set": sum(set(r["original"]["supported"]) == set(r["blinded"]["supported"]) for r in result),
            "all": result})
    else:
        summarize()
    if (REPORT / "variants.json").is_file() and all(
            (RUN / m.replace(":", "_") / "results.json").is_file() for m in MODELS):
        write_report()


def counts(rows):
    n = len(rows)
    lost = sum(r["original_match"] and not r["blinded_match"] for r in rows)
    gained = sum(not r["original_match"] and r["blinded_match"] for r in rows)
    old = sum(r["original_match"] for r in rows)
    new = sum(r["blinded_match"] for r in rows)
    flips = lost + gained
    p = (min(1, 2 * sum(comb(flips, i) for i in range(min(lost, gained) + 1)) / (2 ** flips))
         if flips else 1.0)
    return dict(n=n, original=old, blinded=new, lost=lost, gained=gained, difference_pp=100*(new-old)/n,
                original_key_among_supported=sum(r["correct"] in r["original"]["supported"] for r in rows),
                blinded_key_among_supported=sum(r["correct"] in r["blinded"]["supported"] for r in rows),
                newly_missed_still_including_key=sum(r["original_match"] and not r["blinded_match"]
                    and r["correct"] in r["blinded"]["supported"] for r in rows),
                two_sided_exact_mcnemar_p=p)


def summarize():
    stimuli = {q["id"]: q for q in load_items()}
    results = {}
    for model in MODELS:
        path = RUN / model.replace(":", "_") / "results.json"
        if not path.is_file():
            continue
        rows = read(path)
        eligible = [r for r in rows if r["eligibility"] == "eligible"]
        role_groups = defaultdict(list)
        passage_groups = defaultdict(list)
        for row in eligible:
            q = stimuli[row["id"]]
            words = " ".join(q["original"]["window"].values())
            if q["passage_id"] == "t1_1kgs13":
                has_role = any(w in words for w in ("神人", "老先知", "年老的先知"))
            else:
                has_role = q["passage_id"] == "t1_judg17_18" and "利未人" in words
            role_groups["role_label_in_window" if has_role else "other_windows"].append(row)
            passage_groups[q["passage_id"]].append(row)
        rng = Random(2026)
        passages = list(passage_groups.values())
        totals = [(len(group), sum(int(r["blinded_match"])-int(r["original_match"]) for r in group))
                  for group in passages]
        draws = []
        for _ in range(10000):
            draw = rng.choices(totals, k=len(totals))
            draws.append(100*sum(d for _, d in draw)/sum(n for n, _ in draw))
        draws.sort()
        results[model] = {"all": counts(rows), "eligible": counts(eligible),
                          "eligible_delta_pp_95pct_passage_bootstrap": [draws[249], draws[9749]],
                          "eligible_by_role": {k: counts(v) for k,v in role_groups.items()},
                          "eligible_by_passage": {k: counts(v) for k,v in passage_groups.items()},
                          "withheld": counts([r for r in rows if r["eligibility"] != "eligible"]),
                          "by_source_eligible": {s: counts([r for r in eligible if r["source"] == s])
                                                 for s in sorted({r["source"] for r in eligible})},
                          "responses": [{k:r[k] for k in ("id", "eligibility", "correct", "original", "blinded")}
                                        for r in rows],
                          "changed": [r for r in rows if r["original_match"] != r["blinded_match"]]}
    save(REPORT / "results.json", results)


def write_report():
    summarize()
    clean = read(REPORT / "results.json")
    variants = read(REPORT / "variants.json")
    held = []
    lines = ["# Chinese comprehension before and after pseudonymization", "",
             "## Clean passages", "",
             "Each reader answered all 122 Chinese questions against the corresponding unblinded and blinded Sol "
             "verse windows. The primary comparison uses the 119 pilot-eligible questions. The reader saw the "
             "window, question and four choices. Only an exact, single-option match counted as correct.", "",
             "| Local reader | Original | Blinded | Difference (pp) | Lost | Gained |",
             "|---|---:|---:|---:|---:|---:|"]
    for model in MODELS:
        row = clean[model]["eligible"]
        lines.append(f"| {model} | {row['original']}/{row['n']} | {row['blinded']}/{row['n']} "
                     f"| {row['difference_pp']:+.2f} | {row['lost']} | {row['gained']} |")
        held.append(f"{model} scored {clean[model]['withheld']['original']}/3 before and "
                    f"{clean[model]['withheld']['blinded']}/3 after blinding on the withheld items.")
    gemma = clean["gemma3:4b"]["eligible"]
    lines += ["", f"On {gemma['newly_missed_still_including_key']} of Gemma's {gemma['lost']} newly missed items "
              "it still chose the keyed answer along with at least one distractor. "
              f"Counting any selection containing the key gives {gemma['original_key_among_supported']}/119 "
              f"before blinding and {gemma['blinded_key_among_supported']}/119 afterward.",
              "", "One of Qwen's four newly missed items was a letter-selection error. In Acts 23:23–24 the "
              "blinded explanation correctly identifies the two centurions who received the order, but the "
              "returned letter C selects the two hundred infantrymen. D is the centurions. It is counted as "
              "a miss under the same scoring rule as the original.",
              "", " ".join(held), "", "## Reading the pseudonyms", "",
              "In 1 Kings 13:11 the original introduces an old prophet (一个老先知). The blinded text introduces "
              "him as 一个利德. Two verses later he is still called 先知 when he asks for his donkey. A reader "
              "must infer that 利德 and the prophet are the same person.", "",
              "Another question in the same passage changes from 老先知在哪里找到神人？ to 利德在哪里找到尼伦？ "
              "Gemma originally selected only 橡树下 (‘under an oak tree’). After blinding it also selected "
              "通往拉伦的路上 (‘on the road to the pseudonymized place’). Qwen selected only the key both times.", "",
              "In Judges 17:13 有一个利未人作了我的祭司 becomes 有一个韦伦作了我的祭司. A reader can recover "
              "the keyed answer by matching the wording, even though the replacement hides the group identity "
              "that explains why the speaker expects favor.", "",
              "The original 2 Samuel 21:16 uses 伊施比比诺 in the passage and 以施比·比拿 in an answer choice. "
              "Both become 塞达. Here blinding removes a spelling difference the reader had to resolve.", "",
              "There were 22 eligible windows in 1 Kings 13 or Judges 17–18 containing one of the targeted "
              "role descriptions (老先知, 年老的先知, 神人, or 利未人). Eight keyed choices explicitly used one. "
              "This subgroup is descriptive and comes from two passages.", "",
              "| Reader | Role-description windows, original → blinded | Other windows, original → blinded |",
              "|---|---:|---:|"]
    for model in MODELS:
        groups = clean[model]["eligible_by_role"]
        a, b = groups["role_label_in_window"], groups["other_windows"]
        lines.append(f"| {model} | {a['original']}/{a['n']} → {a['blinded']}/{a['n']} "
                     f"| {b['original']}/{b['n']} → {b['blinded']}/{b['n']} |")
    lines += ["", "## Defect variants", "",
              f"Qwen answered one eligible question in each of the 180 passage–defect–dose combinations "
              f"({variants['unique_questions']} distinct questions). Selection rotated through a fixed hashed order "
              "within each passage. Both versions used the same question, option order and delivered verse labels, "
              "including the usual padding for omissions. The scores below measure agreement with the clean key. "
              "A damaged passage can legitimately support a different answer or supply insufficient evidence.", "",
              "| Family | Original | Blinded | Lost | Gained |", "|---|---:|---:|---:|---:|"]
    for family, v in variants["by_family"].items():
        lines.append(f"| {family.title()} | {v['original']}/{v['n']} | {v['blinded']}/{v['n']} "
                     f"| {v['lost']} | {v['gained']} |")
    lines += ["", f"Across all variants the reader matched {variants['original_keys']}/180 original keys "
              f"and {variants['blinded_keys']}/180 blinded keys. It selected the same supported options in "
              f"{variants['same_supported_set']}/180 pairs.", "", "## Method and scope", "",
              "The clean Qwen3 8B comparison uses the archived original responses, verified against the exact "
              "requests, model digest, Ollama version and settings. Both arms used the same four-item batches and "
              "requested an explanation. The runner retries incomplete batches one item at a time. Gemma 3 4B "
              "answered both clean versions afresh, one question per request. The variant check used four-item "
              "batches with different passages. Gemma and the variant check returned option labels only. "
              "Temperature was zero. Answer keys and release labels were omitted from every model request.", "",
              "The two readers give model-based evidence. Human accuracy, reading time and perceived difficulty "
              "were not measured. Questions share passages, and the variant sample repeats some questions. "
              "The item-level outcomes, paired changes and passage-resampled intervals are in results.json. "
              "Variant-level responses and sample IDs are in variants.json.", ""]
    (REPORT / "comparison.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--variants", action="store_true")
    args = parser.parse_args()
    if args.report_only and not (args.model or args.variants):
        write_report()
    elif args.variants and args.model != MODEL:
        parser.error(f"The defect sample uses --model {MODEL}")
    elif args.report_only:
        parser.error("Use --report-only on its own")
    elif args.model:
        run(args.model, args.variants)
    else:
        parser.error("Supply --model or --report-only")
