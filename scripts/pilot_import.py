#!/usr/bin/env python3
"""Import the tier-1 human-pilot QA windows and passage variants.

Two things get uploaded:

  * QA/window -> intersect translated tier-1 QA with the curated randomized
           three-verse map, remove duplicate-window questions, choose one form
           per remaining window (~75% MCQ / 25% open), and divide the windows
           into eight contiguous groups whose sizes differ by at most one.

  * Passage -> one ExperimentPassage per (tier-1 source passage, condition).
           A Latin-square group may cross a passage boundary; delivery resolves
           the correct variant from (QA passage_id, plan-cell condition).

The Chinese QA target is read once per passage from omission/0%. A real write
refuses if any condition variant is missing.

Idempotent: re-running skips existing QA items and refreshes existing passages.

Usage:
  # dry run -- no DB, prints the plan + quota per chapter
  python scripts/pilot_import.py --eval-root /path/to/eten-whatsapp-bot/evaluation --dry-run

  # real import -- needs DATABASE_URL in the environment (or .env on the host)
  python scripts/pilot_import.py --eval-root /path/to/eten-whatsapp-bot/evaluation

Note: this uploads QA + passages only. Per-participant plan cells
(experiment_plan_cells) are written separately by the Latin-square plan builder.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from _bootstrap import use_platform

use_platform()

from eten_shared.models import (  # noqa: E402
    ExperimentPassage,
    ExperimentPassageVerse,
    ExperimentWindow,
    QAItem,
)

# (condition key, relative dir under the answer-model folder, human-readable name)
# [CHANGED 2026-07-27b] Two matched adequacy ladders; see build_experiment_plan.SLOTS and
# HUMAN_PILOT_DESIGN_2026-07-27.md §4. Keys MUST match SLOTS and export CONDITION_TO_EVAL.
CONDITIONS = [
    ("clean", "omission/0%", "Clean anchor"),
    ("omission15", "omission/15%", "Omission 15%"),
    ("omission30", "omission/30%", "Omission 30%"),
    ("mistranslation15", "mistranslation/15%", "Mistranslation 15%"),
    ("mistranslation30", "mistranslation/30%", "Mistranslation 30%"),
    ("grammar30", "grammar/30%", "Grammar 30%"),
    ("wbw", "google_word_by_word", "Word-by-word (Google)"),
]
CHAPTERS = range(1, 9)
ANSWER_MODELS = ["1.7b", "1.5b", "llama 1b", "llama 3b"]  # search order; target files identical
LANGUAGE = "zh"
MCQ_FRACTION = 0.75
# [NEW 2026-07-27b] Item exclusions, mirroring evaluation/scripts/mcq/regen_mcq_tier01.py. The
# delivered qa_target_pseudonymized.json files still CONTAIN these records --
# promote_mcq_rewrites.py patches, it never deletes -- so the importer must filter them or the
# retired forms reach participants.
MCQ_REWRITES_FILENAME = "mcq_rewrites.json"   # lives at <eval_root>/datasets/mcq/mcq_rewrites.json
EXCLUDED_OPEN_STEMS = {"uw-174382"}           # unscoped question; MCQ form is kept
TIER1_ROOT = "tier1"
TIER1_GROUP_COUNT = 8
TIER1_CSV = "obscure_narrative_passages_tier1.csv"
TIER1_WINDOWS = "tier1_qa_verse_windows.json"
TIER1_DISCRIMINATION_MODELS = ("qwen317b", "qwen2515b", "llama321b")
TIER1_CLEAN_CONDITION = "omission/0%"
TIER1_HIGH_DOSE_CONDITIONS = ("omission/30%", "mistranslation/30%")

# [2026-08-14] Dose evidence is now split by DEFECT FAMILY rather than pooled.
#
# The pooled `dose_drop` averaged omission/30% and mistranslation/30% into one
# number, but the grid shows these are different families with different slopes
# (open Delta(30%): mistranslation .334/.268/.161 vs omission .264/.220/.172),
# and the 2026-07-27 deployment split already treats them separately --
# mistranslation for group-level certification, omission for per-item
# calibration. Pooling hides an item that discriminates on one but not the
# other, which is exactly the distinction the two matched ladders were built to
# expose.
#
# `adversarial` is the addition family's adversarial category: it asserts the
# item's OWN wrong MCQ choices into the passage, so the text now states a
# competing answer. That is a third mechanism -- omission removes the answer,
# mistranslation corrupts it, adversarial addition plants a rival. Generated
# from MCQ distractors but applied to the passage, so it is measurable on the
# open form even though tier-1 MCQ is not deliverable.
TIER1_DEFECT_FAMILIES = {
    "omission": "omission/30%",
    "mistranslation": "mistranslation/30%",
    "adversarial": "addition/adversarial_30%",
}

# Families whose dose_drop enters `selection_score`. Adversarial is REPORTED but
# UNWEIGHTED: the 2026-07-03 analysis found the addition family noisy and
# non-monotonic (that was generic filler, not the adversarial category, so the
# behaviour may differ) and no tier-1 adversarial cells have been verified to
# exist. Promote it only once the grid shows a monotonic dose-response on
# tier-1; until then it must not move the ranking.
TIER1_WEIGHTED_FAMILIES = ("omission", "mistranslation")

# [2026-08-17] Selection primitives: permutation p (GATE) + ladder slope (SCORE).
#
# Produced by `scripts/report_tier1_family_split.py --emit-sensitivity`, which
# fits each item's accuracy against the FULL dose ladder (~18 obs) instead of
# the single 30% contrast (3 obs).
#
# Why the change: re-judging the 12 window-level removals against the ladder
# REVERSED 4 of 10 (binomial p=0.75 against a coin flip), and the kept vs
# removed pools were statistically identical (median best-rho -0.665 vs -0.655,
# strong-responder rate Fisher p=0.535). The 3-obs `dose_drop` carried
# essentially no information about dose response. One kept item, t1_judg9:eo5e,
# has a POSITIVE ladder slope -- it gets easier as the passage degrades -- and
# beat a genuine responder on a 0.042 dose_drop, i.e. one answer cell in twelve.
#
# Why slope rather than rho: Spearman is scale-free, so an item declining
# 1.00->0.95 monotonically scores rho=-0.88 while carrying almost no signal, and
# would outrank a steeper item with one rank inversion. Fisher information is
# s^2 * p(1-p) -- the slope enters squared, rho does not appear at all.
#
# NOT the IRT s_i from scripts/fit_item_sensitivity.py: that is partially
# pooled with a free item intercept and a per-respondent theta offset, and is
# hardcoded to the Luke layout (eval_root/luke{ch}, positional item keys), so it
# does not run on tier-1 today. Porting it is the intended follow-up; this local
# slope is the same quantity in spirit, unpooled.
TIER1_SENSITIVITY_FILE = "tier1_item_sensitivity.json"
TIER1_P_GATE = 0.10

# Selection evidence is read from the OPEN form only. MCQ is binary and carries
# a 25% guessing floor, and the strongest answerer saturates it at the 3-verse
# window -- so MCQ cells contribute ceiling zeros rather than discrimination.
# Open scores are the judge's 0/0.5/1, three levels per observation instead of
# two. The pilot is open-primary (HUMAN_PILOT_DESIGN 2026-07-27 section 4), so
# selecting on open also matches the instrument that will be deployed.
TIER1_SCORING_FORM = "open"


# ---------------------------------------------------------------- data loading

def _variant_dir(eval_root: Path, chapter: int, rel: str):
    for model in ANSWER_MODELS:
        d = eval_root / "outputs" / f"luke{chapter}" / model / rel
        if d.exists():
            return d
    return None


def validate_eval_root(eval_root: Path) -> None:
    """Fail fast with a diagnostic instead of a bare 'no clean-variant dir for Luke 1'.

    That error is almost always a wrong --eval-root (it must point at the *evaluation*
    directory, i.e. the one containing 'outputs/'), not genuinely missing variants."""
    if not eval_root.exists():
        sys.exit(f"--eval-root does not exist: {eval_root}\n"
                 f"  it must point at the 'evaluation' directory, e.g. "
                 f"{Path(__file__).resolve().parents[1] / 'evaluation'}")
    if not (eval_root / "outputs").is_dir():
        hint = ""
        if (eval_root / "evaluation" / "outputs").is_dir():
            hint = f"\n  did you mean: --eval-root {eval_root / 'evaluation'}"
        sys.exit(f"--eval-root has no 'outputs/' subdirectory: {eval_root}{hint}")
    tier1 = eval_root / "outputs" / TIER1_ROOT
    if not tier1.is_dir():
        listing = sorted(p.name for p in (eval_root / "outputs").iterdir())[:8]
        sys.exit(
            f"no tier-1 output directory under {eval_root / 'outputs'}\n"
            f"  expected: {tier1}\n"
            f"  outputs/ contains: {listing}")


# Prefer the pseudonymized (natural-name) files produced by
# evaluation/scripts/pseudonyms/apply_pseudonym_remap.py; fall back to the raw decanonicalized files.
_warned = set()

def _pick(d: Path, pseudo: str, decanon: str) -> Path:
    if (d / pseudo).exists():
        return d / pseudo
    if decanon not in _warned:
        print(f"  [warn] {pseudo} not found -> using {decanon} (token names). "
              f"Run evaluation/scripts/pseudonyms/apply_pseudonym_remap.py for the natural-name version.")
        _warned.add(decanon)
    return d / decanon


def _base_id(passage_id: str) -> str:
    """'uw-174365-open' / 'uw-174365-mcq' -> 'uw-174365'."""
    for suffix in ("-open", "-mcq"):
        if passage_id.endswith(suffix):
            return passage_id[: -len(suffix)]
    return passage_id


def load_chapter_qa(eval_root: Path, chapter: int) -> dict:
    """{base_id: {'open': rec, 'mcq': rec}} for a chapter (from the clean dir)."""
    d = _variant_dir(eval_root, chapter, "omission/0%")
    if d is None:
        raise FileNotFoundError(f"no clean-variant dir for Luke {chapter}")
    recs = json.loads(_pick(d, "qa_target_pseudonymized.json",
                            "qa_target_decanonicalized.json").read_text(encoding="utf-8"))
    by_id: dict = {}
    for r in recs:
        bid = _base_id(r["passage_id"])
        slot = "open" if r.get("q_type") == "open" else "mcq"
        by_id.setdefault(bid, {})[slot] = r
    return by_id


def load_passage(eval_root: Path, chapter: int, rel: str):
    d = _variant_dir(eval_root, chapter, rel)
    if d is None:
        return None, None
    text = _pick(d, "passage_target_pseudonymized.txt",
                 "passage_target_decanonicalized.txt").read_text(encoding="utf-8").strip()
    # first record's reference gives a human-readable chapter label
    ref = None
    qa = _pick(d, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json")
    if qa.exists():
        recs = json.loads(qa.read_text(encoding="utf-8"))
        if recs:
            ref = recs[0].get("passage_reference")
    return text, ref


# --------------------------------------------------------------- tier-1 loading

_TIER1_MARKER = re.compile(r"(?<![\w\]\-–—])(\d{1,3})\s+")


def load_tier1_metadata(eval_root: Path) -> list[dict]:
    path = eval_root / "datasets" / TIER1_CSV
    if not path.exists():
        raise FileNotFoundError(f"missing tier-1 passage catalog: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def tier1_windows_path(eval_root: Path) -> Path:
    return eval_root.parent / "QA_algorithm" / "inputs" / TIER1_WINDOWS


def load_tier1_windows(eval_root: Path) -> list[dict]:
    path = tier1_windows_path(eval_root)
    if not path.exists():
        raise FileNotFoundError(f"missing tier-1 window map: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    windows = payload.get("windows") or []
    if not windows:
        raise ValueError(f"tier-1 window map is empty: {path}")
    return windows


def _tier1_variant_dir(eval_root: Path, passage_id: str, rel: str):
    base = eval_root / "outputs" / TIER1_ROOT / passage_id
    direct = base / rel
    if direct.exists():
        return direct
    # Generated-answer model folders duplicate the translation inputs.  They
    # are a fallback only; root-level condition dirs are canonical.
    for model in ("qwen317b", "qwen2515b", "llama321b", *ANSWER_MODELS):
        candidate = base / model / rel
        if candidate.exists():
            return candidate
    return None


def _tier1_base_id(passage_id: str) -> str:
    value = str(passage_id or "")
    for suffix in ("-open", "-mcq"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value


def _tier1_content_id(base_id: str) -> tuple[str, int]:
    """Return window-map content id and duplicate occurrence index."""
    value = str(base_id).removeprefix("uw-")
    match = re.match(r"^(.*?)(?:#(\d+))?$", value)
    occurrence = max(int(match.group(2) or "1") - 1, 0)
    return match.group(1), occurrence


def load_tier1_qa(eval_root: Path, passage_id: str) -> dict:
    d = _tier1_variant_dir(eval_root, passage_id, "omission/0%")
    if d is None:
        raise FileNotFoundError(f"no clean tier-1 variant for {passage_id}")
    records = json.loads(_pick(
        d, "qa_target_pseudonymized.json", "qa_target_decanonicalized.json"
    ).read_text(encoding="utf-8"))
    by_id = {}
    for record in records:
        base_id = _tier1_base_id(record.get("passage_id"))
        form = "open" if record.get("q_type") == "open" else "mcq"
        by_id.setdefault(base_id, {})[form] = record
    return by_id


def load_tier1_quality_metadata(eval_root: Path, passage_id: str) -> dict[str, dict]:
    """Source-pipeline quality/difficulty metadata keyed like translated base ids."""
    path = eval_root / "datasets" / "qa" / "tier1_QAs_easy" / f"{passage_id}_all_formats.json"
    if not path.exists():
        return {}
    out = {}
    for record in json.loads(path.read_text(encoding="utf-8")):
        content_id = str(record.get("content_id") or "").strip()
        if content_id:
            out[f"uw-{content_id}"] = record
    return out


def tier1_sensitivity_path(eval_root: Path) -> Path:
    """Canonical generated p/s_i artifact consumed by every Tier-1 ranker."""
    return eval_root / "reports" / TIER1_SENSITIVITY_FILE


def load_tier1_sensitivity(eval_root: Path) -> dict[str, dict]:
    """Load generated family-level sensitivity under every supported id form."""
    path = tier1_sensitivity_path(eval_root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for raw_id, families in (payload.get("items") or {}).items():
        item_id = str(raw_id).removesuffix("-open").removesuffix("-mcq")
        bare = item_id.removeprefix("uw-")
        out[bare] = families
        out[f"uw-{bare}"] = families
    return out


def load_tier1_empirical_metrics(eval_root: Path, passage_id: str) -> dict[str, dict]:
    """Per-question clean accuracy and per-FAMILY 30%-dose decline, open form.

    Selection evidence, not a statistical claim: the answer models run at
    temperature 0, so each cell is one deterministic response and re-running
    reproduces it exactly. There is no sampling variance to average down -- the
    only spread comes from the three ability tiers, which are systematic, not
    random. Treat the counts as coverage, not as a sample size.

    [CHANGED 2026-08-14] Two changes from the pooled version:

      * **open form only** (see TIER1_SCORING_FORM). The pooled version averaged
        a binary MCQ score with a 0/0.5/1 open score -- two different scales,
        one of them saturating at the top answerer -- so a value like 0.667
        could mean "all three models right on open, none on MCQ" or the exact
        reverse.
      * **per-family dose drops** (see TIER1_DEFECT_FAMILIES) instead of one
        pooled `degraded` mean.

    Returns per item::

        clean_accuracy, clean_n
        dose_drop_<family>, dose_n_<family>   for each family present
        dose_drop            -- mean over WEIGHTED families only (back-compat)
        degraded_n           -- total weighted-family observations (back-compat)
        families_missing     -- families with no cells on disk

    Absent cells yield None rather than 0.0: "no data" and "no effect" must not
    collapse, or an ungenerated family silently reads as a non-discriminating
    item.
    """
    observed = defaultdict(lambda: defaultdict(list))
    conditions = (TIER1_CLEAN_CONDITION, *TIER1_DEFECT_FAMILIES.values())
    base = eval_root / "outputs" / TIER1_ROOT / passage_id
    for model in TIER1_DISCRIMINATION_MODELS:
        for condition in conditions:
            path = base / model / condition / "scores_target_llama.json"
            if not path.exists():
                continue
            for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                item_id = str(item.get("id") or item.get("passage_id") or "")
                is_open = item_id.endswith("-open")
                if TIER1_SCORING_FORM == "open" and not is_open:
                    continue
                base_id = item_id.removesuffix("-open").removesuffix("-mcq")
                value = item.get("llm_score") if is_open else item.get("direct_correct")
                if value is not None:
                    observed[base_id][condition].append(float(value))

    metrics = {}
    for base_id, cells in observed.items():
        clean = cells.get(TIER1_CLEAN_CONDITION) or []
        if not clean:
            continue
        clean_accuracy = sum(clean) / len(clean)

        entry = {"clean_accuracy": clean_accuracy, "clean_n": len(clean)}
        missing = []
        weighted_values = []
        for family, condition in TIER1_DEFECT_FAMILIES.items():
            values = cells.get(condition) or []
            if values:
                entry[f"dose_drop_{family}"] = clean_accuracy - sum(values) / len(values)
                entry[f"dose_n_{family}"] = len(values)
                if family in TIER1_WEIGHTED_FAMILIES:
                    weighted_values.extend(values)
            else:
                entry[f"dose_drop_{family}"] = None
                entry[f"dose_n_{family}"] = 0
                missing.append(family)

        entry["families_missing"] = missing
        # Back-compat aggregate over WEIGHTED families only, so adversarial
        # cannot move `selection_score` by the back door.
        entry["dose_drop"] = (
            clean_accuracy - sum(weighted_values) / len(weighted_values)
            if weighted_values else None
        )
        entry["degraded_n"] = len(weighted_values)
        metrics[base_id] = entry
    # The ladder fit is a generated cross-passage artifact, while the 30%-dose
    # cells above are loaded passage-by-passage. Merge them here so every
    # consumer of empirical metrics receives the same p/s_i evidence.
    for base_id, families in load_tier1_sensitivity(eval_root).items():
        entry = metrics.setdefault(base_id, {
            "clean_accuracy": None,
            "clean_n": 0,
            "dose_drop": None,
            "degraded_n": 0,
            "families_missing": list(TIER1_DEFECT_FAMILIES),
            **{
                key: value
                for family in TIER1_DEFECT_FAMILIES
                for key, value in (
                    (f"dose_drop_{family}", None),
                    (f"dose_n_{family}", 0),
                )
            },
        })
        entry["sensitivity"] = families
    return metrics


def tier1_collision_features(row: dict, quality: dict, empirical: dict) -> dict:
    """Auditable quality/difficulty/discrimination features for one candidate."""
    base_id = row["base_id"]
    canonical_id = base_id.split("#", 1)[0]
    metadata = quality.get(base_id) or quality.get(canonical_id) or {}
    evidence = empirical.get(base_id) or empirical.get(canonical_id) or {}
    clean_accuracy = evidence.get("clean_accuracy")
    dose_drop = evidence.get("dose_drop")
    relevancy = float(metadata.get("question_relevancy") or 0.0)
    capture = float(metadata.get("information_capture") or 0.0)
    quality_score = (relevancy + capture) / 20.0
    source_difficulty = float(metadata.get("difficulty_value") or 0.0)

    # Maximum at clean accuracy .65: difficult enough to avoid ceiling, but not
    # so hard that a broken/floor item masquerades as discrimination.
    clean_for_target = 0.65 if clean_accuracy is None else clean_accuracy
    difficulty_fit = max(0.0, 1.0 - abs(clean_for_target - 0.65) / 0.65)
    # [2026-08-17] PRIMARY selector: permutation p (gate) + partially pooled
    # item sensitivity s_i (score). Legacy slope-only artifacts remain readable,
    # but newly generated schema-v2 artifacts carry s_i explicitly.
    sensitivity = (evidence.get("sensitivity") or {})
    slopes = {f: (sensitivity.get(f) or {}).get("slope") for f in TIER1_DEFECT_FAMILIES}
    s_values = {f: (sensitivity.get(f) or {}).get("s_i") for f in TIER1_DEFECT_FAMILIES}
    for family in TIER1_DEFECT_FAMILIES:
        if s_values[family] is None and slopes[family] is not None:
            # Schema-v1 compatibility only. Its slope uses dose (higher=worse),
            # whereas s_i uses quality (higher=better), hence the sign flip.
            s_values[family] = -slopes[family]
    pvals = {f: (sensitivity.get(f) or {}).get("p") for f in TIER1_DEFECT_FAMILIES}
    # A family counts as evidence only if it clears the gate AND points the right
    # way. p alone is not enough: the permutation test is one-sided on the slope,
    # so a strongly POSITIVE slope (an item that gets easier as quality drops)
    # would otherwise sail through on p near 1.0 being "not small".
    gated = {
        f: (s_values[f] is not None and pvals[f] is not None
            and pvals[f] <= TIER1_P_GATE and s_values[f] > 0)
        for f in TIER1_DEFECT_FAMILIES
    }
    weighted_s = [
        s_values[f] for f in TIER1_WEIGHTED_FAMILIES
        if gated.get(f) and s_values[f] is not None
    ]
    # Strongest gated sensitivity across weighted families. Magnitude, not
    # consistency: this is the quantity Fisher information consumes.
    best_s_i = max(weighted_s) if weighted_s else None
    n_gated = sum(1 for f in TIER1_WEIGHTED_FAMILIES if gated.get(f))

    family_drops = {
        family: evidence.get(f"dose_drop_{family}")
        for family in TIER1_DEFECT_FAMILIES
    }
    weighted = [
        family_drops[family]
        for family in TIER1_WEIGHTED_FAMILIES
        if family_drops.get(family) is not None
    ]
    drop_for_score = sum(weighted) / len(weighted) if weighted else 0.0

    # Prefer items that respond to BOTH weighted families over ones that spike
    # on a single family, which is more likely idiosyncratic than adequacy-
    # sensitive. Small, so it breaks near-ties rather than reordering the field.
    both_families = all(
        family_drops.get(family) is not None and family_drops[family] > 0
        for family in TIER1_WEIGHTED_FAMILIES
    )

    # This composite is deliberately SECONDARY. p and s_i live only in the
    # primary rank tuple, so no quality/difficulty feature can compensate for a
    # failed evidence gate and s_i cannot leak into both sides of the ordering.
    dose_term = 3.0 * drop_for_score
    dose_basis = "dose_drop_secondary"

    composite = (
        dose_term
        + quality_score
        + 0.75 * difficulty_fit
        + 0.25 * min(source_difficulty, 1.0)
        + (0.15 if both_families else 0.0)
    )

    features = {
        "needs_review": bool(metadata.get("needs_review")),
        "answer_not_fully_in_passage": bool(row["window"].get("answer_not_fully_in_passage")),
        "quality_score": quality_score,
        "source_difficulty": source_difficulty,
        "clean_accuracy": clean_accuracy,
        "dose_drop": dose_drop,
        "difficulty_fit": difficulty_fit,
        "selection_score": composite,
        "question": metadata.get("question") or row["entry"].get("open", {}).get("Q"),
        "clean_n": evidence.get("clean_n", 0),
        "degraded_n": evidence.get("degraded_n", 0),
        "scoring_form": TIER1_SCORING_FORM,
        "responds_to_both_weighted_families": both_families,
        "dose_basis": dose_basis,
        "best_s_i": best_s_i,
        "best_slope": min(
            (slopes[f] for f in TIER1_WEIGHTED_FAMILIES
             if gated.get(f) and slopes[f] is not None),
            default=None,
        ),
        "n_gated_families": n_gated,
        "passes_p_gate": bool(best_s_i is not None),
        # Derived from the drops actually seen, not read back from `evidence`:
        # a caller that assembles evidence by another route would otherwise get
        # a silently empty list and read "no data" as "nothing missing".
        "families_missing": [
            family for family, drop in family_drops.items() if drop is None
        ],
    }
    # Per-family detail. `adversarial` is present here for inspection but is NOT
    # in TIER1_WEIGHTED_FAMILIES, so it does not enter `selection_score`.
    for family in TIER1_DEFECT_FAMILIES:
        features[f"dose_drop_{family}"] = family_drops.get(family)
        features[f"dose_n_{family}"] = evidence.get(f"dose_n_{family}", 0)
        features[f"slope_{family}"] = slopes.get(family)
        features[f"s_i_{family}"] = s_values.get(family)
        features[f"se_s_i_{family}"] = (
            sensitivity.get(family) or {}
        ).get("se_s_i")
        features[f"p_{family}"] = pvals.get(family)
        features[f"gated_{family}"] = bool(gated.get(family))
    return features


def tier1_primary_rank(features: dict) -> tuple:
    """Primary p/s_i evidence rank; larger tuples are always preferred.

    p is intentionally a gate, not a continuous score. Among passing items,
    cross-family replication wins first and the strongest gated s_i wins next.
    Adversarial remains audit-only and cannot move the rank.
    """
    best_s_i = features.get("best_s_i")
    return (
        bool(features.get("passes_p_gate")),
        features.get("n_gated_families") or 0,
        float(best_s_i) if best_s_i is not None else float("-inf"),
    )


def tier1_collision_secondary_rank(features: dict) -> tuple:
    """Existing auditable collision features, used only after p/s_i."""
    clean = features["clean_accuracy"]
    drop = features["dose_drop"]
    return (
        not features["needs_review"],
        not features["answer_not_fully_in_passage"],
        clean is None or clean >= 0.50,
        drop is None or drop >= 0.0,
        drop is not None and drop > 0.0,
        bool(features.get("responds_to_both_weighted_families")),
        features["selection_score"],
        features["quality_score"],
        features["source_difficulty"],
    )


def tier1_collision_rank(features: dict) -> tuple:
    """Global/collision rank: p+s_i primary, collision features secondary."""
    return tier1_primary_rank(features) + tier1_collision_secondary_rank(features)


def rank_tier1_questions(candidates, quality_by_passage, empirical_by_passage):
    """Return a deterministic best-to-worst ranking of every translated item."""
    scored = []
    for source_index, row in enumerate(candidates):
        features = tier1_collision_features(
            row,
            quality_by_passage[row["passage_id"]],
            empirical_by_passage[row["passage_id"]],
        )
        scored.append((tier1_collision_rank(features), -source_index, row, features))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    ranking = []
    for rank, (_key, _tie, row, features) in enumerate(scored, start=1):
        window = row["window"]
        ranking.append({
            "rank": rank,
            "passage_id": row["passage_id"],
            "base_id": row["base_id"],
            "content_id": window.get("content_id"),
            "window_item_key": window.get("key"),
            "window": list(window.get("window") or []),
            "evidence_tier": (
                f"p_gated_{features['n_gated_families']}_families"
                if features.get("passes_p_gate") else "not_p_gated"
            ),
            **features,
        })
    return ranking


def load_tier1_passage(eval_root: Path, passage_id: str, rel: str):
    d = _tier1_variant_dir(eval_root, passage_id, rel)
    if d is None:
        return None
    return _pick(
        d, "passage_target_pseudonymized.txt", "passage_target_decanonicalized.txt"
    ).read_text(encoding="utf-8").strip()


def parse_tier1_verses(text: str, metadata: dict) -> list[tuple[str, str]]:
    """Split a tier-1 target passage with the same sequential marker rule as its map.

    Chapter 1 is printed as the chapter number in NIV-style source text, and the
    two cross-chapter passages restart at verse 1.  A generic numeric parser
    mistakes those chapter markers (and prices/ages) for verse numbers.
    """
    raw = [(int(match.group(1)), match) for match in _TIER1_MARKER.finditer(text)]
    chapters = list(range(int(metadata["chapter_start"]), int(metadata["chapter_end"]) + 1))
    chapter_index = 0
    current = chapters[0]
    accepted = []
    for index, (number, match) in enumerate(raw):
        following = raw[index + 1][0] if index + 1 < len(raw) else None
        next_chapter = chapters[chapter_index + 1] if chapter_index + 1 < len(chapters) else None
        if index == 0 and int(metadata["verse_start"]) == 1 and number == current:
            label = f"{current}:1"
        elif next_chapter is not None and number == next_chapter and following is not None and following < number:
            chapter_index += 1
            current = next_chapter
            label = f"{current}:1"
        else:
            label = f"{current}:{number}"
        accepted.append((label, match))
    want_first = f"{metadata['chapter_start']}:{metadata['verse_start']}"
    labels = [label for label, _ in accepted]
    if not labels or labels[0] != want_first:
        raise ValueError(f"verse parse mismatch for {metadata['id']}: first={labels[:1]}, expected {want_first}")
    verses = []
    for index, (label, marker) in enumerate(accepted):
        end = accepted[index + 1][1].start() if index + 1 < len(accepted) else len(text)
        verse_text = text[marker.end():end].strip()
        if not verse_text:
            raise ValueError(f"empty parsed verse {label} for {metadata['id']}")
        verses.append((label, verse_text))
    return verses


def build_tier1_qa_item(passage_id: str, entry: dict, qtype: str, *, base_id: str) -> QAItem:
    record = entry[qtype]
    kwargs = dict(
        id=record["passage_id"],
        passage_id=passage_id,
        passage_reference=record.get("passage_reference"),
        question_text=record["Q"],
        question_type=qtype,
        form_group_id=base_id,
        automatic_form=qtype,
        expected_answer="",
        required_keywords=list(record.get("required_keywords") or []),
        optional_keywords=list(record.get("optional_keywords") or []),
    )
    if qtype == "open":
        kwargs.update(expected_answer=str(record.get("A") or ""), mcq_choices=[])
    else:
        options = record.get("A") or {}
        correct = str(record.get("correct") or "A").strip()[:1]
        kwargs.update(
            mcq_choices=[options.get(letter, "") for letter in "ABCD"],
            mcq_correct_choice=correct,
            expected_answer=options.get(correct, ""),
        )
    return QAItem(**kwargs)


def partition_tier1_windows(rows: list[dict], groups: int = TIER1_GROUP_COUNT) -> list[dict]:
    """Assign contiguous windows to eight buckets, sizes differing by at most one."""
    quotient, remainder = divmod(len(rows), groups)
    cursor = 0
    out = []
    for group in range(1, groups + 1):
        size = quotient + (1 if group <= remainder else 0)
        for row in rows[cursor:cursor + size]:
            out.append({**row, "group_index": group, "sequence_index": cursor})
            cursor += 1
    return out


def build_tier1_pool(eval_root: Path, mcq_fraction: float, seed: int):
    """Build the 1-QA-per-unique-window pool on the translated/window intersection."""
    metadata = load_tier1_metadata(eval_root)
    window_candidates = defaultdict(list)
    for window in load_tier1_windows(eval_root):
        window_candidates[window["content_id"]].append(window)

    candidates = []
    translated_count = 0
    unmatched = []
    quality_by_passage = {}
    empirical_by_passage = {}
    for passage in metadata:
        passage_id = passage["id"]
        quality_by_passage[passage_id] = load_tier1_quality_metadata(eval_root, passage_id)
        empirical_by_passage[passage_id] = load_tier1_empirical_metrics(eval_root, passage_id)
        qa = load_tier1_qa(eval_root, passage_id)
        for base_id, entry in qa.items():
            translated_count += 1
            content_id, occurrence = _tier1_content_id(base_id)
            matches = window_candidates.get(content_id) or []
            if not matches:
                unmatched.append(base_id)
                continue
            window = matches[min(occurrence, len(matches) - 1)]
            candidates.append({
                "passage_id": passage_id,
                "base_id": base_id,
                "entry": entry,
                "window": window,
            })

    question_ranking = rank_tier1_questions(
        candidates, quality_by_passage, empirical_by_passage
    )

    # Choose one question per exact window. Quality gates precede an auditable
    # composite of dose sensitivity, clean difficulty fit, and source QA scores.
    unique = []
    grouped = defaultdict(list)
    group_order = []
    for row in candidates:
        key = (row["passage_id"], tuple(row["window"]["window_ordinals"]))
        if key not in grouped:
            group_order.append(key)
        grouped[key].append(row)
    collisions = []
    collision_decisions = []
    for key in group_order:
        rows = grouped[key]
        scored = [
            (
                tier1_collision_rank(features := tier1_collision_features(
                    row,
                    quality_by_passage[row["passage_id"]],
                    empirical_by_passage[row["passage_id"]],
                )),
                -index,  # deterministic source-order tie-break
                row,
                features,
            )
            for index, row in enumerate(rows)
        ]
        fingerprints = {
            (
                str(row["entry"].get("open", {}).get("Q") or "").strip(),
                str(row["entry"].get("open", {}).get("A") or "").strip(),
            )
            for row in rows
        }
        if len(rows) > 1 and len(fingerprints) == 1:
            _rank, _tie, chosen, chosen_features = scored[0]
            selection_reason = "exact_duplicate_first_copy"
        else:
            _rank, _tie, chosen, chosen_features = max(
                scored, key=lambda item: (item[0], item[1])
            )
            selection_reason = "p_si_primary_collision_features_secondary"
        unique.append(chosen)
        rejected = []
        for _candidate_rank, _candidate_tie, row, features in scored:
            if row is chosen:
                continue
            collisions.append(row)
            rejected.append({
                "base_id": row["base_id"],
                "window_item_key": row["window"].get("key"),
                **features,
            })
        if rejected:
            collision_decisions.append({
                "passage_id": chosen["passage_id"],
                "window": list(chosen["window"]["window"]),
                "selection_reason": selection_reason,
                "chosen": {
                    "base_id": chosen["base_id"],
                    "window_item_key": chosen["window"].get("key"),
                    **chosen_features,
                },
                "rejected": rejected,
            })

    entries = {row["base_id"]: row["entry"] for row in unique}
    selected_ids = set(entries)
    for ranked in question_ranking:
        ranked["selected_for_pilot_window"] = ranked["base_id"] in selected_ids
    types = choose_question_types(entries, mcq_fraction, seed)
    planned = partition_tier1_windows(unique)
    qa_rows, window_rows = [], []
    for row in planned:
        qtype = types[row["base_id"]]
        qa_item = build_tier1_qa_item(
            row["passage_id"], row["entry"], qtype, base_id=row["base_id"]
        )
        qa_rows.append(qa_item)
        window = row["window"]
        window_rows.append(dict(
            qa_item_id=qa_item.id,
            source_passage_id=row["passage_id"],
            content_id=window["content_id"],
            window_key="|".join(window["window"]),
            group_index=row["group_index"],
            sequence_index=row["sequence_index"],
            window_ordinals=list(window["window_ordinals"]),
            verse_numbers=list(window["window"]),
        ))
    return qa_rows, window_rows, {
        "mapped": len(load_tier1_windows(eval_root)),
        "translated": translated_count,
        "unmatched": unmatched,
        "collisions": collisions,
        "collision_decisions": collision_decisions,
        "question_ranking": question_ranking,
        "unique": len(unique),
        "group_sizes": Counter(row["group_index"] for row in planned),
    }


# ------------------------------------------------- chapter-level type selection

def _open_suitability_key(entry: dict, seed: int):
    """Lower = better OPEN candidate: short, keyword-matchable answer."""
    o = entry.get("open") or {}
    ans = str(o.get("A") or "")
    length = len(ans.split()) or len(ans)
    n_kw = len(o.get("required_keywords") or [])
    tiebreak = int(hashlib.md5(f"{seed}:{o.get('passage_id')}".encode()).hexdigest(), 16)
    return (length, -n_kw, tiebreak)


def allowed_forms(chapter_qa: dict, rewrites: set) -> dict:
    """{base_id: {'open','mcq'}} -- which FORMS of each item may be delivered.

    [NEW 2026-07-27b] Mirrors the exclusions the LLM grid already applies in
    regen_mcq_tier01.py, which the importer previously did not know about:

      * an MCQ form is deliverable only if it has an entry in mcq_rewrites.json.
        The two retired MCQs (build_rewrites_v2.EXCLUDED_IDS) have no rewrite, so their
        ORIGINAL guessable distractors would otherwise be delivered verbatim.
      * the ambiguous open form (EXCLUDED_OPEN_STEMS) is never deliverable; its MCQ form
        is fine, because the options pin the answer.

    An item with no allowed form is dropped entirely.
    """
    out = {}
    for bid, entry in chapter_qa.items():
        forms = set()
        if "mcq" in entry and f"{bid}-mcq" in rewrites:
            forms.add("mcq")
        if "open" in entry and bid not in EXCLUDED_OPEN_STEMS:
            forms.add("open")
        out[bid] = forms
    return out


def choose_question_types(chapter_qa: dict, mcq_fraction: float = MCQ_FRACTION, seed: int = 2026,
                          allowed: dict = None) -> dict:
    """Assign each item 'open' or 'mcq' once for the whole chapter, targeting
    ~mcq_fraction MCQ. Keeps the best open-shaped items (short, keyword-matchable)
    as open; guarantees at least one open and one mcq per chapter.

    ``allowed`` (from allowed_forms) constrains the choice: items with a single allowed
    form are FORCED to it and excluded from the quota, items with none are omitted from
    the result entirely. Without it the old unconstrained behaviour is preserved.
    """
    if allowed is None:
        allowed = {bid: {"open", "mcq"} for bid in chapter_qa}

    forced = {bid: next(iter(f)) for bid, f in allowed.items() if len(f) == 1}
    free = [bid for bid, f in allowed.items() if len(f) == 2]

    # the quota applies to the freely-assignable items, adjusted for what the forced ones
    # already contribute, so a chapter's MCQ fraction stays on target.
    n_total = len(free) + len(forced)
    target_open = round(n_total * (1 - mcq_fraction))
    k_open = target_open - sum(1 for q in forced.values() if q == "open")
    k_open = max(0, min(k_open, len(free)))
    ranked = sorted(free, key=lambda bid: _open_suitability_key(chapter_qa[bid], seed))
    open_ids = set(ranked[:k_open])

    types = dict(forced)
    types.update({bid: ("open" if bid in open_ids else "mcq") for bid in free})
    # guarantee both formats survive in the chapter when the pool allows it
    if types and free:
        if all(q == "mcq" for q in types.values()):
            types[ranked[0]] = "open"
        elif all(q == "open" for q in types.values()):
            types[ranked[-1]] = "mcq"
    return types


# --------------------------------------------------------------- row builders

def build_qa_item(chapter: int, entry: dict, qtype: str, *, form_group_id=None,
                  automatic_form=None) -> QAItem:
    rec = entry.get(qtype) or entry.get("open") or entry.get("mcq") or {}
    ref = rec.get("passage_reference")
    if qtype == "open":
        o = entry["open"]
        return QAItem(
            passage_id=f"luke{chapter}",
            passage_reference=ref,
            question_text=o["Q"],
            question_type="open",
            form_group_id=form_group_id,
            automatic_form=automatic_form,
            expected_answer=str(o.get("A") or ""),
            required_keywords=list(o.get("required_keywords") or []),
            optional_keywords=list(o.get("optional_keywords") or []),
            mcq_choices=[],
        )
    m = entry["mcq"]
    opts = m.get("A") or {}
    choices = [opts.get(k, "") for k in ("A", "B", "C", "D")]
    correct = (m.get("correct") or "A").strip()[:1]
    return QAItem(
        passage_id=f"luke{chapter}",
        passage_reference=ref,
        question_text=m["Q"],
        question_type="mcq",
        form_group_id=form_group_id,
        automatic_form=automatic_form,
        mcq_choices=choices,
        mcq_correct_choice=correct,
        expected_answer=opts.get(correct, ""),
        required_keywords=list(m.get("required_keywords") or []),
        optional_keywords=list(m.get("optional_keywords") or []),
    )


# ------------------------------------------------------------------- planning

def load_mcq_rewrites(eval_root: Path) -> set:
    """Ids with a hand-written distractor rewrite. An MCQ without one is retired."""
    path = eval_root / "datasets" / "mcq" / MCQ_REWRITES_FILENAME
    if not path.exists():
        sys.exit(f"missing {path} -- required to tell rewritten MCQs from retired ones.\n"
                 f"  run evaluation/scripts/mcq/build_rewrites_v2.py first")
    return set(json.loads(path.read_text(encoding="utf-8")))


def build_plan(eval_root: Path, mcq_fraction: float, seed: int, question_forms="mixed"):
    """Return tier-1 QA, windows, variant passages, and a dry-run summary."""
    if question_forms != "mixed":
        raise ValueError(
            "tier-1 enforces exactly one QA per window; --question-forms must be 'mixed'"
        )
    qa_rows, window_rows, pool = build_tier1_pool(eval_root, mcq_fraction, seed)
    metadata = load_tier1_metadata(eval_root)
    passage_rows, summary = [], []
    missing = []
    for ordinal, passage in enumerate(metadata, start=1):
        pcount = 0
        for condition, rel, name in CONDITIONS:
            text = load_tier1_passage(eval_root, passage["id"], rel)
            if text is None:
                missing.append((passage["id"], condition, rel))
                summary.append(f"  ! {passage['id']} {condition}: MISSING {rel}")
                continue
            # Parse now so a malformed/cross-chapter passage fails before DB writes.
            parse_tier1_verses(text, passage)
            passage_rows.append(dict(
                source_passage_id=passage["id"],
                chapter=ordinal,
                condition=condition,
                name=f"{passage['reference']} — {name}",
                language=LANGUAGE,
                passage_reference=passage["reference"],
                passage_text=text,
                passage_metadata=passage,
            ))
            pcount += 1
        n_items = sum(1 for row in window_rows if row["source_passage_id"] == passage["id"])
        summary.append(f"  {passage['id']}: {n_items:2d} unique-window QA, {pcount} variants")

    n_mcq = sum(row.question_type == "mcq" for row in qa_rows)
    summary.extend([
        "",
        f"  window map: {pool['mapped']} mapped; {pool['translated']} translated; "
        f"{pool['unique']} unique deliverable windows",
        f"  removed {len(pool['collisions'])} extra question(s) sharing an exact window",
        f"  Latin-square group sizes: {dict(sorted(pool['group_sizes'].items()))}",
        f"  QA forms: {n_mcq} mcq / {len(qa_rows) - n_mcq} open",
    ])
    summary.append("  collision choices (quality + empirical discrimination):")
    for decision in pool["collision_decisions"]:
        chosen = decision["chosen"]
        rejected = ", ".join(row["base_id"] for row in decision["rejected"])
        clean = chosen["clean_accuracy"]
        drop = chosen["dose_drop"]
        summary.append(
            f"    {decision['passage_id']} {'/'.join(decision['window'])}: "
            f"keep {chosen['base_id']} over {rejected} "
            f"[{decision['selection_reason']}] "
            f"(quality={chosen['quality_score']:.3f}, "
            f"clean={'NA' if clean is None else f'{clean:.3f}'}, "
            f"dose_drop={'NA' if drop is None else f'{drop:.3f}'}, "
            f"difficulty_fit={chosen['difficulty_fit']:.3f})"
        )
    if pool["unmatched"]:
        summary.append(f"  WARNING: {len(pool['unmatched'])} translated QA had no window map")
    if missing:
        summary.append(f"  MISSING_VARIANTS: {len(missing)}")
    return qa_rows, window_rows, passage_rows, summary, missing


def prune_stale_qa(db, qa_rows):
    """[NEW 2026-07-27b] Delete imported QAItems that the current plan no longer contains
    in that form.

    Needed because the importer skips on (passage_id, question_text) and BOTH forms of an
    item share the same question text -- so an item imported earlier as a retired MCQ is
    skipped, not corrected, by a re-run.

    Deleting a QAItem CASCADEs to assignments and participant responses, so rows with any
    response are reported and kept rather than silently destroying collected data.
    """
    from sqlalchemy import func, select
    from eten_shared.models import Assignment, ParticipantResponse, QAItem

    wanted = {(r.passage_id, r.question_text, r.question_type) for r in qa_rows}
    by_text = {(r.passage_id, r.question_text) for r in qa_rows}
    deleted, blocked = [], []
    for existing in db.scalars(select(QAItem)).all():
        key = (existing.passage_id, existing.question_text)
        if key not in by_text:
            continue                      # not part of the pilot pool at all -- leave alone
        if (existing.passage_id, existing.question_text, existing.question_type) in wanted:
            continue                      # correct form already imported
        n_resp = db.scalar(select(func.count(ParticipantResponse.id))
                           .where(ParticipantResponse.qa_item_id == existing.id)) or 0
        n_assign = db.scalar(select(func.count(Assignment.id))
                             .where(Assignment.qa_item_id == existing.id)) or 0
        if n_resp or n_assign:
            blocked.append((existing.id, existing.passage_id, existing.question_type,
                            n_assign, n_resp))
            continue
        db.delete(existing)
        deleted.append((existing.passage_id, existing.question_type,
                        existing.question_text[:40]))
    return deleted, blocked


# ---------------------------------------------------------------------- upload

def upload(database_url, qa_rows, window_rows, passage_rows, prune=False):
    from sqlalchemy import delete, select

    from eten_shared.database import get_session_factory

    factory = get_session_factory(database_url)
    created = {
        "qa": 0,
        "qa_skip": 0,
        "qa_pruned": 0,
        "window": 0,
        "window_skip": 0,
        "passage": 0,
        "passage_skip": 0,
        "experiment_verse": 0,
        "passage_error": None,
    }

    # QA items and passages are committed in SEPARATE transactions so a passage
    # failure (e.g. experiment_passages table/column missing) surfaces clearly
    # and does not silently roll back the QA import.
    with factory() as db:
        if prune:
            deleted, blocked = prune_stale_qa(db, qa_rows)
            created["qa_pruned"] = len(deleted)
            for pid, qtype, text in deleted:
                print(f"  [prune] deleted stale {qtype.upper():4} {pid}: {text}")
            for iid, pid, qtype, na, nr in blocked:
                print(f"  [prune] KEPT {qtype.upper()} {pid} ({iid}): "
                      f"{na} assignment(s), {nr} response(s) would CASCADE -- delete manually "
                      f"if you are sure")
            db.flush()
        qa_id_map = {}
        for item in qa_rows:
            planned_id = item.id
            exists = db.get(QAItem, planned_id) or db.scalar(
                select(QAItem).where(
                    QAItem.passage_id == item.passage_id,
                    QAItem.question_text == item.question_text,
                    QAItem.question_type == item.question_type,
                )
            )
            if exists:
                exists.form_group_id = item.form_group_id
                exists.automatic_form = item.automatic_form
                qa_id_map[planned_id] = exists.id
                created["qa_skip"] += 1
                continue
            db.add(item)
            qa_id_map[planned_id] = planned_id
            created["qa"] += 1
        db.flush()
        normalized_windows = [
            {**row, "qa_item_id": qa_id_map[row["qa_item_id"]]} for row in window_rows
        ]
        wanted_window_qa = {row["qa_item_id"] for row in normalized_windows}
        # Remove stale window definitions from a previous tier-1 pool build;
        # QA rows themselves remain protected by the explicit prune flag.
        existing_windows = list(db.scalars(select(ExperimentWindow)).all())
        for existing in existing_windows:
            if existing.qa_item_id not in wanted_window_qa:
                db.delete(existing)
            else:
                # Move current positions out of the non-negative range before
                # re-numbering, so a changed pool cannot transiently violate
                # the global unique sequence constraint during the upsert.
                existing.sequence_index = -(existing.sequence_index + 1)
        db.flush()
        for row in normalized_windows:
            exists = db.scalar(select(ExperimentWindow).where(
                ExperimentWindow.qa_item_id == row["qa_item_id"]
            ))
            if exists:
                for key, value in row.items():
                    setattr(exists, key, value)
                created["window_skip"] += 1
            else:
                db.add(ExperimentWindow(**row))
                created["window"] += 1
        db.commit()

    try:
        with factory() as db:
            for p in passage_rows:
                p = dict(p)
                metadata = p.pop("passage_metadata")
                exists = db.scalar(
                    select(ExperimentPassage).where(
                        ExperimentPassage.source_passage_id == p["source_passage_id"],
                        ExperimentPassage.condition == p["condition"],
                        ExperimentPassage.language == p["language"],
                    )
                )
                if exists:
                    exists.name = p["name"]
                    exists.passage_reference = p["passage_reference"]
                    exists.passage_text = p["passage_text"]
                    created["passage_skip"] += 1
                    experiment_passage = exists
                else:
                    experiment_passage = ExperimentPassage(**p)
                    db.add(experiment_passage)
                    db.flush()
                    created["passage"] += 1

                parsed_verses = parse_tier1_verses(p["passage_text"], metadata)
                db.execute(
                    delete(ExperimentPassageVerse).where(
                        ExperimentPassageVerse.experiment_passage_id
                        == experiment_passage.id
                    )
                )
                db.flush()
                db.add_all(
                    [
                        ExperimentPassageVerse(
                            experiment_passage_id=experiment_passage.id,
                            verse_number=verse[0],
                            position=position,
                            text=verse[1],
                        )
                        for position, verse in enumerate(parsed_verses, start=1)
                    ]
                )
                created["experiment_verse"] += len(parsed_verses)
            db.commit()
    except Exception as exc:  # noqa: BLE001 - surface the real cause to the user
        created["passage"] = 0
        created["passage_error"] = f"{type(exc).__name__}: {exc}"

    return created


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-root", required=True, type=Path,
                    help="path to eten-whatsapp-bot/evaluation")
    ap.add_argument("--mcq-fraction", type=float, default=MCQ_FRACTION)
    ap.add_argument(
        "--question-forms",
        choices=("mixed", "both", "mcq", "open"),
        default="mixed",
        help=("forms to import: mixed keeps the existing ~75/25 selection; both imports "
              "both available forms; mcq/open imports only that form (default: mixed)"),
    )
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--database-url", default=None, help="overrides DATABASE_URL env")
    ap.add_argument("--dry-run", action="store_true", help="build + print the plan, no DB writes")
    ap.add_argument("--prune-stale-qa", action="store_true",
                    help="delete already-imported QAItems whose form is now retired (an earlier "
                         "import could deliver a retired MCQ with its ORIGINAL distractors). "
                         "The (passage_id, question_text) skip means a plain re-run will NOT "
                         "replace them, because both forms of an item share the same question "
                         "text. Refuses if the row has assignments/responses (FK CASCADE).")
    args = ap.parse_args()

    args.eval_root = args.eval_root.expanduser().resolve()
    validate_eval_root(args.eval_root)
    print(f"eval-root: {args.eval_root}")

    qa_rows, window_rows, passage_rows, summary, missing = build_plan(
        args.eval_root, args.mcq_fraction, args.seed, args.question_forms
    )

    print("Pilot import plan")
    print("\n".join(summary))
    total_mcq = sum(1 for r in qa_rows if r.question_type == "mcq")
    print(f"\nTOTAL: {len(qa_rows)} QA items "
          f"({total_mcq} mcq / {len(qa_rows) - total_mcq} open, "
          f"{total_mcq / max(len(qa_rows),1):.0%} mcq), {len(window_rows)} windows, "
          f"{len(passage_rows)} passage variants")

    if args.dry_run:
        print("\n[dry-run] no database writes.")
        return

    if missing:
        sys.exit(
            f"REFUSING TO WRITE: {len(missing)} required tier-1 variants are missing. "
            "Dry-run output lists them; generate those outputs first."
        )

    result = upload(
        args.database_url, qa_rows, window_rows, passage_rows, prune=args.prune_stale_qa
    )
    print(f"\nUploaded: {result['qa']} QA items ({result['qa_skip']} already present), "
          f"{result['passage']} passages ({result['passage_skip']} already present).")
    if result.get("passage_error"):
        print(f"\n*** PASSAGE IMPORT FAILED: {result['passage_error']}\n"
              f"    Likely the experiment_passages table or its 'name' column is missing.\n"
              f"    Re-run supabase/migrations/experiment_plan_cells.sql, then re-run this import.")
    print(f"Experiment passages contain {result['experiment_verse']} verse rows.")
    print(f"Experiment windows: {result['window']} created, "
          f"{result['window_skip']} refreshed.")


if __name__ == "__main__":
    sys.exit(main())
