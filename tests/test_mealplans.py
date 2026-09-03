"""Tests for weekly plan templates: CRUD + multi-dish cells + apply-to-week
fill-empty (at the cell level) semantics."""

from app.models import MealPlanTemplate, PlannedMeal, Recipe, TemplateSlot


def _seed_recipes(session, names_and_types):
    ids = []
    for n, t in names_and_types:
        r = Recipe(name=n, type=t)
        session.add(r)
        session.flush()
        ids.append(r.id)
    session.commit()
    return ids


def test_multiple_dishes_per_slot_allowed(client, session):
    r_ids = _seed_recipes(session, [("Pasta", "primo"), ("Insalata", "contorno"), ("Frutta", "frutta")])
    for rid in r_ids:
        r = client.post("/planner/2026/36/0/lunch", data={"recipe_id": str(rid)})
        assert r.status_code == 200
    assert session.query(PlannedMeal).filter_by(year=2026, week=36, day=0, slot="lunch").count() == 3


def test_same_recipe_twice_in_cell_is_silent_noop(client, session):
    (rid,) = _seed_recipes(session, [("Pasta", "primo")])
    client.post("/planner/2026/36/0/lunch", data={"recipe_id": str(rid)})
    client.post("/planner/2026/36/0/lunch", data={"recipe_id": str(rid)})
    client.post("/planner/2026/36/0/lunch", data={"recipe_id": str(rid)})
    assert session.query(PlannedMeal).count() == 1


def test_template_apply_fills_only_fully_empty_cells(client, session):
    # Three recipes; template puts two dishes on Mon lunch (primo + contorno)
    # and one on Wed dinner. Pre-plant something on Mon lunch — the whole
    # cell (both template dishes) must be skipped; Wed dinner still gets filled.
    r_ids = _seed_recipes(session, [
        ("Pasta", "primo"),
        ("Insalata", "contorno"),
        ("Zuppa", "primo"),
    ])
    client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    tpl_id = session.query(MealPlanTemplate).one().id
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(r_ids[0])})
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(r_ids[1])})
    client.post(f"/mealplans/{tpl_id}/cell/2/dinner", data={"recipe_id": str(r_ids[2])})

    # Pre-plant Zuppa on Mon lunch — cell is non-empty
    client.post("/planner/2026/36/0/lunch", data={"recipe_id": str(r_ids[2])})

    r = client.post("/planner/2026/36/apply", data={"template_id": str(tpl_id)}, follow_redirects=False)
    assert r.status_code == 303

    mon_lunch = session.query(PlannedMeal).filter_by(year=2026, week=36, day=0, slot="lunch").all()
    wed_dinner = session.query(PlannedMeal).filter_by(year=2026, week=36, day=2, slot="dinner").all()

    # Mon lunch is untouched — still only Zuppa; neither Pasta nor Insalata added
    assert [m.recipe_id for m in mon_lunch] == [r_ids[2]]
    # Wed dinner was empty and now has the template's single Zuppa entry
    assert [m.recipe_id for m in wed_dinner] == [r_ids[2]]


def test_template_apply_is_idempotent(client, session):
    r_ids = _seed_recipes(session, [("Pasta", "primo"), ("Zuppa", "primo")])
    client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    tpl_id = session.query(MealPlanTemplate).one().id
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(r_ids[0])})
    client.post(f"/mealplans/{tpl_id}/cell/1/dinner", data={"recipe_id": str(r_ids[1])})

    for _ in range(3):
        r = client.post("/planner/2026/36/apply", data={"template_id": str(tpl_id)}, follow_redirects=False)
        assert r.status_code == 303

    # After 3 applies: still 2 rows (each cell was filled once, subsequent applies
    # find non-empty cells and skip them entirely).
    assert session.query(PlannedMeal).count() == 2


def test_template_apply_scoped_to_target_week(client, session):
    (rid,) = _seed_recipes(session, [("Pasta", "primo")])
    client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    tpl_id = session.query(MealPlanTemplate).one().id
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(rid)})
    client.post("/planner/2026/36/apply", data={"template_id": str(tpl_id)}, follow_redirects=False)
    all_weeks = {(m.year, m.week) for m in session.query(PlannedMeal).all()}
    assert all_weeks == {(2026, 36)}


def test_template_apply_unknown_template_404(client, session):
    r = client.post("/planner/2026/36/apply", data={"template_id": "9999"}, follow_redirects=False)
    assert r.status_code == 404


def test_recipe_delete_cascades_to_template_slot(client, session):
    (rid,) = _seed_recipes(session, [("Pasta", "primo")])
    client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    tpl_id = session.query(MealPlanTemplate).one().id
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(rid)})
    assert session.query(TemplateSlot).count() == 1

    r = client.post(f"/recipes/{rid}/delete", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert session.query(TemplateSlot).count() == 0
