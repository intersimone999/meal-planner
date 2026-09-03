"""Pure aggregation logic for the shopping list.

Kept separate from the route module so it is trivially unit-testable.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ingredient, PlannedMeal, RecipeIngredient, ShoppingCheck


def derived_for_week(
    session: Session, year: int, week: int
) -> list[tuple[Ingredient, bool]]:
    """Return the derived shopping list for the given ISO year+week.

    Each entry is (Ingredient, is_checked). Unchecked items come first
    (alphabetical), then checked items (alphabetical). "Checked" state
    is scoped to (year, week) via the ShoppingCheck table, so a new
    week naturally shows every item unchecked.
    """
    ingredients_stmt = (
        select(Ingredient)
        .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .join(PlannedMeal, PlannedMeal.recipe_id == RecipeIngredient.recipe_id)
        .where(PlannedMeal.year == year, PlannedMeal.week == week)
        .distinct()
        .order_by(Ingredient.name)
    )
    ingredients = list(session.scalars(ingredients_stmt).all())

    checked_ids = set(
        session.scalars(
            select(ShoppingCheck.ingredient_id).where(
                ShoppingCheck.year == year, ShoppingCheck.week == week
            )
        ).all()
    )

    unchecked = [(i, False) for i in ingredients if i.id not in checked_ids]
    checked = [(i, True) for i in ingredients if i.id in checked_ids]
    return unchecked + checked
