import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app.db import init_db
from app.deps import get_session, templates
from app.i18n import DAY_NAMES_LONG, SLOTS, SLOT_LABELS, format_day_month
from app.models import PlannedMeal, Recipe
from app.routes import auth, ingredients, mealplans, planner, portability, recipes, shopping
from app.security import (
    AuthMiddleware,
    HTTPS_ONLY,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET,
    is_auth_bypassed,
    log_startup_warnings,
)
from app.weekutil import current_iso_year_week

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log_startup_warnings()
    yield


app = FastAPI(title="menuapp", lifespan=lifespan)

# Middleware order: SessionMiddleware must run BEFORE AuthMiddleware so that
# request.session is populated. Starlette applies user-added middleware in
# reverse order (last added = outermost), so AuthMiddleware is added first.
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=HTTPS_ONLY,
    session_cookie=SESSION_COOKIE_NAME,
)

# Expose auth state to all templates so nav can conditionally render logout.
templates.env.globals["is_auth_bypassed"] = is_auth_bypassed

# Presentation helpers — templates call these directly.
from app.i18n import RECIPE_TYPE_EMOJIS, RECIPE_TYPE_LABELS  # noqa: E402
from app.ingredient_emoji import emoji_for as _ing_emoji  # noqa: E402
templates.env.globals["type_label"] = lambda t: RECIPE_TYPE_LABELS.get(t, t)
templates.env.globals["type_emoji"] = lambda t: RECIPE_TYPE_EMOJIS.get(t, "")
templates.env.globals["ing_emoji"] = _ing_emoji


# Cache-busting query param for static assets: templates append ?v=<mtime>
# so the browser refetches CSS whenever the file on disk changes.
import os as _os  # noqa: E402


def _static_v(path: str) -> str:
    try:
        return str(int(_os.path.getmtime(_os.path.join("app", "static", path))))
    except OSError:
        return "0"


templates.env.globals["static_v"] = _static_v

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(recipes.router)
app.include_router(ingredients.router)
app.include_router(planner.router)
app.include_router(mealplans.router)
app.include_router(shopping.router)
app.include_router(portability.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    today = date.today()
    y, w = current_iso_year_week()
    today_day = today.weekday()
    from app.i18n import RECIPE_TYPE_RANK
    todays_rows = session.scalars(
        select(PlannedMeal)
        .where(
            PlannedMeal.year == y,
            PlannedMeal.week == w,
            PlannedMeal.day == today_day,
        )
        .options(selectinload(PlannedMeal.recipe))
    ).all()
    todays_meals: dict[str, list[PlannedMeal]] = {}
    for m in todays_rows:
        todays_meals.setdefault(m.slot, []).append(m)
    for slot_key in todays_meals:
        todays_meals[slot_key].sort(
            key=lambda m: (RECIPE_TYPE_RANK.get(m.recipe.type, 99), m.recipe.name.lower())
        )
    recent_recipes = session.scalars(
        select(Recipe).order_by(Recipe.id.desc()).limit(6)
    ).all()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "year": y,
            "week": w,
            "today_dayname": DAY_NAMES_LONG[today_day],
            "today_date": format_day_month(today),
            "todays_meals": todays_meals,
            "slots": SLOTS,
            "slot_labels": SLOT_LABELS,
            "recent_recipes": recent_recipes,
        },
    )
