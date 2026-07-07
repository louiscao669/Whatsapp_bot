#!/usr/bin/env python3
"""Score translated passages with a compact MQM-style LLM judge."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_METHODS = [
    "google_word_by_word",
    "llm_prompt_low",
    "llm_prompt_medium",
    "llm_prompt_high",
    "helsinki",
    "mBART-50",
    "nllb-200-distilled-600M",
    "nllb-200-1.3B",
]
DEFAULT_CHAPTERS = list(range(1, 9))
DEFAULT_MODEL = os.getenv("OPENAI_MQM_MODEL", "gpt-4.1-mini")
# A verse marker is a number at a segment boundary. The negative lookbehind
# excludes word chars, footnote brackets (]), AND a preceding colon so the
# second number of an inserted scripture cross-reference (e.g. "创6:9") is not
# mistaken for a verse marker. The cross-ref text is left in its verse block so
# the MQM judge scores it as an Accuracy/Addition instead of corrupting verse
# alignment.
VERSE_MARKER_PATTERN = re.compile(r"(?<![\w\]:])(\d{1,3})\s+")
SEVERITY_WEIGHTS = {
    "minor": 1,
    "major": 5,
    "critical": 25,
}
MQM_CATEGORIES = {
    "Accuracy/Omission",
    "Accuracy/Mistranslation",
    "Accuracy/Addition",
    "Terminology",
    "Fluency/Grammar",
    "Untranslated/Non-translation",
    "Other",
}


class MQMError(Exception):
    pass


def load_text(path: Path) -> str:
    if not path.exists():
        raise MQMError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    if chunks:
        return "\n".join(chunks)
    raise MQMError("Model response did not include text output.")


def extract_json_object_text(text: str) -> str:
    value = str(text or "").strip()
    start = value.find("{")
    end = value.rfind("}")
    if start != -1 and end != -1 and end > start:
        return value[start : end + 1]
    return value


def get_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise MQMError("Install the openai package to run MQM scoring.") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise MQMError("OPENAI_API_KEY is required for MQM scoring.")
    return OpenAI()


def parse_verse_blocks(text: str) -> list[dict]:
    matches = list(VERSE_MARKER_PATTERN.finditer(text))
    blocks = []
    if not matches:
        return [{"verse": None, "text": text.strip()}] if text.strip() else []

    if matches[0].start() > 0:
        heading = text[: matches[0].start()].strip()
        if heading:
            blocks.append({"verse": None, "text": heading})

    for index, match in enumerate(matches):
        verse = int(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append({"verse": verse, "text": block})
    return blocks


def target_block_index(text: str) -> dict[int, str]:
    index = {}
    for block in parse_verse_blocks(text):
        verse = block.get("verse")
        if isinstance(verse, int):
            index[verse] = str(block.get("text") or "")
    return index


def verse_chunks(source_text: str, target_text: str, max_source_chars: int) -> list[dict]:
    source_blocks = [
        block for block in parse_verse_blocks(source_text)
        if isinstance(block.get("verse"), int)
    ]
    target_by_verse = target_block_index(target_text)
    chunks = []
    current = []
    current_chars = 0
    for block in source_blocks:
        block_text = str(block.get("text") or "")
        if current and current_chars + len(block_text) > max_source_chars:
            chunks.append(build_chunk(current, target_by_verse))
            current = []
            current_chars = 0
        current.append(block)
        current_chars += len(block_text)
    if current:
        chunks.append(build_chunk(current, target_by_verse))
    return chunks


def build_chunk(source_blocks: list[dict], target_by_verse: dict[int, str]) -> dict:
    verses = [int(block["verse"]) for block in source_blocks]
    target_blocks = [
        target_by_verse.get(verse, f"{verse} [MISSING VERSE]")
        for verse in verses
    ]
    verse_range = (
        str(verses[0])
        if verses[0] == verses[-1]
        else f"{verses[0]}-{verses[-1]}"
    )
    return {
        "verse_range": verse_range,
        "verses": verses,
        "source": "\n".join(str(block["text"]) for block in source_blocks),
        "translation": "\n".join(target_blocks),
    }


def source_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", text))


def normalize_category(value: str) -> str:
    raw = str(value or "").strip()
    aliases = {
        "omission": "Accuracy/Omission",
        "accuracy/omission": "Accuracy/Omission",
        "mistranslation": "Accuracy/Mistranslation",
        "accuracy/mistranslation": "Accuracy/Mistranslation",
        "addition": "Accuracy/Addition",
        "accuracy/addition": "Accuracy/Addition",
        "grammar": "Fluency/Grammar",
        "fluency": "Fluency/Grammar",
        "fluency/grammar": "Fluency/Grammar",
        "non-translation": "Untranslated/Non-translation",
        "untranslated": "Untranslated/Non-translation",
        "untranslated/non-translation": "Untranslated/Non-translation",
        "terminology": "Terminology",
        "other": "Other",
    }
    normalized = aliases.get(raw.lower(), raw)
    return normalized if normalized in MQM_CATEGORIES else "Other"


def normalize_severity(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SEVERITY_WEIGHTS else "minor"


def normalize_errors(raw_errors: Any, chapter: int, method: str, verse_range: str) -> list[dict]:
    if not isinstance(raw_errors, list):
        raise MQMError("MQM response field errors must be a list.")
    errors = []
    for index, raw in enumerate(raw_errors, start=1):
        if not isinstance(raw, dict):
            raise MQMError("Every MQM error must be an object.")
        category = normalize_category(raw.get("category"))
        severity = normalize_severity(raw.get("severity"))
        errors.append(
            {
                "chapter": chapter,
                "method": method,
                "chunk_verse_range": verse_range,
                "error_index": index,
                "verse": str(raw.get("verse") or verse_range).strip(),
                "category": category,
                "severity": severity,
                "weight": SEVERITY_WEIGHTS[severity],
                "source_span": str(raw.get("source_span") or "").strip(),
                "translation_span": str(raw.get("translation_span") or "").strip(),
                "explanation": str(raw.get("explanation") or "").strip(),
            }
        )
    return errors


def score_chunk_with_mqm(
    client: Any,
    *,
    model: str,
    chapter: int,
    method: str,
    chunk: dict,
    retries: int,
) -> list[dict]:
    prompt = {
        "task": (
            "Evaluate the Chinese translation against the English source using a compact "
            "MQM framework. Find concrete translation errors only. Do not penalize "
            "acceptable paraphrases. Do not penalize placeholder-style names if they "
            "consistently preserve the source referent. Return valid JSON only."
        ),
        "chapter": f"Luke {chapter}",
        "method": method,
        "verse_range": chunk["verse_range"],
        "categories": sorted(MQM_CATEGORIES),
        "severity_definitions": {
            "minor": "Small local issue; meaning is mostly recoverable.",
            "major": "Meaning is wrong, missing, added, or hard to recover for a content unit.",
            "critical": "Severe error that reverses core meaning, removes answer-critical content, or makes a verse unusable.",
        },
        "source_english": chunk["source"],
        "translation_chinese": chunk["translation"],
        "output_schema": {
            "errors": [
                {
                    "verse": "Luke 1:13",
                    "category": "Accuracy/Omission",
                    "severity": "major",
                    "source_span": "your prayer has been heard",
                    "translation_span": "",
                    "explanation": "The translation omits this source meaning.",
                }
            ]
        },
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a careful MQM translation quality evaluator. "
                            "Return valid JSON only; do not include markdown."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            data = json.loads(extract_json_object_text(extract_response_text(response)))
            return normalize_errors(
                data.get("errors") or [],
                chapter,
                method,
                chunk["verse_range"],
            )
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise MQMError(
        f"MQM scoring failed for Luke {chapter} {method} verses {chunk['verse_range']}: {last_error}"
    ) from last_error


def aggregate_errors(chapter: int, method: str, source_text: str, errors: list[dict]) -> dict:
    category_counts = Counter(error["category"] for error in errors)
    severity_counts = Counter(error["severity"] for error in errors)
    category_penalties = defaultdict(int)
    for error in errors:
        category_penalties[error["category"]] += int(error["weight"])

    weighted_penalty = sum(int(error["weight"]) for error in errors)
    words = source_word_count(source_text)
    penalty_per_1000_words = (weighted_penalty / words * 1000) if words else None
    mqm_quality_0_1 = (
        1 / (1 + penalty_per_1000_words)
        if penalty_per_1000_words is not None
        else None
    )
    return {
        "chapter": chapter,
        "method": method,
        "source_words": words,
        "error_count": len(errors),
        "weighted_penalty": weighted_penalty,
        "penalty_per_1000_words": penalty_per_1000_words,
        "mqm_quality_0_1": mqm_quality_0_1,
        "category_counts": dict(sorted(category_counts.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
        "category_penalties": dict(sorted(category_penalties.items())),
    }


def method_dirs(root: Path, model_dir: str, chapter: int, methods: list[str] | None) -> list[tuple[str, Path]]:
    base = root / f"luke{chapter}" / model_dir
    if methods:
        return [(method, base / method) for method in methods]
    if not base.exists():
        return []
    dirs = [
        path for path in base.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    ]
    return [(path.name, path) for path in sorted(dirs)]


def source_path_for_method(method_dir: Path, fallback_source: Path) -> Path:
    candidate = method_dir / "passage_source_decanonicalized.txt"
    return candidate if candidate.exists() else fallback_source


def score_method(
    client: Any,
    *,
    root: Path,
    model_dir: str,
    chapter: int,
    method: str,
    method_dir: Path,
    source_template: str,
    translation_file: str,
    model: str,
    max_source_chars: int,
    retries: int,
) -> dict:
    fallback_source = Path(source_template.format(chapter=chapter))
    source_path = source_path_for_method(method_dir, fallback_source)
    target_path = method_dir / translation_file
    source_text = load_text(source_path)
    target_text = load_text(target_path)
    chunks = verse_chunks(source_text, target_text, max_source_chars)
    if not chunks:
        raise MQMError(f"No verse chunks found for Luke {chapter} {method}.")

    errors = []
    for chunk in chunks:
        errors.extend(
            score_chunk_with_mqm(
                client,
                model=model,
                chapter=chapter,
                method=method,
                chunk=chunk,
                retries=retries,
            )
        )

    summary = aggregate_errors(chapter, method, source_text, errors)
    return {
        "chapter": chapter,
        "method": method,
        "source_file": str(source_path),
        "translation_file": str(target_path),
        "chunks": [
            {
                "verse_range": chunk["verse_range"],
                "source_chars": len(chunk["source"]),
                "translation_chars": len(chunk["translation"]),
            }
            for chunk in chunks
        ],
        "summary": summary,
        "errors": errors,
    }


def flatten_summary_rows(results: list[dict]) -> list[dict]:
    rows = []
    categories = sorted(MQM_CATEGORIES)
    severities = sorted(SEVERITY_WEIGHTS)
    for result in results:
        summary = result["summary"]
        row = {
            "chapter": summary["chapter"],
            "method": summary["method"],
            "source_words": summary["source_words"],
            "error_count": summary["error_count"],
            "weighted_penalty": summary["weighted_penalty"],
            "penalty_per_1000_words": summary["penalty_per_1000_words"],
            "mqm_quality_0_1": summary["mqm_quality_0_1"],
            "source_file": result["source_file"],
            "translation_file": result["translation_file"],
        }
        for category in categories:
            key = category.lower().replace("/", "_").replace("-", "_").replace(" ", "_")
            row[f"{key}_count"] = summary["category_counts"].get(category, 0)
            row[f"{key}_penalty"] = summary["category_penalties"].get(category, 0)
        for severity in severities:
            row[f"{severity}_count"] = summary["severity_counts"].get(severity, 0)
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use an LLM judge to score translated passages with compact MQM."
    )
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument(
        "--model-dir",
        default="1.7b",
        help="Output subdirectory under each lukeN folder, e.g. 1.7b or nllb_dropout.",
    )
    parser.add_argument("--chapters", type=int, nargs="+", default=DEFAULT_CHAPTERS)
    parser.add_argument(
        "--methods",
        nargs="+",
        default=None,
        help="Methods to score. Default: all method folders in each chapter/model dir.",
    )
    parser.add_argument(
        "--source-template",
        default="evaluation/datasets/test_passage_luke{chapter}.txt",
        help="Fallback source passage path template. {chapter} is replaced.",
    )
    parser.add_argument(
        "--translation-file",
        default="passage_target.txt",
        help="Translated passage filename inside each method folder. Default: passage_target.txt.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-source-chars", type=int, default=2200)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/outputs/mqm_translation_scores.json"),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("evaluation/outputs/mqm_translation_scores.csv"),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue scoring later methods if one method fails.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists() and args.csv.exists() and not args.force:
        print(f"reuse MQM output: {args.output}")
        print(f"reuse MQM csv: {args.csv}")
        return 0
    if args.max_source_chars < 500:
        print("error: --max-source-chars must be at least 500", file=sys.stderr)
        return 1
    if args.retries < 0:
        print("error: --retries must be zero or greater", file=sys.stderr)
        return 1

    try:
        client = get_openai_client()
    except MQMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    results = []
    failures = []
    for chapter in args.chapters:
        for method, method_dir in method_dirs(args.root, args.model_dir, chapter, args.methods):
            try:
                print(f"score MQM: Luke {chapter} {method}")
                results.append(
                    score_method(
                        client,
                        root=args.root,
                        model_dir=args.model_dir,
                        chapter=chapter,
                        method=method,
                        method_dir=method_dir,
                        source_template=args.source_template,
                        translation_file=args.translation_file,
                        model=args.model,
                        max_source_chars=args.max_source_chars,
                        retries=args.retries,
                    )
                )
            except Exception as exc:
                message = f"Luke {chapter} {method}: {exc}"
                failures.append(message)
                if args.continue_on_error:
                    print(f"warning: {message}", file=sys.stderr)
                    continue
                print(f"error: {message}", file=sys.stderr)
                return 1

    output = {
        "schema_version": 1,
        "model": args.model,
        "taxonomy": {
            "categories": sorted(MQM_CATEGORIES),
            "severity_weights": SEVERITY_WEIGHTS,
            "note": (
                "Compact MQM taxonomy intended for QA-answerability analysis. "
                "Penalty is normalized per 1000 English source words."
            ),
        },
        "results": results,
        "failures": failures,
    }
    write_json(args.output, output)
    write_csv(args.csv, flatten_summary_rows(results))
    print(f"wrote MQM output: {args.output}")
    print(f"wrote MQM csv: {args.csv}")
    if failures:
        print("failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
