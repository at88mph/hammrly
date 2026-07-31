from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_from_url(url: str) -> Engine:
    """Read-only usage: prefer a replica DSN or DB role with SELECT only."""
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if "postgresql" in url.lower():
        kwargs["connect_args"] = {"options": "-c default_transaction_read_only=on"}
    return create_engine(url, **kwargs)


def create_writable_engine_from_url(url: str) -> Engine:
    """Writable engine for narrowly scoped mutations (e.g. notification read_at)."""
    return create_engine(url, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
