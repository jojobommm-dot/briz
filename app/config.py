"""Настройки. Всё, что отличается между машиной разработчика и сервером,
живёт в .env и никогда не попадает в git."""

from functools import lru_cache
from pathlib import Path

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
    # Заявки на банкет и кейтеринг (пока файлами) и локальная база
    data_root: Path = BASE_DIR / "data"

    # --- база ---
    # Для разработки — SQLite в data/; на сервере — PostgreSQL:
    # postgresql+asyncpg://briz:пароль@localhost:5432/briz
    database_url: str = f"sqlite+aiosqlite:///{(BASE_DIR / 'data' / 'briz.db').as_posix()}"

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, url: str) -> str:
        # Хостинги (Render и др.) отдают postgres:// или postgresql:// —
        # SQLAlchemy нужен явный асинхронный драйвер
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url.removeprefix(prefix)
        return url

    # --- кафе ---
    # Пермь живёт по екатеринбургскому времени (UTC+5): от него считаются
    # «сегодня» и «заказ до 11:00»
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
