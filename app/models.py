from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    default_unit: Mapped[str] = mapped_column(String(20))

    recipe_lines: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="ingredient"
    )


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    # Portions the recipe yields as written. PlannedMeal.servings scales this.
    servings: Mapped[int] = mapped_column(default=1)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
    )
    planned: Mapped[list["PlannedMeal"]] = relationship(back_populates="recipe")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE")
    )
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[float]
    # Unit may differ from Ingredient.default_unit if the recipe expresses it
    # differently (e.g. flour default_unit=g, recipe line uses "cups").
    unit: Mapped[str] = mapped_column(String(20))

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship(back_populates="recipe_lines")


class PlannedMeal(Base):
    __tablename__ = "planned_meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int]        # ISO year
    week: Mapped[int]        # ISO week (1-53)
    day: Mapped[int]         # 0=Mon .. 6=Sun
    slot: Mapped[str] = mapped_column(String(30))  # e.g. breakfast|lunch|dinner|snack
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    # Portions actually wanted for this planned meal. Aggregator scales
    # RecipeIngredient quantities by (servings / recipe.servings).
    servings: Mapped[int] = mapped_column(default=1)

    recipe: Mapped[Recipe] = relationship(back_populates="planned")


class ManualShoppingItem(Base):
    __tablename__ = "manual_shopping_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    checked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
