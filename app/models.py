from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# SQLite COLLATE NOCASE lets the UNIQUE index enforce case-insensitive
# uniqueness on names while preserving the user's original casing for display.
NoCaseString = lambda length: String(length, collation="NOCASE")  # noqa: E731


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(NoCaseString(120), unique=True, index=True)

    recipe_lines: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="ingredient"
    )


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(NoCaseString(200), unique=True)
    # Type is required and constrained at the application layer to one of
    # app.i18n.RECIPE_TYPES. SQLite doesn't enforce enum-style CHECK by default
    # in every driver; the route handlers validate the incoming value.
    type: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
    )
    planned: Mapped[list["PlannedMeal"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
    )
    template_slots: Mapped[list["TemplateSlot"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (UniqueConstraint("recipe_id", "ingredient_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE")
    )
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient] = relationship(back_populates="recipe_lines")


class PlannedMeal(Base):
    __tablename__ = "planned_meals"
    # A cell (year, week, day, slot) holds many recipes; only the same recipe
    # being added twice to the same cell is blocked.
    __table_args__ = (
        UniqueConstraint("year", "week", "day", "slot", "recipe_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int]        # ISO year
    week: Mapped[int]        # ISO week (1-53)
    day: Mapped[int]         # 0=Mon .. 6=Sun
    slot: Mapped[str] = mapped_column(String(30))  # "lunch" | "dinner"
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE")
    )

    recipe: Mapped[Recipe] = relationship(back_populates="planned")


class MealPlanTemplate(Base):
    __tablename__ = "meal_plan_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(NoCaseString(120), unique=True)

    slots: Mapped[list["TemplateSlot"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
    )


class TemplateSlot(Base):
    __tablename__ = "template_slots"
    # Same rule as PlannedMeal: cell holds many recipes, no duplicate-per-cell.
    __table_args__ = (
        UniqueConstraint("template_id", "day", "slot", "recipe_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("meal_plan_templates.id", ondelete="CASCADE")
    )
    day: Mapped[int]         # 0=Mon .. 6=Sun
    slot: Mapped[str] = mapped_column(String(30))  # "lunch" | "dinner"
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE")
    )

    template: Mapped[MealPlanTemplate] = relationship(back_populates="slots")
    recipe: Mapped[Recipe] = relationship(back_populates="template_slots")


class PantryItem(Base):
    """User-managed recurring shopping name (§3.6). Every pantry item appears
    on the unified shopping list; no per-item check state (that lives in
    ShoppingCheck, per week)."""

    __tablename__ = "pantry_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(NoCaseString(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class ShoppingCheck(Base):
    """Per-week check state for a shopping-list item, keyed by NAME.

    Name-based so a single row covers both derived ingredients (from planned
    meals) and pantry items uniformly — matching the deduped, unified view
    in §3.5. The (year, week) scoping is what gives 'auto-reset on new week'
    behavior for free.
    """

    __tablename__ = "shopping_checks"
    __table_args__ = (UniqueConstraint("year", "week", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int]
    week: Mapped[int]
    name: Mapped[str] = mapped_column(NoCaseString(200))
