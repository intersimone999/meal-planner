"""End-to-end tests for recipe + ingredient CRUD and cascade behaviour."""

import sqlite3

from app.db import DB_PATH
from app.models import (
    Ingredient,
    MealPlanTemplate,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    TemplateSlot,
)


def _create_recipe(client, name, notes=""):
    r = client.post("/recipes", data={"name": name, "notes": notes}, follow_redirects=False)
    assert r.status_code == 303
    # /recipes/{id}/edit → extract id
    return int(r.headers["location"].rsplit("/", 2)[-2])


def _add_ingredient(client, recipe_id, name):
    r = client.post(
        f"/recipes/{recipe_id}/ingredients",
        data={"name": name},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200
    return r


def test_recipe_create_and_delete_via_client(client, session):
    rid = _create_recipe(client, "Pasta al pesto")
    assert session.query(Recipe).filter_by(name="Pasta al pesto").one().id == rid

    # duplicate name blocked
    r = client.post("/recipes", data={"name": "Pasta al pesto", "notes": ""})
    assert r.status_code == 400

    # delete
    r = client.post(f"/recipes/{rid}/delete", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert session.query(Recipe).filter_by(id=rid).first() is None


def test_ingredient_case_insensitive_dedup(client, session):
    rid = _create_recipe(client, "R")
    _add_ingredient(client, rid, "pomodoro")
    _add_ingredient(client, rid, "POMODORO")
    _add_ingredient(client, rid, "  Pomodoro  ".strip())
    assert session.query(Ingredient).count() == 1
    # And only one link on the recipe
    assert session.query(RecipeIngredient).filter_by(recipe_id=rid).count() == 1


def test_delete_recipe_cascades_to_all_referencing_rows(client, session):
    rid = _create_recipe(client, "Lasagna")
    _add_ingredient(client, rid, "pasta")
    _add_ingredient(client, rid, "ragù")

    # Plant a planned meal
    session.add(
        PlannedMeal(year=2026, week=36, day=0, slot="lunch", recipe_id=rid)
    )
    # Plant a template slot
    t = MealPlanTemplate(name="T")
    session.add(t)
    session.flush()
    session.add(TemplateSlot(template_id=t.id, day=0, slot="lunch", recipe_id=rid))
    session.commit()

    # Sanity
    assert session.query(RecipeIngredient).filter_by(recipe_id=rid).count() == 2
    assert session.query(PlannedMeal).filter_by(recipe_id=rid).count() == 1
    assert session.query(TemplateSlot).filter_by(recipe_id=rid).count() == 1

    # Delete
    r = client.post(f"/recipes/{rid}/delete", headers={"HX-Request": "true"})
    assert r.status_code == 200

    # ORM cascades: RecipeIngredient, PlannedMeal, TemplateSlot rows all gone;
    # ingredients themselves preserved.
    assert session.query(RecipeIngredient).filter_by(recipe_id=rid).count() == 0
    assert session.query(PlannedMeal).filter_by(recipe_id=rid).count() == 0
    assert session.query(TemplateSlot).filter_by(recipe_id=rid).count() == 0
    assert session.query(Ingredient).filter_by(name="pasta").count() == 1


def test_delete_ingredient_in_use_is_blocked(client, session):
    rid = _create_recipe(client, "R")
    _add_ingredient(client, rid, "sale")
    salt_id = session.query(Ingredient).filter_by(name="sale").one().id

    r = client.post(f"/ingredients/{salt_id}/delete", follow_redirects=False)
    assert r.status_code == 400
    assert "usato" in r.text

    # Remove from recipe, then delete succeeds
    r = client.delete(f"/recipes/{rid}/ingredients/{salt_id}")
    assert r.status_code == 200
    r = client.post(f"/ingredients/{salt_id}/delete", follow_redirects=False)
    assert r.status_code == 303


def test_rename_ingredient_reflects_everywhere(client, session):
    rid = _create_recipe(client, "R")
    _add_ingredient(client, rid, "ragù")
    ing_id = session.query(Ingredient).filter_by(name="ragù").one().id

    r = client.post(
        f"/ingredients/{ing_id}/rename",
        data={"name": "Ragù di manzo"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.get(f"/recipes/{rid}/edit")
    assert "Ragù di manzo" in r.text
    assert "ragù" not in r.text or "Ragù di manzo" in r.text  # old spelling gone from chip


def test_ingredient_merge_reassigns_and_deletes_source(client, session):
    r1 = _create_recipe(client, "R1")
    r2 = _create_recipe(client, "R2")
    _add_ingredient(client, r1, "pomodoro")
    _add_ingredient(client, r2, "Pomodoro rosso")

    src = session.query(Ingredient).filter_by(name="Pomodoro rosso").one()
    tgt = session.query(Ingredient).filter_by(name="pomodoro").one()

    r = client.post(
        f"/ingredients/{src.id}/merge",
        data={"target_id": str(tgt.id)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # source gone, target still there
    assert session.query(Ingredient).filter_by(id=src.id).first() is None
    assert session.query(Ingredient).filter_by(id=tgt.id).first() is not None

    # Both R1 and R2 now reference target
    r1_links = session.query(RecipeIngredient).filter_by(recipe_id=r1).all()
    r2_links = session.query(RecipeIngredient).filter_by(recipe_id=r2).all()
    assert [l.ingredient_id for l in r1_links] == [tgt.id]
    assert [l.ingredient_id for l in r2_links] == [tgt.id]


def test_ingredient_merge_handles_recipe_that_had_both(client, session):
    rid = _create_recipe(client, "R")
    _add_ingredient(client, rid, "pomodoro")
    _add_ingredient(client, rid, "Pomodoro rosso")
    # Manually verify the recipe has 2 distinct ingredient links (via UNIQUE)
    assert session.query(RecipeIngredient).filter_by(recipe_id=rid).count() == 2

    src = session.query(Ingredient).filter_by(name="Pomodoro rosso").one()
    tgt = session.query(Ingredient).filter_by(name="pomodoro").one()

    # Merge — must NOT violate UNIQUE(recipe_id, ingredient_id).
    r = client.post(
        f"/ingredients/{src.id}/merge",
        data={"target_id": str(tgt.id)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Recipe now has exactly one link to the target
    links = session.query(RecipeIngredient).filter_by(recipe_id=rid).all()
    assert len(links) == 1 and links[0].ingredient_id == tgt.id


def test_ingredient_merge_into_self_rejected(client, session):
    rid = _create_recipe(client, "R")
    _add_ingredient(client, rid, "sale")
    sid = session.query(Ingredient).filter_by(name="sale").one().id

    r = client.post(
        f"/ingredients/{sid}/merge",
        data={"target_id": str(sid)},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "se stesso" in r.text
