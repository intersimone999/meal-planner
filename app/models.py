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
    __table_args__ = (UniqueConstraint("year", "week", "day", "slot"),)

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
    __table_args__ = (UniqueConstraint("template_id", "day", "slot"),)

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


class ManualShoppingItem(Base):
    __tablename__ = "manual_shopping_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    checked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class ShoppingCheck(Base):
    """Per-week check state for a derived shopping-list ingredient.

    The (year, week) scoping is what gives 'auto-reset on new week' behavior
    for free — viewing a different week yields a different set of rows.
    """

    __tablename__ = "shopping_checks"
    __table_args__ = (UniqueConstraint("year", "week", "ingredient_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int]
    week: Mapped[int]
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE")
    )
