import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = os.environ.get("MENUAPP_DB_PATH", "menuapp.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# check_same_thread=False is required because FastAPI may hand the connection
# to a different thread than the one that opened it.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Import models so their tables register on Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
