"""Заказ комплексных обедов: что можно заказать, на какой день, почём.

Цены и «заказ на доставку до 11:00» — с афиш кафе (см. content.LUNCH).
Сознательные допущения, которые надо сверить с кафе:
- самовывоз принимаем до 14:00 того же дня (PICKUP_CUTOFF);
- слоты доставки — по полчаса с 12:00 до 14:00;
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

MODES = {"delivery": "Доставка", "pickup": "Самовывоз"}
CUTOFF = {"delivery": time(11, 0), "pickup": time(14, 0)}
SLOTS = {
    "delivery": ["12:00–12:30", "12:30–13:00", "13:00–13:30", "13:30–14:00"],
    "pickup": ["12:00", "12:30", "13:00", "13:30", "14:00"],
}
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


def details(option: Option, day: date) -> str:
    menu = menu_for(day) or {}
    return " · ".join(menu[p] for p in option.parts if p in menu)


def is_open(day: date, mode: str, now: datetime) -> bool:
    if menu_for(day) is None or day < now.date():
        return False
    return day > now.date() or now.time() < CUTOFF[mode]


def day_label(day: date, today: date) -> str:
    if day == today:
        return "Сегодня"
    if day == today + timedelta(days=1):
        return "Завтра"
    return WEEKDAYS_FULL[day.weekday()]


def order_days(now: datetime) -> list[dict]:
    """Ближайшие рабочие дни для выбора, начиная с сегодняшнего (если он рабочий)."""
    days, d = [], now.date()
    while len(days) < DAYS_AHEAD:
        if menu_for(d) is not None:
            days.append(
                {
                    "date": d.isoformat(),
                    "label": day_label(d, now.date()),
                    "short": f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}",
                    "open": {m: is_open(d, m, now) for m in MODES},
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
        "cutoff": {m: CUTOFF[m].strftime("%H:%M") for m in MODES},
        "maxQty": MAX_QTY,
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

    @property
    def total(self) -> int:
        return sum(price(o, self.mode) * qty for o, qty in self.items)


def validate(payload: dict, now: datetime) -> tuple[OrderDraft | None, dict[str, str]]:
    errors: dict[str, str] = {}
    mode = str(payload.get("mode", ""))
    if mode not in MODES:
        errors["mode"] = "Выберите доставку или самовывоз"
        mode = "delivery"

    try:
        day = date.fromisoformat(str(payload.get("day", "")))
    except ValueError:
        day = None
    if day is None or menu_for(day) is None:
        errors["day"] = "Выберите рабочий день"
    elif not is_open(day, mode, now):
        errors["day"] = f"На этот день заказ уже закрыт — принимаем до {CUTOFF[mode]:%H:%M}"

    slot = str(payload.get("slot", ""))
    if slot not in SLOTS[mode]:
        errors["slot"] = "Выберите время"

    name = str(payload.get("name", "")).strip()
    if not 2 <= len(name) <= 80:
        errors["name"] = "Как к вам обращаться?"

    phone = normalize_phone(str(payload.get("phone", "")))
    if phone is None:
        errors["phone"] = "Нужен номер из 10–11 цифр, например 8 912 345-67-89"

    address = re.sub(r"\s+", " ", str(payload.get("address", ""))).strip()
    if mode == "delivery" and not 5 <= len(address) <= 200:
        errors["address"] = "Куда привезти: улица, дом, офис"
    if mode == "pickup":
        address = ""

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
    return OrderDraft(mode, day, slot, name, phone, address, comment, items), {}


def new_token() -> str:
    return secrets.token_urlsafe(9)
