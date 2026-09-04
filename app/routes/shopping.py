"""Unified read-view of the week's shopping list (SPEC.md §3.5).

Only interaction is toggling a check; no add/remove — pantry CRUD lives at
/pantry, recipe edits at /recipes/*.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator import shopping_list_for_week
from app.deps import get_session, templates
from app.i18n import format_day_month
from app.ingredient_emoji import DEPARTMENTS, department_for
from app.models import ShoppingCheck
from app.weekutil import (
    current_iso_year_week,
    iso_week_dates,
    shift_iso_week,
    week_delta,
    week_relative_label,
)

router = APIRouter(prefix="/shopping", tags=["shopping"])


def _group_by_dept(items: list[tuple[str, bool]]) -> dict[str, list[tuple[str, bool]]]:
    """Group (name, checked) tuples into DEPARTMENTS-ordered dict; drop empty
    depts. Within each dept, unchecked items come first, both alphabetical."""
    buckets: dict[str, list] = {d: [] for d in DEPARTMENTS}
    for name, checked in items:
        buckets[department_for(name)].append((name, checked))
    for d in buckets:
        buckets[d].sort(key=lambda t: (t[1], t[0].lower()))
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
    items = shopping_list_for_week(session, year, week)
    items_by_dept = _group_by_dept(items)
    dates = iso_week_dates(year, week)
    prev_y, prev_w = shift_iso_week(year, week, -1)
    next_y, next_w = shift_iso_week(year, week, +1)
    return templates.TemplateResponse(
        request,
        "shopping/index.html",
        {
            "year": year,
            "week": week,
            "items_by_dept": items_by_dept,
            "any_items": bool(items),
            "date_range": f"{format_day_month(dates[0])} – {format_day_month(dates[6])}",
            "prev_year": prev_y,
            "prev_week": prev_w,
            "next_year": next_y,
            "next_week": next_w,
            "relative_label": week_relative_label(week_delta(year, week)),
        },
    )


@router.post("/{year}/{week}/toggle", response_class=HTMLResponse)
def toggle(
    request: Request,
    year: int,
    week: int,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome mancante")
    existing = session.scalar(
        select(ShoppingCheck).where(
            ShoppingCheck.year == year,
            ShoppingCheck.week == week,
            ShoppingCheck.name == name,
        )
    )
    if existing:
        session.delete(existing)
        checked = False
    else:
        session.add(ShoppingCheck(year=year, week=week, name=name))
        checked = True
    session.commit()
    return templates.TemplateResponse(
        request,
        "shopping/_row.html",
        {"year": year, "week": week, "name": name, "checked": checked},
    )
