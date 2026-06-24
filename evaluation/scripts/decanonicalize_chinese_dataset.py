#!/usr/bin/env python3
"""Create a de-canonicalized Chinese Bible QA evaluation dataset."""

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_MAPPING = {
    "路加福音": "文本甲",
    "路加": "作者甲",
    "提阿非罗斯": "收信者甲",
    "提阿非罗": "收信者甲",
    "撒迦利亚": "人物甲",
    "以利沙伯": "人物乙",
    "约翰": "人物丙",
    "马利亚": "人物丁",
    "加百列": "使者乙",
    "以色列": "族群甲",
    "亚伯拉罕": "先祖甲",
    "大卫": "君王甲",
    "拿撒勒": "村庄甲",
    "加利利": "地区甲",
    "耶路撒冷": "城市甲",
    "亚比雅": "班次甲",
    "亚伦": "祖先乙",
    "希律": "统治者甲",
    "希律王": "统治者甲",
    "以利亚": "先知甲",
    "约瑟": "人物戊",
    "耶稣": "人物己",
    "雅各": "先祖乙",
    "神": "至高者甲",
    "主": "主人甲",
    "圣灵": "灵甲",
    "圣鬼": "灵甲",
    "最高者": "尊者甲",
    "祭司": "职员甲",
    "殿": "场所甲",
    "庙": "场所甲",
    "香气": "材料甲",
    "香料": "材料甲",
    "熏香": "材料甲",
    "焚香": "材料甲",
    "烧香": "材料甲",
    "献香": "材料甲",
    "香": "材料甲",
    "祈祷": "请求",
    "祷告": "请求",
}

PROTECTED_TOKEN_MAPPING = {
    "__TEXT_A__": "文本甲",
    "__AUTHOR_A__": "作者甲",
    "__RECIPIENT_A__": "收信者甲",
    "__PERSON_A__": "人物甲",
    "__PERSON_B__": "人物乙",
    "__PERSON_C__": "人物丙",
    "__PERSON_D__": "人物丁",
    "__PERSON_E__": "人物戊",
    "__PERSON_F__": "人物己",
    "__MESSENGER_B__": "使者乙",
    "__PEOPLE_A__": "族群甲",
    "__ANCESTOR_A__": "先祖甲",
    "__ANCESTOR_B__": "先祖乙",
    "__KING_A__": "君王甲",
    "__VILLAGE_A__": "村庄甲",
    "__REGION_A__": "地区甲",
    "__CITY_A__": "城市甲",
    "__DIVISION_A__": "班次甲",
    "__FOREFATHER_B__": "祖先乙",
    "__RULER_A__": "统治者甲",
    "__PROPHET_A__": "先知甲",
    "__MOST_HIGH_A__": "至高者甲",
    "__MASTER_A__": "主人甲",
    "__SPIRIT_A__": "灵甲",
    "__HONORED_A__": "尊者甲",
    "__WORKER_A__": "职员甲",
    "__PLACE_A__": "场所甲",
    "__MATERIAL_A__": "材料甲",
    "__REQUEST_A__": "请求",
}

MACHINE_TRANSLATED_PROTECTED_TOKEN_MAPPING = {
    "__人_a__": "人物甲",
    "__人_b__": "人物乙",
    "__人_c__": "人物丙",
    "__人_d__": "人物丁",
    "__人_e__": "人物戊",
    "__人_f__": "人物己",
    "__国王_a__": "君王甲",
    "__工人_a__": "职员甲",
    "__祖先_a__": "先祖甲",
    "__master_a__": "主人甲",
    "__person_a__": "人物甲",
    "__person_b__": "人物乙",
    "__person_c__": "人物丙",
    "__person_d__": "人物丁",
    "__person_e__": "人物戊",
    "__person_f__": "人物己",
}

DEFAULT_ENGLISH_TOKEN_MAPPING = {
    "Luke": "__AUTHOR_A__",
    "Luke's": "__AUTHOR_A__",
    "Luke’s": "__AUTHOR_A__",
    "Theophilus": "__RECIPIENT_A__",
    "Theophilus's": "__RECIPIENT_A__",
    "Theophilus’s": "__RECIPIENT_A__",
    "Zechariah": "__PERSON_A__",
    "Zechariah's": "__PERSON_A__",
    "Zechariah’s": "__PERSON_A__",
    "Elizabeth": "__PERSON_B__",
    "Elizabeth's": "__PERSON_B__",
    "Elizabeth’s": "__PERSON_B__",
    "John": "__PERSON_C__",
    "John's": "__PERSON_C__",
    "John’s": "__PERSON_C__",
    "Mary": "__PERSON_D__",
    "Mary's": "__PERSON_D__",
    "Mary’s": "__PERSON_D__",
    "Gabriel": "__MESSENGER_B__",
    "Israel": "__PEOPLE_A__",
    "Israel's": "__PEOPLE_A__",
    "Israel’s": "__PEOPLE_A__",
    "Abraham": "__ANCESTOR_A__",
    "Abraham's": "__ANCESTOR_A__",
    "Abraham’s": "__ANCESTOR_A__",
    "David": "__KING_A__",
    "David's": "__KING_A__",
    "David’s": "__KING_A__",
    "Nazareth": "__VILLAGE_A__",
    "Galilee": "__REGION_A__",
    "Jerusalem": "__CITY_A__",
    "Abijah": "__DIVISION_A__",
    "Aaron": "__FOREFATHER_B__",
    "Aaron's": "__FOREFATHER_B__",
    "Aaron’s": "__FOREFATHER_B__",
    "Herod": "__RULER_A__",
    "Herod's": "__RULER_A__",
    "Herod’s": "__RULER_A__",
    "Elijah": "__PROPHET_A__",
    "Elijah's": "__PROPHET_A__",
    "Elijah’s": "__PROPHET_A__",
    "Joseph": "__PERSON_E__",
    "Joseph's": "__PERSON_E__",
    "Joseph’s": "__PERSON_E__",
    "Jesus": "__PERSON_F__",
    "Jesus'": "__PERSON_F__",
    "Jesus’": "__PERSON_F__",
    "Jacob": "__ANCESTOR_B__",
    "Jacob's": "__ANCESTOR_B__",
    "Jacob’s": "__ANCESTOR_B__",
    "Holy Spirit": "__SPIRIT_A__",
    "Most High": "__HONORED_A__",
    "God": "__MOST_HIGH_A__",
    "God's": "__MOST_HIGH_A__",
    "God’s": "__MOST_HIGH_A__",
    "Lord": "__MASTER_A__",
    "Lord's": "__MASTER_A__",
    "Lord’s": "__MASTER_A__",
    "priest": "__WORKER_A__",
    "priests": "__WORKER_A__",
    "temple": "__PLACE_A__",
    "incense": "__MATERIAL_A__",
    "prayer": "__REQUEST_A__",
    "prayers": "__REQUEST_A__",
    "praying": "__REQUEST_A__",
}

UNRESOLVED_PROTECTED_TOKEN_RE = re.compile(r"__[^\s]+?__")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def protected_token_mapping() -> dict[str, str]:
    mapping = dict(PROTECTED_TOKEN_MAPPING)
    mapping.update(
        {key.lower(): value for key, value in PROTECTED_TOKEN_MAPPING.items()}
    )
    mapping.update(MACHINE_TRANSLATED_PROTECTED_TOKEN_MAPPING)
    return mapping


def decanonicalization_mapping(
    extra_mapping: dict[str, str] | None = None,
) -> dict[str, str]:
    mapping = dict(DEFAULT_MAPPING)
    mapping.update(protected_token_mapping())
    if extra_mapping:
        mapping.update(extra_mapping)
    return mapping


def replace_text(value: str, mapping: dict[str, str]) -> str:
    # Single-pass replacement prevents inserted placeholders like 主人甲 from
    # being modified again by shorter source keys such as 主.
    sources = [source for source in mapping if source]
    if not sources:
        return value
    protected = value
    restore_tokens = {}
    for index, placeholder in enumerate(
        sorted(
            {replacement for replacement in mapping.values() if replacement},
            key=len,
            reverse=True,
        )
    ):
        token = f"\ue000{index}\ue000"
        protected = protected.replace(placeholder, token)
        restore_tokens[token] = placeholder
    pattern = re.compile(
        "|".join(re.escape(source) for source in sorted(sources, key=len, reverse=True))
    )
    result = pattern.sub(lambda match: mapping[match.group(0)], protected)
    for token, placeholder in restore_tokens.items():
        result = result.replace(token, placeholder)
    result = result.replace("精至高者甲", "精神")
    result = result.replace("使者甲使者乙", "使者乙")
    return result


def replace_english_terms(value: str, mapping: dict[str, str]) -> str:
    sources = [source for source in mapping if source]
    if not sources:
        return value
    protected = value
    restore_tokens = {}
    for index, replacement in enumerate(
        sorted(
            {replacement for replacement in mapping.values() if replacement},
            key=len,
            reverse=True,
        )
    ):
        token = f"\ue100{index}\ue100"
        protected = protected.replace(replacement, token)
        restore_tokens[token] = replacement

    pattern = re.compile(
        r"(?<![A-Za-z])("
        + "|".join(re.escape(source) for source in sorted(sources, key=len, reverse=True))
        + r")(?![A-Za-z])"
    )
    result = pattern.sub(lambda match: mapping[match.group(1)], protected)
    for token, replacement in restore_tokens.items():
        result = result.replace(token, replacement)
    return result


def transform_value(value: Any, mapping: dict[str, str]):
    if isinstance(value, str):
        return replace_text(value, mapping)
    if isinstance(value, list):
        return [transform_value(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: transform_value(item, mapping) for key, item in value.items()}
    return value


def transform_qa_items(items: list[dict], mapping: dict[str, str]) -> list[dict]:
    transformed = []
    for item in items:
        new_item = transform_value(item, mapping)
        new_item["decanonicalized"] = True
        transformed.append(new_item)
    return transformed


def unresolved_protected_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(value, str):
        tokens.extend(UNRESOLVED_PROTECTED_TOKEN_RE.findall(value))
    elif isinstance(value, list):
        for item in value:
            tokens.extend(unresolved_protected_tokens(item))
    elif isinstance(value, dict):
        for item in value.values():
            tokens.extend(unresolved_protected_tokens(item))
    return sorted(set(tokens))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Decanonicalize a Chinese passage and Chinese QA set."
    )
    parser.add_argument("passage_file", type=Path)
    parser.add_argument("qa_json", type=Path)
    parser.add_argument("output_passage_file", type=Path)
    parser.add_argument("output_qa_json", type=Path)
    parser.add_argument(
        "--mapping-json",
        type=Path,
        help="Optional JSON object mapping source strings to replacement strings.",
    )
    parser.add_argument(
        "--metadata-json",
        type=Path,
        help="Optional combined dataset metadata output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mapping = decanonicalization_mapping(
        load_json(args.mapping_json) if args.mapping_json else None
    )

    passage_text = args.passage_file.read_text(encoding="utf-8")
    qa_data = load_json(args.qa_json)
    if isinstance(qa_data, dict):
        qa_items = [qa_data]
    elif isinstance(qa_data, list) and all(isinstance(item, dict) for item in qa_data):
        qa_items = qa_data
    else:
        raise SystemExit("qa_json must be an object or array of objects")

    transformed_passage = replace_text(passage_text, mapping)
    transformed_qa = transform_qa_items(qa_items, mapping)
    unresolved = unresolved_protected_tokens(transformed_passage)
    unresolved.extend(unresolved_protected_tokens(transformed_qa))
    unresolved = sorted(set(unresolved))
    if unresolved:
        raise SystemExit(
            "unresolved protected token(s) after decanonicalization: "
            + ", ".join(unresolved)
        )

    args.output_passage_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_qa_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_passage_file.write_text(transformed_passage, encoding="utf-8")
    args.output_qa_json.write_text(
        json.dumps(transformed_qa, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.metadata_json:
        args.metadata_json.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_json.write_text(
            json.dumps(
                {
                    "dataset_id": "luke_ch1_zh_decanonicalized_v1",
                    "source": {
                        "passage_file": str(args.passage_file),
                        "qa_file": str(args.qa_json),
                    },
                    "outputs": {
                        "passage_file": str(args.output_passage_file),
                        "qa_file": str(args.output_qa_json),
                    },
                    "mapping": mapping,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    print(f"Wrote passage to {args.output_passage_file}")
    print(f"Wrote {len(transformed_qa)} QA item(s) to {args.output_qa_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
