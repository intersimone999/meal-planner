"""Tests for JSON import/export and round-trip fidelity."""

import json

from app.db import Base, engine
from app.models import Ingredient, MealPlanTemplate, Recipe, RecipeIngredient, TemplateSlot
from app.portability import export_all, import_all


def _seed(session):
    ing_names = ["pasta", "pesto", "parmigiano", "riso", "tonno"]
    for n in ing_names:
        session.add(Ingredient(name=n))
    r1 = Recipe(name="Pasta al pesto", type="primo", notes="Con parmigiano")
    r2 = Recipe(name="Insalata di riso", type="contorno", notes=None)
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
    # Multi-dish cell on Mon lunch: primo + contorno
    session.add(TemplateSlot(template_id=tpl.id, day=0, slot="lunch", recipe_id=r1.id))
    session.add(TemplateSlot(template_id=tpl.id, day=0, slot="lunch", recipe_id=r2.id))
    session.add(TemplateSlot(template_id=tpl.id, day=2, slot="dinner", recipe_id=r1.id))
    session.commit()


def test_export_shape_includes_type(session):
    _seed(session)
    data = export_all(session)
    assert set(data.keys()) == {"ingredients", "recipes", "templates"}
    pesto = next(r for r in data["recipes"] if r["name"] == "Pasta al pesto")
    assert pesto["type"] == "primo"
    riso = next(r for r in data["recipes"] if r["name"] == "Insalata di riso")
    assert riso["type"] == "contorno"
    # Template has 3 slot entries; 2 of them share (day=0, slot=lunch)
    slots = data["templates"][0]["slots"]
    assert len(slots) == 3
    mon_lunch = [s for s in slots if s["day"] == 0 and s["slot"] == "lunch"]
    assert len(mon_lunch) == 2


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
    assert summary["ingredients_created"] == 0
    assert summary["recipes_created"] == 0
    assert summary["recipes_skipped"] == 2
    assert summary["templates_created"] == 0
    assert summary["templates_skipped"] == 1


def test_recipe_without_valid_type_counted_invalid(session):
    data = {
        "ingredients": [],
        "recipes": [
            {"name": "MissingType"},                    # no type
            {"name": "BadType", "type": "bogus"},        # bad type
            {"name": "GoodOne", "type": "primo"},
        ],
        "templates": [],
    }
    summary = import_all(session, data)
    assert summary["recipes_created"] == 1
    assert summary["invalid_rows"] >= 2
    assert session.query(Recipe).filter_by(name="GoodOne").count() == 1
    assert session.query(Recipe).filter_by(name="MissingType").count() == 0
    assert session.query(Recipe).filter_by(name="BadType").count() == 0


def test_orphaned_slots_counted_not_fatal(session):
    session.add(Recipe(name="Existing", type="primo"))
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


def test_multi_dish_template_slot_round_trips(session):
    # Ensure a template with two recipes on the same (day, slot) round-trips.
    session.add(Recipe(name="A", type="primo"))
    session.add(Recipe(name="B", type="contorno"))
    session.commit()
    data = {
        "ingredients": [],
        "recipes": [],
        "templates": [{
            "name": "T",
            "slots": [
                {"day": 0, "slot": "lunch", "recipe": "A"},
                {"day": 0, "slot": "lunch", "recipe": "B"},  # same (day, slot), different recipe
                {"day": 0, "slot": "lunch", "recipe": "A"},  # duplicate → invalid_row
            ]
        }]
    }
    summary = import_all(session, data)
    assert summary["templates_created"] == 1
    assert summary["invalid_rows"] >= 1
    tpl = session.query(MealPlanTemplate).filter_by(name="T").one()
    assert len(tpl.slots) == 2


def test_invalid_rows_counted_not_fatal(session):
    data = {
        "ingredients": ["valid", "", 42, None],
        "recipes": [
            {"name": "OK", "type": "primo", "ingredients": ["ok-ing"]},
            {"name": ""},
            "not-a-dict",
            {"noname": True},
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
    assert summary["ingredients_created"] == 2
    assert summary["recipes_created"] == 1
    assert summary["templates_created"] == 1
    tpl = session.query(MealPlanTemplate).filter_by(name="T").one()
    assert len(tpl.slots) == 1
    assert summary["invalid_rows"] >= 5


def test_export_excludes_ephemeral_state(session):
    from app.models import PantryItem, PlannedMeal, ShoppingCheck

    _seed(session)
    r = session.query(Recipe).filter_by(name="Pasta al pesto").one()
    session.add(PlannedMeal(year=2026, week=36, day=0, slot="lunch", recipe_id=r.id))
    session.add(PantryItem(name="detersivo"))
    session.add(ShoppingCheck(year=2026, week=36, name="pasta"))
    session.commit()

    data = export_all(session)
    blob = json.dumps(data)
    assert "planned_meals" not in blob and "detersivo" not in blob
    assert "shopping_checks" not in blob and "pantry_items" not in blob
