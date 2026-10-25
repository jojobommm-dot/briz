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
    assert days[0]["open"] == {"delivery": True, "pickup": True, "hall": True}
    assert all(date.fromisoformat(d["date"]).weekday() < 5 for d in days)  # без выходных
    assert len(days) == lo.DAYS_AHEAD

    after = lo.order_days(at(12, 31))[0]["open"]
    assert after == {"delivery": False, "pickup": True, "hall": True}  # доставка — за час
    assert lo.cutoff("delivery").strftime("%H:%M") == "12:30"
    closed = {"delivery": False, "pickup": False, "hall": False}
    assert lo.order_days(at(13, 31))[0]["open"] == closed


def test_weekend_today_shown_closed():
    sunday = date(2026, 10, 11)
    days = lo.order_days(at(10, 0, day=sunday))
    assert days[0]["label"] == "Сегодня" and days[0]["menu"] is None
    assert not any(days[0]["open"].values())
    assert days[1]["label"] == "Завтра" and days[1]["open"]["delivery"]
    assert sum(1 for d in days if d["menu"]) == lo.DAYS_AHEAD


def test_today_slots_need_lead_time():
    # Доставка — минимум за час: в 11:10 окно 12:00 уже не успеть, 12:30 — да
    assert lo.order_days(at(11, 10))[0]["slots"]["delivery"] == lo.SLOTS["delivery"][1:]
    # Зал и самовывоз — за полчаса: в 12:40 к 13:00 не успеть, к 13:30 — да; завтра — всё время
    today = lo.order_days(at(12, 40))[0]
    assert today["slots"]["hall"] == ["13:30", "14:00"]
    assert today["slots"]["pickup"] == ["13:30", "14:00"]
    assert today["slots"]["delivery"] == []
    tomorrow = lo.order_days(at(12, 40))[1]
    assert tomorrow["slots"]["hall"] == lo.SLOTS["hall"]


def test_prices_follow_mode():
    full = lo.OPTIONS_BY_KIND["full"]
    assert lo.price(full, "delivery") == 390 and lo.price(full, "pickup") == 370
    salad = lo.OPTIONS_BY_KIND["salad"]
    assert lo.price(salad, "delivery") == 110 and lo.price(salad, "pickup") == 120
    assert lo.price(full, "hall") == 370  # в зале — цена кафе


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


def test_hall_order_to_time(client, morning):
    r = client.post(
        "/api/orders",
        json=order_payload(mode="hall", slot="13:00", address="что угодно", guests=3),
    )
    assert r.status_code == 200
    order = r.json()["order"]
    assert (
        order["address"] == ""
        and order["guests"] == 3
        and order["modeLabel"] == "В кафе ко времени"
    )
    assert order["total"] == 2 * 370 + 120
    assert [s["key"] for s in order["flow"]][-2:] == ["served", "done"]
    page = client.get(r.json()["url"]).text
    assert "стол на 3 гостей" in page


@pytest.mark.parametrize("guests", [0, 31, "много", None])
def test_hall_needs_guests(client, morning, guests):
    r = client.post("/api/orders", json=order_payload(mode="hall", slot="13:00", guests=guests))
    assert r.status_code == 422 and "guests" in r.json()["errors"]


def test_hall_slot_too_soon(client, monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: at(12, 40))
    r = client.post("/api/orders", json=order_payload(mode="hall", slot="13:00", guests=1))
    assert r.status_code == 422 and "не успеем" in r.json()["errors"]["slot"]
    r = client.post("/api/orders", json=order_payload(mode="hall", slot="13:30", guests=1))
    assert r.status_code == 200


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


def test_delivery_today_needs_an_hour(client, monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: at(11, 45))
    r = client.post("/api/orders", json=order_payload())  # окно 12:30–13:00
    assert r.status_code == 422 and "минимум 60 минут" in r.json()["errors"]["slot"]
    assert client.post("/api/orders", json=order_payload(slot="13:00–13:30")).status_code == 200
    monkeypatch.setattr(lo, "now_local", lambda: at(12, 45))
    r = client.post("/api/orders", json=order_payload(slot="13:30–14:00"))
    assert r.status_code == 422 and "до 12:30" in r.json()["errors"]["day"]
    # На завтра — можно
    tomorrow = (WEDNESDAY + timedelta(days=1)).isoformat()
    assert client.post("/api/orders", json=order_payload(day=tomorrow)).status_code == 200


def test_guest_cancel_only_while_new(client, morning):
    token = client.post("/api/orders", json=order_payload()).json()["token"]
    assert client.post(f"/api/orders/{token}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/orders/{token}/cancel").status_code == 409
    assert client.get("/api/orders/nope").status_code == 404
