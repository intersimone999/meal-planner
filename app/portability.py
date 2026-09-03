"""Pure import/export logic for JSON portability.

Kept separate from the route module so it's trivially unit-testable.
Format per SPEC.md §3.6. Excludes the weekly plan, manual shopping
items, and derived-ingredient checkboxes — those are ephemeral.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.i18n import RECIPE_TYPES, SLOTS
from app.models import (
    Ingredient,
    MealPlanTemplate,
    Recipe,
    RecipeIngredient,
    TemplateSlot,
)


def export_all(session: Session) -> dict[str, Any]:
    ingredients = sorted(
        i.name
        for i in session.scalars(select(Ingredient)).all()
    )
    recipes_data = []
    recipes = session.scalars(
        select(Recipe)
        .options(
            selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient)
        )
        .order_by(Recipe.name)
    ).all()
    for r in recipes:
        recipes_data.append(
            {
                "name": r.name,
                "type": r.type,
                "notes": r.notes,
                "ingredients": sorted(link.ingredient.name for link in r.ingredients),
            }
        )
    templates_data = []
    tpls = session.scalars(
        select(MealPlanTemplate)
        .options(selectinload(MealPlanTemplate.slots).selectinload(TemplateSlot.recipe))
        .order_by(MealPlanTemplate.name)
    ).all()
    for t in tpls:
        # Sort by (day, slot, recipe) so multi-dish cells serialize deterministically.
        slots = sorted(
            (
                {"day": s.day, "slot": s.slot, "recipe": s.recipe.name}
                for s in t.slots
            ),
            key=lambda s: (s["day"], s["slot"], s["recipe"]),
        )
        templates_data.append({"name": t.name, "slots": slots})
    return {
        "ingredients": ingredients,
        "recipes": recipes_data,
        "templates": templates_data,
    }


def import_all(session: Session, data: dict[str, Any]) -> dict[str, int]:
    """Upsert-by-name importer. Returns a summary dict.

    - Ingredients: create-if-missing.
    - Recipes: skip if same name already exists (never overwrite).
    - Templates: skip if same name already exists.
    - Template slots referencing a recipe not present in the DB after import
      are counted in `orphaned_slots` and their slot row is not created.
    - Invalid rows (missing name, out-of-range day, unknown slot) are counted
      in `invalid_rows`.
    """
    summary = {
        "ingredients_created": 0,
        "recipes_created": 0,
        "recipes_skipped": 0,
        "templates_created": 0,
        "templates_skipped": 0,
        "orphaned_slots": 0,
        "invalid_rows": 0,
    }

    def _get_or_create_ingredient(name: str) -> Ingredient:
        ing = session.scalar(select(Ingredient).where(Ingredient.name == name))
        if ing:
            return ing
        ing = Ingredient(name=name)
        session.add(ing)
        session.flush()
        summary["ingredients_created"] += 1
        return ing

    # 1. Bare ingredients list
    for raw in data.get("ingredients", []) or []:
        if not isinstance(raw, str):
            summary["invalid_rows"] += 1
            continue
        name = raw.strip()
        if not name:
            summary["invalid_rows"] += 1
            continue
        _get_or_create_ingredient(name)

    # 2. Recipes (may reference ingredients not in the bare list — auto-create)
    for raw in data.get("recipes", []) or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            summary["invalid_rows"] += 1
            continue
        name = raw["name"].strip()
        if not name:
            summary["invalid_rows"] += 1
            continue
        type_val = raw.get("type")
        if not isinstance(type_val, str) or type_val not in RECIPE_TYPES:
            # Required per SPEC.md §3.1 — reject the recipe entirely.
            summary["invalid_rows"] += 1
            continue
        if session.scalar(select(Recipe).where(Recipe.name == name)):
            summary["recipes_skipped"] += 1
            continue
        notes_val = raw.get("notes")
        notes = notes_val.strip() if isinstance(notes_val, str) and notes_val.strip() else None
        recipe = Recipe(name=name, type=type_val, notes=notes)
        session.add(recipe)
        session.flush()
        seen_ids: set[int] = set()
        for ing_raw in raw.get("ingredients", []) or []:
            if not isinstance(ing_raw, str):
                summary["invalid_rows"] += 1
                continue
            ing_name = ing_raw.strip()
            if not ing_name:
                summary["invalid_rows"] += 1
                continue
            ing = _get_or_create_ingredient(ing_name)
            if ing.id in seen_ids:
                continue
            seen_ids.add(ing.id)
            session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_id=ing.id))
        summary["recipes_created"] += 1

    session.flush()

    # 3. Templates
    for raw in data.get("templates", []) or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            summary["invalid_rows"] += 1
            continue
        name = raw["name"].strip()
        if not name:
            summary["invalid_rows"] += 1
            continue
        if session.scalar(select(MealPlanTemplate).where(MealPlanTemplate.name == name)):
            summary["templates_skipped"] += 1
            continue
        tpl = MealPlanTemplate(name=name)
        session.add(tpl)
        session.flush()
        seen_cells: set[tuple[int, str, int]] = set()
        for s in raw.get("slots", []) or []:
            if not isinstance(s, dict):
                summary["invalid_rows"] += 1
                continue
            day = s.get("day")
            slot = s.get("slot")
            recipe_name = s.get("recipe")
            if not (isinstance(day, int) and 0 <= day <= 6):
                summary["invalid_rows"] += 1
                continue
            if slot not in SLOTS:
                summary["invalid_rows"] += 1
                continue
            if not isinstance(recipe_name, str) or not recipe_name.strip():
                summary["invalid_rows"] += 1
                continue
            recipe = session.scalar(select(Recipe).where(Recipe.name == recipe_name.strip()))
            if not recipe:
                summary["orphaned_slots"] += 1
                continue
            # Multi-dish cells allowed; only same recipe repeated in same cell blocked.
            cell_key = (day, slot, recipe.id)
            if cell_key in seen_cells:
                summary["invalid_rows"] += 1
                continue
            seen_cells.add(cell_key)
            session.add(
                TemplateSlot(
                    template_id=tpl.id, day=day, slot=slot, recipe_id=recipe.id
                )
            )
        summary["templates_created"] += 1

    session.commit()
    return summary
