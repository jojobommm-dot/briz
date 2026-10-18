"""Адрес базы от хостинга превращается в понятный SQLAlchemy + asyncpg."""

import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Render
        ("postgres://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgresql://u:p@host:5432/db", "postgresql+asyncpg://u:p@host:5432/db"),
        # Neon: параметры libpq → ssl для asyncpg
        (
            "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@ep-x.eu-central-1.aws.neon.tech/neondb?ssl=require",
        ),
        ("postgresql+asyncpg://u@h/d", "postgresql+asyncpg://u@h/d"),
        ("sqlite+aiosqlite:///data/briz.db", "sqlite+aiosqlite:///data/briz.db"),
    ],
)
def test_database_url(raw, expected):
    assert Settings(database_url=raw).database_url == expected
