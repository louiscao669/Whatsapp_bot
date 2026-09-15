#!/usr/bin/env python3
"""Present MCQ options in a controlled order, so a model's LETTER PRIOR stops being
confounded with the item.

Why this exists (measured, tier1 gold72, 2026-09-13):

    each answer model is deterministic at temperature 0 -- on clean text it returns the
    same letter 6/6 times, so the "159 observations per item" in the logs are really
    3-4 distinct decisions, replicated.

    option order is FIXED per item across every model x family x dose cell, so whichever
    letter a model favours is locked to the same item every time:

        llama3.2:1b   A 24%  B 33%  C 22%  D 21%
        qwen2.5:1.5b  A 21%  B 31%  C 31%  D 18%
        qwen3:1.7b    A 21%  B 25%  C 21%  D 33%

    That produced a phantom finding. Selecting items where "a distractor beats the key"
    returned 9 items, 78% of them keyed D against 31% in the full set, on which the
    D-preferring model scored 7/7 where the key was D and 0/2 where it was not. The items
    were fine; the selection was measuring letter bias.

ROTATION, NOT RANDOMNESS, is the default, for two reasons:

  * Paired dose contrasts stay clean. The dose response is a within-item comparison of
    0% against 30%. If the order changed between those cells, the contrast would carry a
    position change as well as a dose change. One rotation offset applied to a whole run
    holds position constant inside the run, so any position effect cancels exactly in the
    paired difference.
  * It is exhaustive rather than approximate. Run the campaign four times at offsets
    0,1,2,3 and every item's key has sat in every position exactly once, so averaging over
    the four runs removes the letter prior EXACTLY. Random permutation only removes it in
    expectation, which at 3-4 effective observations per item is not good enough.

Because the answerers are deterministic, replicates at a fixed order are free information
only in the sense that they cost money and tell you nothing new. Rotating turns the same
number of API calls into four genuinely different observations.

Meta-options (abstention, none-of-the-above) NEVER move: they are appended after the
content options by add_meta_options.py, are never the key, and a respondent reads "E" as
"I can't tell" positionally. Only the content labels are reordered.
"""
from __future__ import annotations

import hashlib
import random
from typing import Dict, List, Sequence


def content_order(labels: Sequence[str], *, rotate: int | None = None,
                  seed: str | None = None, item_key: str = "") -> List[str]:
    """The canonical labels, in the order they will be PRESENTED.

    Exactly one of `rotate` or `seed` is used; with neither, the order is unchanged.

    rotate=K: presented slot j shows the option canonically labelled labels[(j+K) % n].
    An item whose key is at canonical index k appears at presented index (k-K) % n, so
    across K = 0..n-1 the key visits every position exactly once.
    """
    n = len(labels)
    if n == 0:
        return []
    if rotate is not None and seed is not None:
        raise ValueError("choose rotation or seeded shuffle, not both")
    if rotate is not None:
        k = rotate % n
        return [labels[(j + k) % n] for j in range(n)]
    if seed is not None:
        # Per-item permutation, reproducible from (seed, item). Hashed rather than using
        # hash() so it is stable across processes and Python's hash randomisation.
        h = hashlib.sha256(f"{seed}:{item_key}".encode("utf-8")).hexdigest()
        rng = random.Random(int(h[:16], 16))
        out = list(labels)
        rng.shuffle(out)
        return out
    return list(labels)


def presented_to_canonical(labels: Sequence[str], order: Sequence[str]) -> Dict[str, str]:
    """{label as shown to the model: label it means in the source data}.

    Meta-options are absent from `labels` and therefore map to themselves; callers use
    .get(x, x) so an abstention letter passes through untouched.
    """
    return {labels[j]: order[j] for j in range(len(order))}


def reorder_choices(choices: Dict[str, str], labels: Sequence[str],
                    order: Sequence[str]) -> Dict[str, str]:
    """Rebuild the choices dict as the model will see it.

    Every label not in `labels` -- the abstention and none-of-the-above tail -- is copied
    through at its original letter, because those are positional promises to the reader,
    not content.
    """
    mapping = presented_to_canonical(labels, order)
    out = {shown: choices[canon] for shown, canon in mapping.items() if canon in choices}
    for label, text in choices.items():
        if label not in labels:
            out[label] = text
    return out


def canonical_choice(selected: str | None, labels: Sequence[str],
                     order: Sequence[str]) -> str | None:
    """Translate what the model answered back into the source data's lettering.

    Everything downstream -- scorers, the dose-response analyses, the item audits -- keeps
    seeing canonical letters, so enabling rotation changes no other file.
    """
    if selected is None:
        return None
    return presented_to_canonical(labels, order).get(selected, selected)


def self_test() -> int:
    cases = []
    L = ["A", "B", "C", "D"]

    cases.append(("no rotation and no seed leaves the order alone",
                  content_order(L) == L))
    cases.append(("rotation is cyclic",
                  content_order(L, rotate=1) == ["B", "C", "D", "A"]
                  and content_order(L, rotate=3) == ["D", "A", "B", "C"]))
    cases.append(("rotation wraps", content_order(L, rotate=4) == L
                  and content_order(L, rotate=5) == content_order(L, rotate=1)))

    # The property the whole design rests on: over a full ladder of rotations, each
    # item's key sits in every position exactly once.
    for key in L:
        seen = []
        for k in range(4):
            order = content_order(L, rotate=k)
            shown = [s for s, c in presented_to_canonical(L, order).items() if c == key]
            seen.append(shown[0])
        cases.append((f"key {key} visits every position exactly once over rotations 0-3",
                      sorted(seen) == L))

    choices = {"A": "alpha", "B": "bravo", "C": "charlie", "D": "delta"}
    order = content_order(L, rotate=1)
    shown = reorder_choices(choices, L, order)
    cases.append(("reordering moves text, not labels",
                  shown == {"A": "bravo", "B": "charlie", "C": "delta", "D": "alpha"}))
    cases.append(("the model's letter maps back to the source letter",
                  canonical_choice("A", L, order) == "B"
                  and canonical_choice("D", L, order) == "A"))
    cases.append(("round trip: the text under the mapped-back letter is unchanged",
                  all(shown[s] == choices[canonical_choice(s, L, order)] for s in L)))
    cases.append(("None survives", canonical_choice(None, L, order) is None))

    meta = dict(choices, E="I can't tell from this passage", F="None of the above")
    shown_meta = reorder_choices(meta, L, order)
    cases.append(("meta-options keep their letters and text",
                  shown_meta["E"] == meta["E"] and shown_meta["F"] == meta["F"]))
    cases.append(("a meta letter passes through the mapping untouched",
                  canonical_choice("E", L, order) == "E"
                  and canonical_choice("F", L, order) == "F"))
    cases.append(("meta-options are never reachable as content",
                  set(presented_to_canonical(L, order)) == set(L)))

    s1 = content_order(L, seed="s", item_key="it1")
    cases.append(("seeded shuffle is deterministic",
                  s1 == content_order(L, seed="s", item_key="it1")))
    cases.append(("seeded shuffle differs by item",
                  any(content_order(L, seed="s", item_key=f"it{i}") != s1
                      for i in range(2, 12))))
    cases.append(("seeded shuffle is a permutation", sorted(s1) == L))
    raised = False
    try:
        content_order(L, rotate=1, seed="s")
    except ValueError:
        raised = True
    cases.append(("rotation and seed together is refused", raised))
    cases.append(("empty label set is harmless", content_order([]) == []))

    bad = 0
    for name, ok in cases:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        bad += not ok
    print(f"\n{len(cases) - bad}/{len(cases)} self-tests passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(self_test())
