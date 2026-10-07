"""Подключение к базе. Движок создаётся при первом обращении, а не при импорте:
тесты подменяют database_url и вызывают dispose()."""

from collections.abc import AsyncIterator

from sqlalchemy import func, inspect, select, text
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


# Колонки, добавленные после первой версии таблиц: create_all старые таблицы не
# трогает, поэтому досоздаём их сами. Схема пока только растёт — Alembic не нужен
_ADDED_COLUMNS = {
    "orders": {"customer_id": "INTEGER REFERENCES customers(id) ON DELETE SET NULL"},
}


def _add_missing_columns(conn) -> None:
    insp = inspect(conn)
    for table, columns in _ADDED_COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in columns.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


async def init_db() -> None:
    """Создаёт недостающие таблицы и колонки, заводит первого менеджера."""
    from .models import Base

    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    await _ensure_first_staff()


async def _ensure_first_staff() -> None:
    """Сотрудников ещё нет, а в .env задан MANAGE_PASSWORD — создаём менеджера."""
    from .lunch_order import now_local
    from .models import Staff
    from .security import hash_password

    if not settings.manage_password:
        return
    engine()
    async with _sessions() as session:
        if await session.scalar(select(func.count()).select_from(Staff)):
            return
        session.add(
            Staff(
                login=settings.manage_user,
                name="Менеджер",
                password_hash=hash_password(settings.manage_password),
                created_at=now_local(),
            )
        )
        await session.commit()


async def get_session() -> AsyncIterator[AsyncSession]:
    engine()
    async with _sessions() as session:
        yield session


async def dispose() -> None:
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = _sessions = None
