"""Tests for JSON import/export and round-trip fidelity."""

import json

from app.db import Base, engine
from app.models import Ingredient, MealPlanTemplate, Recipe, RecipeIngredient, TemplateSlot
from app.portability import export_all, import_all


def _seed(session):
    ing_names = ["pasta", "pesto", "parmigiano", "riso", "tonno"]
    for n in ing_names:
        session.add(Ingredient(name=n))
    r1 = Recipe(name="Pasta al pesto", notes="Con parmigiano")
    r2 = Recipe(name="Insalata di riso", notes=None)
    session.add_all([r1, r2])
    session.flush()
    for name in ["pasta", "pesto", "parmigiano"]:
        ing = session.query(Ingredient).filter_by(name=name).one()
        session.add(RecipeIngredient(recipe_id=r1.id, ingredient_id=ing.id))
    for name in ["riso", "tonno"]:
        ing = session.query(Ingredient).filter_by(name=name).one()
        session.add(RecipeIngredient(recipe_id=r2.id, ingredient_id=ing.id))
    tpl = MealPlanTemplate(name="Standard")
    session.add(tpl)
    session.flush()
    session.add(TemplateSlot(template_id=tpl.id, day=0, slot="lunch", recipe_id=r1.id))
    session.add(TemplateSlot(template_id=tpl.id, day=2, slot="dinner", recipe_id=r2.id))
    session.commit()


def test_export_shape(session):
    _seed(session)
    data = export_all(session)
    assert set(data.keys()) == {"ingredients", "recipes", "templates"}
    assert data["ingredients"] == sorted(["pasta", "pesto", "parmigiano", "riso", "tonno"])
    names = sorted(r["name"] for r in data["recipes"])
    assert names == ["Insalata di riso", "Pasta al pesto"]
    pesto = next(r for r in data["recipes"] if r["name"] == "Pasta al pesto")
    assert pesto["notes"] == "Con parmigiano"
    assert pesto["ingredients"] == sorted(["pasta", "pesto", "parmigiano"])
    assert len(data["templates"]) == 1
    slots = data["templates"][0]["slots"]
    assert len(slots) == 2
    # Templates reference recipes BY NAME (not id)
    assert {s["recipe"] for s in slots} == {"Pasta al pesto", "Insalata di riso"}


def test_round_trip_via_wipe_and_import(session):
    _seed(session)
    exported = export_all(session)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    summary = import_all(session, exported)
    assert summary["ingredients_created"] == 5
    assert summary["recipes_created"] == 2
    assert summary["templates_created"] == 1
    assert summary["orphaned_slots"] == 0

    re_exported = export_all(session)
    # Order-insensitive equality
    assert sorted(re_exported["ingredients"]) == sorted(exported["ingredients"])
    assert sorted(re_exported["recipes"], key=lambda r: r["name"]) == sorted(
        exported["recipes"], key=lambda r: r["name"]
    )
    assert sorted(re_exported["templates"], key=lambda t: t["name"]) == sorted(
        exported["templates"], key=lambda t: t["name"]
    )


def test_reimport_skips_existing(session):
    _seed(session)
    data = export_all(session)
    summary = import_all(session, data)
    # Everything already exists → 0 created, N skipped
    assert summary["ingredients_created"] == 0  # dedup by name
    assert summary["recipes_created"] == 0
    assert summary["recipes_skipped"] == 2
    assert summary["templates_created"] == 0
    assert summary["templates_skipped"] == 1


def test_orphaned_slots_counted_not_fatal(session):
    # Recipe 'Ghost' is not in the DB — the template slot referencing it must
    # be counted as orphaned; the template itself is still created; the other
    # slot is imported normally.
    session.add(Recipe(name="Existing"))
    session.commit()
    data = {
        "ingredients": [],
        "recipes": [],
        "templates": [
            {
                "name": "T",
                "slots": [
                    {"day": 0, "slot": "lunch", "recipe": "Ghost"},
                    {"day": 3, "slot": "dinner", "recipe": "Existing"},
                ],
            }
        ],
    }
    summary = import_all(session, data)
    assert summary["templates_created"] == 1
    assert summary["orphaned_slots"] == 1

    tpl = session.query(MealPlanTemplate).filter_by(name="T").one()
    assert len(tpl.slots) == 1
    assert tpl.slots[0].day == 3


def test_invalid_rows_counted_not_fatal(session):
    data = {
        "ingredients": ["valid", "", 42, None],  # 3 invalid, 1 valid
        "recipes": [
            {"name": "OK", "ingredients": ["ok-ing"]},
            {"name": ""},          # invalid: empty name
            "not-a-dict",           # invalid: not an object
            {"noname": True},       # invalid: missing name
        ],
        "templates": [
            {"name": "T", "slots": [
                {"day": 99, "slot": "lunch", "recipe": "OK"},   # bad day
                {"day": 0, "slot": "brunch", "recipe": "OK"},   # bad slot
                {"day": 0, "slot": "lunch", "recipe": ""},      # empty recipe
                {"day": 1, "slot": "dinner", "recipe": "OK"},   # valid
            ]},
        ],
    }
    summary = import_all(session, data)
    assert summary["ingredients_created"] == 2  # "valid" + auto-created "ok-ing" from recipe
    assert summary["recipes_created"] == 1
    assert summary["templates_created"] == 1
    # Exactly one valid slot survived
    tpl = session.query(MealPlanTemplate).filter_by(name="T").one()
    assert len(tpl.slots) == 1
    assert summary["invalid_rows"] >= 5  # multiple bad inputs above


def test_export_excludes_ephemeral_state(session):
    from app.models import ManualShoppingItem, PlannedMeal, ShoppingCheck

    _seed(session)
    r = session.query(Recipe).filter_by(name="Pasta al pesto").one()
    ing = session.query(Ingredient).filter_by(name="pasta").one()
    session.add(PlannedMeal(year=2026, week=36, day=0, slot="lunch", recipe_id=r.id))
    session.add(ManualShoppingItem(name="detersivo"))
    session.add(ShoppingCheck(year=2026, week=36, ingredient_id=ing.id))
    session.commit()

    data = export_all(session)
    # These entities MUST NOT leak into the export
    blob = json.dumps(data)
    assert "planned_meals" not in blob and "detersivo" not in blob
    assert "shopping_checks" not in blob
