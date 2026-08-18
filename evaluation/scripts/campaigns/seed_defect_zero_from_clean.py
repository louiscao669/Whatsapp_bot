#!/usr/bin/env python3
"""Reuse the clean llm_prompt_high scores as each defect family's 0% anchor.

Every <defect>/0% cell is `create_clean_copy` of the base translation, and each
model's llm_prompt_high cell was seeded from that same base. So the two are the
identical condition -- same passage, same QA, same model -- and re-answering 0%
once per defect family would spend six runs per passage per model reproducing
one number.

This copies the existing answers and scores across instead, but ONLY after
verifying that the passage and QA are byte-identical. If they differ at all the
cell is refused, because then it is not the same condition and the numbers are
not transferable.

It also writes `_anchor_provenance.json` into each seeded cell. That matters for
analysis: the six 0% cells of one passage/model are now ONE observation reused
six times, not six independent replicates. Anything estimating error bars across
defect families has to know that, or it will treat perfectly correlated copies
as independent and understate the variance.

Usage (from repo root):

    python evaluation/scripts/campaigns/seed_defect_zero_from_clean.py          # report
    python evaluation/scripts/campaigns/seed_defect_zero_from_clean.py --write
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
from datetime import date
from pathlib import Path

DEFAULT_ROOT = Path("evaluation/outputs/tier1")
DEFAULT_DEFECTS = ("omission", "mistranslation", "grammar", "awkward",
                   "addition", "inconsistency")
DEFAULT_MODELS = ("llama321b", "qwen2515b", "qwen317b")
CLEAN_METHOD = "llm_prompt_high"

# Must match for the reuse to be valid.
IDENTITY_FILES = ("passage_target_decanonicalized.txt", "qa_target_decanonicalized.json")
# Cell-defining artifacts, copied from the variant.
ARTIFACTS = ("passage_source_decanonicalized.txt", "passage_target.txt",
             "passage_target_decanonicalized.txt", "passage_translation.json",
             "qa_target.json", "qa_target_decanonicalized.json")
# Results, copied from the clean cell.
RESULTS = ("generated_answers_target_llama.json",
           "generated_answers_target_llama_backtranslated.json",
           "scores_target_llama.json")


def identical(a: Path, b: Path) -> bool:
    return a.exists() and b.exists() and filecmp.cmp(a, b, shallow=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--defects", nargs="+", default=list(DEFAULT_DEFECTS))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    seeded = refused = skipped = 0
    for passage_dir in sorted(p for p in args.root.iterdir() if p.is_dir()):
        pid = passage_dir.name
        for model in args.models:
            clean = passage_dir / model / CLEAN_METHOD
            if not (clean / "scores_target_llama.json").exists():
                continue
            for defect in args.defects:
                variant = passage_dir / defect / "0%"
                if not (variant / "passage_target_decanonicalized.txt").exists():
                    skipped += 1
                    continue
                dst = passage_dir / model / defect / "0%"
                if (dst / "scores_target_llama.json").exists():
                    skipped += 1
                    continue

                mismatch = [f for f in IDENTITY_FILES
                            if not identical(variant / f, clean / f)]
                if mismatch:
                    print(f"  REFUSE {pid}/{model}/{defect}/0%: differs in "
                          f"{', '.join(mismatch)}", file=sys.stderr)
                    refused += 1
                    continue

                print(f"  seed   {pid}/{model}/{defect}/0%  <- {model}/{CLEAN_METHOD}")
                seeded += 1
                if not args.write:
                    continue
                dst.mkdir(parents=True, exist_ok=True)
                for name in ARTIFACTS:
                    if (variant / name).exists():
                        shutil.copy2(variant / name, dst / name)
                for name in RESULTS:
                    if (clean / name).exists():
                        shutil.copy2(clean / name, dst / name)
                (dst / "_anchor_provenance.json").write_text(json.dumps({
                    "date": date.today().isoformat(),
                    "results_copied_from": str(clean),
                    "artifacts_copied_from": str(variant),
                    "independently_answered": False,
                    "note": ("Same condition as the clean cell: passage and QA verified "
                             "byte-identical. The 0% anchors of every defect family for "
                             "this passage/model are copies of ONE run, not independent "
                             "replicates -- do not treat them as such when estimating "
                             "error."),
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{seeded} cell(s) seeded, {refused} refused, {skipped} skipped"
          + ("" if args.write else "   (report only; re-run with --write)"))
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
