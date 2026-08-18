#!/usr/bin/env python3
"""Build the tier-1 pilot partition: boundary-aligned tiles cut into 8 condition cells.

The design this implements
--------------------------
The human pilot's unit of assignment stops being "one chapter" and becomes "one
contiguous run of verse tiles". All 10 tier-1 passages are laid end to end, tiled into
disjoint ~3-verse windows, and cut into 8 contiguous cells -- so a cell looks like
"the rest of passage 1 + the first tiles of passage 2". The partition is FIXED: every
participant gets the same 8 cells, and the Latin square only rotates which condition
each cell is delivered under.

Two properties this buys, both of which the per-chapter design lacked:

  * **Each window is read exactly once, under exactly one condition.** No participant
    ever sees the same verses clean and then degraded, so there is no memory carryover
    to attenuate the defect effect toward null.
  * **Weaker testlet clustering.** A cell spans passage boundaries, so its items no
    longer all sit inside one passage-level randomization unit -- which is the design
    effect logged on 2026-08-03 (SEs ~1.8x too narrow at m~44, rho=0.05).

Why tiles are not a fixed [0-2][3-5] grid
-----------------------------------------
A naive fixed grid splits 9 of the 110 items' required spans across a tile boundary
(e.g. ``t1_2sam21:gphm`` needs ordinals 5-7, ``t1_1kgs13:o8ae`` needs 32-33). A split
span means the delivered window cannot contain the whole answer, so the item is
unanswerable in EVERY condition. That is indistinguishable from an omission having
deleted the answer clause: it depresses accuracy uniformly, reads as a floor effect,
and biases the dose-response slope. Excluding those items would instead throw away 8%
of an already small pool.

So tile cuts are placed by DP instead: a cut is legal only where it splits no required
span, and among legal tilings we take the one closest to uniform 3-verse tiles. Max
required span in the tier-1 set is 3 verses, so a 3-verse minimum tile is always
feasible.

Outputs
-------
``tier1_pilot_partition.json``:
  * ``tiles``   -- per passage, the chosen cut points and each tile's verse ordinals
  * ``cells``   -- the 8 cells, each a list of tiles and the item ids they carry
  * ``items``   -- item id -> (passage, tile index, cell index)
  * ``report``  -- counts, per-cell item totals, and any items that had to be dropped

Usage (from repo root):
  python scripts/build_tier1_pilot_partition.py \
      --windows ../qa_generation/fixtures/tier1_qa_verse_windows.json \
      --out evaluation/datasets/tier1_pilot_partition.json
  python scripts/build_tier1_pilot_partition.py --self-test
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Passage order for the end-to-end layout. Mirrors
# evaluation/datasets/obscure_narrative_passages_tier1.csv so cells are reproducible
# and human-checkable against the source list.
PASSAGE_ORDER = [
    "t1_judg9",
    "t1_judg17_18",
    "t1_1kgs13",
    "t1_2kgs6_7",
    "t1_2kgs11",
    "t1_2chr26",
    "t1_2sam21",
    "t1_acts19",
    "t1_acts20",
    "t1_acts23",
]

TARGET_TILE = 3
MIN_TILE = 3          # must be >= the longest required span (3 in the tier-1 set)
MAX_TILE = 5
N_CELLS = 8


class PartitionError(RuntimeError):
    pass


# ------------------------------------------------------------------ window map


def load_windows(path: Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
        raise PartitionError(f"{path}: no window list found")
    return data


def required_ordinals(record) -> list:
    """Passage ordinals the item's answer actually needs.

    ``window_ordinals`` is the 3-verse window the item was assigned;
    ``answer_position_in_window`` indexes into it, so the required span starts there
    and runs ``required_span_length`` verses.
    """
    window = record["window_ordinals"]
    position = record.get("answer_position_in_window")
    length = max(1, int(record.get("required_span_length") or 1))
    if position is None or position >= len(window):
        return [window[0]]
    start = window[position]
    return list(range(start, start + length))


# ------------------------------------------------------------------ DP tiler


def legal_cuts(n_verses: int, spans: list) -> set:
    """Cut positions that split no required span.

    A tile boundary at ``c`` means one tile ends before ordinal ``c`` and the next
    begins at ``c``. A span [s, e] is split iff s < c <= e.
    """
    forbidden = set()
    for span in spans:
        start, end = span[0], span[-1]
        forbidden.update(range(start + 1, end + 1))
    return {c for c in range(n_verses + 1) if c not in forbidden}


def tile_passage(n_verses: int, spans: list):
    """Return cut positions tiling [0, n_verses) without splitting any span.

    Exact DP: minimise sum of (tile_size - TARGET_TILE)^2 over legal cuts. Ties break
    toward earlier cuts so the result is deterministic.
    """
    if n_verses <= 0:
        raise PartitionError("passage has no verses")
    allowed = legal_cuts(n_verses, spans)
    if 0 not in allowed or n_verses not in allowed:
        raise PartitionError("passage start/end is not a legal cut")

    INF = float("inf")
    best = {0: (0.0, None)}
    for cut in sorted(allowed):
        if cut == 0:
            continue
        best_cost, best_prev = INF, None
        for size in range(MIN_TILE, MAX_TILE + 1):
            prev = cut - size
            if prev < 0 or prev not in best:
                continue
            # A short final tile is tolerated: the passage end is fixed, so the last
            # tile cannot always reach MIN_TILE. Everything else must.
            cost = best[prev][0] + (size - TARGET_TILE) ** 2
            if cost < best_cost:
                best_cost, best_prev = cost, prev
        if best_prev is not None:
            best[cut] = (best_cost, best_prev)

    if n_verses not in best:
        # Fall back: allow one short tile at the end (passages shorter than MIN_TILE,
        # or whose legal cuts do not admit a full tiling).
        return _tile_with_short_tail(n_verses, allowed)

    cuts, node = [n_verses], n_verses
    while node != 0:
        node = best[node][1]
        cuts.append(node)
    return sorted(cuts)


def _tile_with_short_tail(n_verses: int, allowed: set):
    """Greedy fallback that permits a final tile below MIN_TILE."""
    cuts = [0]
    position = 0
    while position < n_verses:
        candidates = [
            position + size
            for size in range(MIN_TILE, MAX_TILE + 1)
            if position + size <= n_verses and position + size in allowed
        ]
        if not candidates:
            if n_verses in allowed and n_verses > position:
                cuts.append(n_verses)
                break
            raise PartitionError(
                f"cannot tile passage of {n_verses} verses without splitting a span"
            )
        position = min(candidates, key=lambda c: abs((c - position) - TARGET_TILE))
        cuts.append(position)
    if cuts[-1] != n_verses:
        cuts.append(n_verses)
    return sorted(set(cuts))


# ------------------------------------------------------------------ partition


def build_partition(records, n_cells=N_CELLS):
    by_passage = defaultdict(list)
    for record in records:
        by_passage[record["passage_id"]].append(record)

    unknown = set(by_passage) - set(PASSAGE_ORDER)
    if unknown:
        raise PartitionError(f"passages missing from PASSAGE_ORDER: {sorted(unknown)}")

    tiles = []          # (passage_id, tile_index, [ordinals], [item ids])
    tile_report = {}
    for passage in PASSAGE_ORDER:
        rows = by_passage.get(passage)
        if not rows:
            continue
        n_verses = max(o for r in rows for o in r["window_ordinals"]) + 1
        spans = [required_ordinals(r) for r in rows]
        cuts = tile_passage(n_verses, spans)

        blocks = list(zip(cuts, cuts[1:]))
        placed = defaultdict(list)
        for record in rows:
            span = required_ordinals(record)
            index = next(
                (i for i, (a, b) in enumerate(blocks) if a <= span[0] and span[-1] < b),
                None,
            )
            if index is None:
                raise PartitionError(
                    f"{record.get('content_id')}: span {span} spans a tile boundary "
                    "after boundary-aligned tiling -- this should be impossible"
                )
            placed[index].append(record)

        for i, (a, b) in enumerate(blocks):
            tiles.append((passage, i, list(range(a, b)),
                          [r["content_id"] for r in placed.get(i, [])]))
        tile_report[passage] = {
            "verses": n_verses, "tiles": len(blocks), "cuts": cuts,
            "items": len(rows),
        }

    # Cut the tile sequence into contiguous cells, balanced on ITEM count (an empty
    # tile costs a participant nothing to read past, an item costs them an answer).
    total_items = sum(len(t[3]) for t in tiles)
    if total_items == 0:
        raise PartitionError("no items to partition")
    target = total_items / n_cells

    cells = [[] for _ in range(n_cells)]
    index, running = 0, 0
    for tile in tiles:
        if index < n_cells - 1 and running >= target * (index + 1) - 0.5:
            index += 1
        cells[index].append(tile)
        running += len(tile[3])

    return tiles, cells, tile_report, total_items


def verify(tiles, cells, records, total_items):
    """Assert the properties the design depends on. Returns a list of failures."""
    failures = []

    # 1. tiles within a passage are disjoint and contiguous
    by_passage = defaultdict(list)
    for passage, _i, ordinals, _items in tiles:
        by_passage[passage].extend(ordinals)
    for passage, ordinals in by_passage.items():
        if len(ordinals) != len(set(ordinals)):
            failures.append(f"{passage}: tiles overlap")
        if sorted(ordinals) != list(range(min(ordinals), max(ordinals) + 1)):
            failures.append(f"{passage}: tiles leave a gap")

    # 2. every item placed exactly once
    placed = [i for _p, _i, _o, items in tiles for i in items]
    if len(placed) != len(set(placed)):
        failures.append("an item was placed in more than one tile")
    if len(placed) != total_items:
        failures.append(f"placed {len(placed)} items, expected {total_items}")

    # 3. no required span crosses its tile
    spans = {r["content_id"]: required_ordinals(r) for r in records}
    for passage, _i, ordinals, items in tiles:
        for item in items:
            span = spans.get(item)
            if span and not set(span).issubset(ordinals):
                failures.append(f"{item}: required span {span} not inside its tile")

    # 4. each tile in exactly one cell -- the no-repeat-exposure property
    in_cells = [(t[0], t[1]) for cell in cells for t in cell]
    if len(in_cells) != len(set(in_cells)):
        failures.append("a tile appears in more than one cell")
    if len(in_cells) != len(tiles):
        failures.append("cells do not cover every tile")

    return failures


# ------------------------------------------------------------------ self-test


def self_test():
    checks = []

    def check(label, ok):
        checks.append((label, ok))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    # legal_cuts blocks exactly the interior of each span
    cuts = legal_cuts(10, [[2, 3, 4]])
    check("cuts inside a span are forbidden", {3, 4} & cuts == set())
    check("cut at span start is legal", 2 in cuts)
    check("cut just after span end is legal", 5 in cuts)

    # a span sitting across the naive grid boundary is respected
    cuts = tile_passage(9, [[2, 3]])
    blocks = list(zip(cuts, cuts[1:]))
    check("boundary-crossing span kept inside one tile",
          any(a <= 2 and 3 < b for a, b in blocks))

    # tiling covers the passage exactly, with no gaps or overlaps
    check("tiling starts at 0 and ends at n", cuts[0] == 0 and cuts[-1] == 9)
    check("all tiles >= MIN_TILE except possibly the last",
          all(b - a >= MIN_TILE for a, b in blocks[:-1]))

    # deterministic
    check("tiling is deterministic", tile_passage(9, [[2, 3]]) == cuts)

    # a passage with no spans still tiles uniformly
    cuts = tile_passage(12, [])
    check("unconstrained passage tiles into uniform 3s",
          [b - a for a, b in zip(cuts, cuts[1:])] == [3, 3, 3, 3])

    print()
    return 0 if all(ok for _l, ok in checks) else 1


# ------------------------------------------------------------------ main


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--windows", type=Path,
                    help="tier1_qa_verse_windows.json from qa_generation/fixtures")
    ap.add_argument("--out", type=Path, help="write the partition JSON here")
    ap.add_argument("--cells", type=int, default=N_CELLS)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("self-test:")
        return self_test()

    if not args.windows:
        ap.error("--windows is required (or use --self-test)")

    records = load_windows(args.windows)
    tiles, cells, tile_report, total_items = build_partition(records, args.cells)
    failures = verify(tiles, cells, records, total_items)

    naive_splits = sum(
        1 for r in records
        if (lambda s: s[0] // TARGET_TILE != s[-1] // TARGET_TILE)(required_ordinals(r))
    )

    print(f"{'passage':16} {'verses':>6} {'tiles':>5} {'items':>5}")
    print("-" * 36)
    for passage in PASSAGE_ORDER:
        info = tile_report.get(passage)
        if info:
            print(f"{passage:16} {info['verses']:>6} {info['tiles']:>5} {info['items']:>5}")
    print("-" * 36)
    print(f"{'TOTAL':16} {sum(i['verses'] for i in tile_report.values()):>6} "
          f"{len(tiles):>5} {total_items:>5}")

    print(f"\nrequired spans split by a NAIVE fixed grid: {naive_splits}")
    print(f"required spans split after boundary-aligned tiling: 0 (verified)")

    print(f"\n{'cell':>4} {'items':>5} {'tiles':>5}  passages spanned")
    print("-" * 64)
    for i, cell in enumerate(cells):
        names = []
        for tile in cell:
            if not names or names[-1] != tile[0]:
                names.append(tile[0])
        print(f"{i:>4} {sum(len(t[3]) for t in cell):>5} {len(cell):>5}  "
              f"{' + '.join(n.replace('t1_', '') for n in names)}")

    if failures:
        print("\nVERIFICATION FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nverified: tiles disjoint + contiguous, every item placed once, "
          "no split spans,every tile in exactly one cell")

    if args.out:
        payload = {
            "schema_version": 1,
            "n_cells": args.cells,
            "target_tile": TARGET_TILE,
            "passage_order": PASSAGE_ORDER,
            "tiles": [
                {"passage_id": p, "tile_index": i, "ordinals": o, "item_ids": items}
                for p, i, o, items in tiles
            ],
            "cells": [
                {
                    "cell_index": i,
                    "tiles": [{"passage_id": t[0], "tile_index": t[1]} for t in cell],
                    "item_ids": [x for t in cell for x in t[3]],
                }
                for i, cell in enumerate(cells)
            ],
            "report": {
                "total_items": total_items,
                "total_tiles": len(tiles),
                "naive_grid_splits": naive_splits,
                "per_passage": tile_report,
            },
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
