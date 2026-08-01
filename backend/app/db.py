import os
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

is_sqlite = settings.DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if is_sqlite else {}

if is_sqlite:
    # Make sure the directory for the sqlite file exists (e.g. /app/data).
    path_part = settings.DATABASE_URL.split("sqlite:///", 1)[-1].lstrip("/")
    db_dir = os.path.dirname("/" + path_part) if path_part else None
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # WAL lets readers (the operator console polling) proceed without
        # blocking on the single background writer that ingestion uses.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def init_db():
    from app import models  # noqa: F401  (ensure models are registered on Base)
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope():
    """Use for background/non-request code: `with session_scope() as db: ...`"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db():
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
