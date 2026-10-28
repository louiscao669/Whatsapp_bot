"""Capture fresh diagnostic responses; never write to the study run."""
from pathlib import Path
import io
import json
import os
import sys
import time
import urllib.request

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
os.environ.update(QA_FORMATS="open,mcq", MCQ_CHOICE_LABELS="ABCDE", MCQ_ABSTAIN_LABEL="E")
from evaluation.agents import generate_chinese_answers as answers

OUT = Path(__file__).resolve().parent
audit = json.loads((OUT / "audit.json").read_text())
failure_records = list(audit["failures"])
mcq_inventory = OUT / "mcq_failures.json"
if mcq_inventory.exists():
    for entry in json.loads(mcq_inventory.read_text()):
        if any(f["answers_file"] == entry["file"] and f["row"]["id"] == entry["row"]["id"]
               for f in failure_records):
            continue
        stage = "wbw" if entry["condition"] == "google_word_by_word" else entry["condition"].split("/")[0]
        failure_records.append({**entry, "answers_file": entry["file"],
                                "cell": f"{stage}/qwen3:1.7b/{entry['passage']}/{entry['condition']}"})
root = Path(audit["run_root"])
windows = answers.load_verse_windows(root / "_inputs/windows.json")
os.environ.update(OLLAMA_NUM_PREDICT="2500", OLLAMA_TIMEOUT="150", MCQ_KEEP_THINKING="1")
selected = [
    ("t1_judg17_18", "omission/5%", "uw-t1_judg17_18:616b-open"),
    ("t1_acts20", "mistranslation/30%", None),
    ("t1_acts23", "mistranslation/10%", "uw-t1_acts23:2b9c-mcq"),
    ("t1_2chr26", "google_word_by_word", "uw-t1_2chr26:9860-mcq"),
    ("t1_judg9", "omission/25%", "uw-t1_judg9:a602-mcq"),
]
real_urlopen = urllib.request.urlopen
summaries = []
for number, (pid, condition, identifier) in enumerate(selected, 1):
    match = [f for f in failure_records if f["passage"] == pid
             and f["condition"] == condition
             and (identifier is None or f["row"]["id"] == identifier)]
    assert len(match) == 1
    failure = match[0]
    identifier = failure["row"]["id"]
    path = OUT / f"replay_{number}.json"
    folder = Path(failure["answers_file"]).parent
    qa = answers.public_questions(answers.load_qa_items(
        root / pid / "_base/_shared" / f"{pid}_base_qa_zh_decanonicalized.json"))
    question = next(q for q in qa if q["id"] == identifier)
    passage = (folder / "passage_target_decanonicalized.txt").read_text()
    index, order = answers.index_passage_verses(
        passage, answers.chapters_from_reference(question["passage_reference"]))
    local = answers.local_passage_for_question(passage, index, question, 2, order, windows)
    expected_prompt = answers.build_raw_answer_prompt(local, question, expanded_answer_format=False)
    if path.exists():
        previous = json.loads(path.read_text())
        if ("response" in previous
                and previous["request"]["messages"][1]["content"] == expected_prompt):
            print(f"REUSE {path.name}", flush=True)
            summaries.append(previous)
            continue
        previous["excluded_from_replay_findings"] = "No response, or prompt differed from the five-option study protocol."
        path.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
        path.rename(path.with_stem(f"{path.stem}_excluded_{time.time_ns()}"))
    record = {"kind": "fresh_diagnostic_replay_not_original_trace", "original_cell": failure["cell"],
              "id": identifier, "question": question["question"], "local_passage": local,
              "started_at": time.time(), "attempts": 1}

    def save():
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")

    def capture(request, timeout):
        record["request"] = json.loads(request.data)
        record["timeout_seconds"] = timeout
        save()
        with real_urlopen(request, timeout=timeout) as response:
            data = response.read()
        record["response"] = json.loads(data)
        record["response_saved_at"] = time.time()
        save()  # Save thinking and termination details before answer parsing.
        return io.BytesIO(data)

    urllib.request.urlopen = capture
    print(f"REPLAY {number}/{len(selected)}: {pid} {condition} {identifier}", flush=True)
    try:
        record["parsed_answer"] = answers.generate_ollama_single_raw(
            base_url="http://localhost:11434", model="qwen3:1.7b", passage=local,
            question=question, no_think=False, expanded_answer_format=False, retries=0)
    except Exception as exc:
        record["error_type"] = type(exc).__name__
        record["error"] = str(exc)
    finally:
        urllib.request.urlopen = real_urlopen
        record["finished_at"] = time.time()
        save()
    response = record.get("response", {})
    message = response.get("message", {})
    print(json.dumps({"file": path.name, "tokens": response.get("eval_count"),
                      "done_reason": response.get("done_reason"),
                      "thinking_chars": len(message.get("thinking", "")),
                      "answer_chars": len(message.get("content", "")),
                      "error": record.get("error")}), flush=True)
    summaries.append(record)

assert len(summaries) == len(selected)
