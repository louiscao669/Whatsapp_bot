#!/usr/bin/env python3
r"""Score Gold-72 QAs on four rubric dimensions and relate them to Tier-1 p/s_i.

The ``score`` command builds each item's exact three-verse BSB window, overlays
the matching BSB-pseudonymized open Q/A, and asks the scorer defined in
``qa_generation/prompts/scored_qa.py`` for the four 1--10 ratings.  Successful
calls are checkpointed one at a time, so ``--resume`` is safe after an
interruption.

The ``analyze`` command recomputes the current BSB omission, mistranslation,
and adversarial p/s_i values from the completed score grid, joins them to the
dimension scores, and reports passage-clustered correlations.  The Gold-72 set
was partly selected using these outcomes, so the resulting associations are
exploratory and should not be read as out-of-sample validation.

Examples (from the repository root):

  python scripts/run_tier1_dimension_study.py score \
    --qa-generation "/path/to/combo/qa_generation" \
    --items evaluation/datasets/tier1_gold_72.json \
    --windows evaluation/datasets/tier1_gold_72_windows.json \
    --passage-dir evaluation/datasets/pseudonymized/passages/tier1_bsb \
    --model gpt-5 --runs 3 --resume

  python scripts/run_tier1_dimension_study.py analyze \
    --score-root evaluation/outputs/tier1_bsb
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "evaluation/reports/tier1_dimension_study"
DEFAULT_ITEMS = REPO_ROOT / "evaluation/datasets/tier1_gold_72.json"
DIMENSIONS = (
    "structure_dependence",
    "statement_uniqueness",
    "answer_certainty",
    "centrality",
)
PASSAGE_FILES = {
    "t1_judg9": "judg_9_1-57.txt",
    "t1_judg17_18": "judg_17_1-18_31.txt",
    "t1_2kgs6_7": "2kgs_6_24-7_20.txt",
    "t1_1kgs13": "1kgs_13_1-34.txt",
    "t1_2kgs11": "2kgs_11_1-21.txt",
    "t1_2chr26": "2chr_26_1-23.txt",
    "t1_2sam21": "2sam_21_15-22.txt",
    "t1_acts19": "acts_19_11-20.txt",
    "t1_acts20": "acts_20_7-12.txt",
    "t1_acts23": "acts_23_12-35.txt",
}
_VERSE_MARKER = re.compile(r"(?<![\w\]\-–—])(\d{1,3})\s+")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def record_list(payload: Any, path: Path | None = None) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "windows", "questions", "records"):
            if isinstance(payload.get(key), list):
                return payload[key]
        lists = [value for value in payload.values() if isinstance(value, list)]
        if len(lists) == 1:
            return lists[0]
    where = f" in {path}" if path else ""
    raise ValueError(f"could not find one record list{where}")


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def load_metadata(path: Path) -> dict[str, dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {row["id"]: row for row in rows}


def parse_tier1_verses(text: str, metadata: dict[str, str]) -> list[tuple[str, str]]:
    """Parse the project's NIV-style chapter/verse markers.

    The first marker can be a chapter number meaning verse 1, and cross-chapter
    passages restart at verse 1.  This mirrors ``scripts/pilot_import.py``.
    """
    raw = [(int(match.group(1)), match) for match in _VERSE_MARKER.finditer(text)]
    chapters = list(
        range(int(metadata["chapter_start"]), int(metadata["chapter_end"]) + 1)
    )
    if not raw or not chapters:
        raise ValueError(f"no verse markers found for {metadata.get('id')}")
    chapter_index = 0
    current = chapters[0]
    accepted: list[tuple[str, re.Match[str]]] = []
    for index, (number, match) in enumerate(raw):
        following = raw[index + 1][0] if index + 1 < len(raw) else None
        next_chapter = (
            chapters[chapter_index + 1]
            if chapter_index + 1 < len(chapters)
            else None
        )
        if index == 0 and int(metadata["verse_start"]) == 1 and number == current:
            label = f"{current}:1"
        elif (
            next_chapter is not None
            and number == next_chapter
            and following is not None
            and following < number
        ):
            chapter_index += 1
            current = next_chapter
            label = f"{current}:1"
        else:
            label = f"{current}:{number}"
        accepted.append((label, match))

    expected = f"{metadata['chapter_start']}:{metadata['verse_start']}"
    if accepted[0][0] != expected:
        raise ValueError(
            f"verse parse mismatch for {metadata.get('id')}: "
            f"first={accepted[0][0]}, expected={expected}"
        )
    verses = []
    for index, (label, marker) in enumerate(accepted):
        end = accepted[index + 1][1].start() if index + 1 < len(accepted) else len(text)
        value = text[marker.end() : end].strip()
        if not value:
            raise ValueError(f"empty parsed verse {label} for {metadata.get('id')}")
        verses.append((label, value))
    return verses


def infer_qa_dir(passage_dir: Path) -> Path | None:
    # .../pseudonymized/passages/tier1_bsb -> .../pseudonymized/qa/tier1_bsb
    if passage_dir.parent.name == "passages":
        candidate = passage_dir.parent.parent / "qa" / passage_dir.name
        if candidate.is_dir():
            return candidate
    return None


def load_open_qa_overlay(qa_dir: Path) -> dict[str, dict[str, str]]:
    overlay: dict[str, dict[str, str]] = {}
    for path in sorted(Path(qa_dir).glob("*_all_formats.json")):
        for row in record_list(read_json(path), path):
            content_id = str(row.get("content_id") or "").strip()
            if not content_id:
                continue
            opened = row.get("open") or {}
            question = opened.get("original_question") or row.get("question")
            answer = opened.get("original_answer") or row.get("answer")
            if not question or not answer:
                continue
            if content_id in overlay:
                raise ValueError(f"duplicate pseudonymized QA content_id: {content_id}")
            overlay[content_id] = {
                "question": str(question).strip(),
                "answer": str(answer).strip(),
                "source": str(path.resolve()),
            }
    if not overlay:
        raise ValueError(f"no *_all_formats.json QAs found in {qa_dir}")
    return overlay


def build_scoring_inputs(
    items_path: Path,
    windows_path: Path,
    passage_dir: Path,
    metadata_path: Path,
    qa_dir: Path | None = None,
) -> list[dict[str, Any]]:
    items = record_list(read_json(items_path), items_path)
    windows = record_list(read_json(windows_path), windows_path)
    window_by_id = {str(row.get("content_id")): row for row in windows}
    if len(window_by_id) != len(windows):
        raise ValueError("duplicate content_id in --windows")
    metadata = load_metadata(metadata_path)
    overlay = load_open_qa_overlay(qa_dir) if qa_dir else {}

    verse_maps: dict[str, dict[str, str]] = {}
    results = []
    seen = set()
    for item in items:
        content_id = str(item.get("content_id") or "").strip()
        passage_id = str(item.get("passage_id") or "").strip()
        if not content_id or not passage_id:
            raise ValueError("every item needs content_id and passage_id")
        if content_id in seen:
            raise ValueError(f"duplicate item content_id: {content_id}")
        seen.add(content_id)
        window = window_by_id.get(content_id)
        if window is None:
            raise ValueError(f"{content_id}: absent from --windows")
        if window.get("passage_id") != passage_id:
            raise ValueError(f"{content_id}: passage_id differs between inputs")
        labels = [str(value) for value in window.get("window") or []]
        if not labels:
            raise ValueError(f"{content_id}: empty verse window")

        if passage_id not in verse_maps:
            filename = PASSAGE_FILES.get(passage_id)
            if filename is None or passage_id not in metadata:
                raise ValueError(f"unknown Tier-1 passage_id: {passage_id}")
            passage_path = Path(passage_dir) / filename
            if not passage_path.is_file():
                raise FileNotFoundError(f"missing BSB passage: {passage_path}")
            parsed = parse_tier1_verses(
                passage_path.read_text(encoding="utf-8"), metadata[passage_id]
            )
            verse_maps[passage_id] = dict(parsed)

        missing_labels = [label for label in labels if label not in verse_maps[passage_id]]
        if missing_labels:
            raise ValueError(f"{content_id}: verses not found in passage: {missing_labels}")
        qa = overlay.get(content_id)
        if qa_dir and qa is None:
            raise ValueError(f"{content_id}: absent from pseudonymized QA directory {qa_dir}")
        question = (qa or {}).get("question") or item.get("question")
        answer = (qa or {}).get("answer") or item.get("answer")
        if not question or not answer:
            raise ValueError(f"{content_id}: missing question or answer")
        window_text = "\n\n".join(
            f"{label} {verse_maps[passage_id][label]}" for label in labels
        )
        results.append(
            {
                "content_id": content_id,
                "passage_id": passage_id,
                "reference": item.get("reference"),
                "global_rank": item.get("global_rank"),
                "window": labels,
                "window_text": window_text,
                "question": str(question).strip(),
                "answer": str(answer).strip(),
                "qa_text_source": (qa or {}).get("source") or str(items_path.resolve()),
                "canonical_question": item.get("question"),
                "canonical_answer": item.get("answer"),
            }
        )
    extras = sorted(set(window_by_id) - seen)
    if extras:
        raise ValueError(f"--windows has {len(extras)} IDs absent from --items")
    return results


def input_fingerprint(records: Iterable[dict[str, Any]], model: str) -> str:
    material = [
        {
            key: row.get(key)
            for key in ("content_id", "passage_id", "window", "window_text", "question", "answer")
        }
        for row in records
    ]
    encoded = json.dumps(
        {"model": model, "records": material},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _score_values(scored: Any) -> dict[str, Any]:
    result = {}
    for dimension in DIMENSIONS:
        value = getattr(scored, dimension, None)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
            raise ValueError(f"invalid {dimension} returned by judge: {value!r}")
        result[dimension] = value
    result["reason"] = getattr(scored, "reason", None)
    return result


def aggregate_scores(raw_payload: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_payload.get("scores", []):
        grouped[row["content_id"]].append(row)
    items = []
    for content_id, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda row: int(row["run"]))
        first = rows[0]
        dimensions = {}
        for dimension in DIMENSIONS:
            values = [float(row[dimension]) for row in rows]
            dimensions[dimension] = {
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
                "min": min(values),
                "max": max(values),
                "distinct": len(set(values)),
            }
        items.append(
            {
                "content_id": content_id,
                "passage_id": first.get("passage_id"),
                "reference": first.get("reference"),
                "global_rank": first.get("global_rank"),
                "question": first.get("question"),
                "answer": first.get("answer"),
                "n_runs": len(rows),
                "runs": [row["run"] for row in rows],
                "dimensions": dimensions,
            }
        )
    return {
        "schema_version": 1,
        "judge_model": raw_payload.get("judge_model"),
        "runs_requested": raw_payload.get("runs_requested"),
        "dimensions": list(DIMENSIONS),
        "n_items": len(items),
        "complete": bool(items)
        and len(items) == raw_payload.get("n_items_expected")
        and all(row["n_runs"] >= raw_payload.get("runs_requested", 1) for row in items),
        "reliability": score_reliability(raw_payload.get("scores", [])),
        "items": items,
    }


def score_reliability(scores: list[dict[str, Any]]) -> dict[str, Any]:
    by_item: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in scores:
        by_item[row["content_id"]][int(row["run"])] = row
    run_ids = sorted({run for values in by_item.values() for run in values})
    complete = [values for values in by_item.values() if all(run in values for run in run_ids)]
    result: dict[str, Any] = {
        "n_complete_items": len(complete),
        "runs": run_ids,
        "note": "ICC(2,1)/(2,k) absolute-agreement; pairwise values are Spearman rho",
        "dimensions": {},
    }
    for dimension in DIMENSIONS:
        matrix = [[float(rows[run][dimension]) for run in run_ids] for rows in complete]
        pairwise = []
        for left_index, left in enumerate(run_ids):
            for right_index in range(left_index + 1, len(run_ids)):
                right = run_ids[right_index]
                rho = spearman(
                    [row[left_index] for row in matrix],
                    [row[right_index] for row in matrix],
                )
                pairwise.append({"runs": [left, right], "rho": rho})
        icc_one, icc_average = icc2(matrix)
        pair_values = [row["rho"] for row in pairwise if row["rho"] is not None]
        result["dimensions"][dimension] = {
            "icc_2_1": icc_one,
            "icc_2_k": icc_average,
            "mean_pairwise_spearman": statistics.mean(pair_values) if pair_values else None,
            "pairwise_spearman": pairwise,
        }
    return result


def icc2(matrix: list[list[float]]) -> tuple[float | None, float | None]:
    """Shrout-Fleiss ICC(2,1) and ICC(2,k), absolute agreement."""
    n = len(matrix)
    k = len(matrix[0]) if matrix else 0
    if n < 2 or k < 2 or any(len(row) != k for row in matrix):
        return None, None
    row_means = [statistics.mean(row) for row in matrix]
    column_means = [statistics.mean(matrix[i][j] for i in range(n)) for j in range(k)]
    grand = statistics.mean(row_means)
    ms_rows = k * sum((value - grand) ** 2 for value in row_means) / (n - 1)
    ms_columns = n * sum((value - grand) ** 2 for value in column_means) / (k - 1)
    residual = sum(
        (matrix[i][j] - row_means[i] - column_means[j] + grand) ** 2
        for i in range(n)
        for j in range(k)
    )
    ms_error = residual / ((n - 1) * (k - 1))
    denom_one = ms_rows + (k - 1) * ms_error + k * (ms_columns - ms_error) / n
    denom_average = ms_rows + (ms_columns - ms_error) / n
    one = (ms_rows - ms_error) / denom_one if abs(denom_one) > 1e-15 else None
    average = (ms_rows - ms_error) / denom_average if abs(denom_average) > 1e-15 else None
    return one, average


def run_score(args: argparse.Namespace) -> int:
    qa_dir = args.qa_dir or infer_qa_dir(args.passage_dir)
    records = build_scoring_inputs(
        args.items, args.windows, args.passage_dir, args.metadata, qa_dir
    )
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        available = {row["content_id"] for row in records}
        missing = sorted(wanted - available)
        if missing:
            raise SystemExit(f"--only IDs not found: {missing}")
        records = [row for row in records if row["content_id"] in wanted]
    source_label = str(qa_dir.resolve()) if qa_dir else "canonical --items text"
    print(
        f"validated {len(records)} scoring item(s), {len({r['passage_id'] for r in records})} "
        f"passage(s); Q/A source: {source_label}"
    )
    if args.dry_run:
        preview = records[0]
        print("dry run: no API calls or files written")
        print(f"first item: {preview['content_id']} | {preview['question']}")
        print(preview["window_text"])
        return 0
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required (or use --dry-run to validate inputs)")
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    qa_generation = args.qa_generation.resolve()
    if not (qa_generation / "prompts/scored_qa.py").is_file():
        raise SystemExit(f"not a qa_generation package root: {qa_generation}")
    sys.path.insert(0, str(qa_generation.parent))
    from qa_generation.prompts.hard_qa import _build_llm
    from qa_generation.prompts.scored_qa import ScoredJSONStructure, score_structure_prompt

    out_dir = args.out_dir
    raw_path = out_dir / "dimension_scores_raw.json"
    aggregate_path = out_dir / "dimension_scores_aggregated.json"
    inputs_path = out_dir / "scoring_inputs.json"
    fingerprint = input_fingerprint(records, args.model)
    if raw_path.exists():
        if not args.resume and not args.overwrite:
            raise SystemExit(
                f"{raw_path} already exists; use --resume or explicitly use --overwrite"
            )
        if args.overwrite:
            payload = {}
        else:
            payload = read_json(raw_path)
            if payload.get("input_fingerprint") != fingerprint:
                raise SystemExit(
                    "resume input/model fingerprint differs from the checkpoint; "
                    "use a new --out-dir or --overwrite"
                )
    else:
        payload = {}
    if not payload:
        payload = {
            "schema_version": 1,
            "judge_model": args.model,
            "runs_requested": args.runs,
            "n_items_expected": len(records),
            "dimensions": list(DIMENSIONS),
            "input_fingerprint": fingerprint,
            "rubric_source": str((qa_generation / "prompts/scored_qa.py").resolve()),
            "qa_text_source": source_label,
            "scores": [],
            "errors": [],
        }
    payload["runs_requested"] = max(int(payload.get("runs_requested", 0)), args.runs)
    payload["n_items_expected"] = len(records)
    atomic_json(
        inputs_path,
        {
            "schema_version": 1,
            "input_fingerprint": fingerprint,
            "judge_model": args.model,
            "items": records,
        },
    )
    atomic_json(raw_path, payload)

    completed = {(row["content_id"], int(row["run"])) for row in payload["scores"]}
    total = len(records) * args.runs
    print(f"checkpoint has {len(completed)}/{total} requested item-run score(s)")
    judge = _build_llm(args.model)
    chain = score_structure_prompt | judge.with_structured_output(ScoredJSONStructure)
    failures: list[tuple[str, int, str]] = []

    def checkpoint() -> None:
        atomic_json(raw_path, payload)
        atomic_json(aggregate_path, aggregate_scores(payload))

    try:
        for record in records:
            for run in range(1, args.runs + 1):
                key = (record["content_id"], run)
                if key in completed:
                    continue
                print(f"[{len(completed) + 1}/{total}] {record['content_id']} run {run}")
                try:
                    output = chain.invoke(
                        {
                            "window": record["window_text"],
                            "Qs": f"Question: {record['question']}\nAnswer: {record['answer']}",
                        }
                    )
                    pairs = list(getattr(output, "qa_pairs", None) or [])
                    exact = [pair for pair in pairs if getattr(pair, "Q", None) == record["question"]]
                    if len(exact) == 1:
                        scored = exact[0]
                    elif len(pairs) == 1:
                        scored = pairs[0]
                    else:
                        raise ValueError(f"judge returned {len(pairs)} Q/A score rows")
                    row = {
                        key: record.get(key)
                        for key in (
                            "content_id",
                            "passage_id",
                            "reference",
                            "global_rank",
                            "question",
                            "answer",
                        )
                    }
                    row["run"] = run
                    row.update(_score_values(scored))
                    payload["scores"].append(row)
                    payload["errors"] = [
                        error
                        for error in payload.get("errors", [])
                        if (error.get("content_id"), error.get("run")) != key
                    ]
                    completed.add(key)
                    checkpoint()
                except Exception as exc:  # API/structured-output failures remain resumable
                    message = f"{type(exc).__name__}: {exc}"
                    failures.append((record["content_id"], run, message))
                    payload["errors"] = [
                        error
                        for error in payload.get("errors", [])
                        if (error.get("content_id"), error.get("run")) != key
                    ]
                    payload["errors"].append(
                        {"content_id": record["content_id"], "run": run, "error": message}
                    )
                    checkpoint()
                    print(f"[warn] {record['content_id']} run {run}: {message}", file=sys.stderr)
    except KeyboardInterrupt:
        checkpoint()
        print(f"\ninterrupted; checkpointed {len(completed)}/{total}. Re-run with --resume.")
        return 130

    checkpoint()
    if failures:
        print(f"completed with {len(failures)} failed call(s); re-run with --resume", file=sys.stderr)
        return 1
    print(f"scoring complete: {len(completed)}/{total}")
    print(f"raw:        {raw_path}")
    print(f"aggregated: {aggregate_path}")
    return 0


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor
        while end + 1 < len(order) and values[order[end + 1]] == values[order[cursor]]:
            end += 1
        shared = (cursor + end) / 2.0 + 1.0
        for position in range(cursor, end + 1):
            result[order[position]] = shared
        cursor = end + 1
    return result


def spearman(xs: Iterable[float], ys: Iterable[float]) -> float | None:
    left, right = list(xs), list(ys)
    if len(left) != len(right) or len(left) < 3:
        return None
    rank_left, rank_right = _ranks(left), _ranks(right)
    mean_left, mean_right = statistics.mean(rank_left), statistics.mean(rank_right)
    numerator = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(rank_left, rank_right)
    )
    scale_left = math.sqrt(sum((value - mean_left) ** 2 for value in rank_left))
    scale_right = math.sqrt(sum((value - mean_right) ** 2 for value in rank_right))
    if scale_left == 0 or scale_right == 0:
        return None
    return numerator / (scale_left * scale_right)


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def association(
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    bootstraps: int,
    permutations: int,
    seed: int,
) -> dict[str, Any]:
    usable = [row for row in rows if row.get(x_key) is not None and row.get(y_key) is not None]
    observed = spearman(
        [float(row[x_key]) for row in usable], [float(row[y_key]) for row in usable]
    )
    passages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        passages[str(row["passage_id"])].append(row)
    rng = random.Random(seed)
    bootstrap_values = []
    passage_names = sorted(passages)
    for _ in range(bootstraps):
        sampled = [rng.choice(passage_names) for _ in passage_names]
        sample_rows = [row for name in sampled for row in passages[name]]
        value = spearman(
            [float(row[x_key]) for row in sample_rows],
            [float(row[y_key]) for row in sample_rows],
        )
        if value is not None:
            bootstrap_values.append(value)

    permutation_p = None
    if observed is not None and permutations > 0:
        hits = 0
        base_y = [float(row[y_key]) for row in usable]
        indices_by_passage: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(usable):
            indices_by_passage[str(row["passage_id"])].append(index)
        base_x = [float(row[x_key]) for row in usable]
        for _ in range(permutations):
            shuffled = base_x[:]
            for indices in indices_by_passage.values():
                values = [shuffled[index] for index in indices]
                rng.shuffle(values)
                for index, value in zip(indices, values):
                    shuffled[index] = value
            value = spearman(shuffled, base_y)
            if value is not None and abs(value) >= abs(observed) - 1e-15:
                hits += 1
        permutation_p = (hits + 1) / (permutations + 1)
    return {
        "n": len(usable),
        "n_passages": len(passages),
        "rho": observed,
        "cluster_bootstrap_ci_95": [
            percentile(bootstrap_values, 0.025),
            percentile(bootstrap_values, 0.975),
        ],
        "within_passage_permutation_p": permutation_p,
        "bootstrap_replicates_used": len(bootstrap_values),
    }


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    available = [(index, value) for index, value in enumerate(p_values) if value is not None]
    result: list[float | None] = [None] * len(p_values)
    if not available:
        return result
    ordered = sorted(available, key=lambda pair: pair[1])
    running = 1.0
    total = len(ordered)
    for reverse_index in range(total - 1, -1, -1):
        original_index, value = ordered[reverse_index]
        rank = reverse_index + 1
        running = min(running, float(value) * total / rank)
        result[original_index] = min(1.0, running)
    return result


def validate_score_matrix(score_root: Path, passages: list[str], module: Any) -> None:
    missing = []
    for passage in passages:
        for model in module.MODELS:
            for ladder in module.LADDERS.values():
                for _dose, condition in ladder:
                    path = score_root / passage / model / condition / "scores_target_llama.json"
                    if not path.is_file():
                        missing.append(path)
    # A baseline appears in several ladders; make diagnostics concise.
    unique = sorted(set(missing))
    if unique:
        examples = "\n  ".join(str(path) for path in unique[:10])
        raise SystemExit(
            f"sensitivity matrix is incomplete: {len(unique)} score file(s) missing; first:\n  {examples}"
        )


def build_sensitivity(
    score_root: Path,
    passages: list[str],
    out_path: Path,
    p_gate: float,
    reuse: bool,
) -> dict[str, Any]:
    if reuse and out_path.is_file():
        return read_json(out_path)
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import report_tier1_family_split as family

    score_root = score_root.resolve()
    if score_root.parent.name != "outputs":
        raise SystemExit(
            "--score-root must have the standard <evaluation>/outputs/<study> layout"
        )
    validate_score_matrix(score_root, passages, family)
    old_root = family.TIER1_ROOT
    try:
        family.TIER1_ROOT = score_root.name
        family.emit_sensitivity(score_root.parent.parent, passages, out_path, p_gate)
    finally:
        family.TIER1_ROOT = old_root
    return read_json(out_path)


def dimension_rows(aggregated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in aggregated.get("items", []):
        flattened = dict(row)
        for dimension in DIMENSIONS:
            stats = row.get("dimensions", {}).get(dimension) or {}
            flattened[dimension] = stats.get("mean")
            flattened[f"{dimension}_sd"] = stats.get("sd")
        result[row["content_id"]] = flattened
    return result


def write_merged_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "content_id",
        "passage_id",
        "reference",
        "global_rank",
        "question",
        "n_runs",
        *DIMENSIONS,
        *[f"{dimension}_sd" for dimension in DIMENSIONS],
        "family",
        "s_i",
        "se_s_i",
        "p",
        "neg_log10_p",
        "passes_gate",
        "slope",
        "n_doses",
        "n_obs",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_correlation_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "dimension",
        "family",
        "outcome",
        "n",
        "n_passages",
        "rho",
        "ci_low",
        "ci_high",
        "within_passage_permutation_p",
        "bh_q",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            copy = dict(row)
            ci = copy.pop("cluster_bootstrap_ci_95", [None, None])
            copy["ci_low"], copy["ci_high"] = ci
            writer.writerow(copy)


def fmt(value: Any, digits: int = 3) -> str:
    return "--" if value is None else f"{float(value):.{digits}f}"


def make_report(
    aggregated: dict[str, Any],
    merged: list[dict[str, Any]],
    correlations: list[dict[str, Any]],
    p_gate: float,
) -> str:
    families = sorted({row["family"] for row in merged})
    lines = [
        "# Tier-1 Gold-72 dimension study",
        "",
        f"Dimension coverage: **{aggregated.get('n_items', 0)}/72 items**; "
        f"requested runs per item: **{aggregated.get('runs_requested')}**; "
        f"aggregate complete: **{aggregated.get('complete')}**.",
        "",
        "## Scoring reliability",
        "",
        "| Dimension | ICC(2,1) | ICC(2,k) | Mean pairwise Spearman |",
        "|---|---:|---:|---:|",
    ]
    reliability = aggregated.get("reliability", {}).get("dimensions", {})
    for dimension in DIMENSIONS:
        row = reliability.get(dimension, {})
        lines.append(
            f"| {dimension} | {fmt(row.get('icc_2_1'))} | {fmt(row.get('icc_2_k'))} "
            f"| {fmt(row.get('mean_pairwise_spearman'))} |"
        )
    lines += [
        "",
        "## Structure dependence versus sensitivity",
        "",
        "| Family | Outcome | n | Spearman rho | Passage-clustered 95% CI | Permutation p | BH q |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in correlations:
        if row["dimension"] != "structure_dependence":
            continue
        low, high = row["cluster_bootstrap_ci_95"]
        lines.append(
            f"| {row['family']} | {row['outcome']} | {row['n']} | {fmt(row['rho'])} "
            f"| [{fmt(low)}, {fmt(high)}] | "
            f"{fmt(row['within_passage_permutation_p'], 4)} | {fmt(row.get('bh_q'), 4)} |"
        )
    gate_lines = []
    for family in families:
        family_rows = [row for row in merged if row["family"] == family]
        passed = sum(bool(row["passes_gate"]) for row in family_rows)
        gate_lines.append(f"- {family}: {passed}/{len(family_rows)} pass p <= {p_gate} and s_i > 0")
    lines += [
        "",
        "## Gate coverage",
        "",
        *gate_lines,
        "",
        "## Interpretation rules",
        "",
        "- A positive correlation with `s_i` means higher rubric scores accompany greater "
        "translation sensitivity.",
        "- A negative correlation with raw `p` means higher rubric scores accompany stronger "
        "dose-response evidence. `neg_log10_p` is the same ordering with the intuitive sign.",
        "- Correlations use all items. They are not filtered to p-gated items, which would "
        "condition on the outcome and bias the estimates.",
        "- Confidence intervals resample whole passages; permutation tests shuffle dimension "
        "scores within passages. This accounts conservatively for overlapping windows and "
        "shared passage context.",
        "- BH q-values cover the nonredundant `s_i` and `neg_log10_p` tests across four "
        "dimensions and three families. Raw-p rows reuse the corresponding evidence q-value.",
        "",
        "## Limitation",
        "",
        "The 72 questions were selected partly using p/s_i. These are exploratory, "
        "post-selection associations, not an independent validation of the rubric. Confirm any "
        "promising structural-dependence result on held-out questions or a newly collected grid.",
        "",
    ]
    return "\n".join(lines)


def run_analyze(args: argparse.Namespace) -> int:
    aggregated_path = args.dimension_scores or args.out_dir / "dimension_scores_aggregated.json"
    if not aggregated_path.is_file():
        raise SystemExit(
            f"missing dimension scores: {aggregated_path}\nRun the score subcommand first."
        )
    aggregated = read_json(aggregated_path)
    if not aggregated.get("complete") and not args.allow_incomplete:
        raise SystemExit(
            "dimension score checkpoint is incomplete; resume scoring, or use "
            "--allow-incomplete for a diagnostic analysis"
        )
    dimensions = dimension_rows(aggregated)
    gold = {row["content_id"]: row for row in record_list(read_json(args.items), args.items)}
    passages = sorted({row["passage_id"] for row in gold.values()})
    sensitivity_path = args.out_dir / "sensitivity_bsb.json"
    sensitivity = build_sensitivity(
        args.score_root, passages, sensitivity_path, args.p_gate, args.reuse_sensitivity
    )
    sensitivity_items = sensitivity.get("items", {})
    missing_dimension = sorted(set(gold) - set(dimensions))
    missing_sensitivity = sorted(set(gold) - set(sensitivity_items))
    if missing_dimension and not args.allow_incomplete:
        raise SystemExit(f"{len(missing_dimension)} Gold IDs lack dimension scores")
    if missing_sensitivity:
        raise SystemExit(
            f"{len(missing_sensitivity)} Gold IDs lack current BSB sensitivity: "
            f"{missing_sensitivity[:8]}"
        )

    merged = []
    families = list(sensitivity.get("families") or [])
    p_floor = 1.0 / 2001.0  # slope_permutation_p currently uses 2,000 permutations.
    for content_id in sorted(set(gold) & set(dimensions) & set(sensitivity_items)):
        base = dict(dimensions[content_id])
        for family in families:
            outcome = sensitivity_items[content_id].get(family)
            if not outcome:
                continue
            p_value = outcome.get("p")
            merged.append(
                {
                    **base,
                    "family": family,
                    **outcome,
                    "neg_log10_p": (
                        -math.log10(max(float(p_value), p_floor))
                        if p_value is not None
                        else None
                    ),
                }
            )

    correlation_rows = []
    for dimension in DIMENSIONS:
        for family in families:
            family_rows = [row for row in merged if row["family"] == family]
            for outcome in ("s_i", "p", "neg_log10_p"):
                # Raw p and -log10(p) have exactly reversed ranks.  Reuse their
                # random stream so Monte Carlo noise cannot make their
                # permutation p-values disagree.
                seed_outcome = "p_evidence" if outcome in ("p", "neg_log10_p") else outcome
                stable_seed = int.from_bytes(
                    hashlib.sha256(
                        f"{args.seed}:{dimension}:{family}:{seed_outcome}".encode()
                    ).digest()[:8],
                    "big",
                )
                stats = association(
                    family_rows,
                    dimension,
                    outcome,
                    args.bootstraps,
                    args.permutations,
                    stable_seed,
                )
                correlation_rows.append(
                    {
                        "dimension": dimension,
                        "family": family,
                        "outcome": outcome,
                        **stats,
                    }
                )

    # FDR is applied to s_i and evidence. Raw p is a monotone sign-reversal of
    # evidence, so it gets the same q-value rather than being counted twice.
    tested = [row for row in correlation_rows if row["outcome"] in ("s_i", "neg_log10_p")]
    adjusted = benjamini_hochberg(
        [row["within_passage_permutation_p"] for row in tested]
    )
    q_by_key = {}
    for row, q_value in zip(tested, adjusted):
        row["bh_q"] = q_value
        q_by_key[(row["dimension"], row["family"], row["outcome"])] = q_value
    for row in correlation_rows:
        if row["outcome"] == "p":
            row["bh_q"] = q_by_key.get(
                (row["dimension"], row["family"], "neg_log10_p")
            )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    merged_csv = args.out_dir / "dimension_sensitivity_merged.csv"
    correlation_csv = args.out_dir / "correlations.csv"
    correlation_json = args.out_dir / "correlations.json"
    report_path = args.out_dir / "report.md"
    write_merged_csv(merged_csv, merged)
    write_correlation_csv(correlation_csv, correlation_rows)
    atomic_json(
        correlation_json,
        {
            "schema_version": 1,
            "method": {
                "coefficient": "Spearman rho",
                "ci": "95% passage-cluster bootstrap percentile interval",
                "p": "two-sided within-passage permutation test",
                "bootstraps": args.bootstraps,
                "permutations": args.permutations,
                "seed": args.seed,
                "multiple_testing": "Benjamini-Hochberg over 24 nonredundant s_i/evidence tests",
            },
            "correlations": correlation_rows,
        },
    )
    report_path.write_text(
        make_report(aggregated, merged, correlation_rows, args.p_gate), encoding="utf-8"
    )
    print(f"joined {len(set(row['content_id'] for row in merged))}/72 items across {len(families)} families")
    print(f"merged data:  {merged_csv}")
    print(f"correlations: {correlation_csv}")
    print(f"report:       {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    score = subparsers.add_parser("score", help="score the Gold-72 QAs on four dimensions")
    score.add_argument("--qa-generation", type=Path, required=True)
    score.add_argument("--items", type=Path, required=True)
    score.add_argument("--windows", type=Path, required=True)
    score.add_argument("--passage-dir", type=Path, required=True)
    score.add_argument(
        "--qa-dir",
        type=Path,
        help="matching pseudonymized *_all_formats.json directory; inferred from --passage-dir",
    )
    score.add_argument(
        "--metadata",
        type=Path,
        default=REPO_ROOT / "evaluation/datasets/obscure_narrative_passages_tier1.csv",
    )
    score.add_argument("--model", default="gpt-5")
    score.add_argument("--runs", type=int, default=3)
    score.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    score.add_argument("--only", help="optional comma-separated content IDs")
    score.add_argument("--resume", action="store_true")
    score.add_argument("--overwrite", action="store_true")
    score.add_argument("--dry-run", action="store_true")
    score.set_defaults(func=run_score)

    analyze = subparsers.add_parser("analyze", help="join dimensions to current BSB p/s_i")
    analyze.add_argument(
        "--score-root", type=Path, default=REPO_ROOT / "evaluation/outputs/tier1_bsb"
    )
    analyze.add_argument("--dimension-scores", type=Path)
    analyze.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    analyze.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    analyze.add_argument("--p-gate", type=float, default=0.10)
    analyze.add_argument("--bootstraps", type=int, default=2000)
    analyze.add_argument("--permutations", type=int, default=5000)
    analyze.add_argument("--seed", type=int, default=20260819)
    analyze.add_argument("--reuse-sensitivity", action="store_true")
    analyze.add_argument("--allow-incomplete", action="store_true")
    analyze.set_defaults(func=run_analyze)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if getattr(args, "resume", False) and getattr(args, "overwrite", False):
        raise SystemExit("choose only one of --resume or --overwrite")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
