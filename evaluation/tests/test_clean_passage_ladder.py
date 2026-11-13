from evaluation.scripts.pipeline.build_clean_passage_ladder import edit_span, omission_verses, replay


def test_omitting_first_clauses_keeps_remaining_words_under_the_source_verse():
    clean = "24 起初，仍在城里。\n\n7 次日，仍有马。\n\n2 众人离开。\n"
    verses = {"6:24": "起初，仍在城里。", "7:1": "次日，仍有马。", "7:2": "众人离开。"}
    edits = [edit_span(clean.index(s), s, "") for s in ("24 起初，", "7 次日，", "2 众人离开。")]
    assert replay(clean, edits) == "仍在城里。\n\n仍有马。\n\n\n"
    assert omission_verses(clean, verses, edits) == {"6:24": "仍在城里。", "7:1": "仍有马。"}
