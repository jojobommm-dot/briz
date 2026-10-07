"""Кабинет гостя и кабинет менеджера: вход, заказы, адреса, кухня, доставка."""

from datetime import date, datetime

import pytest

from app import kitchen
from app import lunch_order as lo
from app.security import hash_password, login_throttle, verify_password

WEDNESDAY = date(2026, 10, 7)


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
    }
    payload.update(over)
    r = client.post("/api/orders", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def register(client, phone="89121112233", password="secret12", name="Ирина"):
    return client.post(
        "/kabinet/registraciya",
        data={"name": name, "phone": phone, "password": password, "next": "/kabinet"},
        follow_redirects=False,
    )


def test_password_hashing():
    h = hash_password("пароль-1")
    assert h.startswith("scrypt$") and verify_password("пароль-1", h)
    assert not verify_password("пароль-2", h) and not verify_password("x", "мусор")


# ---------- гость ----------


def test_cabinet_requires_login(client):
    r = client.get("/kabinet", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/kabinet/vhod?next=")
    assert client.get("/api/me").json() == {"loggedIn": False}


def test_register_login_logout(client):
    r = register(client)
    assert r.status_code == 303 and r.headers["location"] == "/kabinet"
    page = client.get("/kabinet")
    assert page.status_code == 200 and "Ирина" in page.text
    assert client.get("/api/me").json()["phone"] == "+79121112233"

    # Повторная регистрация того же номера
    client.post("/kabinet/vyhod")
    r = register(client, phone="+7 912 111 22 33")
    assert r.status_code == 422 and "уже зарегистрирован" in r.text

    assert (
        client.post("/kabinet/vhod", data={"phone": "89121112233", "password": "wrong"}).status_code
        == 401
    )
    r = client.post(
        "/kabinet/vhod",
        data={"phone": "8 (912) 111-22-33", "password": "secret12"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert client.get("/api/me").json()["loggedIn"] is True


def test_register_validation(client):
    r = register(client, phone="123", password="123", name="")
    assert r.status_code == 422
    for msg in ("Как к вам обращаться", "10–11 цифр", "не короче 6"):
        assert msg in r.text


def test_login_throttle(client):
    register(client)
    client.post("/kabinet/vyhod")
    for _ in range(5):
        client.post("/kabinet/vhod", data={"phone": "89121112233", "password": "wrong"})
    r = client.post("/kabinet/vhod", data={"phone": "89121112233", "password": "secret12"})
    assert r.status_code == 429


def test_open_redirect_blocked(client):
    register(client)
    client.post("/kabinet/vyhod")
    r = client.post(
        "/kabinet/vhod",
        data={"phone": "89121112233", "password": "secret12", "next": "//evil.example"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/kabinet"


def test_order_goes_to_cabinet_and_address_saved(client):
    register(client)
    o = order(client)
    order(client, address="ул. Кировоградская, 5, офис 12")  # тот же адрес — не дублируется
    order(client, mode="pickup", slot="13:00", address="")
    me = client.get("/api/me").json()
    assert me["addresses"] == ["ул. Кировоградская, 5, офис 12"]
    page = client.get("/kabinet")
    assert f"№{o['order']['number']}" in page.text and "Повторить" in page.text
    assert f"/zakaz?repeat={o['token']}" in page.text


def test_claim_orders_made_before_login(client):
    before = order(client)  # без кабинета, с телефона 8 912 111-22-33
    stranger = order(client, phone="89990000000")
    register(client)
    r = client.post("/api/me/claim", json={"tokens": [before["token"], stranger["token"], "nope"]})
    # Чужой телефон не привяжется, даже если ссылка на заказ известна
    assert r.json() == {"claimed": 1}
    assert f"№{before['order']['number']}" in client.get("/kabinet").text
    assert client.post("/api/me/claim", json={"tokens": [before["token"]]}).json() == {"claimed": 0}


def test_profile_and_password_change(client):
    register(client)
    client.post("/kabinet/profil", data={"name": "Ирина Петровна"})
    assert client.get("/api/me").json()["name"] == "Ирина Петровна"
    r = client.post(
        "/kabinet/parol", data={"old": "wrong", "new": "newpass1"}, follow_redirects=False
    )
    assert "bad-password" in r.headers["location"]
    client.post("/kabinet/parol", data={"old": "secret12", "new": "newpass1"})
    client.post("/kabinet/vyhod")
    assert (
        client.post(
            "/kabinet/vhod",
            data={"phone": "89121112233", "password": "newpass1"},
            follow_redirects=False,
        ).status_code
        == 303
    )


# ---------- менеджер ----------


def staff_login(client, login="manager", password="secret"):
    return client.post(
        "/manage/vhod",
        data={"login": login, "password": password, "next": "/manage/zakazy"},
        follow_redirects=False,
    )


def test_manage_requires_login(client):
    r = client.get("/manage/kuhnya", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/manage/vhod?next=")
    assert client.get("/manage/api/latest").status_code == 401
    assert staff_login(client, password="wrong").status_code == 401
    # Кука гостя не открывает кабинет менеджера
    register(client)
    assert client.get("/manage/zakazy", follow_redirects=False).status_code == 303


def test_manager_flow(client):
    token = order(client)["token"]
    assert staff_login(client).status_code == 303

    page = client.get(f"/manage/zakazy?day={WEDNESDAY}")
    assert page.status_code == 200 and "Ирина" in page.text
    assert client.get("/manage/api/latest").json() == {"maxId": 1, "new": 1}

    for status in ("accepted", "cooking", "on_way", "done"):
        r = client.post(
            "/manage/zakazy/1/status",
            data={"status": status, "back": "/manage/dostavka"},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"].startswith("/manage/dostavka")
        assert client.get(f"/api/orders/{token}").json()["status"] == status
    assert client.post("/manage/zakazy/1/status", data={"status": "ready"}).status_code == 400

    client.post("/manage/vyhod")
    assert client.get("/manage/zakazy", follow_redirects=False).status_code == 303


def test_kitchen_sheet(client):
    order(client)  # 2 полных + суп, доставка 12:30
    order(
        client,
        mode="pickup",
        slot="13:00",
        address="",
        items=[{"kind": "no_salad", "qty": 3}, {"kind": "salad", "qty": 1}],
    )
    cancelled = order(client, items=[{"kind": "full", "qty": 10}])
    client.post(f"/api/orders/{cancelled['token']}/cancel")
    staff_login(client)

    page = client.get(f"/manage/kuhnya?day={WEDNESDAY}")
    assert page.status_code == 200
    for text in (
        "Бефстроганов из курицы",
        "Греча с овощами",
        "к 12:30",
        "к 13:00",
        "Из чего складываются",
    ):
        assert text in page.text


def test_kitchen_math():
    from app.models import Order, OrderItem

    def mk(oid, mode, slot, status, items):
        return Order(id=oid, mode=mode, slot=slot, status=status,
                     items=[OrderItem(kind=k, title=lo.OPTIONS_BY_KIND[k].title, qty=q, price=0) for k, q in items])  # fmt: skip

    orders = [
        mk(1, "delivery", "12:00–12:30", "on_way", [("full", 2)]),
        mk(2, "pickup", "13:00", "new", [("no_salad", 3), ("salad", 1)]),
        mk(3, "delivery", "12:00–12:30", "cancelled", [("full", 50)]),
    ]
    sheet = kitchen.build(orders, WEDNESDAY)
    rows = {r.part: r for r in sheet.rows}
    assert rows["salad"].total == 3 and rows["soup"].total == 5 and rows["main"].total == 5
    assert rows["side"].total == rows["main"].total  # второе всегда с гарниром
    assert rows["soup"].sent == 2 and rows["soup"].left == 3  # заказ 1 уже у курьера
    assert rows["main"].by_time == {"12:00": 2, "13:00": 3}
    assert rows["soup"].amount == "1,25 л" and rows["salad"].amount == "300 г"
    assert sheet.packaging == {"soup": 5, "salad": 3, "main": 5, "cutlery": 5, "bags": 2}
    assert sheet.orders == 2 and sheet.waiting == 1
    full = next(c for c in sheet.combos if c["title"] == "Полный комплекс")
    assert full["parts"] == ["Салат", "Суп", "Второе", "Гарнир"] and full["qty"] == 2


def test_delivery_sheet(client):
    order(client)
    order(client, mode="pickup", slot="13:00", address="", phone="89990000000", name="Пётр")
    staff_login(client)
    page = client.get(f"/manage/dostavka?day={WEDNESDAY}")
    assert page.status_code == 200
    assert "12:30 · Доставка" in page.text and "13:00 · Самовывоз" in page.text
    assert "1 770 ₽" in page.text  # 910 доставка + 860 самовывоз по ценам кафе
