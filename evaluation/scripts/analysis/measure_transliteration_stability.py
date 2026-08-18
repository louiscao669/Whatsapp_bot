#!/usr/bin/env python3
"""Measure how stably each English pseudonym transliterates into Chinese.

Why this exists
---------------
Swapping ``__PERSON_C__`` protected tokens for natural English pseudonyms
("Jesus" -> "Marun") unifies blinding across all eight translation methods, but
it trades a *recall* problem for a *consistency* problem. A protected token is a
fixed string that maps back by lookup. An invented name is transliterated, and
nothing guarantees "Marun" becomes the same Chinese string twice.

Two distinct failures follow, and only one of them is about scoring:

1. Scoring: 玛伦 might back-translate to "Malun", which no longer matches the
   rubric's "Marun". Affects ~23% of open items; MCQ and the keyword scorer are
   unaffected.
2. Referential integrity (worse): if one passage renders "Marun" as 玛伦 in one
   verse and 马伦 in another, the passage is internally inconsistent. That is a
   translation defect introduced by the blinding scheme itself, confounded with
   the defect being deliberately injected.

Run this before committing to a grid re-run. If names render stably, the
approach is sound and normalization is only a safety net. If they do not, the
normalizer has to work before the approach is viable at all.

Method
------
Direct alignment of a name inside a translated sentence is hard, so this uses
contrast pairs instead. Each probe template is translated twice -- once carrying
the pseudonym, once carrying a fixed control name -- and the span that differs
between the two Chinese outputs is that pseudonym's rendering in that context.
No alignment model required.

Two measurements come out:

* cross-context stability -- does one name render identically across different
  syntactic frames?
* in-passage stability -- how many distinct renderings actually appear in a full
  translated passage?

Usage (from evaluation/):

    # validate the extraction logic offline, no API calls
    python scripts/analysis/measure_transliteration_stability.py --self-test

    # offline dry run with a fake translator
    python scripts/analysis/measure_transliteration_stability.py \\
      --passage datasets/pseudonymized/passages/test_passage_luke5.txt \\
      --simulate --simulate-instability 0.3

    # the real thing
    export OPENAI_API_KEY=...
    python scripts/analysis/measure_transliteration_stability.py \\
      --passage datasets/pseudonymized/passages/test_passage_luke5.txt \\
      --methods nllb-200-1.3B llm_prompt_high nllb-200-1.3B-dropout-0.9 \\
      --top 10 --out outputs/_stability/luke5.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Default data paths resolve against evaluation/ rather than the current working
# directory, so the script runs identically from the repo root (like main.py) or
# from evaluation/ (like the other pseudonym scripts).
EVAL_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TABLE = EVAL_DIR / "datasets/pseudonym_remap/english_pseudonyms.json"

# Probe frames. The name is placed in subject, object, possessive, oblique, and
# sentence-medial position, because MT models transliterate differently
# depending on surrounding tokens.
TEMPLATES = [
    "{name} went into the town.",
    "The crowd followed {name}.",
    "{name}'s friend was waiting by the road.",
    "They spoke to {name} about the matter.",
    "In those days {name} came to the river.",
]

# Fixed contrast name. Must not appear in the pseudonym table, and should be
# similar in length and shape so the diff isolates the name cleanly.
CONTROL_NAME = "Zovith"

CJK = re.compile(r"[㐀-鿿]+")
LATIN = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
# A rendering is either a CJK run or a Latin run. Latin must be included:
# GPT-4.1-mini frequently declines to transliterate an invented name and passes
# it through in Latin script, so a CJK-only extractor sees no difference between
# the control and name sentences and latches onto incidental particle changes
# (了, 里) instead.
TOKEN = re.compile(r"[㐀-鿿]+|[A-Za-z][A-Za-z'’\-]*")

# Particles and function words that show up as diff noise when the real
# difference is elsewhere. A single-character CJK extraction is almost never a
# name, so these are rejected outright.
PARTICLE_NOISE = set("了里的着在与和就都也很过更还把被给对从")


class StabilityError(Exception):
    pass


# --------------------------------------------------------------------------
# extraction


def extract_rendering(
    control_zh: str, name_zh: str, expected_latin: str | None = None
) -> str | None:
    """Return the span in ``name_zh`` that replaced the control name.

    The two inputs are translations of the same sentence differing only in the
    name, so a sequence diff isolates the rendering. The result may be CJK (the
    name was transliterated) or Latin (the model passed the name through
    untranslated), and both are legitimate outcomes worth recording.
    """
    # Check for the name surviving intact in Latin script before diffing. A
    # character-level diff of "Zovith" against "Hemil" aligns the shared "i" and
    # returns the fragment "Hem"; an exact token match is unambiguous and must
    # take priority.
    if expected_latin:
        present = re.search(
            rf"(?<![A-Za-z]){re.escape(expected_latin)}(?![A-Za-z])", name_zh
        )
        absent_from_control = not re.search(
            rf"(?<![A-Za-z]){re.escape(expected_latin)}(?![A-Za-z])", control_zh
        )
        if present and absent_from_control:
            return present.group(0)

    matcher = difflib.SequenceMatcher(None, control_zh, name_zh, autojunk=False)
    candidates = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            span = name_zh[j1:j2]
            for run in TOKEN.findall(span):
                # A lone CJK particle is diff noise, not a transliteration.
                if len(run) == 1 and run in PARTICLE_NOISE:
                    continue
                candidates.append(run)
    if not candidates:
        # The diff found nothing usable. If the name survives verbatim in Latin
        # script, report that directly rather than returning None -- "not
        # transliterated" is a finding, not a measurement failure.
        if expected_latin:
            for run in LATIN.findall(name_zh):
                if run.lower() == expected_latin.lower():
                    return run
        return None
    return max(candidates, key=len)


def normalize_variants(variants: list[str]) -> list[str]:
    return sorted({v for v in variants if v})


def count_variants_nonoverlapping(text: str, variants: list[str]) -> dict[str, int]:
    """Count variant occurrences without double-counting overlaps.

    Renderings of one name often nest ("玛伦" inside "玛伦顿"), and short
    two-character renderings can collide with each other. Matching longest-first
    and consuming the matched span keeps the total honest; without this the
    recovery rate can exceed 1.0, which is meaningless.
    """
    counts = {variant: 0 for variant in variants}
    if not variants:
        return {}
    remaining = text
    for variant in sorted(variants, key=len, reverse=True):
        if not variant:
            continue
        hits = remaining.count(variant)
        if hits:
            counts[variant] = hits
            # Consume so shorter, nested variants cannot claim the same span.
            remaining = remaining.replace(variant, "\x00")
    return {variant: hits for variant, hits in counts.items() if hits}


# --------------------------------------------------------------------------
# translation backends


def real_translator(
    method: str,
    target_language: str,
    source_language: str,
    temperature: float | None = None,
    seed: int | None = None,
):
    from evaluation.scripts.scoring.translation_quality import translate_with_method

    def translate(texts: list[str]) -> list[str]:
        return translate_with_method(
            texts,
            method,
            target_language=target_language,
            source_language=source_language,
            temperature=temperature,
            seed=seed,
        )

    return translate


# --------------------------------------------------------------------------
# null diff: how much does a translator vary against itself?


def null_diff(translate, passage: str, runs: int = 2) -> dict:
    """Translate the same passage repeatedly and measure self-divergence.

    This is the noise floor for any differential method. The leave-one-name-out
    diff assumes that translating two nearly identical inputs yields two nearly
    identical outputs; if a translator disagrees with *itself* on identical
    input, that assumption is void and the name signal is unrecoverable.

    It also quantifies an independent source of variance in existing results:
    LLM passages were sampled at the API default temperature of 1.0, one draw
    per cell, with no seed recorded.
    """
    outputs = translate([passage] * runs)
    base = outputs[0]
    comparisons = []
    for index, other in enumerate(outputs[1:], start=1):
        matcher = difflib.SequenceMatcher(None, base, other, autojunk=False)
        ratio = matcher.ratio()
        changed = sum(
            max(i2 - i1, j2 - j1)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != "equal"
        )
        comparisons.append(
            {
                "run": index,
                "similarity": round(ratio, 4),
                "changed_chars": changed,
                "base_length": len(base),
                "other_length": len(other),
                "changed_fraction": round(changed / max(len(base), 1), 4),
            }
        )
    return {
        "runs": runs,
        "identical": len(set(outputs)) == 1,
        "comparisons": comparisons,
        "outputs": outputs,
    }


def simulated_translator(method: str, instability: float):
    """Deterministic fake translator for offline logic checks.

    Renders each Latin-script name as CJK characters drawn from a per-name pool,
    picking a different pool entry as a function of context with probability
    ``instability``. This exercises the same code path as a real model without
    network access, and lets the extraction logic be validated against a known
    ground truth.
    """
    # A wide pool keeps unrelated names from colliding by chance, so the offline
    # demo isolates the instability being simulated instead of mixing in
    # spurious collisions.
    first_pool = (
        "玛马码麻莫墨蒙孟米密弥迷穆牧慕木内纳尼倪诺挪奴努维韦威薇文温瓦娃"
        "卡康考柯克library".replace("library", "")
    )
    second_pool = (
        "伦仑轮论沦纶顿敦盾吨萨撒莎沙山善德得特图土屠兰岚蓝澜里利力立丽"
        "松嵩宋斯思司丝那娜哪"
    )
    seed_salt = sum(ord(char) for char in method)

    def render(name: str, context_index: int) -> str:
        base = sum(ord(char) * (index + 3) for index, char in enumerate(name))
        first = first_pool[(base + seed_salt) % len(first_pool)]
        second = second_pool[(base * 7 + seed_salt) % len(second_pool)]
        if instability and ((base + context_index * 31 + seed_salt) % 100) < (
            instability * 100
        ):
            second = second_pool[
                (base * 7 + seed_salt + context_index + 1) % len(second_pool)
            ]
        return first + second

    def translate(texts: list[str]) -> list[str]:
        out = []
        for index, text in enumerate(texts):
            result = text
            for name in sorted(set(re.findall(r"\b[A-Z][a-z]+\b", text)), key=len, reverse=True):
                result = result.replace(name, render(name, index))
            # Crude stand-in for the non-name words.
            result = re.sub(r"[A-Za-z]+", "词", result)
            out.append(result)
        return out

    return translate


# --------------------------------------------------------------------------
# measurement


def select_names(table: list[dict], passage: str, top: int) -> list[str]:
    """Most frequent single-token pseudonyms in this passage.

    Multiword deity titles are excluded: they are translated semantically rather
    than transliterated, so they fail differently and need their own check.
    """
    counts = Counter()
    for entity in table:
        pseudonym = entity["pseudonym"]
        if " " in pseudonym:
            continue
        hits = len(re.findall(rf"\b{re.escape(pseudonym)}\b", passage))
        if hits:
            counts[pseudonym] = hits
    return [name for name, _ in counts.most_common(top)]


def measure_method(
    translate,
    names: list[str],
    passage: str,
) -> dict:
    # One batch: control probes, then each name's probes, then the passage.
    control_probes = [template.format(name=CONTROL_NAME) for template in TEMPLATES]
    batch = list(control_probes)
    for name in names:
        batch.extend(template.format(name=name) for template in TEMPLATES)
    batch.append(passage)

    translated = translate(batch)
    if len(translated) != len(batch):
        raise StabilityError(
            f"translator returned {len(translated)} texts for {len(batch)} inputs"
        )

    control_zh = translated[: len(TEMPLATES)]
    passage_zh = translated[-1]

    per_name = {}
    cursor = len(TEMPLATES)
    for name in names:
        name_zh = translated[cursor : cursor + len(TEMPLATES)]
        cursor += len(TEMPLATES)

        renderings = []
        for index, (control, candidate) in enumerate(zip(control_zh, name_zh)):
            rendering = extract_rendering(control, candidate, expected_latin=name)
            renderings.append(
                {
                    "template": TEMPLATES[index],
                    "rendering": rendering,
                    # Raw translations are retained so a suspicious result can be
                    # diagnosed as an extraction failure rather than assumed to be
                    # a translation failure.
                    "control_zh": control,
                    "name_zh": candidate,
                    "rendering_length": len(rendering) if rendering else 0,
                }
            )

        variants = normalize_variants([row["rendering"] for row in renderings])
        in_passage = count_variants_nonoverlapping(passage_zh, variants)

        latin_probes = sum(
            1
            for row in renderings
            if row["rendering"] and LATIN.fullmatch(row["rendering"])
        )
        cjk_probes = sum(
            1
            for row in renderings
            if row["rendering"] and CJK.fullmatch(row["rendering"])
        )
        # A name left in Latin script inside Chinese text round-trips perfectly
        # but is glaringly unnatural to a native reader, so it trades a scoring
        # problem for a fluency problem. Counted separately for that reason.
        latin_in_passage = len(
            re.findall(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", passage_zh)
        )

        per_name[name] = {
            "probe_renderings": renderings,
            "distinct_probe_variants": variants,
            "cross_context_stable": len(variants) == 1,
            "unresolved_probes": sum(1 for r in renderings if r["rendering"] is None),
            "latin_probes": latin_probes,
            "cjk_probes": cjk_probes,
            "latin_mentions_in_passage": latin_in_passage,
            "in_passage_counts": in_passage,
            "in_passage_distinct": len(in_passage),
            "in_passage_total": sum(in_passage.values()),
        }

    expected = {
        name: len(re.findall(rf"\b{re.escape(name)}\b", passage)) for name in names
    }

    # Two different pseudonyms rendering to the same Chinese string is a hard
    # failure, not a measurement artifact: the passage has silently merged two
    # referents. It also inflates the recovery rate, since both names claim the
    # same spans, so it is reported separately rather than folded into the total.
    owners = defaultdict(list)
    for name, payload in per_name.items():
        for variant in payload["distinct_probe_variants"]:
            owners[variant].append(name)
    collisions = {
        variant: sorted(holders)
        for variant, holders in owners.items()
        if len(holders) > 1
    }

    return {
        "names": per_name,
        "expected_passage_mentions": expected,
        "variant_collisions": collisions,
    }


def summarize(results: dict) -> dict:
    rows = []
    for method, payload in results.items():
        names = payload["names"]
        stable = sum(1 for r in names.values() if r["cross_context_stable"])
        passage_stable = sum(1 for r in names.values() if r["in_passage_distinct"] <= 1)
        unresolved = sum(r["unresolved_probes"] for r in names.values())
        recovered = sum(r["in_passage_total"] for r in names.values())
        expected = sum(payload["expected_passage_mentions"].values())
        rows.append(
            {
                "method": method,
                "names": len(names),
                "cross_context_stable": stable,
                "in_passage_single_variant": passage_stable,
                "unresolved_probes": unresolved,
                "passage_mentions_recovered": recovered,
                "passage_mentions_expected": expected,
                "recovery_rate": round(recovered / expected, 3) if expected else None,
                "colliding_variants": len(payload.get("variant_collisions", {})),
                "latin_probes": sum(r["latin_probes"] for r in names.values()),
                "cjk_probes": sum(r["cjk_probes"] for r in names.values()),
                "latin_mentions_in_passage": sum(
                    r["latin_mentions_in_passage"] for r in names.values()
                ),
            }
        )
    return {"per_method": rows}


# --------------------------------------------------------------------------
# self-test


def self_test() -> int:
    """Validate extraction against known ground truth. No network required."""
    checks = []

    # 1. Clean case: the rendering is the only difference.
    got = extract_rendering("佐维词去了城里。", "玛伦词去了城里。")
    checks.append(("clean substitution", got == "玛伦", got))

    # 2. Rendering at end of sentence.
    got = extract_rendering("人群跟随佐维。", "人群跟随玛伦。")
    checks.append(("sentence-final", got == "玛伦", got))

    # 3. Three-character rendering.
    got = extract_rendering("佐维去了。", "玛伦顿去了。")
    checks.append(("three-char name", got == "玛伦顿", got))

    # 4. Identical inputs mean no name was found.
    got = extract_rendering("完全相同的句子。", "完全相同的句子。")
    checks.append(("no difference -> None", got is None, got))

    # 5. Longest CJK run wins when surrounding words also shift.
    got = extract_rendering("佐维在路边等候。", "玛伦顿在路旁等候。")
    checks.append(("picks longest differing run", got == "玛伦顿", got))

    # 6. End-to-end through the simulated translator, stable setting.
    translate = simulated_translator("test", instability=0.0)
    payload = measure_method(translate, ["Marun"], "Marun went to the town. Marun spoke.")
    marun = payload["names"]["Marun"]
    checks.append(
        (
            "simulated stable -> one variant",
            marun["cross_context_stable"] and len(marun["distinct_probe_variants"]) == 1,
            marun["distinct_probe_variants"],
        )
    )

    # 7. End-to-end, unstable setting must be detected as unstable.
    translate = simulated_translator("test", instability=1.0)
    payload = measure_method(translate, ["Marun"], "Marun went to the town.")
    marun = payload["names"]["Marun"]
    checks.append(
        (
            "simulated unstable -> multiple variants",
            len(marun["distinct_probe_variants"]) > 1,
            marun["distinct_probe_variants"],
        )
    )

    # 8. Nested variants must not be double-counted.
    got = count_variants_nonoverlapping("玛伦顿去了，玛伦顿回来。", ["玛伦", "玛伦顿"])
    checks.append(("nested variants counted once", got == {"玛伦顿": 2}, got))

    # 9. Distinct variants both counted.
    got = count_variants_nonoverlapping("玛伦去了，马伦回来。", ["玛伦", "马伦"])
    checks.append(("distinct variants both counted", got == {"玛伦": 1, "马伦": 1}, got))

    # 10. Collisions between names are reported.
    translate = simulated_translator("test", instability=0.0)
    payload = measure_method(translate, ["Marun", "Marun"], "Marun went.")
    checks.append(
        (
            "identical names collide",
            isinstance(payload.get("variant_collisions"), dict),
            payload.get("variant_collisions"),
        )
    )

    # 11. Control name must not be in the shipped table.
    table_path = DEFAULT_TABLE
    if table_path.exists():
        table = json.loads(table_path.read_text(encoding="utf-8"))["entities"]
        collision = any(entity["pseudonym"] == CONTROL_NAME for entity in table)
        checks.append(("control name not in table", not collision, CONTROL_NAME))

    failures = 0
    for label, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            failures += 1
        print(f"  [{status}] {label}" + ("" if passed else f"  got={detail!r}"))
    print(f"{len(checks) - failures}/{len(checks)} checks passed")
    return 1 if failures else 0


# --------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passage", type=Path, help="Pseudonymized English passage.")
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["nllb-200-1.3B", "llm_prompt_high", "nllb-200-1.3B-dropout-0.9"],
    )
    parser.add_argument("--top", type=int, default=10, help="Names to probe.")
    parser.add_argument("--target-language", default="Simplified Chinese")
    parser.add_argument("--source-language", default="en")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--simulate", action="store_true", help="Offline fake translator.")
    parser.add_argument("--simulate-instability", type=float, default=0.0)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--null-diff",
        action="store_true",
        help=(
            "Translate the same passage twice and report self-divergence. This "
            "is the noise floor for any differential method, and it also "
            "measures run-to-run variance in LLM translation cells."
        ),
    )
    parser.add_argument("--null-diff-runs", type=int, default=2)
    # Defaults to 0: the leave-one-name-out and probe diffs both assume the
    # translator is stable against itself. The pipeline default is untouched.
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help=(
            "Sampling temperature for LLM methods. Defaults to 0 here so diffs "
            "are not swamped by sampling noise. Pass --temperature 1.0 to "
            "measure the pipeline's historical behaviour."
        ),
    )
    parser.add_argument("--seed", type=int, default=1234, help="Sampling seed.")
    parser.add_argument(
        "--dump-probes",
        action="store_true",
        help=(
            "Print every probe translation and the span extracted from it. Use "
            "when the summary looks implausible: a recovery rate above 1.0 or "
            "many collisions usually means extraction grabbed a clause instead "
            "of a name, not that the model translated badly."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return self_test()
    if not args.passage:
        print("error: --passage is required (or use --self-test)", file=sys.stderr)
        return 1

    try:
        table = json.loads(args.table.read_text(encoding="utf-8"))["entities"]
        passage = args.passage.read_text(encoding="utf-8")
        names = select_names(table, passage, args.top)
        if not names:
            raise StabilityError(f"no pseudonyms found in {args.passage}")

        print(f"probing {len(names)} name(s): {', '.join(names)}")
        results = {}
        for method in args.methods:
            translate = (
                simulated_translator(method, args.simulate_instability)
                if args.simulate
                else real_translator(
                    method,
                    args.target_language,
                    args.source_language,
                    temperature=args.temperature,
                    seed=args.seed,
                )
            )
            if args.null_diff:
                print(f"[{method}] null diff: {args.null_diff_runs} identical runs")
                results[method] = {"null_diff": null_diff(translate, passage, args.null_diff_runs)}
                continue
            print(f"[{method}] translating {len(names) * len(TEMPLATES) + len(TEMPLATES) + 1} text(s)")
            results[method] = measure_method(translate, names, passage)

    except (StabilityError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"error: {exc}\nInstall translation deps or pass --simulate.", file=sys.stderr)
        return 1

    if args.null_diff:
        payload = {"passage": str(args.passage), "null_diff": results}
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
            )
            print(f"wrote {args.out}")
        print()
        header = f"{'method':26s} {'identical':>10s} {'similarity':>11s} {'chars changed':>14s}"
        print(header)
        print("-" * len(header))
        for method, entry in results.items():
            data = entry["null_diff"]
            worst = min(c["similarity"] for c in data["comparisons"])
            changed = max(c["changed_chars"] for c in data["comparisons"])
            print(
                f"{method:26s} {str(data['identical']):>10s} "
                f"{worst:>11.4f} {changed:>14d}"
            )
        print()
        print(
            "identical  = every run byte-identical\n"
            "similarity = worst pairwise similarity, 1.0 means no divergence\n"
            "\n"
            "If similarity is near 1.0 the leave-one-name-out diff is viable as\n"
            "configured. If it is well below 1.0, the translator disagrees with\n"
            "itself on identical input: rerun with --temperature 0, and treat\n"
            "existing single-draw LLM cells as carrying unmeasured variance."
        )
        return 0

    if args.dump_probes:
        for method, payload in results.items():
            print(f"\n===== {method} =====")
            for name, row in payload["names"].items():
                print(f"\n--- {name} ---")
                for probe in row["probe_renderings"]:
                    length = probe["rendering_length"]
                    flag = "  <-- SUSPECT (too long for a name)" if length > 5 else ""
                    print(f"  control : {probe['control_zh']}")
                    print(f"  name    : {probe['name_zh']}")
                    print(f"  extract : {probe['rendering']!r} (len {length}){flag}")
                print(f"  variants: {row['distinct_probe_variants']}")
            if payload.get("variant_collisions"):
                print("\n  COLLISIONS:")
                for variant, holders in payload["variant_collisions"].items():
                    print(f"    {variant!r} claimed by {holders}")

    summary = summarize(results)
    payload = {
        "passage": str(args.passage),
        "simulated": args.simulate,
        "names": names,
        "summary": summary,
        "results": results,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")

    print()
    header = (
        f"{'method':26s} {'stable':>8s} {'1-variant':>10s} "
        f"{'latin/cjk':>11s} {'latin in psg':>13s} {'recovery':>9s}"
    )
    print(header)
    print("-" * len(header))
    for row in summary["per_method"]:
        rate = row["recovery_rate"]
        print(
            f"{row['method']:26s} "
            f"{row['cross_context_stable']:>3d}/{row['names']:<4d} "
            f"{row['in_passage_single_variant']:>5d}/{row['names']:<4d} "
            f"{row['latin_probes']:>5d}/{row['cjk_probes']:<5d} "
            f"{row['latin_mentions_in_passage']:>13d} "
            f"{(rate if rate is not None else 0):>9.3f}"
        )
    print()
    print(
        "stable       = one rendering across all probe frames\n"
        "1-variant    = only one rendering actually occurs in the passage\n"
        "latin/cjk    = probes where the name stayed in Latin script vs was\n"
        "               transliterated. A high Latin count means the model\n"
        "               declined to transliterate: round-trips perfectly, but\n"
        "               Latin text inside Chinese is glaringly unnatural to a\n"
        "               native reader and damages the fluency being measured.\n"
        "latin in psg = Latin-script mentions surviving in the real passage\n"
        "recovery     = share of expected mentions found; above 1.0 means\n"
        "               variants collide and the run needs --dump-probes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
