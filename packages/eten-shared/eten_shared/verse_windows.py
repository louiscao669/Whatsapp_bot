"""Delivery-window repair: keep a damaged window at full length.

Pure and dependency-free on purpose -- imported by the live assignment path, and by tests
and scripts that run where sqlalchemy is not installed (the same reason wh_type.py is
standalone).

WHY. Omission deletes verses from the passage, so a curated three-verse window can reach
delivery holding two, one, or none. Serving the remainder makes window LENGTH carry the
answer: measured on gold72 (2026-09-28), a window with all three verses present never has
its answer deleted -- 0% at both 15% and 30% dose -- so "three verses" tells a reader to
rule out abstention before reading, and the rule "abstain iff <= 1 verse" scores 81.4% on
its own, beating two of the three answer models. Padding removes that shortcut.

WHAT IT CANNOT DO, which is what keeps it honest: it only ever adds verses that SURVIVED.
A verse omission deleted stays deleted, so padding can never restore the answer to the
item's own question. It can pull in a neighbouring item's answer -- but only one that
neighbour would have shown anyway, because the dose is applied once to the passage and
every window is a view onto the same damaged text.

Gaps are expected. Survivors need not be contiguous, and a reader seeing non-adjacent
verses is seeing exactly what omission did to the passage.
"""
from __future__ import annotations

PASSAGE_DELIVERY_VERSE_COUNT = 3


def _verse_sort_key(number):
    """Numeric order for a verse label, tolerating "13:20" and plain "20"."""
    text = str(number)
    tail = text.rsplit(":", 1)[-1]
    digits = "".join(ch for ch in tail if ch.isdigit())
    return int(digits) if digits else 0


def pad_window_verses(window_numbers, all_verses, occupied=(), want=PASSAGE_DELIVERY_VERSE_COUNT):
    """Restore a damaged window to ``want`` SURVIVING verses, avoiding claimed ones.

    Omission deletes verses from the passage, so a curated three-verse window can arrive
    at delivery holding two, one, or none. Serving the remainder makes window LENGTH carry
    information: measured on gold72, a window with all three verses present never has its
    answer deleted (0% at both doses), so "three verses" tells a reader to rule out
    abstention before reading, and "abstain iff <= 1 verse" alone scores 81.4% -- beating
    two of the three answer models. Padding removes that shortcut.

    What padding CANNOT do, and this is what keeps it honest: it only ever adds verses
    that SURVIVED. A verse omission deleted stays deleted, so padding can never restore
    the answer to the item's own question. It can pull in a neighbouring item's answer,
    but only one that neighbour would have shown anyway -- the dose is applied once to the
    passage, and every window is a view onto that same damaged text.

    ``occupied`` is the set of verse labels other items' windows already claim. Padding
    prefers verses nobody else uses, so the overlap it creates is as small as the
    surviving text allows; it takes a claimed verse only when there is no free one left,
    because a short window is the worse failure.

    Gaps are expected: the survivors need not be contiguous, and a reader seeing
    non-adjacent verses is seeing what omission did.
    """
    wanted = list(window_numbers or [])
    ordered = list(all_verses or [])
    if not ordered:
        return []
    present_idx = [i for i, verse in enumerate(ordered) if verse.verse_number in set(wanted)]
    if len(present_idx) >= want:
        return [ordered[i] for i in present_idx[:want]]

    if present_idx:
        lo, hi = min(present_idx), max(present_idx)
        chosen = list(present_idx)
    else:
        # The whole window is gone. Anchor where it used to sit, by verse order, so the
        # reader still gets the right neighbourhood rather than the start of the passage.
        if not wanted:
            return []
        target = _verse_sort_key(wanted[0])
        after = [i for i, v in enumerate(ordered) if _verse_sort_key(v.verse_number) >= target]
        lo = hi = (after[0] if after else len(ordered) - 1)
        chosen = [lo]
        if len(chosen) >= want:
            return [ordered[i] for i in sorted(chosen)]

    claimed = set(occupied or ())

    def take(index):
        chosen.append(index)

    # Expand outward, preferring a free verse over a claimed one at each step; ties go
    # forward first so the window reads in passage order.
    while len(chosen) < want:
        candidates = []
        if hi + 1 < len(ordered):
            candidates.append(("after", hi + 1))
        if lo - 1 >= 0:
            candidates.append(("before", lo - 1))
        if not candidates:
            break
        free = [c for c in candidates if ordered[c[1]].verse_number not in claimed]
        side, index = (free or candidates)[0]
        take(index)
        if side == "after":
            hi = index
        else:
            lo = index
    return [ordered[i] for i in sorted(set(chosen))]
