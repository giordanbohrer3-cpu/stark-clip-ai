"""Engine/sessão SQLModel. SQLite (WAL) local ou PostgreSQL via STARK_DATABASE_URL."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().db_url
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return eng
    return create_engine(url, pool_pre_ping=True)


def init_db() -> None:
    from . import models  # noqa: F401  registra tabelas

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
