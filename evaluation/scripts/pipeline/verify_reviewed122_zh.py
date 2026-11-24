"""Blind-check the published Simplified Chinese translations on the local Ollama service."""
import argparse
import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests

ROOT = Path(__file__).resolve().parents[3]
BANK = ROOT / "evaluation/datasets/qa/reviewed122"
MODEL = "qwen3:8b"
PROMPT = """你是独立审题员。每题只根据该题给出的中文经文和题目作答。选择所有经文能支持、且确实回答所问的选项。
若只有一个合理答案就选它；多个答案都合理则全选；若没有证据则返回空数组。不要使用别题或常识补充证据。
每题返回编号 id、选项字母列表 supported 和简短的具体依据 reason。按 id 逐题返回。"""
SCHEMA = {"type":"object", "properties":{"items":{"type":"array","items":{"type":"object",
          "properties":{"id":{"type":"integer"},"supported":{"type":"array","items":{"type":"string","enum":list("ABCD")}},
                        "reason":{"type":"string"}}, "required":["id","supported","reason"]}}},"required":["items"]}


OPTION_DETAIL_RULE = """按题干所问写选项。先用一句短话说清每个选项回答了什么，再决定哪些细节必须保留。
如果问做了什么，选项只写做了什么，保留必要的人物、对象和目的。题干已交代的工具、钱款不必再说。
人物的品行、性格或物品的特点，即使出现在英文选项或经文里，只要删掉仍然完整回答题目，也不影响
与其他选项的区别，就删掉。可以用“人”等普通名词。不要把这类修饰语换成另一个称呼或一串成语。
例如，问“村民做了什么？”，当各项说的是不同的行动，“他们搭救了两个疲惫不堪的旅人”可写成
“他们救了旅人”。若问“旅人当时怎么样？”，疲惫就是答案。若选项区别在于救了谁或救了几人，
就保留能区分对象或数量的词。改写时保留经文所描述的对象和范围。若只说一地物产丰富，
不要自行推断当地人得到了什么或生活怎样。删词后仍须忠实于原意，每项仍有区别，错项仍然是错的。"""

STEM_NAME_RULE = """题干中的人名或族名须能从本题显示的中文经文确定为该事件的人物。若经文只称某人为
官员、亲属或来访者，用经文支持且指代明确的称呼；若用称呼会泄露答案或仍无法确定人物，标出问题。
不要因英文原题或上下文给出了名字就把它补进题干。经文已清楚指认的人名可以保留。
核对题干预设的身份、称谓、关系和动作。如果所给经文从答话开始，未交代对方是谁，可直接问
经文明确的动作和原因。把猜测、计划和已经发生的事区分开来。涉及同一官职或机构时，沿用
这段中文经文的具体称谓，避免换成另一个职级。逐一读题干和各个选项，检查领属关系和句末
的“的”是否成立。问谁做了某事时，直接问动作，用人名或身份回答。若同伴、地点、时间已经足以
指明事件，删去无助于区分人物的亲属链和“自己的”等修饰，采用日常动词。经文只涉及一座殿且
不考查其归属时，可用“圣殿”这样的简称；若要区分地点或身份，则须保留必要的限定。
原题让读者辨认谁，改写后仍要让读者辨认那个人。不要在题干里先说出姓名，再问双方的关系。
若问原因，须能从本段中文判断因果。若只能看出某个事实，保留疑点供审阅。区分请求和实际行动、
人群原来的住处和事件发生的地点。不要为了定位而引用紧挨答案的原句。
如果要辨认动作涉及的人，直接问“谁”或“对谁”，不要把姓名写进题干再问“扮演了什么角色”。
若去掉“发言者认为”等引语仍能问清同一件事，就直接写出有关的动作。若要区分两人的判断，
保留经文能确定的说话人；同时保留“请”“愿”“若”等会影响意思的字眼。"""

DETAIL_REVIEW_PROMPT = STEM_NAME_RULE + "\n" + """你是选择题审题员。逐项做删词检查。先看题干问动作、对象、特征还是别的，
再和其他选项比较。对人物称呼也要试一试：改成普通名词后，能否照样答题和区分各项？
经文中确有某种描述，只能证明它有出处，不能证明选项必须写它。
""" + OPTION_DETAIL_RULE + """
对多余的描述或误删的必要特征，在 issues 里指出选项字母、具体词语和理由，方便改写。
再核对同一字母的英文原选项：动作、人物关系、否定和必要条件也必须一致，不能因缩短而改变选项的意思。
不要评判选项的真假。英文原选项里的错误在中文里保留是正确做法。没有具体需要修改的地方就返回空列表。"""

FIDELITY_PROMPT = """Check the Chinese translation against the English original. Accept a grounded
role in the stem in place of an extra-textual name, or a direct question about the same
action when its speaker or recipient is unavailable, if the requested fact is preserved.
Identify what the original leaves for the reader to supply. Giving the answer in the stem
and asking its role, or asking about a state in place of its cause, changes that target.
Compare stem
with stem and each choice with the same English letter. Use the displayed verses to resolve
participants, offices and the factual setup. Keep ranks and relationships precise.
Each issue must quote English words, quote the corresponding Chinese words, and identify a
material difference such as a changed actor, action, negation, quantity, referent or contrast.
Omitting a description is faithful if the stem does not ask for it and the choices are still
distinct. A deliberately wrong choice must keep its English meaning.

For example, English C 'She gave him a horse' and Chinese C '她给了他一匹马' agree even if
the verse says she gave him bread. For a faithful translation return {"id":1,"issues":[]}.
English C 'She gave him a horse' and Chinese C '他给了她一匹马' reverse who gave the horse.
Only the latter pair warrants an issue. Return one item per ID."""
FIDELITY_SCHEMA = {
    "type": "object", "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "required": ["id", "issues"],
        "properties": {"id": {"type": "integer"}, "issues": {"type": "array", "items": {"type": "string"}}},
    }}},
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    Path(f.name).replace(path)


def load_translations(translations=BANK / "zh.json"):
    source = read(BANK / "english.json")
    translated = read(translations)
    windows = read(BANK / "clean_zh_verses.json")
    if len(source) != 122 or len({r["id"] for r in source}) != 122 or len(translated) != len(source):
        raise ValueError("Expected 122 English and Chinese questions")
    for en, zh in zip(source, translated, strict=True):
        if any(en[k] != zh[k] for k in ("id", "source", "passage_id", "correct", "reference")):
            raise ValueError(f"Source identity or key drift for {en['id']}")
        if (list(en["verses"]) != list(zh["verses"]) or len(zh["choices"]) != 4
                or len(set(zh["choices"])) != 4 or not all([zh["question"], *zh["choices"]])):
            raise ValueError(f"Invalid translated choices or window for {en['id']}")
        if any(windows[en["passage_id"]][label] != verse for label, verse in zh["verses"].items()):
            raise ValueError(f"Chinese passage changed for {en['id']}")
        if not all(re.search(r"[\u3400-\u9fff]", text) for text in [zh["question"], *zh["choices"]]):
            raise ValueError(f"Expected Chinese text in the stem and all four choices for {en['id']}")
    return list(enumerate(translated, 1))


def review_batch(session, run, tasks, recipe):
    digest = sha256(json.dumps([recipe, tasks], ensure_ascii=False).encode()).hexdigest()
    path = run / f"{recipe['check']}_checks" / (digest + ".json")
    if path.exists():
        return read(path)
    response = session.post(
        "http://127.0.0.1:11434/api/chat", allow_redirects=False, timeout=300,
        json={"model": MODEL, "stream": False, "think": False, "format": recipe["schema"],
              "options": recipe["options"],
              "messages": [{"role": "system", "content": recipe["prompt"]},
                           {"role": "user", "content": json.dumps(tasks, ensure_ascii=False)}]},
    )
    response.raise_for_status()
    body = response.json()
    try:
        if not body.get("done") or body.get("done_reason") == "length":
            raise ValueError("Incomplete model response")
        findings = json.loads(body["message"]["content"])["items"]
        if sorted(v["id"] for v in findings) != [task["id"] for task in tasks]:
            raise ValueError("Missing or repeated question in local review")
    except (ValueError, KeyError, TypeError):
        if len(tasks) == 1:
            raise
        findings = [review_batch(session, run, [task], recipe)[0] for task in tasks]
    write(path, findings)
    return findings


def run_check(session, run, rows, recipe, sources):
    check = recipe["check"]
    manifest = run / f"{check}_manifest.json"
    if manifest.exists() and read(manifest) != recipe:
        raise ValueError("Review inputs or settings changed. Choose a fresh --run-dir.")
    write(manifest, recipe)
    results = []
    for start in range(0, len(rows), 4):
        batch = rows[start:start + 4]
        tasks = []
        for n, row in batch:
            chinese = {"question": row["question"], "choices": dict(zip("ABCD", row["choices"], strict=True))}
            if check == "fidelity":
                src = sources[row["id"]]
                english = {"question": src["question"], "choices": dict(zip("ABCD", src["choices"], strict=True))}
                task = {"id": n, "english": english, "chinese": chinese, "verse_for_names": row["verses"]}
            else:
                task = dict(id=n, window=row["verses"], **chinese)
            tasks.append(task)
        verdicts = {v["id"]: v for v in review_batch(session, run, tasks, recipe)}
        for n, row in batch:
            verdict = verdicts[n]
            if check == "blind":
                results.append(dict(id=row["id"], index=n, correct=row["correct"], review=verdict,
                                    matched=verdict["supported"] == [row["correct"]]))
            else:
                results.append(dict(id=row["id"], index=n, issues=verdict["issues"]))
        print(f"{check}: {len(results)}/{len(rows)}", flush=True)
    write(run / f"{check}_audit.json", results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--translations", type=Path, default=BANK / "zh.json",
                        help="Translated bank to check in English source order.")
    parser.add_argument("--check-fidelity", action="store_true",
                        help="Also compare the translated stem and each distractor to its English source.")
    args = parser.parse_args()
    rows = load_translations(args.translations)
    sources = {r["id"]: r for r in read(BANK / "english.json")}
    with requests.Session() as session:
        session.trust_env = False
        version = session.get("http://127.0.0.1:11434/api/version", timeout=10, allow_redirects=False)
        version.raise_for_status()
        models = session.get("http://127.0.0.1:11434/api/tags", timeout=10, allow_redirects=False)
        models.raise_for_status()
        model = next(m for m in models.json()["models"] if m["name"] == MODEL)
        recipe = {
            "ollama_version": version.json()["version"], "model": MODEL, "model_digest": model["digest"],
            "options": {"seed": 2026, "temperature": 0, "num_ctx": 8192, "num_predict": 1150},
            "think": False, "bank_sha256": sha256(args.translations.read_bytes()).hexdigest(),
            "source_sha256": sha256((BANK / "english.json").read_bytes()).hexdigest(),
            "review_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        blind = run_check(session, args.run_dir, rows, dict(recipe, check="blind", prompt=PROMPT, schema=SCHEMA), sources)
        print("Blind key matches:", dict(Counter(r["matched"] for r in blind)))
        if args.check_fidelity:
            fidelity = run_check(session, args.run_dir, rows, dict(recipe, check="fidelity", prompt=FIDELITY_PROMPT,
                                                                   schema=FIDELITY_SCHEMA), sources)
            print("Flagged for translation fidelity:", sum(bool(r["issues"]) for r in fidelity))


if __name__ == "__main__":
    main()
