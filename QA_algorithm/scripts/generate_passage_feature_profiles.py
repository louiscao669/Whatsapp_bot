#!/usr/bin/env python3
"""Generate passage-level feature profiles for QA scheduling.

For each QA item, this script extracts the question passage window
(`passage_reference` +/- N verses), computes deterministic lexical counts, and
asks an LLM to judge sentence-level translation components. The final output is
a passage-level aggregate table per question/window.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSE_MARKER_RE = re.compile(r"(?<![\w\]])(\d{1,3})\s+")
REFERENCE_RE = re.compile(r"(\d+)\s*:\s*(\d+)(?:\s*[-–—]\s*(\d+))?")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

FUNCTION_LABELS = ("declarative", "interrogative", "imperative", "exclamatory")
STYLE_LABELS = ("narrative", "descriptive", "expository", "persuasive", "dialogue", "poetic")
SEMANTIC_PATTERN_LABELS = (
    "S+V",
    "S+V+O",
    "S+V+C",
    "S+V+O+O",
    "S+V+O+C",
    "S+V+O+A",
    "other",
)
STRUCTURE_LABELS = ("simple", "compound", "complex", "compound_complex", "fragment")
DIFFICULTY_BUCKETS = ("easy", "medium", "hard")
NON_LEXICAL_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "if",
        "than",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "about",
        "between",
        "under",
        "over",
        "without",
        "within",
        "along",
        "among",
        "upon",
        "i",
        "me",
        "my",
        "mine",
        "you",
        "your",
        "yours",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "it",
        "its",
        "we",
        "us",
        "our",
        "ours",
        "they",
        "them",
        "their",
        "theirs",
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "this",
        "that",
        "these",
        "those",
        "not",
        "no",
        "there",
        "here",
        "then",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "some",
        "any",
    }
)


class FeatureProfileError(Exception):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise FeatureProfileError("LLM response must be a JSON object.")
    return data


def load_qa_items(path: Path) -> list[dict]:
    data = load_json(path)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "questions", "qa_pairs"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise FeatureProfileError(f"QA file must be a list or object with items/questions: {path}")


def index_passage_verses(passage: str) -> dict[int, str]:
    matches = []
    for match in VERSE_MARKER_RE.finditer(passage):
        verse_number = int(match.group(1))
        if 1 <= verse_number <= 200:
            matches.append((verse_number, match.start()))
    verses: dict[int, str] = {}
    for index, (verse_number, start) in enumerate(matches):
        end = matches[index + 1][1] if index + 1 < len(matches) else len(passage)
        verse_text = passage[start:end].strip()
        if verse_text:
            verses[verse_number] = verse_text
    return verses


def reference_from_item(item: dict) -> str:
    return str(
        item.get("passage_reference")
        or item.get("title")
        or item.get("reference")
        or item.get("passage_ref")
        or ""
    ).strip()


def parse_reference(reference: str) -> tuple[int | None, int, int]:
    match = REFERENCE_RE.search(reference)
    if not match:
        raise FeatureProfileError(f"Could not parse passage reference: {reference}")
    chapter = int(match.group(1))
    start = int(match.group(2))
    end = int(match.group(3) or start)
    if end < start:
        start, end = end, start
    return chapter, start, end


def local_window(
    verse_index: dict[int, str],
    *,
    reference: str,
    verse_window: int,
) -> tuple[str, dict]:
    chapter, reference_start, reference_end = parse_reference(reference)
    if not verse_index:
        raise FeatureProfileError("Passage has no verse markers.")
    start = max(min(verse_index), reference_start - verse_window)
    end = min(max(verse_index), reference_end + verse_window)
    selected = [
        verse_index[verse_number]
        for verse_number in range(start, end + 1)
        if verse_number in verse_index
    ]
    return "\n".join(selected).strip(), {
        "chapter": chapter,
        "reference": reference,
        "reference_start": reference_start,
        "reference_end": reference_end,
        "window_start": start,
        "window_end": end,
        "verse_window": verse_window,
        "window_verse_count": end - start + 1,
    }


def load_spacy_model(model_name: str) -> Any:
    try:
        import spacy
    except ImportError as exc:
        raise FeatureProfileError(
            "spaCy is required for lexical feature extraction. Install it with "
            "`python3 -m pip install spacy`."
        ) from exc
    try:
        return spacy.load(model_name)
    except OSError as exc:
        raise FeatureProfileError(
            f"spaCy model not found: {model_name}. Install it with "
            f"`python3 -m spacy download {model_name}`."
        ) from exc


def token_lemma(token: Any) -> str:
    lemma = str(getattr(token, "lemma_", "") or "").strip().lower()
    if not lemma or lemma == "-pron-":
        lemma = str(getattr(token, "lower_", "") or token.text).strip().lower()
    return lemma


def morph_values(token: Any, key: str) -> list[str]:
    morph = getattr(token, "morph", None)
    if morph is None:
        return []
    try:
        values = morph.get(key)
    except Exception:
        return []
    return [str(value) for value in values if str(value)]


def is_non_lexical_token(token: Any) -> bool:
    word = str(getattr(token, "lower_", "") or token.text).strip().lower()
    lemma = token_lemma(token)
    return word in NON_LEXICAL_WORDS or lemma in NON_LEXICAL_WORDS


def lexical_profile(text: str, nlp: Any) -> dict:
    doc = nlp(text)
    tokens = [
        token
        for token in doc
        if not token.is_space and (token.is_alpha or token.like_num)
    ]
    words = [token.text.lower() for token in tokens]
    lemmas = [token_lemma(token) for token in tokens]
    lexical_tokens = [
        token for token in tokens if token.is_alpha and not is_non_lexical_token(token)
    ]
    non_lexical_tokens = [
        token for token in tokens if token.is_alpha and is_non_lexical_token(token)
    ]
    number_tokens = [token for token in tokens if token.like_num and not token.is_alpha]
    lexical_words = [token.text.lower() for token in lexical_tokens]
    lexical_lemmas = [token_lemma(token) for token in lexical_tokens]
    non_lexical_words = [token.text.lower() for token in non_lexical_tokens]
    non_lexical_lemmas = [token_lemma(token) for token in non_lexical_tokens]
    numbers = [token.text.lower() for token in number_tokens]
    tense_values = [
        value
        for token in tokens
        for value in morph_values(token, "Tense")
    ]
    verb_form_values = [
        value
        for token in tokens
        for value in morph_values(token, "VerbForm")
    ]
    morph_values_all = [
        str(token.morph)
        for token in tokens
        if str(getattr(token, "morph", "") or "")
    ]
    return {
        "token_count": len(words),
        "unique_word_count": len(set(words)),
        "unique_lemma_count": len(set(lemmas)),
        "word_counts": dict(Counter(words).most_common()),
        "form_counts": dict(Counter(words).most_common()),
        "lemma_counts": dict(Counter(lemmas).most_common()),
        "lexical_word_counts": dict(Counter(lexical_words).most_common()),
        "lexical_lemma_counts": dict(Counter(lexical_lemmas).most_common()),
        "content_lemma_counts": dict(Counter(lexical_lemmas).most_common()),
        "non_lexical_word_counts": dict(Counter(non_lexical_words).most_common()),
        "non_lexical_lemma_counts": dict(Counter(non_lexical_lemmas).most_common()),
        "number_counts": dict(Counter(numbers).most_common()),
        "pos_counts": dict(Counter(token.pos_ or "UNKNOWN" for token in tokens).most_common()),
        "tag_counts": dict(Counter(token.tag_ or "UNKNOWN" for token in tokens).most_common()),
        "morph_counts": dict(Counter(morph_values_all).most_common()),
        "verb_form_counts": dict(Counter(verb_form_values).most_common()),
        "tense_counts": dict(Counter(tense_values).most_common()),
    }


def split_sentences(text: str) -> list[str]:
    parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    sentences = []
    for part in parts:
        cleaned = re.sub(r"^\d+\s+", "", part).strip()
        if cleaned:
            sentences.append(cleaned)
    return sentences


def zero_counts(labels: tuple[str, ...]) -> dict[str, int]:
    return {label: 0 for label in labels}


def normalized_label(value: Any, labels: tuple[str, ...], default: str) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "compound-complex": "compound_complex",
        "compound complex": "compound_complex",
        "svo": "S+V+O",
        "sv": "S+V",
        "svc": "S+V+C",
        "svoo": "S+V+O+O",
        "svoc": "S+V+O+C",
        "svoa": "S+V+O+A",
    }
    raw = aliases.get(raw, raw)
    for label in labels:
        if raw == label.lower():
            return label
    return default


def difficulty_bucket(score: float) -> str:
    if score < 0.34:
        return "easy"
    if score < 0.67:
        return "medium"
    return "hard"


def build_llm_prompt(*, passage: str, sentences: list[str]) -> str:
    return json.dumps(
        {
            "task": (
                "Analyze this Bible passage window for translation-question scheduling. "
                "Label each sentence/clause, then list idioms and formulaic biblical "
                "expressions that appear in the passage. Return JSON only."
            ),
            "labels": {
                "function": list(FUNCTION_LABELS),
                "style": list(STYLE_LABELS),
                "semantic_pattern": list(SEMANTIC_PATTERN_LABELS),
                "structure": list(STRUCTURE_LABELS),
                "difficulty_score": "0.0 easy to 1.0 hard",
            },
            "guidance": [
                "Use idioms only for expressions whose meaning is not fully predictable from the words.",
                "Use formulaic_expressions for repeated biblical/conventional phrases even if their meaning is transparent.",
                "Use canonical keys for idioms/formulaic expressions, lowercase English where possible.",
                "If a sentence contains multiple clauses, choose the dominant semantic pattern and structure.",
                "Do not invent phrases not present in the passage.",
            ],
            "passage": passage,
            "sentences": sentences,
            "schema": {
                "sentences": [
                    {
                        "index": 1,
                        "text": "sentence text",
                        "function": "declarative",
                        "style": "narrative",
                        "semantic_pattern": "S+V+O",
                        "structure": "complex",
                        "difficulty_score": 0.0,
                        "difficulty_bucket": "easy|medium|hard",
                        "idioms": [{"key": "canonical idiom", "surface": "surface phrase"}],
                        "formulaic_expressions": [
                            {"key": "canonical expression", "surface": "surface phrase"}
                        ],
                    }
                ],
                "notes": "brief rationale",
            },
        },
        ensure_ascii=False,
    )


def call_openai(prompt: str, *, model: str) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        raise FeatureProfileError("OPENAI_API_KEY is required unless --dry-run is used.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise FeatureProfileError("Install the openai package to run LLM judgment.") from exc
    client = OpenAI()
    response = client.responses.create(model=model, input=prompt, temperature=0)
    text = getattr(response, "output_text", None)
    if not text:
        chunks = []
        for output in getattr(response, "output", []) or []:
            for content in getattr(output, "content", []) or []:
                value = getattr(content, "text", None)
                if value:
                    chunks.append(value)
        text = "\n".join(chunks)
    return extract_json_object(text or "")


def normalize_phrase_items(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    output = []
    for item in items:
        if isinstance(item, str):
            key = item.strip().lower()
            surface = item.strip()
        elif isinstance(item, dict):
            key = str(item.get("key") or item.get("idiom") or item.get("expression") or "").strip().lower()
            surface = str(item.get("surface") or item.get("text") or key).strip()
        else:
            continue
        if key:
            output.append({"key": key, "surface": surface or key})
    return output


def normalize_sentence_analysis(raw: dict, sentences: list[str]) -> list[dict]:
    raw_sentences = raw.get("sentences")
    if not isinstance(raw_sentences, list):
        raw_sentences = []
    output = []
    for index, sentence in enumerate(sentences, start=1):
        item = raw_sentences[index - 1] if index - 1 < len(raw_sentences) else {}
        if not isinstance(item, dict):
            item = {}
        score = item.get("difficulty_score", 0.5)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.5
        score = min(1.0, max(0.0, score))
        output.append(
            {
                "index": index,
                "text": str(item.get("text") or sentence).strip(),
                "function": normalized_label(
                    item.get("function"), FUNCTION_LABELS, "declarative"
                ),
                "style": normalized_label(item.get("style"), STYLE_LABELS, "narrative"),
                "semantic_pattern": normalized_label(
                    item.get("semantic_pattern"), SEMANTIC_PATTERN_LABELS, "other"
                ),
                "structure": normalized_label(item.get("structure"), STRUCTURE_LABELS, "simple"),
                "difficulty_score": score,
                "difficulty_bucket": difficulty_bucket(score),
                "idioms": normalize_phrase_items(item.get("idioms")),
                "formulaic_expressions": normalize_phrase_items(
                    item.get("formulaic_expressions")
                ),
            }
        )
    return output


def aggregate_llm_features(sentence_analyses: list[dict]) -> dict:
    function_counts = zero_counts(FUNCTION_LABELS)
    style_counts = zero_counts(STYLE_LABELS)
    semantic_counts = zero_counts(SEMANTIC_PATTERN_LABELS)
    structure_counts = zero_counts(STRUCTURE_LABELS)
    difficulty_scores = []
    idiom_counts: Counter[str] = Counter()
    formulaic_counts: Counter[str] = Counter()
    idiom_occurrences = []
    formulaic_occurrences = []

    for sentence in sentence_analyses:
        function_counts[sentence["function"]] += 1
        style_counts[sentence["style"]] += 1
        semantic_counts[sentence["semantic_pattern"]] += 1
        structure_counts[sentence["structure"]] += 1
        difficulty_scores.append(float(sentence["difficulty_score"]))
        for phrase in sentence.get("idioms", []):
            idiom_counts[phrase["key"]] += 1
            idiom_occurrences.append(
                {"sentence_index": sentence["index"], **phrase}
            )
        for phrase in sentence.get("formulaic_expressions", []):
            formulaic_counts[phrase["key"]] += 1
            formulaic_occurrences.append(
                {"sentence_index": sentence["index"], **phrase}
            )

    mean_difficulty = (
        sum(difficulty_scores) / len(difficulty_scores) if difficulty_scores else 0.0
    )
    return {
        "function_counts": function_counts,
        "style_counts": style_counts,
        "semantic_pattern_counts": semantic_counts,
        "structure_counts": structure_counts,
        "idiom_counts": dict(idiom_counts.most_common()),
        "formulaic_expression_counts": dict(formulaic_counts.most_common()),
        "idiom_summary": {
            "has_idiom": bool(idiom_counts),
            "total_idiom_occurrences": sum(idiom_counts.values()),
            "unique_idiom_count": len(idiom_counts),
            "occurrences": idiom_occurrences,
        },
        "formulaic_expression_summary": {
            "has_formulaic_expression": bool(formulaic_counts),
            "total_formulaic_expression_occurrences": sum(formulaic_counts.values()),
            "unique_formulaic_expression_count": len(formulaic_counts),
            "occurrences": formulaic_occurrences,
        },
        "difficulty": {
            "score": mean_difficulty,
            "bucket": difficulty_bucket(mean_difficulty),
            "max_sentence_score": max(difficulty_scores) if difficulty_scores else 0.0,
        },
    }


def question_id(item: dict, index: int) -> str:
    return str(
        item.get("id")
        or item.get("content_id")
        or item.get("passage_id")
        or item.get("reference_id")
        or index
    )


def build_profile(
    *,
    item: dict,
    index: int,
    passage_text: str,
    verse_index: dict[int, str],
    nlp: Any,
    verse_window: int,
    model: str,
    retries: int,
    dry_run: bool,
) -> dict:
    reference = reference_from_item(item)
    window_text, window = local_window(
        verse_index,
        reference=reference,
        verse_window=verse_window,
    )
    sentences = split_sentences(window_text)
    lexical = lexical_profile(window_text, nlp)

    if dry_run:
        sentence_analyses = [
            {
                "index": sentence_index,
                "text": sentence,
                "function": "declarative",
                "style": "narrative",
                "semantic_pattern": "other",
                "structure": "simple",
                "difficulty_score": 0.0,
                "difficulty_bucket": "easy",
                "idioms": [],
                "formulaic_expressions": [],
            }
            for sentence_index, sentence in enumerate(sentences, start=1)
        ]
        llm_notes = "dry_run"
    else:
        prompt = build_llm_prompt(passage=window_text, sentences=sentences)
        last_error: Exception | None = None
        raw = {}
        for attempt in range(retries + 1):
            try:
                raw = call_openai(prompt, model=model)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(2**attempt)
        if last_error:
            raise FeatureProfileError(
                f"LLM feature judgment failed for {reference}: {last_error}"
            ) from last_error
        sentence_analyses = normalize_sentence_analysis(raw, sentences)
        llm_notes = str(raw.get("notes") or "").strip()

    aggregate = aggregate_llm_features(sentence_analyses)
    return {
        "question_id": question_id(item, index),
        "source_item_index": index,
        "passage_reference": reference,
        "feature_window": window,
        "passage_text": window_text,
        "feature_profile": {
            "lexical_counts": lexical,
            **aggregate,
        },
        "sentence_analyses": sentence_analyses,
        "llm_notes": llm_notes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate passage-level feature profiles for QA scheduling."
    )
    parser.add_argument("passage_file", type=Path)
    parser.add_argument("qa_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument(
        "--verse-window",
        type=int,
        default=2,
        help="Verses before/after each question reference. Default 2 gives 5 verses.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI judgment model. Defaults to FEATURE_PROFILE_MODEL or gpt-4.1-mini.",
    )
    parser.add_argument(
        "--spacy-model",
        default=os.getenv("FEATURE_PROFILE_SPACY_MODEL", "en_core_web_sm"),
        help="spaCy model for lexical features. Default: en_core_web_sm.",
    )
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verse_window < 0:
        print("--verse-window must be non-negative", file=sys.stderr)
        return 2
    if args.retries < 0:
        print("--retries must be non-negative", file=sys.stderr)
        return 2
    if not args.passage_file.exists():
        print(f"Passage file not found: {args.passage_file}", file=sys.stderr)
        return 2
    if not args.qa_json.exists():
        print(f"QA file not found: {args.qa_json}", file=sys.stderr)
        return 2

    model = args.model
    if not model:
        model = os.getenv("FEATURE_PROFILE_MODEL")
    if not model:
        model = "gpt-4.1-mini"

    try:
        passage_text = args.passage_file.read_text(encoding="utf-8")
        verse_index = index_passage_verses(passage_text)
        qa_items = load_qa_items(args.qa_json)
        nlp = load_spacy_model(args.spacy_model)
        profiles = [
            build_profile(
                item=item,
                index=index,
                passage_text=passage_text,
                verse_index=verse_index,
                nlp=nlp,
                verse_window=args.verse_window,
                model=model,
                retries=args.retries,
                dry_run=args.dry_run,
            )
            for index, item in enumerate(qa_items, start=1)
        ]
        write_json(
            args.output_json,
            {
                "schema_version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "passage_file": str(args.passage_file),
                "qa_json": str(args.qa_json),
                "provider": "openai",
                "model": model,
                "spacy_model": args.spacy_model,
                "verse_window": args.verse_window,
                "profile_count": len(profiles),
                "profiles": profiles,
            },
        )
    except FeatureProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote feature profiles: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
