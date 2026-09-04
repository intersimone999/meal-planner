"""Tests for the unified shopping-list aggregator (app/aggregator.py).

Per SPEC.md §3.5, the shopping list is the union of (planned ingredients)
+ (pantry items), deduped case-insensitively, with per-(year, week, name)
check state via the ShoppingCheck table.
"""

from app.aggregator import shopping_list_for_week
from app.models import (
    Ingredient,
    PantryItem,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    ShoppingCheck,
)


def _add_recipe(session, name, ingredient_names, type="altro"):
    r = Recipe(name=name, type=type)
    session.add(r)
    session.flush()
    for n in ingredient_names:
        ing = session.query(Ingredient).filter_by(name=n).first()
        if not ing:
            ing = Ingredient(name=n)
            session.add(ing)
            session.flush()
        session.add(RecipeIngredient(recipe_id=r.id, ingredient_id=ing.id))
    session.flush()
    return r


def _plan(session, year, week, day, slot, recipe):
    session.add(
        PlannedMeal(year=year, week=week, day=day, slot=slot, recipe_id=recipe.id)
    )
    session.flush()


def test_empty_week_no_pantry_returns_empty(session):
    assert shopping_list_for_week(session, 2026, 36) == []


def test_only_pantry_items(session):
    session.add_all([PantryItem(name="caffè"), PantryItem(name="sale")])
    session.commit()
    names = [n for n, _ in shopping_list_for_week(session, 2026, 36)]
    assert names == ["caffè", "sale"]


def test_single_planned_meal_returns_its_ingredients(session):
    r = _add_recipe(session, "R", ["pomodoro", "basilico", "aglio"])
    _plan(session, 2026, 36, 0, "lunch", r)
    names = [n for n, _ in shopping_list_for_week(session, 2026, 36)]
    assert names == ["aglio", "basilico", "pomodoro"]


def test_planned_and_pantry_union_and_dedup(session):
    r = _add_recipe(session, "R", ["pomodoro", "olio"])
    _plan(session, 2026, 36, 0, "lunch", r)
    session.add_all([PantryItem(name="olio"), PantryItem(name="caffè")])
    session.commit()
    names = [n for n, _ in shopping_list_for_week(session, 2026, 36)]
    # olio appears in both — deduped case-insensitively
    assert names == ["caffè", "olio", "pomodoro"]


def test_dedup_is_case_insensitive(session):
    r = _add_recipe(session, "R", ["Pomodoro"])
    _plan(session, 2026, 36, 0, "lunch", r)
    session.add(PantryItem(name="pomodoro"))
    session.commit()
    names = [n for n, _ in shopping_list_for_week(session, 2026, 36)]
    assert len(names) == 1
    # Preserves the first-seen casing (from the derived path in this fixture)
    assert names[0] in ("Pomodoro", "pomodoro")


def test_different_weeks_isolated(session):
    r = _add_recipe(session, "R", ["farina"])
    _plan(session, 2026, 36, 0, "lunch", r)
    assert [n for n, _ in shopping_list_for_week(session, 2026, 36)] == ["farina"]
    assert shopping_list_for_week(session, 2026, 37) == []


def test_pantry_present_across_weeks(session):
    session.add(PantryItem(name="caffè"))
    session.commit()
    # Pantry is week-independent — shows on every week
    for w in (35, 36, 37):
        assert [n for n, _ in shopping_list_for_week(session, 2026, w)] == ["caffè"]


def test_check_state_is_per_week_and_name(session):
    session.add(PantryItem(name="caffè"))
    session.commit()
    session.add(ShoppingCheck(year=2026, week=36, name="caffè"))
    session.commit()
    assert shopping_list_for_week(session, 2026, 36) == [("caffè", True)]
    # Next week not affected
    assert shopping_list_for_week(session, 2026, 37) == [("caffè", False)]


def test_check_case_insensitive_lookup(session):
    session.add(PantryItem(name="Caffè"))
    session.commit()
    # A ShoppingCheck stored with different casing should still match
    session.add(ShoppingCheck(year=2026, week=36, name="CAFFÈ"))
    session.commit()
    assert shopping_list_for_week(session, 2026, 36) == [("Caffè", True)]
