from collections.abc import Iterator

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import SessionLocal


def _root_path_context(request: Request) -> dict:
    """Expose the ASGI scope's root_path to every template as `root_path`
    (empty string when running standalone). Templates prepend it to hard-
    coded absolute paths so links keep working behind a reverse-proxy
    sub-path (see app/middleware.py for the sibling response-side fix)."""
    return {"root_path": request.scope.get("root_path", "")}


templates = Jinja2Templates(
    directory="app/templates",
    context_processors=[_root_path_context],
)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
