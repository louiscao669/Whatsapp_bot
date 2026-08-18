#!/usr/bin/env python3
"""Fit Tier-1 p/s_i evidence and rank every translated question.

Primary ordering is lexicographic: permutation-p gate, number of weighted
families passing, then strongest gated s_i. Existing collision quality,
answerability, clean-difficulty, dose-drop, and source-quality features are
secondary and cannot override the primary evidence tier.

Run from the repository root:

    python scripts/rank_tier1_questions.py --eval-root evaluation
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pilot_import as pilot  # noqa: E402
from report_tier1_family_split import emit_sensitivity  # noqa: E402


CSV_FIELDS = [
    "rank", "passage_id", "base_id", "content_id", "window_item_key",
    "evidence_tier", "selected_for_pilot_window", "question",
    "passes_p_gate", "n_gated_families", "best_s_i",
    "s_i_omission", "se_s_i_omission", "p_omission", "gated_omission",
    "s_i_mistranslation", "se_s_i_mistranslation", "p_mistranslation",
    "gated_mistranslation", "s_i_adversarial", "se_s_i_adversarial",
    "p_adversarial", "gated_adversarial", "needs_review",
    "answer_not_fully_in_passage", "clean_accuracy", "dose_drop",
    "difficulty_fit", "quality_score", "source_difficulty",
    "selection_score", "window",
]


def write_csv(path: Path, ranking: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in ranking:
            record = dict(row)
            record["window"] = "|".join(record.get("window") or [])
            writer.writerow(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-root", type=Path, default=Path("evaluation"))
    parser.add_argument("--p-gate", type=float, default=pilot.TIER1_P_GATE)
    parser.add_argument(
        "--no-refresh-sensitivity", action="store_true",
        help="reuse evaluation/reports/tier1_item_sensitivity.json",
    )
    parser.add_argument(
        "--out-json", type=Path,
        default=Path("evaluation/reports/tier1_question_ranking.json"),
    )
    parser.add_argument(
        "--out-csv", type=Path,
        default=Path("evaluation/reports/tier1_question_ranking.csv"),
    )
    parser.add_argument("--mcq-fraction", type=float, default=pilot.MCQ_FRACTION)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    eval_root = args.eval_root.expanduser().resolve()
    pilot.TIER1_P_GATE = args.p_gate
    sensitivity_path = pilot.tier1_sensitivity_path(eval_root)
    passages = [row["id"] for row in pilot.load_tier1_metadata(eval_root)]
    if not args.no_refresh_sensitivity or not sensitivity_path.exists():
        emit_sensitivity(eval_root, passages, sensitivity_path, args.p_gate)

    _qa_rows, _window_rows, report = pilot.build_tier1_pool(
        eval_root, args.mcq_fraction, args.seed
    )
    ranking = report["question_ranking"]
    tiers = Counter(row["evidence_tier"] for row in ranking)
    payload = {
        "schema_version": 1,
        "ranking_contract": {
            "direction": "rank 1 is best",
            "primary": [
                f"permutation p <= {args.p_gate} and positive s_i",
                "number of passing weighted families",
                "strongest gated s_i",
            ],
            "secondary": "tier1_collision_features lexicographic rank",
            "weighted_families": list(pilot.TIER1_WEIGHTED_FAMILIES),
            "audit_only_families": sorted(
                set(pilot.TIER1_DEFECT_FAMILIES) - set(pilot.TIER1_WEIGHTED_FAMILIES)
            ),
            "s_i_definition": (
                "partially pooled logit slope per SD of translation quality "
                "with free item intercept and answer-model ability offset"
            ),
        },
        "counts": {
            "translated": report["translated"],
            "ranked": len(ranking),
            "unique_windows": report["unique"],
            "removed_window_collisions": len(report["collisions"]),
            "evidence_tiers": dict(sorted(tiers.items())),
        },
        "sensitivity_source": str(sensitivity_path),
        "questions": ranking,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(args.out_csv, ranking)
    print(f"ranked {len(ranking)} questions; evidence tiers: {dict(tiers)}")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
