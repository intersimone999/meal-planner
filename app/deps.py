from collections.abc import Iterator

from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import SessionLocal

templates = Jinja2Templates(directory="app/templates")


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
