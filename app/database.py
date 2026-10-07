"""Подключение к базе. Движок создаётся при первом обращении, а не при импорте:
тесты подменяют database_url и вызывают dispose()."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings

_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    global _engine, _sessions
    if _engine is None:
        if settings.database_url.startswith("sqlite"):
            settings.data_root.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(settings.database_url)
        _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def init_db() -> None:
    """Создаёт недостающие таблицы. Миграций пока нет — схема только растёт."""
    from .models import Base

    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    engine()
    async with _sessions() as session:
        yield session


async def dispose() -> None:
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = _sessions = None
