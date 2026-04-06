from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from app.config import get_settings

try:
    from sqlalchemy.ext.asyncio import (
        AsyncEngine,
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
except ModuleNotFoundError:
    AsyncEngine = Any  # type: ignore[misc,assignment]
    AsyncSession = Any  # type: ignore[misc,assignment]
    async_sessionmaker = None  # type: ignore[assignment]
    create_async_engine = None  # type: ignore[assignment]


def _require_sqlalchemy() -> None:
    if create_async_engine is None or async_sessionmaker is None:
        raise RuntimeError(
            "SQLAlchemy async dependencies are not installed. Run `pip install -e .[dev]` first."
        )


@lru_cache
def get_engine() -> AsyncEngine:
    _require_sqlalchemy()
    settings = get_settings()
    return create_async_engine(  # type: ignore[misc]
        settings.database_url_resolved,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> Any:
    _require_sqlalchemy()
    return async_sessionmaker(  # type: ignore[misc]
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def get_optional_db_session() -> AsyncIterator[AsyncSession | None]:
    try:
        session_factory = get_session_factory()
    except (ModuleNotFoundError, RuntimeError):
        yield None
        return

    async with session_factory() as session:
        yield session
