"""JSON для Android-приложения."""

from datetime import datetime

from app import lunch_order as lo


def test_content(client):
    data = client.get("/api/app/content").json()
    assert data["cafe"]["phone"] == "+73422837704"
    assert data["cafe"]["hours"][0] == {"days": "Пн–Чт, Вс", "time": "12:00–24:00"}
    salads = data["menu"][0]
    assert salads["title"] == "Салаты" and salads["dishes"][0]["price"] == 730
    images = [d["image"] for c in data["menu"] for d in c["dishes"] if d["image"]]
    assert images and all(i.startswith("/static/img/") for i in images)
    assert data["lunch"]["prices"][0] == {
        "title": "Полный комплекс",
        "inCafe": 370,
        "delivery": 390,
    }
    assert len(data["lunch"]["week"]) == 5
    assert [p["price"] for p in data["banquet"]["packages"]] == [1500, 1800, 2100]


def test_lunch(client, monkeypatch):
    monkeypatch.setattr(lo, "now_local", lambda: datetime(2026, 10, 7, 9, 30))  # среда
    data = client.get("/api/app/lunch").json()
    today = data["days"][0]
    assert today["label"] == "Сегодня" and today["open"]["delivery"]
    assert today["image"].startswith("/static/img/briz/week-")
    assert data["options"][0]["price"] == {"delivery": 390, "pickup": 370, "hall": 370}
    assert data["cutoff"]["delivery"] == "12:30"
