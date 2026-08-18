#!/usr/bin/env python3
"""Score translations with CometKiwi (reference-free COMET quality estimation).

Independent adequacy metric for the burden/MQM bridge program (alternative-B
check): per verse, src = the cell's source passage when available
(passage_source_decanonicalized.txt, so canonicalized cells stay in the same
placeholder space as their target), and mt = the cell's Chinese translation
(passage_target.txt). No reference needed.

Two scoring modes:
  methods (default)   the 8-method x 8-chapter grid that Delta/B/MQM live on
  --scan-defects      additionally score defect-variant cells
                      (luke{c}/<model-dir>/<family>/<level>/passage_target.txt)
                      as the metric's certification set: expect monotonic dose
                      response for omission/mistranslation, flat-ish for
                      grammar/awkward.

Outputs (under --out-dir):
  cometkiwi_segments.csv   one row per scored verse
  cometkiwi_cells.csv      one row per cell (mean score, coverage)

Requires: pip install unbabel-comet
  plus accepting the license of Unbabel/wmt22-cometkiwi-da on Hugging Face
  and `huggingface-cli login` before first download.

Usage:
  python evaluation/scripts/scoring/cometkiwi_score_translations.py --chapters 1 2 3 4 5 6 7 8
  python evaluation/scripts/scoring/cometkiwi_score_translations.py --chapters 1 --scan-defects
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.scoring.mqm_score_translations import (  # noqa: E402
    parse_verse_blocks,
    target_block_index,
)

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

FOOTNOTE_PATTERN = re.compile(r"\[\w+\]")
LEADING_VERSE_PATTERN = re.compile(r"^\d{1,3}\s*")


def clean_segment(text: str) -> str:
    text = LEADING_VERSE_PATTERN.sub("", text.strip())
    return FOOTNOTE_PATTERN.sub("", text).strip()


def source_verse_index(source_path: Path) -> dict[int, str]:
    text = source_path.read_text(encoding="utf-8")
    index = {}
    for block in parse_verse_blocks(text):
        if isinstance(block.get("verse"), int):
            index[block["verse"]] = clean_segment(block["text"])
    return index


def collect_cells(args: argparse.Namespace) -> list[dict]:
    """Each cell: chapter, kind, method, level, target_path."""
    cells = []
    for chapter in args.chapters:
        base = args.root / f"luke{chapter}" / args.model_dir
        for method in args.methods:
            cell_dir = base / method
            cells.append({
                "chapter": chapter, "kind": "method", "method": method,
                "level": "",
                "source_path": cell_dir / args.source_file,
                "target_path": cell_dir / args.translation_file,
            })
        if args.scan_defects and base.exists():
            method_set = set(args.methods)
            for family_dir in sorted(p for p in base.iterdir() if p.is_dir()):
                if family_dir.name in method_set or family_dir.name.startswith("_"):
                    continue
                for level_dir in sorted(p for p in family_dir.iterdir() if p.is_dir()):
                    target = level_dir / args.translation_file
                    if target.exists():
                        cells.append({
                            "chapter": chapter, "kind": "defect",
                            "method": family_dir.name, "level": level_dir.name,
                            "source_path": level_dir / args.source_file,
                            "target_path": target,
                        })
    return cells


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--model-dir", default="1.7b")
    parser.add_argument("--methods", nargs="+", default=DEFAULT_METHODS)
    parser.add_argument("--source-file", default="passage_source_decanonicalized.txt")
    parser.add_argument("--translation-file", default="passage_target.txt")
    parser.add_argument(
        "--source-template", default="evaluation/datasets/passages/test_passage_luke{chapter}.txt")
    parser.add_argument("--scan-defects", action="store_true",
                        help="Also score defect-variant cells (certification set).")
    parser.add_argument("--comet-model", default="Unbabel/wmt22-cometkiwi-da")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--gpus", type=int, default=0, help="0 = CPU (works fine).")
    parser.add_argument(
        "--num-workers",
        type=int,
        default=1,
        help="DataLoader workers for COMET predict. Use 1+ with current torch/comet.",
    )
    parser.add_argument("--out-dir", type=Path,
                        default=Path("evaluation/outputs/reports/cometkiwi"))
    parser.add_argument("--tag", default="",
                        help="Suffix for output filenames, e.g. 'defects_luke1'.")
    args = parser.parse_args()

    try:
        from comet import download_model, load_from_checkpoint
    except ImportError:
        print("error: pip install unbabel-comet (then accept the model license on "
              "Hugging Face and run `huggingface-cli login`)", file=sys.stderr)
        return 1

    # ---- build segment list -------------------------------------------------
    fallback_sources = {
        c: source_verse_index(Path(args.source_template.format(chapter=c)))
        for c in args.chapters
    }
    cells = collect_cells(args)
    segments, seg_meta, cell_rows = [], [], []
    for cell in cells:
        if cell["source_path"].exists():
            src_index = source_verse_index(cell["source_path"])
        else:
            src_index = fallback_sources[cell["chapter"]]
        if not cell["target_path"].exists():
            print(f"warning: missing {cell['target_path']}", file=sys.stderr)
            continue
        tgt_index = target_block_index(cell["target_path"].read_text(encoding="utf-8"))
        matched = missing = 0
        for verse, src_text in sorted(src_index.items()):
            mt_text = clean_segment(tgt_index.get(verse, ""))
            if not mt_text:
                missing += 1
                continue
            segments.append({"src": src_text, "mt": mt_text})
            seg_meta.append({**{k: cell[k] for k in ("chapter", "kind", "method", "level")},
                             "verse": verse})
            matched += 1
        cell_rows.append({**{k: cell[k] for k in ("chapter", "kind", "method", "level")},
                          "n_scored": matched, "n_missing_target_verses": missing})
    print(f"cells: {len(cell_rows)}   segments: {len(segments)}")
    if not segments:
        print("error: nothing to score", file=sys.stderr)
        return 1

    # ---- score --------------------------------------------------------------
    model = load_from_checkpoint(download_model(args.comet_model))
    output = model.predict(
        segments,
        batch_size=args.batch_size,
        gpus=args.gpus,
        num_workers=args.num_workers,
    )
    scores = list(output.scores)
    assert len(scores) == len(seg_meta)

    # ---- write --------------------------------------------------------------
    args.out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"_{args.tag}" if args.tag else ""
    seg_path = args.out_dir / f"cometkiwi_segments{tag}.csv"
    with seg_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["chapter", "kind", "method", "level", "verse",
                            "cometkiwi", "src", "mt"])
        writer.writeheader()
        for meta, seg, score in zip(seg_meta, segments, scores):
            writer.writerow({**meta, "cometkiwi": f"{score:.6f}", **seg})

    by_cell: dict[tuple, list[float]] = {}
    for meta, score in zip(seg_meta, scores):
        key = (meta["chapter"], meta["kind"], meta["method"], meta["level"])
        by_cell.setdefault(key, []).append(score)
    cells_path = args.out_dir / f"cometkiwi_cells{tag}.csv"
    with cells_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["chapter", "kind", "method", "level", "cometkiwi_mean",
                            "cometkiwi_min", "n_scored", "n_missing_target_verses"])
        writer.writeheader()
        for row in cell_rows:
            key = (row["chapter"], row["kind"], row["method"], row["level"])
            vals = by_cell.get(key, [])
            writer.writerow({
                "chapter": row["chapter"], "kind": row["kind"],
                "method": row["method"], "level": row["level"],
                "cometkiwi_mean": f"{sum(vals)/len(vals):.6f}" if vals else "",
                "cometkiwi_min": f"{min(vals):.6f}" if vals else "",
                "n_scored": row["n_scored"],
                "n_missing_target_verses": row["n_missing_target_verses"],
            })

    print(f"wrote: {seg_path}")
    print(f"wrote: {cells_path}")

    # quick method-level summary
    if any(r["kind"] == "method" for r in cell_rows):
        method_means: dict[str, list[float]] = {}
        for meta, score in zip(seg_meta, scores):
            if meta["kind"] == "method":
                method_means.setdefault(meta["method"], []).append(score)
        print("\nmethod means (all chapters):")
        for method, vals in sorted(method_means.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
            print(f"  {sum(vals)/len(vals):.4f}  {method}  (n={len(vals)})")
    return 0


if __name__ == "__main__":
    main()
