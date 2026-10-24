import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Клиент со своей временной базой и папкой заявок на каждый тест."""
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(
        settings, "database_url", f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}"
    )
    monkeypatch.setattr(settings, "manage_password", "secret")
    # Тесты не должны зависеть от .env машины: с https-адресом куки входа ставятся
    # с флагом Secure, а тестовый клиент ходит по http и их не возвращает
    monkeypatch.setattr(settings, "base_url", "http://testserver")
    with TestClient(app) as c:  # с lifespan: создаются таблицы
        yield c
