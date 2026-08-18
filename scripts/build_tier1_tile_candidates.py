#!/usr/bin/env python3
"""Group tier-1 QA candidates by disjoint tile, ready for a tile-granularity selection pass.

Why this exists
---------------
The existing ``pilot_window_selection`` verdicts were made at **exact-window**
granularity: two questions competed only if their 3-verse windows were byte-identical.
That rule leaves the pilot with items whose windows merely *overlap* -- 66% of the
surviving 78 share verses with another surviving item -- so the local-independence
problem it was meant to solve is still there.

The pilot design now uses **disjoint tiles** (``build_tier1_pilot_partition.py``), where
each tile is a ~3-verse block placed so no item's required span is split. One question
per tile gives genuine independence: no two delivered items share a verse.

This script re-groups the candidates at that granularity so the selection can be redone
against the right unit. It does NOT choose -- it only says which questions are competing
for which tile, and which of them still need a score.

What it resets, and what it keeps
---------------------------------
* **Rank-based window removals are RESET to candidates.** A question that lost its
  exact-window contest may be the strongest question available in its *tile* -- the two
  groupings do not nest, so the old verdict does not transfer. Prior verdicts are
  preserved on each candidate as ``prior_window_verdict`` for audit, not applied.
* **Exact-duplicate removals are KEPT.** ``t1_2chr26:rxf3#2`` and ``t1_acts20:jxkk#2``
  are the second copies of the content_id collision fixed on 2026-08-04. Duplicates are
  duplicates at any granularity.
* **The null stub is marked undeliverable.** ``t1_judg9:o93q`` carries a content_id and
  ``reference 9:54`` but null ``id``/``passage_id``/``question`` -- the defect logged on
  2026-08-03. It cannot be delivered, so it must not win a tile by default.
* **Items absent from the 90-record all_formats file are included but flagged.** Ten
  items exist in the window map but not in ``tier1_all_formats.json``, and they are the
  sole occupants of ten tiles that are otherwise barren. Whether that upstream drop was
  deliberate is unresolved, so they are surfaced rather than silently kept or dropped.

Output ``tier1_tile_candidates.json``: one entry per occupied tile, its candidates, the
metrics each already has, and ``needs_scoring`` for those that never competed.

Usage (from repo root):
  python scripts/build_tier1_tile_candidates.py \
      --partition evaluation/datasets/tier1_pilot_partition.json \
      --all-formats evaluation/datasets/qa/tier1_QAs_easy/tier1_all_formats.json \
      --shortened evaluation/datasets/tier1_shortened.json \
      --out evaluation/datasets/tier1_tile_candidates.json
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Removals that survive re-grouping: genuine duplicate records, not contest losers.
DUPLICATE_REASONS = {"exact_duplicate_later_copy"}


def _records(path: Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for value in data.values():
        if isinstance(value, list):
            return value
    raise SystemExit(f"{path}: no record list found")


def _is_deliverable(record) -> bool:
    """A record needs question text and an answer to be shown to anyone."""
    if not record:
        return False
    question = record.get("question") or record.get("original_question")
    answer = record.get("answer") or record.get("original_answer") or record.get("A")
    return bool(str(question or "").strip()) and bool(answer)


def build(partition, all_formats, shortened):
    by_cid_af = {r.get("content_id"): r for r in all_formats}
    by_cid_sh = {r.get("content_id"): r for r in shortened}

    dropped_duplicates = {
        r["content_id"] for r in all_formats
        if (r.get("pilot_window_selection") or {}).get("reason") in DUPLICATE_REASONS
    }

    tiles_out = []
    stats = Counter()
    for tile in partition["tiles"]:
        candidates = []
        for content_id in tile["item_ids"]:
            if content_id in dropped_duplicates:
                stats["skipped_duplicate"] += 1
                continue

            af = by_cid_af.get(content_id)
            sh = by_cid_sh.get(content_id)
            source = af or sh
            selection = (af or {}).get("pilot_window_selection") or {}
            metrics = selection.get("metrics") or None
            deliverable = _is_deliverable(af) or _is_deliverable(sh)

            candidates.append({
                "content_id": content_id,
                "question": (source or {}).get("question")
                            or (source or {}).get("original_question"),
                "reference": (source or {}).get("reference"),
                "deliverable": deliverable,
                "in_all_formats": af is not None,
                # Recorded for audit. NOT applied -- window verdicts do not
                # transfer to tiles, because the two groupings do not nest.
                "prior_window_verdict": selection.get("status"),
                "prior_window_reason": selection.get("reason"),
                "metrics": metrics,
                "needs_scoring": metrics is None and deliverable,
            })
            if not deliverable:
                stats["undeliverable"] += 1
            elif af is None:
                stats["absent_from_all_formats"] += 1
            if metrics is None and deliverable:
                stats["needs_scoring"] += 1

        usable = [c for c in candidates if c["deliverable"]]
        if not usable:
            stats["barren_tiles"] += 1
            continue

        stats["occupied_tiles"] += 1
        stats["contested_tiles" if len(usable) > 1 else "auto_selected_tiles"] += 1
        tiles_out.append({
            "passage_id": tile["passage_id"],
            "tile_index": tile["tile_index"],
            "ordinals": tile["ordinals"],
            "n_candidates": len(usable),
            "contested": len(usable) > 1,
            "candidates": candidates,
        })

    return tiles_out, stats


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partition", type=Path, required=True)
    ap.add_argument("--all-formats", type=Path, required=True)
    ap.add_argument("--shortened", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    partition = json.loads(args.partition.read_text(encoding="utf-8"))
    tiles, stats = build(partition,
                         _records(args.all_formats),
                         _records(args.shortened))

    total_tiles = len(partition["tiles"])
    print(f"tiles in partition            : {total_tiles}")
    print(f"  occupied (>=1 usable item)  : {stats['occupied_tiles']}")
    print(f"    auto-selected (1 item)    : {stats['auto_selected_tiles']}")
    print(f"    CONTESTED (needs ranking) : {stats['contested_tiles']}")
    print(f"  barren                      : {stats['barren_tiles']}")
    print()
    print(f"items needing a score         : {stats['needs_scoring']}")
    print(f"items absent from all_formats : {stats['absent_from_all_formats']}")
    print(f"undeliverable (null stub etc.): {stats['undeliverable']}")
    print(f"duplicates excluded outright  : {stats['skipped_duplicate']}")

    contested = [t for t in tiles if t["contested"]]
    print(f"\ncontested tiles ({len(contested)}):")
    for tile in contested:
        names = ", ".join(
            f"{c['content_id'].split(':')[-1]}"
            f"{'' if c['metrics'] else '*'}"
            for c in tile["candidates"] if c["deliverable"]
        )
        print(f"  {tile['passage_id']:14} tile {tile['tile_index']:>2} "
              f"verses {tile['ordinals']}: {names}")
    print("  (* = no score yet)")

    if args.out:
        payload = {
            "schema_version": 1,
            "granularity": "disjoint_tile",
            "note": "window-level rank verdicts reset; duplicates kept removed",
            "summary": dict(stats),
            "tiles": tiles,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
