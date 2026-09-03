from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
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


@router.post("/{ingredient_id}/merge")
def merge_ingredient(
    ingredient_id: int,
    request: Request,
    target_id: str = Form(""),
    session: Session = Depends(get_session),
):
    if not target_id:
        return _list_with(request, session, "Scegli un ingrediente in cui unire.", 400)
    try:
        tid = int(target_id)
    except ValueError:
        return _list_with(request, session, "ID di destinazione non valido.", 400)
    if tid == ingredient_id:
        return _list_with(
            request, session, "Non puoi unire un ingrediente in se stesso.", 400
        )
    source = session.get(Ingredient, ingredient_id)
    target = session.get(Ingredient, tid)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Ingrediente non trovato")

    # Use core SQL to avoid the ORM's relationship auto-nullification
    # when deleting the source Ingredient (its .recipe_lines collection
    # would try to set ingredient_id=NULL on rows we just reassigned).

    # 1. Drop source-links on recipes that already reference target
    #    (would otherwise violate UNIQUE(recipe_id, ingredient_id) on reassign).
    session.execute(
        sa_delete(RecipeIngredient).where(
            RecipeIngredient.ingredient_id == ingredient_id,
            RecipeIngredient.recipe_id.in_(
                select(RecipeIngredient.recipe_id).where(
                    RecipeIngredient.ingredient_id == tid
                )
            ),
        )
    )
    # 2. Reassign remaining source-links to target.
    session.execute(
        sa_update(RecipeIngredient)
        .where(RecipeIngredient.ingredient_id == ingredient_id)
        .values(ingredient_id=tid)
    )
    # 3. Delete the (now unreferenced) source ingredient.
    session.execute(sa_delete(Ingredient).where(Ingredient.id == ingredient_id))
    session.commit()
    return RedirectResponse(url="/ingredients", status_code=303)
