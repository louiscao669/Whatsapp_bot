#!/usr/bin/env python3
"""Offline tests for scripts/run_tier1_dimension_study.py."""

from __future__ import annotations

import unittest
from pathlib import Path

import run_tier1_dimension_study as study


REPO_ROOT = Path(__file__).resolve().parents[1]


class DimensionStudyTests(unittest.TestCase):
    def test_hydrates_all_gold_items_with_bsb_qa_and_exact_windows(self):
        passage_dir = REPO_ROOT / "evaluation/datasets/pseudonymized/passages/tier1_bsb"
        rows = study.build_scoring_inputs(
            REPO_ROOT / "evaluation/datasets/tier1_gold_72.json",
            REPO_ROOT / "evaluation/datasets/tier1_gold_72_windows.json",
            passage_dir,
            REPO_ROOT / "evaluation/datasets/obscure_narrative_passages_tier1.csv",
            study.infer_qa_dir(passage_dir),
        )
        self.assertEqual(len(rows), 72)
        self.assertEqual(len({row["content_id"] for row in rows}), 72)
        self.assertTrue(all(len(row["window"]) == 3 for row in rows))
        self.assertTrue(all(row["window_text"].count("\n\n") == 2 for row in rows))
        # This proves the BSB pseudonymized QA replaced the canonical Uzziah/Eloth text.
        example = next(row for row in rows if row["content_id"] == "t1_2chr26:abwv")
        self.assertIn("Kireth", example["question"])
        self.assertNotIn("Uzziah", example["question"])
        self.assertTrue(example["window_text"].startswith("26:1 "))

    def test_aggregate_and_reliability(self):
        scores = []
        for item_index in range(5):
            for run in (1, 2, 3):
                value = min(10, item_index + run)
                scores.append(
                    {
                        "content_id": f"p:item{item_index}",
                        "passage_id": "p",
                        "run": run,
                        "question": "q",
                        "answer": "a",
                        **{dimension: value for dimension in study.DIMENSIONS},
                    }
                )
        payload = {
            "judge_model": "test",
            "runs_requested": 3,
            "n_items_expected": 5,
            "scores": scores,
        }
        result = study.aggregate_scores(payload)
        self.assertTrue(result["complete"])
        self.assertEqual(result["n_items"], 5)
        self.assertEqual(result["items"][0]["n_runs"], 3)
        self.assertAlmostEqual(
            result["items"][0]["dimensions"]["structure_dependence"]["mean"], 2.0
        )
        reliability = result["reliability"]["dimensions"]["structure_dependence"]
        self.assertAlmostEqual(reliability["mean_pairwise_spearman"], 1.0)
        self.assertIsNotNone(reliability["icc_2_k"])

    def test_spearman_ties_and_bh(self):
        self.assertAlmostEqual(study.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        tied = study.spearman([1, 1, 2, 3], [1, 1, 2, 3])
        self.assertAlmostEqual(tied, 1.0)
        adjusted = study.benjamini_hochberg([0.01, 0.04, 0.03, None])
        self.assertEqual(adjusted[3], None)
        self.assertAlmostEqual(adjusted[0], 0.03)
        self.assertAlmostEqual(adjusted[1], 0.04)
        self.assertAlmostEqual(adjusted[2], 0.04)

    def test_clustered_association_is_deterministic(self):
        rows = []
        for passage in ("a", "b", "c"):
            for value in range(1, 7):
                rows.append(
                    {
                        "passage_id": passage,
                        "x": float(value),
                        "y": float(value) + (0.1 if passage == "b" else 0.0),
                    }
                )
        first = study.association(rows, "x", "y", 50, 100, 17)
        second = study.association(rows, "x", "y", 50, 100, 17)
        self.assertEqual(first, second)
        self.assertGreater(first["rho"], 0.99)
        self.assertLessEqual(first["within_passage_permutation_p"], 0.02)

    def test_resume_fingerprint_changes_when_text_changes(self):
        row = {
            "content_id": "p:x",
            "passage_id": "p",
            "window": ["1:1"],
            "window_text": "1:1 text",
            "question": "Who?",
            "answer": "A",
        }
        original = study.input_fingerprint([row], "gpt-5")
        changed = study.input_fingerprint([{**row, "answer": "B"}], "gpt-5")
        self.assertNotEqual(original, changed)


if __name__ == "__main__":
    unittest.main()
