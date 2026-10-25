"""Заказ комплексных обедов: что можно заказать, на какой день, почём.

Три способа получить обед:
- доставка — привозим в офис к получасовому окну;
- самовывоз — забирают в кафе с собой;
- в кафе ко времени — гость заказывает заранее, к его приходу обед уже на столе.

Цены — с афиш кафе (см. content.LUNCH); самовывоз и обед в зале — по цене кафе.
Сознательные допущения, которые надо сверить с кафе:
- на сегодня принимаем не позже чем за час до начала окна доставки и за полчаса
  до самовывоза или прихода в зал (MIN_LEAD) — кухне и курьеру нужно успеть;
  отсюда последний заказ на сегодня: доставка до 12:30, самовывоз и зал до 13:30;
- слоты — по полчаса с 12:00 до 14:00;
- оплата при получении (онлайн-оплата — следующим шагом).
Всё это — константы ниже, меняются в одном месте.
"""

import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .banquet import normalize_phone
from .config import settings
from .content import LUNCH, WEEK_IMAGES


@dataclass(frozen=True)
class Option:
    kind: str
    title: str
    parts: tuple[str, ...]  # из каких блюд дня состоит
    price_row: int  # строка LUNCH["prices"]


OPTIONS = [
    Option("full", "Полный комплекс", ("salad", "soup", "main"), 0),
    Option("no_soup", "Салат и второе", ("salad", "main"), 1),
    Option("no_salad", "Суп и второе", ("soup", "main"), 1),
    Option("main", "Второе с гарниром", ("main",), 2),
    Option("soup", "Суп", ("soup",), 3),
    Option("salad", "Салат", ("salad",), 4),
]
OPTIONS_BY_KIND = {o.kind: o for o in OPTIONS}

MODES = {"delivery": "Доставка", "pickup": "Самовывоз", "hall": "В кафе ко времени"}
SLOTS = {
    "delivery": ["12:00–12:30", "12:30–13:00", "13:00–13:30", "13:30–14:00"],
    "pickup": ["12:00", "12:30", "13:00", "13:30", "14:00"],
    "hall": ["12:00", "12:30", "13:00", "13:30", "14:00"],
}
# На сегодня — не ближе, чем за столько до выбранного времени
MIN_LEAD = {
    "delivery": timedelta(hours=1),
    "pickup": timedelta(minutes=30),
    "hall": timedelta(minutes=30),
}
MAX_GUESTS = 30  # столик в зале; больше — это банкет
DAYS_AHEAD = 5  # рабочих дней в выборе
MAX_QTY = 50  # одной позиции; больше — это уже кейтеринг

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]  # fmt: skip


def now_local() -> datetime:
    """Местное время Перми без часового пояса — так оно и хранится в базе."""
    return datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)


def price(option: Option, mode: str) -> int:
    _, in_cafe, delivery = LUNCH["prices"][option.price_row]
    return delivery if mode == "delivery" else in_cafe


def menu_for(day: date) -> dict | None:
    """Блюда дня; в выходные обедов нет."""
    if day.weekday() >= len(LUNCH["week"]):
        return None
    _, salad, soup, main, side = LUNCH["week"][day.weekday()]
    return {"salad": salad, "soup": soup, "main": f"{main}, {side.lower()}"}


def dishes_for(day: date) -> dict | None:
    """Блюда дня по отдельности, гарнир — отдельно от второго (для кухни)."""
    if day.weekday() >= len(LUNCH["week"]):
        return None
    _, salad, soup, main, side = LUNCH["week"][day.weekday()]
    return {"salad": salad, "soup": soup, "main": main, "side": side}


def details(option: Option, day: date) -> str:
    menu = menu_for(day) or {}
    return " · ".join(menu[p] for p in option.parts if p in menu)


def slot_start(slot: str) -> time:
    """«12:30–13:00» → 12:30: к этому времени обед должен быть готов."""
    return time.fromisoformat(slot.split("–")[0])


def open_slots(day: date, mode: str, now: datetime) -> list[str]:
    """Какое время ещё можно выбрать: на сегодня — не ближе MIN_LEAD."""
    if menu_for(day) is None or day < now.date():
        return []
    if day > now.date():
        return list(SLOTS[mode])
    return [s for s in SLOTS[mode] if datetime.combine(day, slot_start(s)) - now >= MIN_LEAD[mode]]


def cutoff(mode: str) -> time:
    """До скольки принимаем заказ на сегодня: последнее время минус MIN_LEAD."""
    last = datetime.combine(date.min, slot_start(SLOTS[mode][-1]))
    return (last - MIN_LEAD[mode]).time()


def is_open(day: date, mode: str, now: datetime) -> bool:
    return bool(open_slots(day, mode, now))


def day_label(day: date, today: date) -> str:
    if day == today:
        return "Сегодня"
    if day == today + timedelta(days=1):
        return "Завтра"
    return WEEKDAYS_FULL[day.weekday()]


def order_days(now: datetime) -> list[dict]:
    """Ближайшие рабочие дни для выбора. «Сегодня» — всегда первым: в выходной оно
    видно неактивным с пояснением, иначе гость не понимает, куда делся сегодняшний день."""
    days, d = [], now.date()
    if menu_for(d) is None:
        days.append(
            {
                "date": d.isoformat(),
                "label": "Сегодня",
                "short": f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}",
                "open": {m: False for m in MODES},
                "slots": {m: [] for m in MODES},
                "menu": None,
                "image": None,
            }
        )
        d += timedelta(days=1)
    while sum(1 for x in days if x["menu"]) < DAYS_AHEAD:
        if menu_for(d) is not None:
            days.append(
                {
                    "date": d.isoformat(),
                    "label": day_label(d, now.date()),
                    "short": f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}",
                    "open": {m: is_open(d, m, now) for m in MODES},
                    "slots": {m: open_slots(d, m, now) for m in MODES},
                    "menu": menu_for(d),
                    "image": WEEK_IMAGES[d.weekday()],
                }
            )
        d += timedelta(days=1)
    return days


def page_data(now: datetime) -> dict:
    """Всё, что нужно экрану заказа: дни, варианты с ценами, слоты, время приёма."""
    return {
        "days": order_days(now),
        "options": [
            {
                "kind": o.kind,
                "title": o.title,
                "parts": list(o.parts),
                "price": {m: price(o, m) for m in MODES},
            }
            for o in OPTIONS
        ],
        "modes": MODES,
        "slots": SLOTS,
        "cutoff": {m: cutoff(m).strftime("%H:%M") for m in MODES},
        "maxQty": MAX_QTY,
        "maxGuests": MAX_GUESTS,
    }


@dataclass
class OrderDraft:
    mode: str
    day: date
    slot: str
    name: str
    phone: str
    address: str
    comment: str
    items: list[tuple[Option, int]]
    guests: int = 0  # только для зала: на сколько человек накрыть

    @property
    def total(self) -> int:
        return sum(price(o, self.mode) * qty for o, qty in self.items)


def validate(payload: dict, now: datetime) -> tuple[OrderDraft | None, dict[str, str]]:
    errors: dict[str, str] = {}
    mode = str(payload.get("mode", ""))
    if mode not in MODES:
        errors["mode"] = "Выберите, как получить обед"
        mode = "delivery"

    try:
        day = date.fromisoformat(str(payload.get("day", "")))
    except ValueError:
        day = None
    if day is None or menu_for(day) is None:
        errors["day"] = "Выберите рабочий день"
    elif not is_open(day, mode, now):
        errors["day"] = f"На сегодня уже не успеем — принимаем до {cutoff(mode):%H:%M}"

    slot = str(payload.get("slot", ""))
    if slot not in SLOTS[mode]:
        errors["slot"] = "Выберите время"
    elif day is not None and "day" not in errors and slot not in open_slots(day, mode, now):
        lead = int(MIN_LEAD[mode].total_seconds() // 60)
        errors["slot"] = f"На {slot} уже не успеем — нужно минимум {lead} минут, выберите попозже"

    name = str(payload.get("name", "")).strip()
    if not 2 <= len(name) <= 80:
        errors["name"] = "Как к вам обращаться?"

    phone = normalize_phone(str(payload.get("phone", "")))
    if phone is None:
        errors["phone"] = "Нужен номер из 10–11 цифр, например 8 912 345-67-89"

    address = re.sub(r"\s+", " ", str(payload.get("address", ""))).strip()
    if mode == "delivery" and not 5 <= len(address) <= 200:
        errors["address"] = "Куда привезти: улица, дом, офис"
    if mode != "delivery":
        address = ""

    guests = 0
    if mode == "hall":
        try:
            guests = int(payload.get("guests", 0))
        except (TypeError, ValueError):
            guests = 0
        if not 1 <= guests <= MAX_GUESTS:
            errors["guests"] = f"На сколько человек накрыть: от 1 до {MAX_GUESTS}"

    items: list[tuple[Option, int]] = []
    raw_items = payload.get("items")
    for it in raw_items if isinstance(raw_items, list) else []:
        option = OPTIONS_BY_KIND.get(str(it.get("kind", ""))) if isinstance(it, dict) else None
        try:
            qty = int(it.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0
        if option is None or not 1 <= qty <= MAX_QTY:
            errors["items"] = "В заказе что-то не так — обновите страницу"
            break
        items.append((option, qty))
    if not items and "items" not in errors:
        errors["items"] = "Добавьте хотя бы один обед"

    comment = str(payload.get("comment", "")).strip()[:500]

    if errors:
        return None, errors
    return OrderDraft(mode, day, slot, name, phone, address, comment, items, guests), {}


def new_token() -> str:
    return secrets.token_urlsafe(9)
