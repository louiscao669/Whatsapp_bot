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


TranslationMethod = Literal[
    "google_word_by_word",
    "llm_prompt_low",
    "llm_prompt_medium",
    "llm_prompt_high",
    "helsinki",
    "mBART-50",
    "nllb-200-distilled-600M",
    "nllb-200-1.3B",
]


class TranslationQualityError(Exception):
    pass


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
PROTECTED_TOKEN_IN_TEXT_PATTERN = re.compile(r"__([A-Z0-9_]+)__")
PROTECTED_TOKEN_SPLIT_PATTERN = re.compile(r"(__[A-Z0-9_]+__)")
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


def translation_units_without_placeholders(text: str) -> list[dict[str, str | bool]]:
    units: list[dict[str, str | bool]] = []
    for part in PROTECTED_TOKEN_SPLIT_PATTERN.split(text):
        if not part:
            continue
        if PROTECTED_TOKEN_IN_TEXT_PATTERN.fullmatch(part):
            units.append({"translate": False, "text": part})
            continue
        for chunk in split_long_translation_text(part):
            match = re.fullmatch(r"(\s*)(.*?)(\s*)", chunk, flags=re.DOTALL)
            if not match or not match.group(2):
                units.append({"translate": False, "text": chunk})
                continue
            units.append(
                {
                    "translate": True,
                    "text": match.group(2),
                    "prefix": match.group(1),
                    "suffix": match.group(3),
                }
            )
    return units


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
) -> list[str]:
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
    outputs = []
    for text in ensure_texts(texts):
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                response = client.responses.create(
                    model=model,
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
    batch_size: int = 4,
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
    src_lang = "eng_Latn"
    tgt_lang = "zho_Hans"
    tokenizer = AutoTokenizer.from_pretrained(model_name, src_lang=src_lang)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()

    forced_bos_token_id = tokenizer.convert_tokens_to_ids(tgt_lang)
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
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        for unit, translated in zip(unit_batch, decoded):
            unit["translated"] = translated
    return assemble_verse_translation_plans(plans)


def translate_with_method(
    texts: str | Iterable[str],
    method: TranslationMethod,
    *,
    target_language: str = "Simplified Chinese",
    source_language: str = "en",
    helsinki_model: Optional[str] = None,
    mbart_model: Optional[str] = None,
    nllb_distilled_model: Optional[str] = None,
    nllb_model: Optional[str] = None,
    openai_model: Optional[str] = None,
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
        )
    if method == "llm_prompt_medium":
        return llm_prompt_translate(
            texts,
            target_language=target_language,
            quality="medium",
            model=openai_model,
        )
    if method == "llm_prompt_high":
        return llm_prompt_translate(
            texts,
            target_language=target_language,
            quality="high",
            model=openai_model,
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
        )
    if method == "nllb-200-1.3B":
        return nllb_translate(
            texts,
            model_name=nllb_model
            or os.getenv("NLLB_MODEL", "facebook/nllb-200-1.3B"),
            target_language=target_language,
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
        choices=[
            "google_word_by_word",
            "llm_prompt_low",
            "llm_prompt_medium",
            "llm_prompt_high",
            "helsinki",
            "mBART-50",
            "nllb-200-distilled-600M",
            "nllb-200-1.3B",
        ],
    )
    parser.add_argument("--target-language", default="Simplified Chinese")
    parser.add_argument("--source-language", default="en")
    parser.add_argument("--helsinki-model")
    parser.add_argument("--mbart-model")
    parser.add_argument("--nllb-distilled-model")
    parser.add_argument("--nllb-model")
    parser.add_argument("--openai-model")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        source_texts = read_texts_from_json_or_text(args.input_file)
        translations = translate_with_method(
            source_texts,
            args.method,
            target_language=args.target_language,
            source_language=args.source_language,
            helsinki_model=args.helsinki_model,
            mbart_model=args.mbart_model,
            nllb_distilled_model=args.nllb_distilled_model,
            nllb_model=args.nllb_model,
            openai_model=args.openai_model,
        )
        output_json = method_output_path(args.output_path, args.method)
        write_json(
            output_json,
            {
                "method": args.method,
                "target_language": args.target_language,
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
