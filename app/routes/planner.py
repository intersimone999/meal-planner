from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.deps import templates

router = APIRouter(prefix="/planner", tags=["planner"])


@router.get("", response_class=HTMLResponse)
def current_week(request: Request):
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return RedirectResponse(url=f"/planner/{iso_year}/{iso_week}", status_code=303)


@router.get("/{year}/{week}", response_class=HTMLResponse)
def show_week(request: Request, year: int, week: int):
    return templates.TemplateResponse(
        request, "planner/index.html", {"year": year, "week": week}
    )
