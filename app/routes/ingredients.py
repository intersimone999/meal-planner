from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_session, templates
from app.models import Ingredient, RecipeIngredient

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


def _list_with(request: Request, session: Session, error: str | None = None, status_code: int = 200):
    usage_col = func.count(RecipeIngredient.id).label("usage")
    rows = session.execute(
        select(Ingredient, usage_col)
        .join(
            RecipeIngredient,
            RecipeIngredient.ingredient_id == Ingredient.id,
            isouter=True,
        )
        .group_by(Ingredient.id)
        .order_by(Ingredient.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "ingredients/list.html",
        {"rows": rows, "error": error},
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
def list_ingredients(request: Request, session: Session = Depends(get_session)):
    return _list_with(request, session)


@router.post("/{ingredient_id}/rename")
def rename_ingredient(
    ingredient_id: int,
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    ing = session.get(Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(status_code=404, detail="Ingrediente non trovato")
    new_name = name.strip()
    if not new_name:
        return _list_with(request, session, "Il nome non può essere vuoto.", 400)
    other = session.scalar(
        select(Ingredient).where(
            Ingredient.name == new_name, Ingredient.id != ingredient_id
        )
    )
    if other:
        return _list_with(
            request, session, f"Esiste già un ingrediente «{new_name}».", 400
        )
    ing.name = new_name
    session.commit()
    return RedirectResponse(url="/ingredients", status_code=303)


@router.post("/{ingredient_id}/delete")
def delete_ingredient(
    ingredient_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    ing = session.get(Ingredient, ingredient_id)
    if not ing:
        raise HTTPException(status_code=404, detail="Ingrediente non trovato")
    usage = session.scalar(
        select(func.count(RecipeIngredient.id)).where(
            RecipeIngredient.ingredient_id == ingredient_id
        )
    )
    if usage and usage > 0:
        plural = "ricetta" if usage == 1 else "ricette"
        return _list_with(
            request,
            session,
            f"Non posso eliminare «{ing.name}»: è ancora usato in {usage} {plural}.",
            400,
        )
    session.delete(ing)
    session.commit()
    return RedirectResponse(url="/ingredients", status_code=303)
