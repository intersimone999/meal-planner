"""Tests for the ingredient → emoji auto-lookup (app/ingredient_emoji.py)."""

from app.ingredient_emoji import emoji_for


def test_common_single_words():
    assert emoji_for("mela") == "🍎"
    assert emoji_for("pomodoro") == "🍅"
    assert emoji_for("basilico") == "🌿"
    assert emoji_for("parmigiano") == "🧀"
    assert emoji_for("pasta") == "🍝"
    assert emoji_for("vino") == "🍷"


def test_case_and_accent_insensitive():
    assert emoji_for("MELA") == "🍎"
    assert emoji_for("Mela") == "🍎"
    assert emoji_for("Caffè") == "☕"
    assert emoji_for("CAFFE") == "☕"
    assert emoji_for("Ragù") == "🍝"


def test_plural_forms():
    assert emoji_for("mele") == "🍎"
    assert emoji_for("pomodori") == "🍅"
    assert emoji_for("uova") == "🥚"
    assert emoji_for("carote") == "🥕"


def test_whole_word_not_substring():
    # "pomelo" contains "pom" but not a whole "mela" or "pomodoro" word.
    # Bug hedge: "melone" is its own keyword, so "melone" returns 🍈, not 🍎.
    assert emoji_for("melone") == "🍈"
    # "pomelo" is unknown; must NOT match "mela" substring.
    assert emoji_for("pomelo") == ""


def test_multi_word_qualifiers_win():
    # "pesce spada" should hit its own emoji, not the generic pesce 🐟.
    assert emoji_for("pesce spada") == "🗡️"
    # But plain "pesce" still gets the generic 🐟.
    assert emoji_for("pesce fresco") == "🐟"


def test_unknown_returns_empty():
    assert emoji_for("qualcosa che non esiste") == ""
    assert emoji_for("") == ""
    assert emoji_for(None) == ""


def test_compound_names_pick_first_match():
    # An ingredient name with several matching words returns SOME emoji from
    # the table (whichever pattern hits first in insertion order). We don't
    # commit to which one — just that it's non-empty and comes from a known
    # entry.
    e = emoji_for("insalata di pomodori")
    assert e in ("🥬", "🍅")
