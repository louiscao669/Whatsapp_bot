"""parse_tier1_verses: the word-by-word "17 号" artefact (2026-10-26 hard66 run).

pilot_import imports Flask/platform at module scope, so the parser and its
regexes are extracted via AST, the same way test_pilot_import_exclusions does.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_parser():
    src = (REPO_ROOT / "human_pilot" / "pilot_import.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {"_TIER1_MARKER", "_MARKER_NUMBER_WORD", "clean_tier1_verse_text",
             "parse_tier1_verses"}
    keep = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in names)
        or (isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) in names for t in node.targets))
    ]
    namespace = {"re": re}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "pilot_import", "exec"), namespace)
    return namespace


NS = _load_parser()
META = {"id": "t1_acts19", "chapter_start": 19, "verse_start": 16,
        "chapter_end": 19, "verse_end": 18}


def test_marker_rendered_as_number_word_is_stripped():
    text = "16 然后这男人跳了起来。 17 号 这成为已知的到全部这犹太人。 18 许多谁有相信现在来了向前。"
    verses = dict(NS["parse_tier1_verses"](text, META))
    assert verses["19:17"] == "这成为已知的到全部这犹太人。"
    assert verses["19:16"] == "然后这男人跳了起来。"
    assert not any(v.startswith("号") for v in verses.values())


def test_a_real_号_inside_a_verse_is_kept():
    assert NS["clean_tier1_verse_text"]("他的名号传遍各地。") == "他的名号传遍各地。"
    assert NS["clean_tier1_verse_text"]("号角吹响了。") == "号角吹响了。"
