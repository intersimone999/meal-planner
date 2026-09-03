from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_session, templates
from app.i18n import DAY_NAMES_SHORT, RECIPE_TYPE_RANK, SLOT_LABELS, SLOTS
from app.models import MealPlanTemplate, Recipe, TemplateSlot

router = APIRouter(prefix="/mealplans", tags=["mealplans"])


def _validate(day: int, slot: str) -> None:
    if not 0 <= day <= 6:
        raise HTTPException(status_code=400, detail="Giorno non valido")
    if slot not in SLOTS:
        raise HTTPException(status_code=400, detail="Fascia oraria non valida")


def _load_template(session: Session, template_id: int) -> MealPlanTemplate:
    tpl = session.scalar(
        select(MealPlanTemplate)
        .where(MealPlanTemplate.id == template_id)
        .options(selectinload(MealPlanTemplate.slots).selectinload(TemplateSlot.recipe))
    )
    if not tpl:
        raise HTTPException(status_code=404, detail="Modello non trovato")
    return tpl


def _load_cell_entries(session: Session, template_id: int, day: int, slot: str) -> list[TemplateSlot]:
    rows = session.scalars(
        select(TemplateSlot)
        .where(
            TemplateSlot.template_id == template_id,
            TemplateSlot.day == day,
            TemplateSlot.slot == slot,
        )
        .options(selectinload(TemplateSlot.recipe))
    ).all()
    return sorted(
        rows,
        key=lambda e: (RECIPE_TYPE_RANK.get(e.recipe.type, 99), e.recipe.name.lower()),
    )


def _cell_response(request: Request, template_id: int, day: int, slot: str, entries: list[TemplateSlot]):
    return templates.TemplateResponse(
        request,
        "mealplans/_cell.html",
        {"template_id": template_id, "day": day, "slot": slot, "entries": entries},
    )


# --- List / create / update / delete -----------------------------------------


@router.get("", response_class=HTMLResponse)
def list_templates(request: Request, session: Session = Depends(get_session)):
    usage = func.count(TemplateSlot.id).label("usage")
    rows = session.execute(
        select(MealPlanTemplate, usage)
        .join(TemplateSlot, TemplateSlot.template_id == MealPlanTemplate.id, isouter=True)
        .group_by(MealPlanTemplate.id)
        .order_by(MealPlanTemplate.name)
    ).all()
    return templates.TemplateResponse(
        request, "mealplans/list.html", {"rows": rows}
    )


@router.get("/new", response_class=HTMLResponse)
def new_template_form(request: Request):
    return templates.TemplateResponse(
        request, "mealplans/new.html", {"name": "", "error": None}
    )


@router.post("")
def create_template(
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request, "mealplans/new.html",
            {"error": "Il nome è obbligatorio.", "name": name},
            status_code=400,
        )
    existing = session.scalar(select(MealPlanTemplate).where(MealPlanTemplate.name == name))
    if existing:
        return templates.TemplateResponse(
            request, "mealplans/new.html",
            {"error": f"Esiste già un modello con il nome «{name}».", "name": name},
            status_code=400,
        )
    tpl = MealPlanTemplate(name=name)
    session.add(tpl)
    session.commit()
    return RedirectResponse(url=f"/mealplans/{tpl.id}/edit", status_code=303)


@router.get("/{template_id}/edit", response_class=HTMLResponse)
def edit_template_form(
    template_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    tpl = _load_template(session, template_id)
    grid: dict[tuple[int, str], list[TemplateSlot]] = {}
    for s in tpl.slots:
        grid.setdefault((s.day, s.slot), []).append(s)
    for key in grid:
        grid[key].sort(
            key=lambda s: (RECIPE_TYPE_RANK.get(s.recipe.type, 99), s.recipe.name.lower())
        )
    return templates.TemplateResponse(
        request,
        "mealplans/edit.html",
        {
            "template": tpl,
            "grid": grid,
            "day_names": DAY_NAMES_SHORT,
            "slots": SLOTS,
            "slot_labels": SLOT_LABELS,
            "error": None,
        },
    )


@router.post("/{template_id}")
def update_template(
    template_id: int,
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    tpl = session.get(MealPlanTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Modello non trovato")
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Il nome è obbligatorio.")
    other = session.scalar(
        select(MealPlanTemplate).where(
            MealPlanTemplate.name == name, MealPlanTemplate.id != template_id
        )
    )
    if other:
        raise HTTPException(
            status_code=400, detail=f"Esiste già un modello «{name}»."
        )
    tpl.name = name
    session.commit()
    return RedirectResponse(url=f"/mealplans/{template_id}/edit", status_code=303)


@router.post("/{template_id}/delete")
def delete_template(
    template_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    tpl = session.get(MealPlanTemplate, template_id)
    if tpl:
        session.delete(tpl)
        session.commit()
    if request.headers.get("HX-Request", "").lower() == "true":
        return HTMLResponse("", status_code=200)
    return RedirectResponse(url="/mealplans", status_code=303)


# --- Per-cell HTMX endpoints -------------------------------------------------


@router.get("/{template_id}/cell/{day}/{slot}", response_class=HTMLResponse)
def render_cell(
    template_id: int, day: int, slot: str,
    request: Request,
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    entries = _load_cell_entries(session, template_id, day, slot)
    return _cell_response(request, template_id, day, slot, entries)


@router.get("/{template_id}/cell/{day}/{slot}/edit", response_class=HTMLResponse)
def edit_cell(
    template_id: int, day: int, slot: str,
    request: Request,
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    entries = _load_cell_entries(session, template_id, day, slot)
    already = {e.recipe_id for e in entries}
    recipes = [
        r for r in session.scalars(select(Recipe).order_by(Recipe.name)).all()
        if r.id not in already
    ]
    return templates.TemplateResponse(
        request,
        "mealplans/_edit_cell.html",
        {
            "template_id": template_id, "day": day, "slot": slot,
            "entries": entries,
            "recipes": recipes,
        },
    )


@router.post("/{template_id}/cell/{day}/{slot}", response_class=HTMLResponse)
def add_to_cell(
    template_id: int, day: int, slot: str,
    request: Request,
    recipe_id: str = Form(""),
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    tpl = session.get(MealPlanTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Modello non trovato")
    if not recipe_id:
        entries = _load_cell_entries(session, template_id, day, slot)
        return _cell_response(request, template_id, day, slot, entries)
    try:
        rid = int(recipe_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID ricetta non valido")
    if not session.get(Recipe, rid):
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    existing = session.scalar(
        select(TemplateSlot).where(
            TemplateSlot.template_id == template_id,
            TemplateSlot.day == day, TemplateSlot.slot == slot,
            TemplateSlot.recipe_id == rid,
        )
    )
    if not existing:
        session.add(TemplateSlot(template_id=template_id, day=day, slot=slot, recipe_id=rid))
        session.commit()
    entries = _load_cell_entries(session, template_id, day, slot)
    return _cell_response(request, template_id, day, slot, entries)


@router.delete("/{template_id}/cell/{day}/{slot}/{recipe_id}", response_class=HTMLResponse)
def remove_from_cell(
    template_id: int, day: int, slot: str, recipe_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    _validate(day, slot)
    existing = session.scalar(
        select(TemplateSlot).where(
            TemplateSlot.template_id == template_id,
            TemplateSlot.day == day, TemplateSlot.slot == slot,
            TemplateSlot.recipe_id == recipe_id,
        )
    )
    if existing:
        session.delete(existing)
        session.commit()
    entries = _load_cell_entries(session, template_id, day, slot)
    return _cell_response(request, template_id, day, slot, entries)
