"""Стол ко времени: бронь столика с предзаказом из основного меню.

Гость выбирает день, время и сколько человек; по желанию — блюда из меню,
их подадут к приходу. Оплата в кафе. Менеджер подтверждает бронь звонком
или кнопкой во вкладке «Столы».

Сознательные допущения, которые надо сверить с кафе:
- бронь — с 12:00 и не позже чем за два часа до закрытия (LAST_TIME);
- на сегодня — не ближе чем за час (MIN_LEAD): кухне нужно успеть с предзаказом;
- стол — до 12 человек, больше — это банкет (MAX_GUESTS);
- бронируем на две недели вперёд (DAYS_AHEAD).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from . import lunch_order as lo
from .banquet import PHONE_ERROR, normalize_phone
from .content import MENU, Dish

FIRST_TIME = time(12, 0)
# Последнее время брони по дням недели (пн = 0): кафе в пт и сб открыто до 02:00
LAST_TIME = {0: time(22, 0), 1: time(22, 0), 2: time(22, 0), 3: time(22, 0),
             4: time(23, 30), 5: time(23, 30), 6: time(22, 0)}  # fmt: skip
STEP = timedelta(minutes=30)
MIN_LEAD = timedelta(hours=1)
DAYS_AHEAD = 14
MAX_GUESTS = 12
MAX_QTY = 20  # одного блюда

GUEST_CAN_CANCEL = ("new", "confirmed")  # пришёл — отменять уже нечего


def can_edit(status: str, day: date, slot: str, now: datetime) -> bool:
    """Гость меняет бронь сам, пока не пришёл и до неё не меньше MIN_LEAD."""
    return status in GUEST_CAN_CANCEL and slot in open_times(day, now)


def dish_key(category: str, dish: Dish) -> str:
    """Ключ блюда в заказе: раздел + название. Индекс не годится — меню меняется."""
    return f"{category}/{dish.name}"


DISHES: dict[str, tuple[str, Dish]] = {
    dish_key(c.slug, d): (c.title, d) for c in MENU for d in c.dishes
}


def all_times(day: date) -> list[str]:
    t = datetime.combine(day, FIRST_TIME)
    last = datetime.combine(day, LAST_TIME[day.weekday()])
    out = []
    while t <= last:
        out.append(t.strftime("%H:%M"))
        t += STEP
    return out


def open_times(day: date, now: datetime) -> list[str]:
    """Какое время ещё можно выбрать: на сегодня — не ближе MIN_LEAD."""
    if day < now.date() or day > now.date() + timedelta(days=DAYS_AHEAD - 1):
        return []
    return [
        t for t in all_times(day) if datetime.combine(day, time.fromisoformat(t)) - now >= MIN_LEAD
    ]


def book_days(now: datetime) -> list[dict]:
    days = []
    for i in range(DAYS_AHEAD):
        d = now.date() + timedelta(days=i)
        days.append(
            {
                "date": d.isoformat(),
                "label": lo.day_label(d, now.date()),
                "short": f"{lo.WEEKDAYS[d.weekday()]}, {d.day} {lo.MONTHS[d.month - 1]}",
                "times": open_times(d, now),
            }
        )
    return days


def page_data(now: datetime) -> dict:
    return {
        "days": book_days(now),
        "menu": [
            {
                "slug": c.slug,
                "title": c.title,
                "dishes": [
                    {
                        "key": dish_key(c.slug, d),
                        "name": d.name,
                        "price": d.price,
                        "weight": d.weight,
                        "note": d.note,
                    }
                    for d in c.dishes
                ],
            }
            for c in MENU
        ],
        "maxGuests": MAX_GUESTS,
        "maxQty": MAX_QTY,
    }


@dataclass
class BookingDraft:
    day: date
    time: str
    guests: int
    name: str
    phone: str
    comment: str
    items: list[tuple[str, str, Dish, int]]  # ключ, раздел, блюдо, сколько

    @property
    def total(self) -> int:
        return sum(d.price * qty for _, _, d, qty in self.items)


def validate(payload: dict, now: datetime) -> tuple[BookingDraft | None, dict[str, str]]:
    errors: dict[str, str] = {}

    try:
        day = date.fromisoformat(str(payload.get("day", "")))
    except ValueError:
        day = None
    slot = str(payload.get("time", ""))
    if day is None:
        errors["day"] = "Выберите день"
    elif not now.date() <= day < now.date() + timedelta(days=DAYS_AHEAD):
        errors["day"] = f"Бронируем на {DAYS_AHEAD} дней вперёд — дальше позвоните, договоримся"
    elif slot not in all_times(day):
        errors["time"] = "Выберите время"
    elif slot not in open_times(day, now):
        errors["time"] = f"На {slot} уже не успеем — бронь не позже чем за час"

    try:
        guests = int(payload.get("guests", 0))
    except (TypeError, ValueError):
        guests = 0
    if not 1 <= guests <= MAX_GUESTS:
        errors["guests"] = f"Стол — от 1 до {MAX_GUESTS} человек; больше — это банкет"

    name = str(payload.get("name", "")).strip()
    if not 2 <= len(name) <= 80:
        errors["name"] = "Как к вам обращаться?"

    phone = normalize_phone(str(payload.get("phone", "")))
    if phone is None:
        errors["phone"] = PHONE_ERROR

    items = []
    raw = payload.get("items")
    for it in raw if isinstance(raw, list) else []:
        key = str(it.get("key", "")) if isinstance(it, dict) else ""
        found = DISHES.get(key)
        try:
            qty = int(it.get("qty", 0))
        except (TypeError, ValueError, AttributeError):
            qty = 0
        if found is None or not 1 <= qty <= MAX_QTY:
            errors["items"] = "В предзаказе что-то не так — обновите страницу"
            break
        items.append((key, found[0], found[1], qty))

    comment = re.sub(r"\s+", " ", str(payload.get("comment", ""))).strip()[:500]

    if errors:
        return None, errors
    return BookingDraft(day, slot, guests, name, phone, comment, items), {}
