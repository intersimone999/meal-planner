"""Pure aggregation logic for the unified shopping list (SPEC.md §3.5).

Kept separate from the route module so it is trivially unit-testable.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Ingredient,
    PantryItem,
    PlannedMeal,
    RecipeIngredient,
    ShoppingCheck,
)


def shopping_list_for_week(
    session: Session, year: int, week: int
) -> list[tuple[str, bool]]:
    """Return the unified shopping list for the given ISO year+week.

    Union of (recipe ingredients planned for the week) + (all pantry items),
    deduped by lowercased name, sorted alphabetically. Each entry is
    (display_name, is_checked). Check state comes from ShoppingCheck rows
    keyed on (year, week, name); the auto-reset on a new week falls out of
    the schema.
    """
    derived_names = list(
        session.scalars(
            select(Ingredient.name)
            .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
            .join(PlannedMeal, PlannedMeal.recipe_id == RecipeIngredient.recipe_id)
            .where(PlannedMeal.year == year, PlannedMeal.week == week)
            .distinct()
        ).all()
    )
    pantry_names = list(
        session.scalars(select(PantryItem.name).order_by(PantryItem.name)).all()
    )

    # Dedup case-insensitive; keep the first-seen original casing.
    seen: dict[str, str] = {}
    for name in derived_names + pantry_names:
        key = name.lower()
        if key not in seen:
            seen[key] = name

    display_names = sorted(seen.values(), key=str.lower)

    checked_names_lc = {
        c.lower()
        for c in session.scalars(
            select(ShoppingCheck.name).where(
                ShoppingCheck.year == year, ShoppingCheck.week == week
            )
        ).all()
    }

    return [(n, n.lower() in checked_names_lc) for n in display_names]
