#!/usr/bin/env python3
"""Tests for the per-defect-family split in tier-1 item selection.

The contract: `selection_score` is driven by the OPEN form and by the WEIGHTED
defect families only. `adversarial` is computed and reported but must never move
a ranking until the grid shows it is monotonic on tier-1 -- the 2026-07-03
analysis found the addition family noisy and non-monotonic, and no tier-1
adversarial cells have been verified to exist.

These run without the offline grid (evaluation/outputs is a symlink to
eten-research-outputs, absent in some checkouts), by feeding synthetic evidence
dicts straight into the feature builder.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "pilot_import_mod", REPO_ROOT / "scripts" / "pilot_import.py"
)
pilot = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(pilot)
except Exception as exc:  # pragma: no cover - needs Flask in some envs
    print(f"SKIP: cannot import pilot_import ({exc})")
    raise SystemExit(0)

FAILURES = []


def check(label, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        FAILURES.append(label)


def _row(qid="q1"):
    return {
        "base_id": qid,
        "window": {"answer_not_fully_in_passage": False},
        "entry": {"open": {"Q": "question?"}},
    }


QUALITY = {"q1": {"question_relevancy": 8.0, "information_capture": 8.0,
                  "difficulty_value": 0.5, "needs_review": False}}


def _features(**evidence):
    base = {"clean_accuracy": 0.8, "clean_n": 3}
    base.update(evidence)
    return pilot.tier1_collision_features(_row(), QUALITY, {"q1": base})


def test_adversarial_is_reported():
    f = _features(dose_drop_omission=0.2, dose_n_omission=3,
                  dose_drop_mistranslation=0.3, dose_n_mistranslation=3,
                  dose_drop_adversarial=0.4, dose_n_adversarial=3)
    check("adversarial dose_drop is surfaced", f["dose_drop_adversarial"] == 0.4)
    check("per-family drops surfaced", f["dose_drop_omission"] == 0.2
          and f["dose_drop_mistranslation"] == 0.3)
    check("scoring form recorded", f["scoring_form"] == "open")


def test_adversarial_does_not_move_the_score():
    """The load-bearing test: adversarial must be inert in the composite."""
    common = dict(dose_drop_omission=0.2, dose_n_omission=3,
                  dose_drop_mistranslation=0.2, dose_n_mistranslation=3)
    low = _features(**common, dose_drop_adversarial=-0.9, dose_n_adversarial=3)
    high = _features(**common, dose_drop_adversarial=0.9, dose_n_adversarial=3)
    absent = _features(**common, dose_drop_adversarial=None, dose_n_adversarial=0)
    check("selection_score identical across adversarial values",
          low["selection_score"] == high["selection_score"] == absent["selection_score"])
    check("rank key identical too",
          pilot.tier1_collision_rank(low) == pilot.tier1_collision_rank(high))


def test_weighted_families_average_not_pool():
    f = _features(dose_drop_omission=0.1, dose_n_omission=3,
                  dose_drop_mistranslation=0.5, dose_n_mistranslation=3)
    # dose term = mean(0.1, 0.5) = 0.3 -> 3.0 * 0.3 = 0.9
    quality = (8.0 + 8.0) / 20.0
    difficulty_fit = max(0.0, 1.0 - abs(0.8 - 0.65) / 0.65)
    expected = 0.9 + quality + 0.75 * difficulty_fit + 0.25 * 0.5 + 0.15
    check("composite uses the mean of weighted family drops",
          abs(f["selection_score"] - expected) < 1e-9)


def test_one_family_present_still_scores():
    f = _features(dose_drop_omission=0.4, dose_n_omission=3,
                  dose_drop_mistranslation=None, dose_n_mistranslation=0)
    check("item with only one family still gets a score",
          f["selection_score"] > 0)
    check("missing family reported", "mistranslation" in f["families_missing"])
    check("single-family item does NOT get the both-families bonus",
          f["responds_to_both_weighted_families"] is False)


def test_both_families_beats_one_family_spike():
    """A single-family spike should not outrank a consistent responder."""
    both = _features(dose_drop_omission=0.25, dose_n_omission=3,
                     dose_drop_mistranslation=0.25, dose_n_mistranslation=3)
    spike = _features(dose_drop_omission=0.5, dose_n_omission=3,
                      dose_drop_mistranslation=-0.1, dose_n_mistranslation=3)
    check("consistent responder outranks single-family spike",
          pilot.tier1_collision_rank(both) > pilot.tier1_collision_rank(spike))


def test_absent_family_is_not_zero():
    """'No data' must not read as 'no effect'."""
    f = _features(dose_drop_omission=0.3, dose_n_omission=3,
                  dose_drop_mistranslation=None, dose_n_mistranslation=0)
    check("absent family stays None, not 0.0",
          f["dose_drop_mistranslation"] is None)
    pooled = _features(dose_drop_omission=0.3, dose_n_omission=3,
                       dose_drop_mistranslation=0.0, dose_n_mistranslation=3)
    check("absent family scores differently from a measured zero",
          f["selection_score"] != pooled["selection_score"])


def test_negative_drop_still_fails_the_gate():
    """Pre-existing behaviour must survive the refactor."""
    good = _features(dose_drop_omission=0.1, dose_n_omission=3,
                     dose_drop_mistranslation=0.1, dose_n_mistranslation=3)
    bad = _features(dose_drop_omission=-0.2, dose_n_omission=3,
                    dose_drop_mistranslation=-0.2, dose_n_mistranslation=3)
    check("negative mean drop loses regardless of composite",
          pilot.tier1_collision_rank(good) > pilot.tier1_collision_rank(bad))


def _sens(**families):
    """Build a sensitivity block: family -> {slope, p}."""
    return {"sensitivity": {f: dict(zip(("slope", "p"), v))
                            for f, v in families.items()}}


def _si(**families):
    return {"sensitivity": {f: dict(zip(("s_i", "p"), v))
                            for f, v in families.items()}}


def test_s_i_is_primary_and_dose_drop_stays_secondary():
    f = _features(dose_drop_omission=0.02, dose_n_omission=3,
                  dose_drop_mistranslation=0.02, dose_n_mistranslation=3,
                  **_sens(omission=(-0.13, 0.002)))
    check("secondary dose basis stays dose_drop",
          f["dose_basis"] == "dose_drop_secondary")
    check("legacy slope maps to positive s_i", abs(f["best_s_i"] - 0.13) < 1e-9)
    check("p gate passes", f["passes_p_gate"] is True)


def test_no_ladder_fit_falls_back_to_dose_drop():
    f = _features(dose_drop_omission=0.2, dose_n_omission=3,
                  dose_drop_mistranslation=0.2, dose_n_mistranslation=3)
    check("secondary score still uses dose_drop",
          f["dose_basis"] == "dose_drop_secondary")
    check("p gate not claimed", f["passes_p_gate"] is False)


def test_positive_slope_is_rejected_even_with_a_small_p():
    """One-sided permutation p plus a sign check.

    An item that gets EASIER as quality drops must never gate through; p alone
    cannot express that, so the sign is checked explicitly.
    """
    f = _features(dose_drop_omission=0.1, dose_n_omission=3,
                  **_sens(omission=(+0.12, 0.01)))
    check("positive slope fails the gate", f["gated_omission"] is False)
    check("and maps to a negative s_i", f["s_i_omission"] == -0.12)


def test_steep_slope_outranks_consistent_but_shallow():
    """The whole reason for slope over rho.

    A shallow item can be perfectly monotonic (rho ~ -0.9) yet carry almost no
    signal. Fisher information goes as s^2, so magnitude must win.
    """
    steep = _features(dose_drop_omission=0.05, dose_n_omission=3,
                      **_sens(omission=(-0.133, 0.002)))
    shallow = _features(dose_drop_omission=0.05, dose_n_omission=3,
                        **_sens(omission=(-0.001, 0.050)))
    check("steeper s_i ranks higher in the primary tuple",
          pilot.tier1_primary_rank(steep) > pilot.tier1_primary_rank(shallow))
    check("s_i does not leak into the secondary composite",
          steep["selection_score"] == shallow["selection_score"])
    check("both pass the gate (p<=0.10)",
          steep["passes_p_gate"] and shallow["passes_p_gate"])


def test_gated_item_outranks_ungated_regardless_of_composite():
    gated = _features(dose_drop_omission=0.0, dose_n_omission=3,
                      **_sens(omission=(-0.05, 0.01)))
    ungated = _features(dose_drop_omission=0.5, dose_n_omission=3,
                        dose_drop_mistranslation=0.5, dose_n_mistranslation=3)
    check("p-gated item wins on the rank key",
          pilot.tier1_collision_rank(gated) > pilot.tier1_collision_rank(ungated))


def test_more_gated_families_breaks_ties():
    one = _features(**_sens(omission=(-0.10, 0.01)))
    two = _features(**_sens(omission=(-0.10, 0.01), mistranslation=(-0.10, 0.01)))
    check("two gated families outrank one",
          pilot.tier1_collision_rank(two) > pilot.tier1_collision_rank(one))


def test_schema2_s_i_is_used_directly():
    f = _features(**_si(omission=(0.75, 0.01)))
    check("schema-v2 s_i is exposed", f["s_i_omission"] == 0.75)
    check("positive s_i passes with small p", f["gated_omission"] is True)


def test_primary_gate_cannot_be_overridden_by_secondary_features():
    gated = _features(dose_drop_omission=-0.9, dose_n_omission=3,
                      **_si(omission=(0.01, 0.01)))
    ungated = _features(dose_drop_omission=0.9, dose_n_omission=3,
                        dose_drop_mistranslation=0.9, dose_n_mistranslation=3)
    check("p/s_i primary gate dominates every secondary feature",
          pilot.tier1_collision_rank(gated) > pilot.tier1_collision_rank(ungated))


def test_adversarial_slope_still_cannot_move_the_score():
    a = _features(**_sens(omission=(-0.10, 0.01), adversarial=(-0.90, 0.001)))
    b = _features(**_sens(omission=(-0.10, 0.01), adversarial=(+0.90, 0.999)))
    check("adversarial slope reported but unweighted",
          a["selection_score"] == b["selection_score"])
    check("its slope is still surfaced", a["slope_adversarial"] == -0.90)


def test_family_constants_are_consistent():
    check("adversarial is defined", "adversarial" in pilot.TIER1_DEFECT_FAMILIES)
    check("adversarial is NOT weighted",
          "adversarial" not in pilot.TIER1_WEIGHTED_FAMILIES)
    check("weighted families all defined",
          all(f in pilot.TIER1_DEFECT_FAMILIES for f in pilot.TIER1_WEIGHTED_FAMILIES))


def main():
    print("per-family split:")
    test_adversarial_is_reported()
    test_adversarial_does_not_move_the_score()
    test_weighted_families_average_not_pool()
    test_one_family_present_still_scores()
    test_both_families_beats_one_family_spike()
    test_absent_family_is_not_zero()
    test_negative_drop_still_fails_the_gate()
    print("slope + p as primary selector:")
    test_s_i_is_primary_and_dose_drop_stays_secondary()
    test_no_ladder_fit_falls_back_to_dose_drop()
    test_positive_slope_is_rejected_even_with_a_small_p()
    test_steep_slope_outranks_consistent_but_shallow()
    test_gated_item_outranks_ungated_regardless_of_composite()
    test_more_gated_families_breaks_ties()
    test_schema2_s_i_is_used_directly()
    test_primary_gate_cannot_be_overridden_by_secondary_features()
    test_adversarial_slope_still_cannot_move_the_score()
    test_family_constants_are_consistent()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        return 1
    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
