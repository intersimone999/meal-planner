from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_session, templates
from app.models import Recipe

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("", response_class=HTMLResponse)
def list_recipes(request: Request, session: Session = Depends(get_session)):
    recipes = session.scalars(select(Recipe).order_by(Recipe.name)).all()
    return templates.TemplateResponse(
        request, "recipes/list.html", {"recipes": recipes}
    )
