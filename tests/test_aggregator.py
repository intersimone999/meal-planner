"""Tests for the shopping-list aggregator (app/aggregator.py).

The aggregator is the load-bearing piece of the shopping-list feature —
per SPEC.md §3.5, its behaviour under dedup and per-week check isolation
is the entire acceptance criterion for the feature.
"""

from app.aggregator import derived_for_week
from app.models import (
    Ingredient,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    ShoppingCheck,
)


def _add_recipe(session, name, ingredient_names):
    r = Recipe(name=name)
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


def test_empty_week_returns_empty(session):
    assert derived_for_week(session, 2026, 36) == []


def test_single_meal_returns_its_ingredients_sorted(session):
    r = _add_recipe(session, "R1", ["pomodoro", "basilico", "aglio"])
    _plan(session, 2026, 36, 0, "lunch", r)

    result = derived_for_week(session, 2026, 36)
    names = [i.name for i, checked in result]
    assert names == ["aglio", "basilico", "pomodoro"]
    assert all(checked is False for _, checked in result)


def test_two_meals_share_ingredient_is_deduped(session):
    r1 = _add_recipe(session, "Pasta", ["pasta", "pomodoro", "parmigiano"])
    r2 = _add_recipe(session, "Bruschetta", ["pane", "pomodoro", "aglio"])
    _plan(session, 2026, 36, 0, "lunch", r1)
    _plan(session, 2026, 36, 2, "dinner", r2)

    names = [i.name for i, _ in derived_for_week(session, 2026, 36)]
    # union of both, deduped, sorted; pomodoro appears exactly once
    assert names == ["aglio", "pane", "parmigiano", "pasta", "pomodoro"]
    assert names.count("pomodoro") == 1


def test_different_weeks_are_isolated(session):
    r = _add_recipe(session, "R", ["farina"])
    _plan(session, 2026, 36, 0, "lunch", r)

    assert [i.name for i, _ in derived_for_week(session, 2026, 36)] == ["farina"]
    assert derived_for_week(session, 2026, 37) == []
    assert derived_for_week(session, 2025, 36) == []


def test_check_state_is_per_week(session):
    r = _add_recipe(session, "R", ["riso"])
    _plan(session, 2026, 36, 0, "lunch", r)
    _plan(session, 2026, 37, 0, "lunch", r)

    riso_id = session.query(Ingredient).filter_by(name="riso").one().id
    # Check on week 36
    session.add(ShoppingCheck(year=2026, week=36, ingredient_id=riso_id))
    session.commit()

    w36 = derived_for_week(session, 2026, 36)
    w37 = derived_for_week(session, 2026, 37)

    assert [(i.name, c) for i, c in w36] == [("riso", True)]
    # Week 37 must be UNAFFECTED
    assert [(i.name, c) for i, c in w37] == [("riso", False)]


def test_unchecked_items_come_before_checked(session):
    r = _add_recipe(session, "R", ["banana", "avocado", "cetriolo"])
    _plan(session, 2026, 36, 0, "lunch", r)

    banana_id = session.query(Ingredient).filter_by(name="banana").one().id
    session.add(ShoppingCheck(year=2026, week=36, ingredient_id=banana_id))
    session.commit()

    result = derived_for_week(session, 2026, 36)
    # unchecked first (alpha), then checked (alpha)
    assert [(i.name, c) for i, c in result] == [
        ("avocado", False),
        ("cetriolo", False),
        ("banana", True),
    ]
