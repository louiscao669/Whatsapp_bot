#!/usr/bin/env python3
"""Make google_word_by_word survivable on long passages: per-token retry + cache.

THE BUG. `google_word_by_word` sends one HTTP request per whitespace token and
raises `TranslationQualityError` on the FIRST failure, discarding every token
translated so far. Unlike the OpenAI stages it gets no `retries` parameter --
`translate_with_method` dispatches straight to it -- so `--retries 2` retries
the WHOLE passage, re-sending every request from scratch.

Success therefore compounds against length, P(ok) = (1-p)^n. Measured on the
2026-08-23 tier-1 batch (run largest-first, so this is not quota exhaustion):

    1239 w FAILED   1108 FAILED   1033 FAILED   665 FAILED   650 FAILED
     517 w FAILED    219 FAILED    138 OK        201 OK

which fits a per-token failure rate around 0.3%: ~50% at 200 words, ~2% at 1239.

THE FIX, two parts:

  1. PER-TOKEN RETRY WITH BACKOFF, then keep the SOURCE token rather than
     aborting. A handful of untranslated English words inside a word-salad
     baseline is a trivial blemish; losing the passage costs the whole cell.
     This makes P(success) ~1 independent of length.

  2. TOKEN CACHE keyed on the lowercased word, in-process and on disk. These
     passages repeat vocabulary heavily, so this cuts request volume several
     fold and shrinks the exposure window proportionally. The disk cache also
     makes a re-run nearly free, which matters because the previous batch
     burned thousands of requests on passages that never completed.

The fallback count is returned via `last_wbw_fallbacks()` and printed, because
silent degradation is exactly the failure mode that made the earlier runs hard
to diagnose. A passage with many fallbacks is not a clean word-salad baseline
and should be inspected before use.

Idempotent. Writes a .bak once.

Usage:
  python3 evaluation/scripts/variants/patch_wbw_resilience.py [--check]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

TARGET = Path("evaluation/scripts/scoring/translation_quality.py")
MARKER = "# --- wbw resilience (patched) ---"

OLD = '''    translator = GoogleTranslator(
        source=source_language,
        target=normalize_target_language(target_language),
    )
    outputs = []
    for text in ensure_texts(texts):
        translated_words = []
        for word in text.split(" "):
            if not word:
                translated_words.append("")
                continue
            if is_protected_token(word):
                translated_words.append(word)
                continue
            try:
                translated_words.append(translator.translate(word.lower()))
            except Exception as exc:
                raise TranslationQualityError(
                    f"Google word-by-word translation failed for token {word!r}: {exc}"
                ) from exc
            if sleep_seconds:
                time.sleep(sleep_seconds)
        outputs.append(" ".join(translated_words))
    return outputs'''

NEW = '''    translator = GoogleTranslator(
        source=source_language,
        target=normalize_target_language(target_language),
    )

    # --- wbw resilience (patched) ---
    cache_path = _wbw_cache_path(source_language, target_language)
    cache = _wbw_load_cache(cache_path)
    attempts = int(os.getenv("WBW_TOKEN_RETRIES", "3"))
    base_delay = float(os.getenv("WBW_RETRY_BASE_DELAY", "0.5"))
    global _WBW_LAST_STATS
    stats = {"tokens": 0, "requests": 0, "cache_hits": 0, "fallbacks": 0,
             "fallback_tokens": []}

    outputs = []
    for text in ensure_texts(texts):
        translated_words = []
        for word in text.split(" "):
            if not word:
                translated_words.append("")
                continue
            if is_protected_token(word):
                translated_words.append(word)
                continue
            stats["tokens"] += 1
            key = word.lower()
            if key in cache:
                stats["cache_hits"] += 1
                translated_words.append(cache[key])
                continue
            rendered = None
            for attempt in range(attempts):
                try:
                    stats["requests"] += 1
                    rendered = translator.translate(key)
                    break
                except Exception:
                    if attempt + 1 >= attempts:
                        break
                    time.sleep(base_delay * (2 ** attempt))
            if rendered is None:
                # Keep the SOURCE token. Aborting here is what cost whole
                # passages before; an untranslated word is survivable damage.
                rendered = word
                stats["fallbacks"] += 1
                if len(stats["fallback_tokens"]) < 25:
                    stats["fallback_tokens"].append(word)
            else:
                cache[key] = rendered
            translated_words.append(rendered)
            if sleep_seconds:
                time.sleep(sleep_seconds)
        outputs.append(" ".join(translated_words))

    _wbw_save_cache(cache_path, cache)
    _WBW_LAST_STATS = stats
    if stats["fallbacks"]:
        print(
            f"  [wbw] {stats['fallbacks']}/{stats['tokens']} tokens kept as "
            f"SOURCE after {attempts} attempts "
            f"({100 * stats['fallbacks'] / max(stats['tokens'], 1):.1f}%): "
            f"{stats['fallback_tokens'][:8]}",
            file=sys.stderr,
        )
    print(
        f"  [wbw] {stats['tokens']} tokens, {stats['requests']} requests, "
        f"{stats['cache_hits']} cache hits "
        f"({100 * stats['cache_hits'] / max(stats['tokens'], 1):.0f}% saved)",
        file=sys.stderr,
    )
    return outputs'''

HELPERS = '''

# --- wbw resilience (patched) ---
# Token cache + fallback accounting for google_word_by_word. Keyed on the
# lowercased token, which is exactly what the translator is asked for, so a hit
# is byte-identical to what the request would have returned.
_WBW_LAST_STATS: dict = {}


def last_wbw_fallbacks() -> dict:
    """Stats from the most recent google_word_by_word call.

    `fallbacks` counts tokens left untranslated after exhausting retries. A
    passage with a high count is NOT a clean word-salad baseline -- inspect it
    before treating it as one.
    """
    return dict(_WBW_LAST_STATS)


def _wbw_cache_path(source_language: str, target_language: str) -> Path:
    override = os.getenv("WBW_CACHE_PATH")
    if override:
        return Path(override)
    safe = f"{source_language}_{normalize_target_language(target_language)}"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", safe)
    return Path("evaluation/datasets/perturbations") / f".wbw_cache_{safe}.json"


def _wbw_load_cache(path: Path) -> dict:
    if os.getenv("WBW_CACHE_DISABLED"):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _wbw_save_cache(path: Path, cache: dict) -> None:
    if os.getenv("WBW_CACHE_DISABLED") or not cache:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass  # a cache failure must never break a translation run

'''


def apply(text: str) -> tuple[str, list[str]]:
    if MARKER in text:
        return text, ["already patched"]
    notes = []
    if OLD not in text:
        raise SystemExit("google_word_by_word body not found -- file drifted; patch by hand")

    anchor = "def google_word_by_word("
    idx = text.index(anchor)
    text = text[:idx] + HELPERS.lstrip("\n") + "\n" + text[idx:]
    notes.append("inserted cache helpers + last_wbw_fallbacks()")

    text = text.replace(OLD, NEW)
    notes.append("per-token retry with backoff; source-token fallback instead of abort")
    notes.append("token cache (in-process + on disk) with request/hit accounting")
    return text, notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args()

    path = args.target
    if not path.exists():
        raise SystemExit(f"{path} not found -- run from the repo root")
    original = path.read_text(encoding="utf-8")
    patched, notes = apply(original)
    for note in notes:
        print(f"  - {note}")
    if patched == original:
        return 0
    if args.check:
        print("\n--check: not written")
        return 0
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        print(f"  - backup -> {backup}")
    path.write_text(patched, encoding="utf-8")
    print(f"  - wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
