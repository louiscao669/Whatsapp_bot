#!/usr/bin/env python3
"""Refresh Tier-1 defect variants with the QA set from their clean base cell.

This intentionally leaves each perturbed passage and its defect metadata
unchanged.  Use it when the clean QA selection changes but the shared passage
translation (and therefore the already-built perturbations) does not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


PASSAGES = (
    "t1_judg9",
    "t1_judg17_18",
    "t1_2kgs6_7",
    "t1_1kgs13",
    "t1_2kgs11",
    "t1_2chr26",
    "t1_2sam21",
    "t1_acts19",
    "t1_acts20",
    "t1_acts23",
)
DEFECTS = (
    "omission",
    "mistranslation",
    "grammar",
    "awkward",
    "addition",
    "inconsistency",
)
QA_FILES = ("qa_target.json", "qa_target_decanonicalized.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_items(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise RuntimeError(f"Expected a JSON array: {path}")
    return value


def item_ids(items: list[dict]) -> list[str]:
    return [str(item.get("passage_id") or item.get("id") or "") for item in items]


def atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".refresh-tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy the clean-base QA artifacts into every nonzero Tier-1 defect "
            "variant without regenerating the perturbed passages."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("evaluation/outputs/tier1_bsb"),
    )
    parser.add_argument("--method", default="llm_prompt_high")
    parser.add_argument("--passages", nargs="*", choices=PASSAGES, default=PASSAGES)
    parser.add_argument("--defects", nargs="*", choices=DEFECTS, default=DEFECTS)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag the command is a dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    planned: list[tuple[Path, Path]] = []
    variants: list[tuple[Path, list[str]]] = []
    already_current = 0
    shared_files = 0

    for passage in args.passages:
        passage_root = args.root / passage
        base_method = passage_root / "_base" / args.method
        base_shared = passage_root / "_base" / "_shared"
        base_ids: dict[str, list[str]] = {}
        for filename in QA_FILES:
            source = base_method / filename
            if not source.is_file():
                raise RuntimeError(f"Missing clean-base QA artifact: {source}")
            ids = item_ids(read_items(source))
            if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
                raise RuntimeError(f"Missing or duplicate item IDs in {source}")
            base_ids[filename] = ids
        if base_ids[QA_FILES[0]] != base_ids[QA_FILES[1]]:
            raise RuntimeError(f"Clean-base QA artifacts disagree for {passage}")

        for defect in args.defects:
            defect_root = passage_root / defect
            if not defect_root.is_dir():
                raise RuntimeError(f"Missing defect directory: {defect_root}")

            defect_shared = defect_root / "_shared"
            for source in base_shared.glob("*_qa_zh*.json"):
                destination = defect_shared / source.name
                if not destination.is_file() or digest(source) != digest(destination):
                    planned.append((source, destination))
                    shared_files += 1

            for variant in sorted(defect_root.iterdir()):
                if (
                    not variant.is_dir()
                    or variant.name.startswith("_")
                    or variant.name == "0%"
                ):
                    continue
                if not (variant / "passage_target_decanonicalized.txt").is_file():
                    raise RuntimeError(f"Incomplete defect variant: {variant}")
                variants.append((variant, base_ids[QA_FILES[0]]))
                current = True
                for filename in QA_FILES:
                    source = base_method / filename
                    destination = variant / filename
                    if not destination.is_file() or digest(source) != digest(destination):
                        current = False
                        planned.append((source, destination))
                if current:
                    already_current += 1

    print(
        f"validated {len(variants)} nonzero variant(s): "
        f"{already_current} already current, "
        f"{len(variants) - already_current} need QA refresh"
    )
    print(f"planned file copies: {len(planned)} ({shared_files} shared-cache file(s))")
    if not args.apply:
        print("dry run: no files written")
        return

    for source, destination in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_copy(source, destination)

    errors: list[str] = []
    for variant, expected_ids in variants:
        for filename in QA_FILES:
            path = variant / filename
            if item_ids(read_items(path)) != expected_ids:
                errors.append(str(path))
    if errors:
        raise RuntimeError(
            "QA ID/order verification failed after refresh:\n" + "\n".join(errors)
        )
    print(f"refreshed and verified {len(variants)} nonzero variant(s)")


if __name__ == "__main__":
    main()
