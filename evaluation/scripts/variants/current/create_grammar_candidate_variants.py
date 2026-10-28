#!/usr/bin/env python3
"""Expand an approved grammar pool and select distinct, nested percentage levels.

The candidate count is a minimum number of different approved clauses, not a
number of proposals or alternative rewrites of the same clause. Surplus approved
edits remain in the bank; they need not appear in the highest-dose passage.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.variants.current import create_grammar_variants as grammar


# Shared with the standard generator so both CLIs use the same selection rules.
plan_nested_selections = grammar.plan_nested_selections


def reuse_caches(source_bank_dir: Path, destination_bank_dir: Path) -> None:
    """Merge exact cached requests without changing the source experiment."""
    if source_bank_dir.resolve() == destination_bank_dir.resolve():
        return
    for filename, field in (
        ("proposals.json", "proposals"), ("judgments.json", "judgments"),
        ("meaning_readings.json", "readings"), ("meaning_judgments.json", "reviews"),
    ):
        source = source_bank_dir / filename
        if not source.is_file():
            if field in ("readings", "reviews"):
                continue  # Historical banks predate the independent meaning review.
            raise grammar.GrammarError(f"Missing cache to reuse: {source}")
        destination = destination_bank_dir / filename
        incoming = grammar.read_json_object(source)
        saved = grammar.read_json_object(destination) if destination.exists() else {
            "schema_version": 1, field: {},
        }
        for data in (incoming, saved):
            if data.get("schema_version") != 1 or not isinstance(data.get(field), dict):
                raise grammar.GrammarError(f"Invalid {field} cache: {source_bank_dir}")
        for key, record in incoming[field].items():
            if key in saved[field] and saved[field][key] != record:
                raise grammar.GrammarError(f"Conflicting cached {field} entry: {key}")
            saved[field][key] = record
        grammar.write_json_atomic(destination, saved)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--passage-dirs", nargs="+", required=True)
    parser.add_argument("--source-model-dir", default="_base")
    parser.add_argument("--source-method", default="llm_prompt_high")
    parser.add_argument("--output-model-dir", default="grammar_candidate_test")
    parser.add_argument("--reuse-cache-model-dir", help="Existing experiment whose _grammar_bank caches to copy and reuse.")
    parser.add_argument(
        "--target-candidates", type=int, required=True,
        help="Minimum total approved edits on different clauses, including existing approvals.",
    )
    parser.add_argument("--rates", nargs="+", default=[grammar.format_rate(r) for r in grammar.DEFAULT_RATES])
    parser.add_argument("--retry-rounds", type=int, default=grammar.DEFAULT_RETRY_ROUNDS)
    parser.add_argument("--coverage-tolerance-pp", type=float, default=2.0, help="Maximum absolute deviation in percentage points (default: 2).")
    parser.add_argument("--generator-model", default=None, help="Defaults to the judge model.")
    parser.add_argument("--judge-model", default="gpt-4o-mini")
    parser.add_argument("--max-candidates-per-clause", type=int, default=3)
    parser.add_argument("--proposal-batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--protected-terms", action="append", default=[], metavar="NAME_MAP.json")
    parser.add_argument("--offline", action="store_true", help="Fail if an uncached model call is needed.")
    parser.add_argument("--force", action="store_true", help="Replace previously exported variants in the output directory.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        rates = sorted(set(grammar.parse_rates(args.rates)))
        positive = [rate for rate in rates if rate > 0]
        if not positive:
            raise grammar.GrammarError("Request at least one positive rate.")
        if args.target_candidates < len(positive):
            raise grammar.GrammarError("--target-candidates must be at least the number of positive levels.")
        if args.max_candidates_per_clause < 1 or args.proposal_batch_size < 1:
            raise grammar.GrammarError("Proposal batch size and candidates per clause must be positive.")
        if args.retry_rounds < 0:
            raise grammar.GrammarError("--retry-rounds must be nonnegative.")
        if not math.isfinite(args.coverage_tolerance_pp) or not 0 <= args.coverage_tolerance_pp <= 100:
            raise grammar.GrammarError("Coverage tolerance must be between 0 and 100 percentage points.")
        grammar.load_protected_terms(args.protected_terms)
    except (grammar.GrammarError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failures = []
    for passage in args.passage_dirs:
        passage_dir = args.root / passage
        source_model = passage_dir / args.source_model_dir
        source = source_model / args.source_method
        output = passage_dir / args.output_model_dir
        try:
            if not (source / "passage_target.txt").is_file():
                raise grammar.GrammarError(f"Missing clean source: {source / 'passage_target.txt'}")
            if args.reuse_cache_model_dir:
                previous = passage_dir / args.reuse_cache_model_dir
                if previous.resolve() == output.resolve():
                    raise grammar.GrammarError("Use a separate output directory from --reuse-cache-model-dir.")
                reuse_caches(previous / "_grammar_bank", output / "_grammar_bank")
            seed = args.seed + grammar.seed_offset(passage)
            banks = grammar.prepare_grammar_banks(
                source, output, seed=seed, bank_rate=max(positive),
                model=args.judge_model, generator_model=args.generator_model,
                max_candidates=args.max_candidates_per_clause,
                proposal_batch_size=args.proposal_batch_size, offline=args.offline,
                min_approved_candidates=args.target_candidates,
                retry_rounds=args.retry_rounds,
            )
            plans = {}
            report = {
                "schema_version": 1, "selection_method": "planned_nested_subsets_v1",
                "target_candidates": args.target_candidates,
                "coverage_tolerance_pp": args.coverage_tolerance_pp,
                "requested_rates": rates, "files": {},
            }
            for filename, bank in banks.items():
                if len(bank["entries"]) < args.target_candidates:
                    raise grammar.GrammarError(
                        f"{filename}: approved {len(bank['entries'])}/{args.target_candidates} "
                        "requested clauses after trying all eligible clauses. Caches and bank saved; "
                        "no variants exported. A larger target cannot create new eligible clauses."
                    )
                plans[filename] = plan_nested_selections(bank, rates, tolerance_pp=args.coverage_tolerance_pp)
                doses = []
                for rate in rates:
                    indices = plans[filename][rate]
                    affected = sum(bank["entries"][i]["content_chars"] for i in indices)
                    actual = affected / bank["total_content_chars"]
                    doses.append({
                        "requested_rate": rate, "actual_affected_rate": actual,
                        "affected_content_chars": affected,
                        "coverage_error_percentage_points": 100 * (actual - rate),
                        "within_tolerance": abs(100 * (actual - rate)) <= args.coverage_tolerance_pp + 1e-9,
                        "selected_bank_indices": indices,
                        "selected_unit_indices": [bank["entries"][i]["unit_index"] for i in indices],
                    })
                    print(f"{passage} {filename}: {rate:.0%} -> {actual:.2%}, {len(indices)} approved edits")
                report["files"][filename] = {
                    "bank_id": bank["bank_id"], "approved_candidate_count": len(bank["entries"]),
                    "pool_coverage": bank["actual_affected_rate"], "doses": doses,
                }
            # Plan every source file before publishing any condition.
            grammar.copy_shared_files(source_model / "_shared", output / "_shared")
            if 0 in rates:
                grammar.create_clean_copy(source, output, args.force)
            for rate in positive:
                grammar.create_variant(
                    source_method_dir=source, output_dir=output, rate=rate, seed=seed,
                    force=args.force, banks=banks,
                    selections={filename: plan[rate] for filename, plan in plans.items()},
                )
            grammar.write_json_atomic(output / "dose_selection.json", report)
        except (grammar.GrammarError, ValueError, OSError) as exc:
            print(f"error: {passage}: {exc}", file=sys.stderr)
            failures.append(passage)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
