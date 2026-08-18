#!/usr/bin/env python3
"""Run a 10-item BSB MCQ smoke test without regenerating or translating QA.

The fixed panel contains the four BSB-reworded questions plus one unchanged
question from each remaining Tier-1 passage. It reads the already-translated
Chinese QA and clean Chinese passages from ``evaluation/outputs/tier1_bsb``.

Examples (from the repository root):

    python evaluation/scripts/campaigns/smoke_test_bsb_mcqs.py --dry-run
    python evaluation/scripts/campaigns/smoke_test_bsb_mcqs.py
    python evaluation/scripts/campaigns/smoke_test_bsb_mcqs.py \
      --models llama3.2:1b qwen2.5:1.5b
    python evaluation/scripts/campaigns/smoke_test_bsb_mcqs.py --force \
      --mcq-choice-mapper openai --mcq-choice-model gpt-4.1-mini
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ANSWER_SCRIPT = REPO_ROOT / "evaluation/agents/generate_chinese_answers.py"

# Four rewritten items, then one unchanged item from every other passage.
PANEL = {
    "t1_judg9": "t1_judg9:w5fv",
    "t1_judg17_18": "t1_judg17_18:e4u2",
    "t1_acts19": "t1_acts19:b1be",
    "t1_acts23": "t1_acts23:exnu",
    "t1_2chr26": "t1_2chr26:zu38",
    "t1_2kgs6_7": "t1_2kgs6_7:dbzo",
    "t1_acts20": "t1_acts20:kqua",
    "t1_2kgs11": "t1_2kgs11:fn7d",
    "t1_2sam21": "t1_2sam21:kjsg",
    "t1_1kgs13": "t1_1kgs13:mjwk",
}


def model_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", model)


def load_mcq(path: Path, content_id: str) -> dict:
    records = json.loads(path.read_text(encoding="utf-8"))
    wanted = f"uw-{content_id}-mcq"
    matches = [row for row in records if row.get("passage_id") == wanted]
    if len(matches) != 1:
        raise RuntimeError(f"{path}: expected one {wanted}, found {len(matches)}")
    row = matches[0]
    choices = row.get("A")
    correct = row.get("correct")
    if not isinstance(choices, dict) or set(choices) != set("ABCD"):
        raise RuntimeError(f"{wanted}: choices are not exactly A-D")
    if correct not in choices:
        raise RuntimeError(f"{wanted}: invalid correct choice {correct!r}")
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("evaluation/outputs/tier1_bsb"),
        help="Root containing the existing BSB _base artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/outputs/tier1_bsb_smoke"),
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["llama3.2:1b", "qwen2.5:1.5b"],
    )
    parser.add_argument(
        "--mcq-choice-mapper",
        choices=("rules", "openai"),
        default="rules",
        help="Map raw model responses to A-D with rules or an OpenAI fallback.",
    )
    parser.add_argument(
        "--mcq-choice-model",
        default="gpt-4.1-mini",
        help="OpenAI model used when --mcq-choice-mapper=openai.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root if args.root.is_absolute() else REPO_ROOT / args.root
    output_dir = (
        args.output_dir
        if args.output_dir.is_absolute()
        else REPO_ROOT / args.output_dir
    )

    inputs = {}
    for passage_id, content_id in PANEL.items():
        base = root / passage_id / "_base/llm_prompt_high"
        passage = base / "passage_target_decanonicalized.txt"
        qa = base / "qa_target_decanonicalized.json"
        if not passage.is_file() or not qa.is_file():
            raise RuntimeError(f"missing BSB base artifacts for {passage_id}: {base}")
        inputs[passage_id] = (passage, load_mcq(qa, content_id))

    print(f"validated smoke panel: {len(inputs)} MCQs across {len(PANEL)} passages")
    if args.dry_run:
        for model in args.models:
            for passage_id, (passage, row) in inputs.items():
                print(
                    f"would run {model}: {row['passage_id']} using "
                    f"{passage.relative_to(REPO_ROOT)}"
                )
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    with tempfile.TemporaryDirectory(prefix="eten-bsb-smoke-") as temp_name:
        temp_dir = Path(temp_name)
        for passage_id, (passage, row) in inputs.items():
            subset = temp_dir / f"{passage_id}_qa.json"
            subset.write_text(
                json.dumps([row], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            for model in args.models:
                slug = model_slug(model)
                result_path = output_dir / slug / f"{passage_id}.json"
                result_path.parent.mkdir(parents=True, exist_ok=True)
                if args.force or not result_path.exists():
                    command = [
                        sys.executable,
                        str(ANSWER_SCRIPT),
                        str(passage),
                        str(subset),
                        str(result_path),
                        "--provider",
                        "ollama",
                        "--model",
                        model,
                        "--verse-window",
                        "2",
                        "--mcq-choice-mapper",
                        args.mcq_choice_mapper,
                        "--allow-partial-answers",
                    ]
                    if args.mcq_choice_mapper == "openai":
                        command.extend(["--mcq-choice-model", args.mcq_choice_model])
                    if model.lower().startswith("qwen3"):
                        command.append("--ollama-no-think")
                    print(f"=== {passage_id} / {model}")
                    subprocess.run(command, cwd=REPO_ROOT, check=True)
                else:
                    print(f"reuse {result_path.relative_to(REPO_ROOT)}")

                generated = json.loads(result_path.read_text(encoding="utf-8"))
                if len(generated) != 1:
                    raise RuntimeError(f"{result_path}: expected one answer")
                answer = generated[0]
                selected = answer.get("selected_choice")
                correct = row["correct"]
                summary.append(
                    {
                        "passage_id": passage_id,
                        "content_id": PANEL[passage_id],
                        "model": model,
                        "question_zh": row["Q"],
                        "correct_choice": correct,
                        "correct_text_zh": row["A"][correct],
                        "selected_choice": selected,
                        "selected_text_zh": answer.get("selected_choice_text"),
                        "passed": selected == correct,
                    }
                )

    report_json = output_dir / "comparison.json"
    report_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    passed = sum(row["passed"] for row in summary)
    print(f"\n{passed}/{len(summary)} model-item checks passed")
    for row in summary:
        mark = "PASS" if row["passed"] else "FAIL"
        print(
            f"  {mark} {row['content_id']} / {row['model']}: "
            f"selected={row['selected_choice']} correct={row['correct_choice']}"
        )
    print(f"report: {report_json.relative_to(REPO_ROOT)}")
    return 0 if passed == len(summary) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
