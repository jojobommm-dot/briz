"""Смоук-тест: страницы открываются, заявка на банкет проходит и проверяется."""

import json
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import banquet
from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_root", tmp_path)
    return TestClient(app)


@pytest.mark.parametrize(
    "path", ["/", "/menu", "/banket", "/obedy", "/kontakty", "/banket/spasibo"]
)
def test_pages_open(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "Бриз" in r.text


def test_static_and_health(client):
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/static/css/site.css").status_code == 200
    assert client.get("/static/manifest.webmanifest").status_code == 200


def test_404_page(client):
    r = client.get("/net-takoy")
    assert r.status_code == 404
    assert "Такой страницы нет" in r.text


def test_package_preselected_from_link(client):
    r = client.get("/banket?paket=svadba")
    assert 'value="svadba" data-price="2100" checked' in r.text


def _good_form(**over):
    form = {
        "name": "Ольга",
        "phone": "8 (912) 345-67-89",
        "event_date": (date.today() + timedelta(days=30)).isoformat(),
        "guests": "25",
        "package": "prazdnik",
        "comment": "Юбилей",
    }
    form.update(over)
    return form


def test_banquet_request_saved(client, tmp_path):
    r = client.post("/banket/zayavka", data=_good_form(), follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/banket/spasibo"
    saved = json.loads((tmp_path / "banquet_requests.jsonl").read_text(encoding="utf-8"))
    assert saved["phone"] == "+79123456789"
    assert saved["guests"] == 25


def test_banquet_request_errors_keep_input(client, tmp_path):
    r = client.post("/banket/zayavka", data=_good_form(phone="123", guests="99"))
    assert r.status_code == 422
    assert "Нужен номер" in r.text
    assert "от 1 до 35 гостей" in r.text
    assert 'value="Ольга"' in r.text
    assert not (tmp_path / "banquet_requests.jsonl").exists()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+7 912 345-67-89", "+79123456789"),
        ("89123456789", "+79123456789"),
        ("9123456789", "+79123456789"),
        ("12345", None),
        ("59123456789", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert banquet.normalize_phone(raw) == expected


def test_past_date_rejected():
    req, errors = banquet.validate(_good_form(event_date="2020-01-01"))
    assert req is None
    assert errors["event_date"] == "Эта дата уже прошла"


def test_home_blocks(client):
    r = client.get("/")
    # Слайдер, нумерованный список услуг и карусель блюд из content.py
    assert r.text.count('class="hero__slide') == 4
    assert "<h1" in r.text and r.text.count("<h1") == 1
    assert 'class="numbered__num">06<' in r.text
    assert "Карбонара" in r.text
    # Все картинки, на которые ссылается главная, на месте
    for src in set(re.findall(r"/static/img/[\w/.-]+", r.text)):
        assert client.get(src).status_code == 200, src


def test_lunch_real_prices(client):
    r = client.get("/obedy")
    assert "370 ₽" in r.text and "390 ₽" in r.text
    assert "до 11:00" in r.text


def test_pwa_files(client):
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert sw.headers["content-type"].startswith("application/javascript")
    assert sw.headers["cache-control"] == "no-cache"
    assert '"/offline"' in sw.text and "/static/css/site.css?v=" in sw.text

    m = client.get("/manifest.webmanifest")
    assert m.headers["content-type"].startswith("application/manifest+json")
    manifest = m.json()
    assert manifest["display"] == "standalone" and manifest["start_url"].startswith("/")
    # Всё, на что ссылается манифест, отдаётся
    files = [i["src"] for i in manifest["icons"]] + [s["src"] for s in manifest["screenshots"]]
    files += [i["src"] for sc in manifest["shortcuts"] for i in sc["icons"]]
    for src in files:
        assert client.get(src).status_code == 200, src
    assert any(i.get("purpose") == "maskable" for i in manifest["icons"])

    assert client.get("/offline").status_code == 200
    home = client.get("/").text
    assert 'rel="manifest" href="/manifest.webmanifest"' in home
    assert "apple-touch-icon" in home
