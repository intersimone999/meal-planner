from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_session, templates
from app.i18n import DAY_NAMES_SHORT, SLOT_LABELS, SLOTS, format_day_month
from app.models import PlannedMeal, Recipe
from app.weekutil import current_iso_year_week, iso_week_dates, shift_iso_week

router = APIRouter(prefix="/planner", tags=["planner"])


def _validate(day: int, slot: str) -> None:
    if not 0 <= day <= 6:
        raise HTTPException(status_code=400, detail="Giorno non valido")
    if slot not in SLOTS:
        raise HTTPException(status_code=400, detail="Fascia oraria non valida")


def _load_meal(session: Session, year: int, week: int, day: int, slot: str) -> PlannedMeal | None:
    return session.scalar(
        select(PlannedMeal)
        .where(
            PlannedMeal.year == year,
            PlannedMeal.week == week,
            PlannedMeal.day == day,
            PlannedMeal.slot == slot,
        )
        .options(selectinload(PlannedMeal.recipe))
    )


def _cell_response(request: Request, year: int, week: int, day: int, slot: str, meal: PlannedMeal | None):
    return templates.TemplateResponse(
        request,
        "planner/_cell.html",
        {"year": year, "week": week, "day": day, "slot": slot, "meal": meal},
    )


@router.get("", response_class=HTMLResponse)
def current_week():
    y, w = current_iso_year_week()
    return RedirectResponse(url=f"/planner/{y}/{w}", status_code=303)


@router.get("/{year}/{week}", response_class=HTMLResponse)
def show_week(
    request: Request,
    year: int,
    week: int,
    session: Session = Depends(get_session),
):
    meals = session.scalars(
        select(PlannedMeal)
        .where(PlannedMeal.year == year, PlannedMeal.week == week)
        .options(selectinload(PlannedMeal.recipe))
    ).all()
    grid = {(m.day, m.slot): m for m in meals}
    dates = iso_week_dates(year, week)
    prev_y, prev_w = shift_iso_week(year, week, -1)
    next_y, next_w = shift_iso_week(year, week, +1)
    return templates.TemplateResponse(
        request,
        "planner/index.html",
        {
            "year": year,
            "week": week,
            "grid": grid,
            "dates": dates,
            "date_labels": [format_day_month(d) for d in dates],
            "day_names": DAY_NAMES_SHORT,
            "slots": SLOTS,
            "slot_labels": SLOT_LABELS,
            "prev_year": prev_y,
            "prev_week": prev_w,
            "next_year": next_y,
            "next_week": next_w,
        },
    )


@router.get("/{year}/{week}/{day}/{slot}", response_class=HTMLResponse)
def render_cell(
    request: Request,
    year: int,
    week: int,
    day: int,
    slot: str,
    session: Session = Depends(get_session),
):
    """Render a single cell in its current state (used by 'annulla' from edit mode)."""
    _validate(day, slot)
    meal = _load_meal(session, year, week, day, slot)
    return _cell_response(request, year, week, day, slot, meal)


@router.get("/{year}/{week}/{day}/{slot}/edit", response_class=HTMLResponse)
def edit_cell(
    request: Request,
    year: int,
    week: int,
    day: int,
    slot: str,
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    meal = _load_meal(session, year, week, day, slot)
    recipes = session.scalars(select(Recipe).order_by(Recipe.name)).all()
    return templates.TemplateResponse(
        request,
        "planner/_edit_cell.html",
        {
            "year": year,
            "week": week,
            "day": day,
            "slot": slot,
            "meal": meal,
            "recipes": recipes,
        },
    )


@router.post("/{year}/{week}/{day}/{slot}", response_class=HTMLResponse)
def assign_cell(
    request: Request,
    year: int,
    week: int,
    day: int,
    slot: str,
    recipe_id: str = Form(""),
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    existing = _load_meal(session, year, week, day, slot)
    if not recipe_id:
        # Empty selection ⇒ treat as remove
        if existing:
            session.delete(existing)
            session.commit()
        return _cell_response(request, year, week, day, slot, None)
    try:
        rid = int(recipe_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID ricetta non valido")
    recipe = session.get(Recipe, rid)
    if not recipe:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    if existing:
        existing.recipe_id = rid
    else:
        session.add(
            PlannedMeal(year=year, week=week, day=day, slot=slot, recipe_id=rid)
        )
    session.commit()
    meal = _load_meal(session, year, week, day, slot)
    return _cell_response(request, year, week, day, slot, meal)


@router.delete("/{year}/{week}/{day}/{slot}", response_class=HTMLResponse)
def remove_cell(
    request: Request,
    year: int,
    week: int,
    day: int,
    slot: str,
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    existing = _load_meal(session, year, week, day, slot)
    if existing:
        session.delete(existing)
        session.commit()
    return _cell_response(request, year, week, day, slot, None)
