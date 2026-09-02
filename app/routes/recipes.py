from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.deps import get_session, templates
from app.models import Ingredient, Recipe, RecipeIngredient

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


@router.get("", response_class=HTMLResponse)
def list_recipes(request: Request, session: Session = Depends(get_session)):
    recipes = session.scalars(
        select(Recipe)
        .options(
            selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient)
        )
        .order_by(Recipe.name)
    ).all()
    return templates.TemplateResponse(
        request, "recipes/list.html", {"recipes": recipes}
    )


@router.get("/new", response_class=HTMLResponse)
def new_recipe_form(request: Request):
    return templates.TemplateResponse(
        request, "recipes/new.html", {"name": "", "notes": "", "error": None}
    )


@router.post("")
def create_recipe(
    request: Request,
    name: str = Form(...),
    notes: str = Form(""),
    session: Session = Depends(get_session),
):
    name = name.strip()
    notes = notes.strip()
    if not name:
        return templates.TemplateResponse(
            request,
            "recipes/new.html",
            {"error": "Il nome è obbligatorio.", "name": name, "notes": notes},
            status_code=400,
        )
    existing = session.scalar(select(Recipe).where(Recipe.name == name))
    if existing:
        return templates.TemplateResponse(
            request,
            "recipes/new.html",
            {
                "error": f"Esiste già una ricetta con il nome «{name}».",
                "name": name,
                "notes": notes,
            },
            status_code=400,
        )
    recipe = Recipe(name=name, notes=notes or None)
    session.add(recipe)
    session.commit()
    return RedirectResponse(url=f"/recipes/{recipe.id}/edit", status_code=303)


@router.get("/{recipe_id}/edit", response_class=HTMLResponse)
def edit_recipe_form(
    recipe_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    recipe = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(
            selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient)
        )
    )
    if not recipe:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    all_ingredients = session.scalars(
        select(Ingredient).order_by(Ingredient.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "recipes/edit.html",
        {"recipe": recipe, "all_ingredients": all_ingredients, "error": None},
    )


@router.post("/{recipe_id}")
def update_recipe(
    recipe_id: int,
    request: Request,
    name: str = Form(...),
    notes: str = Form(""),
    session: Session = Depends(get_session),
):
    recipe = session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    name = name.strip()
    notes = notes.strip()
    if not name:
        return _edit_with_error(request, session, recipe, "Il nome è obbligatorio.")
    other = session.scalar(
        select(Recipe).where(Recipe.name == name, Recipe.id != recipe_id)
    )
    if other:
        return _edit_with_error(
            request, session, recipe, f"Esiste già una ricetta con il nome «{name}»."
        )
    recipe.name = name
    recipe.notes = notes or None
    session.commit()
    return RedirectResponse(url=f"/recipes/{recipe_id}/edit", status_code=303)


def _edit_with_error(request, session, recipe, error):
    recipe_with_ings = session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe.id)
        .options(
            selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient)
        )
    )
    all_ingredients = session.scalars(
        select(Ingredient).order_by(Ingredient.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "recipes/edit.html",
        {"recipe": recipe_with_ings, "all_ingredients": all_ingredients, "error": error},
        status_code=400,
    )


@router.post("/{recipe_id}/delete")
def delete_recipe(
    recipe_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    recipe = session.get(Recipe, recipe_id)
    if recipe:
        session.delete(recipe)
        session.commit()
    if _is_htmx(request):
        return HTMLResponse("", status_code=200)
    return RedirectResponse(url="/recipes", status_code=303)


@router.post("/{recipe_id}/ingredients", response_class=HTMLResponse)
def add_ingredient_to_recipe(
    recipe_id: int,
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    recipe = session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    name = name.strip()
    if not name:
        return HTMLResponse("", status_code=204)
    ing = session.scalar(select(Ingredient).where(Ingredient.name == name))
    if not ing:
        ing = Ingredient(name=name)
        session.add(ing)
        session.flush()
    existing_link = session.scalar(
        select(RecipeIngredient).where(
            RecipeIngredient.recipe_id == recipe_id,
            RecipeIngredient.ingredient_id == ing.id,
        )
    )
    if not existing_link:
        session.add(RecipeIngredient(recipe_id=recipe_id, ingredient_id=ing.id))
        session.commit()
    else:
        session.commit()  # commit any new-ingredient row even if link existed
    return templates.TemplateResponse(
        request,
        "recipes/_chip.html",
        {"recipe": recipe, "ingredient": ing},
    )


@router.delete("/{recipe_id}/ingredients/{ingredient_id}")
def remove_ingredient_from_recipe(
    recipe_id: int,
    ingredient_id: int,
    session: Session = Depends(get_session),
):
    link = session.scalar(
        select(RecipeIngredient).where(
            RecipeIngredient.recipe_id == recipe_id,
            RecipeIngredient.ingredient_id == ingredient_id,
        )
    )
    if link:
        session.delete(link)
        session.commit()
    return Response(status_code=200)
