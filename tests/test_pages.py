"""Смоук-тест: страницы открываются, заявка на банкет проходит и проверяется."""

import re
from datetime import date, timedelta

import pytest

from app import banquet


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


def _leads_page(client) -> str:
    """Заявки видит менеджер в /manage/zayavki — там их и проверяем."""
    client.post("/manage/vhod", data={"login": "manager", "password": "secret"})
    return client.get("/manage/zayavki").text


def test_banquet_request_saved(client):
    r = client.post("/banket/zayavka", data=_good_form(), follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/banket/spasibo"
    page = _leads_page(client)
    assert 'href="tel:+79123456789"' in page
    assert "25 гостей" in page and "Банкет" in page


def test_banquet_request_errors_keep_input(client):
    r = client.post("/banket/zayavka", data=_good_form(phone="123", guests="99"))
    assert r.status_code == 422
    assert "Нужен номер" in r.text
    assert "от 1 до 35 гостей" in r.text
    assert 'value="Ольга"' in r.text
    assert 'class="m-order m-lead' not in _leads_page(client)


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
    assert r.text.count('class="week__slide') == 5
    assert 'id="galereya"' in r.text
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


def test_banquet_prefill_from_home_form(client):
    r = client.get("/banket?date=2030-05-20&guests=25&paket=svadba")
    assert 'value="2030-05-20"' in r.text
    assert 'value="25"' in r.text
    assert 'value="svadba" data-price="2100" checked' in r.text
    # Мусор в адресе не попадает в форму
    r = client.get("/banket?date=zavtra&guests=500")
    assert 'value="zavtra"' not in r.text and 'value="500"' not in r.text


def test_keytering_page_and_request(client, tmp_path):
    r = client.get("/keytering?format=shashlyk")
    assert r.status_code == 200
    assert 'value="shashlyk" checked' in r.text
    assert "Выездной" in r.text

    good = {
        "format": "furshet",
        "event_date": (date.today() + timedelta(days=10)).isoformat(),
        "guests": "40",
        "place": "Пермь, ул. Кировоградская, 1, офис",
        "name": "Андрей",
        "phone": "+7 912 000-11-22",
        "comment": "",
    }
    r = client.post("/keytering/zayavka", data=good, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/keytering/spasibo"
    page = _leads_page(client)
    assert "40 гостей" in page and 'href="tel:+79120001122"' in page
    assert "Фуршет" in page and "Кировоградская, 1, офис" in page
    assert client.get("/keytering/spasibo").status_code == 200

    r = client.post("/keytering/zayavka", data={**good, "guests": "2", "place": ""})
    assert r.status_code == 422
    assert "от 5 до 500 гостей" in r.text and "Куда привезти" in r.text


def test_nav_has_keytering(client):
    assert 'href="/keytering"' in client.get("/").text


def test_menu_page(client):
    from app.content import MENU

    r = client.get("/menu")
    assert r.status_code == 200
    assert r.text.count('class="pcat"') == len(MENU)
    assert "«Посикунчики» с мясом" in r.text
    # У каждого раздела есть свой рисунок пером, а у страницы — клякса
    sketch = client.get("/static/icons/sketch.svg").text
    for c in MENU:
        assert f'id="{c.slug}"' in sketch, c.slug
    assert client.get("/static/img/menu/splash.svg").status_code == 200
