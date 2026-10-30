"""Рабочие вкладки Android-приложения: вход сотрудника и JSON тех же вкладок, что /manage."""

from datetime import date, datetime

import pytest

from app import booking as bk
from app import lunch_order as lo
from app.content import MENU
from app.security import login_throttle

WEDNESDAY = date(2026, 10, 7)
FRIDAY = date(2026, 10, 9)
API = "/api/app/staff"


@pytest.fixture(autouse=True)
def morning(monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: datetime(2026, 10, 7, 9, 30))
    login_throttle.fails.clear()


def order(client, **over):
    payload = {
        "mode": "delivery",
        "day": WEDNESDAY.isoformat(),
        "slot": "12:30–13:00",
        "name": "Ирина",
        "phone": "8 912 111-22-33",
        "address": "ул. Кировоградская, 5, офис 12",
        "items": [{"kind": "full", "qty": 2}, {"kind": "soup", "qty": 1}],
        "duplicate": "new",
    }
    payload.update(over)
    r = client.post("/api/orders", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def login(client, password="secret"):
    return client.post(f"{API}/login", json={"login": "manager", "password": password})


def test_login_and_session(client):
    assert client.get(f"{API}/me").status_code == 401
    assert client.get(f"{API}/orders").json() == {"error": "Нужно войти"}

    r = login(client, "wrong")
    assert r.status_code == 401 and r.json() == {"error": "Неверный логин или пароль"}
    r = login(client)
    assert r.status_code == 200 and r.json() == {
        "name": "Менеджер",
        "login": "manager",
        "role": "manager",
    }
    # Каждый заход в рабочие вкладки продлевает вход
    me = client.get(f"{API}/me")
    assert me.status_code == 200 and "briz_staff=" in me.headers["set-cookie"]

    client.post(f"{API}/logout")
    assert client.get(f"{API}/me").status_code == 401


def test_login_throttle_shared_with_site(client):
    for _ in range(5):
        login(client, "wrong")
    r = login(client)
    assert r.status_code == 429 and "Подождите" in r.json()["error"]


def test_orders_tab_and_status(client):
    order(client)
    order(
        client,
        mode="pickup",
        slot="13:00",
        address="",
        name="Пётр",
        items=[{"kind": "full", "qty": 1}],
    )
    login(client)

    data = client.get(f"{API}/orders?day={WEDNESDAY}").json()
    assert data["day"] == "2026-10-07" and data["days"][0]["label"] == "Сегодня"
    assert data["count"] == 2 and data["waiting"] == 2
    assert data["revenue"] == sum(o["total"] for o in data["orders"])
    assert [d["left"] for d in data["dishes"]] == [3, 4, 3, 3]  # салат, суп, второе, гарнир
    first = data["orders"][0]  # новые сверху
    assert first["name"] == "Пётр" and first["modeLabel"] == "Самовывоз"
    assert first["next"] == "accepted" and first["nextLabel"] == "Принят" and first["canCancel"]
    ira = data["orders"][1]
    assert ira["phone"] == "+79121112233" and ira["address"].startswith("ул. Кировоградская")
    assert ira["items"][0]["qty"] == 2 and ira["items"][0]["title"] == "Полный комплекс"

    for status, nxt in (("accepted", "cooking"), ("cooking", "on_way"), ("on_way", "done")):
        r = client.post(f"{API}/orders/{ira['id']}/status", json={"status": status})
        assert r.status_code == 200 and r.json()["status"] == status and r.json()["next"] == nxt
    # Шаг не из пути доставки, неизвестный заказ
    assert (
        client.post(f"{API}/orders/{ira['id']}/status", json={"status": "ready"}).status_code == 400
    )
    assert client.post(f"{API}/orders/99/status", json={"status": "accepted"}).status_code == 404

    r = client.post(f"{API}/orders/{first['id']}/status", json={"status": "cancelled"}).json()
    assert r["statusLabel"] == "Отменён" and r["next"] is None and not r["canCancel"]
    assert client.get(f"{API}/orders?day={WEDNESDAY}").json()["count"] == 1


def test_kitchen_tab(client):
    order(client)  # 2 полных + суп, доставка 12:30
    order(client, mode="pickup", slot="13:00", address="",
          items=[{"kind": "no_salad", "qty": 3}, {"kind": "salad", "qty": 1}])  # fmt: skip
    login(client)

    data = client.get(f"{API}/kitchen?day={WEDNESDAY}").json()
    assert data["count"] == 2 and data["times"] == ["12:30", "13:00"]
    soup = next(d for d in data["dishes"] if d["label"] == "Суп")
    assert soup["total"] == 6 and soup["byTime"] == [3, 3] and soup["amount"] == "1,5 л"
    assert soup["delivery"] == 3 and soup["pickup"] == 3 and soup["portion"] == "250 мл"
    assert [c["title"] for c in data["combos"]][0] == "Полный комплекс"
    assert data["packaging"]["bags"] == 2 and data["hall"] == {
        "tables": 0,
        "guests": 0,
        "byTime": [],
    }


def test_handout_tab(client):
    order(client)
    order(client, mode="pickup", slot="13:00", address="", phone="89990001122", name="Пётр")
    order(client, mode="hall", slot="13:00", address="", guests=2, name="Анна",
          items=[{"kind": "full", "qty": 2}])  # fmt: skip
    login(client)

    data = client.get(f"{API}/handout?day={WEDNESDAY}").json()
    assert data["toCollect"] == 2510  # как на сайте: 910 + 860 + 740
    assert [m["count"] for m in data["modes"]] == [3, 1, 1, 1] and data["modes"][0][
        "label"
    ] == "Все"
    assert [g["time"] for g in data["groups"]] == ["12:30", "13:00"]
    # Самовывоз и зал к одному времени — сначала стойка, потом зал
    assert [o["name"] for o in data["groups"][1]["orders"]] == ["Пётр", "Анна"]

    courier = client.get(f"{API}/handout?day={WEDNESDAY}&mode=delivery").json()
    assert courier["mode"] == "delivery" and courier["toCollect"] == 910
    assert [o["name"] for g in courier["groups"] for o in g["orders"]] == ["Ирина"]


def test_bookings_tab(client, monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: datetime(2026, 10, 9, 12, 0))
    salad = bk.dish_key(MENU[0].slug, MENU[0].dishes[0])
    booking = {
        "day": FRIDAY.isoformat(),
        "time": "19:00",
        "guests": 4,
        "name": "Ольга",
        "phone": "8 912 345-67-89",
        "items": [{"key": salad, "qty": 2}],
        "duplicate": "new",
    }
    client.post("/api/bookings", json=booking)
    client.post("/api/bookings", json={**booking, "time": "20:30", "name": "Пётр", "guests": 2,
                                       "items": [{"key": salad, "qty": 1}]})  # fmt: skip
    login(client)

    data = client.get(f"{API}/bookings?day={FRIDAY}").json()
    assert len(data["days"]) == bk.DAYS_AHEAD and data["days"][1]["label"] == "Завтра"
    assert data["count"] == 2 and data["waiting"] == 2 and data["guests"] == 6
    assert data["capacity"] == 35
    assert data["pre"] == [
        {
            "name": MENU[0].dishes[0].name,
            "category": MENU[0].title,
            "qty": 3,
            "byTime": [{"time": "19:00", "qty": 2}, {"time": "20:30", "qty": 1}],
        }
    ]
    olga = data["bookings"][0]
    assert olga["name"] == "Ольга" and olga["nextLabel"] == "Стол подтверждён"

    r = client.post(f"{API}/bookings/{olga['id']}/status", json={"status": "confirmed"}).json()
    assert r["statusLabel"] == "Стол подтверждён" and r["next"] == "seated"
    assert (
        client.post(f"{API}/bookings/{olga['id']}/status", json={"status": "zzz"}).status_code
        == 400
    )


def test_leads_tab_and_latest(client):
    good = {
        "name": "Ольга",
        "phone": "8 912 345-67-89",
        "event_date": "2026-11-14",
        "guests": "21",
        "package": "prazdnik",
        "comment": "Юбилей мамы",
    }
    client.post("/banket/zayavka", data=good, follow_redirects=False)
    order(client)
    login(client)

    assert client.get(f"{API}/latest").json() == {
        "maxId": 1,
        "maxLead": 1,
        "maxBooking": 0,
        "lastEdit": "",
        "newOrders": 1,
        "newBookings": 0,
        "newLeads": 1,
    }
    lead = client.get(f"{API}/leads").json()["open"][0]
    assert lead["event"] == "сб, 14.11.2026" and lead["guests"] == "21 гость"
    assert lead["option"] == "Праздничный" and lead["kindLabel"] == "Банкет"
    assert [a["status"] for a in lead["actions"]] == ["in_work", "done", "declined"]

    r = client.post(f"{API}/leads/{lead['id']}/status", json={"status": "in_work"}).json()
    assert [a["label"] for a in r["actions"]] == ["Договорились", "Отказ"]
    assert (
        client.post(f"{API}/leads/{lead['id']}/status", json={"status": "lost"}).status_code == 400
    )
    assert client.post(f"{API}/leads/9/status", json={"status": "done"}).status_code == 404

    client.post(f"{API}/leads/{lead['id']}/status", json={"status": "done"})
    board = client.get(f"{API}/leads").json()
    assert board["open"] == [] and board["closed"][0]["actions"][0]["label"] == "Вернуть в работу"
    assert client.get(f"{API}/latest").json()["newLeads"] == 0
