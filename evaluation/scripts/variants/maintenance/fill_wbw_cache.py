#!/usr/bin/env python3
"""Pre-fill the google_word_by_word token cache from a machine Google is not blocking.

google_word_by_word looks each whitespace token up on Google's free endpoint and
caches the answer in evaluation/datasets/perturbations/.wbw_cache_en_zh-CN.json,
keyed on the lower-cased token. When one machine's IP address has been rate
limited, run THIS script somewhere else (e.g. the study VM), copy the cache file
back, and the real build then runs entirely from the cache -- same method, same
translations, no live requests.

Tokens are split exactly the way google_word_by_word splits them (on single
spaces, from the raw passage file), so every key the build will ask for is here.

  python3 evaluation/scripts/variants/maintenance/fill_wbw_cache.py
  python3 evaluation/scripts/variants/maintenance/fill_wbw_cache.py --gap 1.0
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "evaluation" / "scripts" / "scoring" / "current"))
from translation_quality import is_protected_token  # noqa: E402

DEFAULT_CACHE = REPO / "evaluation/datasets/perturbations/.wbw_cache_en_zh-CN.json"
DEFAULT_PASSAGES = REPO / "evaluation/datasets/passages/tier1_bsb"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--passages", type=Path, default=DEFAULT_PASSAGES)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--gap", type=float, default=0.5, help="seconds between live requests")
    args = ap.parse_args()

    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source="en", target="zh-CN")

    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache.exists() else {}
    wanted = []
    for path in sorted(args.passages.glob("*.txt")):
        for word in path.read_text(encoding="utf-8").split(" "):
            if not word or is_protected_token(word):
                continue
            key = word.lower()
            if key not in cache and key not in wanted:
                wanted.append(key)
    print(f"cache has {len(cache)} tokens; {len(wanted)} to look up (~{len(wanted) * (args.gap + 0.3) / 60:.0f} min)")

    failed = []
    for i, key in enumerate(wanted, 1):
        for attempt in range(6):
            try:
                time.sleep(args.gap)
                cache[key] = translator.translate(key)
                break
            except Exception as exc:  # TooManyRequests, network errors
                if attempt == 5:
                    failed.append(key)
                    print(f"  giving up on {key!r}: {type(exc).__name__}")
                else:
                    time.sleep(5 * 2 ** attempt)
        if i % 25 == 0 or i == len(wanted):
            args.cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  {i}/{len(wanted)}")
        if len(failed) >= 10 and len(failed) == i:
            print("every lookup is failing -- this machine is blocked too", file=sys.stderr)
            return 1

    args.cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"done: {len(cache)} tokens cached, {len(failed)} failed -> {args.cache}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
