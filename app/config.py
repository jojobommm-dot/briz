"""Настройки. Всё, что отличается между машиной разработчика и сервером,
живёт в .env и никогда не попадает в git."""

from functools import lru_cache
from pathlib import Path

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

    # --- кафе ---
    # Пермь живёт по екатеринбургскому времени (UTC+5): от него считаются
    # «сегодня» и «заказ до 11:00»
    timezone: str = "Asia/Yekaterinburg"

    # --- панель менеджера (/manage) ---
    # Пусто — панель выключена. Вход по логину и паролю (HTTP Basic)
    manage_user: str = "manager"
    manage_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
