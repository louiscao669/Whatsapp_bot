"""Score evidence-following when an existing Chinese MCQ distractor becomes the unique key."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import random
from types import SimpleNamespace

import requests

from eten_shared.verse_windows import pad_window_verses
from evaluation.scripts.analysis.current import check_blinding_comprehension as paired
from evaluation.scripts.pipeline.blind_reviewed122 import MAP, Names

REPORT = paired.ROOT / "evaluation/reports/chinese_conflicting_details_2026-11-09"
RUN = paired.ROOT / "evaluation/runs/chinese_conflicting_details_2026-11-09"
LETTERS = "ABCD"
PROMPT = "请阅读给出的中文段落，选出经文最直接支持、且回答了问题的一个选项。如果没有唯一答案，选 ?。只返回选项字母或 ?。"
SCHEMA = {"type":"object","properties":{"answer":{"type":"string","enum":[*LETTERS,"?"]}},"required":["answer"]}
OPTIONS = {"temperature":0,"seed":2026,"num_ctx":4096,"num_predict":40}
ARMS = ("canonical", "pseudonyms")


def delivery_labels(qa, rows, verses):
    wanted = list(qa["verses"])
    if len(wanted) >= 3:
        return wanted
    occupied = {v for other in rows if other["id"] != qa["id"] and other["source"] == qa["source"]
                and other["passage_id"] == qa["passage_id"] for v in other["verses"]}
    available = [SimpleNamespace(verse_number=v) for v in verses]
    return [v.verse_number for v in pad_window_verses(wanted, available, occupied=occupied)]


def prepare():
    read, require = paired.read, paired.require
    statuses = {r["id"]:r["status"] for r in read(paired.BLIND / "qa/pilot_review.json")}
    qa = {r["id"]:r for r in read(paired.DATA / "qa/reviewed122/zh.json")}
    blind = {r["id"]:r for r in read(paired.BLIND / "qa/zh.json")}
    eligible = [r for r in qa.values() if statuses[r["id"]] == "eligible"]
    table = read(MAP)
    cases = []
    for cohort, entries in read(REPORT / "cases.json").items():
        for spec in entries:
            q = qa[spec["id"]]
            b = blind[q["id"]]
            pid = q["passage_id"]
            require(statuses[q["id"]] == "eligible" and q["correct"] == b["correct"] == spec["clean_key"]
                    and spec["foil"] in LETTERS and spec["foil"] != q["correct"], "Invalid keys or eligibility")
            require(q["choices"][LETTERS.index(spec["foil"])] == spec["verified_foil_choice"],
                    f"Foil letter differs from reviewed choice text for {q['id']}")
            pack = read(paired.SOURCE / f"{pid}.json")["conditions"]
            blinded = read(paired.BLIND / "passages" / f"{pid}.json")["conditions"]
            labels = delivery_labels(q, eligible, pack["clean"]["verses"])
            clean = {v:pack["clean"]["verses"][v] for v in labels}
            clean_b = {v:blinded["clean"]["verses"][v] for v in labels}
            names = Names(table, "zh", pid)
            require([names.apply(c) for c in q["choices"]] == b["choices"]
                    and names.apply(q["question"]) == b["question"], "Blinding changed the choices or stem")
            if cohort == "released":
                key = "mistranslation" + str(spec["dose"])
                edited = {v:pack[key]["verses"][v] for v in labels}
                edited_b = {v:blinded[key]["verses"][v] for v in labels}
                v, before, after = spec["anchor"]
                require(before in clean[v] and after in edited[v] and before not in edited[v], "Invalid evidence anchor")
            else:
                edited = clean.copy()
                for v, before, after in spec["edits"]:
                    require(edited[v].count(before) == 1, f"Missing or ambiguous edit in {q['id']}")
                    edited[v] = edited[v].replace(before, after)
                edited_b = {v:names.apply(text) for v,text in edited.items()}
            windows = {"canonical":{"clean":clean,"conflict":edited},
                       "pseudonyms":{"clean":clean_b,"conflict":edited_b}}
            for v in labels:
                require(names.apply(clean[v]) == clean_b[v] and names.apply(edited[v]) == edited_b[v],
                        "Edited and original arms are not the same facts")
                names.check(edited_b[v], f"{q['id']}/{v}")
            for arm in ARMS:
                require(windows[arm]["clean"] != windows[arm]["conflict"], "Unchanged window")
            cases.append({"cohort":cohort, "id":q["id"], "passage_id":pid, "clean_key":q["correct"],
                          "foil":spec["foil"], "windows":windows, "fact":spec["fact"],
                          "questions":{"canonical":q["question"],"pseudonyms":b["question"]},
                          "choices":{"canonical":q["choices"],"pseudonyms":b["choices"]}})
    require(len(cases) == len({c["id"] for c in cases}), "Repeated question")
    return cases


def tasks_for(cases):
    trials = []
    for q in cases:
        # Swapping only the two competing positions balances each factual answer over the same two letters.
        swapped = list(LETTERS)
        i, j = (LETTERS.index(q[k]) for k in ("clean_key","foil"))
        swapped[i], swapped[j] = swapped[j], swapped[i]
        for order, order_map in (("published", LETTERS), ("swapped", "".join(swapped))):
            for arm in ARMS:
                for condition, window in q["windows"][arm].items():
                    choices = {letter:q["choices"][arm][LETTERS.index(source)]
                               for letter,source in zip(LETTERS, order_map, strict=True)}
                    payload = {"经文":window, "问题":q["questions"][arm], "选项":choices}
                    trials.append({"id":q["id"], "cohort":q["cohort"], "order":order,"order_map":order_map,
                                   "arm":arm,"condition":condition,"payload":payload})
    random.Random(20261109).shuffle(trials)
    return trials


def run(model, offline):
    cases = prepare()
    paired.freeze(REPORT / "verified_windows.json", cases)
    folder = RUN / model.replace(":", "_")
    baseline_identity = paired.read(paired.RUN / model.replace(":","_") / "manifest.json")
    spec = {"model":model, "digest":baseline_identity["digest"], "ollama":baseline_identity["ollama"],
            "options":OPTIONS, "schema":SCHEMA, "prompt":PROMPT, "cases_sha256":paired.checksum(REPORT / "cases.json"),
            "windows_sha256":paired.checksum(REPORT / "verified_windows.json")}
    paired.freeze(folder / "manifest.json", spec)
    trials = tasks_for(cases)
    answers = []
    with requests.Session() as session:
        session.trust_env = False
        if not offline:
            version = session.get(paired.LOCAL + "/api/version", timeout=10, allow_redirects=False)
            version.raise_for_status()
            tags = session.get(paired.LOCAL + "/api/tags", timeout=10, allow_redirects=False)
            tags.raise_for_status()
            paired.require(version.json()["version"] == spec["ollama"] and
                           any(m["name"] == model and m["digest"] == spec["digest"] for m in tags.json()["models"]),
                           "Local model or server version differs from prior experiment")
        for i, trial in enumerate(trials,1):
            task = json.dumps(trial["payload"], ensure_ascii=False)
            body = {"model":model, "options":OPTIONS, "think":False, "stream":False, "format":SCHEMA,
                    "messages":[{"role":"system","content":PROMPT},{"role":"user","content":task}]}
            rid = sha256(json.dumps(body,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            receipt = folder / "cache" / (rid+".json")
            if receipt.is_file():
                reply = paired.read(receipt)
            else:
                paired.require(not offline, f"Missing receipt: {rid}")
                resp = session.post(paired.LOCAL+"/api/chat",json=body,timeout=240,allow_redirects=False)
                resp.raise_for_status()
                raw = resp.json()
                paired.require(raw.get("done") and raw.get("done_reason") != "length", "Incomplete reply")
                reply = json.loads(raw["message"]["content"])
                paired.freeze(receipt, reply)
            letter = reply["answer"]
            paired.require(letter in [*LETTERS,"?"], "Unexpected response")
            semantic = trial["order_map"][LETTERS.index(letter)] if letter != "?" else "?"
            answers.append({**{k:v for k,v in trial.items() if k!="payload"}, "receipt":rid, "letter":letter,
                            "semantic_answer":semantic})
            if i%16==0 or i==len(trials):
                print(model, i, "/", len(trials),flush=True)
    paired.save(REPORT / (model.replace(":","_")+".json"),{"experiment":spec,"answers":answers})


def summary():
    cases = {c["id"]:c for c in prepare()}
    stats = {}
    item_rows = []
    for model in paired.MODELS:
        results = paired.read(REPORT / (model.replace(":","_")+".json"))["answers"]
        by_trial = {(r["id"],r["arm"],r["condition"],r["order"]):r["semantic_answer"] for r in results}
        paired.require(len(by_trial)==len(results)==8*len(cases),"Incomplete factorial design")
        stats[model] = {}
        for cohort in ("released","constructed"):
            scores = {}
            for arm in ARMS:
                s=Counter()
                for q in cases.values():
                    if q["cohort"]!=cohort:
                        continue
                    s["questions"]+=1
                    answers=[]
                    for order in ("published","swapped"):
                        clean=by_trial[q["id"],arm,"clean",order]
                        answer=by_trial[q["id"],arm,"conflict",order]
                        answers.append(answer)
                        s["presentations"]+=1
                        s["clean_correct"]+=clean==q["clean_key"]
                        s["follows_edit"]+=answer==q["foil"]
                        s["retains_original"]+=answer==q["clean_key"]
                        s["abstains"]+=answer=="?"
                        s["other_distractor"]+=answer not in (q["clean_key"],q["foil"],"?")
                        s["clean_correct_and_switches"]+=clean==q["clean_key"] and answer==q["foil"]
                    s["follows_both_orders"]+=answers==[q["foil"]]*2
                scores[arm]=dict(s)
            stats[model][cohort]=scores
        for q in cases.values():
            item = {"model":model, "id":q["id"], "cohort":q["cohort"], "fact":q["fact"]}
            for arm in ARMS:
                item[arm] = []
                for order in ("published","swapped"):
                    conflict = by_trial[q["id"],arm,"conflict",order]
                    item[arm].append({"order":order, "clean_answer":by_trial[q["id"],arm,"clean",order],
                                      "conflict_answer":conflict, "follows_edit":conflict == q["foil"],
                                      "retains_original":conflict == q["clean_key"]})
            item_rows.append(item)
    paired.save(REPORT/"summary.json",stats)
    paired.save(REPORT/"item_results.json",item_rows)
    return stats


def write_report(stats):
    lines = ["# Following a conflicting detail in Chinese MCQs", "",
             "The test compares the released Chinese Sol passages with the v1 pseudonyms. Each case keeps the "
             "question and four choices fixed while the altered passage makes a different existing choice correct. "
             "The clean control uses the same verse labels, including any delivery padding.", ""]
    for title, cohort in (("Published mistranslations", "released"), ("Additional single-fact tests", "constructed")):
        lines += [f"## {title}", "",
                  "| Model | Naming | Clean key on clean passage | Edited key on altered passage | Original key retained | Other / insufficient | Followed in both orders |",
                  "|---|---|---:|---:|---:|---:|---:|"]
        for model in paired.MODELS:
            for arm in ARMS:
                s = stats[model][cohort][arm]
                n = s["presentations"]
                lines.append(f"| {model} | {arm} | {s['clean_correct']}/{n} | {s['follows_edit']}/{n} "
                             f"| {s['retains_original']}/{n} | {s['other_distractor']} / {s['abstains']} "
                             f"| {s['follows_both_orders']}/{s['questions']} |")
        lines += ["", "Among presentations where the model first demonstrated the original fact on the clean "
                  "control, the counts that also switched to the new key on the altered passage were as follows.", ""]
        for model in paired.MODELS:
            group = stats[model][cohort]
            lines.append(f"- {model} with original names {group['canonical']['clean_correct_and_switches']}/"
                         f"{group['canonical']['clean_correct']} and with pseudonyms "
                         f"{group['pseudonyms']['clean_correct_and_switches']}/{group['pseudonyms']['clean_correct']}.")
        lines.append("")
    lines += ["## What the misses looked like", "",
              "All misses on the seven released conflicts came from Acts 20:7. The original says the first "
              "day of the week. The variant says the last day, making the seventh-day choice correct. With "
              "either set of names, Qwen chose the seventh day in the published order and the first day when "
              "the two options traded places. Gemma chose the sixth day in both orders and naming conditions. "
              "On every other published conflict both readers followed the edit in both orders.", "",
              "In the supplemental cases, Gemma's two additional misses with biblical names were the two "
              "orders of one 2 Samuel 21 question. It chose Shimei's descendants, while the edited text says "
              "David's and the original says Rapha's. That difference gives little evidence for recall of the original answer.",
              "", "## Selection and interpretation", "",
              "I screened the 122 original Chinese MCQs against the edits in their assigned verse windows. "
              "The primary set uses pilot-eligible questions with one directly supported alternate option in both "
              "naming conditions. Each question enters once, at the lowest published dose at which its switch is clear. "
              "The seven questions span four passages. Five are from Judges. No reader's predictions were used to choose or label them.", "",
              "Changes that merely removed evidence, broke the premise of the question, or made a distractor only "
              "approximately right were excluded. For example, the high-dose Acts 19 version changes both burning to "
              "selling and practitioners of magic to practitioners of medicine. The original stem still asks about "
              "practitioners of magic. The published 2 Kings 11 change says the people were devastated, while the "
              "existing choice specifically says they wept.", "",
              "The separate supplemental set uses ten other eligible questions, one per passage, with a deliberate "
              "change to one fact. Repeated mentions of that fact were updated together. These passages exist only "
              "as diagnostic stimuli. The four choices were already in the bank. Each case was labeled before scoring. "
              "An independent choice-text readback corrected the tower-door foil letter before scoring.", "",
              "Each local model had 136 independent requests. Each of the 17 questions appeared with both name sets, "
              "both clean and conflicting evidence, and two option orders. The second order exchanges the original "
              "and edited keys. Tables count semantic choices after reversing that permutation. "
              "Both models received the same Chinese passage-only prompt, without the keys or condition labels, "
              "at temperature zero with thinking disabled. A single option or an explicit insufficient-evidence "
              "response was allowed. Distinct option orders are repeated measures on the same questions.", "",
              "Selecting the original key despite contrary evidence is compatible with prior knowledge, a reading "
              "mistake, or a guessing preference. These responses alone cannot distinguish them. The study "
              "materials and eligibility decisions were not modified.", "",
              "cases.json records the reviewed alternate option, evidence, published dose or isolated edit. "
              "verified_windows.json contains the exact Chinese stimuli. item_results.json gives the clean and "
              "altered response for every question, naming condition and order.", ""]
    (REPORT / "comparison.md").write_text("\n".join(lines),encoding="utf-8")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=paired.MODELS)
    parser.add_argument("--offline", action="store_true")
    args=parser.parse_args()
    if args.model:
        run(args.model,args.offline)
    else:
        stats = summary()
        write_report(stats)
        print(json.dumps(stats,indent=2))
