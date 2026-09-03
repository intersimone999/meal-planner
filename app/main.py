import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.db import init_db
from app.deps import templates
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

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(recipes.router)
app.include_router(ingredients.router)
app.include_router(planner.router)
app.include_router(mealplans.router)
app.include_router(shopping.router)
app.include_router(portability.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
