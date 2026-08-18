#!/usr/bin/env python3
"""Re-window tier-1 QAs so they stop overlapping, instead of deleting one of each pair.

The problem this replaces
-------------------------
Two QAs whose 3-verse windows overlap create a dependency: the same verses reach
one respondent twice, and if they land in different condition cells the earlier
read contaminates the later one. The existing pilot selection resolved that by
DELETING one of the pair -- which is only necessary when the two items need the
SAME verse.

When their required spans differ, the overlap is an accident of which window was
drawn, not a property of the questions. Both can be kept by moving one window.
95 of 110 items have more than one legal window (72 have three), so there is
usually room.

How it works
------------
A disjoint set of fixed-width windows is exactly a set of non-overlapping
intervals, so this is interval scheduling, not graph colouring. The legacy path
uses earliest-deadline-first scheduling. When ``--ranking`` is supplied, dynamic
programming first maximises how many questions receive a disjoint slot and then
uses the global QA ranking to resolve every equal-capacity overlap.

Two hard limits, both worth reading before trusting the output:

  * **Capacity.** A passage of n verses admits at most floor(n / 3) disjoint
    3-verse windows. t1_judg9 has 55 verses and 19 items, so 18 is the ceiling --
    at least one item cannot be placed no matter how clever the assignment.
  * **Shared answer verses.** Two items whose required spans intersect can never
    have disjoint windows, because both windows must contain the shared verse.
    These are the cases where deletion really is the only option, and they are
    reported separately so the two reasons are never conflated.

Usage (from repo root):
  python scripts/rewindow_tier1_disjoint.py \
      --windows ../qa_generation/fixtures/tier1_qa_verse_windows.json \
      --all-formats evaluation/datasets/qa/tier1_QAs_easy/tier1_all_formats.json \
      --out evaluation/datasets/tier1_disjoint_windows.json
  python scripts/rewindow_tier1_disjoint.py \
      --windows QA_algorithm/inputs/tier1_qa_verse_windows.json \
      --ranking evaluation/reports/tier1_question_ranking.json \
      --out evaluation/datasets/tier1_gold_72_selection.json \
      --gold-out evaluation/datasets/tier1_gold_72.json \
      --gold-missing-out evaluation/datasets/tier1_gold_72_missing.json
  python scripts/rewindow_tier1_disjoint.py --self-test
"""

import argparse
import bisect
import json
import sys
from collections import defaultdict
from pathlib import Path

WINDOW = 3


def _list_from(path: Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for value in data.values():
        if isinstance(value, list):
            return value
    raise SystemExit(f"{path}: no record list found")


def required_ordinals(record):
    """Ordinals the item's answer needs (window position + span length)."""
    window = record["window_ordinals"]
    position = record.get("answer_position_in_window")
    length = max(1, int(record.get("required_span_length") or 1))
    if position is None or position >= len(window):
        return [window[0]]
    start = window[position]
    return list(range(start, start + length))


def candidate_starts(span, n_verses, width=WINDOW):
    """Every legal window start whose window fully contains `span`.

    Enumerated from ordinals rather than parsing ``candidate_windows`` (which
    holds chapter:verse labels), so the two chapter-crossing passages -- flattened
    to passage ordinals -- need no special handling.
    """
    lo, hi = span[0], span[-1]
    if hi - lo + 1 > width:
        return []
    first = max(0, hi - width + 1)
    last = min(lo, n_verses - width)
    return list(range(first, last + 1)) if last >= first else []


def assign_disjoint(items, n_verses, width=WINDOW):
    """Earliest-deadline-first packing. Returns (assignment, unplaced).

    ``items`` is [(item_id, required_span)].

    Each item admits a contiguous range of starts [first_i, last_i], and
    disjointness means starts differ by at least `width`. That is unit-job
    scheduling with release times and deadlines, for which the optimal greedy
    sorts by DEADLINE (last_i, the latest start still containing the span) and
    takes the earliest feasible slot. Sorting by span END instead -- which is
    release time, not deadline -- is a different and non-optimal order; it
    coincides only for single-verse spans, which is why it looked fine at first.
    """
    def bounds(span):
        starts = candidate_starts(span, n_verses, width)
        return (starts[0], starts[-1]) if starts else (None, None)

    ordered = sorted(
        items,
        key=lambda it: (
            bounds(it[1])[1] if bounds(it[1])[1] is not None else 10**9,
            bounds(it[1])[0] if bounds(it[1])[0] is not None else 10**9,
            it[0],
        ),
    )
    assignment, unplaced = {}, []
    cursor = 0
    for item_id, span in ordered:
        first, last = bounds(span)
        if first is None:
            unplaced.append((item_id, span))
            continue
        start = max(first, cursor)
        if start > last:
            unplaced.append((item_id, span))
            continue
        assignment[item_id] = list(range(start, start + width))
        cursor = start + width
    return assignment, unplaced


def assign_disjoint_ranked(items, n_verses, rank_by_item, width=WINDOW):
    """Maximum-cardinality schedule, using global QA rank as the tie-break.

    Every legal window for an item is an interval option. Options belonging to
    the same item necessarily overlap (all contain that item's required span),
    so ordinary weighted interval scheduling can never select an item twice.
    The objective is lexicographic:

      1. retain as many questions as possible;
      2. among equal-size schedules, prefer the sorted list of better ranks;
      3. break exact ties deterministically by content id and window start.

    Unranked questions sort after every ranked question, but remain eligible
    when they are needed to preserve maximum capacity.
    """
    unranked = max(rank_by_item.values(), default=0) + len(items) + 1
    options = []
    for item_id, span in items:
        for start in candidate_starts(span, n_verses, width):
            options.append({
                "item_id": item_id,
                "start": start,
                "end": start + width,
                "rank": rank_by_item.get(item_id, unranked),
            })
    options.sort(key=lambda row: (
        row["end"], row["start"], row["rank"], row["item_id"]
    ))
    ends = [row["end"] for row in options]

    def preference(schedule):
        ranks = sorted(row["rank"] for row in schedule)
        return len(schedule), tuple(-rank for rank in ranks)

    def better(left, right):
        left_key, right_key = preference(left), preference(right)
        if left_key != right_key:
            return left if left_key > right_key else right
        left_tie = tuple(sorted((row["item_id"], row["start"]) for row in left))
        right_tie = tuple(sorted((row["item_id"], row["start"]) for row in right))
        return left if left_tie <= right_tie else right

    # dp[k] is the best schedule using options[:k].
    dp = [tuple()]
    for index, option in enumerate(options):
        previous = bisect.bisect_right(ends, option["start"], hi=index) - 1
        include = dp[previous + 1] + (option,)
        exclude = dp[index]
        dp.append(better(include, exclude))

    assignment = {
        row["item_id"]: list(range(row["start"], row["end"]))
        for row in dp[-1]
    }
    unplaced = [(item_id, span) for item_id, span in items if item_id not in assignment]
    return assignment, unplaced


def load_question_ranking(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"ranking has no question list: {path}")
    out = {}
    for row in rows:
        content_id = row.get("content_id") or str(row.get("base_id") or "").removeprefix("uw-")
        if content_id and row.get("rank") is not None:
            out[content_id] = int(row["rank"])
    return out


def forced_conflicts(items):
    """Pairs that can never be disjoint: their required spans intersect."""
    out = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if set(items[i][1]) & set(items[j][1]):
                out.append((items[i][0], items[j][0]))
    return out


def overlap_pairs(assignment):
    out = []
    keys = sorted(assignment)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if set(assignment[keys[i]]) & set(assignment[keys[j]]):
                out.append((keys[i], keys[j]))
    return out


def self_test():
    checks = []

    def check(label, ok):
        checks.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    # two items, different answer verses, windows currently overlapping
    items = [("a", [1]), ("b", [4])]
    assign, unplaced = assign_disjoint(items, 9)
    check("both placed when answer verses differ", len(assign) == 2 and not unplaced)
    check("and the windows are disjoint", not overlap_pairs(assign))

    # same answer verse -> impossible
    items = [("a", [4]), ("b", [4])]
    assign, unplaced = assign_disjoint(items, 9)
    check("same answer verse cannot both be placed", len(unplaced) == 1)
    check("forced conflict detected", forced_conflicts(items) == [("a", "b")])

    # capacity ceiling
    items = [(str(i), [i]) for i in range(5)]
    assign, unplaced = assign_disjoint(items, 6)   # floor(6/3) = 2 slots
    check("capacity ceiling respected", len(assign) <= 2)

    # adjacent spans one verse apart are separable in a long passage
    items = [("a", [0]), ("b", [3]), ("c", [6])]
    assign, unplaced = assign_disjoint(items, 12)
    check("three spaced items all placed", len(assign) == 3 and not overlap_pairs(assign))

    # a span wider than the window is unplaceable
    check("over-wide span yields no candidates", candidate_starts([0, 1, 2, 3], 12) == [])

    # Rank resolves a genuine overlap without changing capacity.
    items = [("lower", [2]), ("higher", [2])]
    assign, unplaced = assign_disjoint_ranked(
        items, 6, {"lower": 20, "higher": 2}
    )
    check("ranking chooses the better QA in an unavoidable overlap",
          set(assign) == {"higher"})

    # Cardinality remains primary: one excellent blocker cannot replace two
    # lower-ranked questions that fit on either side of it.
    items = [("best", [2, 3]), ("left", [0]), ("right", [5])]
    assign, unplaced = assign_disjoint_ranked(
        items, 6, {"best": 1, "left": 80, "right": 90}
    )
    check("maximum question count remains above ranking preference",
          set(assign) == {"left", "right"})
    print()
    return 0 if all(checks) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--windows", type=Path)
    ap.add_argument("--all-formats", type=Path,
                    help="restrict to the QAs in this file (the 90-record set)")
    ap.add_argument("--ranking", type=Path,
                    help="global question-ranking JSON; preserves maximum count, "
                         "then prefers better-ranked QAs in overlaps")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--gold-out", type=Path,
                    help="also write the selected QAs in tier1_gold format")
    ap.add_argument("--gold-missing-out", type=Path,
                    help="write the selected QAs absent from the supplied ranking")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("self-test:")
        return self_test()
    if not args.windows:
        ap.error("--windows is required (or --self-test)")
    if (args.gold_out or args.gold_missing_out) and not args.ranking:
        ap.error("--gold-out/--gold-missing-out require --ranking")

    records = _list_from(args.windows)
    rank_by_item = load_question_ranking(args.ranking) if args.ranking else {}
    keep = None
    if args.all_formats:
        keep = {r.get("content_id") for r in _list_from(args.all_formats)}

    # Passage length must come from ALL records, not the filtered subset:
    # n_verses is inferred from the highest window ordinal seen, so filtering out
    # the items near a passage's end silently shrinks the passage and with it the
    # capacity ceiling floor(n/3). t1_2sam21 collapsed from 8 verses to 3 that
    # way, turning capacity 2 into capacity 1.
    verses_by_passage = {}
    for record in records:
        pid = record["passage_id"]
        top = max(record["window_ordinals"]) + 1
        verses_by_passage[pid] = max(verses_by_passage.get(pid, 0), top)

    by_passage = defaultdict(list)
    for record in records:
        cid = record.get("content_id")
        if keep is not None and cid not in keep:
            continue
        by_passage[record["passage_id"]].append(record)

    print(f"{'passage':15}{'items':>6}{'verses':>7}{'cap':>5}"
          f"{'placed':>8}{'unplaced':>9}{'forced':>8}{'before':>8}")
    print("-" * 74)
    results, totals = {}, defaultdict(int)
    for passage in sorted(by_passage):
        rows = by_passage[passage]
        n_verses = verses_by_passage[passage]
        items = [(r["content_id"], required_ordinals(r)) for r in rows]
        before = len(overlap_pairs({r["content_id"]: r["window_ordinals"] for r in rows}))
        assignment, unplaced = (
            assign_disjoint_ranked(items, n_verses, rank_by_item)
            if args.ranking else assign_disjoint(items, n_verses)
        )
        forced = forced_conflicts(items)
        cap = n_verses // WINDOW
        print(f"{passage:15}{len(rows):>6}{n_verses:>7}{cap:>5}"
              f"{len(assignment):>8}{len(unplaced):>9}{len(forced):>8}{before:>8}")
        results[passage] = {
            "n_verses": n_verses, "capacity": cap,
            "assignment": {k: v for k, v in assignment.items()},
            "selected": [
                {
                    "content_id": content_id,
                    "window_ordinals": window,
                    "global_rank": rank_by_item.get(content_id),
                }
                for content_id, window in sorted(
                    assignment.items(), key=lambda item: (item[1][0], item[0])
                )
            ],
            "unplaced": [
                {
                    "content_id": item_id,
                    "required": span,
                    "global_rank": rank_by_item.get(item_id),
                }
                for item_id, span in unplaced
            ],
            "forced_conflicts": forced,
            "overlaps_before": before,
            "overlaps_after": len(overlap_pairs(assignment)),
        }
        totals["items"] += len(rows)
        totals["placed"] += len(assignment)
        totals["unplaced"] += len(unplaced)
        totals["forced"] += len(forced)
        totals["before"] += before
        totals["after"] += len(overlap_pairs(assignment))

    print("-" * 74)
    print(f"{'TOTAL':15}{totals['items']:>6}{'':>7}{'':>5}"
          f"{totals['placed']:>8}{totals['unplaced']:>9}"
          f"{totals['forced']:>8}{totals['before']:>8}")
    print(f"\noverlapping pairs: {totals['before']} before -> {totals['after']} after")
    print(f"items keepable with disjoint windows: {totals['placed']}/{totals['items']}")
    print(f"items that cannot be placed (capacity or shared answer verse): "
          f"{totals['unplaced']}")
    print(f"pairs sharing a required verse (deletion genuinely needed): {totals['forced']}")

    if rank_by_item:
        selected_ids = {
            content_id
            for passage in results.values()
            for content_id in passage["assignment"]
        }
        totals["ranked_selected"] = sum(item_id in rank_by_item for item_id in selected_ids)
        totals["unranked_selected"] = len(selected_ids) - totals["ranked_selected"]

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "schema_version": 1,
            "window_size": WINDOW,
            "source_set": "all_formats" if keep is not None else "window_map",
            "selection_order": (
                "maximum_count_then_global_question_rank"
                if args.ranking else "maximum_count_then_content_id"
            ),
            "ranking_source": str(args.ranking) if args.ranking else None,
            "summary": dict(totals),
            "passages": results,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")

    if args.gold_out or args.gold_missing_out:
        required_path = args.windows.with_name("tier1_required_spans.json")
        required = json.loads(required_path.read_text(encoding="utf-8"))
        by_content_id = {record["content_id"]: record for record in records}
        selected = []
        for passage_id in sorted(results):
            assignment = results[passage_id]["assignment"]
            for content_id, window in sorted(
                assignment.items(), key=lambda item: (item[1][0], item[0])
            ):
                record = by_content_id[content_id]
                source = required.get(record.get("span_key")) or {}
                selected.append({
                    "content_id": content_id,
                    "passage_id": passage_id,
                    "reference": source.get("reference") or record.get("reference"),
                    "question": source.get("question"),
                    "answer": source.get("gold_answer"),
                    "window_ordinals": window,
                    "has_grid_data": content_id in rank_by_item,
                    "global_rank": rank_by_item.get(content_id),
                })
        provenance = {
            "selection_method": "maximum_count_then_global_question_rank",
            "ranking_source": str(args.ranking) if args.ranking else None,
            "ranked_selected": sum(row["has_grid_data"] for row in selected),
            "unranked_selected": sum(not row["has_grid_data"] for row in selected),
        }
        if args.gold_out:
            args.gold_out.parent.mkdir(parents=True, exist_ok=True)
            args.gold_out.write_text(json.dumps({
                "schema_version": 2,
                "n_items": len(selected),
                "provenance": provenance,
                "items": selected,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {args.gold_out}")
        if args.gold_missing_out:
            missing = [row for row in selected if not row["has_grid_data"]]
            args.gold_missing_out.parent.mkdir(parents=True, exist_ok=True)
            args.gold_missing_out.write_text(json.dumps({
                "schema_version": 2,
                "n_items": len(missing),
                "note": "selected maximum-capacity QAs absent from the 90-item ranking",
                "provenance": provenance,
                "items": missing,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {args.gold_missing_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
