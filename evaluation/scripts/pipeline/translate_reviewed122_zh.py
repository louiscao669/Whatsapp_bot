"""Generate a Simplified Chinese MCQ bank from the frozen English bank and Chinese verses."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

import requests

from evaluation.scripts.pipeline.verify_reviewed122_zh import (
    BANK, ROOT, DETAIL_REVIEW_PROMPT, FIDELITY_SCHEMA, OPTION_DETAIL_RULE, STEM_NAME_RULE, read, review_batch, write,
)

URL = "http://127.0.0.1:11434"
MODEL = "qwen3:8b"
MODEL_DIGEST = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"
OPTIONS = {"temperature": 0, "seed": 2026, "top_k": 1, "num_ctx": 8192, "num_predict": 768}
LETTERS = "ABCD"
FACTS_PROMPT = """You edit the four English options of a reading-comprehension question before
translation. Read the question and compare all four choices. Return the shortest plain English
answer to the question that each choice asserts. Start with the action or fact that answers the
question. Preserve the parties, object, purpose, polarity, time and quantity wherever they are
part of that answer or necessary to keep the choices distinct. Strip incidental participant
traits, even if true of those people. If given 'They rescued exhausted travelers', write 'They
rescued travelers' for a question about what they did. Keep 'exhausted' for a question about
the travelers' condition, or if another choice is rescuing well-rested travelers. Keep the same
four claims at their original letters, including any false claim. Leave an already focused
option alone. Do not answer the quiz."""
PROMPT = """你为阅读理解实验编写简体中文选择题。准确翻译英文题干，按下列规则把每个英文选项
改写成自然、简明的中文。\n""" + STEM_NAME_RULE + "\n" + OPTION_DETAIL_RULE + """
四个选项保留原来的字母位置和各自回答的事实。保留答题所需的动作关系、因果、时间、否定、数量
和不确定性。用中文经文核对人名和地名，不从经文补回英文选项没有的人物描述。必要时参照英文经文消除指代歧义。选项中经文未提及的人用
通行的简体中文圣经译名。各项句式平行，保持错误选项原有的错误，不提示答案，不为弥补两种
经文的差异补写事实。只返回中文题干和四个选项，不带字母前缀或说明。"""
SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "choices": {
            "type": "object",
            "properties": {letter: {"type": "string"} for letter in LETTERS},
            "required": list(LETTERS),
            "additionalProperties": False,
        },
    },
    "required": ["question", "choices"],
    "additionalProperties": False,
}
DEFAULT_RUN = ROOT / "evaluation/runs/reviewed122_zh_focused_choices"
FACTS_SCHEMA = {
    "type": "object", "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "required": ["id", "choices"],
        "properties": {"id": {"type": "integer"}, "choices": SCHEMA["properties"]["choices"]},
    }}},
}


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def runtime(session):
    version = session.get(f"{URL}/api/version", timeout=10, allow_redirects=False)
    version.raise_for_status()
    response = session.get(f"{URL}/api/tags", timeout=10, allow_redirects=False)
    response.raise_for_status()
    model = next((m for m in response.json()["models"] if m["name"] == MODEL), None)
    if model is None or model["digest"].removeprefix("sha256:") != MODEL_DIGEST:
        raise ValueError(f"This recipe requires {MODEL} with digest {MODEL_DIGEST}")
    return {"ollama_version": version.json()["version"], "model": MODEL, "model_digest": MODEL_DIGEST}


def validate_candidate(candidate, row):
    if not isinstance(candidate, dict) or set(candidate) != {"question", "choices"}:
        raise ValueError("Return one question and a choices object.")
    options = candidate["choices"]
    if not isinstance(options, dict) or set(options) != set(LETTERS):
        raise ValueError("Include exactly the four choice labels A, B, C, D.")
    values = [candidate["question"], *(options[letter] for letter in LETTERS)]
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError("Every requested field must contain text.")
    stem, *choices = [value.strip() for value in values]
    if not re.search(r"[\u3400-\u9fff]", stem) or len(set(choices)) != 4:
        raise ValueError("Use a Chinese stem and keep the four distinct source choices distinct.")
    for en, zh in zip(row["choices"], choices, strict=True):
        if re.search(r"[A-Za-z]", en) and not re.search(r"[\u3400-\u9fff]", zh):
            raise ValueError(f"Translate the full choice into Chinese: {zh!r}")
    return stem, choices


def translate_item(session, row, window, manifest_hash, run):
    task = {
        "english_verses": row["verses"],
        "chinese_verses": window,
        "question": row["question"],
        "choices": dict(zip(LETTERS, row["choices"], strict=True)),
    }
    facts_recipe = {"check": "option_facts", "model": MODEL, "options": OPTIONS,
                    "prompt": FACTS_PROMPT, "schema": FACTS_SCHEMA, "translation_recipe": manifest_hash}
    review_recipe = {"check": "option_detail", "model": MODEL, "options": OPTIONS,
                     "prompt": DETAIL_REVIEW_PROMPT, "schema": FIDELITY_SCHEMA,
                     "translation_recipe": manifest_hash}
    key = digest([facts_recipe, PROMPT, review_recipe, row["id"], task])
    path = run / "translations" / f"{key}.json"
    if path.exists():
        checkpoint = read(path)
        if (checkpoint["key"] != key or checkpoint["id"] != row["id"]
                or digest(checkpoint["completion"]) != checkpoint["completion_digest"]):
            raise ValueError(f"Invalid translation checkpoint for {row['id']}")
        stem, choices = validate_candidate(checkpoint["completion"], row)
    else:
        source_options = task["choices"]
        source_input = {"id": 1, "question": row["question"], "choices": source_options}
        facts, = review_batch(session, run, [source_input], facts_recipe)
        focused = facts.get("choices")
        if (not isinstance(focused, dict) or set(focused) != set(LETTERS)
                or not all(isinstance(v, str) and v.strip() for v in focused.values())
                or len({v.strip().casefold() for v in focused.values()}) != 4):
            # A choice contrast was lost. Translate from the original and check all four together.
            focused = source_options
        user_text = json.dumps(dict(task, choices=focused), ensure_ascii=False)
        messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": user_text}]
        attempts = []
        for attempt in range(3):
            payload = {"model": MODEL, "options": OPTIONS, "format": SCHEMA, "stream": False,
                       "think": False, "messages": messages}
            response = session.post(f"{URL}/api/chat", json=payload, timeout=240, allow_redirects=False)
            response.raise_for_status()
            body = response.json()
            raw = body["message"]["content"]
            attempts.append(raw)
            try:
                if not body.get("done") or body.get("done_reason") == "length":
                    raise ValueError("The output was incomplete. Translate concisely.")
                candidate = json.loads(raw)
                stem, choices = validate_candidate(candidate, row)
                review_input = {"id": 1, "question": stem, "choices": dict(zip(LETTERS, choices)),
                                "verses": window, "english_question": row["question"],
                                "english_choices": task["choices"]}
                finding, = review_batch(session, run, [review_input], review_recipe)
                issues = finding.get("issues")
                if not isinstance(issues, list) or not all(isinstance(i, str) and i.strip() for i in issues):
                    raise ValueError("The option detail review returned invalid findings.")
                if issues:
                    raise ValueError("Revise the cited stem or choices. " + " ".join(issues)
                                     + "\nOriginal English choices: " + json.dumps(source_options, ensure_ascii=False))
                break
            except ValueError as exc:
                if attempt == 2:
                    raise ValueError(f"Translation failed for {row['id']}: {exc}") from exc
                messages.extend([{"role": "assistant", "content": raw},
                                 {"role": "user", "content": f"Correct this output problem: {exc}"}])
        write(path, {"key": key, "id": row["id"], "source_facts": focused, "attempts": attempts,
                     "completion": candidate, "completion_digest": digest(candidate)})
    return {**row, "verses": window, "question": stem, "choices": choices}


def run_translation(run, only_id=None):
    run = run.resolve()
    if run == BANK.resolve():
        raise ValueError("Choose a separate run directory to protect the published pilot bank.")
    rows = read(BANK / "english.json")
    windows = read(BANK / "clean_zh_verses.json")
    if len(rows) != len({row["id"] for row in rows}) or len(rows) != 122:
        raise ValueError("Expected 122 unique English source IDs")
    if only_id is not None:
        rows = [row for row in rows if row["id"] == only_id]
        if not rows:
            raise ValueError(f"Unknown source ID {only_id!r}")
    with requests.Session() as session:
        session.trust_env = False
        manifest = {
            **runtime(session), "options": OPTIONS, "think": False, "system_prompt": PROMPT,
            "output_schema": SCHEMA, "detail_review_prompt": DETAIL_REVIEW_PROMPT,
            "source_facts_prompt": FACTS_PROMPT, "source_facts_schema": FACTS_SCHEMA,
            "detail_review_schema": FIDELITY_SCHEMA, "item_ids": [r["id"] for r in rows],
            "source_sha256": sha256((BANK / "english.json").read_bytes()).hexdigest(),
            "chinese_verses_sha256": sha256((BANK / "clean_zh_verses.json").read_bytes()).hexdigest(),
            "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        manifest_path = run / "manifest.json"
        if manifest_path.exists() and read(manifest_path) != manifest:
            raise ValueError("Different inputs, model, code, or runtime; choose a fresh --run-dir.")
        if not manifest_path.exists():
            if run.exists() and any(run.iterdir()):
                raise ValueError("Choose an empty run directory for the new recipe.")
            write(manifest_path, manifest)
        key = digest(manifest)
        translated = []
        for index, row in enumerate(rows, 1):
            window = {label: windows[row["passage_id"]][label] for label in row["verses"]}
            translated.append(translate_item(session, row, window, key, run))
            if index % 10 == 0 or index == len(rows):
                print(f"{index}/{len(rows)} translated", flush=True)
    write(run / "zh.json", translated)
    output_hash = sha256((run / "zh.json").read_bytes()).hexdigest()
    write(run / "result.json", {"count": len(rows), "manifest_digest": key, "bank_sha256": output_hash})
    print(f"Wrote {run / 'zh.json'} (sha256 {output_hash})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--item", help="Generate one source ID in a separate run directory.")
    args = parser.parse_args()
    run_translation(args.run_dir, args.item)


if __name__ == "__main__":
    main()
