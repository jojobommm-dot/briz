"""Стол ко времени: бронь, предзаказ, статус, вкладка менеджера, кабинет."""

import json
from datetime import date, datetime, timedelta

import pytest

from app import booking as bk
from app import lunch_order as lo
from app.content import MENU
from app.security import login_throttle

FRIDAY = date(2026, 10, 9)
SALAD = bk.dish_key(MENU[0].slug, MENU[0].dishes[0])  # «Бриз», 730 ₽
SOUP = bk.dish_key(MENU[0].slug, MENU[0].dishes[1])


def at(hour: int, minute: int = 0, day: date = FRIDAY) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)


@pytest.fixture(autouse=True)
def friday_noon(monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: at(12, 0))
    login_throttle.fails.clear()


def payload(**over):
    p = {
        "day": FRIDAY.isoformat(),
        "time": "19:00",
        "guests": 4,
        "name": "Ольга",
        "phone": "8 912 345-67-89",
        "comment": "У окна",
        "items": [{"key": SALAD, "qty": 2}, {"key": SOUP, "qty": 1}],
    }
    p.update(over)
    return p


def staff_login(client):
    return client.post(
        "/manage/vhod",
        data={"login": "manager", "password": "secret", "next": "/manage/stoly"},
        follow_redirects=False,
    )


def test_times_follow_hours_and_lead():
    # Пятница до 23:30, в будни — до 22:00; на сегодня — не ближе чем за час
    assert bk.all_times(FRIDAY)[-1] == "23:30"
    assert bk.all_times(FRIDAY + timedelta(days=3))[-1] == "22:00"  # понедельник
    assert bk.open_times(FRIDAY, at(12, 0))[0] == "13:00"
    assert bk.open_times(FRIDAY, at(23, 0)) == []
    days = bk.book_days(at(12, 0))
    assert len(days) == bk.DAYS_AHEAD and days[1]["label"] == "Завтра"
    assert days[1]["times"][0] == "12:00"  # суббота — тоже можно


def test_page_renders(client):
    r = client.get("/stol")
    assert r.status_code == 200
    data = json.loads(r.text.split('id="booking-data">')[1].split("</script>")[0])
    assert data["menu"][0]["dishes"][0]["key"] == SALAD
    assert data["days"][0]["times"][0] == "13:00"


def test_booking_with_preorder(client):
    r = client.post("/api/bookings", json=payload())
    assert r.status_code == 200, r.text
    b = r.json()["booking"]
    price = MENU[0].dishes[0].price * 2 + MENU[0].dishes[1].price
    assert b["total"] == price and b["guests"] == 4 and b["status"] == "new"
    assert [i["qty"] for i in b["items"]] == [2, 1]
    page = client.get(r.json()["url"]).text
    assert "стол на 4 человека" in page and "подадим к 19:00" in page


def test_booking_without_preorder(client):
    r = client.post("/api/bookings", json=payload(items=[], guests=5))
    b = r.json()["booking"]
    assert b["total"] == 0 and b["items"] == []
    assert "Без предзаказа" in client.get(r.json()["url"]).text


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"time": "12:30"}, "time"),  # уже не успеем: на сегодня — за час
        ({"time": "03:00"}, "time"),
        ({"day": (FRIDAY + timedelta(days=20)).isoformat()}, "day"),
        ({"day": "вчера"}, "day"),
        ({"guests": 13}, "guests"),
        ({"guests": 0}, "guests"),
        ({"phone": "123"}, "phone"),
        ({"name": ""}, "name"),
        ({"items": [{"key": "salaty/Пицца", "qty": 1}]}, "items"),
        ({"items": [{"key": SALAD, "qty": 99}]}, "items"),
    ],
)
def test_validation(client, over, field):
    r = client.post("/api/bookings", json=payload(**over))
    assert r.status_code == 422 and field in r.json()["errors"]


def test_guest_cancel_until_seated(client):
    token = client.post("/api/bookings", json=payload()).json()["token"]
    assert client.post(f"/api/bookings/{token}/cancel").json()["status"] == "cancelled"
    token = client.post("/api/bookings", json=payload()).json()["token"]
    staff_login(client)
    client.post("/manage/stoly/2/status", data={"status": "confirmed"})
    client.post("/manage/stoly/2/status", data={"status": "seated"})
    assert client.post(f"/api/bookings/{token}/cancel").status_code == 409


def test_manager_tab(client):
    client.post("/api/bookings", json=payload())
    client.post(
        "/api/bookings", json=payload(time="20:30", name="Пётр", items=[{"key": SALAD, "qty": 1}])
    )
    staff_login(client)
    assert client.get("/manage/api/latest").json()["maxBooking"] == 2

    page = client.get(f"/manage/stoly?day={FRIDAY}").text
    assert "Ольга" in page and "Пётр" in page and page.index("Ольга") < page.index("Пётр")
    salad = MENU[0].dishes[0].name
    assert f"<b>{salad}</b>" in page
    assert "к 19:00 — 2; к 20:30 — 1" in page  # предзаказ кухне по времени

    r = client.post("/manage/stoly/1/status", data={"status": "confirmed"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("#b1")
    assert "Стол подтверждён" in client.get(f"/manage/stoly?day={FRIDAY}").text
    assert client.post("/manage/stoly/1/status", data={"status": "zzz"}).status_code == 400


def test_booking_goes_to_cabinet(client):
    client.post(
        "/kabinet/registraciya",
        data={"name": "Ольга", "phone": "89123456789", "password": "secret12", "next": "/kabinet"},
    )
    client.post("/api/bookings", json=payload())
    page = client.get("/kabinet").text
    assert "Брони столов" in page and "стол на 4" in page
