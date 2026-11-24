from unittest.mock import patch

from evaluation.scripts.pipeline import build_sol_wbw_names as release
from evaluation.scripts.scoring.current import translation_quality as quality


def test_saved_google_tokens_and_normal_generator_reproduce_the_pilot(tmp_path, monkeypatch):
    from deep_translator import GoogleTranslator

    for variable in ("WBW_CACHE_DISABLED", "WBW_KEEP_SPACES", "WBW_NAME_OVERRIDES_DISABLED",
                     "WBW_NAME_OVERRIDES_PATH"):
        monkeypatch.delenv(variable, raising=False)
    cache = tmp_path / "google.json"
    cache.write_bytes((release.DATA / "perturbations/.wbw_cache_en_zh-CN.json").read_bytes())
    monkeypatch.setenv("WBW_CACHE_PATH", str(cache))
    overlay, report = release.build()
    assert overlay == release.read(release.OUTPUT)
    assert report == release.REPORT.read_text()
    config = release.read(release.DATA / "perturbations/sol_wbw_names.json")
    with patch.object(GoogleTranslator, "translate", side_effect=AssertionError("Unexpected network lookup")) as live:
        for pid, filename in config["source_files"].items():
            source = (release.DATA / "passages/tier1_bsb" / filename).read_text()
            [result] = quality.translate_with_method(source, "google_word_by_word")
            assert result.strip() == overlay["passages"][pid]["text"].strip()
        live.assert_not_called()


def test_named_spans_keep_punctuation_and_distinguish_lord_and_lord_name():
    pairs = [("Lord", "主"), ("LORD’s", "领主的"), ("Ebed,\n\n31", "耶比底,\n\n31"), ("said", "说")]
    protected, _ = quality.protect_wbw_names(pairs, {"LORD": "耶和华", "Ebed": "以别"})
    assert quality.wbw_join(protected) == "主耶和华的以别,\n\n31 说"


def test_translator_holds_unknown_and_mismatched_names_before_google(monkeypatch):
    from deep_translator import GoogleTranslator
    import pytest

    for variable in ("WBW_NAME_OVERRIDES_DISABLED", "WBW_NAME_OVERRIDES_PATH"):
        monkeypatch.delenv(variable, raising=False)
    with patch.object(GoogleTranslator, "translate") as live:
        with pytest.raises(quality.TranslationQualityError, match="Zimri .*verse 30"):
            quality.translate_with_method("30 Zimri spoke.", "google_word_by_word")
        with pytest.raises(quality.TranslationQualityError, match="verse 30: Zebul → 西布勒"):
            quality.translate_with_method("30 Zebul spoke.\n\n31 Ebed spoke.", "google_word_by_word",
                                          wbw_clean_texts="30 以别说话。\n\n31 西布勒说话。")
        with pytest.raises(quality.TranslationQualityError, match="same verse markers"):
            quality.google_word_by_word("30 Zebul spoke.", wbw_clean_texts="31 西布勒说话。")
        with pytest.raises(quality.TranslationQualityError, match="one clean passage"):
            quality.google_word_by_word(["Zebul spoke.", "Ebed spoke."], wbw_clean_texts=["西布勒说话。"])
        live.assert_not_called()


def test_main_wbw_stage_rechecks_stale_output_and_empty_glossary(tmp_path, monkeypatch):
    from evaluation import main as pipeline
    from deep_translator import GoogleTranslator
    from types import SimpleNamespace
    import json
    import pytest

    for variable in ("WBW_NAME_OVERRIDES_DISABLED", "WBW_NAME_OVERRIDES_PATH", "WBW_CACHE_DISABLED", "WBW_KEEP_SPACES"):
        monkeypatch.delenv(variable, raising=False)
    infile = tmp_path / "judges.txt"
    source = (release.DATA / "passages/tier1_bsb/judg_9_1-57.txt").read_text()
    verse = next(v for v in source.split("\n\n") if v.startswith("30 "))
    infile.write_text(verse)
    args = SimpleNamespace(force=False, force_passage_translate=False, pseudonym_map=None, pre_blinded=True,
                           passage_file=infile, output_dir=tmp_path, mapping_json=None, target_language="zh-CN",
                           source_language="en", helsinki_model=None, mbart_model=None, nllb_distilled_model=None,
                           nllb_model=None, nllb_dropout_rate=0., passage_translation_model=None,
                           temperature=None, seed=None)
    method = "google_word_by_word"
    paths = pipeline.method_output_paths(args, method)
    receipt, text = paths["translated_passage_json"], paths["translated_passage"]
    text.parent.mkdir()
    old = "30 西布听见耶比底的儿子迦勒说话。"
    text.write_text(old)
    receipt.write_text(json.dumps({"method": method, "source_texts": [verse], "translations": [old]}))
    cache = tmp_path / "cache.json"
    cache.write_bytes((release.DATA / "perturbations/.wbw_cache_en_zh-CN.json").read_bytes())
    monkeypatch.setenv("WBW_CACHE_PATH", str(cache))
    # Reviewed names precede Google lookups even when a cropped verse has new punctuation.
    with patch.object(GoogleTranslator, "translate", return_value="愤怒。"):
        assert pipeline.run_passage_translate_stage(args, method, receipt, text, None)
    output = text.read_text()
    assert "西布勒" in output and "以别" in output and "耶比底" not in output
    saved = json.loads(receipt.read_text())
    review, = saved["name_review"]["passages"]
    assert (review["reference"], review["verses"], review["checked_occurrences"]) == ("Sol", ["9:30"], 3)
    with patch.object(pipeline, "translate_with_method", side_effect=AssertionError("unexpected regeneration")):
        assert not pipeline.run_passage_translate_stage(args, method, receipt, text, None)
        args.wbw_clean_passage = tmp_path / "clean.txt"
        args.wbw_clean_passage.write_text("30 城长西布听见以别的儿子迦勒说话。")
        with pytest.raises(quality.TranslationQualityError, match="Zebul → 西布勒"):
            pipeline.run_passage_translate_stage(args, method, receipt, text, None)
    assert text.read_text() == output
    with pytest.raises(quality.TranslationQualityError, match="conflicting Sol"):
        quality.google_word_by_word(verse, glossary={"Zebul": "西布"})


def test_custom_glossary_extends_review_and_preserves_placeholders():
    names, audit = quality.wbw_name_review("1 Zimri met __PERSON_A__ and Ebed.", {"Zimri": "心利"},
                                           "1 心利见了人物甲和以别。")
    assert audit[0]["checked_occurrences"] == 2 and audit[0]["reference"] == "supplied"
    assert names["Zimri"] == "心利" and names["Ebed"] == "以别"
