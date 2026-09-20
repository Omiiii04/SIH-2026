"""
PostgreSQL async session factory for the SIH-2026 Orchestrator.

Uses SQLAlchemy 2.x async engine with asyncpg driver.

Phase 1: engine / session factory are defined but not connected (no live DB required).
Phase 2: call ``init_db()`` at app startup to create tables and open the pool.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from orchestrator.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Return the module-level async engine, creating it on first call."""
    global _engine
    if _engine is None:
        cfg = get_settings()
        _engine = create_async_engine(
            cfg.postgres_dsn,
            echo=cfg.debug,
            pool_size=5,
            max_overflow=10,
        )
        logger.info("PostgreSQL async engine created: host=%s db=%s", cfg.postgres_host, cfg.postgres_db)
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields an ``AsyncSession``.

    Usage::

        async with get_session() as session:
            session.add(some_model_instance)
            await session.commit()
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Create all tables defined in ``orchestrator.models``.
    Call this once at application startup (Phase 2).
    """
    from orchestrator.models import Base  # local import to avoid circular deps

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified.")


async def close_db() -> None:
    """Dispose the engine connection pool. Call at application shutdown."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("PostgreSQL engine disposed.")
