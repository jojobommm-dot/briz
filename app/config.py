"""Настройки. Всё, что отличается между машиной разработчика и сервером,
живёт в .env и никогда не попадает в git."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Бриз"
    debug: bool = False
    base_url: str = "https://example.ru"  # без слэша на конце

    static_root: Path = BASE_DIR / "static"
    templates_root: Path = BASE_DIR / "templates"
    # Локальная база SQLite (на сервере — PostgreSQL)
    data_root: Path = BASE_DIR / "data"

    # --- база ---
    # Для разработки — SQLite в data/; на сервере — PostgreSQL:
    # postgresql+asyncpg://briz:пароль@localhost:5432/briz
    database_url: str = f"sqlite+aiosqlite:///{(BASE_DIR / 'data' / 'briz.db').as_posix()}"

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, url: str) -> str:
        # Хостинги (Render, Neon) отдают postgres:// или postgresql:// —
        # SQLAlchemy нужен явный асинхронный драйвер
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url.removeprefix(prefix)
        if not url.startswith("postgresql+asyncpg://"):
            return url
        # Neon дописывает ?sslmode=require&channel_binding=require — это параметры
        # libpq, asyncpg их не знает и падает. Шифрование у него задаётся ssl=
        base, _, query = url.partition("?")
        params = dict(parse_qsl(query))
        params.pop("channel_binding", None)
        if "sslmode" in params:
            params.setdefault("ssl", params.pop("sslmode"))
        return f"{base}?{urlencode(params)}" if params else base

    # --- кафе ---
    # Пермь живёт по екатеринбургскому времени (UTC+5): от него считаются
    # «сегодня» и до скольки ещё можно заказать
    timezone: str = "Asia/Yekaterinburg"

    # --- вход: гости и сотрудники ---
    # Подпись кук сессий. На сервере обязательно своя: openssl rand -hex 32
    secret_key: str = "dev-only-change-me"
    # Первый менеджер: если сотрудников в базе нет, при запуске создаётся
    # этот логин с этим паролем. Остальных — tools/staff.py
    manage_user: str = "manager"
    manage_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
