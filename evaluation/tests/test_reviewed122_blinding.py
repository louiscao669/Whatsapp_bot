from collections import Counter

import pytest

from evaluation.scripts.pipeline.blind_reviewed122 import MAP, Names, read
from evaluation.scripts.pseudonyms.current import pseudonymize_english_source as legacy
from evaluation.scripts.pseudonyms.current.reconcile_qa_aliases import collect_text


def test_same_name_across_chinese_spellings_and_roles():
    names = Names(read(MAP), "zh", "t1_2chr26")
    assert names.apply("官长玛西亚、官员玛西雅") == "官长玛斯、官员玛斯"
    assert names.apply("书记耶列、书记耶利") == "书记珂顿、书记珂顿"
    for spelling in ("亚撒利亚", "亚撒利雅"):
        with pytest.raises(ValueError):
            names.check(spelling, "choice")


def test_genealogy_and_ordinary_uses_remain_distinct():
    table = read(MAP)
    judges = Names(table, "zh", "t1_judg17_18")
    samuel = Names(table, "zh", "t1_2sam21")
    assert len({judges.apply("约拿单"), judges.apply("革顺"), samuel.apply("约拿单")}) == 3
    assert judges.apply("但他不愿交出他的神像。") == "但他不愿交出他的神像。"
    assert judges.apply("但人") != "但人"


def test_unseen_option_only_names_and_foreign_script_raise():
    table = read(MAP)
    with pytest.raises(ValueError):
        Names(table, "en", "t1_acts23").check("Melchizedek.", "choice A")
    with pytest.raises(ValueError):
        Names(table, "zh", "t1_acts23").check("总督 Festus", "choice D")


def test_legacy_flat_and_lettered_choices_are_applied_and_scanned():
    rules = legacy.build_rules([{"canonical": "Paul", "pseudonym": "Tilir"}])
    for field, choices in (("choices", ["Paul"]), ("A", {"B": "Paul"})):
        source = {field: choices, "id": "Paul", "correct": "B", "verses": {"20:7": "Paul spoke."}}
        result = legacy.pseudonymize_qa_value(source, None, rules, Counter())
        assert result["id"] == "Paul" and result["correct"] == "B"
        for collect in (legacy.collect_strings, collect_text):
            strings = []
            collect(result, None, strings)
            assert strings == ["Tilir", "Tilir spoke."]
