from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator import derived_for_week
from app.deps import get_session, templates
from app.i18n import format_day_month
from app.ingredient_emoji import DEPARTMENTS, department_for
from app.models import Ingredient, ManualShoppingItem, ShoppingCheck
from app.weekutil import (
    current_iso_year_week,
    iso_week_dates,
    shift_iso_week,
    week_delta,
    week_relative_label,
)

router = APIRouter(prefix="/shopping", tags=["shopping"])


def _group_by_dept(items, name_getter, checked_getter):
    """Group items into DEPARTMENTS-ordered dict; drop empty depts.
    Within each dept, unchecked items come first, both alphabetical."""
    buckets: dict[str, list] = {d: [] for d in DEPARTMENTS}
    for it in items:
        buckets[department_for(name_getter(it))].append(it)
    for d in buckets:
        buckets[d].sort(key=lambda x: (checked_getter(x), name_getter(x).lower()))
    return {d: v for d, v in buckets.items() if v}


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
    derived_flat = derived_for_week(session, year, week)
    manual_flat = session.scalars(select(ManualShoppingItem)).all()

    derived_by_dept = _group_by_dept(
        derived_flat,
        name_getter=lambda t: t[0].name,       # t = (Ingredient, checked)
        checked_getter=lambda t: t[1],
    )
    manual_by_dept = _group_by_dept(
        manual_flat,
        name_getter=lambda i: i.name,
        checked_getter=lambda i: i.checked,
    )

    dates = iso_week_dates(year, week)
    prev_y, prev_w = shift_iso_week(year, week, -1)
    next_y, next_w = shift_iso_week(year, week, +1)
    return templates.TemplateResponse(
        request,
        "shopping/index.html",
        {
            "year": year,
            "week": week,
            "derived_by_dept": derived_by_dept,
            "manual_by_dept": manual_by_dept,
            "any_derived": bool(derived_flat),
            "any_manual": bool(manual_flat),
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
    # NOTE: the newly-added row is returned as a standalone <li> that HTMX
    # appends to #manual-flat-list. The user needs to reload the page to see
    # it grouped into the right department. Trade-off: incremental append
    # is trivial; live regrouping would require a full-section re-render.
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
