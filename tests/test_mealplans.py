"""Tests for weekly plan templates: CRUD + apply-to-week fill-empty semantics."""

from app.models import MealPlanTemplate, PlannedMeal, Recipe, TemplateSlot


def _seed_recipes(session, names):
    ids = []
    for n in names:
        r = Recipe(name=n)
        session.add(r)
        session.flush()
        ids.append(r.id)
    session.commit()
    return ids


def test_template_apply_fills_only_empty_slots(client, session):
    r_ids = _seed_recipes(session, ["Pasta", "Zuppa", "Risotto"])

    # Build template: Mon lunch=Pasta, Wed dinner=Zuppa, Fri lunch=Risotto
    r = client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    assert r.status_code == 303
    tpl_id = session.query(MealPlanTemplate).one().id
    for day, slot, rid in [
        (0, "lunch", r_ids[0]),
        (2, "dinner", r_ids[1]),
        (4, "lunch", r_ids[2]),
    ]:
        client.post(f"/mealplans/{tpl_id}/cell/{day}/{slot}", data={"recipe_id": str(rid)})

    # Pre-plant a meal on Mon lunch (Zuppa) — must NOT be overwritten
    client.post("/planner/2026/36/0/lunch", data={"recipe_id": str(r_ids[1])})

    # Apply template
    r = client.post(
        "/planner/2026/36/apply",
        data={"template_id": str(tpl_id)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    meals = {(m.day, m.slot): m.recipe_id for m in session.query(PlannedMeal).all()}
    assert meals[(0, "lunch")] == r_ids[1]   # preserved (Zuppa, not Pasta)
    assert meals[(2, "dinner")] == r_ids[1]  # filled from template
    assert meals[(4, "lunch")] == r_ids[2]   # filled from template
    assert len(meals) == 3                    # nothing else added


def test_template_apply_is_idempotent(client, session):
    r_ids = _seed_recipes(session, ["Pasta", "Zuppa"])
    client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    tpl_id = session.query(MealPlanTemplate).one().id
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(r_ids[0])})
    client.post(f"/mealplans/{tpl_id}/cell/1/dinner", data={"recipe_id": str(r_ids[1])})

    for _ in range(3):
        r = client.post(
            "/planner/2026/36/apply",
            data={"template_id": str(tpl_id)},
            follow_redirects=False,
        )
        assert r.status_code == 303

    # Still exactly 2 rows — no duplicates
    assert session.query(PlannedMeal).count() == 2


def test_template_apply_does_not_touch_other_weeks(client, session):
    r_ids = _seed_recipes(session, ["Pasta"])
    client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    tpl_id = session.query(MealPlanTemplate).one().id
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(r_ids[0])})

    client.post(
        "/planner/2026/36/apply",
        data={"template_id": str(tpl_id)},
        follow_redirects=False,
    )

    all_weeks = {(m.year, m.week) for m in session.query(PlannedMeal).all()}
    assert all_weeks == {(2026, 36)}


def test_template_apply_unknown_template_404(client, session):
    r = client.post(
        "/planner/2026/36/apply",
        data={"template_id": "9999"},
        follow_redirects=False,
    )
    assert r.status_code == 404


def test_recipe_delete_cascades_to_template_slot(client, session):
    r_ids = _seed_recipes(session, ["Pasta"])
    client.post("/mealplans", data={"name": "T"}, follow_redirects=False)
    tpl_id = session.query(MealPlanTemplate).one().id
    client.post(f"/mealplans/{tpl_id}/cell/0/lunch", data={"recipe_id": str(r_ids[0])})
    assert session.query(TemplateSlot).count() == 1

    r = client.post(f"/recipes/{r_ids[0]}/delete", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert session.query(TemplateSlot).count() == 0
