#!/usr/bin/env python3
"""Passage translation methods for evaluation-quality experiments.

The functions here intentionally keep optional dependencies behind each method.
This lets the evaluation package import even when local translation tools such
as Transformers or deep-translator are not installed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Literal, Optional


SUPPORTED_BASE_METHODS = {
    "google_word_by_word",
    "llm_prompt_low",
    "llm_prompt_medium",
    "llm_prompt_high",
    "helsinki",
    "mBART-50",
    "nllb-200-distilled-600M",
    "nllb-200-1.3B",
}
NLLB_DROPOUT_METHOD_PREFIX = "nllb-200-1.3B-dropout"
DEFAULT_NLLB_DROPOUT_RATES = (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)


class TranslationQualityError(Exception):
    pass


def format_dropout_rate(rate: float) -> str:
    return f"{rate:.1f}"


def nllb_dropout_method_name(rate: float) -> str:
    return f"{NLLB_DROPOUT_METHOD_PREFIX}-{format_dropout_rate(rate)}"


def parse_nllb_dropout_rate(method: str) -> Optional[float]:
    if method == NLLB_DROPOUT_METHOD_PREFIX:
        return None
    prefix = f"{NLLB_DROPOUT_METHOD_PREFIX}-"
    if not str(method or "").startswith(prefix):
        return None
    raw_rate = str(method)[len(prefix) :]
    try:
        rate = float(raw_rate)
    except ValueError as exc:
        raise TranslationQualityError(
            f"NLLB dropout method must end with a numeric rate, got: {method}"
        ) from exc
    validate_nllb_dropout_rate(rate)
    return rate


def is_supported_method(method: str) -> bool:
    if method in SUPPORTED_BASE_METHODS or method == NLLB_DROPOUT_METHOD_PREFIX:
        return True
    try:
        return parse_nllb_dropout_rate(method) is not None
    except TranslationQualityError:
        return False


def validate_nllb_dropout_rate(rate: float) -> None:
    if rate < 0.0 or rate > 0.9:
        raise TranslationQualityError("--nllb-dropout-rate must be between 0.0 and 0.9.")


def set_dropout_rate(model, rate: float) -> None:
    import torch

    validate_nllb_dropout_rate(rate)
    for module in model.modules():
        if isinstance(module, torch.nn.Dropout):
            module.p = rate
            module.train()
            continue

        # NLLB-200 1.3B loads through Transformers' M2M100 classes, which use
        # functional dropout with numeric attributes instead of nn.Dropout modules.
        has_dropout_attr = False
        for attr in ("dropout", "activation_dropout"):
            value = getattr(module, attr, None)
            if isinstance(value, float):
                setattr(module, attr, rate)
                has_dropout_attr = True
        if has_dropout_attr:
            module.train()


def normalize_target_language(target_language: str) -> str:
    value = (target_language or "").strip().lower()
    aliases = {
        "chinese": "zh-CN",
        "simplified chinese": "zh-CN",
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "mandarin": "zh-CN",
        "french": "fr",
        "fr": "fr",
        "spanish": "es",
        "es": "es",
    }
    return aliases.get(value, target_language)


def ensure_texts(texts: str | Iterable[str]) -> list[str]:
    if isinstance(texts, str):
        return [texts]
    return [str(text) for text in texts]


def read_texts_from_json_or_text(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]

    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        return [str(item) for item in data]
    if isinstance(data, dict):
        for key in ("passages", "texts", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
        for key in ("passage", "passage_text", "text", "content"):
            value = data.get(key)
            if isinstance(value, str):
                return [value]
    raise TranslationQualityError(
        "Input must be text, a JSON string, a JSON list, or an object with "
        "passage/passage_text/text/content/passages/texts/items/data."
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def method_output_path(output_path: Path, method: str) -> Path:
    if output_path.suffix.lower() == ".json":
        return output_path
    return output_path / method / "passage_translation.json"


PROTECTED_TOKEN_PATTERN = re.compile(r"^\W*__[A-Z0-9_]+__\W*$")
VERSE_MARKER_PATTERN = re.compile(r"(?<![\w\]])(\d{1,3})\s+")


def is_protected_token(value: str) -> bool:
    return bool(PROTECTED_TOKEN_PATTERN.fullmatch(value))


def split_long_translation_text(text: str, max_chars: int = 450) -> list[str]:
    chunks = []
    remaining = text
    while len(remaining) > max_chars:
        candidates = [
            remaining.rfind("\n\n", 0, max_chars),
            remaining.rfind(". ", 0, max_chars),
            remaining.rfind("? ", 0, max_chars),
            remaining.rfind("! ", 0, max_chars),
            remaining.rfind("; ", 0, max_chars),
            remaining.rfind(", ", 0, max_chars),
            remaining.rfind(" ", 0, max_chars),
        ]
        split_at = max(candidates)
        if split_at < max_chars // 2:
            split_at = max_chars
        else:
            split_at += 1
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        chunks.append(remaining)
    return chunks


def assemble_translation_plans(plans: list[list[dict[str, str | bool]]]) -> list[str]:
    outputs = []
    for plan in plans:
        parts = []
        for unit in plan:
            if unit.get("translate"):
                parts.append(
                    f"{unit.get('prefix', '')}"
                    f"{unit.get('translated', unit['text'])}"
                    f"{unit.get('suffix', '')}"
                )
            else:
                parts.append(str(unit["text"]))
        outputs.append("".join(parts))
    return outputs


def verse_translation_unit(text: str) -> dict[str, str | bool]:
    match = re.fullmatch(r"(\s*)(.*?)(\s*)", text, flags=re.DOTALL)
    if not match or not match.group(2):
        return {"translate": False, "text": text}
    return {
        "translate": True,
        "text": match.group(2),
        "prefix": match.group(1),
        "suffix": match.group(3),
    }


def verse_translation_plan(text: str) -> list[dict[str, Any]]:
    matches = list(VERSE_MARKER_PATTERN.finditer(text))
    if not matches:
        return [
            {
                "verse_number": None,
                "units": [verse_translation_unit(text)],
            }
        ]

    blocks: list[dict[str, Any]] = []
    if matches[0].start() > 0:
        blocks.append(
            {
                "verse_number": None,
                "units": [verse_translation_unit(text[: matches[0].start()])],
            }
        )

    for index, match in enumerate(matches):
        verse_number = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(
            {
                "verse_number": verse_number,
                "units": [verse_translation_unit(text[start:end])],
            }
        )
    return blocks


def verse_translation_plans(texts: list[str]) -> list[list[dict[str, Any]]]:
    return [verse_translation_plan(text) for text in texts]


def translatable_units_from_verse_plans(
    plans: list[list[dict[str, Any]]],
) -> list[dict[str, str | bool]]:
    return [
        unit
        for passage_plan in plans
        for block in passage_plan
        for unit in block["units"]
        if unit.get("translate")
    ]


def assemble_verse_translation_plans(plans: list[list[dict[str, Any]]]) -> list[str]:
    outputs = []
    for passage_plan in plans:
        parts = []
        for block in passage_plan:
            translated = assemble_translation_plans([block["units"]])[0]
            verse_number = block["verse_number"]
            if verse_number is None:
                parts.append(translated)
            else:
                parts.append(f"{verse_number} {translated}")
        outputs.append("".join(parts))
    return outputs


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


# --- wbw canonical-name overrides ---
# THE BUG THIS FIXES. google_word_by_word keys its cache on `word.lower()`, and the
# capital is the only thing marking a proper noun, so the translator is asked for a
# common word: "Dan" -> 担 (the verb "to carry"), "Micah" -> 米卡 (a secular
# transliteration, not the Bible's 米迦), "who" -> "WHO" (the organization, left in
# Latin script). Worse, the answer depends on what punctuation rode along with the
# token -- 'micah' -> 米卡 but 'micah,' -> 米迦 -- so one passage called the same man
# by two names. That gave the arm three tells a reader can use without reading:
# Latin script in Chinese text, names that disagree with the MCQ options, and names
# that disagree with themselves.
#
# The overrides are consulted BEFORE the cache and are keyed on the token's latin
# core, so the fix needs no re-translation and no network. Every entry was verified
# to occur in that passage's reference Chinese target before being written, which is
# what keeps the passage's names consistent with the QA built from that reference.
_WBW_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'\u2019\-]*")
_WBW_POSSESSIVE = re.compile(r"(?:'s|\u2019s)$")


def _wbw_name_overrides_path() -> Path:
    override = os.getenv("WBW_NAME_OVERRIDES_PATH")
    if override:
        return Path(override)
    return Path("evaluation/datasets/perturbations/wbw_name_overrides.json")


def _wbw_load_name_overrides() -> dict:
    if os.getenv("WBW_NAME_OVERRIDES_DISABLED"):
        return {}
    try:
        data = json.loads(_wbw_name_overrides_path().read_text(encoding="utf-8"))
        return {str(k).lower(): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def wbw_name_override(word: str, overrides: dict) -> str | None:
    """`word` rendered via the override table, or None to fall through to the cache.

    ALL-or-nothing by design: a token is only rewritten when EVERY latin run in it is
    a known entry, so "twenty-two" or a name glued to an unknown word is left for the
    normal path instead of being half-translated. Trailing punctuation, newlines and
    verse numbers ride along untouched -- 'Micah.\n\n12' keeps its verse number.
    """
    if not overrides:
        return None
    runs = _WBW_LATIN_RUN.findall(word)
    if not runs:
        return None
    out = word
    for run in runs:
        rendered = overrides.get(run.lower())
        if rendered is None:
            stem = _WBW_POSSESSIVE.sub("", run.lower())
            if stem == run.lower():
                return None
            rendered = overrides.get(stem)
            if rendered is None:
                return None
            rendered += "\u7684"  # 的, matching how the cache renders "micah\u2019s"
        out = out.replace(run, rendered, 1)
    return out


def google_word_by_word(
    texts: str | Iterable[str],
    *,
    target_language: str = "zh-CN",
    source_language: str = "en",
    sleep_seconds: float = 0.0,
) -> list[str]:
    """Lowest baseline: translate each whitespace token independently.

    This intentionally destroys phrase-level context. It is useful as a weak
    floor, not as a realistic user-facing translator.
    """

    try:
        from deep_translator import GoogleTranslator
    except ImportError as exc:
        raise TranslationQualityError(
            "Install deep-translator to use google_word_by_word: "
            "pip install deep-translator"
        ) from exc

    translator = GoogleTranslator(
        source=source_language,
        target=normalize_target_language(target_language),
    )

    # --- wbw resilience (patched) ---
    cache_path = _wbw_cache_path(source_language, target_language)
    cache = _wbw_load_cache(cache_path)
    name_overrides = _wbw_load_name_overrides()
    attempts = int(os.getenv("WBW_TOKEN_RETRIES", "3"))
    base_delay = float(os.getenv("WBW_RETRY_BASE_DELAY", "0.5"))
    # Pause after every LIVE request (cache hits are free). Google's public
    # endpoint answers TooManyRequests above ~5 requests/second, and once it
    # does, every later lookup in the run fails too.
    request_gap = float(os.getenv("WBW_REQUEST_GAP", str(sleep_seconds or 0)))
    global _WBW_LAST_STATS
    stats = {"tokens": 0, "requests": 0, "cache_hits": 0, "fallbacks": 0,
             "name_overrides": 0, "fallback_tokens": []}

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
            # Canonical names first: the cache's answer for a lower-cased proper noun
            # is wrong by construction, so it must not get a chance to win here.
            overridden = wbw_name_override(word, name_overrides)
            if overridden is not None:
                stats["name_overrides"] += 1
                translated_words.append(overridden)
                continue
            key = word.lower()
            if key in cache:
                stats["cache_hits"] += 1
                translated_words.append(cache[key])
                continue
            rendered = None
            for attempt in range(attempts):
                try:
                    stats["requests"] += 1
                    if request_gap:
                        time.sleep(request_gap)
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
                if stats["requests"] % 25 == 0:
                    _wbw_save_cache(cache_path, cache)
            translated_words.append(rendered)
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
    return outputs


LLM_QUALITY_PROMPTS = {
    "low": (
        "Translate into {target_language} with deliberately low quality while "
        "preserving the rough topic. Use awkward literal wording, weak grammar, "
        "and occasional unnatural word choices, but do not add new facts."
    ),
    "medium": (
        "Translate into {target_language} with medium quality. Preserve the main "
        "meaning, but allow some literal phrasing and minor awkwardness."
    ),
    "high": (
        "Translate into {target_language} accurately and naturally. Preserve all "
        "meaning, entities, negation, quantities, and discourse relations."
    ),
}


def llm_prompt_translate(
    texts: str | Iterable[str],
    *,
    target_language: str = "Simplified Chinese",
    quality: Literal["low", "medium", "high"] = "medium",
    model: Optional[str] = None,
    retries: int = 2,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    glossary: Optional[dict[str, str]] = None,
) -> list[str]:
    """Translate with prompt-controlled quality.

    ``temperature`` and ``seed`` default to None, which omits them from the
    request and preserves the historical behaviour exactly (API default
    temperature 1.0, no seed). Pass temperature=0 when a run has to be
    reproducible, for example when diffing two translations that differ only in
    one substituted name -- at temperature 1.0 sampling noise swamps the signal.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise TranslationQualityError(
            "Install openai to use LLM translation: pip install openai"
        ) from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise TranslationQualityError("OPENAI_API_KEY is required for LLM translation.")

    model = model or os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini")
    client = OpenAI()
    prompt_instruction = LLM_QUALITY_PROMPTS[quality].format(
        target_language=target_language
    )
    prompt_instruction += (
        " Preserve every token matching __[A-Z0-9_]+__ exactly, including "
        "capitalization and underscores. Never lowercase, translate, split, "
        "or add spaces inside these tokens."
    )
    if glossary:
        # Without a fixed target-side rendering, each call transliterates the
        # pseudonyms independently: the passage came out with 塔杜尔 for "Tadul"
        # while the questions used 卢丹 for "Ludan" and left "Lidor" in Latin
        # script. Questions then referred to entities the passage never named,
        # and MCQ accuracy fell below chance. The name map already fixes one
        # rendering per entity; this hands it to the model.
        prompt_instruction += (
            " Render these names EXACTLY as given, every time they occur; "
            "do not transliterate them yourself and do not leave them in the "
            "source script."
        )
    # The Responses API accepts temperature but not seed -- seed is a
    # chat.completions parameter. Passing it raises TypeError, so it is
    # accepted for interface symmetry and ignored here.
    sampling: dict[str, Any] = {}
    if temperature is not None:
        sampling["temperature"] = temperature

    outputs = []
    for text in ensure_texts(texts):
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                response = client.responses.create(
                    model=model,
                    **sampling,
                    input=[
                        {
                            "role": "system",
                            "content": (
                                "You are a translation engine for controlled "
                                "evaluation experiments. Return only the translated "
                                "text, with no markdown or explanation."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "instruction": prompt_instruction,
                                    "source_language": "English",
                                    "target_language": target_language,
                                    **({"name_glossary": glossary} if glossary else {}),
                                    "text": text,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                )
                outputs.append(extract_openai_text(response).strip())
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(2**attempt)
        if last_error:
            raise TranslationQualityError(str(last_error)) from last_error
    return outputs


def extract_openai_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    if chunks:
        return "\n".join(chunks)
    raise TranslationQualityError("OpenAI response did not include text output.")


def helsinki_nmt_translate(
    texts: str | Iterable[str],
    *,
    model_name: str,
    target_language: str = "Simplified Chinese",
    batch_size: int = 8,
) -> list[str]:
    try:
        import torch
        from transformers import MarianMTModel, MarianTokenizer
    except ImportError as exc:
        raise TranslationQualityError(
            "Install transformers, torch, and sentencepiece to use Helsinki NMT: "
            "pip install transformers torch sentencepiece"
        ) from exc

    torch.set_num_threads(1)
    tokenizer = MarianTokenizer.from_pretrained(model_name)
    model = MarianMTModel.from_pretrained(model_name)
    model.eval()

    target_prefix = helsinki_target_prefix(target_language, model_name)
    input_texts = ensure_texts(texts)
    plans = verse_translation_plans(input_texts)
    translatable_units = translatable_units_from_verse_plans(plans)

    for start in range(0, len(translatable_units), batch_size):
        unit_batch = translatable_units[start : start + batch_size]
        batch = [
            f"{target_prefix} {text}" if target_prefix else text
            for text in (str(unit["text"]) for unit in unit_batch)
        ]
        encoded = tokenizer(batch, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            generated = model.generate(**encoded)
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        for unit, translated in zip(unit_batch, decoded):
            unit["translated"] = translated

    return assemble_verse_translation_plans(plans)


def helsinki_target_prefix(target_language: str, model_name: str) -> str:
    if "opus-mt-en-zh" not in model_name:
        return ""
    return ">>cmn_Hans<<"


def mbart_translate(
    texts: str | Iterable[str],
    *,
    model_name: str,
    batch_size: int = 4,
) -> list[str]:
    try:
        import torch
        from transformers import MBart50TokenizerFast, MBartForConditionalGeneration
    except ImportError as exc:
        raise TranslationQualityError(
            "Install transformers, torch, and sentencepiece to use mBART-50: "
            "pip install transformers torch sentencepiece"
        ) from exc

    torch.set_num_threads(1)
    tokenizer = MBart50TokenizerFast.from_pretrained(model_name)
    model = MBartForConditionalGeneration.from_pretrained(model_name)
    model.eval()
    tokenizer.src_lang = "en_XX"
    forced_bos_token_id = tokenizer.lang_code_to_id["zh_CN"]

    input_texts = ensure_texts(texts)
    plans = verse_translation_plans(input_texts)
    translatable_units = translatable_units_from_verse_plans(plans)

    for start in range(0, len(translatable_units), batch_size):
        unit_batch = translatable_units[start : start + batch_size]
        batch = [str(unit["text"]) for unit in unit_batch]
        encoded = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=1024,
        )
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                forced_bos_token_id=forced_bos_token_id,
                max_new_tokens=1024,
                no_repeat_ngram_size=3,
                repetition_penalty=1.2,
                num_beams=4,
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        for unit, translated in zip(unit_batch, decoded):
            unit["translated"] = translated
    return assemble_verse_translation_plans(plans)


def nllb_translate(
    texts: str | Iterable[str],
    *,
    model_name: str,
    target_language: str = "Simplified Chinese",
    source_language: str = "en",
    batch_size: int = 4,
    dropout_rate: float = 0.0,
) -> list[str]:
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError as exc:
        raise TranslationQualityError(
            "Install transformers, torch, and sentencepiece to use NLLB: "
            "pip install transformers torch sentencepiece"
        ) from exc

    torch.set_num_threads(1)
    src_lang = nllb_language_code(source_language, default="eng_Latn")
    tgt_lang = nllb_language_code(target_language, default="zho_Hans")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()
    set_dropout_rate(model, dropout_rate)

    tokenizer.src_lang = src_lang
    forced_bos_token_id = tokenizer.convert_tokens_to_ids(tgt_lang)
    if forced_bos_token_id is None or forced_bos_token_id == tokenizer.unk_token_id:
        raise TranslationQualityError(f"Unknown NLLB target language code: {tgt_lang}")
    input_texts = ensure_texts(texts)
    plans = verse_translation_plans(input_texts)
    translatable_units = translatable_units_from_verse_plans(plans)

    for start in range(0, len(translatable_units), batch_size):
        unit_batch = translatable_units[start : start + batch_size]
        batch = [str(unit["text"]) for unit in unit_batch]
        encoded = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=1024,
        )
        with torch.no_grad():
            generated = model.generate(
                **encoded,
                forced_bos_token_id=forced_bos_token_id,
                max_new_tokens=1024,
                num_beams=1,
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        for unit, translated in zip(unit_batch, decoded):
            unit["translated"] = translated
    return assemble_verse_translation_plans(plans)


def nllb_language_code(value: str, *, default: str) -> str:
    normalized = str(value or "").strip()
    if "_" in normalized and len(normalized) >= 7:
        return normalized
    aliases = {
        "en": "eng_Latn",
        "english": "eng_Latn",
        "eng": "eng_Latn",
        "zh": "zho_Hans",
        "zh-cn": "zho_Hans",
        "chinese": "zho_Hans",
        "simplified chinese": "zho_Hans",
        "mandarin": "zho_Hans",
        "fr": "fra_Latn",
        "french": "fra_Latn",
        "es": "spa_Latn",
        "spanish": "spa_Latn",
    }
    return aliases.get(normalized.lower(), default)


def translate_with_method(
    texts: str | Iterable[str],
    method: str,
    *,
    target_language: str = "Simplified Chinese",
    source_language: str = "en",
    helsinki_model: Optional[str] = None,
    mbart_model: Optional[str] = None,
    nllb_distilled_model: Optional[str] = None,
    nllb_model: Optional[str] = None,
    openai_model: Optional[str] = None,
    nllb_dropout_rate: Optional[float] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    glossary: Optional[dict[str, str]] = None,
) -> list[str]:
    if method == "google_word_by_word":
        return google_word_by_word(
            texts,
            target_language=target_language,
            source_language=source_language,
        )
    if method == "llm_prompt_low":
        return llm_prompt_translate(
            texts,
            target_language=target_language,
            quality="low",
            model=openai_model,
            temperature=temperature,
            seed=seed,
            glossary=glossary,
        )
    if method == "llm_prompt_medium":
        return llm_prompt_translate(
            texts,
            target_language=target_language,
            quality="medium",
            model=openai_model,
            temperature=temperature,
            seed=seed,
            glossary=glossary,
        )
    if method == "llm_prompt_high":
        return llm_prompt_translate(
            texts,
            target_language=target_language,
            quality="high",
            model=openai_model,
            temperature=temperature,
            seed=seed,
            glossary=glossary,
        )
    if method == "helsinki":
        return helsinki_nmt_translate(
            texts,
            model_name=helsinki_model
            or os.getenv("HELSINKI_MODEL", "Helsinki-NLP/opus-mt-en-zh"),
            target_language=target_language,
        )
    if method == "mBART-50":
        return mbart_translate(
            texts,
            model_name=mbart_model
            or os.getenv("MBART_MODEL", "facebook/mbart-large-50-many-to-many-mmt"),
        )
    if method == "nllb-200-distilled-600M":
        return nllb_translate(
            texts,
            model_name=nllb_distilled_model
            or os.getenv("NLLB_DISTILLED_MODEL", "facebook/nllb-200-distilled-600M"),
            target_language=target_language,
            source_language=source_language,
        )
    if method == "nllb-200-1.3B":
        return nllb_translate(
            texts,
            model_name=nllb_model
            or os.getenv("NLLB_MODEL", "facebook/nllb-200-1.3B"),
            target_language=target_language,
            source_language=source_language,
            dropout_rate=0.0,
        )
    parsed_dropout_rate = parse_nllb_dropout_rate(method)
    if method == NLLB_DROPOUT_METHOD_PREFIX or parsed_dropout_rate is not None:
        rate = nllb_dropout_rate if parsed_dropout_rate is None else parsed_dropout_rate
        if rate is None:
            rate = 0.0
        validate_nllb_dropout_rate(rate)
        return nllb_translate(
            texts,
            model_name=nllb_model
            or os.getenv("NLLB_MODEL", "facebook/nllb-200-1.3B"),
            target_language=target_language,
            source_language=source_language,
            dropout_rate=rate,
        )
    raise TranslationQualityError(f"Unknown translation method: {method}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate passages with a selected evaluation-quality method."
    )
    parser.add_argument("input_file", type=Path)
    parser.add_argument(
        "output_path",
        type=Path,
        help=(
            "Output JSON file, or an output directory. If a directory is supplied, "
            "the file is written to <output>/<method>/passage_translation.json."
        ),
    )
    parser.add_argument(
        "--method",
        required=True,
        help=(
            "Translation method. Also supports nllb-200-1.3B-dropout or "
            "nllb-200-1.3B-dropout-<rate>, where rate is 0.0 to 0.9."
        ),
    )
    parser.add_argument("--target-language", default="Simplified Chinese")
    parser.add_argument("--source-language", default="en")
    parser.add_argument("--helsinki-model")
    parser.add_argument("--mbart-model")
    parser.add_argument("--nllb-distilled-model")
    parser.add_argument("--nllb-model")
    parser.add_argument(
        "--nllb-dropout-rate",
        type=float,
        default=0.0,
        help=(
            "Dropout rate for nllb-200-1.3B-dropout. Must be between 0.0 and 0.9. "
            "Ignored when the method name already includes a rate."
        ),
    )
    parser.add_argument("--openai-model")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        source_texts = read_texts_from_json_or_text(args.input_file)
        if not is_supported_method(args.method):
            raise TranslationQualityError(f"Unknown translation method: {args.method}")
        validate_nllb_dropout_rate(args.nllb_dropout_rate)
        translations = translate_with_method(
            source_texts,
            args.method,
            target_language=args.target_language,
            source_language=args.source_language,
            helsinki_model=args.helsinki_model,
            mbart_model=args.mbart_model,
            nllb_distilled_model=args.nllb_distilled_model,
            nllb_model=args.nllb_model,
            nllb_dropout_rate=args.nllb_dropout_rate,
            openai_model=args.openai_model,
        )
        output_json = method_output_path(args.output_path, args.method)
        method_dropout_rate = parse_nllb_dropout_rate(args.method)
        if args.method == NLLB_DROPOUT_METHOD_PREFIX:
            method_dropout_rate = args.nllb_dropout_rate
        write_json(
            output_json,
            {
                "method": args.method,
                "target_language": args.target_language,
                "nllb_dropout_rate": method_dropout_rate,
                "translations": translations,
            },
        )
    except TranslationQualityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(translations)} translation(s) to {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
