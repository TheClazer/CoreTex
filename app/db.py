"""SQLAlchemy engine + session factory + Base.

We use synchronous SQLAlchemy 2.0 — simpler than async, works fine inside
FastAPI's threadpool (each request gets its own session via Depends), and
crucially lets the RQ worker share the same models/session without a
second async event loop.

The engine is created lazily so the app boots even when DATABASE_URL is
empty (CoreTex still works as a stateless converter without Postgres).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker[Session]] = None


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def _normalize_url(url: str) -> str:
    """Railway / Heroku hand out ``postgres://`` URLs; SQLAlchemy needs ``postgresql://``."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def get_engine() -> Optional[Engine]:
    """Return the lazy-initialised Engine, or None if DATABASE_URL is unset."""
    global _engine, _SessionFactory
    if _engine is not None:
        return _engine
    if not settings.DATABASE_URL:
        return None
    url = _normalize_url(settings.DATABASE_URL)
    if url.startswith("sqlite"):
        # Local-dev convenience. SQLite hands the same connection to
        # different threads under FastAPI's threadpool, so check_same_thread
        # must be off and a single shared connection (StaticPool) used.
        # The Postgres/Railway path below is left exactly as before.
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
    else:
        _engine = create_engine(
            url,
            pool_pre_ping=True,        # graceful reconnect on stale Railway pgbouncer
            pool_size=5,
            max_overflow=10,
            future=True,
        )
    _SessionFactory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    logger.info("Database engine initialised at %s", url.split("@")[-1])
    return _engine


def get_session_factory() -> Optional[sessionmaker[Session]]:
    if _SessionFactory is None:
        get_engine()
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for one-off database work (used by the worker)."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Yields a session, rolls back on exception."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    session = factory()
    try:
        yield session
    finally:
        session.close()


def create_all() -> None:
    """Create tables idempotently. Called at app startup when DB is configured."""
    engine = get_engine()
    if engine is None:
        return
    # Import models so SQLAlchemy registers them before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    logger.info("Database tables ensured.")


def db_enabled() -> bool:
    return bool(settings.DATABASE_URL)
