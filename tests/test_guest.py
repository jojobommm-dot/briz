"""Гость без кабинета: долгая кука, «мои заказы», правка вместо второго заказа, перенос в кабинет."""

from datetime import date, datetime

import pytest

from app import lunch_order as lo
from app.guest import GUEST_COOKIE, GUEST_DAYS
from app.security import login_throttle

WEDNESDAY = date(2026, 10, 7)
FRIDAY = date(2026, 10, 9)


@pytest.fixture(autouse=True)
def morning(monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: datetime(2026, 10, 7, 9, 30))
    login_throttle.fails.clear()


def order_payload(**over):
    p = {
        "mode": "delivery",
        "day": WEDNESDAY.isoformat(),
        "slot": "12:30–13:00",
        "name": "Ирина",
        "phone": "8 912 111-22-33",
        "address": "ул. Кировоградская, 5, офис 12",
        "items": [{"kind": "full", "qty": 2}],
    }
    p.update(over)
    return p


def booking_payload(**over):
    p = {
        "day": FRIDAY.isoformat(),
        "time": "19:00",
        "guests": 4,
        "name": "Ирина",
        "phone": "8 912 111-22-33",
        "items": [],
    }
    p.update(over)
    return p


def staff_login(client):
    client.post(
        "/manage/vhod",
        data={"login": "manager", "password": "secret", "next": "/manage/zakazy"},
        follow_redirects=False,
    )


def test_order_sets_long_guest_cookie(client):
    r = client.post("/api/orders", json=order_payload())
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{GUEST_COOKIE}=") and f"Max-Age={GUEST_DAYS * 86400}" in cookie
    assert "HttpOnly" in cookie


def test_my_orders_by_cookie_or_link(client):
    made = client.post("/api/orders", json=order_payload()).json()
    booked = client.post("/api/bookings", json=booking_payload()).json()
    mine = client.get("/api/my").json()
    assert [o["token"] for o in mine["orders"]] == [made["token"]]
    assert [b["token"] for b in mine["bookings"]] == [booked["token"]]
    assert mine["orders"][0]["canEdit"] is True

    client.cookies.clear()  # другой браузер или кука потерялась
    assert client.get("/api/my").json() == {"orders": [], "bookings": []}
    # Ссылки, запомненные на телефоне, — запасной путь
    by_link = client.get(f"/api/my?tokens={made['token']},{booked['token']}").json()
    assert len(by_link["orders"]) == 1 and len(by_link["bookings"]) == 1


def test_my_orders_hide_closed(client):
    token = client.post("/api/orders", json=order_payload()).json()["token"]
    client.post(f"/api/orders/{token}/cancel")
    assert client.get("/api/my").json()["orders"] == []


def test_edit_order_instead_of_second(client):
    made = client.post("/api/orders", json=order_payload()).json()
    r = client.put(
        f"/api/orders/{made['token']}",
        json=order_payload(
            mode="pickup", slot="13:00", address="", items=[{"kind": "full", "qty": 3}]
        ),
    )
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["number"] == made["order"]["number"]  # тот же заказ, не новый
    assert o["mode"] == "pickup" and o["total"] == 3 * 370 and o["editedAt"] == "09:30"
    assert "Изменён в 09:30" in client.get(f"/zakaz/{made['token']}").text
    assert len(client.get("/api/my").json()["orders"]) == 1

    staff_login(client)
    assert client.get("/manage/api/latest").json()["lastEdit"].startswith("2026-10-07 09:30")
    assert "изменён гостем в 09:30" in client.get(f"/manage/zakazy?day={WEDNESDAY}").text


def test_edit_validates_and_locks(client):
    made = client.post("/api/orders", json=order_payload()).json()
    bad = client.put(f"/api/orders/{made['token']}", json=order_payload(items=[]))
    assert bad.status_code == 422 and "items" in bad.json()["errors"]

    staff_login(client)
    client.post(f"/manage/zakazy/{made['order']['number']}/status", data={"status": "accepted"})
    r = client.put(f"/api/orders/{made['token']}", json=order_payload())
    assert r.status_code == 409
    assert client.get(f"/api/orders/{made['token']}").json()["canEdit"] is False


def test_edit_closed_after_cutoff(client, monkeypatch):
    made = client.post("/api/orders", json=order_payload()).json()
    monkeypatch.setattr(lo, "now_local", lambda: datetime(2026, 10, 7, 12, 45))
    assert client.put(f"/api/orders/{made['token']}", json=order_payload()).status_code == 409


def test_edit_booking_needs_new_confirmation(client):
    made = client.post("/api/bookings", json=booking_payload()).json()
    staff_login(client)
    client.post(f"/manage/stoly/{made['booking']['number']}/status", data={"status": "confirmed"})
    r = client.put(f"/api/bookings/{made['token']}", json=booking_payload(time="20:00", guests=6))
    assert r.status_code == 200, r.text
    b = r.json()["booking"]
    assert b["time"] == "20:00" and b["guests"] == 6
    assert b["status"] == "new"  # время и число гостей поменялись — подтвердить заново
    assert "изменена гостем" in client.get(f"/manage/stoly?day={FRIDAY}").text

    client.post(f"/manage/stoly/{b['number']}/status", data={"status": "confirmed"})
    client.post(f"/manage/stoly/{b['number']}/status", data={"status": "seated"})
    assert client.put(f"/api/bookings/{made['token']}", json=booking_payload()).status_code == 409


def test_registration_pulls_guest_orders(client):
    order = client.post("/api/orders", json=order_payload()).json()
    booking = client.post("/api/bookings", json=booking_payload()).json()
    client.post(
        "/kabinet/registraciya",
        data={"name": "Ирина", "phone": "89121112233", "password": "secret12", "next": "/kabinet"},
    )
    page = client.get("/kabinet").text
    assert f"№{order['order']['number']}" in page
    assert "Брони столов" in page and f"№{booking['booking']['number']}" in page


def test_login_pulls_guest_orders(client):
    client.post(
        "/kabinet/registraciya",
        data={"name": "Ирина", "phone": "89121112233", "password": "secret12", "next": "/kabinet"},
    )
    client.post("/kabinet/vyhod")
    made = client.post("/api/orders", json=order_payload()).json()  # вышел и заказал как гость
    client.post("/kabinet/vhod", data={"phone": "89121112233", "password": "secret12"})
    assert f"№{made['order']['number']}" in client.get("/kabinet").text


# ---------- дубли по номеру телефона ----------


def test_same_phone_other_browser_is_asked(client):
    first = client.post("/api/orders", json=order_payload()).json()
    client.cookies.clear()  # другой браузер, тот же номер — записан иначе
    r = client.post("/api/orders", json=order_payload(phone="+7 (912) 111-22-33", name="Аня"))
    assert r.status_code == 409
    dup = r.json()["duplicate"]
    assert dup["number"] == first["order"]["number"] and dup["canReplace"] is True
    assert dup["phone"] == "+7 (912) ***-**-33"
    assert dup["token"] == ""  # чужому браузеру — ни ссылки, ни имени, ни адреса
    assert "Ирина" not in r.text and "Кировоградская" not in r.text
    # Состав и сумма — чтобы решить, заменять ли; телефон — только маской
    assert dup["items"] == [{"title": "Полный комплекс", "qty": 2}] and dup["total"] == 780
    assert "79121112233" not in r.text


def test_same_browser_gets_link_to_edit(client):
    first = client.post("/api/orders", json=order_payload()).json()
    r = client.post("/api/orders", json=order_payload(mode="pickup", slot="13:00", address=""))
    assert r.status_code == 409 and r.json()["duplicate"]["token"] == first["token"]
    # Ссылка, запомненная на телефоне, — тоже «свой»
    client.cookies.clear()
    r = client.post("/api/orders", json=order_payload(known=[first["token"]]))
    assert r.json()["duplicate"]["token"] == first["token"]


def test_replace_previous_order(client):
    first = client.post("/api/orders", json=order_payload()).json()
    client.cookies.clear()
    r = client.post(
        "/api/orders",
        json=order_payload(
            replace=first["order"]["number"], name="Аня", items=[{"kind": "soup", "qty": 1}]
        ),
    )
    assert r.status_code == 200, r.text
    o = r.json()["order"]
    assert o["number"] == first["order"]["number"] and o["name"] == "Аня" and o["total"] == 130
    assert client.get(f"/api/orders/{first['token']}").json()["name"] == "Аня"  # один заказ, не два


def test_replace_needs_same_phone_and_open_order(client):
    first = client.post("/api/orders", json=order_payload()).json()
    number = first["order"]["number"]
    r = client.post("/api/orders", json=order_payload(replace=number, phone="89121112244"))
    assert r.status_code == 409  # чужой номер — чужой заказ
    staff_login(client)
    client.post(f"/manage/zakazy/{number}/status", data={"status": "accepted"})
    client.cookies.clear()
    r = client.post("/api/orders", json=order_payload())
    assert r.status_code == 409 and r.json()["duplicate"]["canReplace"] is False
    assert client.post("/api/orders", json=order_payload(replace=number)).status_code == 409


def test_force_second_order_and_other_day(client):
    client.post("/api/orders", json=order_payload())
    r = client.post("/api/orders", json=order_payload(duplicate="new"))
    assert r.status_code == 200  # гость подтвердил: это другой заказ
    thursday = date(2026, 10, 8).isoformat()
    assert client.post("/api/orders", json=order_payload(day=thursday)).status_code == 200
    client.post(f"/api/orders/{r.json()['token']}/cancel")


def test_booking_duplicate_by_phone(client):
    first = client.post("/api/bookings", json=booking_payload()).json()
    client.cookies.clear()
    r = client.post("/api/bookings", json=booking_payload(phone="+79121112233", time="20:00"))
    assert r.status_code == 409
    dup = r.json()["duplicate"]
    assert dup["number"] == first["booking"]["number"] and dup["token"] == ""
    r = client.post(
        "/api/bookings", json=booking_payload(replace=dup["number"], time="20:00", guests=2)
    )
    assert r.status_code == 200 and r.json()["booking"]["time"] == "20:00"
    assert client.post("/api/bookings", json=booking_payload(duplicate="new")).status_code == 200
