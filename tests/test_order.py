"""Заказ обедов: экран, оформление, статусы, панель менеджера."""

import json
from datetime import date, datetime, timedelta

import pytest

from app import lunch_order as lo

# Среда 7 октября 2026: в среду в меню оливье, «Строганов» и бефстроганов
WEDNESDAY = date(2026, 10, 7)


def at(hour: int, minute: int = 0, day: date = WEDNESDAY) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)


@pytest.fixture
def morning(monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: at(9, 30))


def order_payload(**over):
    payload = {
        "mode": "delivery",
        "day": WEDNESDAY.isoformat(),
        "slot": "12:30–13:00",
        "name": "Ирина",
        "phone": "8 (912) 111-22-33",
        "address": "ул. Кировоградская, 5, офис 12",
        "comment": "",
        "items": [{"kind": "full", "qty": 2}, {"kind": "soup", "qty": 1}],
    }
    payload.update(over)
    return payload


def test_days_and_cutoff():
    days = lo.order_days(at(10, 59))
    assert days[0]["date"] == WEDNESDAY.isoformat() and days[0]["label"] == "Сегодня"
    assert days[0]["open"] == {"delivery": True, "pickup": True}
    assert all(date.fromisoformat(d["date"]).weekday() < 5 for d in days)  # без выходных
    assert len(days) == lo.DAYS_AHEAD

    after = lo.order_days(at(11, 0))[0]["open"]
    assert after == {"delivery": False, "pickup": True}  # доставка до 11:00, самовывоз дольше
    assert lo.order_days(at(14, 0))[0]["open"] == {"delivery": False, "pickup": False}


def test_prices_follow_mode():
    full = lo.OPTIONS_BY_KIND["full"]
    assert lo.price(full, "delivery") == 390 and lo.price(full, "pickup") == 370
    salad = lo.OPTIONS_BY_KIND["salad"]
    assert lo.price(salad, "delivery") == 110 and lo.price(salad, "pickup") == 120


def test_page_renders(client, morning):
    r = client.get("/zakaz")
    assert r.status_code == 200
    data = json.loads(r.text.split('id="order-data">')[1].split("</script>")[0])
    assert data["days"][0]["menu"]["main"].startswith("Бефстроганов из курицы")
    assert {o["kind"] for o in data["options"]} == {
        "full",
        "no_soup",
        "no_salad",
        "main",
        "soup",
        "salad",
    }


def test_create_order_and_status(client, morning):
    r = client.post("/api/orders", json=order_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    order = body["order"]
    assert order["total"] == 2 * 390 + 130  # цены доставки считает сервер
    assert order["status"] == "new" and order["canCancel"]
    assert order["items"][0]["details"].startswith("Оливье с ветчиной")
    assert order["number"] == 1

    page = client.get(body["url"])
    assert page.status_code == 200 and "Заказ №1" in page.text
    assert client.get(f"/api/orders/{body['token']}").json()["statusLabel"] == "Новый"


def test_server_ignores_client_prices(client, morning):
    r = client.post(
        "/api/orders", json=order_payload(items=[{"kind": "full", "qty": 1, "price": 1}], total=1)
    )
    assert r.json()["order"]["total"] == 390


def test_pickup_has_no_address_and_cafe_prices(client, morning):
    r = client.post(
        "/api/orders", json=order_payload(mode="pickup", slot="13:00", address="что угодно")
    )
    order = r.json()["order"]
    assert order["address"] == "" and order["total"] == 2 * 370 + 120


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"items": []}, "items"),
        ({"items": [{"kind": "pizza", "qty": 1}]}, "items"),
        ({"items": [{"kind": "full", "qty": 99}]}, "items"),
        ({"phone": "123"}, "phone"),
        ({"address": ""}, "address"),
        ({"slot": "03:00"}, "slot"),
        ({"day": "2026-10-10"}, "day"),  # суббота
        ({"mode": "drone"}, "mode"),
    ],
)
def test_validation(client, morning, over, field):
    r = client.post("/api/orders", json=order_payload(**over))
    assert r.status_code == 422
    assert field in r.json()["errors"]


def test_delivery_closed_after_eleven(client, monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: at(11, 5))
    r = client.post("/api/orders", json=order_payload())
    assert r.status_code == 422 and "до 11:00" in r.json()["errors"]["day"]
    # На завтра — можно
    tomorrow = (WEDNESDAY + timedelta(days=1)).isoformat()
    assert client.post("/api/orders", json=order_payload(day=tomorrow)).status_code == 200


def test_guest_cancel_only_while_new(client, morning):
    token = client.post("/api/orders", json=order_payload()).json()["token"]
    assert client.post(f"/api/orders/{token}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/orders/{token}/cancel").status_code == 409
    assert client.get("/api/orders/nope").status_code == 404


def test_manager_flow(client, morning):
    token = client.post("/api/orders", json=order_payload()).json()["token"]

    assert client.get("/manage/zakazy").status_code == 401
    assert client.get("/manage/zakazy", auth=("manager", "wrong")).status_code == 401

    auth = ("manager", "secret")
    page = client.get(f"/manage/zakazy?day={WEDNESDAY}", auth=auth)
    assert page.status_code == 200
    assert "Ирина" in page.text and "Курьер" not in page.text.split("m-order__bottom")[0]
    assert client.get("/manage/api/latest", auth=auth).json() == {"maxId": 1, "new": 1}

    for status in ("accepted", "cooking", "on_way", "done"):
        r = client.post(
            "/manage/zakazy/1/status", data={"status": status}, auth=auth, follow_redirects=False
        )
        assert r.status_code == 303
        assert client.get(f"/api/orders/{token}").json()["status"] == status

    # Чужой для доставки шаг не пройдёт
    assert (
        client.post("/manage/zakazy/1/status", data={"status": "ready"}, auth=auth).status_code
        == 400
    )


def test_manage_disabled_without_password(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "manage_password", "")
    assert client.get("/manage/zakazy", auth=("manager", "")).status_code == 503
