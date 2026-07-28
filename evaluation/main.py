#!/usr/bin/env python3
"""Run the Chinese QA evaluation pipeline.

Pipeline:
1. Translate QA questions to Chinese while preserving open standard answers in English.
2. Decanonicalize the English source passage before passage translation.
3. Translate the decanonicalized source passage to Chinese.
4. Decanonicalize translated Chinese QA and any remaining translated passage aliases.
5. Generate Chinese answers from the decanonicalized passage and questions with GPT.
6. Back-translate generated open answers to English.
7. Score against the initially imported English QA set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.agents.generate_chinese_answers import (
    GenerationError,
    generate_answers,
    load_passage,
    load_qa_items,
    public_questions,
    write_json as write_generated_json,
)
from evaluation.scripts.score_generated_answers import (
    ScoreError,
    backtranslate_generated_answers,
    extract_items,
    load_json as load_score_json,
    score_items,
    summarize,
    write_json as write_score_json,
)
from evaluation.scripts.decanonicalize_chinese_dataset import (
    DEFAULT_ENGLISH_TOKEN_MAPPING,
    DEFAULT_MAPPING,
    PROTECTED_TOKEN_MAPPING,
    load_json as load_mapping_json,
    protected_token_mapping,
    replace_english_terms,
    replace_text,
)
from evaluation.scripts.translate_llm_qa_to_chinese import (
    TranslationError,
    extract_response_text,
    load_json as load_translation_json,
    normalize_items,
    translate_items,
    write_json as write_translation_json,
)
from evaluation.scripts.translation_quality import (
    DEFAULT_NLLB_DROPOUT_RATES,
    NLLB_DROPOUT_METHOD_PREFIX,
    TranslationQualityError,
    is_supported_method,
    nllb_dropout_method_name,
    parse_nllb_dropout_rate,
    read_texts_from_json_or_text,
    translate_with_method,
    validate_nllb_dropout_rate,
    write_json as write_quality_json,
)


DEFAULT_OUTPUT_DIR = Path("evaluation/outputs")
ALL_TRANSLATION_METHODS = [
    "google_word_by_word",
    "llm_prompt_low",
    "llm_prompt_medium",
    "llm_prompt_high",
    "helsinki",
    "mBART-50",
    "nllb-200-distilled-600M",
    "nllb-200-1.3B",
]
NLLB_DROPOUT_GRADIENT_METHODS = [
    nllb_dropout_method_name(rate)
    for rate in DEFAULT_NLLB_DROPOUT_RATES
]
LLM_QUALITY_METHODS = {"llm_prompt_low", "llm_prompt_medium", "llm_prompt_high"}
NATURAL_SOURCE_MT_METHODS = {
    "helsinki",
    "mBART-50",
    "nllb-200-distilled-600M",
    "nllb-200-1.3B",
}
ENTITY_TYPE_CONFIG = {
    "person": ("PERSON", "人物"),
    "place": ("PLACE", "地点"),
    "group": ("GROUP", "群体"),
    "role": ("ROLE", "角色"),
    "object": ("OBJECT", "物件"),
    "title": ("TITLE", "称号"),
    "other": ("ENTITY", "实体"),
}
STOP_STAGES = ("entity-inventory", "translate", "passage-translate", "decanonicalize", "answer", "backtranslate", "score")


class PipelineError(Exception):
    pass


def is_nllb_dropout_method(method: str) -> bool:
    if method == NLLB_DROPOUT_METHOD_PREFIX:
        return True
    try:
        return parse_nllb_dropout_rate(method) is not None
    except TranslationQualityError:
        return False


def uses_natural_source_text(method: str) -> bool:
    return method in NATURAL_SOURCE_MT_METHODS or is_nllb_dropout_method(method)


def default_run_name(qa_json: Path) -> str:
    name = qa_json.stem.strip() or "evaluation"
    for suffix in ("_en", "_qa", "_questions"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name or "evaluation"


def shared_output_paths(args: argparse.Namespace) -> dict:
    output_dir = args.output_dir
    run_name = args.run_name or default_run_name(args.qa_json)
    return {
        "entity_inventory": args.entity_inventory_json
        or output_dir / "_shared" / f"{run_name}_entity_inventory.json",
        "translated_qa": args.translated_qa_json
        or output_dir / "_shared" / f"{run_name}_qa_zh.json",
        "decanonicalized_qa": args.decanonicalized_qa_json
        or output_dir / "_shared" / f"{run_name}_qa_zh_decanonicalized.json",
    }


def method_output_paths(args: argparse.Namespace, method: str) -> dict:
    method_dir = args.output_dir / method
    return {
        "method_dir": method_dir,
        "source_decanonicalized_passage": method_dir / "passage_source_decanonicalized.txt",
        "translated_passage_json": method_dir / "passage_translation.json",
        "translated_passage": method_dir / "passage_target.txt",
        "translated_qa": method_dir / "qa_target.json",
        "decanonicalized_passage": method_dir / "passage_target_decanonicalized.txt",
        "decanonicalized_qa": method_dir / "qa_target_decanonicalized.json",
        "decanonicalized_metadata": method_dir / "decanonicalized_metadata.json",
        "generated_answers": method_dir / "generated_answers_target_llama.json",
        "backtranslated_answers": method_dir
        / "generated_answers_target_llama_backtranslated.json",
        "scores": method_dir / "scores_target_llama.json",
    }


def method_has_existing_artifacts(paths: dict) -> bool:
    return (
        paths["translated_passage_json"].exists()
        and paths["translated_passage"].exists()
        and paths["decanonicalized_passage"].exists()
        and paths["decanonicalized_qa"].exists()
    )


def is_supported_or_existing_artifact_method(method: str, paths: dict) -> bool:
    return is_supported_method(method) or method_has_existing_artifacts(paths)


def selected_methods(args: argparse.Namespace) -> list[str]:
    methods = list(args.methods or ALL_TRANSLATION_METHODS)
    if args.include_nllb_dropout_gradient:
        methods.extend(NLLB_DROPOUT_GRADIENT_METHODS)
    if args.skip_llm_quality_methods:
        methods = [method for method in methods if method not in LLM_QUALITY_METHODS]
    seen = set()
    deduped = []
    for method in methods:
        if method not in seen:
            seen.add(method)
            deduped.append(method)
    return deduped


def should_run(path: Path, *, force: bool, force_stage: bool) -> bool:
    return force or force_stage or not path.exists()


def stage_enabled(args: argparse.Namespace, stage: str) -> bool:
    stop_after = args.stop_after or "score"
    return STOP_STAGES.index(stage) <= STOP_STAGES.index(stop_after)


def require_openai_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise PipelineError("OPENAI_API_KEY is required for this pipeline.")


def normalize_entity_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "location": "place",
        "city": "place",
        "town": "place",
        "region": "place",
        "people": "group",
        "role_or_title": "role",
        "office": "role",
        "thing": "object",
        "divine_title": "title",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in ENTITY_TYPE_CONFIG else "other"


def normalized_aliases(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    aliases = []
    seen = set()
    for value in values:
        alias = str(value or "").strip()
        if not alias or alias in seen:
            continue
        seen.add(alias)
        aliases.append(alias)
    return aliases


def assign_entity_placeholders(raw_entities: list[dict]) -> list[dict]:
    counters = {entity_type: 0 for entity_type in ENTITY_TYPE_CONFIG}
    entities = []
    used_sources = set()
    for raw in raw_entities:
        source = str(raw.get("source") or raw.get("canonical") or "").strip()
        if not source:
            continue
        source_key = source.lower()
        if source_key in used_sources:
            continue
        used_sources.add(source_key)

        entity_type = normalize_entity_type(raw.get("type"))
        counters[entity_type] += 1
        token_prefix, placeholder_prefix = ENTITY_TYPE_CONFIG[entity_type]
        index = counters[entity_type]
        token = f"__LOCAL_{token_prefix}_{index:02d}__"
        placeholder = f"{placeholder_prefix}{index:02d}"

        aliases = normalized_aliases(raw.get("aliases"))
        if source not in aliases:
            aliases.insert(0, source)

        entities.append(
            {
                "source": source,
                "type": entity_type,
                "protected_token": token,
                "placeholder": placeholder,
                "aliases": aliases,
                "chinese_alias_hints": normalized_aliases(
                    raw.get("chinese_alias_hints") or raw.get("chinese_aliases")
                ),
                "reason": str(raw.get("reason") or raw.get("notes") or "").strip(),
            }
        )
    return entities


def entity_inventory_english_mapping(inventory: dict | None) -> dict[str, str]:
    mapping = {}
    for entity in (inventory or {}).get("entities", []):
        token = str(entity.get("protected_token") or "").strip()
        if not token:
            continue
        for alias in normalized_aliases(entity.get("aliases")):
            mapping[alias] = token
    return mapping


def entity_inventory_chinese_mapping(inventory: dict | None) -> dict[str, str]:
    mapping = {}
    for entity in (inventory or {}).get("entities", []):
        placeholder = str(entity.get("placeholder") or "").strip()
        if not placeholder:
            continue
        for alias in normalized_aliases(entity.get("chinese_alias_hints")):
            mapping[alias] = placeholder
    return mapping


def load_entity_inventory(path: Path | None) -> dict | None:
    if not path or not path.exists():
        return None
    data = load_score_json(path)
    if not isinstance(data, dict):
        raise PipelineError(f"Entity inventory must be a JSON object: {path}")
    entities = data.get("entities")
    if not isinstance(entities, list):
        raise PipelineError(f"Entity inventory missing entities array: {path}")
    return data


def canonicalization_entries(
    extra_mapping: dict[str, str] | None = None,
    entity_inventory: dict | None = None,
) -> list[dict]:
    token_to_placeholder = dict(PROTECTED_TOKEN_MAPPING)
    for entity in (entity_inventory or {}).get("entities", []):
        token = str(entity.get("protected_token") or "").strip()
        placeholder = str(entity.get("placeholder") or "").strip()
        if token and placeholder:
            token_to_placeholder[token] = placeholder

    english_aliases: dict[str, list[str]] = {}
    for source, token in DEFAULT_ENGLISH_TOKEN_MAPPING.items():
        english_aliases.setdefault(token, []).append(source)
    for entity in (entity_inventory or {}).get("entities", []):
        token = str(entity.get("protected_token") or "").strip()
        for alias in normalized_aliases(entity.get("aliases")):
            english_aliases.setdefault(token, []).append(alias)

    chinese_aliases: dict[str, list[str]] = {}
    for source, placeholder in DEFAULT_MAPPING.items():
        chinese_aliases.setdefault(placeholder, []).append(source)
    for entity in (entity_inventory or {}).get("entities", []):
        placeholder = str(entity.get("placeholder") or "").strip()
        for alias in normalized_aliases(entity.get("chinese_alias_hints")):
            chinese_aliases.setdefault(placeholder, []).append(alias)
    if extra_mapping:
        for source, placeholder in extra_mapping.items():
            if placeholder in set(token_to_placeholder.values()):
                chinese_aliases.setdefault(placeholder, []).append(source)

    entries = []
    for token, placeholder in token_to_placeholder.items():
        entries.append(
            {
                "placeholder": placeholder,
                "protected_token": token,
                "english_aliases": sorted(set(english_aliases.get(token, []))),
                "chinese_alias_hints": sorted(set(chinese_aliases.get(placeholder, []))),
            }
        )
    return entries


def extract_json_object_text(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    start = value.find("{")
    end = value.rfind("}")
    if start != -1 and end != -1 and end > start:
        return value[start : end + 1]
    return value


def validate_canonicalized_qa(raw_items: Any, original_items: list[dict]) -> list[dict]:
    if not isinstance(raw_items, list):
        raise PipelineError("Canonicalization response field qa_items must be an array.")
    if len(raw_items) != len(original_items):
        raise PipelineError(
            f"Canonicalization returned {len(raw_items)} QA item(s), "
            f"expected {len(original_items)}."
        )
    output = []
    for index, (raw, original) in enumerate(zip(raw_items, original_items), start=1):
        if not isinstance(raw, dict):
            raise PipelineError(f"Canonicalized QA item {index} is not an object.")
        item = dict(raw)
        for key, value in original.items():
            if key not in item:
                item[key] = value
        if original.get("q_type") == "open":
            item["A"] = original.get("A")
        if original.get("q_type") == "mcq" and "correct" in original:
            item["correct"] = original["correct"]
        item["decanonicalized"] = True
        output.append(item)
    return output


def cleanup_protected_tokens(
    value: Any,
    extra_token_mapping: dict[str, str] | None = None,
) -> Any:
    mapping = protected_token_mapping()
    if extra_token_mapping:
        mapping.update(extra_token_mapping)
    if isinstance(value, str):
        return replace_text(value, mapping)
    if isinstance(value, list):
        return [cleanup_protected_tokens(item, extra_token_mapping) for item in value]
    if isinstance(value, dict):
        return {
            key: cleanup_protected_tokens(item, extra_token_mapping)
            for key, item in value.items()
        }
    return value


def canonicalization_context(
    args: argparse.Namespace,
    entity_inventory: dict | None,
) -> tuple[list[dict], dict[str, str], str]:
    extra_mapping = entity_inventory_chinese_mapping(entity_inventory)
    if args.mapping_json:
        extra_mapping.update(load_mapping_json(args.mapping_json))
    entries = canonicalization_entries(extra_mapping, entity_inventory)
    extra_token_mapping = {
        str(entity.get("protected_token")): str(entity.get("placeholder"))
        for entity in (entity_inventory or {}).get("entities", [])
        if entity.get("protected_token") and entity.get("placeholder")
    }
    model = args.canonicalization_model or args.translation_model
    return entries, extra_token_mapping, model


def llm_canonicalize_qa_items(
    *,
    qa_items: list[dict],
    entries: list[dict],
    extra_token_mapping: dict[str, str] | None,
    model: str,
    retries: int,
) -> list[dict]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise PipelineError("Install the openai package before canonicalization.") from exc

    client = OpenAI()
    prompt = {
        "task": (
            "Canonicalize a translated Chinese QA set. Replace every mention of each "
            "mapped person, place, object, role, group, or divine title with its exact "
            "Chinese placeholder. Use the mapping table field named placeholder as the "
            "required output form; never output protected_token values. Do not otherwise "
            "translate, summarize, reorder, or rewrite the text. Preserve QA metadata. "
            "For open QA items, leave A exactly unchanged. For MCQ items, canonicalize "
            "Q and choice text but preserve choice labels and correct."
        ),
        "mapping": entries,
        "qa_items": qa_items,
        "output_schema": {
            "qa_items": "canonicalized QA array with the same length and schema",
        },
    }

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You canonicalize translated evaluation QA. Return valid "
                            "JSON only. Do not include markdown or explanations."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            data = json.loads(extract_json_object_text(extract_response_text(response)))
            canonical_qa = validate_canonicalized_qa(data.get("qa_items"), qa_items)
            return cleanup_protected_tokens(canonical_qa, extra_token_mapping)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise PipelineError(f"QA canonicalization failed: {last_error}") from last_error


def llm_canonicalize_passage(
    *,
    passage_text: str,
    entries: list[dict],
    extra_token_mapping: dict[str, str] | None,
    model: str,
    retries: int,
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise PipelineError("Install the openai package before canonicalization.") from exc

    client = OpenAI()
    prompt = {
        "task": (
            "Canonicalize a translated Chinese Bible passage. Replace every mention of "
            "each mapped person, place, object, role, group, or divine title with its "
            "exact Chinese placeholder. Use the mapping table field named placeholder "
            "as the required output form; never output protected_token values. Aliases "
            "may be translated, transliterated, abbreviated, or awkwardly machine-"
            "translated. When an alias appears inside a compound verb-object phrase, "
            "replace only the mapped object/title/name and preserve the surrounding "
            "verb or grammar; for example, canonicalize 烧香 or 焚香 as 烧材料甲 or "
            "焚材料甲, not by deleting the action. Do not otherwise translate, "
            "summarize, reorder, or rewrite the text. Preserve verse numbers."
        ),
        "mapping": entries,
        "passage": passage_text,
        "output_schema": {
            "passage": "canonicalized passage text",
        },
    }

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You canonicalize translated Bible passages. Return valid "
                            "JSON only. Do not include markdown or explanations."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            data = json.loads(extract_json_object_text(extract_response_text(response)))
            passage = str(data.get("passage") or "").strip()
            if not passage:
                raise PipelineError("Canonicalization response field passage is empty.")
            return cleanup_protected_tokens(passage, extra_token_mapping)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise PipelineError(f"Passage canonicalization failed: {last_error}") from last_error


def compact_source_items_for_entity_discovery(items: list[dict]) -> list[dict]:
    compact = []
    for index, item in enumerate(normalize_items(items), start=1):
        entry = {
            "item_index": index,
            "q_type": item["q_type"],
            "Q": item["Q"],
        }
        if item["q_type"] == "open":
            entry["A"] = item.get("A")
        else:
            entry["choices"] = item.get("A")
        compact.append(entry)
    return compact


def validate_entity_inventory_response(raw: Any) -> list[dict]:
    if isinstance(raw, dict):
        raw_entities = raw.get("entities")
    else:
        raw_entities = raw
    if not isinstance(raw_entities, list):
        raise PipelineError("Entity discovery response must include an entities array.")
    entities = []
    global_sources = {source.lower() for source in DEFAULT_ENGLISH_TOKEN_MAPPING}
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        source = str(raw_entity.get("source") or raw_entity.get("canonical") or "").strip()
        if not source:
            continue
        if source.lower() in global_sources:
            continue
        aliases = normalized_aliases(raw_entity.get("aliases"))
        if any(alias.lower() in global_sources for alias in aliases):
            continue
        entities.append(raw_entity)
    return assign_entity_placeholders(entities)


def llm_discover_entity_inventory(
    *,
    passage_text: str,
    qa_items: list[dict],
    model: str,
    retries: int,
) -> dict:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise PipelineError("Install the openai package before entity discovery.") from exc

    client = OpenAI()
    prompt = {
        "task": (
            "Read the English Bible chapter passage and QA items. Identify recurring "
            "chapter-local named entities, places, groups, roles, titles, and concrete "
            "objects that should be anonymized for an evaluation dataset. Do not include "
            "terms already covered by the provided global mapping. Prefer entities that "
            "appear in the passage or QA and could leak canonical context or make answers "
            "too easy because the name is recognizable."
        ),
        "global_mapping_sources": sorted(DEFAULT_ENGLISH_TOKEN_MAPPING),
        "allowed_types": sorted(ENTITY_TYPE_CONFIG),
        "entity_guidelines": [
            "Include proper names and named places not in the global mapping.",
            "Include salient roles when they function like an entity in the chapter, such as centurion or Pharisee.",
            "Include aliases and possessive forms needed for exact English replacement.",
            "Use source as the shortest canonical English surface form.",
            "Do not invent placeholders; the pipeline assigns placeholders after validation.",
            "Provide likely Chinese alias hints if obvious, otherwise use an empty array.",
        ],
        "passage": passage_text,
        "qa_items": compact_source_items_for_entity_discovery(qa_items),
        "output_schema": {
            "entities": [
                {
                    "source": "canonical English surface form",
                    "type": "person/place/group/role/object/title/other",
                    "aliases": ["English aliases and possessive forms"],
                    "chinese_alias_hints": ["optional likely Chinese aliases"],
                    "reason": "short reason",
                }
            ]
        },
    }

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You identify entity inventories for anonymized evaluation "
                            "datasets. Return valid JSON only. Do not include markdown "
                            "or explanations."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            data = json.loads(extract_json_object_text(extract_response_text(response)))
            entities = validate_entity_inventory_response(data)
            return {
                "schema_version": 1,
                "model": model,
                "entities": entities,
                "english_mapping": entity_inventory_english_mapping(
                    {"entities": entities}
                ),
                "chinese_mapping": entity_inventory_chinese_mapping(
                    {"entities": entities}
                ),
            }
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(2**attempt)
    raise PipelineError(f"Entity discovery failed: {last_error}") from last_error


def entity_inventory_stage_needed(
    args: argparse.Namespace,
    shared_paths: dict,
    method_paths: dict[str, dict],
) -> bool:
    if args.skip_entity_discovery:
        return False
    if args.stop_after == "entity-inventory":
        return (
            args.force
            or args.force_entity_inventory
            or not shared_paths["entity_inventory"].exists()
        )
    if args.force or args.force_entity_inventory or not shared_paths["entity_inventory"].exists():
        return any(
            args.force
            or args.force_entity_inventory
            or args.force_decanonicalize
            or args.force_passage_translate
            or not paths["decanonicalized_passage"].exists()
            or not paths["decanonicalized_qa"].exists()
            or not paths["decanonicalized_metadata"].exists()
            or not paths["translated_passage"].exists()
            for paths in method_paths.values()
        )
    return False


def run_entity_inventory_stage(
    args: argparse.Namespace,
    entity_inventory_path: Path,
    *,
    needed: bool,
) -> bool:
    if args.skip_entity_discovery:
        print("skip entity inventory")
        return False
    if not needed:
        if entity_inventory_path.exists():
            print(f"reuse entity inventory: {entity_inventory_path}")
        return False

    print(f"run entity inventory: {entity_inventory_path}")
    passage_text = "\n\n".join(read_texts_from_json_or_text(args.passage_file))
    qa_items = load_translation_json(args.qa_json)
    model = args.entity_discovery_model or args.translation_model
    inventory = llm_discover_entity_inventory(
        passage_text=passage_text,
        qa_items=qa_items,
        model=model,
        retries=args.retries,
    )
    entity_inventory_path.parent.mkdir(parents=True, exist_ok=True)
    write_score_json(entity_inventory_path, inventory)
    return True


def shared_needs_openai(
    args: argparse.Namespace,
    paths: dict,
    entity_inventory_needed: bool,
) -> bool:
    if (
        stage_enabled(args, "entity-inventory")
        and not args.skip_entity_discovery
        and entity_inventory_needed
    ):
        return True
    if stage_enabled(args, "translate") and should_run(
        paths["translated_qa"],
        force=args.force,
        force_stage=args.force_translate,
    ):
        return True
    if stage_enabled(args, "decanonicalize") and should_run(
        paths["decanonicalized_qa"],
        force=args.force,
        force_stage=(
            args.force_decanonicalize
            or args.force_translate
            or entity_inventory_needed
        ),
    ):
        return True
    return False


def method_needs_openai(args: argparse.Namespace, method: str, paths: dict) -> bool:
    if stage_enabled(args, "passage-translate") and method in LLM_QUALITY_METHODS and should_run(
        paths["translated_passage_json"],
        force=args.force,
        force_stage=args.force_passage_translate,
    ):
        return True
    if stage_enabled(args, "decanonicalize") and should_run(
        paths["decanonicalized_passage"],
        force=args.force,
        force_stage=(
            args.force_decanonicalize
            or args.force_passage_translate
            or args.force_translate
            or not paths["translated_passage"].exists()
            or not paths["translated_qa"].exists()
            or not paths["decanonicalized_qa"].exists()
            or not paths["decanonicalized_metadata"].exists()
        ),
    ):
        return True
    if stage_enabled(args, "answer") and should_run(
        paths["generated_answers"],
        force=args.force,
        force_stage=(
            args.force_answer
            or args.force_passage_translate
            or args.force_decanonicalize
            or not paths["translated_passage"].exists()
            or not paths["decanonicalized_qa"].exists()
            or not paths["decanonicalized_passage"].exists()
        ),
    ):
        return args.answer_provider == "openai"
    if stage_enabled(args, "backtranslate") and should_run(
        paths["backtranslated_answers"],
        force=args.force,
        force_stage=args.force_backtranslate or args.force_answer,
    ):
        return True
    if stage_enabled(args, "score") and should_run(
        paths["scores"],
        force=args.force,
        force_stage=args.force_score or args.force_backtranslate or args.force_answer,
    ):
        return not args.skip_llm
    return False


def run_translate_stage(args: argparse.Namespace, translated_qa_path: Path) -> bool:
    if not should_run(
        translated_qa_path,
        force=args.force,
        force_stage=args.force_translate,
    ):
        print(f"reuse translate: {translated_qa_path}")
        return False

    print(f"run translate: {translated_qa_path}")
    items = normalize_items(load_translation_json(args.qa_json))
    translated = translate_items(
        items,
        model=args.translation_model,
        target_language=args.target_language,
        batch_size=args.translation_batch_size,
        retries=args.retries,
        dry_run=False,
    )
    write_translation_json(translated_qa_path, translated)
    return True


def run_passage_translate_stage(
    args: argparse.Namespace,
    method: str,
    translated_passage_json_path: Path,
    translated_passage_path: Path,
    entity_inventory: dict | None,
) -> bool:
    if not should_run(
        translated_passage_json_path,
        force=args.force,
        force_stage=args.force_passage_translate,
    ) and translated_passage_path.exists():
        print(f"[{method}] reuse passage translate: {translated_passage_path}")
        return False

    print(f"[{method}] run passage translate: {translated_passage_path}")
    raw_source_texts = read_texts_from_json_or_text(args.passage_file)
    if uses_natural_source_text(method):
        source_texts = raw_source_texts
    else:
        source_mapping = dict(DEFAULT_ENGLISH_TOKEN_MAPPING)
        source_mapping.update(entity_inventory_english_mapping(entity_inventory))
        if args.mapping_json:
            source_mapping.update(load_mapping_json(args.mapping_json))
        source_texts = [
            replace_english_terms(text, source_mapping)
            for text in raw_source_texts
        ]
    translations = translate_with_method(
        source_texts,
        method,
        target_language=args.target_language,
        source_language=args.source_language,
        helsinki_model=args.helsinki_model,
        mbart_model=args.mbart_model,
        nllb_distilled_model=args.nllb_distilled_model,
        nllb_model=args.nllb_model,
        nllb_dropout_rate=args.nllb_dropout_rate,
        openai_model=args.passage_translation_model,
    )
    method_dropout_rate = parse_nllb_dropout_rate(method) if is_nllb_dropout_method(method) else None
    if method == NLLB_DROPOUT_METHOD_PREFIX:
        method_dropout_rate = args.nllb_dropout_rate
    write_quality_json(
        translated_passage_json_path,
        {
            "method": method,
            "source_language": args.source_language,
            "target_language": args.target_language,
            "nllb_dropout_rate": method_dropout_rate,
            "source_texts": source_texts,
            "translations": translations,
        },
    )
    source_decanonicalized_path = method_output_paths(args, method)[
        "source_decanonicalized_passage"
    ]
    source_decanonicalized_path.parent.mkdir(parents=True, exist_ok=True)
    source_decanonicalized_path.write_text(
        "\n\n".join(source_texts),
        encoding="utf-8",
    )
    translated_passage_path.parent.mkdir(parents=True, exist_ok=True)
    translated_passage_path.write_text("\n\n".join(translations), encoding="utf-8")
    return True


def run_method_qa_stage(
    shared_translated_qa_path: Path,
    method_translated_qa_path: Path,
    *,
    force: bool,
    upstream_changed: bool,
    method: str,
) -> bool:
    if not (force or upstream_changed or not method_translated_qa_path.exists()):
        print(f"[{method}] reuse QA translate: {method_translated_qa_path}")
        return False
    print(f"[{method}] write QA translate: {method_translated_qa_path}")
    qa_data = load_score_json(shared_translated_qa_path)
    write_score_json(method_translated_qa_path, qa_data)
    return True


def run_shared_qa_decanonicalize_stage(
    args: argparse.Namespace,
    translated_qa_path: Path,
    decanonicalized_qa_path: Path,
    upstream_changed: bool,
    entity_inventory: dict | None,
) -> bool:
    if not should_run(
        decanonicalized_qa_path,
        force=args.force,
        force_stage=args.force_decanonicalize or upstream_changed,
    ):
        print(f"reuse shared QA decanonicalize: {decanonicalized_qa_path}")
        return False

    print(f"run shared QA decanonicalize: {decanonicalized_qa_path}")
    entries, extra_token_mapping, canonicalization_model = canonicalization_context(
        args,
        entity_inventory,
    )
    qa_data = load_score_json(translated_qa_path)
    qa_items = extract_items(qa_data)
    transformed_qa = llm_canonicalize_qa_items(
        qa_items=qa_items,
        entries=entries,
        extra_token_mapping=extra_token_mapping,
        model=canonicalization_model,
        retries=args.retries,
    )
    write_score_json(decanonicalized_qa_path, transformed_qa)
    return True


def run_decanonicalize_stage(
    args: argparse.Namespace,
    method: str,
    translated_passage_path: Path,
    shared_decanonicalized_qa_path: Path,
    decanonicalized_passage_path: Path,
    decanonicalized_qa_path: Path,
    metadata_path: Path,
    upstream_changed: bool,
    entity_inventory: dict | None,
    entity_inventory_path: Path | None,
) -> bool:
    missing_output = (
        not decanonicalized_passage_path.exists()
        or not decanonicalized_qa_path.exists()
        or not metadata_path.exists()
    )
    if not (args.force or args.force_decanonicalize or upstream_changed or missing_output):
        print(f"[{method}] reuse decanonicalize: {decanonicalized_qa_path}")
        return False

    print(f"[{method}] run decanonicalize: {decanonicalized_qa_path}")
    entries, extra_token_mapping, canonicalization_model = canonicalization_context(
        args,
        entity_inventory,
    )

    passage_text = translated_passage_path.read_text(encoding="utf-8")
    transformed_passage = llm_canonicalize_passage(
        passage_text=passage_text,
        entries=entries,
        extra_token_mapping=extra_token_mapping,
        model=canonicalization_model,
        retries=args.retries,
    )
    transformed_qa = load_score_json(shared_decanonicalized_qa_path)

    decanonicalized_passage_path.parent.mkdir(parents=True, exist_ok=True)
    decanonicalized_qa_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    decanonicalized_passage_path.write_text(
        transformed_passage,
        encoding="utf-8",
    )
    write_score_json(decanonicalized_qa_path, transformed_qa)
    write_score_json(
        metadata_path,
        {
            "dataset_id": (
                f"{args.run_name or default_run_name(args.qa_json)}_{method}"
                "_target_decanonicalized"
            ),
            "method": method,
            "source": {
                "passage_file": str(args.passage_file),
                "qa_file": str(args.qa_json),
                "source_decanonicalized_passage_file": str(
                    method_output_paths(args, method)["source_decanonicalized_passage"]
                ),
                "translated_passage_file": str(translated_passage_path),
                "shared_decanonicalized_qa_file": str(shared_decanonicalized_qa_path),
            },
            "outputs": {
                "passage_file": str(decanonicalized_passage_path),
                "qa_file": str(decanonicalized_qa_path),
            },
            "canonicalization": {
                "method": "llm",
                "model": canonicalization_model,
                "mapping": entries,
                "entity_inventory_file": (
                    str(entity_inventory_path) if entity_inventory_path else None
                ),
            },
        },
    )
    return True


def run_answer_stage(
    args: argparse.Namespace,
    decanonicalized_passage_path: Path,
    decanonicalized_qa_path: Path,
    generated_answers_path: Path,
    upstream_changed: bool,
) -> bool:
    if not should_run(
        generated_answers_path,
        force=args.force,
        force_stage=args.force_answer or upstream_changed,
    ):
        print(f"reuse answer: {generated_answers_path}")
        return False

    print(f"run answer: {generated_answers_path}")
    passage = load_passage(decanonicalized_passage_path)
    questions = public_questions(load_qa_items(decanonicalized_qa_path))
    answer_model = args.answer_model
    if not answer_model:
        if args.answer_provider == "ollama":
            answer_model = os.getenv("OLLAMA_EVALUATOR_MODEL", "llama3.2:3b")
        else:
            answer_model = os.getenv("OPENAI_EVALUATOR_MODEL", "gpt-4.1-mini")
    answers = generate_answers(
        passage,
        questions,
        provider=args.answer_provider,
        model=answer_model,
        ollama_base_url=args.ollama_base_url,
        batch_size=args.answer_batch_size,
        verse_window=None if args.answer_verse_window < 0 else args.answer_verse_window,
        retries=args.retries,
        dry_run=False,
        allow_partial_answers=args.allow_partial_answers,
        ollama_no_think=args.ollama_no_think,
        expanded_answer_format=args.expanded_answer_format,
        mcq_choice_mapper=args.mcq_choice_mapper,
        mcq_choice_model=args.mcq_choice_model,
    )
    write_generated_json(generated_answers_path, answers)
    return True


def run_backtranslate_stage(
    args: argparse.Namespace,
    generated_answers_path: Path,
    backtranslated_answers_path: Path,
    upstream_changed: bool,
) -> bool:
    if not should_run(
        backtranslated_answers_path,
        force=args.force,
        force_stage=args.force_backtranslate or upstream_changed,
    ):
        print(f"reuse backtranslate: {backtranslated_answers_path}")
        return False

    print(f"run backtranslate: {backtranslated_answers_path}")
    generated_items = extract_items(load_score_json(generated_answers_path))
    standard_items = extract_items(load_score_json(args.qa_json))
    backtranslated = backtranslate_generated_answers(
        generated_items,
        standard_items,
        translation_model=args.translation_model,
        retries=args.retries,
        batch_size=args.backtranslation_batch_size,
    )
    write_score_json(backtranslated_answers_path, backtranslated)
    return True


def run_score_stage(
    args: argparse.Namespace,
    backtranslated_answers_path: Path,
    scores_path: Path,
    upstream_changed: bool,
) -> bool:
    if not should_run(
        scores_path,
        force=args.force,
        force_stage=args.force_score or upstream_changed,
    ):
        print(f"reuse score: {scores_path}")
        return False

    print(f"run score: {scores_path}")
    generated_items = extract_items(load_score_json(backtranslated_answers_path))
    standard_items = extract_items(load_score_json(args.qa_json))
    scored = score_items(
        generated_items,
        standard_items,
        judge_model=args.judge_model,
        translation_model=args.translation_model,
        retries=args.retries,
        skip_llm=args.skip_llm,
        placeholder_standard_answers=True,
        judge_batch_size=args.judge_batch_size,
    )
    write_score_json(
        scores_path,
        {
            "summary": summarize(scored),
            "items": scored,
        },
    )
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run QA translation, decanonicalization, GPT answer generation, "
            "back-translation, and scoring."
        )
    )
    parser.add_argument(
        "passage_file",
        type=Path,
        help="Original English passage text or JSON file.",
    )
    parser.add_argument(
        "qa_json",
        type=Path,
        help="Original English QA set with standard answers.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for cached pipeline outputs. Default: evaluation/outputs.",
    )
    parser.add_argument("--run-name", help="Output filename prefix.")
    parser.add_argument(
        "--translated-qa-json",
        type=Path,
        help="Override translated QA output path.",
    )
    parser.add_argument(
        "--decanonicalized-qa-json",
        type=Path,
        help="Override shared decanonicalized QA output path.",
    )
    parser.add_argument(
        "--mapping-json",
        type=Path,
        help="Optional JSON object mapping canonical Chinese terms to placeholders.",
    )
    parser.add_argument(
        "--entity-inventory-json",
        type=Path,
        help=(
            "Override chapter-local entity inventory path. Default: "
            "<output-dir>/_shared/<run-name>_entity_inventory.json."
        ),
    )
    parser.add_argument(
        "--skip-entity-discovery",
        action="store_true",
        help="Disable LLM chapter-local entity inventory discovery.",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        help=(
            "Passage translation methods to run. Default: existing baseline methods. "
            "Also supports nllb-200-1.3B-dropout or "
            "nllb-200-1.3B-dropout-<rate>, where rate is 0.0 to 0.9."
        ),
    )
    parser.add_argument(
        "--include-nllb-dropout-gradient",
        action="store_true",
        help=(
            "Also run NLLB-200 1.3B dropout methods for rates "
            "0.0, 0.1, 0.2, 0.3, 0.5, 0.7, and 0.9."
        ),
    )
    parser.add_argument(
        "--skip-llm-quality-methods",
        action="store_true",
        help="Skip llm_prompt_low, llm_prompt_medium, and llm_prompt_high.",
    )
    parser.add_argument(
        "--target-language",
        default="Simplified Chinese",
        help="Passage and question translation target language. Default: Simplified Chinese.",
    )
    parser.add_argument(
        "--source-language",
        default="en",
        help="Passage source language for translation-quality methods. Default: en.",
    )
    parser.add_argument(
        "--translation-model",
        default=os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini"),
        help="OpenAI model for QA translation and answer back-translation.",
    )
    parser.add_argument(
        "--passage-translation-model",
        default=os.getenv("OPENAI_PASSAGE_TRANSLATION_MODEL", "gpt-4.1-mini"),
        help="OpenAI model for GPT/LLM passage translation-quality methods.",
    )
    parser.add_argument(
        "--canonicalization-model",
        default=os.getenv("OPENAI_CANONICALIZATION_MODEL"),
        help=(
            "OpenAI model for post-translation entity/object canonicalization. "
            "Default: OPENAI_CANONICALIZATION_MODEL or --translation-model."
        ),
    )
    parser.add_argument(
        "--entity-discovery-model",
        default=os.getenv("OPENAI_ENTITY_DISCOVERY_MODEL"),
        help=(
            "OpenAI model for chapter-local entity discovery. Default: "
            "OPENAI_ENTITY_DISCOVERY_MODEL or --translation-model."
        ),
    )
    parser.add_argument(
        "--answer-provider",
        choices=("openai", "ollama"),
        default=os.getenv("EVALUATOR_PROVIDER", "openai"),
        help="Model provider for answer generation. Default: EVALUATOR_PROVIDER or openai.",
    )
    parser.add_argument(
        "--answer-model",
        default=None,
        help=(
            "Model for answer generation. Defaults to llama3.2:3b for Ollama, "
            "or OPENAI_EVALUATOR_MODEL/gpt-4.1-mini for OpenAI."
        ),
    )
    parser.add_argument(
        "--allow-partial-answers",
        action="store_true",
        help=(
            "Write failed answer records instead of aborting a method when a "
            "question fails after retries. Failed MCQs use selected_choice null "
            "and score as wrong."
        ),
    )
    parser.add_argument(
        "--ollama-no-think",
        action="store_true",
        help="Prefix Ollama answer prompts with /no_think for Qwen3-style thinking models.",
    )
    parser.add_argument(
        "--expanded-answer-format",
        action="store_true",
        help=(
            "Ask the answer model to include answer_confidence, "
            "insufficient_information, and evidence_quality in generated answers."
        ),
    )
    parser.add_argument(
        "--mcq-choice-mapper",
        choices=("rules", "openai"),
        default=os.getenv("MCQ_CHOICE_MAPPER", "rules"),
        help=(
            "How to map raw MCQ answers to A-D. rules uses deterministic parsing. "
            "openai uses rules first, then asks OpenAI to choose the closest option. "
            "Default: MCQ_CHOICE_MAPPER or rules."
        ),
    )
    parser.add_argument(
        "--mcq-choice-model",
        default=os.getenv("OPENAI_MCQ_CHOICE_MODEL", "gpt-4.1-mini"),
        help=(
            "OpenAI model for --mcq-choice-mapper openai. "
            "Default: OPENAI_MCQ_CHOICE_MODEL or gpt-4.1-mini."
        ),
    )
    parser.add_argument(
        "--ollama-base-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        help="Ollama server base URL. Default: OLLAMA_BASE_URL or localhost:11434.",
    )
    parser.add_argument(
        "--judge-model",
        default=os.getenv("OPENAI_JUDGE_MODEL", "gpt-4.1-mini"),
        help="OpenAI model for semantic judging.",
    )
    parser.add_argument(
        "--translation-batch-size",
        type=int,
        default=20,
        help="QA items per translation request. Default: 20.",
    )
    parser.add_argument(
        "--answer-batch-size",
        type=int,
        default=5,
        help=(
            "Questions per answer-generation request when --answer-verse-window is -1. "
            "Default: 5."
        ),
    )
    parser.add_argument(
        "--answer-verse-window",
        type=int,
        default=2,
        help=(
            "Verses before/after each question's passage_reference to send to the "
            "answer model. Default: 2. Use -1 to send the full passage and allow "
            "batching."
        ),
    )
    parser.add_argument(
        "--backtranslation-batch-size",
        type=int,
        default=20,
        help="Generated open answers per back-translation request. Default: 20.",
    )
    parser.add_argument(
        "--judge-batch-size",
        type=int,
        default=20,
        help="Open answers per LLM judge request. Default: 20.",
    )
    parser.add_argument("--helsinki-model")
    parser.add_argument("--mbart-model")
    parser.add_argument("--nllb-distilled-model")
    parser.add_argument("--nllb-model")
    parser.add_argument(
        "--nllb-dropout-rate",
        type=float,
        default=0.0,
        help=(
            "Dropout rate for method nllb-200-1.3B-dropout. Must be 0.0 to 0.9. "
            "Ignored by methods that include the rate in the method name."
        ),
    )
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument(
        "--continue-on-method-error",
        action="store_true",
        help="Continue with later methods if one translation method fails.",
    )
    parser.add_argument(
        "--stop-after",
        choices=STOP_STAGES,
        help="Stop after the named pipeline stage. Default: score.",
    )
    parser.add_argument("--force", action="store_true", help="Rerun every stage.")
    parser.add_argument("--force-entity-inventory", action="store_true")
    parser.add_argument("--force-translate", action="store_true")
    parser.add_argument("--force-passage-translate", action="store_true")
    parser.add_argument("--force-decanonicalize", action="store_true")
    parser.add_argument("--force-answer", action="store_true")
    parser.add_argument("--force-backtranslate", action="store_true")
    parser.add_argument("--force-score", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.retries < 0:
        raise PipelineError("--retries must be zero or greater.")
    try:
        validate_nllb_dropout_rate(args.nllb_dropout_rate)
    except TranslationQualityError as exc:
        raise PipelineError(str(exc)) from exc
    if args.answer_verse_window < -1:
        raise PipelineError("--answer-verse-window must be -1 or greater.")
    for field in (
        "translation_batch_size",
        "answer_batch_size",
        "backtranslation_batch_size",
        "judge_batch_size",
    ):
        if getattr(args, field) < 1:
            raise PipelineError(f"--{field.replace('_', '-')} must be at least 1.")
    if not args.passage_file.exists():
        raise PipelineError(f"Passage file not found: {args.passage_file}")
    if not args.qa_json.exists():
        raise PipelineError(f"QA JSON file not found: {args.qa_json}")
    methods = selected_methods(args)
    if not methods:
        raise PipelineError("No translation methods selected.")
    for method in methods:
        paths = method_output_paths(args, method)
        if not is_supported_or_existing_artifact_method(method, paths):
            raise PipelineError(
                f"Unknown translation method: {method}. If this is an external "
                "artifact folder, it must already contain passage_translation.json, "
                "passage_target.txt, passage_target_decanonicalized.txt, and "
                "qa_target_decanonicalized.json."
            )

def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        methods = selected_methods(args)
        shared_paths = shared_output_paths(args)
        method_paths = {
            method: method_output_paths(args, method)
            for method in methods
        }
        entity_inventory_needed = entity_inventory_stage_needed(
            args,
            shared_paths,
            method_paths,
        )
        if shared_needs_openai(args, shared_paths, entity_inventory_needed) or any(
            method_needs_openai(args, method, paths)
            for method, paths in method_paths.items()
        ):
            require_openai_key()

        entity_inventory_changed = run_entity_inventory_stage(
            args,
            shared_paths["entity_inventory"],
            needed=entity_inventory_needed,
        )
        entity_inventory = (
            None
            if args.skip_entity_discovery
            else load_entity_inventory(shared_paths["entity_inventory"])
        )
        if args.stop_after == "entity-inventory":
            print("pipeline complete")
            print(f"entity_inventory: {shared_paths['entity_inventory']}")
            return 0

        translated_qa_changed = False
        if stage_enabled(args, "translate"):
            translated_qa_changed = run_translate_stage(
                args,
                shared_paths["translated_qa"],
            )
        if args.stop_after == "translate":
            print("pipeline complete")
            print(f"entity_inventory: {shared_paths['entity_inventory']}")
            print(f"shared_translated_qa: {shared_paths['translated_qa']}")
            return 0

        shared_decanonicalized_qa_changed = False
        if stage_enabled(args, "decanonicalize"):
            shared_decanonicalized_qa_changed = run_shared_qa_decanonicalize_stage(
                args,
                shared_paths["translated_qa"],
                shared_paths["decanonicalized_qa"],
                translated_qa_changed or entity_inventory_changed,
                entity_inventory,
            )

        completed = []
        failed = []
        for method in methods:
            paths = method_paths[method]
            try:
                passage_changed = False
                if stage_enabled(args, "passage-translate"):
                    passage_changed = run_passage_translate_stage(
                        args,
                        method,
                        paths["translated_passage_json"],
                        paths["translated_passage"],
                        entity_inventory,
                    )
                if not stage_enabled(args, "decanonicalize"):
                    completed.append(method)
                    continue
                method_qa_changed = run_method_qa_stage(
                    shared_paths["translated_qa"],
                    paths["translated_qa"],
                    force=args.force or args.force_translate,
                    upstream_changed=translated_qa_changed,
                    method=method,
                )
                decanonicalized_changed = run_decanonicalize_stage(
                    args,
                    method,
                    paths["translated_passage"],
                    shared_paths["decanonicalized_qa"],
                    paths["decanonicalized_passage"],
                    paths["decanonicalized_qa"],
                    paths["decanonicalized_metadata"],
                    passage_changed
                    or method_qa_changed
                    or entity_inventory_changed
                    or shared_decanonicalized_qa_changed,
                    entity_inventory,
                    shared_paths["entity_inventory"]
                    if not args.skip_entity_discovery
                    else None,
                )
                if not stage_enabled(args, "answer"):
                    completed.append(method)
                    continue
                answers_changed = run_answer_stage(
                    args,
                    paths["decanonicalized_passage"],
                    paths["decanonicalized_qa"],
                    paths["generated_answers"],
                    decanonicalized_changed,
                )
                if not stage_enabled(args, "backtranslate"):
                    completed.append(method)
                    continue
                backtranslated_changed = run_backtranslate_stage(
                    args,
                    paths["generated_answers"],
                    paths["backtranslated_answers"],
                    answers_changed,
                )
                if stage_enabled(args, "score"):
                    run_score_stage(
                        args,
                        paths["backtranslated_answers"],
                        paths["scores"],
                        backtranslated_changed,
                    )
                completed.append(method)
            except (
                GenerationError,
                PipelineError,
                ScoreError,
                TranslationError,
                TranslationQualityError,
            ) as exc:
                if not args.continue_on_method_error:
                    raise
                failed.append((method, str(exc)))
                print(f"[{method}] error: {exc}", file=sys.stderr)

    except (
        GenerationError,
        PipelineError,
        ScoreError,
        TranslationError,
        TranslationQualityError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("pipeline complete")
    if not args.skip_entity_discovery:
        print(f"entity_inventory: {shared_paths['entity_inventory']}")
    print(f"shared_translated_qa: {shared_paths['translated_qa']}")
    print(f"shared_decanonicalized_qa: {shared_paths['decanonicalized_qa']}")
    for method in completed:
        print(f"{method}: {method_paths[method]['method_dir']}")
    if failed:
        print("failed methods:")
        for method, message in failed:
            print(f"{method}: {message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
