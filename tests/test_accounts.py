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
        # Здесь нарочно несколько заказов с одного номера — дубли проверяет test_guest.py
        "duplicate": "new",
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
    for msg in ("Как к вам обращаться", "нужен российский", "не короче 6"):
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
    stranger = order(client, phone="89990001122")
    register(client)
    # Заказ из этого же браузера с тем же телефоном переехал в кабинет сразу при регистрации,
    # заказ с чужим телефоном — нет, даже из того же браузера
    page = client.get("/kabinet").text
    assert f"№{before['order']['number']}" in page
    assert f"№{stranger['order']['number']}" not in page
    r = client.post("/api/me/claim", json={"tokens": [stranger["token"], "nope"]})
    assert r.json() == {"claimed": 0}


def test_claim_from_other_browser_needs_link(client):
    made = order(client)
    client.cookies.clear()  # другой браузер: метки гостя нет
    register(client)
    assert f"№{made['order']['number']}" not in client.get("/kabinet").text
    # Ссылка на заказ, запомненная в браузере, — второй признак
    assert client.post("/api/me/claim", json={"tokens": [made["token"]]}).json() == {"claimed": 1}
    assert f"№{made['order']['number']}" in client.get("/kabinet").text


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
    assert client.get("/manage/api/latest").json() == {
        "maxId": 1,
        "maxLead": 0,
        "maxBooking": 0,
        "lastEdit": "",
        "new": 1,
    }

    for status in ("accepted", "cooking", "on_way", "done"):
        r = client.post(
            "/manage/zakazy/1/status",
            data={"status": status, "back": "/manage/vydacha"},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"].startswith("/manage/vydacha")
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

    def mk(oid, mode, slot, status, items, guests=0):
        return Order(id=oid, mode=mode, slot=slot, status=status, guests=guests,
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
    assert sheet.hall == {"tables": 0, "guests": 0, "by_time": {}}


def test_kitchen_hall_needs_no_packaging():
    from app.models import Order, OrderItem

    hall = Order(id=1, mode="hall", slot="13:00", status="served", guests=3,
                 items=[OrderItem(kind="full", title="Полный комплекс", qty=3, price=0)])  # fmt: skip
    sheet = kitchen.build([hall], WEDNESDAY)
    rows = {r.part: r for r in sheet.rows}
    assert rows["soup"].hall == 3 and rows["soup"].sent == 3  # стол накрыт — с кухни ушло
    assert sheet.packaging == {"soup": 0, "salad": 0, "main": 0, "cutlery": 0, "bags": 0}
    assert sheet.hall == {"tables": 1, "guests": 3, "by_time": {"13:00": 1}}
    assert sheet.combos[0]["hall"] == 3


def test_handout_sheet(client):
    order(client)
    order(client, mode="pickup", slot="13:00", address="", phone="89990001122", name="Пётр")
    order(client, mode="hall", slot="13:00", address="", guests=2, name="Анна",
          items=[{"kind": "full", "qty": 2}])  # fmt: skip
    staff_login(client)
    # Старый адрес вкладки ведёт на новый
    r = client.get(f"/manage/dostavka?day={WEDNESDAY}", follow_redirects=False)
    assert r.headers["location"] == f"/manage/vydacha?day={WEDNESDAY}"

    page = client.get(f"/manage/vydacha?day={WEDNESDAY}").text
    assert "к 12:30" in page and "к 13:00" in page
    assert "Стол на 2 гостей к 13:00" in page
    assert "2 510 ₽" in page  # 910 доставка + 860 самовывоз + 740 в зале по ценам кафе
    # Самовывоз и зал к одному времени — в одной группе, сначала стойка, потом зал
    assert page.index("Пётр") < page.index("Анна")

    courier = client.get(f"/manage/vydacha?day={WEDNESDAY}&mode=delivery").text
    assert "Ирина" in courier and "Пётр" not in courier and "Анна" not in courier
    assert "910 ₽" in courier


def test_manage_poll_uses_latest_order_overall(client):
    # День без свежего заказа не должен считать его новым и перезагружаться по кругу
    order(client)
    staff_login(client)
    page = client.get("/manage/zakazy?day=2026-10-08").text
    assert 'data-max-id="1"' in page


def test_leads_flow(client):
    good = {
        "name": "Ольга",
        "phone": "8 912 345-67-89",
        "event_date": "2026-11-14",
        "guests": "21",
        "package": "prazdnik",
        "comment": "Юбилей мамы",
    }
    assert client.post("/banket/zayavka", data=good, follow_redirects=False).status_code == 303
    assert client.get("/manage/zayavki", follow_redirects=False).status_code == 303

    staff_login(client)
    assert client.get("/manage/api/latest").json()["maxLead"] == 1
    page = client.get("/manage/zayavki").text
    assert '<span class="m-count">1</span>' in page
    assert "сб, 14.11.2026" in page
    assert "21 гость" in page
    assert "Праздничный" in page
    assert "Юбилей мамы" in page

    r = client.post("/manage/zayavki/1/status", data={"status": "in_work"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/manage/zayavki#z1"
    assert 'class="m-count"' not in client.get("/manage/zayavki").text
    assert client.post("/manage/zayavki/1/status", data={"status": "lost"}).status_code == 400
    assert client.post("/manage/zayavki/9/status", data={"status": "done"}).status_code == 404

    client.post("/manage/zayavki/1/status", data={"status": "done"})
    page = client.get("/manage/zayavki").text
    assert "Открытых заявок нет" in page and "Договорились" in page
