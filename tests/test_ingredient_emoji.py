"""Tests for the ingredient → emoji + department auto-lookup."""

from app.ingredient_emoji import (
    DEPARTMENTS,
    DEPARTMENT_LABELS,
    department_for,
    emoji_for,
)


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
    assert emoji_for("melone") == "🍈"
    assert emoji_for("pomelo") == ""


def test_multi_word_qualifiers_win():
    assert emoji_for("pesce spada") == "🗡️"
    assert emoji_for("pesce fresco") == "🐟"


def test_unknown_returns_empty():
    assert emoji_for("qualcosa che non esiste") == ""
    assert emoji_for("") == ""
    assert emoji_for(None) == ""


def test_compound_names_pick_first_match():
    e = emoji_for("insalata di pomodori")
    assert e in ("🥬", "🍅")


# ---- department_for -----------------------------------------------------

def test_department_for_known_ingredients():
    # Fruit & veg
    assert department_for("mela") == "frutta_verdura"
    assert department_for("pomodoro") == "frutta_verdura"
    assert department_for("basilico") == "frutta_verdura"
    # Bread
    assert department_for("pane") == "panetteria"
    assert department_for("focaccia") == "panetteria"
    # Pasta / rice
    assert department_for("pasta") == "pasta_riso"
    assert department_for("riso") == "pasta_riso"
    assert department_for("farina") == "pasta_riso"
    # Dairy & eggs
    assert department_for("latte") == "latticini_uova"
    assert department_for("parmigiano") == "latticini_uova"
    assert department_for("uova") == "latticini_uova"
    # Salumi vs carne
    assert department_for("prosciutto") == "salumi"
    assert department_for("salame") == "salumi"
    assert department_for("pollo") == "carne"
    assert department_for("bistecca") == "carne"
    # Fish
    assert department_for("tonno") == "pesce"
    assert department_for("gamberetti") == "pesce"
    # Condimenti
    assert department_for("olio d'oliva") == "condimenti"
    assert department_for("sale") == "condimenti"
    assert department_for("pesto") == "condimenti"
    # Beverages
    assert department_for("vino") == "bevande"
    assert department_for("caffè") == "bevande"
    # Sweets
    assert department_for("cioccolato") == "dolci"
    assert department_for("miele") == "dolci"
    # Canned / legumes
    assert department_for("fagioli") == "scatolame"
    assert department_for("noci") == "scatolame"
    # Household
    assert department_for("detersivo piatti") == "pulizia"
    assert department_for("carta igienica") == "pulizia"


def test_department_for_unknown_returns_altro():
    assert department_for("boh") == "altro"
    assert department_for("") == "altro"
    assert department_for(None) == "altro"


def test_department_order_is_supermarket_flow():
    # First should be produce; last two should be pulizia + altro.
    assert DEPARTMENTS[0] == "frutta_verdura"
    assert DEPARTMENTS[-2:] == ["pulizia", "altro"]
    # Every department id has a label.
    for d in DEPARTMENTS:
        assert d in DEPARTMENT_LABELS and DEPARTMENT_LABELS[d]
