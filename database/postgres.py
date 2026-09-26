"""
database/postgres.py
────────────────────
Phase 4 — PostgreSQL async session factory (promoted from Phase 1 stub).

Uses SQLAlchemy 2.x async engine with asyncpg driver.

Public API
──────────
  init_db()         — create tables at startup
  close_db()        — dispose pool at shutdown
  get_session()     — async context manager yielding an AsyncSession
  upsert_user()     — insert-or-ignore for the users table
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from orchestrator.config import get_settings

logger = logging.getLogger(__name__)

_engine:          AsyncEngine                   | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Internal engine / factory
# ─────────────────────────────────────────────────────────────────────────────

def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg = get_settings()
        _engine = create_async_engine(
            cfg.postgres_dsn,
            echo=cfg.debug,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,           # detect stale connections
        )
        logger.info(
            "PostgreSQL async engine created: host=%s db=%s",
            cfg.postgres_host, cfg.postgres_db,
        )
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


# ─────────────────────────────────────────────────────────────────────────────
# Public session context manager
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a transactional ``AsyncSession``.

    Usage::

        async with get_session() as session:
            session.add(some_orm_instance)
            await session.commit()
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle helpers
# ─────────────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Create all tables defined in ``orchestrator.models``.
    Safe to call multiple times — uses ``CREATE TABLE IF NOT EXISTS``.
    """
    from orchestrator.models import Base  # local import avoids circular deps

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL: all tables created / verified.")


async def migrate_db() -> None:
    """
    Idempotent column additions for tables that already exist in production.

    Uses ``ADD COLUMN IF NOT EXISTS`` so it is safe to run on every startup.
    Does NOT drop or rename columns — only adds missing ones.
    Preserves all existing row data.
    """
    engine = _get_engine()
    # worker_nodes — add columns introduced by the dynamic node architecture
    migrations = [
        # Human-readable display name (NODE_N_NAME from .env)
        "ALTER TABLE worker_nodes ADD COLUMN IF NOT EXISTS name VARCHAR(128)",
        # Whether this node is in the active .env pool
        "ALTER TABLE worker_nodes ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE",
        # Scheduling priority (NODE_N_PRIORITY from .env, lower = higher priority)
        "ALTER TABLE worker_nodes ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 1",
        # Last time the health monitor probed this node
        "ALTER TABLE worker_nodes ADD COLUMN IF NOT EXISTS last_checked TIMESTAMP",
        # Last time the health monitor got a successful response
        "ALTER TABLE worker_nodes ADD COLUMN IF NOT EXISTS last_success TIMESTAMP",
        # sessions table
        """CREATE TABLE IF NOT EXISTS sessions (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(128) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            title VARCHAR(256) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_sessions_updated_at ON sessions (updated_at)",
        # messages table
        """CREATE TABLE IF NOT EXISTS messages (
            id VARCHAR(64) PRIMARY KEY,
            session_id VARCHAR(64) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            user_id VARCHAR(128) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL,
            content TEXT NOT NULL,
            request_id VARCHAR(64),
            routing_metadata TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_messages_session_id ON messages (session_id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_user_id ON messages (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages (created_at)",
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            await conn.execute(text(sql))
    logger.info("PostgreSQL: schema migrations applied.")



async def close_db() -> None:
    """Dispose the engine connection pool. Call at application shutdown."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("PostgreSQL engine disposed.")


async def ping_db() -> bool:
    """Return True if the database is reachable, False otherwise."""
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("PostgreSQL ping failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Row-level helpers used by orchestrator/persistence.py
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_user(session: AsyncSession, user_id: str) -> None:
    """
    Insert a users row if it doesn't already exist.
    Uses PostgreSQL ON CONFLICT DO NOTHING so it's idempotent.
    """
    from orchestrator.models import User

    stmt = (
        pg_insert(User)
        .values(user_id=user_id)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    await session.execute(stmt)
