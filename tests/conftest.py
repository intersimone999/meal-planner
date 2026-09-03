"""Shared test fixtures.

Sets MENUAPP_DB_PATH to a temporary file BEFORE importing the app so the
module-level SQLAlchemy engine in `app.db` picks up the isolated path.
"""

import os
import tempfile
from pathlib import Path

# Must be set before `app.*` is imported anywhere.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="menuapp-tests-"))
os.environ.setdefault("MENUAPP_DB_PATH", str(_TMP_DIR / "test.db"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    """Drop + recreate all tables around every test for full isolation."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
