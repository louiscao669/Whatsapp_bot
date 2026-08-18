#!/usr/bin/env python3
"""Persist the Gate-1 one-question-per-window decisions in tier-1 metadata.

The importer remains the source of truth for the ranking. This script copies its
collision decisions onto both canonical metadata views:

* evaluation/datasets/qa/tier1_QAs_easy/*_all_formats.json
* QA_algorithm/inputs/tier1_qa_verse_windows.json

Only questions involved in a collision are annotated. Later copies of an exact
duplicate are explicitly marked not chosen, just like lower-ranked questions.
"""

import argparse
import json
from pathlib import Path

from pilot_import import build_tier1_pool


REPO_ROOT = Path(__file__).resolve().parents[1]
ANNOTATION_FIELD = "pilot_window_selection"
METRIC_FIELDS = (
    "passes_p_gate",
    "n_gated_families",
    "best_s_i",
    "s_i_omission",
    "se_s_i_omission",
    "p_omission",
    "gated_omission",
    "s_i_mistranslation",
    "se_s_i_mistranslation",
    "p_mistranslation",
    "gated_mistranslation",
    "quality_score",
    "source_difficulty",
    "clean_accuracy",
    "dose_drop",
    "difficulty_fit",
    "selection_score",
    "clean_n",
    "degraded_n",
    "needs_review",
    "answer_not_fully_in_passage",
)


def _metrics(row: dict) -> dict:
    return {name: row[name] for name in METRIC_FIELDS if name in row}


def build_annotations(eval_root: Path) -> tuple[dict, dict]:
    """Return annotations keyed by QA content ID and curated window-map key."""
    _qa_rows, _window_rows, report = build_tier1_pool(eval_root, 0.75, 2026)
    by_content_id = {}
    by_window_key = {}

    for decision in report["collision_decisions"]:
        chosen = decision["chosen"]
        chosen_base_id = chosen["base_id"]
        chosen_content_id = chosen_base_id.removeprefix("uw-")
        common = {
            "selected_base_id": chosen_base_id,
            "selected_content_id": chosen_content_id,
            "selection_reason": decision["selection_reason"],
            "window": decision["window"],
        }
        chosen_annotation = {
            "status": "chosen",
            "removed_from_human_pilot": False,
            **common,
            "metrics": _metrics(chosen),
        }
        by_content_id[chosen_content_id] = chosen_annotation
        by_window_key[chosen["window_item_key"]] = chosen_annotation

        rejection_reason = (
            "exact_duplicate_later_copy"
            if decision["selection_reason"] == "exact_duplicate_first_copy"
            else "lower_p_si_primary_or_collision_features_secondary_rank"
        )
        for rejected in decision["rejected"]:
            rejected_content_id = rejected["base_id"].removeprefix("uw-")
            rejected_annotation = {
                "status": "not_chosen",
                "removed_from_human_pilot": True,
                **common,
                "reason": rejection_reason,
                "metrics": _metrics(rejected),
            }
            by_content_id[rejected_content_id] = rejected_annotation
            by_window_key[rejected["window_item_key"]] = rejected_annotation

    return by_content_id, by_window_key


def _write_json(path: Path, value, indent: int) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )


def annotate_metadata(repo_root: Path, eval_root: Path, check: bool = False) -> dict:
    by_content_id, by_window_key = build_annotations(eval_root)
    qa_root = eval_root / "datasets" / "qa" / "tier1_QAs_easy"
    seen_content_ids = set()
    changed_files = 0

    for path in sorted(qa_root.glob("*_all_formats.json")):
        records = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for record in records:
            content_id = record.get("content_id")
            annotation = by_content_id.get(content_id)
            if annotation is not None:
                seen_content_ids.add(content_id)
                if record.get(ANNOTATION_FIELD) != annotation:
                    record[ANNOTATION_FIELD] = annotation
                    changed = True
            elif ANNOTATION_FIELD in record:
                del record[ANNOTATION_FIELD]
                changed = True
        if changed:
            changed_files += 1
            if not check:
                # Preserve the source file's established one- or two-space style.
                first_item = next(
                    (line for line in path.read_text(encoding="utf-8").splitlines()
                     if line.lstrip().startswith("{")),
                    "  {",
                )
                _write_json(path, records, max(len(first_item) - len(first_item.lstrip()), 1))

    window_path = repo_root / "QA_algorithm" / "inputs" / "tier1_qa_verse_windows.json"
    window_document = json.loads(window_path.read_text(encoding="utf-8"))
    seen_window_keys = set()
    window_changed = False
    for record in window_document["windows"]:
        key = record.get("key")
        annotation = by_window_key.get(key)
        if annotation is not None:
            seen_window_keys.add(key)
            if record.get(ANNOTATION_FIELD) != annotation:
                record[ANNOTATION_FIELD] = annotation
                window_changed = True
        elif ANNOTATION_FIELD in record:
            del record[ANNOTATION_FIELD]
            window_changed = True
    if window_changed:
        changed_files += 1
        if not check:
            _write_json(window_path, window_document, 2)

    missing_content = sorted(set(by_content_id) - seen_content_ids)
    missing_windows = sorted(set(by_window_key) - seen_window_keys)
    if missing_content or missing_windows:
        raise RuntimeError(
            f"annotation targets missing: QA={missing_content}, windows={missing_windows}"
        )

    statuses = [annotation["status"] for annotation in by_content_id.values()]
    return {
        "chosen": statuses.count("chosen"),
        "not_chosen": statuses.count("not_chosen"),
        "changed_files": changed_files,
        "in_sync": changed_files == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--eval-root", type=Path, default=REPO_ROOT / "evaluation")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report whether annotations are current without writing files",
    )
    args = parser.parse_args()
    report = annotate_metadata(args.repo_root, args.eval_root, check=args.check)
    action = "would update" if args.check else "updated"
    if report["in_sync"]:
        action = "already in sync"
    print(
        f"tier-1 pilot metadata {action}: "
        f"{report['chosen']} chosen, {report['not_chosen']} not chosen; "
        f"{report['changed_files']} file(s) changed"
    )
    return 1 if args.check and not report["in_sync"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
