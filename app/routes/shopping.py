from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_session, templates
from app.models import ManualShoppingItem

router = APIRouter(prefix="/shopping", tags=["shopping"])


@router.get("", response_class=HTMLResponse)
def current_week(request: Request):
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return RedirectResponse(url=f"/shopping/{iso_year}/{iso_week}", status_code=303)


@router.get("/{year}/{week}", response_class=HTMLResponse)
def show_list(
    request: Request,
    year: int,
    week: int,
    session: Session = Depends(get_session),
):
    # Derived section is not yet implemented — placeholder empty list.
    # See CLAUDE.md "Data flow for the shopping list" for the target algorithm:
    # load PlannedMeal rows for (year, week), join RecipeIngredient, group by
    # (ingredient_id, unit), scale by (planned.servings / recipe.servings), sum.
    derived: list = []
    manual = session.scalars(
        select(ManualShoppingItem).order_by(
            ManualShoppingItem.checked, ManualShoppingItem.created_at
        )
    ).all()
    return templates.TemplateResponse(
        request,
        "shopping/index.html",
        {"year": year, "week": week, "derived": derived, "manual": manual},
    )
