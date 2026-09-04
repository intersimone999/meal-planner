from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator import derived_for_week
from app.deps import get_session, templates
from app.models import Ingredient, ManualShoppingItem, ShoppingCheck
from app.weekutil import (
    current_iso_year_week,
    iso_week_dates,
    shift_iso_week,
    week_delta,
    week_relative_label,
)
from app.i18n import format_day_month

router = APIRouter(prefix="/shopping", tags=["shopping"])


@router.get("", response_class=HTMLResponse)
def current_week():
    y, w = current_iso_year_week()
    return RedirectResponse(url=f"/shopping/{y}/{w}", status_code=303)


@router.get("/{year}/{week}", response_class=HTMLResponse)
def show_list(
    request: Request,
    year: int,
    week: int,
    session: Session = Depends(get_session),
):
    derived = derived_for_week(session, year, week)
    manual = session.scalars(
        select(ManualShoppingItem).order_by(
            ManualShoppingItem.checked,
            ManualShoppingItem.created_at,
        )
    ).all()
    dates = iso_week_dates(year, week)
    prev_y, prev_w = shift_iso_week(year, week, -1)
    next_y, next_w = shift_iso_week(year, week, +1)
    return templates.TemplateResponse(
        request,
        "shopping/index.html",
        {
            "year": year,
            "week": week,
            "derived": derived,
            "manual": manual,
            "date_range": f"{format_day_month(dates[0])} – {format_day_month(dates[6])}",
            "prev_year": prev_y,
            "prev_week": prev_w,
            "next_year": next_y,
            "next_week": next_w,
            "relative_label": week_relative_label(week_delta(year, week)),
        },
    )


# --- Derived checkboxes ------------------------------------------------------


@router.post("/{year}/{week}/toggle/{ingredient_id}", response_class=HTMLResponse)
def toggle_derived(
    request: Request,
    year: int,
    week: int,
    ingredient_id: int,
    session: Session = Depends(get_session),
):
    ing = session.get(Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(status_code=404, detail="Ingrediente non trovato")
    existing = session.scalar(
        select(ShoppingCheck).where(
            ShoppingCheck.year == year,
            ShoppingCheck.week == week,
            ShoppingCheck.ingredient_id == ingredient_id,
        )
    )
    if existing:
        session.delete(existing)
        checked = False
    else:
        session.add(
            ShoppingCheck(year=year, week=week, ingredient_id=ingredient_id)
        )
        checked = True
    session.commit()
    return templates.TemplateResponse(
        request,
        "shopping/_derived_row.html",
        {"year": year, "week": week, "ing": ing, "checked": checked},
    )


# --- Manual items ------------------------------------------------------------


@router.post("/manual", response_class=HTMLResponse)
def add_manual(
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    name = name.strip()
    if not name:
        return HTMLResponse("", status_code=204)
    item = ManualShoppingItem(name=name)
    session.add(item)
    session.commit()
    return templates.TemplateResponse(
        request, "shopping/_manual_row.html", {"item": item}
    )


@router.post("/manual/{item_id}/toggle", response_class=HTMLResponse)
def toggle_manual(
    request: Request,
    item_id: int,
    session: Session = Depends(get_session),
):
    item = session.get(ManualShoppingItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Voce non trovata")
    item.checked = not item.checked
    session.commit()
    return templates.TemplateResponse(
        request, "shopping/_manual_row.html", {"item": item}
    )


@router.delete("/manual/{item_id}")
def delete_manual(
    item_id: int,
    session: Session = Depends(get_session),
):
    item = session.get(ManualShoppingItem, item_id)
    if item:
        session.delete(item)
        session.commit()
    return Response(status_code=200)
