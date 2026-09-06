"""Pytest fixtures for async database and service tests."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.models import Base
from src.services.order_service import OrderService


@pytest_asyncio.fixture
async def db_session():
    """Creates a clean in-memory async SQLite session for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def order_service(db_session: AsyncSession) -> OrderService:
    """Returns an OrderService connected to the in-memory test database."""
    return OrderService(db_session)
