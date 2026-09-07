"""Asynchronous database engine, session factory, and SQLite WAL configuration."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.database.models import Base
from src.utils.logger import logger

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(database_url: str) -> AsyncEngine:
    """Creates or returns the cached AsyncEngine configured for SQLite WAL mode."""
    global _engine
    if _engine is None:
        # Ensure parent directory exists for file-based sqlite
        if database_url.startswith("sqlite+aiosqlite:///"):
            path = database_url.replace("sqlite+aiosqlite:///", "")
            if path and not path.startswith(":memory:"):
                dir_path = os.path.dirname(path)
                if dir_path:
                    os.makedirs(dir_path, exist_ok=True)

        _engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
        )

        # Set SQLite PRAGMAs for performance, concurrency, and durability
        if "sqlite" in database_url:
            @event.listens_for(_engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.close()

    return _engine


def get_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Returns the configured session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine(database_url)
        _session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def init_db(database_url: str) -> None:
    """Initializes the database schema."""
    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in database_url:
            def migrate_sqlite(sync_conn):
                cursor = sync_conn.connection.cursor()
                cursor.execute("PRAGMA table_info(blocked_users);")
                cols = [row[1] for row in cursor.fetchall()]
                if cols and "username" not in cols:
                    cursor.execute("ALTER TABLE blocked_users ADD COLUMN username VARCHAR(64);")
                cursor.close()
            await conn.run_sync(migrate_sqlite)
    logger.info("Database initialized successfully with WAL mode enabled.")


async def close_db() -> None:
    """Disposes the engine connection pool."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine connections closed.")


@asynccontextmanager
async def get_session(database_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager providing an isolated database session."""
    factory = get_session_factory(database_url)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
