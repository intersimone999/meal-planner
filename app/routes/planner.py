from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_session, templates
from app.i18n import DAY_NAMES_SHORT, RECIPE_TYPE_RANK, SLOT_LABELS, SLOTS, format_day_month
from app.models import MealPlanTemplate, PlannedMeal, Recipe, TemplateSlot
from app.weekutil import current_iso_year_week, iso_week_dates, shift_iso_week

router = APIRouter(prefix="/planner", tags=["planner"])


def _validate(day: int, slot: str) -> None:
    if not 0 <= day <= 6:
        raise HTTPException(status_code=400, detail="Giorno non valido")
    if slot not in SLOTS:
        raise HTTPException(status_code=400, detail="Fascia oraria non valida")


def _load_cell_meals(session: Session, year: int, week: int, day: int, slot: str) -> list[PlannedMeal]:
    rows = session.scalars(
        select(PlannedMeal)
        .where(
            PlannedMeal.year == year,
            PlannedMeal.week == week,
            PlannedMeal.day == day,
            PlannedMeal.slot == slot,
        )
        .options(selectinload(PlannedMeal.recipe))
    ).all()
    # Sort by recipe type rank, then by recipe name.
    return sorted(
        rows,
        key=lambda m: (RECIPE_TYPE_RANK.get(m.recipe.type, 99), m.recipe.name.lower()),
    )


def _cell_response(request: Request, year: int, week: int, day: int, slot: str, meals: list[PlannedMeal]):
    return templates.TemplateResponse(
        request,
        "planner/_cell.html",
        {"year": year, "week": week, "day": day, "slot": slot, "meals": meals},
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
    rows = session.scalars(
        select(PlannedMeal)
        .where(PlannedMeal.year == year, PlannedMeal.week == week)
        .options(selectinload(PlannedMeal.recipe))
    ).all()
    grid: dict[tuple[int, str], list[PlannedMeal]] = {}
    for m in rows:
        grid.setdefault((m.day, m.slot), []).append(m)
    for key in grid:
        grid[key].sort(
            key=lambda m: (RECIPE_TYPE_RANK.get(m.recipe.type, 99), m.recipe.name.lower())
        )
    dates = iso_week_dates(year, week)
    prev_y, prev_w = shift_iso_week(year, week, -1)
    next_y, next_w = shift_iso_week(year, week, +1)
    mealplans = session.scalars(
        select(MealPlanTemplate).order_by(MealPlanTemplate.name)
    ).all()
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
            "mealplans": mealplans,
        },
    )


@router.get("/{year}/{week}/{day}/{slot}", response_class=HTMLResponse)
def render_cell(
    request: Request, year: int, week: int, day: int, slot: str,
    session: Session = Depends(get_session),
):
    """Re-render a cell in its current state (used by 'annulla' from edit mode)."""
    _validate(day, slot)
    meals = _load_cell_meals(session, year, week, day, slot)
    return _cell_response(request, year, week, day, slot, meals)


@router.get("/{year}/{week}/{day}/{slot}/edit", response_class=HTMLResponse)
def edit_cell(
    request: Request, year: int, week: int, day: int, slot: str,
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    meals = _load_cell_meals(session, year, week, day, slot)
    already = {m.recipe_id for m in meals}
    recipes = [
        r for r in session.scalars(select(Recipe).order_by(Recipe.name)).all()
        if r.id not in already
    ]
    return templates.TemplateResponse(
        request,
        "planner/_edit_cell.html",
        {
            "year": year, "week": week, "day": day, "slot": slot,
            "meals": meals,
            "recipes": recipes,
        },
    )


@router.post("/{year}/{week}/{day}/{slot}", response_class=HTMLResponse)
def add_to_cell(
    request: Request, year: int, week: int, day: int, slot: str,
    recipe_id: str = Form(""),
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    if not recipe_id:
        # No selection ⇒ just re-render the current cell (silent no-op).
        meals = _load_cell_meals(session, year, week, day, slot)
        return _cell_response(request, year, week, day, slot, meals)
    try:
        rid = int(recipe_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID ricetta non valido")
    if not session.get(Recipe, rid):
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    # Duplicate-per-cell is a silent no-op (idempotent add).
    existing = session.scalar(
        select(PlannedMeal).where(
            PlannedMeal.year == year, PlannedMeal.week == week,
            PlannedMeal.day == day, PlannedMeal.slot == slot,
            PlannedMeal.recipe_id == rid,
        )
    )
    if not existing:
        session.add(
            PlannedMeal(year=year, week=week, day=day, slot=slot, recipe_id=rid)
        )
        session.commit()
    meals = _load_cell_meals(session, year, week, day, slot)
    return _cell_response(request, year, week, day, slot, meals)


@router.delete("/{year}/{week}/{day}/{slot}/{recipe_id}", response_class=HTMLResponse)
def remove_from_cell(
    request: Request, year: int, week: int, day: int, slot: str, recipe_id: int,
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    existing = session.scalar(
        select(PlannedMeal).where(
            PlannedMeal.year == year, PlannedMeal.week == week,
            PlannedMeal.day == day, PlannedMeal.slot == slot,
            PlannedMeal.recipe_id == recipe_id,
        )
    )
    if existing:
        session.delete(existing)
        session.commit()
    meals = _load_cell_meals(session, year, week, day, slot)
    return _cell_response(request, year, week, day, slot, meals)


@router.post("/{year}/{week}/apply")
def apply_template(
    year: int, week: int,
    template_id: int = Form(...),
    session: Session = Depends(get_session),
):
    tpl = session.scalar(
        select(MealPlanTemplate)
        .where(MealPlanTemplate.id == template_id)
        .options(selectinload(MealPlanTemplate.slots))
    )
    if not tpl:
        raise HTTPException(status_code=404, detail="Modello non trovato")
    if not tpl.slots:
        return RedirectResponse(url=f"/planner/{year}/{week}", status_code=303)

    # Group template rows by (day, slot).
    by_cell: dict[tuple[int, str], list[int]] = {}
    for s in tpl.slots:
        by_cell.setdefault((s.day, s.slot), []).append(s.recipe_id)

    # For each cell in the template, insert only if the target cell is
    # FULLY EMPTY (§3.4 fill-empty at the cell level, no partial merge).
    # One SELECT COUNT per cell — fine for at most 14 cells.
    for (day, slot), recipe_ids in by_cell.items():
        existing = session.scalar(
            select(func.count(PlannedMeal.id)).where(
                PlannedMeal.year == year, PlannedMeal.week == week,
                PlannedMeal.day == day, PlannedMeal.slot == slot,
            )
        )
        if existing == 0:
            for rid in recipe_ids:
                session.add(
                    PlannedMeal(year=year, week=week, day=day, slot=slot, recipe_id=rid)
                )
    session.commit()
    return RedirectResponse(url=f"/planner/{year}/{week}", status_code=303)
