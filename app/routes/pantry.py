"""Pantry (voci manuali) — flat management of recurring shopping names.

Per SPEC.md §3.6: add / rename / delete only, no check state, no dept
grouping. Every entry here automatically appears on the unified shopping
list (§3.5).
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_session, templates
from app.models import PantryItem

router = APIRouter(prefix="/pantry", tags=["pantry"])


def _list_with(request: Request, session: Session, error: str | None = None, status_code: int = 200):
    rows = session.scalars(select(PantryItem).order_by(PantryItem.name)).all()
    return templates.TemplateResponse(
        request,
        "pantry/list.html",
        {"items": rows, "error": error},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def list_pantry(request: Request, session: Session = Depends(get_session)):
    return _list_with(request, session)


@router.post("")
def add_pantry(
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    name = name.strip()
    if not name:
        return _list_with(request, session, "Il nome è obbligatorio.", 400)
    existing = session.scalar(select(PantryItem).where(PantryItem.name == name))
    if existing:
        return _list_with(request, session, f"«{name}» è già in dispensa.", 400)
    session.add(PantryItem(name=name))
    session.commit()
    return RedirectResponse(url="/pantry", status_code=303)


@router.post("/{item_id}/rename")
def rename_pantry(
    item_id: int,
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    item = session.get(PantryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Voce non trovata")
    new_name = name.strip()
    if not new_name:
        return _list_with(request, session, "Il nome non può essere vuoto.", 400)
    other = session.scalar(
        select(PantryItem).where(PantryItem.name == new_name, PantryItem.id != item_id)
    )
    if other:
        return _list_with(request, session, f"«{new_name}» esiste già.", 400)
    item.name = new_name
    session.commit()
    return RedirectResponse(url="/pantry", status_code=303)


@router.post("/{item_id}/delete")
def delete_pantry(
    item_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    item = session.get(PantryItem, item_id)
    if item:
        session.delete(item)
        session.commit()
    if request.headers.get("HX-Request", "").lower() == "true":
        return HTMLResponse("", status_code=200)
    return RedirectResponse(url="/pantry", status_code=303)
