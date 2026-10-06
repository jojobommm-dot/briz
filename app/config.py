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
    # Сюда до появления базы (шаг 2) складываются заявки на банкет
    data_root: Path = BASE_DIR / "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
