#!/usr/bin/env python3
"""Fetch the CUV (Chinese Union Version, 1919, public domain) text of Luke
and produce decanonicalized variants using the same placeholder scheme as the
evaluation pipeline.

Source: bible-api.com parameterized API (/data/cuv/LUK/<chapter>), which
serves the public-domain CUV. (BibleGateway has no public API and its ToS
forbids scraping; bible-api.com is the sanctioned route for CUV.)

Placeholder mapping per chapter = DEFAULT_MAPPING from
decanonicalize_chinese_dataset.py, updated with the union of
`chinese_alias_hints -> placeholder` pairs found in every method cell's
`decanonicalized_metadata.json` (evaluation/outputs/luke{c}/<model-dir>/*/).
Conflicting hints (same Chinese name, different placeholder across methods)
are resolved by majority vote and reported.

Outputs (per chapter, under --out-dir):
  luke{c}_cuv.txt                      canonical, passage-style "N text" markers
  luke{c}_cuv_decanonicalized.txt      placeholder version, same format
  luke{c}_cuv_verses.json              [{verse, text, text_decanonicalized}]
  cuv_decanonicalization_metadata.json mapping + conflicts, all chapters

Usage:
  python evaluation/scripts/data_prep/fetch_cuv_reference.py --chapters 1 2 3 4 5 6 7 8
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.scripts.data_prep.decanonicalize_chinese_dataset import (  # noqa: E402
    DEFAULT_MAPPING,
    replace_text,
)

API_URL = "https://bible-api.com/data/cuv/LUK/{chapter}"

# bible-api.com serves CUV in Traditional Chinese (zh-tw); the evaluation
# pipeline (mapping keys + all model translations) is Simplified. Convert t2s.
try:
    from opencc import OpenCC

    _T2S = OpenCC("t2s")
except ImportError:  # noqa: BLE001
    _T2S = None

# CUV merges some verses (e.g. Luke 1:1-2); merged verses carry this marker.
MERGED_MARKERS = {"併於上節", "并于上节"}


def to_simplified(text: str) -> str:
    if _T2S is None:
        raise RuntimeError(
            "opencc is required for Traditional->Simplified conversion: "
            "pip install opencc-python-reimplemented"
        )
    return _T2S.convert(text)


def fetch_chapter(chapter: int, retries: int = 3) -> list[dict]:
    url = API_URL.format(chapter=chapter)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cuv-reference-fetch"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            verses = data.get("verses") or []
            if not verses:
                raise ValueError(f"no verses in response for {url}")
            out = []
            for v in verses:
                number = v.get("verse")
                text = (v.get("text") or "").strip()
                if number is None or not text:
                    raise ValueError(f"malformed verse entry in {url}: {v}")
                out.append({"verse": int(number), "text": text})
            return out
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch Luke {chapter} from {url}: {last}")


def chapter_mapping(
    root: Path, model_dir: str, chapter: int
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """DEFAULT_MAPPING updated with the union of per-method alias hints."""
    votes: dict[str, Counter] = defaultdict(Counter)
    meta_files = sorted((root / f"luke{chapter}" / model_dir).glob("*/decanonicalized_metadata.json"))
    for path in meta_files:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        entries = (meta.get("canonicalization") or {}).get("mapping") or []
        for entry in entries:
            placeholder = entry.get("placeholder")
            if not placeholder:
                continue
            for hint in entry.get("chinese_alias_hints") or []:
                if hint:
                    votes[hint][placeholder] += 1
    mapping = dict(DEFAULT_MAPPING)
    conflicts: dict[str, list[str]] = {}
    for hint, counter in votes.items():
        if len(counter) > 1:
            conflicts[hint] = [f"{p}:{n}" for p, n in counter.most_common()]
        mapping[hint] = counter.most_common(1)[0][0]
    if not meta_files:
        print(f"warning: no decanonicalized_metadata.json under luke{chapter}/{model_dir}; "
              "falling back to DEFAULT_MAPPING only", file=sys.stderr)
    return mapping, conflicts


def passage_style(verses: list[dict], key: str) -> str:
    return " ".join(f"{v['verse']} {v[key]}" for v in verses if v[key]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapters", type=int, nargs="+", default=list(range(1, 9)))
    parser.add_argument("--root", type=Path, default=Path("evaluation/outputs"))
    parser.add_argument("--model-dir", default="1.7b")
    parser.add_argument("--out-dir", type=Path, default=Path("evaluation/datasets/cuv"))
    parser.add_argument("--sleep", type=float, default=2.5,
                        help="Seconds between API calls (rate limit: 15 req / 30 s).")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, dict] = {}

    for i, chapter in enumerate(args.chapters):
        verses_path = args.out_dir / f"luke{chapter}_cuv_verses.json"
        if verses_path.exists() and not args.force:
            print(f"reuse: {verses_path}")
            continue
        if i > 0 and args.sleep > 0:
            time.sleep(args.sleep)
        print(f"fetch CUV: Luke {chapter}")
        verses = fetch_chapter(chapter)
        mapping, conflicts = chapter_mapping(args.root, args.model_dir, chapter)
        for v in verses:
            v["text_traditional"] = v["text"]
            v["text"] = to_simplified(v["text_traditional"])
            v["merged_with_previous"] = v["text"].strip("。 ") in MERGED_MARKERS
            if v["merged_with_previous"]:
                # CUV folded this verse into the previous one; no standalone
                # text exists. Exclude from verse-level scoring (or score the
                # source verses jointly against the previous CUV verse).
                v["text"] = ""
                v["text_decanonicalized"] = ""
            else:
                v["text_decanonicalized"] = replace_text(v["text"], mapping)

        verses_path.write_text(
            json.dumps(verses, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out_dir / f"luke{chapter}_cuv.txt").write_text(
            passage_style(verses, "text"), encoding="utf-8")
        (args.out_dir / f"luke{chapter}_cuv_decanonicalized.txt").write_text(
            passage_style(verses, "text_decanonicalized"), encoding="utf-8")

        metadata[f"luke{chapter}"] = {
            "n_verses": len(verses),
            "mapping": mapping,
            "conflicts": conflicts,
        }
        if conflicts:
            print(f"  conflicts (majority vote used): {conflicts}", file=sys.stderr)

    if metadata:
        meta_path = args.out_dir / "cuv_decanonicalization_metadata.json"
        existing = {}
        if meta_path.exists():
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        existing.update(metadata)
        meta_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote: {meta_path}")
    print(f"done: {args.out_dir}")
    return 0


if __name__ == "__main__":
    main()
